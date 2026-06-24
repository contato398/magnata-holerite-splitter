"""
src/services/secullum_ponto.py — Integração Secullum Ponto Web (Banco ID 149582)

Módulo isolado. Não importa app.py; reaproveita apenas os padrões de Airtable
(BASE_ID, throttle, raw requests) já usados no projeto.

Responsabilidades:
  1. Autenticação: troca usuário/senha por token Bearer (com cache de expiração).
  2. Sincronização: cadastra novos funcionários no Ponto Web via POST (CPF obrigatório).
  3. Varredura: lê os cálculos do período e gera alertas para
        - Batidas Ímpares (nº de batidas no dia é ímpar)
        - Desvios de Carga Horária maiores que 02:00
  4. Alertas: gravados na estrutura atual do Airtable, na tabela "Pendências/Revisar",
     vinculados ao Funcionário correspondente (casamento por CPF).

Exposto como Blueprint Flask (`secullum_bp`). Para integrar ao app principal:

    from src.services.secullum_ponto import secullum_bp
    app.register_blueprint(secullum_bp)

Variáveis de ambiente esperadas (configurar no Render — nunca commitar segredos):
    AIRTABLE_API_KEY        já existente no projeto
    SECULLUM_USUARIO        login (e-mail) da conta Secullum
    SECULLUM_SENHA          senha da conta Secullum
    SECULLUM_BANCO_ID       opcional; default "149582"
    SECULLUM_CLIENT_ID      opcional; default "3" (cliente OAuth do Ponto Web)
    SECULLUM_ALERTA_STATUS  opcional; status aplicado às pendências (default "Aberta")

NOTA IMPORTANTE sobre a API Secullum:
    Os endpoints/headers seguem o padrão público da Integração Externa do Ponto Web
    (autenticador.secullum.com.br/Token + pontowebapi.secullum.com.br/IntegracaoExterna,
    header `secullumidbancoselecionado`). Os nomes de campos retornados pelo endpoint
    de Cálculos podem variar conforme a configuração do banco; por isso a leitura é
    defensiva e os nomes de coluna são configuráveis (ver SECULLUM_COL_*). Confirme
    contra a conta real antes do primeiro disparo em produção.
"""

import os
import re
import time
import logging
from datetime import datetime, date, timedelta

import requests
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

# ── Configuração Secullum ──────────────────────────────────────────────────────
SECULLUM_USUARIO   = os.environ.get('SECULLUM_USUARIO', '')
SECULLUM_SENHA     = os.environ.get('SECULLUM_SENHA', '')
SECULLUM_BANCO_ID  = os.environ.get('SECULLUM_BANCO_ID', '149582')
SECULLUM_CLIENT_ID = os.environ.get('SECULLUM_CLIENT_ID', '3')

AUTH_URL = 'https://autenticador.secullum.com.br/Token'
API_BASE = 'https://pontowebapi.secullum.com.br/IntegracaoExterna'

# Nomes das colunas de cálculo (configuráveis caso o banco use rótulos diferentes).
# O "desvio de carga horária" é lido como o saldo do dia (extras - faltas).
SECULLUM_COL_SALDO  = os.environ.get('SECULLUM_COL_SALDO', 'Saldo')
SECULLUM_COL_FALTAS = os.environ.get('SECULLUM_COL_FALTAS', 'Faltas')
SECULLUM_COL_EXTRAS = os.environ.get('SECULLUM_COL_EXTRAS', 'Extras')

# Limite do desvio: 02:00 = 120 minutos. Alerta dispara para desvios > este valor.
THRESHOLD_DESVIO_MIN = 120

# ── Airtable (mesmos IDs do app.py) ─────────────────────────────────────────────
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY', '')
BASE_ID    = 'appaCpIVj7Q97VhFy'
TABLE_FUNC = 'tblNd8G66kjwos3eP'   # Funcionários
TABLE_PEND = 'tblRkJBL6Wwf4fxVC'   # Pendências/Revisar  ← alertas vivem aqui

