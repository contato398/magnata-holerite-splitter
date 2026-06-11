"""
magnata-holerite-splitter — app.py v2
Arquitetura de memória eficiente: 2 passes
  Pass 1: varredura leve (pdfplumber, 1 página por vez) → só guarda CPF + índice
  Pass 2: por colaborador → extrai PDF (pypdf) → Airtable → libera memória → gc
"""

import os
import re
import io
import gc
import time
import zipfile
import base64
import logging
import requests
from calendar import monthrange
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import pdfplumber
from pypdf import PdfReader, PdfWriter

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def _mem_mb():
    """RSS em MB via /proc/self/status (Linux). Retorna -1 se indisponível."""
    try:
        with open('/proc/self/status') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return -1


app = Flask(__name__)
CORS(app)   # permite requisições de qualquer origem (inclusive file://)

# ── Airtable ──────────────────────────────────────────────────────────────────
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY', '')
BASE_ID     = 'appaCpIVj7Q97VhFy'
TABLE_FUNC  = 'tblNd8G66kjwos3eP'   # Funcionários
TABLE_HOL   = 'tblVaUgZeFfa5zRcH'   # Holerites
TABLE_CONT  = 'tblWITpkSbPg4SBAR'   # Contabilidade Mensal

F_HOL_NOME     = 'fldS42HdVbLhDRVOY'
F_HOL_STATUS   = 'fld0hQpNpQTVmDSeZ'
F_HOL_FUNC     = 'fldTXMjeHfgyDas9f'
F_HOL_DATA     = 'fld8hTVUDyDf5jfPE'
F_HOL_FOLHA    = 'fldqQZwNnMf8BGfyP'
F_HOL_PDF      = 'fldGXsgmuADtZIgtx'
F_HOL_MES_CONT = 'fldUYB4uxkmBf7vDe'

MESES_PT = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
]

# ── Rate limiter Airtable: máx 5 req/s por base ───────────────────────────────
_last_at_call = 0.0


def _at_throttle():
    """Garante no máximo ~4,5 chamadas/s à API do Airtable."""
    global _last_at_call
    now = time.monotonic()
    gap = now - _last_at_call
    if gap < 0.23:          # 1/4.5 ≈ 0,22 s
        time.sleep(0.23 - gap)
    _last_at_call = time.monotonic()


def _at_headers():
    return {
        'Authorization': f'Bearer {AIRTABLE_API_KEY}',
        'Content-Type': 'application/json'
    }


# ── Helpers PDF ───────────────────────────────────────────────────────────────

def extrair_cpf(texto: str):
    if not texto:
        return None
    linhas = texto.split('\n')
    for i, linha in enumerate(linhas):
        if 'CPF' in linha:
            m = re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', linha)
            if m:
                return m.group()
            if i + 1 < len(linhas):
                m = re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', linhas[i + 1])
                if m:
                    return m.group()
    m = re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', texto)
    return m.group() if m else None


def extrair_nome_funcionario(texto: str):
    if not texto:
        return 'Desconhecido'
    linhas = texto.split('\n')
    for i, linha in enumerate(linhas):
        if 'Nome do Funcionário' in linha or 'Nome do Funcionario' in linha:
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


def construir_mapa_cpf(pdf_bytes: bytes) -> tuple[dict, int]:
    """
    Pass 1 — LEVE.
    Percorre o PDF uma página por vez, extrai apenas CPF + nome + índice.
    Nunca acumula textos nem objetos de página em memória.
    Retorna: ({cpf: {'nome': str, 'paginas': [int]}}, total_paginas)
    """
    mapa: dict = {}
    logger.info(f'[P1] Iniciando varredura | RAM: {_mem_mb()} MB')

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        total = len(pdf.pages)
        logger.info(f'[P1] Total de páginas: {total}')

        for i in range(total):
            page = pdf.pages[i]
            try:
                texto = page.extract_text() or ''
                cpf   = extrair_cpf(texto)
                nome  = extrair_nome_funcionario(texto)

                # Descartar texto imediatamente — não guardar em lista
                del texto

                if not cpf:
                    cpf = f'sem_cpf_{i}'

                if cpf not in mapa:
                    mapa[cpf] = {'nome': nome, 'paginas': []}
                mapa[cpf]['paginas'].append(i)

                logger.info(f'[P1] Pág {i+1:03d}/{total}: CPF={cpf} | Nome={nome}')

            except Exception as exc:
                logger.warning(f'[P1] Pág {i+1}/{total}: erro → {exc}')
                mapa[f'sem_cpf_{i}'] = {'nome': 'Erro extração', 'paginas': [i]}

            # GC a cada 15 páginas
            if (i + 1) % 15 == 0:
                gc.collect()
                logger.info(f'[P1] GC executado | RAM: {_mem_mb()} MB')

    gc.collect()
    logger.info(f'[P1] Concluído: {len(mapa)} colaboradores | RAM: {_mem_mb()} MB')
    return mapa, total


