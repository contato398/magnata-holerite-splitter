# -*- coding: utf-8 -*-
"""
src/ingestao_secullum.py — Ingestão e Espelhamento Puro v2
Arquitetura: zero recálculo. Os dados chegam do Secullum e são espelhados
diretamente no Airtable exatamente como estão.

Endpoints
─────────
POST /ingestao/espelho-ponto
    Aceita multipart/form-data com campo 'arquivo' (PDF ou TXT/AFD).
    Detecta o formato automaticamente e faz upsert em Folha de Ponto
    cruzando por CPF/N.Folha + Data da jornada.

POST /ingestao/relatorio-secullum
    Aceita JSON com campo 'texto' (relatório de Inconsistências colado).
    Espelha os totais mensais (Faltas, Extras, Banco) por N.Folha.

GET  /ingestao/secullum/horarios
    Lista os horários cadastrados no Secullum Ponto Web.
    Use para preencher MAPA_CARGO_HORARIO abaixo.

Notas de campo
──────────────
• A tabela Folha de Ponto não tem campos text/number graváveis para
  Faltas/Extras brutas — são fórmulas calculadas a partir de Entrada/Saída.
  Para armazenar os totais brutos do Secullum, adicione à tabela:
    Sec_Faltas  (singleLineText)
    Sec_Extras  (singleLineText)
    Sec_Banco   (singleLineText)
  e descomente as linhas marcadas com TODO abaixo.

• O parser de PDF (Espelho de Ponto) usa regex baseada no layout típico
  do Secullum Ponto Web. Valide com um arquivo real e ajuste se necessário.

• Brasil não adota horário de verão desde 2019 → BRT = UTC-3 fixo.
"""

import io
import re
import os
import requests
import pdfplumber
from flask import Blueprint, request, jsonify

ingestao_bp = Blueprint('ingestao', __name__)

# ── Airtable ──────────────────────────────────────────────────────────────────
AT_BASE  = 'appaCpIVj7Q97VhFy'
AT_FUNC  = 'tblNd8G66kjwos3eP'   # Funcionários
AT_PONTO = 'tblmgV10s3dZiP8av'   # Folha de Ponto

# Funcionários — campos usados
F_CPF         = 'fld0Y3bXdArkSIJxo'
F_PIS         = 'fldNNWb5BLgdBdsJO'
F_NOME        = 'fld2fSiomk9AOLGDb'
F_CODIGO      = 'fldCtZHUjJBi7JQXb'   # N.Folha
F_CONFERENCIA = 'fldTp5QaaWhqnukuE'   # Conferência do Cadastro

# Folha de Ponto — campos graváveis
F_FUNC        = 'fldR50BgugvINUG2v'   # Funcionário (link)
F_DATA        = 'fldqKMo8FVKTYaSoI'   # Data
F_STATUS      = 'fld8p57Bu5aNYtqd5'   # Status
F_TIPO        = 'fldtv8Dzmk1h97FVg'   # Tipo
F_ENTRADA     = 'fldgF4cITGk0inwX4'   # Entrada-
F_SAIDA_AL    = 'fldx3dhHn1BHeQzSm'   # Saída-pro-almoço
F_RETORNO_AL  = 'fldI6cRPzLQ8Z7q8b'   # Volta-do-almoço
F_SAIDA       = 'fldwJgA0KUpR8Mxpa'   # Saída-
# TODO: adicionar campos Sec_Faltas / Sec_Extras / Sec_Banco à tabela
# F_SEC_FALTAS = 'fld???'
# F_SEC_EXTRAS = 'fld???'
# F_SEC_BANCO  = 'fld???'

AT_KEY     = os.environ.get('AIRTABLE_API_KEY', '')
AT_HEADERS = {'Authorization': f'Bearer {AT_KEY}', 'Content-Type': 'application/json'}

STATUS_VALIDACAO  = 'Validação Pendente'
TIPO_ESPELHAMENTO = 'Espelhamento Secullum'
BRT               = '-03:00'


# ── Escala Automática ─────────────────────────────────────────────────────────
# Mapa Cargo (Airtable) → horarioNumero no Secullum.
# Execute GET /ingestao/secullum/horarios para ver os números disponíveis
# e preencha os valores None abaixo.
MAPA_CARGO_HORARIO = {
    'CONTROLADOR DE ACESSO': None,      # preencher após GET /horarios
    'SUPERVISOR DE PERIMETRO': None,    # idem
    'SUPERVISOR': None,                 # idem
    'AUXILIAR DE LIMPEZA': 6,           # comercial — confirmado
    'SERVICOS GERAIS': 6,               # comercial — confirmado
    'JARDINEIRO': 6,
    'ZELADOR': 6,
}