F_FUNC_CPF      = 'fld0Y3bXdArkSIJxo'
F_FUNC_NOME     = 'fld2fSiomk9AOLGDb'   # Nome Completo
F_FUNC_STATUS   = 'fld5T04dlg1Yt6Xj8'
F_FUNC_CODIGO   = 'fldCtZHUjJBi7JQXb'
F_FUNC_PIS      = 'fldNNWb5BLgdBdsJO'
F_FUNC_ADMISSAO = 'fld5L1djmJugvLe8c'

F_PEND_NOME   = 'fldovcs6bySCshoXI'   # Pendência (primary, texto)
F_PEND_STATUS = 'fldf1an8HCV2DxEwk'   # Status (singleSelect)
F_PEND_TIPO   = 'fldyZgyB5F5fv6kUX'   # Tipo de Problema (singleSelect)
F_PEND_FUNC   = 'fldNrmGLfas2Wf4kb'   # Funcionário (link)
F_PEND_OBS    = 'fld2bqGLlotCVRBn5'   # Observação (multilineText)
F_PEND_DATA   = 'fldRolmP0rSbJevUZ'   # Data (dateTime)

ALERTA_STATUS = os.environ.get('SECULLUM_ALERTA_STATUS', 'Aberta')
TIPO_BATIDA_IMPAR = 'Batida Ímpar (Ponto)'
TIPO_DESVIO_CARGA = 'Desvio de Carga Horária (Ponto)'

# ── Rate limiter Airtable (espelha _at_throttle do app.py) ──────────────────────
_last_at_call = 0.0


def _at_throttle():
    global _last_at_call
    now = time.monotonic()
    gap = now - _last_at_call
    if gap < 0.23:
        time.sleep(0.23 - gap)
    _last_at_call = time.monotonic()


def _at_headers():
    return {
        'Authorization': f'Bearer {AIRTABLE_API_KEY}',
        'Content-Type': 'application/json',
    }


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ 1. AUTENTICAÇÃO — credenciais → token Bearer (com cache)                   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

_token_cache = {'access_token': None, 'expira_em': 0.0}


def get_token(forcar: bool = False) -> str:
    """Retorna um access_token válido, renovando quando expirado.

    Troca usuário/senha (grant_type=password) por um Bearer token no autenticador
    da Secullum. O token é cacheado em memória até ~60s antes de expirar.
    """
    agora = time.monotonic()
    if not forcar and _token_cache['access_token'] and agora < _token_cache['expira_em']:
        return _token_cache['access_token']

    if not SECULLUM_USUARIO or not SECULLUM_SENHA:
        raise RuntimeError('SECULLUM_USUARIO/SECULLUM_SENHA não configurados no ambiente.')

    payload = {
        'grant_type': 'password',
        'username': SECULLUM_USUARIO,
        'password': SECULLUM_SENHA,
        'client_id': SECULLUM_CLIENT_ID,
    }
    r = requests.post(
        AUTH_URL,
        data=payload,  # OAuth token endpoint usa form-urlencoded
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=30,
    )
    if not r.ok:
        logger.error(f'[SECULLUM] Falha na autenticação HTTP {r.status_code}: {r.text[:300]}')
    r.raise_for_status()

    dados = r.json()
    token = dados['access_token']
    expira_seg = int(dados.get('expires_in', 3600))
    _token_cache['access_token'] = token
    _token_cache['expira_em'] = agora + max(expira_seg - 60, 60)
    logger.info('[SECULLUM] Token renovado (expira em ~%ss).', expira_seg)
    return token


def _secullum_headers() -> dict:
    return {
        'Authorization': f'Bearer {get_token()}',
        'secullumidbancoselecionado': str(SECULLUM_BANCO_ID),
        'Content-Type': 'application/json',
    }