def extrair_pdf_colaborador(pdf_bytes: bytes, indices: list[int]) -> bytes:
    """
    Extrai somente as páginas do colaborador usando pypdf (muito mais leve).
    Retorna bytes do PDF individual e libera todos os objetos temporários.
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for idx in indices:
        writer.add_page(reader.pages[idx])
    buf = io.BytesIO()
    writer.write(buf)
    resultado = buf.getvalue()
    del reader, writer, buf
    return resultado


def extrair_pdf_do_request() -> bytes | None:
    """Extrai bytes do PDF do request (multipart, json base64, ou raw)."""
    ct = request.content_type or ''
    if 'multipart/form-data' in ct:
        if 'pdf' in request.files:
            return request.files['pdf'].read()
        if request.files:
            return next(iter(request.files.values())).read()
    elif 'application/json' in ct:
        data = request.get_json(force=True, silent=True) or {}
        if 'pdf_base64' in data:
            try:
                return base64.b64decode(data['pdf_base64'])
            except Exception:
                pass
    elif request.data and len(request.data) > 100:
        return request.data
    return None


# ── Helpers Airtable ──────────────────────────────────────────────────────────

def mes_anterior_info():
    hoje = datetime.now()
    if hoje.month == 1:
        return MESES_PT[11], hoje.year - 1, 12
    return MESES_PT[hoje.month - 2], hoje.year, hoje.month - 1


def buscar_mes_contabilidade_atual():
    hoje = datetime.now()
    nome = f'{MESES_PT[hoje.month - 1]} {hoje.year}'
    _at_throttle()
    r = requests.get(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_CONT}',
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
        params={
            'filterByFormula': f'{{Mês - Contabilidade}}="{nome}"',
            'maxRecords': 1,
            'fields[]': ['Mês - Contabilidade'],
        },
        timeout=10,
    )
    if r.ok:
        records = r.json().get('records', [])
        if records:
            return records[0]['id'], nome
    return None, nome


def buscar_funcionario_por_cpf(cpf: str):
    """Retorna (record_id, nome_completo) ou (None, None)."""
    headers = {'Authorization': f'Bearer {AIRTABLE_API_KEY}'}
    cpf_num = re.sub(r'\D', '', cpf)
    for valor in [cpf, cpf_num]:
        _at_throttle()
        r = requests.get(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}',
            headers=headers,
            params={
                'filterByFormula': f'{{CPF}}="{valor}"',
                'maxRecords': 1,
                'fields[]': ['Nome Completo', 'CPF'],
            },
            timeout=10,
        )
        if r.ok:
            records = r.json().get('records', [])
            if records:
                nome = records[0].get('fields', {}).get('Nome Completo', '')
                return records[0]['id'], nome
    return None, None


def criar_registro_holerite(nome, func_id, folha_mensal, data_str, mes_cont_id):
    _at_throttle()
    r = requests.post(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_HOL}',
        headers=_at_headers(),
        json={
            'fields': {
                F_HOL_NOME:     f'{nome} - {folha_mensal}',
                F_HOL_STATUS:   'Concluído',
                F_HOL_FUNC:     [func_id],
                F_HOL_DATA:     data_str,
                F_HOL_FOLHA:    folha_mensal,
                F_HOL_MES_CONT: [mes_cont_id],
            }
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()['id']


def anexar_pdf_holerite(record_id, pdf_bytes, filename):
    _at_throttle()
    url = (
        f'https://content.airtable.com/v0/{BASE_ID}/{TABLE_HOL}'
        f'/{record_id}/uploadAttachment/{F_HOL_PDF}'
    )
    r = requests.post(
        url,
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
        files={'file': (filename, io.BytesIO(pdf_bytes), 'application/pdf')},
        data={'filename': filename, 'contentType': 'application/pdf'},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'servico': 'magnata-holerite-splitter',
        'versao': '2.0',
        'ram_mb': _mem_mb(),
    })


@app.route('/separar', methods=['POST'])
def separar():
    """Divide o PDF e retorna JSON com base64 por funcionário (sem salvar no Airtable)."""
    try:
        pdf_bytes = extrair_pdf_do_request()
        if not pdf_bytes or len(pdf_bytes) < 100:
            return jsonify({'erro': 'PDF não recebido ou inválido.'}), 400
        if pdf_bytes[:4] != b'%PDF':
            return jsonify({'erro': 'Dados não são PDF válido.',
                            'primeiros_bytes': pdf_bytes[:8].hex()}), 400

        mapa, _ = construir_mapa_cpf(pdf_bytes)
        if not mapa:
            return jsonify({'erro': 'Nenhum holerite encontrado'}), 422

        funcionarios = []
        for cpf, dados in mapa.items():
            pdf_ind = extrair_pdf_colaborador(pdf_bytes, dados['paginas'])
            pdf_b64 = base64.b64encode(pdf_ind).decode('utf-8')
            nome_arq = (
                f"holerite_{cpf.replace('.','').replace('-','')}"
                f"_{dados['nome'].replace(' ','_')[:30]}.pdf"
            )
            funcionarios.append({
                'cpf': cpf, 'nome': dados['nome'],
                'nome_arquivo': nome_arq, 'pdf_base64': pdf_b64,
                'tamanho_bytes': len(pdf_ind),
            })
            del pdf_ind, pdf_b64
            gc.collect()

        return jsonify({
            'total_funcionarios': len(funcionarios),
            'funcionarios': funcionarios,
        })
    except Exception as exc:
        logger.exception('Erro em /separar')
        return jsonify({'erro': str(exc), 'etapa': 'separar'}), 500


@app.route('/separar/zip', methods=['POST'])
def separar_zip():
    """Divide o PDF e retorna um ZIP com os holerites individuais."""
    try:
        pdf_bytes = None
        if 'pdf' in request.files:
            pdf_bytes = request.files['pdf'].read()
        elif request.is_json and 'pdf_base64' in request.json:
            pdf_bytes = base64.b64decode(request.json['pdf_base64'])
        else:
            return jsonify({'erro': 'Envie o PDF via "pdf" (multipart) ou "pdf_base64" (JSON)'}), 400

        mapa, _ = construir_mapa_cpf(pdf_bytes)
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for cpf, dados in mapa.items():
                pdf_ind = extrair_pdf_colaborador(pdf_bytes, dados['paginas'])
                nome_arq = (
                    f"holerite_{cpf.replace('.','').replace('-','')}"
                    f"_{dados['nome'].replace(' ','_')[:30]}.pdf"
                )
                zf.writestr(nome_arq, pdf_ind)
                del pdf_ind
                gc.collect()

        zip_b64 = base64.b64encode(zip_buf.getvalue()).decode('utf-8')
        return jsonify({
            'total_funcionarios': len(mapa),
            'zip_base64': zip_b64,
            'tamanho_zip_bytes': len(zip_buf.getvalue()),
        })
    except Exception as exc:
        logger.exception('Erro em /separar/zip')
        return jsonify({'erro': str(exc), 'etapa': 'separar_zip'}), 500


@app.route('/processar-holerites', methods=['POST'])
def processar_holerites():
    """
    Fluxo completo — memória eficiente:
      1. Recebe o PDF
      2. Pass 1: varredura leve página por página → mapa CPF→páginas
      3. Pass 2: por colaborador → extrai PDF → cria registro Airtable
                 → anexa PDF → libera memória → gc → próximo

    Parâmetros (form-data ou query string):
      pdf            — arquivo PDF (multipart)         [obrigatório]
      folha_mensal   — ex. "Maio 2026"                 [opcional, auto-detecta]
      mes_cont_id    — ID da Contabilidade Mensal       [opcional, auto-busca]

    Retorna sempre JSON, inclusive em caso de erro.
    """
    etapa = 'init'

    try:
        if not AIRTABLE_API_KEY:
            return jsonify({
                'status': 'erro',
                'erro': 'AIRTABLE_API_KEY não configurada no servidor.',
                'etapa': etapa,
            }), 500

        # 1. Receber PDF
        etapa = 'receber_pdf'
        pdf_bytes = extrair_pdf_do_request()
        if not pdf_bytes or len(pdf_bytes) < 100:
            return jsonify({'status': 'erro', 'erro': 'PDF não recebido.', 'etapa': etapa}), 400
        if pdf_bytes[:4] != b'%PDF':
            return jsonify({'status': 'erro', 'erro': 'Dados não são PDF válido.', 'etapa': etapa}), 400

        pdf_kb = len(pdf_bytes) // 1024
        logger.info(f'[INICIO] PDF recebido: {pdf_kb} KB | RAM: {_mem_mb()} MB')

        # 2. Parâmetros de mês
        etapa = 'parametros_mes'
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

        nome_mes, ano, mes_num = mes_anterior_info()
        if not folha_mensal:
            folha_mensal = f'{nome_mes} {ano}'

        etapa = 'buscar_mes_contabilidade'
        if not mes_cont_id:
            mes_cont_id, nome_mes_cont = buscar_mes_contabilidade_atual()
            if not mes_cont_id:
                return jsonify({
                    'status': 'erro',
                    'erro': f'Contabilidade Mensal do mês atual não encontrada ({nome_mes_cont}). '
                            'Passe mes_cont_id manualmente.',
                    'etapa': etapa,
                }), 500

        ultimo_dia    = monthrange(ano, mes_num)[1]
        data_holerite = f'{ano}-{mes_num:02d}-{ultimo_dia:02d}'

        logger.info(
            f'[CONFIG] folha_mensal={folha_mensal} | data={data_holerite} | mes_cont_id={mes_cont_id}'
        )

        # 3. Pass 1: mapa CPF → páginas (leve)
        etapa = 'pass1_mapear_cpf'
        mapa, total_paginas = construir_mapa_cpf(pdf_bytes)

        if not mapa:
            return jsonify({
                'status': 'erro', 'erro': 'Nenhum CPF encontrado no PDF.', 'etapa': etapa,
            }), 422

        total_colab = len(mapa)
        logger.info(
            f'[P2] Iniciando criação no Airtable | '
            f'{total_colab} colaboradores | {total_paginas} páginas | RAM: {_mem_mb()} MB'
        )

        criados: list = []
        erros:   list = []
        contador = 0

        # 4. Pass 2: um colaborador por vez
        for cpf, dados in mapa.items():
            contador += 1
            nome_pdf  = dados['nome']
            paginas   = dados['paginas']
            tag       = f'[P2 {contador:02d}/{total_colab}]'

            # Colaborador sem CPF identificado
            if cpf.startswith('sem_cpf'):
                logger.warning(f'{tag} CPF não extraído | págs: {paginas}')
                erros.append({
                    'cpf': 'N/A', 'nome': nome_pdf,
                    'motivo': 'CPF não extraído da página',
                    'paginas': paginas,
                })
                continue

            # Buscar funcionário no Airtable
            etapa = f'buscar_funcionario:{cpf}'
            func_id, nome_at = buscar_funcionario_por_cpf(cpf)
            if not func_id:
                logger.warning(f'{tag} Funcionário não encontrado | CPF: {cpf}')
                erros.append({
                    'cpf': cpf, 'nome': nome_pdf,
                    'motivo': 'Funcionário não encontrado no Airtable',
                })
                continue

            nome_final = nome_at or nome_pdf
            filename   = f'Holerite {folha_mensal} - {nome_final}.pdf'
            logger.info(f'{tag} {nome_final} (CPF: {cpf}) | págs: {paginas}')

            pdf_ind = None
            try:
                # Extrair PDF individual (somente as páginas do colaborador)
                etapa  = f'extrair_pdf:{cpf}'
                pdf_ind = extrair_pdf_colaborador(pdf_bytes, paginas)
                logger.info(f'{tag} PDF: {len(pdf_ind)//1024} KB | RAM: {_mem_mb()} MB')

                # Criar registro no Airtable
                etapa     = f'criar_registro:{cpf}'
                record_id = criar_registro_holerite(
                    nome_final, func_id, folha_mensal, data_holerite, mes_cont_id
                )
                logger.info(f'{tag} Registro criado: {record_id}')

                # Anexar PDF ao registro
                etapa = f'anexar_pdf:{cpf}'
                anexar_pdf_holerite(record_id, pdf_ind, filename)
                logger.info(f'{tag} PDF anexado ✓')

                criados.append({
                    'cpf': cpf, 'nome': nome_final,
                    'record_id': record_id, 'arquivo': filename,
                    'paginas': paginas,
                })

            except requests.HTTPError as exc:
                motivo = f'HTTP {exc.response.status_code}: {exc.response.text[:300]}'
                logger.error(f'{tag} ERRO Airtable: {motivo}')
                erros.append({
                    'cpf': cpf, 'nome': nome_final,
                    'motivo': motivo, 'etapa': etapa,
                })
            except Exception as exc:
                logger.exception(f'{tag} ERRO inesperado: {exc}')
                erros.append({
                    'cpf': cpf, 'nome': nome_final,
                    'motivo': str(exc), 'etapa': etapa,
                })
            finally:
                # Liberar memória do PDF individual, seja sucesso ou erro
                if pdf_ind is not None:
                    del pdf_ind
                gc.collect()

        # Liberar PDF original
        del pdf_bytes
        gc.collect()

        logger.info(
            f'[FIM] páginas={total_paginas} | colaboradores={total_colab} | '
            f'criados={len(criados)} | erros={len(erros)} | RAM: {_mem_mb()} MB'
        )

        return jsonify({
            'status': 'concluido',
            'folha_mensal': folha_mensal,
            'mes_contabilidade_id': mes_cont_id,
            'total_paginas': total_paginas,
            'total_colaboradores': total_colab,
            'total_criados': len(criados),
            'total_erros': len(erros),
            'criados': criados,
            'erros': erros,
        })

    except Exception as exc:
        logger.exception(f'[ERRO CRÍTICO] etapa={etapa}')
        return jsonify({
            'status': 'erro_critico',
            'erro': str(exc),
            'etapa': etapa,
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
