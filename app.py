import os
import re
import io
import zipfile
import base64
from flask import Flask, request, jsonify
import pdfplumber
from pypdf import PdfReader, PdfWriter

app = Flask(__name__)

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
        return "Desconhecido"
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
    return "Desconhecido"

def separar_pdf_por_cpf(pdf_bytes):
    resultado = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        textos_por_pagina = []
        for page in pdf.pages:
            texto = page.extract_text() or ''
            textos_por_pagina.append(texto)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    cpfs_por_pagina = []
    for i, texto in enumerate(textos_por_pagina):
        cpf = extrair_cpf(texto)
        nome = extrair_nome_funcionario(texto)
        cpfs_por_pagina.append({'cpf': cpf, 'nome': nome, 'pagina_idx': i})
    grupos = {}
    for item in cpfs_por_pagina:
        cpf = item['cpf']
        if cpf is None:
            cpf = 'sem_cpf'
        if cpf not in grupos:
            grupos[cpf] = {'nome': item['nome'], 'paginas': []}
        grupos[cpf]['paginas'].append(item['pagina_idx'])
    for cpf, dados in grupos.items():
        writer = PdfWriter()
        for idx in dados['paginas']:
            writer.add_page(reader.pages[idx])
        buf = io.BytesIO()
        writer.write(buf)
        resultado[cpf] = {
            'nome': dados['nome'],
            'pdf_bytes': buf.getvalue()
        }
    return resultado

def tentar_extrair_pdf(valor):
    if not valor:
        return None
    if isinstance(valor, bytes):
        if valor[:4] == b'%PDF':
            return valor
        try:
            decoded = base64.b64decode(valor)
            if decoded[:4] == b'%PDF':
                return decoded
        except:
            pass
        return valor
    if isinstance(valor, str):
        try:
            decoded = base64.b64decode(valor)
            if decoded[:4] == b'%PDF':
                return decoded
        except:
            pass
        try:
            padded = valor + '=' * (4 - len(valor) % 4)
            decoded = base64.urlsafe_b64decode(padded)
            if decoded[:4] == b'%PDF':
                return decoded
        except:
            pass
        try:
            as_bytes = valor.encode('latin-1')
            if as_bytes[:4] == b'%PDF':
                return as_bytes
        except:
            pass
        try:
            as_bytes = bytes.fromhex(valor.replace(' ', ''))
            if as_bytes[:4] == b'%PDF':
                return as_bytes
        except:
            pass
        try:
            return valor.encode('latin-1')
        except:
            return valor.encode('utf-8', errors='replace')
    return None

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'servico': 'magnata-holerite-splitter'})

@app.route('/analisar', methods=['POST'])
def analisar():
    try:
        pdf_bytes = None
        content_type = request.content_type or ''
        if 'application/json' in content_type:
            data = request.get_json(force=True, silent=True) or {}
            if 'pdf_base64' in data:
                pdf_bytes = tentar_extrair_pdf(data['pdf_base64'])
        if not pdf_bytes or len(pdf_bytes) < 100:
            return jsonify({'erro': 'PDF nao recebido'}), 400
        paginas = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                texto = page.extract_text() or ''
                paginas.append({'pagina': i + 1, 'texto': texto[:500]})
        return jsonify({'paginas': paginas})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/separar', methods=['POST'])
def separar():
    try:
        pdf_bytes = None
        content_type = request.content_type or ''
        debug_info = {
            'content_type': content_type,
            'tamanho_body': len(request.data),
            'campos_form': list(request.files.keys()),
        }
        if 'multipart/form-data' in content_type and 'pdf' in request.files:
            pdf_bytes = request.files['pdf'].read()
        elif 'multipart/form-data' in content_type and request.files:
            for key in request.files:
                pdf_bytes = request.files[key].read()
                break
        elif 'application/json' in content_type:
            data = request.get_json(force=True, silent=True) or {}
            if 'pdf_base64' in data:
                valor = data['pdf_base64']
                pdf_bytes = tentar_extrair_pdf(valor)
                debug_info['pdf_base64_tamanho'] = len(str(valor))
                debug_info['pdf_base64_primeiros'] = str(valor)[:100]
        elif request.data and len(request.data) > 100:
            pdf_bytes = request.data
        if not pdf_bytes or len(pdf_bytes) < 100:
            return jsonify({'erro': 'PDF nao recebido ou invalido.', 'debug': debug_info}), 400
        is_pdf = pdf_bytes[:4] == b'%PDF'
        debug_info['comeca_com_pdf'] = is_pdf
        debug_info['primeiros_bytes'] = pdf_bytes[:8].hex()
        debug_info['tamanho_recebido'] = len(pdf_bytes)
        if not is_pdf:
            return jsonify({'erro': 'Dados recebidos nao sao um PDF valido.', 'debug': debug_info}), 400
        resultado = separar_pdf_por_cpf(pdf_bytes)
        if not resultado:
            return jsonify({'erro': 'Nenhum holerite encontrado no PDF'}), 422
        funcionarios = []
        for cpf, dados in resultado.items():
            pdf_b64 = base64.b64encode(dados['pdf_bytes']).decode('utf-8')
            nome_arquivo = f"holerite_{cpf.replace('.', '').replace('-', '')}_{dados['nome'].replace(' ', '_')[:30]}.pdf"
            funcionarios.append({
                'cpf': cpf,
                'nome': dados['nome'],
                'nome_arquivo': nome_arquivo,
                'pdf_base64': pdf_b64,
                'tamanho_bytes': len(dados['pdf_bytes'])
            })
        return jsonify({'total_funcionarios': len(funcionarios), 'funcionarios': funcionarios})
    except Exception as e:
        return jsonify({'erro': f'Erro ao processar PDF: {str(e)}'}), 500

@app.route('/separar/zip', methods=['POST'])
def separar_zip():
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
                nome_arquivo = f"holerite_{cpf.replace('.', '').replace('-', '')}_{dados['nome'].replace(' ', '_')[:30]}.pdf"
                zf.writestr(nome_arquivo, dados['pdf_bytes'])
        zip_b64 = base64.b64encode(zip_buf.getvalue()).decode('utf-8')
        return jsonify({'total_funcionarios': len(resultado), 'zip_base64': zip_b64, 'tamanho_zip_bytes': len(zip_buf.getvalue())})
    except Exception as e:
        return jsonify({'erro': f'Erro ao processar PDF: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
