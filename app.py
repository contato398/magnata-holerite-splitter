"""
magnata-holerite-splitter — app.py v2 — deploy trigger
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
import pdfplumber
import uuid as _uuid
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
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB máx upload

@app.after_request
def _add_cors(response):
    """CORS nativo — sem flask-cors. Suporta file:// e qualquer origem de teste."""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    return response

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


def construir_mapa_cpf(caminho_pdf: str) -> tuple[dict, int]:
    """
    Pass 1 — LEVE.
    Percorre o PDF uma página por vez, extrai apenas CPF + nome + índice.
    Nunca acumula textos nem objetos de página em memória.
    Retorna: ({cpf: {'nome': str, 'paginas': [int]}}, total_paginas)
    """
    mapa: dict = {}
    logger.info(f'[P1] Iniciando varredura | RAM: {_mem_mb()} MB')

    with pdfplumber.open(caminho_pdf) as pdf:
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


def extrair_pdf_colaborador(caminho_pdf: str, indices: list[int]) -> bytes:
    """
    Extrai somente as páginas do colaborador usando pypdf (muito mais leve).
    Retorna bytes do PDF individual e libera todos os objetos temporários.
    """
    reader = PdfReader(caminho_pdf)
    writer = PdfWriter()
    for idx in indices:
        writer.add_page(reader.pages[idx])
    buf = io.BytesIO()
    writer.write(buf)
    resultado = buf.getvalue()
    del reader, writer, buf
    return resultado


def extrair_pdf_do_request() -> str | None:
    """Salva PDF em /tmp (streaming — sem carregar em RAM). Retorna caminho do arquivo."""
    ct = request.content_type or ''
    if 'multipart/form-data' in ct:
        arq = request.files.get('pdf') or (
            next(iter(request.files.values()), None) if request.files else None
        )
        if arq:
            caminho = f'/tmp/holerite_{_uuid.uuid4().hex}.pdf'
            arq.save(caminho)
            tamanho = os.path.getsize(caminho)
            logger.info(f'[PDF] Salvo em disco: {caminho} | {tamanho // 1024} KB')
            return caminho
    elif 'application/json' in ct:
        data = request.get_json(force=True, silent=True) or {}
        if 'pdf_base64' in data:
            try:
                caminho = f'/tmp/holerite_{_uuid.uuid4().hex}.pdf'
                with open(caminho, 'wb') as f:
                    f.write(base64.b64decode(data['pdf_base64']))
                return caminho
            except Exception:
                pass
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
        timeout=30,
    )
    if r.ok:
        records = r.json().get('records', [])
        if records:
            return records[0]['id'], nome
    return None, nome


def buscar_funcionario_por_cpf(cpf: str):
    """Retorna (record_id, nome_completo) ou (None, None).
    Tenta 3 variantes de filtro: formatado, numérico string, numérico inteiro.
    O campo CPF no Airtable pode estar como texto ou como número.
    """
    headers = {'Authorization': f'Bearer {AIRTABLE_API_KEY}'}
    cpf_num = re.sub(r'\D', '', cpf)

    # Variantes de filtro — tenta formatado, string numérica e inteiro puro
    formulas = [
        f'{{CPF}}="{cpf}"',       # "326.052.678-14"
        f'{{CPF}}="{cpf_num}"',   # "32605267814"
        f'{{CPF}}={cpf_num}',     # 32605267814  (campo numérico, sem aspas)
    ]

    for formula in formulas:
        _at_throttle()
        try:
            r = requests.get(
                f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}',
                headers=headers,
                params={
                    'filterByFormula': formula,
                    'maxRecords': 1,
                    'fields[]': ['Nome Completo', 'CPF'],
                },
                timeout=30,
            )
            if r.ok:
                records = r.json().get('records', [])
                if records:
                    nome = records[0].get('fields', {}).get('Nome Completo', '')
                    logger.info(f'[AT] Funcionário encontrado com fórmula: {formula}')
                    return records[0]['id'], nome
        except requests.exceptions.Timeout:
            logger.warning(f'[AT] Timeout na busca de CPF {cpf} (fórmula: {formula})')
            continue
        except Exception as exc:
            logger.warning(f'[AT] Erro na busca de CPF {cpf}: {exc}')
            continue

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
        f'https://content.airtable.com/v0/{BASE_ID}'
        f'/{record_id}/{F_HOL_PDF}/uploadAttachment'
    )
    r = requests.post(
        url,
        headers={
            'Authorization': f'Bearer {AIRTABLE_API_KEY}',
            'Content-Type': 'application/json',
        },
        json={
            'contentType': 'application/pdf',
            'filename': filename,
            'file': base64.b64encode(pdf_bytes).decode('utf-8'),
        },
        timeout=60,
    )
    if not r.ok:
        logger.error(f'[ATTACH] HTTP {r.status_code}: {r.text[:500]}')
    r.raise_for_status()
    return r.json()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'servico': 'magnata-holerite-splitter',
        'versao': '2.4',
        'ram_mb': _mem_mb(),
    })


