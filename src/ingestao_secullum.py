# -*- coding: utf-8 -*-
"""
src/ingestao_secullum.py
Ingestão e Espelhamento Puro do Relatório de Inconsistências da Secullum.

Estratégia: zero recálculo. Os valores de Faltas, Atrasos, Extras, Banco
são copiados exatamente como estão no relatório e enviados ao Airtable.
O Funcionário tem "Conferência do Cadastro" marcado como "Validação Pendente"
para acionar o fluxo do Evolution.

Endpoint: POST /ingestao/relatorio-secullum
Body JSON:
  {
    "texto":      "<texto bruto do relatório colado>",
    "referencia": "2026-06-01",   // data de referência (1º dia do mês)
    "dry_run":    true            // false para gravar de verdade
  }

NOTA DE CAMPO: A tabela Folha de Ponto (tblmgV10s3dZiP8av) não possui campos
de texto/número graváveis para Faltas, Extras e Horas brutas do Secullum —
esses campos são todos fórmulas calculadas. Para espelhar esses valores no
Airtable, adicione à tabela Folha de Ponto os seguintes campos:
  - "Sec_Faltas"    (singleLineText)
  - "Sec_Atrasos"   (singleLineText)
  - "Sec_Extras"    (singleLineText)
  - "Sec_Banco"     (singleLineText)
e descomente as linhas correspondentes em _criar_folha_ponto() abaixo.
"""

import re
import os
import requests
from flask import Blueprint, request, jsonify

ingestao_bp = Blueprint('ingestao', __name__)

# ── Airtable ──────────────────────────────────────────────────────────────────
AT_BASE         = 'appaCpIVj7Q97VhFy'
AT_FUNC_TABLE   = 'tblNd8G66kjwos3eP'  # Funcionários
AT_PONTO_TABLE  = 'tblmgV10s3dZiP8av'  # Folha de Ponto

# Campos — Funcionários
F_FUNC_CONFERENCIA = 'fldTp5QaaWhqnukuE'   # Conferência do Cadastro

# Campos — Folha de Ponto (existentes, graváveis)
F_PONTO_FUNC   = 'fldR50BgugvINUG2v'   # Funcionário (link)
F_PONTO_DATA   = 'fldqKMo8FVKTYaSoI'   # Data
F_PONTO_STATUS = 'fld8p57Bu5aNYtqd5'   # Status
F_PONTO_TIPO   = 'fldtv8Dzmk1h97FVg'   # Tipo

# Campos — Folha de Ponto (AINDA NÃO EXISTEM — adicionar no Airtable)
# F_PONTO_SEC_FALTAS   = 'fld???'  # Sec_Faltas   (singleLineText)
# F_PONTO_SEC_ATRASOS  = 'fld???'  # Sec_Atrasos  (singleLineText)
# F_PONTO_SEC_EXTRAS   = 'fld???'  # Sec_Extras   (singleLineText)
# F_PONTO_SEC_BANCO    = 'fld???'  # Sec_Banco    (singleLineText)

AT_KEY     = os.environ.get('AIRTABLE_API_KEY', '')
AT_HEADERS = {'Authorization': f'Bearer {AT_KEY}', 'Content-Type': 'application/json'}

STATUS_VALIDACAO = 'Validação Pendente'
TIPO_ESPELHAMENTO = 'Espelhamento Secullum'


# ── Parser ────────────────────────────────────────────────────────────────────

def _parse_relatorio(texto: str) -> list:
    """
    Lê o texto do Relatório de Inconsistências da Secullum e retorna
    uma lista de dicts com os dados brutos de cada funcionário.

    Formato esperado (colunas do SUBTOTAL):
      SUBTOTAL  <Faltas>  <Atrasos>  <Extras>  <BancoTotal>  <Intervalo>  <Interjornada>
    """
    linhas = texto.splitlines()
    funcionarios = []
    atual = None

    for linha in linhas:
        nm = re.search(r'NOME:\s+(.+?)\s+N[.º\s]*FOLHA:\s*(\S+)', linha)
        if nm and 'SUBTOTAL' not in linha and 'HORARIO' not in linha:
            if atual:
                funcionarios.append(atual)
            atual = {
                'nome':    nm.group(1).strip(),
                'n_folha': nm.group(2).strip(),
            }
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
            atual['faltas']       = sub.group(1)
            atual['atrasos']      = sub.group(2)
            atual['extras']       = sub.group(3)
            atual['banco']        = sub.group(4)
            atual['intervalo']    = sub.group(5)
            atual['interjornada'] = sub.group(6)
            funcionarios.append(atual)
            atual = None

    if atual:
        funcionarios.append(atual)

    return funcionarios


# ── Airtable helpers ──────────────────────────────────────────────────────────