# Fallback se o cargo não estiver no mapa ou o valor for None
HORARIO_PADRAO = int(os.environ.get('SECULLUM_HORARIO_NUMERO_PADRAO', '6'))


def horario_para_cargo(cargo: str) -> int:
    """Retorna o horarioNumero do Secullum para um dado cargo."""
    import unicodedata
    chave = unicodedata.normalize('NFKD', cargo or '').encode('ascii', 'ignore').decode('ascii').upper().strip()
    return MAPA_CARGO_HORARIO.get(chave) or HORARIO_PADRAO


# ── Parsers ───────────────────────────────────────────────────────────────────

def _parse_afd(conteudo: str) -> list:
    """
    Parseia AFD (Portaria 1.510/2009).
    Tipo 3 = marcação de ponto: 3 YYYYMMDD HHMM PPPPPPPPPP NNNNN

    Retorna lista de {pis, data (YYYY-MM-DD), hora (HH:MM)}.
    """
    batidas = []
    for linha in conteudo.splitlines():
        linha = linha.rstrip('\r')
        if len(linha) < 23 or linha[0] != '3':
            continue
        try:
            d = linha[1:9]     # YYYYMMDD
            h = linha[9:13]    # HHMM
            p = linha[13:23]   # PIS (10 dígitos)
            batidas.append({
                'pis':  p.strip(),
                'data': f'{d[0:4]}-{d[4:6]}-{d[6:8]}',
                'hora': f'{h[0:2]}:{h[2:4]}',
            })
        except (IndexError, ValueError):
            continue
    return batidas


def _parse_espelho_pdf(conteudo_bytes: bytes) -> list:
    """
    Parseia o PDF do Espelho de Ponto da Secullum.

    Layout esperado (típico do Secullum Ponto Web):
        FUNCIONÁRIO: NOME COMPLETO              N.FOLHA: 123
        ...
        DD/MM  DIA  07:00  12:00  13:00  16:00  ...
        DD/MM  DIA  F (falta)
        ...

    Retorna lista de {n_folha, nome, data_dm (DD/MM), batidas [HH:MM, ...]}.

    ⚠ Ajuste as regex abaixo caso o layout real difira desta estimativa.
    """
    registros = []
    try:
        with pdfplumber.open(io.BytesIO(conteudo_bytes)) as pdf:
            n_folha_atual = None
            nome_atual = None

            for page in pdf.pages:
                texto = page.extract_text() or ''
                for linha in texto.splitlines():

                    # Cabeçalho do colaborador
                    m = re.search(
                        r'(?:FUNCION[AÁ]RIO|NOME):\s*(.+?)\s+N[.º\s]*FOLHA:\s*(\S+)',
                        linha, re.IGNORECASE,
                    )
                    if m:
                        nome_atual    = m.group(1).strip()
                        n_folha_atual = m.group(2).strip()
                        continue

                    if not n_folha_atual:
                        continue

                    # Linha de dia: DD/MM  [3 chars dia]  [horários ou F/A]
                    dm = re.match(r'^(\d{2}/\d{2})\s+\w{2,3}\s+', linha)
                    if dm:
                        data_dm = dm.group(1)
                        horarios = re.findall(r'\b(\d{2}:\d{2})\b', linha)
                        if horarios:   # ignora dias de falta total (sem batida)
                            registros.append({
                                'n_folha': n_folha_atual,
                                'nome':    nome_atual,
                                'data_dm': data_dm,
                                'batidas': horarios,
                            })
    except Exception as exc:
        raise ValueError(f'Erro ao ler PDF do Espelho: {exc}') from exc

    return registros