def _secullum_request(metodo: str, caminho: str, **kwargs):
    """Wrapper com refresh automático de token em caso de 401."""
    url = f'{API_BASE}/{caminho.lstrip("/")}'
    r = requests.request(metodo, url, headers=_secullum_headers(), timeout=60, **kwargs)
    if r.status_code == 401:
        logger.info('[SECULLUM] 401 — renovando token e repetindo.')
        get_token(forcar=True)
        r = requests.request(metodo, url, headers=_secullum_headers(), timeout=60, **kwargs)
    if not r.ok:
        logger.error(f'[SECULLUM] {metodo} {caminho} → HTTP {r.status_code}: {r.text[:400]}')
    r.raise_for_status()
    return r.json() if r.text else None


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ 2. SINCRONIZAÇÃO — cadastro de novo funcionário (CPF obrigatório)          ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def _so_digitos(s: str) -> str:
    return re.sub(r'\D', '', s or '')


def listar_funcionarios_secullum() -> list:
    """Lista os funcionários cadastrados no banco selecionado do Ponto Web."""
    dados = _secullum_request('GET', 'Funcionarios')
    return dados if isinstance(dados, list) else dados.get('Funcionarios', [])


def buscar_funcionario_secullum_por_cpf(cpf: str):
    """Retorna o registro Secullum cujo CPF bate, ou None."""
    alvo = _so_digitos(cpf)
    for f in listar_funcionarios_secullum():
        if _so_digitos(str(f.get('Cpf', ''))) == alvo:
            return f
    return None


def sincronizar_funcionario(cpf: str, nome: str = None, numero: str = None,
                            pis: str = None, admissao: str = None) -> dict:
    """Cadastra (ou retorna o existente) um funcionário no Ponto Web via POST.

    CPF é obrigatório. Se o funcionário já existe no Secullum (mesmo CPF), não
    duplica — retorna {'status': 'existente', ...}.

    Args:
        cpf: CPF (com ou sem máscara). Obrigatório.
        nome: nome completo; se omitido, busca em Funcionários do Airtable.
        numero: matrícula/folha; default = Código do Airtable, senão dígitos do CPF.
        pis: PIS/NIS.
        admissao: data de admissão 'YYYY-MM-DD'.
    """
    cpf_num = _so_digitos(cpf)
    if not cpf_num:
        raise ValueError('CPF é obrigatório para sincronizar funcionário.')

    # Completa dados a partir do Airtable quando não fornecidos.
    func_at = _buscar_funcionario_airtable_por_cpf(cpf_num)
    campos_at = (func_at or {}).get('fields', {})
    nome = nome or campos_at.get('Nome Completo') or campos_at.get('Funcionário')
    if not nome:
        raise ValueError(f'Nome não informado e CPF {cpf} não encontrado no Airtable.')
    numero = numero or campos_at.get('Código') or cpf_num
    pis = pis or campos_at.get('PIS')
    admissao = admissao or campos_at.get('Data de Admissão')

    # Não duplica se já existir no Secullum.
    existente = buscar_funcionario_secullum_por_cpf(cpf_num)
    if existente:
        logger.info('[SECULLUM] Funcionário CPF %s já existe (Id=%s).', cpf, existente.get('Id'))
        return {'status': 'existente', 'funcionario': existente}

    payload = {
        'Id': 0,
        'Nome': nome,
        'NumeroFolha': str(numero),
        'Cpf': cpf_num,
        'Demitido': False,
    }
    if pis:
        payload['Pis'] = _so_digitos(pis)
    if admissao:
        payload['DataAdmissao'] = admissao

    criado = _secullum_request('POST', 'Funcionarios', json=payload)
    logger.info('[SECULLUM] Funcionário %s (CPF %s) sincronizado.', nome, cpf)
    return {'status': 'criado', 'funcionario': criado}


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ 3. VARREDURA — batidas ímpares e desvios de carga horária > 02:00          ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def _hhmm_para_minutos(valor) -> int | None:
    """Converte 'HH:MM' (com sinal) ou número de minutos em inteiro de minutos.

    Aceita '02:30', '-01:15', 90 (int = minutos) ou '90'. Retorna None se vazio.
    """
    if valor is None or valor == '':
        return None
    if isinstance(valor, (int, float)):
        return int(valor)
    s = str(valor).strip()
    sinal = -1 if s.startswith('-') else 1
    s = s.lstrip('+-')
    if ':' in s:
        try:
            h, m = s.split(':')[:2]
            return sinal * (int(h) * 60 + int(m))
        except ValueError:
            return None
    try:
        return sinal * int(round(float(s.replace(',', '.'))))
    except ValueError:
        return None


