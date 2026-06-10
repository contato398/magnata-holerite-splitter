import os
import re
import io
import zipfile
import base64
import requests
from calendar import monthrange
from datetime import datetime
from flask import Flask, request, jsonify
import pdfplumber
from pypdf import PdfReader, PdfWriter

app = Flask(__name__)

# ââ Airtable ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY', '')
BASE_ID          = 'appaCpIVj7Q97VhFy'
TABLE_FUNC       = 'tblNd8G66kjwos3eP'   # FuncionÃ¡rios
TABLE_HOL        = 'tblVaUgZeFfa5zRcH'   # Holerites
TABLE_CONT       = 'tblWITpkSbPg4SBAR'   # Contabilidade Mensal

# IDs dos campos em Holerites
F_HOL_NOME     = 'fldS42HdVbLhDRVOY'
F_HOL_STATUS   = 'fld0hQpNpQTVmDSeZ'
F_HOL_FUNC     = 'fldTXMjeHfgyDas9f'
F_HOL_DATA     = 'fld8hTVUDyDf5jfPE'
F_HOL_FOLHA    = 'fldqQZwNnMf8BGfyP'
F_HOL_PDF      = 'fldGXsgmuADtZIgtx'
F_HOL_MES_CONT = 'fldUYB4uxkmBf7vDe'

MESES_PT = [
    'Janeiro', 'Fevereiro', 'MarÃ§o', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
]

# ââ Helpers PDF âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def extrair_cpf(texto):
    if not texto:
        return None
    linhas = texto.split('\n')
    for i, linha in enumerate(linhas):
        if 'CPF' in linha:
            cpf_match = re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', linha)
            if cpf_match:
                return cpf_match.group()
            if i + 1 < len(linhas):
                cpf_match = re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', linhas[i + 1])
                if cpf_match:
                    return cpf_match.group()
    cpf_match = re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', texto)
    if cpf_match:
        return cpf_match.group()
    return None


def extrair_nome_funcionario(texto):
    if not texto:
        return 'Desconhecido'
    linhas = texto.split('\n')
    for i, linha in enumerate(linhas):
        if 'Nome do FuncionÃ¡rio' in linha or 'Nome do Funcionario' in linha:
            if i + 1 < len(linhas):
                proxima = linhas[i + 1].strip()
                partes = proxima.split()
                if partes and partes[0].isdigit():
                    nome_partes = []
                    for p in partes[1:]:
                        if re.match(r'^\d{5,6}$', p):
                            break
                        nome_partes.append(p)
                    if nome_partes:
                        return ' '.join(nome_partes)
    return 'Desconhecido'


def separar_pdf_por_cpf(pdf_bytes):
    resultado = {}
    textos_completos = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        textos_por_pagina = [page.extract_text() or '' for page in pdf.pages]
    reader = PdfReader(io.BytesIO(pdf_bytes))
    grupos = {}
    for i, texto in enumerate(textos_por_pagina):
        cpf  = extrair_cpf(texto)
        nome = extrair_nome_funcionario(texto)
        if cpf is None:
            cpf = f'sem_cpf_{i}'
        if cpf not in grupos:
            grupos[cpf] = {'nome': nome, 'paginas': [], 'textos': []}
        grupos[cpf]['paginas'].append(i)
        grupos[cpf]['textos'].append(texto)
    for cpf, dados in grupos.items():
        writer = PdfWriter()
        for idx in dados['paginas']:
            writer.add_page(reader.pages[idx])
        buf = io.BytesIO()
        writer.write(buf)
        resultado[cpf] = {
            'nome': dados['nome'],
            'pdf_bytes': buf.getvalue(),
            'texto_extraido': '\n---PAGINA---\n'.join(dados['textos'])
        }
    return resultado