def _parse_inconsistencias(texto: str) -> list:
    """
    Parser do Relatório de Inconsistências da Secullum.
    Extrai totais mensais por colaborador: Faltas, Atrasos, Extras, Banco.
    """
    linhas = texto.splitlines()
    funcionarios = []
    atual = None

    for linha in linhas:
        nm = re.search(r'NOME:\s+(.+?)\s+N[.º\s]*FOLHA:\s*(\S+)', linha)
        if nm and 'SUBTOTAL' not in linha and 'HORARIO' not in linha:
            if atual:
                funcionarios.append(atual)
            atual = {'nome': nm.group(1).strip(), 'n_folha': nm.group(2).strip()}
            continue

        if not atual:
            continue

        sub = re.match(
            r'^SUBTOTAL\s+'
            r'(\d+:\d+)\s+'   # Faltas
            r'(\d+:\d+)\s+'   # Atrasos
            r'(\d+:\d+)\s+'   # Extras
            r'(\d+:\d+)\s+'   # Banco Total
            r'(\d+:\d+)\s+'   # Intervalo
            r'(\d+:\d+)',      # Interjornada
            linha.strip(),
        )
        if sub:
            atual.update({
                'faltas': sub.group(1), 'atrasos': sub.group(2),
                'extras': sub.group(3), 'banco':   sub.group(4),
            })
            funcionarios.append(atual)
            atual = None

    if atual:
        funcionarios.append(atual)

    return funcionarios


# ── Airtable helpers ──────────────────────────────────────────────────────────

def _at_get_all(table: str, params: dict) -> list:
    """Busca com paginação automática."""
    url = f'https://api.airtable.com/v0/{AT_BASE}/{table}'
    records, p = [], dict(params)
    while True:
        resp = requests.get(url, headers=AT_HEADERS, params=p, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get('records', []))
        offset = data.get('offset')
        if not offset:
            break
        p = {**p, 'offset': offset}
    return records


def _at_patch(table: str, rec_id: str, fields: dict) -> None:
    url = f'https://api.airtable.com/v0/{AT_BASE}/{table}/{rec_id}'
    requests.patch(url, headers=AT_HEADERS,
                   json={'fields': fields, 'typecast': True},
                   timeout=15).raise_for_status()


def _at_post(table: str, fields: dict) -> str:
    url = f'https://api.airtable.com/v0/{AT_BASE}/{table}'
    resp = requests.post(url, headers=AT_HEADERS,
                         json={'fields': fields, 'typecast': True},
                         timeout=15)
    resp.raise_for_status()
    return resp.json()['id']


def _buscar_func(valor: str, campo_nome: str) -> dict | None:
    """Busca 1 registro em Funcionários por campo + valor."""
    records = _at_get_all(AT_FUNC, {
        'filterByFormula': f'{{{campo_nome}}}="{valor}"',
        'fields[]': ['Nome Completo', 'Código', 'PIS', 'CPF', 'Cargo'],
        'maxRecords': 1,
    })
    return records[0] if records else None


def _buscar_ponto_existente(func_rec_id: str, data_iso: str) -> dict | None:
    """Retorna o registro de Folha de Ponto para Funcionário + Data, se existir."""
    records = _at_get_all(AT_PONTO, {
        'filterByFormula': f'{{{F_DATA}}}="{data_iso}"',
        'fields[]': [F_FUNC, F_DATA, F_ENTRADA, F_SAIDA_AL, F_RETORNO_AL, F_SAIDA],
    })
    for rec in records:
        if func_rec_id in rec.get('fields', {}).get(F_FUNC, []):
            return rec
    return None


def _batidas_em_campos(data_iso: str, batidas: list) -> dict:
    """
    Distribui lista de horários ['HH:MM', ...] pelos campos da Folha de Ponto.

    1 batida  → só Entrada (registro incompleto)
    2 batidas → Entrada + Saída (12x36 ou jornada direta sem almoço)
    3 batidas → Entrada + Saída-almoço + Retorno (jornada truncada)
    4 batidas → Entrada + Saída-almoço + Retorno + Saída (padrão comercial)
    5+ batidas → idem, extras ignorados (podem ser re-batidas por erro)
    """
    def dt(h: str) -> str:
        return f'{data_iso}T{h}:00{BRT}'

    c, n = {}, len(batidas)
    if n >= 1: c[F_ENTRADA]    = dt(batidas[0])
    if n == 2: c[F_SAIDA]      = dt(batidas[1])
    if n >= 3: c[F_SAIDA_AL]   = dt(batidas[1])
    if n >= 3: c[F_RETORNO_AL] = dt(batidas[2])
    if n >= 4: c[F_SAIDA]      = dt(batidas[3])
    return c


def _upsert_folha_ponto(func_rec_id: str, data_iso: str, batidas: list) -> tuple:
    """
    Cria ou atualiza registro na Folha de Ponto.
    Retorna (record_id, criado: bool).
    """
    campos_batidas = _batidas_em_campos(data_iso, batidas)
    existente = _buscar_ponto_existente(func_rec_id, data_iso)

    if existente:
        _at_patch(AT_PONTO, existente['id'], campos_batidas)
        return existente['id'], False

    campos = {
        F_FUNC:   [func_rec_id],
        F_DATA:   data_iso,
        F_STATUS: STATUS_VALIDACAO,
        F_TIPO:   TIPO_ESPELHAMENTO,
        **campos_batidas,
    }
    rec_id = _at_post(AT_PONTO, campos)
    return rec_id, True