def _minutos_para_hhmm(minutos: int) -> str:
    sinal = '-' if minutos < 0 else ''
    minutos = abs(int(minutos))
    return f'{sinal}{minutos // 60:02d}:{minutos % 60:02d}'


def obter_calculos(funcionario_id, data_inicio: str, data_fim: str) -> list:
    """Retorna os cálculos diários de um funcionário no período (lista de dias)."""
    payload = {
        'FuncionarioId': funcionario_id,
        'DataInicio': data_inicio,
        'DataFim': data_fim,
    }
    dados = _secullum_request('POST', 'Calculos', json=payload)
    if isinstance(dados, list):
        return dados
    # Algumas versões retornam {'Dias': [...]} ou {'Calculos': [...]}
    return dados.get('Dias') or dados.get('Calculos') or []


def _coluna(dia: dict, nome: str):
    """Lê uma coluna de cálculo de forma tolerante a formato.

    Suporta tanto {'Colunas': {'Saldo': '02:00'}} quanto chave direta no dia.
    """
    colunas = dia.get('Colunas') or dia.get('colunas') or {}
    if nome in colunas:
        return colunas[nome]
    # fallback: chave direta no objeto-dia
    return dia.get(nome)


def _contar_batidas(dia: dict) -> int:
    batidas = dia.get('Batidas') or dia.get('batidas') or []
    if isinstance(batidas, list):
        return len([b for b in batidas if b not in (None, '', '00:00')])
    return 0


def _desvio_minutos(dia: dict) -> int | None:
    """Desvio de carga horária do dia, em minutos (abs).

    Prioriza a coluna de Saldo; se ausente, deriva de Extras - Faltas.
    """
    saldo = _hhmm_para_minutos(_coluna(dia, SECULLUM_COL_SALDO))
    if saldo is not None:
        return abs(saldo)
    extras = _hhmm_para_minutos(_coluna(dia, SECULLUM_COL_EXTRAS)) or 0
    faltas = _hhmm_para_minutos(_coluna(dia, SECULLUM_COL_FALTAS)) or 0
    if extras == 0 and faltas == 0:
        return None
    return abs(extras - faltas)


def _data_do_dia(dia: dict) -> str:
    raw = dia.get('Data') or dia.get('data') or ''
    # normaliza ISO 'YYYY-MM-DDTHH:MM:SS' → 'YYYY-MM-DD'
    return str(raw)[:10]


