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
        - Folga Trabalhada (jornada real em dia de FOLGA/Feriado real da
          escala, marcado pelo próprio /Calcular) e Troca de Plantão cruzada
          (falta de zero batidas casada com a Folga Trabalhada de outro
          colaborador no mesmo dia) — 100% baseado na escala, sem depender de
          local de trabalho cadastrado no Airtable.
  4. Bônus de Assiduidade: avalia por CPF se houve falta, atraso na entrada
     ou saída antecipada (> tolerância) no período, comparando a jornada real
     contra o horário programado (Horario.Descricao).
  5. Alertas: gravados na estrutura atual do Airtable, na tabela "Pendências/Revisar",
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
import traceback
import unicodedata
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
# Base oficial da Integração Externa do Ponto Web (confirmada na doc/exemplo Secullum).
API_BASE = 'https://pontowebintegracaoexterna.secullum.com.br/IntegracaoExterna'

# Nomes das colunas de cálculo (configuráveis caso o banco use rótulos diferentes).
SECULLUM_COL_FALTAS = os.environ.get('SECULLUM_COL_FALTAS', 'Faltas')
SECULLUM_COL_EXTRAS = os.environ.get('SECULLUM_COL_EXTRAS', 'Extras')
# Atraso na entrada / saída antecipada — usar o que a própria Secullum já
# calcula (testado contra dado real), em vez de derivar do Horario.Descricao:
# esse texto se provou não confiável 3x nesta integração (tag PAR/ÍMPAR
# invertida, "Normais" sempre vazio em vários horários, e a faixa "07h-19h"
# de um colaborador cujas batidas reais são todas no período 19h-07h).
SECULLUM_COL_ATRASO = os.environ.get('SECULLUM_COL_ATRASO', 'Atras.')
SECULLUM_COL_ADIANTAMENTO = os.environ.get('SECULLUM_COL_ADIANTAMENTO', 'Adian.')

# Base do "desvio de carga horária":
#   faltas → só horas faltantes (anomalias reais de jornada; default — evita ruído 12x36)
#   ambos  → |Extras - Faltas| (literal; em escalas 12x36 gera muitos falsos positivos)
#   extras → só horas extras
# Decisão de produto (24/06/2026): focar em faltas para não inundar com extras de escala.
SECULLUM_DESVIO_BASE = os.environ.get('SECULLUM_DESVIO_BASE', 'faltas').lower()

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
F_FUNC_BONUS_JUN2026 = 'fldPMJrQP5IAAEMxL'   # "Bônus Assiduidade Jun/2026" (criado v2.55)

F_PEND_NOME   = 'fldovcs6bySCshoXI'   # Pendência (primary, texto)
F_PEND_STATUS = 'fldf1an8HCV2DxEwk'   # Status (singleSelect)
F_PEND_TIPO   = 'fldyZgyB5F5fv6kUX'   # Tipo de Problema (singleSelect)
F_PEND_FUNC   = 'fldNrmGLfas2Wf4kb'   # Funcionário (link)
F_PEND_OBS    = 'fld2bqGLlotCVRBn5'   # Observação (multilineText)
F_PEND_DATA   = 'fldRolmP0rSbJevUZ'   # Data (dateTime)

ALERTA_STATUS = os.environ.get('SECULLUM_ALERTA_STATUS', 'Aberta')
TIPO_BATIDA_IMPAR = 'Batida Ímpar (Ponto)'
TIPO_DESVIO_CARGA = 'Desvio de Carga Horária (Ponto)'
# Cruzamento jornada real x escala teórica (FOLGA/Feriado real) — não depende de
# local de trabalho (Airtable); só da própria escala resolvida pela Secullum.
TIPO_FOLGA_TRABALHADA = 'Folga Trabalhada (Banco de Horas / Extra)'
# Fallback ambíguo: pareamento achado mas saldo de plantões não decide o motivo
# (v2.55 normalmente resolve para TIPO_TROCA_INFORMAL ou TIPO_COBERTURA_EMERGENCIA).
TIPO_TROCA_FALTOU = 'Troca de Plantão (Faltou / Cedido)'
TIPO_TROCA_COBRIU = 'Troca de Plantão (Cobriu / Dobrou)'
# v2.55 — distinção jurídica via saldo de plantões do mês (diretriz da diretoria).
TIPO_TROCA_INFORMAL = 'Troca de Plantão (Informal)'
TIPO_COBERTURA_EMERGENCIA = 'Dobra / Cobertura de Emergência (FT)'

# Plantão noturno: entrada a partir desta hora indica jornada que vira o dia.
HORA_INICIO_NOTURNO = int(os.environ.get('SECULLUM_HORA_NOTURNO', '18'))

# Bônus de Assiduidade: perde com qualquer falta/atraso/saída antecipada > tolerância.
BONUS_ASSIDUIDADE_VALOR = os.environ.get('SECULLUM_BONUS_ASSIDUIDADE', '100,00')
BONUS_TOLERANCIA_MIN = int(os.environ.get('SECULLUM_BONUS_TOLERANCIA_MIN', '5'))

# ── v2.55: Arquitetura de intervalos por posto e função (diretriz da diretoria) ─
# IDs (não texto!) dos 5 postos de exceção — "100% com intervalo" independente da
# função. Resolvidos contra a tabela Locais do Airtable (confirmados em sessão
# anterior); usar ID em vez de nome evita o mesmo tipo de erro de texto não
# confiável já visto 3x com Horario.Descricao.
EXCEPTION_POSTO_IDS = {
    'rec7sjIAiKZd0ermb',  # MORADAS DO SOL
    'rechZpE1xGvFXUNyL',  # CASTROLANDA
    'recd8OPca3z9dk2fq',  # LAGO DOS IPES
    'reclQfhuQSPVLZgB3',  # UNIMED - VIRGILIO
    'recZKE9y6Hn1Hl1Kg',  # UNIMED - SHOPPING
}
# Palavras (texto normalizado) que indicam função SOLO (turno 12x36 sem intervalo,
# expectativa de só 2 batidas: Entrada/Saída). Tudo que não bater aqui (Limpeza,
# Zeladoria, Jardinagem, Administrativo, Serviços Gerais etc.) tem intervalo.
_PALAVRAS_FUNCAO_SOLO = ('CONTROLADOR', 'PORTARIA', 'PORTEIRO', 'PERIMETRO')
N_BATIDAS_COM_INTERVALO = 4
N_BATIDAS_SOLO = 2

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