def _marcar_validacao_pendente(func_rec_id: str) -> None:
    _at_patch(AT_FUNC, func_rec_id, {F_CONFERENCIA: STATUS_VALIDACAO})


# ── Secullum helper ───────────────────────────────────────────────────────────

def _listar_horarios_secullum() -> list:
    try:
        from src.services.secullum_ponto import _secullum_request
        return _secullum_request('GET', 'Horarios') or []
    except Exception as exc:
        return [{'erro': str(exc)}]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@ingestao_bp.route('/ingestao/espelho-ponto', methods=['POST', 'OPTIONS'])
def ingerir_espelho_ponto():
    """
    Upload de Espelho de Ponto (PDF) ou AFD (TXT).
    Form-data esperado:
        arquivo    → arquivo PDF ou TXT/AFD
        referencia → ano de referência, ex: "2026"
        dry_run    → "true" (default) ou "false"
    """
    if request.method == 'OPTIONS':
        return ('', 204)

    arquivo    = request.files.get('arquivo')
    referencia = (request.form.get('referencia') or '').strip()
    dry_run    = request.form.get('dry_run', 'true').lower() != 'false'

    if not arquivo:
        return jsonify({'erro': 'Campo "arquivo" obrigatório (multipart/form-data).'}), 400
    if not referencia:
        return jsonify({'erro': 'Campo "referencia" obrigatório (ex: "2026").'}), 400

    nome_arquivo   = (arquivo.filename or '').lower()
    conteudo_bytes = arquivo.read()
    modo           = 'pdf' if nome_arquivo.endswith('.pdf') else 'afd'

    # ── Parse ─────────────────────────────────────────────────────────────────
    if modo == 'pdf':
        try:
            registros_dia = _parse_espelho_pdf(conteudo_bytes)
        except ValueError as exc:
            return jsonify({'erro': str(exc)}), 400
    else:
        texto_afd = conteudo_bytes.decode('latin-1', errors='replace')
        batidas_raw = _parse_afd(texto_afd)
        # Agrupa por PIS + Data
        grupos: dict = {}
        for b in batidas_raw:
            grupos.setdefault((b['pis'], b['data']), []).append(b['hora'])
        registros_dia = [
            {'pis': pis, 'data_iso': dt, 'batidas': horas}
            for (pis, dt), horas in sorted(grupos.items())
        ]

    # ── Processa cada dia ─────────────────────────────────────────────────────
    resultados = []
    criados = atualizados = nao_achados = erros = sem_batidas = 0

    for reg in registros_dia:
        entrada = {'modo': modo}

        # Resolve Funcionário e data ISO
        if modo == 'afd':
            pis = reg['pis']
            func_rec = _buscar_func(pis, 'PIS')
            if not func_rec:
                # PIS pode estar formatado no Airtable (163.12345.67-8)
                func_rec = None   # lookup adicional por CPF não aplicável aqui
            data_iso = reg['data_iso']
            batidas  = reg.get('batidas', [])
            entrada.update({'pis': pis, 'data': data_iso})
        else:
            n_folha  = reg.get('n_folha', '')
            func_rec = _buscar_func(n_folha, 'Código') if n_folha else None
            data_dm  = reg.get('data_dm', '')
            try:
                dia, mes = data_dm.split('/')
                ano = referencia.split('-')[0]   # suporta "2026" ou "2026-06"
                data_iso = f'{ano}-{mes}-{dia}'
            except (ValueError, AttributeError):
                data_iso = ''
            batidas  = reg.get('batidas', [])
            entrada.update({'n_folha': n_folha, 'data': data_iso})

        if not func_rec:
            entrada['status'] = 'nao_encontrado'
            nao_achados += 1
            resultados.append(entrada)
            continue

        func_rec_id = func_rec['id']
        entrada['funcionario_id'] = func_rec_id
        entrada['nome'] = func_rec['fields'].get('Nome Completo', '')

        if dry_run:
            entrada.update({'status': 'dry_run', 'batidas': batidas})
            resultados.append(entrada)
            continue

        if not data_iso or not batidas:
            entrada['status'] = 'sem_batidas'
            sem_batidas += 1
            resultados.append(entrada)
            continue

        try:
            ponto_id, criado = _upsert_folha_ponto(func_rec_id, data_iso, batidas)
            _marcar_validacao_pendente(func_rec_id)
            entrada.update({
                'status':   'criado' if criado else 'atualizado',
                'folha_id': ponto_id,
                'batidas':  batidas,
            })
            if criado:
                criados += 1
            else:
                atualizados += 1
        except requests.HTTPError as exc:
            entrada.update({'status': 'erro', 'detalhe': str(exc)})
            erros += 1

        resultados.append(entrada)

    return jsonify({
        'modo':            modo,
        'referencia':      referencia,
        'dry_run':         dry_run,
        'total':           len(registros_dia),
        'criados':         criados,
        'atualizados':     atualizados,
        'nao_encontrados': nao_achados,
        'sem_batidas':     sem_batidas,
        'erros':           erros,
        'resultados':      resultados,
    })