def extrair_pdf_do_request():
    """Extrai bytes do PDF de qualquer formato de request."""
    content_type = request.content_type or ''
    pdf_bytes = None
    if 'multipart/form-data' in content_type:
        if 'pdf' in request.files:
            pdf_bytes = request.files['pdf'].read()
        elif request.files:
            pdf_bytes = next(iter(request.files.values())).read()
    elif 'application/json' in content_type:
        data = request.get_json(force=True, silent=True) or {}
        if 'pdf_base64' in data:
            try:
                pdf_bytes = base64.b64decode(data['pdf_base64'])
            except Exception:
                pass
    elif request.data and len(request.data) > 100:
        pdf_bytes = request.data
    return pdf_bytes


# ââ Helpers Airtable ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _at_headers():
    return {
        'Authorization': f'Bearer {AIRTABLE_API_KEY}',
        'Content-Type': 'application/json'
    }


def mes_anterior_info():
    """Retorna (nome_mes_pt, ano, mes_num) do mÃªs anterior ao atual."""
    hoje = datetime.now()
    if hoje.month == 1:
        return MESES_PT[11], hoje.year - 1, 12
    return MESES_PT[hoje.month - 2], hoje.year, hoje.month - 1


def buscar_mes_contabilidade_atual():
    """Busca o registro do mÃªs CORRENTE na Contabilidade Mensal (ex: Junho 2026)."""
    hoje = datetime.now()
    nome = f'{MESES_PT[hoje.month - 1]} {hoje.year}'
    params = {
        'filterByFormula': f'{{MÃªs - Contabilidade}}="{nome}"',
        'maxRecords': 1,
        'fields[]': ['MÃªs - Contabilidade']
    }
    r = requests.get(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_CONT}',
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
        params=params, timeout=10
    )
    if r.ok:
        records = r.json().get('records', [])
        if records:
            return records[0]['id'], nome
    return None, nome


def buscar_funcionario_por_cpf(cpf):
    """Retorna (record_id, nome_completo) ou (None, None)."""
    headers = {'Authorization': f'Bearer {AIRTABLE_API_KEY}'}
    cpf_num = re.sub(r'\D', '', cpf)
    for valor in [cpf, cpf_num]:
        params = {
            'filterByFormula': f'{{CPF}}="{valor}"',
            'maxRecords': 1,
            'fields[]': ['Nome Completo', 'CPF']
        }
        r = requests.get(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}',
            headers=headers, params=params, timeout=10
        )
        if r.ok:
            records = r.json().get('records', [])
            if records:
                nome = records[0].get('fields', {}).get('Nome Completo', '')
                return records[0]['id'], nome
    return None, None


def criar_registro_holerite(nome, func_id, folha_mensal, data_str, mes_cont_id):
    """Cria o registro na tabela Holerites e retorna o record_id."""
    payload = {
        'fields': {
            F_HOL_NOME:     f'{nome} - {folha_mensal}',
            F_HOL_STATUS:   'ConcluÃ­do',
            F_HOL_FUNC:     [func_id],
            F_HOL_DATA:     data_str,
            F_HOL_FOLHA:    folha_mensal,
            F_HOL_MES_CONT: [mes_cont_id],
        }
    }
    r = requests.post(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_HOL}',
        headers=_at_headers(), json=payload, timeout=15
    )
    r.raise_for_status()
    return r.json()['id']


def anexar_pdf_holerite(record_id, pdf_bytes, filename):
    """Faz upload do PDF ao campo PDF HOLERITE do registro."""
    url = (
        f'https://content.airtable.com/v0/{BASE_ID}/{TABLE_HOL}'
        f'/{record_id}/uploadAttachment/{F_HOL_PDF}'
    )
    headers = {'Authorization': f'Bearer {AIRTABLE_API_KEY}'}
    r = requests.post(
        url,
        headers=headers,
        files={'file': (filename, io.BytesIO(pdf_bytes), 'application/pdf')},
        data={'filename': filename, 'contentType': 'application/pdf'},
        timeout=30
    )
    r.raise_for_status()
    return r.json()


