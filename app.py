from flask import Flask, request, jsonify
import fitz  # pymupdf
import re
import base64
import io

app = Flask(__name__)

def extrair_cpf(texto):
    """Extrai CPF do texto da página no formato XXX.XXX.XXX-XX"""
    padrao = r'\d{3}\.\d{3}\.\d{3}-\d{2}'
    cpfs = re.findall(padrao, texto)
    return cpfs[0] if cpfs else None

def extrair_nome(texto):
    """Tenta extrair o nome do funcionário da página"""
    linhas = texto.split('\n')
    for i, linha in enumerate(linhas):
        if 'Nome do Funcion' in linha or 'NOME DO FUNCION' in linha:
            # Nome geralmente vem antes ou depois desta linha
            if i > 0:
                nome = linhas[i-1].strip()
                if nome and len(nome) > 3:
                    return nome
    # Fallback: busca padrão de nomes em maiúsculas
    padrao_nome = r'\b[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÈÌÒÙÇ]{2,}(?:\s+[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÈÌÒÙÇ]{2,}){2,}\b'
    nomes = re.findall(padrao_nome, texto)
    # Filtra palavras que são certamente não-nomes
    ignorar = {'MAGNATA', 'PORTARIA', 'SERVICOS', 'LTDA', 'CNPJ', 'CONTROLADOR',
                'ACESSO', 'ADMISSAO', 'SALARIO', 'TOTAL', 'VALOR', 'INSS',
                'FGTS', 'IRRF', 'BASE', 'CALC', 'MENSAL', 'FOLHA', 'NORMAL'}
    for nome in nomes:
        palavras = set(nome.split())
        if not palavras.intersection(ignorar) and len(nome) > 8:
            return nome
    return None

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'servico': 'Holerite Splitter - Magnata'})

@app.route('/separar', methods=['POST'])
def separar_holerites():
    """
    Recebe um PDF em base64, separa por página (1 página = 1 funcionário)
    e retorna lista de PDFs individuais em base64 com CPF e nome.
    
    Body JSON esperado:
    {
        "pdf_base64": "<string base64 do PDF>",
        "mes_ano": "Maio2026"  (opcional, para nomear os arquivos)
    }
    """
    dados = request.get_json()

    if not dados or 'pdf_base64' not in dados:
        return jsonify({'erro': 'Campo pdf_base64 obrigatório'}), 400

    mes_ano = dados.get('mes_ano', 'MesAtual')

    try:
        # Decodifica o PDF
        pdf_bytes = base64.b64decode(dados['pdf_base64'])
        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        total_paginas = len(doc)

        resultados = []
        erros = []

        for i in range(total_paginas):
            pagina = doc[i]
            texto = pagina.get_text()

            cpf = extrair_cpf(texto)
            nome = extrair_nome(texto)

            if not cpf:
                erros.append({
                    'pagina': i + 1,
                    'erro': 'CPF não encontrado nesta página'
                })
                continue

            # Cria PDF individual com apenas esta página
            doc_individual = fitz.open()
            doc_individual.insert_pdf(doc, from_page=i, to_page=i)

            buffer = io.BytesIO()
            doc_individual.save(buffer)
            doc_individual.close()
            buffer.seek(0)
            pdf_individual_base64 = base64.b64encode(buffer.read()).decode('utf-8')

            # Nome do arquivo: Holerite_NOME_MesAno.pdf
            cpf_limpo = cpf.replace('.', '').replace('-', '')
            nome_arquivo = f"Holerite_{nome.replace(' ', '_') if nome else cpf_limpo}_{mes_ano}.pdf"

            resultados.append({
                'pagina': i + 1,
                'cpf': cpf,
                'cpf_limpo': cpf_limpo,
                'nome': nome or 'Não identificado',
                'nome_arquivo': nome_arquivo,
                'pdf_base64': pdf_individual_base64
            })

        doc.close()

        return jsonify({
            'sucesso': True,
            'total_paginas': total_paginas,
            'total_processados': len(resultados),
            'total_erros': len(erros),
            'holerites': resultados,
            'erros': erros
        })

    except Exception as e:
        return jsonify({'erro': str(e), 'sucesso': False}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