@app.route('/separar', methods=['POST'])
def separar():
    """Divide o PDF e retorna JSON com base64 por funcionário (sem salvar no Airtable)."""
    try:
        caminho_pdf = extrair_pdf_do_request()
        if not caminho_pdf or not os.path.exists(caminho_pdf) or os.path.getsize(caminho_pdf) < 100:
            return jsonify({'erro': 'PDF não recebido ou inválido.'}), 400
        with open(caminho_pdf, 'rb') as _f:
            _header = _f.read(4)
        if _header != b'%PDF':
            os.unlink(caminho_pdf)
            return jsonify({'erro': 'Dados não são PDF válido.'}), 400

        mapa, _ = construir_mapa_cpf(caminho_pdf)
        if not mapa:
            return jsonify({'erro': 'Nenhum holerite encontrado'}), 422

        funcionarios = []
        for cpf, dados in mapa.items():
            pdf_ind = extrair_pdf_colaborador(caminho_pdf, dados['paginas'])
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
        caminho_pdf = extrair_pdf_do_request()
        if not caminho_pdf or not os.path.exists(caminho_pdf) or os.path.getsize(caminho_pdf) < 100:
            return jsonify({'erro': 'Envie o PDF via "pdf" (multipart) ou "pdf_base64" (JSON)'}), 400

        mapa, _ = construir_mapa_cpf(caminho_pdf)
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for cpf, dados in mapa.items():
                pdf_ind = extrair_pdf_colaborador(caminho_pdf, dados['paginas'])
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
    finally:
        if 'caminho_pdf' in dir() and caminho_pdf and os.path.exists(caminho_pdf):
            os.unlink(caminho_pdf)


@app.route('/processar-holerites', methods=['POST', 'OPTIONS'])
def processar_holerites():
    # Preflight CORS
    if request.method == 'OPTIONS':
        return jsonify({}), 200
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
        caminho_pdf = None
        caminho_pdf = extrair_pdf_do_request()
        if not caminho_pdf or not os.path.exists(caminho_pdf) or os.path.getsize(caminho_pdf) < 100:
            return jsonify({'status': 'erro', 'erro': 'PDF não recebido.', 'etapa': etapa}), 400
        with open(caminho_pdf, 'rb') as _f:
            _header = _f.read(4)
        if _header != b'%PDF':
            os.unlink(caminho_pdf)
            caminho_pdf = None
            return jsonify({'status': 'erro', 'erro': 'Dados não são PDF válido.', 'etapa': etapa}), 400

        pdf_kb = os.path.getsize(caminho_pdf) // 1024
        logger.info(f'[INICIO] PDF salvo em disco: {pdf_kb} KB | RAM: {_mem_mb()} MB')

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
        mapa, total_paginas = construir_mapa_cpf(caminho_pdf)

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
                pdf_ind = extrair_pdf_colaborador(caminho_pdf, paginas)
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

        # Liberar PDF temporário do disco
        if caminho_pdf and os.path.exists(caminho_pdf):
            os.unlink(caminho_pdf)
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