# ââ Endpoints âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'servico': 'magnata-holerite-splitter'})


@app.route('/separar', methods=['POST'])
def separar():
    """Divide o PDF e retorna JSON com base64 por funcionÃ¡rio (sem salvar no Airtable)."""
    try:
        pdf_bytes = extrair_pdf_do_request()
        if not pdf_bytes or len(pdf_bytes) < 100:
            return jsonify({'erro': 'PDF nÃ£o recebido ou invÃ¡lido.'}), 400
        if pdf_bytes[:4] != b'%PDF':
            return jsonify({'erro': 'Dados recebidos nÃ£o sÃ£o um PDF vÃ¡lido.',
                            'primeiros_bytes': pdf_bytes[:8].hex()}), 400

        resultado = separar_pdf_por_cpf(pdf_bytes)
        if not resultado:
            return jsonify({'erro': 'Nenhum holerite encontrado no PDF'}), 422

        texto_geral = next(iter(resultado.values()))['texto_extraido'][:4000]
        funcionarios = []
        for cpf, dados in resultado.items():
            pdf_b64 = base64.b64encode(dados['pdf_bytes']).decode('utf-8')
            nome_arquivo = (
                f"holerite_{cpf.replace('.','').replace('-','')}"
                f"_{dados['nome'].replace(' ','_')[:30]}.pdf"
            )
            funcionarios.append({
                'cpf': cpf, 'nome': dados['nome'],
                'nome_arquivo': nome_arquivo, 'pdf_base64': pdf_b64,
                'tamanho_bytes': len(dados['pdf_bytes']),
                'texto_extraido_preview': dados['texto_extraido'][:4000]
            })

        return jsonify({
            'total_funcionarios': len(funcionarios),
            'texto_extraido_preview': texto_geral,
            'funcionarios': funcionarios
        })
    except Exception as e:
        return jsonify({'erro': f'Erro ao processar PDF: {str(e)}'}), 500


@app.route('/separar/zip', methods=['POST'])
def separar_zip():
    """Divide o PDF e retorna um ZIP com todos os holerites individuais."""
    try:
        pdf_bytes = None
        if 'pdf' in request.files:
            pdf_bytes = request.files['pdf'].read()
        elif request.is_json and 'pdf_base64' in request.json:
            pdf_bytes = base64.b64decode(request.json['pdf_base64'])
        else:
            return jsonify({'erro': 'Envie o PDF via campo "pdf" ou "pdf_base64"'}), 400

        resultado = separar_pdf_por_cpf(pdf_bytes)
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for cpf, dados in resultado.items():
                nome_arquivo = (
                    f"holerite_{cpf.replace('.','').replace('-','')}"
                    f"_{dados['nome'].replace(' ','_')[:30]}.pdf"
                )
                zf.writestr(nome_arquivo, dados['pdf_bytes'])
        zip_b64 = base64.b64encode(zip_buf.getvalue()).decode('utf-8')
        return jsonify({
            'total_funcionarios': len(resultado),
            'zip_base64': zip_b64,
            'tamanho_zip_bytes': len(zip_buf.getvalue())
        })
    except Exception as e:
        return jsonify({'erro': f'Erro ao processar PDF: {str(e)}'}), 500