SECULLUM_RETRIES = int(os.environ.get('SECULLUM_RETRIES', '4'))
# Intervalo mínimo entre chamadas à API Secullum (evita 429 Too Many Requests).
SECULLUM_MIN_INTERVAL = float(os.environ.get('SECULLUM_MIN_INTERVAL', '1.0'))
_last_secullum_call = 0.0


def _secullum_throttle():
    """Espaça as chamadas à API Secullum para não estourar o rate limit (429)."""
    global _last_secullum_call
    gap = time.monotonic() - _last_secullum_call
    if gap < SECULLUM_MIN_INTERVAL:
        time.sleep(SECULLUM_MIN_INTERVAL - gap)
    _last_secullum_call = time.monotonic()


def _espera_429(resp, tentativa: int) -> float:
    """Quanto esperar após um 429: respeita Retry-After, senão backoff (cap 30s)."""
    ra = resp.headers.get('Retry-After', '')
    if ra.strip().isdigit():
        return min(float(ra), 30.0)
    return min(3.0 * tentativa, 30.0)


def _secullum_request(metodo: str, caminho: str, **kwargs):
    """Wrapper resiliente: throttle + refresh de token em 401 + retry com backoff.

    Faz throttle client-side antes de cada chamada. Repete em falhas transitórias
    (timeout, conexão, 429, 502/503/504) até SECULLUM_RETRIES vezes, respeitando
    Retry-After no 429. Erros 4xx (exceto 401/429) propagam de imediato.
    """
    url = f'{API_BASE}/{caminho.lstrip("/")}'
    kwargs.setdefault('timeout', 60)
    ultimo = None
    for tentativa in range(1, SECULLUM_RETRIES + 1):
        try:
            _secullum_throttle()
            r = requests.request(metodo, url, headers=_secullum_headers(), **kwargs)
            if r.status_code == 401:
                logger.info('[SECULLUM] 401 — renovando token e repetindo.')
                get_token(forcar=True)
                _secullum_throttle()
                r = requests.request(metodo, url, headers=_secullum_headers(), **kwargs)
            if r.status_code == 429:
                espera = _espera_429(r, tentativa)
                ultimo = 'HTTP 429'
                logger.warning('[SECULLUM] 429 em %s — aguardando %.1fs (tentativa %s/%s)',
                               caminho, espera, tentativa, SECULLUM_RETRIES)
                time.sleep(espera)
                continue
            if r.status_code in (502, 503, 504):
                ultimo = f'HTTP {r.status_code}'
                logger.warning('[SECULLUM] %s %s → %s (tentativa %s/%s)',
                               metodo, caminho, ultimo, tentativa, SECULLUM_RETRIES)
                time.sleep(1.5 * tentativa)
                continue
            if not r.ok:
                logger.error(f'[SECULLUM] {metodo} {caminho} → HTTP {r.status_code}: {r.text[:400]}')
            r.raise_for_status()
            return r.json() if r.text else None
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            ultimo = exc
            logger.warning('[SECULLUM] %s %s falhou (tentativa %s/%s): %s',
                           metodo, caminho, tentativa, SECULLUM_RETRIES, exc)
            time.sleep(1.5 * tentativa)
    raise requests.exceptions.RequestException(
        f'Secullum {metodo} {caminho} falhou após {SECULLUM_RETRIES} tentativas: {ultimo}')


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

def periodo_folha(ano: int, mes: int) -> tuple:
    """Janela oficial de apuração da folha (v2.56, decisão da diretoria).

    A Magnata NÃO fecha o ponto no mês comercial cheio (01 a 30/31). O corte
    oficial é do dia 28 do mês anterior ao dia 28 do mês de competência — ex.:
    competência Junho/2026 → 28/05/2026 a 28/06/2026. Retorna (inicio, fim) ISO.
    """
    fim = date(ano, mes, 28)
    if mes == 1:
        inicio = date(ano - 1, 12, 28)
    else:
        inicio = date(ano, mes - 1, 28)
    return inicio.isoformat(), fim.isoformat()


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


# Resposta do /Calcular é colunar: {'Colunas': [...], 'Linhas': [{'Key':data,'Value':[...]}]}.
# Colunas de batida = "Entrada N" / "Saída N"; valor é "HH:MM" (ou "FOLGA"/vazio).
_RE_COL_BATIDA = re.compile(r'^(Entrada|Sa[íi]da)\s*\d+$', re.IGNORECASE)
_RE_HORA = re.compile(r'^\d{1,2}:\d{2}$')


def obter_calculos(cpf: str, data_inicio: str, data_fim: str) -> dict:
    """Retorna o cálculo do período no formato colunar do Ponto Web.

    Endpoint oficial: POST /IntegracaoExterna/Calcular. Filtra por CPF,
    com dataInicial/dataFinal (date-time). Retorna {'Colunas':[...], 'Linhas':[...]}.
    """
    payload = {
        'funcionarioCpf': _so_digitos(cpf),
        'dataInicial': f'{data_inicio}T00:00:00',
        'dataFinal': f'{data_fim}T00:00:00',
    }
    dados = _secullum_request('POST', 'Calcular', json=payload)
    return dados if isinstance(dados, dict) else {}


def _linhas_calculo(calc: dict):
    """Itera (data_iso, {coluna: valor}) sobre cada dia da resposta do /Calcular."""
    colunas = calc.get('Colunas') or []
    for linha in calc.get('Linhas') or []:
        valores = linha.get('Value') or []
        yield str(linha.get('Key', ''))[:10], dict(zip(colunas, valores))