def varrer_pendencias(data_inicio: str, data_fim: str,
                      dry_run: bool = False, limit: int = None) -> dict:
    """Varre o período e gera alertas de Batidas Ímpares e Desvios > 02:00.

    Para cada funcionário ativo no Ponto Web, busca os cálculos diários e
    cria pendências no Airtable (tabela Pendências/Revisar). Idempotente: não
    recria uma pendência cujo título determinístico já exista.

    Args:
        data_inicio, data_fim: 'YYYY-MM-DD'.
        dry_run: se True, só relata o que faria (não grava no Airtable).
        limit: nº máximo de funcionários a processar (debug).

    Returns:
        Resumo com contadores e a lista de alertas detectados.
    """
    funcionarios = listar_funcionarios_secullum()
    if limit:
        funcionarios = funcionarios[:limit]

    alertas = []
    criados = 0
    pulados_existentes = 0

    for f in funcionarios:
        fid = f.get('Id')
        nome = f.get('Nome', '')
        cpf = _so_digitos(str(f.get('Cpf', '')))
        if f.get('Demitido'):
            continue

        try:
            dias = obter_calculos(fid, data_inicio, data_fim)
        except Exception as exc:
            logger.warning('[SECULLUM] Cálculos falharam p/ %s (Id=%s): %s', nome, fid, exc)
            continue

        for dia in dias:
            data_dia = _data_do_dia(dia)
            n_batidas = _contar_batidas(dia)
            desvio = _desvio_minutos(dia)

            # — Batidas ímpares —
            if n_batidas and n_batidas % 2 != 0:
                alertas.append(_montar_alerta(
                    tipo=TIPO_BATIDA_IMPAR, nome=nome, cpf=cpf, data_dia=data_dia,
                    obs=f'{n_batidas} batidas registradas no dia {data_dia} '
                        f'(número ímpar — provável batida faltante).',
                ))

            # — Desvio de carga horária > 02:00 —
            if desvio is not None and desvio > THRESHOLD_DESVIO_MIN:
                alertas.append(_montar_alerta(
                    tipo=TIPO_DESVIO_CARGA, nome=nome, cpf=cpf, data_dia=data_dia,
                    obs=f'Desvio de carga horária de {_minutos_para_hhmm(desvio)} '
                        f'no dia {data_dia} (limite: 02:00).',
                ))

    # Persiste no Airtable.
    for alerta in alertas:
        if dry_run:
            continue
        try:
            if _alerta_existe(alerta['titulo']):
                pulados_existentes += 1
                continue
            criar_alerta_pendencia(alerta)
            criados += 1
        except Exception as exc:
            logger.error('[SECULLUM] Falha ao gravar alerta "%s": %s', alerta['titulo'], exc)

    resumo = {
        'periodo': f'{data_inicio}..{data_fim}',
        'funcionarios_processados': len(funcionarios),
        'alertas_detectados': len(alertas),
        'alertas_criados': criados,
        'alertas_ja_existentes': pulados_existentes,
        'dry_run': dry_run,
        'alertas': alertas,
    }
    logger.info('[SECULLUM] Varredura: %s', {k: v for k, v in resumo.items() if k != 'alertas'})
    return resumo


def _montar_alerta(tipo: str, nome: str, cpf: str, data_dia: str, obs: str) -> dict:
    # Título determinístico → permite deduplicação entre varreduras.
    titulo = f'[Ponto] {tipo} — {nome} — {data_dia}'
    return {'titulo': titulo, 'tipo': tipo, 'nome': nome, 'cpf': cpf,
            'data_dia': data_dia, 'obs': obs}


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ 4. ALERTAS → Airtable (tabela Pendências/Revisar)                          ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def _buscar_funcionario_airtable_por_cpf(cpf: str):
    """Retorna o registro completo do Funcionário (ou None) casando por CPF.

    Espelha a estratégia de fórmulas do app.py (com e sem máscara).
    """
    cpf_num = _so_digitos(cpf)
    headers = {'Authorization': f'Bearer {AIRTABLE_API_KEY}'}
    for formula in (f'{{CPF}}="{cpf}"', f'{{CPF}}="{cpf_num}"', f'{{num-cpf}}={cpf_num}'):
        _at_throttle()
        try:
            r = requests.get(
                f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}',
                headers=headers,
                params={'filterByFormula': formula, 'maxRecords': 1},
                timeout=30,
            )
            if r.ok and r.json().get('records'):
                return r.json()['records'][0]
        except requests.exceptions.RequestException as exc:
            logger.warning('[AT] Erro buscando CPF %s: %s', cpf, exc)
    return None


def _alerta_existe(titulo: str) -> bool:
    """True se já houver uma pendência com este título (evita duplicar)."""
    _at_throttle()
    # escapa aspas duplas para a fórmula
    titulo_esc = titulo.replace('"', '\\"')
    r = requests.get(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_PEND}',
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
        params={'filterByFormula': f'{{Pendência}}="{titulo_esc}"', 'maxRecords': 1},
        timeout=30,
    )
    return bool(r.ok and r.json().get('records'))