@app.route('/processar-holerites', methods=['POST'])
def processar_holerites():
    """
    Fluxo completo: recebe PDF â divide por CPF â busca funcionÃ¡rio no Airtable
    â cria registro Holerite â anexa PDF individual.

    ParÃ¢metros (form-data ou query string):
      - pdf            : arquivo PDF (multipart) â obrigatÃ³rio
      - folha_mensal   : ex. "Maio 2026" (opcional, auto-detecta pelo mÃªs anterior)
      - mes_cont_id    : record ID da Contabilidade Mensal (opcional, auto-busca)
    """
    if not AIRTABLE_API_KEY:
        return jsonify({'erro': 'AIRTABLE_API_KEY nÃ£o configurada no servidor.'}), 500

    try:
        pdf_bytes = extrair_pdf_do_request()
        if not pdf_bytes or len(pdf_bytes) < 100:
            return jsonify({'erro': 'PDF nÃ£o recebido ou invÃ¡lido.'}), 400
        if pdf_bytes[:4] != b'%PDF':
            return jsonify({'erro': 'Dados recebidos nÃ£o sÃ£o um PDF vÃ¡lido.'}), 400

        # ââ ParÃ¢metros de mÃªs ââââââââââââââââââââââââââââââââââââââââââââââââ
        folha_mensal = (
            request.form.get('folha_mensal')
            or request.args.get('folha_mensal')
            or (request.get_json(silent=True) or {}).get('folha_mensal')
        )
        mes_cont_id = (
            request.form.get('mes_cont_id')
            or request.args.get('mes_cont_id')
            or (request.get_json(silent=True) or {}).get('mes_cont_id')
        )

        # Auto-detecÃ§Ã£o de mÃªs
        nome_mes, ano, mes_num = mes_anterior_info()
        if not folha_mensal:
            folha_mensal = f'{nome_mes} {ano}'
        if not mes_cont_id:
            mes_cont_id, _ = buscar_mes_contabilidade_atual()
            if not mes_cont_id:
                return jsonify({'erro': f'NÃ£o foi possÃ­vel encontrar o registro de Contabilidade Mensal do mÃªs atual. Passe mes_cont_id manualmente.'}), 500

        ultimo_dia = monthrange(ano, mes_num)[1]
        data_holerite = f'{ano}-{mes_num:02d}-{ultimo_dia:02d}'

        # ââ Dividir PDF ââââââââââââââââââââââââââââââââââââââââââââââââââââââ
        holerites = separar_pdf_por_cpf(pdf_bytes)
        if not holerites:
            return jsonify({'erro': 'Nenhum holerite encontrado no PDF'}), 422

        criados = []
        erros   = []

        for cpf, dados in holerites.items():
            nome_pdf = dados['nome']
            is_sem_cpf = cpf.startswith('sem_cpf')

            if is_sem_cpf:
                erros.append({'cpf': 'N/A', 'nome': nome_pdf, 'motivo': 'CPF nÃ£o encontrado na pÃ¡gina'})
                continue

            # Buscar funcionÃ¡rio
            func_id, nome_at = buscar_funcionario_por_cpf(cpf)
            if not func_id:
                erros.append({'cpf': cpf, 'nome': nome_pdf, 'motivo': 'FuncionÃ¡rio nÃ£o encontrado no Airtable'})
                continue

            nome_final = nome_at or nome_pdf
            filename = f'Holerite {folha_mensal} - {nome_final}.pdf'

            try:
                # Criar registro
                record_id = criar_registro_holerite(
                    nome_final, func_id, folha_mensal, data_holerite, mes_cont_id
                )
                # Anexar PDF
                anexar_pdf_holerite(record_id, dados['pdf_bytes'], filename)

                criados.append({
                    'cpf': cpf,
                    'nome': nome_final,
                    'record_id': record_id,
                    'arquivo': filename
                })
            except requests.HTTPError as e:
                erros.append({
                    'cpf': cpf,
                    'nome': nome_final,
                    'motivo': f'Erro Airtable: {e.response.status_code} {e.response.text[:200]}'
                })
            except Exception as e:
                erros.append({'cpf': cpf, 'nome': nome_final, 'motivo': str(e)})

        return jsonify({
            'folha_mensal': folha_mensal,
            'mes_contabilidade_id': mes_cont_id,
            'total_no_pdf': len(holerites),
            'total_criados': len(criados),
            'total_erros': len(erros),
            'criados': criados,
            'erros': erros
        })

    except Exception as e:
        return jsonify({'erro': f'Erro interno: {str(e)}'}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