@ingestao_bp.route('/ingestao/relatorio-secullum', methods=['POST', 'OPTIONS'])
def ingerir_relatorio_secullum():
    """
    Espelhamento de totais mensais do Relatório de Inconsistências.
    Body JSON:
        texto      → texto bruto do relatório (copiar da tela)
        referencia → "YYYY-MM-DD" (1º dia do mês, ex: "2026-06-01")
        dry_run    → true/false
    """
    if request.method == 'OPTIONS':
        return ('', 204)

    body       = request.get_json(silent=True) or {}
    texto      = (body.get('texto') or '').strip()
    referencia = (body.get('referencia') or '').strip()
    dry_run    = body.get('dry_run', True)

    if not texto:
        return jsonify({'erro': 'Campo "texto" obrigatório.'}), 400
    if not referencia:
        return jsonify({'erro': 'Campo "referencia" obrigatório (YYYY-MM-DD).'}), 400

    funcionarios = _parse_inconsistencias(texto)
    if not funcionarios:
        return jsonify({'aviso': 'Nenhum funcionário encontrado no texto.', 'total': 0}), 200

    resultados = []
    espelhados = nao_achados = erros = 0

    for f in funcionarios:
        entrada = {
            'nome':    f['nome'],    'n_folha': f['n_folha'],
            'faltas':  f.get('faltas',  '00:00'),
            'atrasos': f.get('atrasos', '00:00'),
            'extras':  f.get('extras',  '00:00'),
            'banco':   f.get('banco',   '00:00'),
        }

        if dry_run:
            entrada['status'] = 'dry_run'
            resultados.append(entrada)
            continue

        rec = _buscar_func(f['n_folha'], 'Código')
        if not rec:
            entrada['status'] = 'nao_encontrado'
            nao_achados += 1
            resultados.append(entrada)
            continue

        try:
            ponto_id = _at_post(AT_PONTO, {
                F_FUNC:   [rec['id']],
                F_DATA:   referencia,
                F_STATUS: STATUS_VALIDACAO,
                F_TIPO:   TIPO_ESPELHAMENTO,
                # TODO: descomentar após criar campos Sec_* na tabela:
                # F_SEC_FALTAS: f.get('faltas'),
                # F_SEC_EXTRAS: f.get('extras'),
                # F_SEC_BANCO:  f.get('banco'),
            })
            _marcar_validacao_pendente(rec['id'])
            entrada.update({
                'status':          'espelhado',
                'funcionario_id':  rec['id'],
                'folha_ponto_id':  ponto_id,
            })
            espelhados += 1
        except requests.HTTPError as exc:
            entrada.update({'status': 'erro', 'detalhe': str(exc)})
            erros += 1

        resultados.append(entrada)

    return jsonify({
        'referencia':      referencia,
        'dry_run':         dry_run,
        'total':           len(funcionarios),
        'espelhados':      espelhados,
        'nao_encontrados': nao_achados,
        'erros':           erros,
        'resultados':      resultados,
    })


@ingestao_bp.route('/ingestao/secullum/horarios', methods=['GET'])
def listar_horarios():
    """
    Lista os horários cadastrados no Secullum Ponto Web.
    Use o campo 'Numero' retornado para preencher MAPA_CARGO_HORARIO acima.
    """
    horarios = _listar_horarios_secullum()
    return jsonify({
        'horarios':        horarios,
        'mapa_atual':      MAPA_CARGO_HORARIO,
        'horario_padrao':  HORARIO_PADRAO,
    })