def criar_alerta_pendencia(alerta: dict) -> str:
    """Cria uma pendência no Airtable a partir de um alerta de ponto.

    Vincula ao Funcionário quando o CPF é encontrado. Usa typecast para os
    singleSelect (Status / Tipo de Problema), criando a opção se ainda não existir.
    """
    campos = {
        F_PEND_NOME: alerta['titulo'],
        F_PEND_OBS:  alerta['obs'],
        F_PEND_DATA: datetime.now().isoformat(timespec='seconds'),
        F_PEND_TIPO: alerta['tipo'],
    }
    if ALERTA_STATUS:
        campos[F_PEND_STATUS] = ALERTA_STATUS

    func = _buscar_funcionario_airtable_por_cpf(alerta['cpf']) if alerta.get('cpf') else None
    if func:
        campos[F_PEND_FUNC] = [func['id']]

    _at_throttle()
    r = requests.post(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_PEND}',
        headers=_at_headers(),
        json={'fields': campos, 'typecast': True},
        timeout=30,
    )
    if not r.ok:
        logger.error('[AT] Falha criando pendência HTTP %s: %s', r.status_code, r.text[:400])
    r.raise_for_status()
    return r.json()['id']


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ Blueprint Flask — rotas de integração                                      ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

secullum_bp = Blueprint('secullum', __name__, url_prefix='/secullum')


@secullum_bp.route('/health', methods=['GET'])
def secullum_health():
    return jsonify({
        'servico': 'secullum-ponto',
        'banco_id': SECULLUM_BANCO_ID,
        'credenciais_ok': bool(SECULLUM_USUARIO and SECULLUM_SENHA),
        'limite_desvio': _minutos_para_hhmm(THRESHOLD_DESVIO_MIN),
    })


@secullum_bp.route('/sincronizar', methods=['POST', 'OPTIONS'])
def rota_sincronizar():
    """Sincroniza um novo funcionário no Ponto Web. CPF obrigatório.

    Body JSON: {"cpf": "...", "nome": "...", "numero": "...", "pis": "...",
                "admissao": "YYYY-MM-DD"}
    """
    if request.method == 'OPTIONS':
        return ('', 204)
    body = request.get_json(silent=True) or {}
    cpf = body.get('cpf')
    if not cpf or not _so_digitos(cpf):
        return jsonify({'erro': 'CPF é obrigatório.'}), 400
    try:
        resultado = sincronizar_funcionario(
            cpf=cpf, nome=body.get('nome'), numero=body.get('numero'),
            pis=body.get('pis'), admissao=body.get('admissao'),
        )
        return jsonify(resultado), (201 if resultado.get('status') == 'criado' else 200)
    except (ValueError, RuntimeError) as exc:
        return jsonify({'erro': str(exc)}), 400
    except requests.exceptions.HTTPError as exc:
        return jsonify({'erro': 'Falha na API Secullum', 'detalhe': str(exc)}), 502


@secullum_bp.route('/varrer', methods=['POST', 'OPTIONS'])
def rota_varrer():
    """Varre o período e gera alertas (batidas ímpares / desvios > 02:00).

    Body JSON: {"data_inicio": "YYYY-MM-DD", "data_fim": "YYYY-MM-DD",
                "dry_run": false, "limit": null}
    Sem datas → mês corrente até hoje.
    """
    if request.method == 'OPTIONS':
        return ('', 204)
    body = request.get_json(silent=True) or {}
    hoje = date.today()
    data_inicio = body.get('data_inicio') or hoje.replace(day=1).isoformat()
    data_fim = body.get('data_fim') or hoje.isoformat()
    try:
        resumo = varrer_pendencias(
            data_inicio=data_inicio, data_fim=data_fim,
            dry_run=bool(body.get('dry_run', False)), limit=body.get('limit'),
        )
        return jsonify(resumo), 200
    except requests.exceptions.HTTPError as exc:
        return jsonify({'erro': 'Falha na API Secullum', 'detalhe': str(exc)}), 502