def _contar_batidas(mapa: dict) -> int:
    """Conta os horários de batida (Entrada/Saída N) efetivamente preenchidos no dia."""
    n = 0
    for col, val in mapa.items():
        if _RE_COL_BATIDA.match(col) and isinstance(val, str) and _RE_HORA.match(val.strip()):
            n += 1
    return n


def _desvio_minutos(mapa: dict, base: str = None) -> int | None:
    """Desvio de carga horária do dia, em minutos (abs).

    Base = SECULLUM_DESVIO_BASE (ambos|faltas|extras), com override opcional.
    None quando não há desvio na base escolhida.
    """
    base = base or SECULLUM_DESVIO_BASE
    extras = _hhmm_para_minutos(mapa.get(SECULLUM_COL_EXTRAS)) or 0
    faltas = _hhmm_para_minutos(mapa.get(SECULLUM_COL_FALTAS)) or 0
    if base == 'faltas':
        val = faltas
    elif base == 'extras':
        val = extras
    else:
        val = abs(extras - faltas)
    return val if val else None


def _faltas_minutos(mapa: dict) -> int:
    return _hhmm_para_minutos(mapa.get(SECULLUM_COL_FALTAS)) or 0


def _trabalhou(mapa: dict) -> bool:
    """True se houve presença real no dia (alguma batida ou horas normais > 0)."""
    if _contar_batidas(mapa) > 0:
        return True
    return (_hhmm_para_minutos(mapa.get('Normais')) or 0) > 0


def _horario_noturno(func: dict) -> bool:
    """Heurística: plantão noturno (vira o dia) se a 1ª hora do horário é >= 18h.

    Ex.: "12x36 19h - 07h IMPAR" → entrada 19h → noturno.
    """
    desc = ((func.get('Horario') or {}).get('Descricao') or '')
    m = re.search(r'(\d{1,2})\s*[hH:]', desc)
    return bool(m and int(m.group(1)) >= HORA_INICIO_NOTURNO)


def _normalizar_texto(s: str) -> str:
    """Maiúsculas, sem acento, espaços/hífens colapsados — p/ matching de função."""
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[\s\-_/]+', ' ', s).strip().upper()


def _funcao_e_solo(cargo_texto: str) -> bool:
    """True se o cargo/função é turno solo 12x36 (Controlador de Acesso/Portaria)."""
    t = _normalizar_texto(cargo_texto)
    return any(p in t for p in _PALAVRAS_FUNCAO_SOLO)


def _tem_intervalo(postos_ids: set, cargo_texto: str) -> bool:
    """Regra de exceção por posto (100% intervalo, qualquer função) > regra geral
    por função (Limpeza/Zeladoria/Jardinagem/Administrativo = intervalo;
    Controlador de Acesso/Portaria = turno solo, sem intervalo)."""
    if postos_ids & EXCEPTION_POSTO_IDS:
        return True
    return not _funcao_e_solo(cargo_texto)