def _buscar_funcionario_por_folha(n_folha: str):
    """Retorna o record Airtable do Funcionário pelo N.Folha (campo Código)."""
    url = f'https://api.airtable.com/v0/{AT_BASE}/{AT_FUNC_TABLE}'
    resp = requests.get(url, headers=AT_HEADERS, params={
        'filterByFormula': f'{{Código}}="{n_folha}"',
        'fields[]': ['Nome Completo', 'Código'],
        'maxRecords': 1,
    }, timeout=15)
    resp.raise_for_status()
    records = resp.json().get('records', [])
    return records[0] if records else None


def _marcar_validacao_pendente(func_rec_id: str) -> None:
    url = f'https://api.airtable.com/v0/{AT_BASE}/{AT_FUNC_TABLE}/{func_rec_id}'
    requests.patch(url, headers=AT_HEADERS, json={
        'fields': {F_FUNC_CONFERENCIA: STATUS_VALIDACAO},
        'typecast': True,
    }, timeout=15).raise_for_status()


def _criar_folha_ponto(func_rec_id: str, referencia: str, dados: dict) -> str:
    """
    Cria um registro na tabela Folha de Ponto espelhando o mês de referência.
    Os campos Sec_Faltas/Extras/etc. estão comentados até serem criados no Airtable.
    """
    fields = {
        F_PONTO_FUNC:   [func_rec_id],
        F_PONTO_DATA:   referencia,
        F_PONTO_STATUS: STATUS_VALIDACAO,
        F_PONTO_TIPO:   TIPO_ESPELHAMENTO,
        # Descomente após criar os campos no Airtable:
        # F_PONTO_SEC_FALTAS:  dados.get('faltas', '00:00'),
        # F_PONTO_SEC_ATRASOS: dados.get('atrasos', '00:00'),
        # F_PONTO_SEC_EXTRAS:  dados.get('extras', '00:00'),
        # F_PONTO_SEC_BANCO:   dados.get('banco', '00:00'),
    }
    url = f'https://api.airtable.com/v0/{AT_BASE}/{AT_PONTO_TABLE}'
    resp = requests.post(url, headers=AT_HEADERS, json={
        'fields': fields,
        'typecast': True,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()['id']


# ── Endpoint ──────────────────────────────────────────────────────────────────

@ingestao_bp.route('/ingestao/relatorio-secullum', methods=['POST', 'OPTIONS'])
def ingerir_relatorio_secullum():
    if request.method == 'OPTIONS':
        return ('', 204)

    body       = request.get_json(silent=True) or {}
    texto      = (body.get('texto') or '').strip()
    referencia = (body.get('referencia') or '').strip()  # "YYYY-MM-DD"
    dry_run    = body.get('dry_run', True)

    if not texto:
        return jsonify({'erro': 'Campo "texto" obrigatório.'}), 400
    if not referencia:
        return jsonify({'erro': 'Campo "referencia" obrigatório (YYYY-MM-DD, ex: 2026-06-01).'}), 400

    funcionarios = _parse_relatorio(texto)

    if not funcionarios:
        return jsonify({
            'aviso': 'Nenhum funcionário encontrado no texto. Verifique o formato do relatório.',
            'total': 0,
        }), 200

    resultados   = []
    espelhados   = 0
    nao_achados  = 0
    com_erro     = 0

    for f in funcionarios:
        entrada = {
            'nome':    f['nome'],
            'n_folha': f['n_folha'],
            'faltas':  f.get('faltas', '00:00'),
            'atrasos': f.get('atrasos', '00:00'),
            'extras':  f.get('extras', '00:00'),
            'banco':   f.get('banco', '00:00'),
        }

        if dry_run:
            entrada['status'] = 'dry_run'
            resultados.append(entrada)
            continue

        rec = _buscar_funcionario_por_folha(f['n_folha'])
        if not rec:
            entrada['status'] = 'nao_encontrado'
            nao_achados += 1
            resultados.append(entrada)
            continue

        try:
            _marcar_validacao_pendente(rec['id'])
            ponto_id = _criar_folha_ponto(rec['id'], referencia, f)
            entrada['status']          = 'espelhado'
            entrada['funcionario_id']  = rec['id']
            entrada['folha_ponto_id']  = ponto_id
            espelhados += 1
        except requests.HTTPError as exc:
            entrada['status']  = 'erro'
            entrada['detalhe'] = str(exc)
            com_erro += 1

        resultados.append(entrada)

    return jsonify({
        'referencia':    referencia,
        'dry_run':       dry_run,
        'total':         len(funcionarios),
        'espelhados':    espelhados,
        'nao_encontrados': nao_achados,
        'erros':         com_erro,
        'resultados':    resultados,
    })