def _mapa_posto_cargo_airtable() -> dict:
    """cpf -> {'postos': set(record IDs), 'cargo': str} do Funcionários (Airtable).

    Usado só para decidir tem_intervalo (v2.55). Não consome cota da Secullum.
    """
    info_cpf = {}
    url = f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}'
    params = {'fields[]': ['CPF', 'Locais de trabalho', 'Cargo'], 'pageSize': 100}
    offset = None
    while True:
        if offset:
            params['offset'] = offset
        _at_throttle()
        r = requests.get(url, headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
                         params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for rec in data.get('records', []):
            fl = rec.get('fields', {})
            cpf = _so_digitos(str(fl.get('CPF', '')))
            if not cpf:
                continue
            info_cpf[cpf] = {
                'postos': set(fl.get('Locais de trabalho') or []),
                'cargo': fl.get('Cargo', ''),
            }
        offset = data.get('offset')
        if not offset:
            break
    return info_cpf


_RE_NAO_ESCALA = re.compile(r'^(FOLGA|FERIADO)$', re.IGNORECASE)


def _dia_e_folga_teorica(mapa: dict) -> bool:
    """True se a escala teórica do dia for FOLGA/Feriado (ground truth Secullum).

    Testado contra dados reais: o rótulo PAR/ÍMPAR do Horario.Descricao NÃO é
    confiável (ex.: funcionário rotulado "PAR" trabalha de fato nos dias
    ÍMPARES — é só o nome de um grupo/turma interno, não a paridade real).
    A fonte de verdade é o próprio /Calcular: ele já resolve a escala
    internamente (12x36, 5x2 etc.) e escreve "FOLGA" ou "Feriado" nas colunas
    de batida nos dias sem expediente, em vez de deixá-las vazias/nulas.
    """
    for col, val in mapa.items():
        if _RE_COL_BATIDA.match(col) and isinstance(val, str) and _RE_NAO_ESCALA.match(val.strip()):
            return True
    return False


# NOTA: tentamos um sinal "Normais=0 e Extras>0" pra achar Folga Trabalhada
# quando a pessoa bate ponto na folga (já que o marcador "FOLGA" só aparece
# com zero batidas). Descartado: confirmado em dados reais que vários
# funcionários (ex.: ANDRE LUIZ, ARTHUR SOARES — config "12x36 ... PAR/ÍMPAR"
# bem comum, 27/88 contas) têm "Normais" SEMPRE vazio mesmo no dia normal de
# trabalho, com tudo creditado em Extras — não é um sinal de dia fora da
# escala, é só a config de horário daquela conta. Sem essa coluna confiável,
# "Folga Trabalhada" só é detectável quando a Secullum mantém o literal
# "FOLGA"/"Feriado" (ou seja, quando NÃO houve batida) — então essa varredura
# não tenta mais distinguir "folga trabalhada com sucesso" via heurística.


def _analisar_batidas(mapa: dict) -> dict:
    """Analisa as batidas do dia (Regra #1: a jornada já vem agrupada na linha).

    Retorna {'n', 'impar', 'lado_faltante'}: lado_faltante='entrada' ou 'saida'
    indica qual marcação ficou faltando quando o nº de batidas é ímpar.
    Como o /Calcular já agrega as marcações pós-meia-noite na linha do dia em que
    o plantão começou, NÃO há risco de tratar a batida do dia seguinte como isolada.
    """
    cols = []
    for col, val in mapa.items():
        m = _RE_COL_BATIDA.match(col)
        if not m:
            continue
        num_match = re.search(r'\d+', col)
        num = int(num_match.group()) if num_match else 0
        is_entrada = col.strip().lower().startswith('entrada')
        v = val.strip() if isinstance(val, str) else val
        hora = v if (isinstance(v, str) and _RE_HORA.match(v)) else None
        cols.append((num, 0 if is_entrada else 1, is_entrada, hora))
    cols.sort(key=lambda x: (x[0], x[1]))   # Entrada N antes de Saída N

    preenchidas = [(is_ent, hora) for (_, _, is_ent, hora) in cols if hora]
    n = len(preenchidas)
    impar = n % 2 != 0
    lado = None
    if impar:
        # Se a última marcação registrada é uma ENTRADA, faltou a SAÍDA; senão, a ENTRADA.
        lado = 'saida' if preenchidas[-1][0] else 'entrada'
    return {'n': n, 'impar': impar, 'lado_faltante': lado}


def _descricao_batida_impar(ab: dict, noturno: bool, data_dia: str) -> str:
    """Texto da pendência de batida ímpar (Regra #3: distingue entrada x saída)."""
    if ab['lado_faltante'] == 'entrada':
        falta = ('ENTRADA (início do plantão, na noite do dia anterior)' if noturno
                 else 'ENTRADA')
    else:
        falta = ('SAÍDA (na manhã do dia seguinte ao início do plantão)' if noturno
                 else 'SAÍDA')
    escala = 'plantão noturno' if noturno else 'jornada'
    return (f'{ab["n"]} batida(s) no dia {data_dia} — número ímpar. '
            f'Em {escala}, provável esquecimento da {falta}. Verificar e ajustar.')


# ── Bônus de Assiduidade: atraso/saída antecipada já calculados pela Secullum ──
# "Fechamento" do plantão (Saída + 3h) é resolvido pelo próprio /Calcular: ele já
# devolve a jornada inteira (incl. virada de dia) numa única linha por plantão —
# confirmado contra dados reais (plantão 19h-07h aparece todo na linha do dia de
# início, sem quebra no dia civil seguinte). Por isso não há janela pra recalcular.
#
# Para atraso/saída antecipada, NÃO derivamos do Horario.Descricao: esse texto se
# provou não confiável (rótulo PAR/ÍMPAR invertido; faixa "07h-19h" de um
# colaborador cujas batidas reais são todas 19h-07h). Usamos direto as colunas
# que a própria Secullum já calcula: "Atras." (testado contra dado real: bateu
# 18:46 num horário "rotulado" 07h-19h e a Secullum corretamente não acusou
# atraso) e "Adian." (par natural de "Atraso" — adiantamento da saída).
def _avaliar_bonus_assiduidade(dias_status: dict, dias: dict,
                               perdoados: set = None, zelo_perdido: set = None) -> dict:
    """Bônus de Assiduidade: 100% assíduo no período = sem nenhum motivo de corte.

    Perde com >=1: falta não justificada, atraso na entrada > tolerância,
    saída antecipada > tolerância (colunas "Atras."/"Adian." da Secullum), ou
    intervalo não registrado (falta de zelo, v2.55). Dias de FOLGA/Feriado não
    contam. `perdoados`: datas de falta perdoadas (Troca de Plantão Informal
    confirmada por saldo de plantões — quem cedeu o turno preserva o bônus).
    """
    perdoados = perdoados or set()
    zelo_perdido = zelo_perdido or set()
    motivos = []
    for data_dia, mapa in sorted(dias.items()):
        if dias_status.get(data_dia) == 'folga':
            continue
        if not _trabalhou(mapa) and _faltas_minutos(mapa) > 0:
            if data_dia not in perdoados:
                motivos.append(f'Falta em {data_dia}')
            continue
        if data_dia in zelo_perdido:
            motivos.append(f'Intervalo não registrado (falta de zelo) em {data_dia}')
            continue
        ab = _analisar_batidas(mapa)
        if ab['impar']:
            motivos.append(f'Ocorrência de Batida Ímpar/Esquecimento '
                           f'({"faltou a entrada" if ab["lado_faltante"] == "entrada" else "faltou a saída"}) '
                           f'no dia {data_dia}')
        atraso = _hhmm_para_minutos(mapa.get(SECULLUM_COL_ATRASO)) or 0
        antecipada = _hhmm_para_minutos(mapa.get(SECULLUM_COL_ADIANTAMENTO)) or 0
        if atraso > BONUS_TOLERANCIA_MIN:
            motivos.append(f'Atraso de {_minutos_para_hhmm(atraso)} em {data_dia}')
        if antecipada > BONUS_TOLERANCIA_MIN:
            motivos.append(f'Saída antecipada de {_minutos_para_hhmm(antecipada)} em {data_dia}')
    elegivel = not motivos
    return {
        'elegivel': elegivel,
        'bonus': f'Sim (R$ {BONUS_ASSIDUIDADE_VALOR})' if elegivel else 'Não (R$ 0,00)',
        'motivos': motivos,
    }


def varrer_pendencias(data_inicio: str, data_fim: str,
                      dry_run: bool = False, limit: int = None,
                      desvio_base: str = None, offset: int = 0) -> dict:
    """Varre o período e gera alertas de Batidas Ímpares e Desvios > 02:00.

    Para cada funcionário ativo no Ponto Web, busca os cálculos diários e
    cria pendências no Airtable (tabela Pendências/Revisar). Idempotente: não
    recria uma pendência cujo título determinístico já exista.

    Suporta fatiamento por (offset, limit): no Render free, 88 chamadas numa
    única requisição estouram o timeout, então o scan é feito em lotes.

    Cruzamento jornada real x escala teórica ("Travas Humanas"):
    o próprio /Calcular já resolve a escala e marca FOLGA/Feriado nas colunas
    de batida (ground truth; rótulo PAR/ÍMPAR do horário NÃO é confiável).
    - Folga teórica + zero batidas → ignorado (não é falta).
    - Folga teórica + trabalhou → "Folga Trabalhada" (DP valida banco de horas).
    - Trabalho teórico + zero batidas → cruza, em toda a empresa, com quem teve
      Folga Trabalhada no mesmo dia. O pareamento é classificado pelo SALDO DE
      PLANTÕES do mês (v2.55): saldo neutro para os dois → "Troca de Plantão
      (Informal)" (preserva o bônus de quem cedeu); B acima da escala e A
      abaixo → "Dobra/Cobertura de Emergência (FT)" (hora extra legítima p/ B,
      falta de A mantida p/ averiguação de atestado); senão, fallback ambíguo
      "Faltou/Cedido"+"Cobriu/Dobrou" p/ revisão manual. Sem par, vira Desvio
      de Carga Horária simples.

    Arquitetura de intervalos por posto/função (v2.55, "fim dos falsos-
    positivos"): nos 5 postos de exceção (`EXCEPTION_POSTO_IDS`), todo mundo
    tem intervalo (espera 4 batidas) independente da função. Nos demais
    postos, depende do Cargo (Airtable, com fallback no Funcao da Secullum):
    Controlador de Acesso/Portaria/Supervisor de Perímetro = turno solo (só
    2 batidas; dia com exatamente 2 batidas conta hora extra Art. 71 CLT, sem
    afetar o bônus); os demais cargos têm intervalo (dia com exatamente 2
    batidas, faltando o par do intervalo, aplica o Intervalo Pré-Assinalado da
    CLT — não gera Desvio de Carga — mas corta o bônus por falta de zelo).

    Também avalia o Bônus de Assiduidade (R$) de cada funcionário no período:
    perde com qualquer falta não perdoada, atraso na entrada ou saída
    antecipada (> 5 min, `BONUS_TOLERANCIA_MIN`, colunas nativas "Atras."/
    "Adian." da Secullum) ou intervalo não registrado. Resultado em
    `resumo['bonus_assiduidade']`; grava no Airtable (campo
    F_FUNC_BONUS_JUN2026) quando `dry_run=False`.

    Args:
        data_inicio, data_fim: 'YYYY-MM-DD'.
        dry_run: se True, só relata o que faria (não grava no Airtable).
        offset, limit: recorte de funcionários a processar neste lote.
        desvio_base: override da base do desvio (faltas|extras|ambos).

    Returns:
        Resumo com contadores, alertas e o bônus de assiduidade por CPF.
    """
    funcionarios = listar_funcionarios_secullum()
    funcionarios.sort(key=lambda f: f.get('Nome', ''))

    # Posto/cargo (Airtable) — só para a Regra de Intervalo (v2.55). Fora da cota Secullum.
    posto_cargo = _mapa_posto_cargo_airtable()

    total_funcionarios = len(funcionarios)
    offset = offset or 0
    if limit:
        funcionarios = funcionarios[offset:offset + limit]
    elif offset:
        funcionarios = funcionarios[offset:]

    alertas = []
    criados = 0
    pulados_existentes = 0
    inativos = 0
    sem_cpf = 0
    calculados = 0
    com_erro = []   # nomes dos funcionários cujo cálculo falhou (mesmo após retries)

    # ── Passada 1: coleta cálculos por funcionário ──────────────────────────────
    dados_func = {}   # cpf -> {'nome', 'noturno', 'tem_intervalo', 'dias': {data: mapa}}
    for f in funcionarios:
        fid = f.get('Id')
        nome = f.get('Nome', '')
        cpf = _so_digitos(str(f.get('Cpf', '')))
        if f.get('Demissao'):   # data de demissão preenchida = inativo
            inativos += 1
            continue
        if not cpf:
            sem_cpf += 1
            continue

        try:
            calc = obter_calculos(cpf, data_inicio, data_fim)
            calculados += 1
        except Exception as exc:
            com_erro.append(nome)
            logger.warning('[SECULLUM] Cálculos falharam p/ %s (Id=%s): %s', nome, fid, exc)
            continue

        dias = {data: mapa for data, mapa in _linhas_calculo(calc)}
        pc = posto_cargo.get(cpf, {})
        cargo_texto = pc.get('cargo') or (f.get('Funcao') or {}).get('Descricao') or ''
        dados_func[cpf] = {
            'nome': nome, 'noturno': _horario_noturno(f), 'dias': dias,
            'tem_intervalo': _tem_intervalo(pc.get('postos', set()), cargo_texto),
        }

    # ── Passada 1.5: status da escala teórica por dia (trabalho/folga) ─────────
    # Ground truth do próprio /Calcular (marcador "FOLGA"/"Feriado" nas colunas
    # de batida). folga_trabalhada / falta_critica são a base do cruzamento
    # "jornada real x escala teórica", sem nenhum filtro de local de trabalho.
    folga_trabalhada = {}   # data -> set(cpf) que trabalhou na folga teórica
    falta_critica = {}      # data -> set(cpf) com zero batidas em dia de trabalho teórico
    for cpf, info in dados_func.items():
        dias_status = {}
        for data_dia, mapa in info['dias'].items():
            status = 'folga' if _dia_e_folga_teorica(mapa) else 'trabalho'
            dias_status[data_dia] = status
            if status == 'folga' and _trabalhou(mapa):
                folga_trabalhada.setdefault(data_dia, set()).add(cpf)
            elif status == 'trabalho' and not _trabalhou(mapa) and _faltas_minutos(mapa) > 0:
                falta_critica.setdefault(data_dia, set()).add(cpf)
        info['dias_status'] = dias_status

    # ── Passada 1.6: pareamento — falta crítica (A) x folga trabalhada (B) ──────
    # Sem filtro de local: qualquer Folga Trabalhada no mesmo dia é candidata.
    pareamento_a = {}   # (data, cpf_a) -> set(cpf_b)
    for data_dia, cpfs_a in falta_critica.items():
        candidatos_dia = folga_trabalhada.get(data_dia, set())
        if not candidatos_dia:
            continue
        for cpf_a in cpfs_a:
            pareamento_a[(data_dia, cpf_a)] = candidatos_dia

    # ── Passada 1.7: saldo de plantões do mês (trabalhados reais − teórico) ────
    saldo_plantoes = {}
    for cpf, info in dados_func.items():
        dias_total = len(info['dias'])
        dias_folga_marcador = sum(1 for m in info['dias'].values() if _dia_e_folga_teorica(m))
        dias_trabalhados_reais = sum(1 for m in info['dias'].values() if _trabalhou(m))
        saldo_plantoes[cpf] = dias_trabalhados_reais - (dias_total - dias_folga_marcador)

    # ── Passada 1.8: classifica os pareamentos por saldo (distinção jurídica) ──
    # Saldo neutro p/ ambos → Troca Informal (preserva bônus de quem cedeu).
    # B acima da escala / A abaixo → Cobertura de Emergência (FT), falta de A
    # mantida p/ averiguação de atestado. Senão, fallback ambíguo p/ revisão.
    perdoados = {}        # cpf_a -> set(datas) com falta perdoada (Troca Informal)
    dias_pareados_a = set()
    dias_pareados_b = set()
    for (data_dia, cpf_a), candidatos in pareamento_a.items():
        nome_a = dados_func.get(cpf_a, {}).get('nome', cpf_a)
        saldo_a = saldo_plantoes.get(cpf_a, 0)
        dias_pareados_a.add((data_dia, cpf_a))
        for cpf_b in candidatos:
            nome_b = dados_func.get(cpf_b, {}).get('nome', cpf_b)
            saldo_b = saldo_plantoes.get(cpf_b, 0)
            dias_pareados_b.add((data_dia, cpf_b))
            if saldo_a == 0 and saldo_b == 0:
                tipo_a, tipo_b = TIPO_TROCA_INFORMAL, TIPO_TROCA_INFORMAL
                obs_a = (f'Ausência (zero batidas) no dia de TRABALHO ({data_dia}); '
                         f'{nome_b} cobriu na folga teórica dele. Saldo de plantões do mês '
                         f'neutro para ambos — troca informal 1 por 1. Bônus preservado.')
                obs_b = (f'Trabalhou na FOLGA teórica ({data_dia}) cobrindo {nome_a}. Saldo '
                         f'de plantões do mês neutro para ambos — troca informal 1 por 1.')
                perdoados.setdefault(cpf_a, set()).add(data_dia)
            elif saldo_b > 0 and saldo_a < 0:
                tipo_a, tipo_b = TIPO_DESVIO_CARGA, TIPO_COBERTURA_EMERGENCIA
                obs_a = (f'Ausência (zero batidas) no dia de TRABALHO ({data_dia}). Saldo de '
                         f'plantões do mês ABAIXO da escala (coberto por {nome_b}, que está '
                         f'acima). Falta mantida para averiguação de atestado/justificativa.')
                obs_b = (f'Trabalhou na FOLGA teórica ({data_dia}) cobrindo {nome_a}. Saldo '
                         f'de plantões do mês ACIMA da escala — Dobra/Cobertura de '
                         f'Emergência, hora extra legítima.')
            else:
                tipo_a, tipo_b = TIPO_TROCA_FALTOU, TIPO_TROCA_COBRIU
                obs_a = (f'Ausência total (zero batidas) no dia de TRABALHO da escala '
                         f'teórica ({data_dia}); {nome_b} trabalhou em sua folga teórica '
                         f'nesse dia. Saldo de plantões do mês inconclusivo — confirmar '
                         f'manualmente o motivo.')
                obs_b = (f'Trabalhou na FOLGA teórica ({data_dia}), cobrindo {nome_a}, que '
                         f'faltou nesse dia. Saldo de plantões do mês inconclusivo — '
                         f'confirmar manualmente.')
            alertas.append(_montar_alerta(tipo=tipo_a, nome=nome_a, cpf=cpf_a,
                                          data_dia=data_dia, obs=obs_a))
            alertas.append(_montar_alerta(tipo=tipo_b, nome=nome_b, cpf=cpf_b,
                                          data_dia=data_dia, obs=obs_b))

    # ── Passada 2: detecção de alertas (com as travas) ─────────────────────────
    zelo_perdido = {}        # cpf -> set(datas) sem intervalo registrado (corta bônus)
    horas_extra_art71 = {}   # cpf -> nº de plantões solo (12x36) com direito ao Art. 71 CLT
    for cpf, info in dados_func.items():
        nome = info['nome']
        noturno = info['noturno']
        for data_dia, mapa in info['dias'].items():
            status = info['dias_status'].get(data_dia)

            # — Regra #3: batida ímpar (distingue entrada x saída; ciente do noturno) —
            ab = _analisar_batidas(mapa)
            if ab['impar']:
                alertas.append(_montar_alerta(
                    tipo=TIPO_BATIDA_IMPAR, nome=nome, cpf=cpf, data_dia=data_dia,
                    obs=_descricao_batida_impar(ab, noturno, data_dia),
                ))

            # — Arquitetura de Intervalos (v2.55): só em dia de TRABALHO com batidas —
            if status == 'trabalho' and not ab['impar'] and ab['n'] == N_BATIDAS_SOLO \
                    and _trabalhou(mapa):
                if info['tem_intervalo']:
                    # Intervalo Pré-Assinalado da CLT: computa como trabalhado (sem
                    # Desvio de Carga), mas corta o bônus por falta de zelo.
                    zelo_perdido.setdefault(cpf, set()).add(data_dia)
                else:
                    # Turno solo 12x36: 12h cheias + 1h extra Art. 71 CLT, bônus preservado.
                    horas_extra_art71[cpf] = horas_extra_art71.get(cpf, 0) + 1
                continue

            # — Dia de FOLGA na escala teórica: zero batidas é ignorado (não é falta) —
            if status == 'folga':
                if _trabalhou(mapa) and (data_dia, cpf) not in dias_pareados_b:
                    alertas.append(_montar_alerta(
                        tipo=TIPO_FOLGA_TRABALHADA, nome=nome, cpf=cpf, data_dia=data_dia,
                        obs=f'Trabalhou no dia de FOLGA da escala teórica ({data_dia}) com '
                            f'batidas e carga normal. Validar pagamento de extra ou '
                            f'lançamento em banco de horas.',
                    ))
                continue

            # — Dia de TRABALHO, zero batidas, já classificado na Passada 1.8 —
            if (data_dia, cpf) in dias_pareados_a:
                continue

            # — Desvio de carga horária > 02:00 (sem pareamento encontrado) —
            desvio = _desvio_minutos(mapa, base=desvio_base)
            if desvio is None or desvio <= THRESHOLD_DESVIO_MIN:
                continue
            faltas_min = _faltas_minutos(mapa)
            if faltas_min > THRESHOLD_DESVIO_MIN:
                alertas.append(_montar_alerta(
                    tipo=TIPO_DESVIO_CARGA, nome=nome, cpf=cpf, data_dia=data_dia,
                    obs=f'Falta de carga horária de {_minutos_para_hhmm(faltas_min)} em '
                        f'{data_dia} (limite 02:00), sem par de Folga Trabalhada '
                        f'encontrado nesse dia.',
                ))
            else:
                alertas.append(_montar_alerta(
                    tipo=TIPO_DESVIO_CARGA, nome=nome, cpf=cpf, data_dia=data_dia,
                    obs=f'Desvio de carga horária de {_minutos_para_hhmm(desvio)} '
                        f'no dia {data_dia} (limite: 02:00).',
                ))

    # ── Bônus de Assiduidade + Auditoria (v2.57) por CPF ────────────────────────
    bonus_assiduidade = {}
    for cpf, info in dados_func.items():
        avaliacao = _avaliar_bonus_assiduidade(
            info['dias_status'], info['dias'],
            perdoados=perdoados.get(cpf, set()), zelo_perdido=zelo_perdido.get(cpf, set()),
        )
        plantoes_solo = horas_extra_art71.get(cpf, 0)
        avaliacao['horas_extra_art71_clt'] = f'{plantoes_solo:02d}:00'
        avaliacao['plantoes_solo_art71'] = plantoes_solo
        avaliacao['tem_intervalo'] = info['tem_intervalo']

        total_min = 0
        total_batidas_periodo = 0
        for mapa in info['dias'].values():
            total_min += (_hhmm_para_minutos(mapa.get('Normais')) or 0)
            total_min += (_hhmm_para_minutos(mapa.get(SECULLUM_COL_EXTRAS)) or 0)
            total_batidas_periodo += _contar_batidas(mapa)
        avaliacao['horas_trabalhadas_total'] = _minutos_para_hhmm(total_min)

        # Glosa Crítica (v2.57): zero batidas em TODO o período é risco/parametrização
        # não-resolvida, não uma falta pontual — sobrescreve o motivo padrão para não
        # diluir o alerta numa lista de "Falta em {data}" repetida dia a dia.
        if total_batidas_periodo == 0:
            avaliacao['glosa_critica'] = True
            avaliacao['motivos'] = [
                'Glosa Crítica: Ausência total de registros no Ponto Web. Risco '
                'operacional ou afastamento/licença/demissão não parametrizada.'
            ]
            avaliacao['elegivel'] = False
            avaliacao['bonus'] = 'Não (R$ 0,00)'
        else:
            avaliacao['glosa_critica'] = False

        bonus_assiduidade[cpf] = {'nome': info['nome'], **avaliacao}

    # Persiste no Airtable: alertas (Pendências/Revisar) + Bônus (Funcionários).
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

    bonus_gravados = 0
    if not dry_run:
        for cpf, b in bonus_assiduidade.items():
            try:
                if gravar_bonus_assiduidade(cpf, b['bonus']):
                    bonus_gravados += 1
            except Exception as exc:
                logger.error('[SECULLUM] Falha gravando bônus de %s (CPF %s): %s', b['nome'], cpf, exc)

    por_tipo = {}
    for a in alertas:
        por_tipo[a['tipo']] = por_tipo.get(a['tipo'], 0) + 1

    proc_fim = offset + len(funcionarios)
    proximo_offset = proc_fim if proc_fim < total_funcionarios else None

    resumo = {
        'periodo': f'{data_inicio}..{data_fim}',
        'desvio_base': desvio_base or SECULLUM_DESVIO_BASE,
        'offset': offset,
        'lote_tamanho': len(funcionarios),
        'funcionarios_total': total_funcionarios,
        'proximo_offset': proximo_offset,
        'funcionarios_calculados': calculados,
        'funcionarios_inativos': inativos,
        'funcionarios_sem_cpf': sem_cpf,
        'funcionarios_com_erro': len(com_erro),
        'nomes_com_erro': com_erro,
        'alertas_detectados': len(alertas),
        'alertas_por_tipo': por_tipo,
        'trocas_cruzadas_pareadas': len(pareamento_a),
        'alertas_criados': criados,
        'alertas_ja_existentes': pulados_existentes,
        'bonus_assiduidade': bonus_assiduidade,
        'elegiveis_bonus': sum(1 for v in bonus_assiduidade.values() if v['elegivel']),
        'bonus_gravados_airtable': bonus_gravados,
        'dry_run': dry_run,
        'alertas': alertas,
    }
    logger.info('[SECULLUM] Varredura: %s',
                {k: v for k, v in resumo.items() if k not in ('alertas', 'bonus_assiduidade')})
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


def gravar_bonus_assiduidade(cpf: str, valor_texto: str) -> bool:
    """Grava a elegibilidade do Bônus de Assiduidade no Funcionário (Airtable).

    Campo F_FUNC_BONUS_JUN2026 ("Bônus Assiduidade Jun/2026", singleSelect,
    criado v2.55). Retorna False se o funcionário não for encontrado por CPF.
    """
    func = _buscar_funcionario_airtable_por_cpf(cpf)
    if not func:
        return False
    _at_throttle()
    r = requests.patch(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}/{func["id"]}',
        headers=_at_headers(),
        json={'fields': {F_FUNC_BONUS_JUN2026: valor_texto}, 'typecast': True},
        timeout=30,
    )
    if not r.ok:
        logger.error('[AT] Falha gravando bônus CPF %s HTTP %s: %s', cpf, r.status_code, r.text[:400])
    r.raise_for_status()
    return True


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

    Body JSON: {"competencia": "YYYY-MM", "data_inicio": "YYYY-MM-DD",
                "data_fim": "YYYY-MM-DD", "dry_run": false, "limit": null}

    `competencia` (recomendado, v2.56) calcula automaticamente a janela
    oficial de apuração da folha — 28 do mês anterior a 28 do mês de
    competência (ver `periodo_folha`), não o mês comercial cheio. Tem
    prioridade sobre data_inicio/data_fim explícitos. Sem nenhum dos dois,
    usa a competência vigente (a que contém hoje). A data final nunca
    ultrapassa hoje (não há como buscar batidas do futuro); quando isso
    ocorre, `periodo_incompleto=true` no resumo — reprocessar depois que o
    período fechar de verdade.
    """
    if request.method == 'OPTIONS':
        return ('', 204)
    body = request.get_json(silent=True) or {}
    hoje = date.today()
    competencia = body.get('competencia')
    if competencia:
        ano_c, mes_c = (int(p) for p in competencia.split('-')[:2])
        data_inicio, data_fim = periodo_folha(ano_c, mes_c)
    else:
        data_inicio = body.get('data_inicio')
        data_fim = body.get('data_fim')
        if not data_inicio or not data_fim:
            ano_ref, mes_ref = hoje.year, hoje.month
            if hoje.day >= 28:   # já viramos pro período de apuração seguinte
                mes_ref += 1
                if mes_ref > 12:
                    mes_ref, ano_ref = 1, ano_ref + 1
            data_inicio_calc, data_fim_calc = periodo_folha(ano_ref, mes_ref)
            data_inicio = data_inicio or data_inicio_calc
            data_fim = data_fim or data_fim_calc
    data_fim_efetivo = min(data_fim, hoje.isoformat())
    try:
        resumo = varrer_pendencias(
            data_inicio=data_inicio, data_fim=data_fim_efetivo,
            dry_run=bool(body.get('dry_run', False)), limit=body.get('limit'),
            desvio_base=body.get('desvio_base'), offset=int(body.get('offset') or 0),
        )
        resumo['periodo_solicitado'] = f'{data_inicio}..{data_fim}'
        resumo['periodo_incompleto'] = data_fim_efetivo < data_fim
        return jsonify(resumo), 200
    except requests.exceptions.HTTPError as exc:
        return jsonify({'erro': 'Falha na API Secullum', 'detalhe': str(exc)}), 502
    except Exception as exc:
        logger.exception('[SECULLUM] Erro na varredura')
        return jsonify({
            'erro': type(exc).__name__,
            'detalhe': str(exc),
            'traceback': traceback.format_exc().splitlines()[-8:],
        }), 500


@secullum_bp.route('/debug', methods=['GET'])
def rota_debug():
    """Diagnóstico: mostra os shapes crus retornados pela Secullum.

    Faz auth → lista funcionários → cálculos do 1º funcionário no período,
    devolvendo amostras para validar nomes de campo/coluna. Uso temporário.
    """
    out = {}
    try:
        out['token_ok'] = bool(get_token())
    except Exception as exc:
        out['token_ok'] = False
        out['token_erro'] = f'{type(exc).__name__}: {exc}'
        return jsonify(out), 200

    try:
        funcs = listar_funcionarios_secullum()
        out['funcionarios_tipo'] = type(funcs).__name__
        out['funcionarios_qtd'] = len(funcs) if isinstance(funcs, list) else None
        if request.args.get('listar_horarios'):
            out['horarios'] = [
                {'cpf': f.get('Cpf'), 'nome': f.get('Nome'),
                 'descricao': ((f.get('Horario') or {}).get('Descricao'))}
                for f in (funcs if isinstance(funcs, list) else [])
            ]
            return jsonify(out), 200
        cpf_query = request.args.get('cpf')
        amostra = (funcs[0] if isinstance(funcs, list) and funcs else None)
        if cpf_query and isinstance(funcs, list):
            alvo = _so_digitos(cpf_query)
            achado = next((f for f in funcs if _so_digitos(str(f.get('Cpf', ''))) == alvo), None)
            if achado:
                amostra = achado
                out['funcionario_amostra_e_do_cpf_pedido'] = True
        out['funcionario_amostra'] = amostra
    except Exception as exc:
        out['funcionarios_erro'] = f'{type(exc).__name__}: {exc}'
        out['funcionarios_traceback'] = traceback.format_exc().splitlines()[-6:]
        return jsonify(out), 200

    try:
        cpf = request.args.get('cpf') or (amostra.get('Cpf') if amostra else None)
        # default: mês passado (mais provável de estar fechado/calculado)
        ref = date.today().replace(day=1) - timedelta(days=1)
        di = request.args.get('di') or ref.replace(day=1).isoformat()
        df = request.args.get('df') or ref.isoformat()
        out['calc_cpf'] = cpf
        out['calc_periodo'] = f'{di}..{df}'

        payload = {
            'funcionarioCpf': _so_digitos(cpf or ''),
            'dataInicial': f'{di}T00:00:00',
            'dataFinal': f'{df}T00:00:00',
        }
        bruto = _secullum_request('POST', 'Calcular', json=payload)
        out['calculos_raw_tipo'] = type(bruto).__name__
        if isinstance(bruto, list):
            out['calculos_raw_qtd'] = len(bruto)
            out['calculos_raw_amostra'] = bruto[:2]
        else:
            out['calculos_raw_amostra'] = bruto
    except Exception as exc:
        out['calculos_erro'] = f'{type(exc).__name__}: {exc}'
        out['calculos_traceback'] = traceback.format_exc().splitlines()[-6:]

    return jsonify(out), 200
