"""
magnata-holerite-splitter — app.py v2.6
Novidades vs v2.5:
  - Novo endpoint /email/webhook (Fase 2 - Caixa de Entrada):
    recebe e-mails/anexos via Google Apps Script, registra em
    Emails Savian / Arquivos / Processar Arquivos, classifica o tipo de
    documento e cria pendências quando necessário. Suporta dry_run e
    é protegido por X-API-KEY.
"""

import os
import re
import io
import json
import gc
import time
import zipfile
import base64
import hashlib
import logging
import requests
from collections import Counter
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

F_HOL_NOME      = 'fldS42HdVbLhDRVOY'
F_HOL_STATUS    = 'fld0hQpNpQTVmDSeZ'
F_HOL_FUNC      = 'fldTXMjeHfgyDas9f'
F_HOL_DATA      = 'fld8hTVUDyDf5jfPE'
F_HOL_FOLHA     = 'fldqQZwNnMf8BGfyP'
F_HOL_PDF       = 'fldGXsgmuADtZIgtx'
F_HOL_MES_CONT  = 'fldUYB4uxkmBf7vDe'
F_HOL_VENCIM    = 'fldOal5gy1aqF5RPT'   # Total Vencimentos
F_HOL_DESCONTOS = 'fldRiNiS9Rqfjo5Hg'   # Total Descontos
F_HOL_LIQUIDO   = 'fldnOzg7FcXxes2dm'   # Valor Líquido
F_HOL_INSS      = 'fldvDY9x8dC0FCLrd'   # Descontos INSS

# Funcionários — campos usados no pré-cadastro (Fase 5C)
F_FUNC_STATUS    = 'fld5T04dlg1Yt6Xj8'
F_FUNC_CARGO     = 'fldK1lJS1L4tbZVmZ'
F_FUNC_CPF       = 'fld0Y3bXdArkSIJxo'
F_FUNC_NOME      = 'fld2fSiomk9AOLGDb'   # Nome Completo
F_FUNC_ADMISSAO  = 'fld5L1djmJugvLe8c'   # Data de Admissão
F_FUNC_PDF_FOLHA = 'fldgBhXpEFmy20yxd'   # PDF Folha Ponto (prontuário)

# ── Tabelas/Campos Fase 2 — Caixa de Entrada ─────────────────────────────────
TABLE_EMAILS     = 'tblljRRrraXSipJd1'   # Emails Savian
TABLE_ARQUIVOS   = 'tblRsvhz8oOcUqhkv'   # Arquivos
TABLE_PROCESSAR  = 'tblXaLXvGJMyFOayc'   # Processar Arquivos
TABLE_PENDENCIAS = 'tblRkJBL6Wwf4fxVC'   # Pendências/Revisar

# ── Tabelas — Diagnóstico de Distribuição (read-only) ────────────────────────
TABLE_LOCAIS    = 'tblZy1WfzmGIeR8ZP'   # Locais
TABLE_CLIENTES  = 'tbl0znyuCEzoCHtCV'   # Clientes
TABLE_ENVIOS    = 'tblAu4wgdfTgLOoa4'   # Envios de Documentos

# Emails Savian
F_EMAIL_NAME     = 'fldwKHHiVVEKySwx4'
F_EMAIL_STATUS   = 'fld44SrJN9Va8avMX'
F_EMAIL_ASSUNTO  = 'fld66diI0hksJE5PS'
F_EMAIL_CONTEUDO = 'fldzi2kWBoT2kfEhL'
F_EMAIL_MSGID    = 'fldCCdUEMF3hlTngA'

# Arquivos
F_ARQ_NOME     = 'fldjVGYri7DZDJuee'   # Arquivo (campo primário)
F_ARQ_STATUS   = 'fld9yxb30SlLJxqoM'
F_ARQ_DATA     = 'fldKcfvu5Anec54xa'
F_ARQ_ATTACH   = 'fldm6S1xnp8S6sKFE'
F_ARQ_EMAILS   = 'fld2yYAHWe0smV5Bb'
F_ARQ_NOME_ARQ = 'fldsOySQRfZ8rPGDw'   # Nome do Arquivo
F_ARQ_HASH     = 'fldOB09YlKDEqKSFO'  # Hash do Anexo

# Processar Arquivos
F_PROC_NAME      = 'fldmrG1ZTHHU4QYQK'
F_PROC_STATUS    = 'fldvN9T5MiuKZGDi0'
F_PROC_DATA      = 'flddNzmqp1Im1D02m'
F_PROC_ARQUIVOS2 = 'fldLWSmK81i8jbtCG'
F_PROC_TIPO_DOC  = 'fldvkOVlwCMywGTES'

# Pendências/Revisar
F_PEND_NOME   = 'fldovcs6bySCshoXI'
F_PEND_STATUS = 'fldf1an8HCV2DxEwk'
F_PEND_TIPO   = 'fldyZgyB5F5fv6kUX'
F_PEND_ORIGEM = 'fldUk3hr2mCkfu1Wb'
F_PEND_OBS    = 'fld2bqGLlotCVRBn5'
F_PEND_DATA   = 'fldRolmP0rSbJevUZ'

EMAIL_WEBHOOK_KEY = os.environ.get('EMAIL_WEBHOOK_KEY', '')

# Regras de classificação de documento (Fase 2)
# Lista de (tipo_documento, [regex de palavras-chave]) — primeira que casar vence
TIPO_DOC_REGRAS = [
    ('Holerite', [r'Recibo\s+de\s+Pagamento', r'Total\s+de\s+Vencimentos', r'Valor\s+L[íi]quido']),
    ('Folha de Ponto', [r'Folha\s+de\s+Ponto', r'Espelho\s+de\s+Ponto']),
    ('Contrato de Experiência', [r'Contrato\s+de\s+Experi[êe]ncia']),
    ('Contrato de Trabalho', [r'Contrato\s+de\s+Trabalho', r'\bCTPS\b']),
    ('Férias', [r'Aviso\s+de\s+F[ée]rias', r'Recibo\s+de\s+F[ée]rias', r'Per[íi]odo\s+de\s+Gozo']),
    ('FGTS', [r'FGTS\s+Digital', r'Guia\s+do\s+FGTS', r'\bGFD\b']),
    ('Guia', [r'Guia\s+de\s+Recolhimento', r'\bGPS\b', r'\bDARF\b']),
    ('Boleto', [r'\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d\s+\d{14}', r'Linha\s+Digit[áa]vel']),
    ('Nota Fiscal', [r'NFS-?e', r'Nota\s+Fiscal\s+de\s+Servi[çc]o', r'DANFE']),
]


def classificar_documento(texto: str):
    """Retorna (tipo_documento, confianca) com base em palavras-chave no texto extraído."""
    for tipo, padroes in TIPO_DOC_REGRAS:
        hits = sum(1 for p in padroes if re.search(p, texto, re.IGNORECASE))
        if hits > 0:
            return tipo, hits
    return 'Outro', 0


MESES_PT = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
]

# ── Rate limiter Airtable ─────────────────────────────────────────────────────
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
        'Content-Type': 'application/json'
    }


# ── Erros Airtable (Fase 6 — diagnóstico/sanitização) ────────────────────────

class AirtableError(Exception):
    """
    Erro de gravação/leitura no Airtable que preserva o motivo exato
    retornado pela API (status HTTP + corpo da resposta), em vez de deixar
    apenas a mensagem genérica de requests.raise_for_status() ("422 Client
    Error: Unprocessable Entity for url: ...").
    """

    def __init__(self, status_code: int, body_text: str, context: str = ''):
        self.status_code = status_code
        self.body_text = body_text or ''
        self.context = context
        try:
            self.error_json = json.loads(body_text) if body_text else None
        except ValueError:
            self.error_json = None
        super().__init__(self._mensagem())

    def _mensagem(self) -> str:
        detalhe = None
        if isinstance(self.error_json, dict):
            err = self.error_json.get('error')
            if isinstance(err, dict):
                detalhe = f"{err.get('type', '')}: {err.get('message', '')}".strip(': ')
            elif isinstance(err, str):
                detalhe = err
        if not detalhe:
            detalhe = self.body_text[:300]
        prefixo = f'[{self.context}] ' if self.context else ''
        return f'{prefixo}Airtable HTTP {self.status_code}: {detalhe}'


def _raise_for_airtable(r, context: str = ''):
    """Loga e levanta AirtableError com o erro exato retornado pela API, se a resposta não for 2xx."""
    if not r.ok:
        logger.error(f'[AT] {context} HTTP {r.status_code}: {r.text[:1000]}')
        raise AirtableError(r.status_code, r.text, context)


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


def parse_br_float(s: str):
    """Converte string no formato brasileiro '1.234,56' para float."""
    try:
        return float(s.replace('.', '').replace(',', '.'))
    except Exception:
        return None


def extrair_valores_holerite(texto: str) -> dict:
    """
    Extrai valores financeiros do texto de um holerite.

    Formato esperado no PDF:
      ...
      998 INSS M2  7,94  181,79
      Total de Vencimentos  Total de Descontos
      181,79

      Valor Líquido  2.108,34
      ...

    Retorna dict com chaves (todas opcionais):
      total_descontos, valor_liquido, total_vencimentos, inss
    """
    if not texto:
        return {}

    resultado = {}

    # 1. Valor Líquido — "Valor Líquido 2.108,34" (pode ser 0,00 para afastados INSS)
    m = re.search(
        r'Valor\s+L[íi]quido\s+([\d.]+,\d{2})',
        texto, re.IGNORECASE
    )
    if m:
        v = parse_br_float(m.group(1))
        if v is not None:
            resultado['valor_liquido'] = v

    # 2. Total Descontos — primeiro número após a linha dupla de totais
    #    "Total de Vencimentos  Total de Descontos\n182,55"
    m = re.search(
        r'Total\s+de\s+Vencimentos\s+Total\s+de\s+Descontos\s*\n\s*([\d.]+,\d{2})',
        texto, re.IGNORECASE
    )
    if m:
        v = parse_br_float(m.group(1))
        if v is not None:
            resultado['total_descontos'] = v
    else:
        # fallback: procura "Total de Descontos" seguido do valor na mesma ou próxima linha
        m = re.search(
            r'Total\s+de\s+Descontos\s+([\d.]+,\d{2})',
            texto, re.IGNORECASE
        )
        if m:
            v = parse_br_float(m.group(1))
            if v is not None:
                resultado['total_descontos'] = v

    # 3. Total Vencimentos = Total Descontos + Valor Líquido
    if 'total_descontos' in resultado and 'valor_liquido' in resultado:
        resultado['total_vencimentos'] = round(
            resultado['total_descontos'] + resultado['valor_liquido'], 2
        )

    # 4. INSS — linha com código INSS (geralmente 998 INSS M2 <ref> <valor>)
    #    pega o ÚLTIMO número monetário da linha que contém "INSS"
    for linha in texto.split('\n'):
        if re.search(r'\bINSS\b', linha, re.IGNORECASE):
            # só considera linhas de item (começam com dígito = código)
            if re.match(r'^\d', linha.strip()):
                numeros = re.findall(r'[\d.]+,\d{2}', linha)
                if numeros:
                    v = parse_br_float(numeros[-1])
                    if v is not None and v > 0:
                        resultado['inss'] = v
                    break

    return resultado


def _cpf_digitos_validos(cpf_num: str) -> bool:
    """Valida CPF (11 dígitos) pelo algoritmo dos dígitos verificadores."""
    if len(cpf_num) != 11 or cpf_num == cpf_num[0] * 11:
        return False
    for i in (9, 10):
        soma = sum(int(cpf_num[n]) * (i + 1 - n) for n in range(i))
        digito = (soma * 10 % 11) % 10
        if digito != int(cpf_num[i]):
            return False
    return True


# Padrões que indicam que o posto de trabalho é a própria empresa/sede,
# não um cliente/posto externo.
PADROES_LOCAL_INTERNO = [
    r'pr[óo]pria\s+empresa',
    r'sede\s+da\s+(?:empresa|contratante|magnata)',
    r'(?:o\s+)?mesmo\s+da\s+empresa',
    r'mesmo\s+endere[çc]o\s+da\s+(?:empresa|contratante)',
    r'nas\s+depend[êe]ncias\s+da\s+(?:empresa|contratante)',
    r'na\s+sede\s+d[aeo]\s+(?:empresa|contratante|magnata)',
    r'instala[çc][õo]es\s+da\s+(?:empresa|contratante)',
]

# Trechos genéricos/sem sentido isolado — se forem o único conteúdo
# extraído para o local, tratamos como "desconhecido" em vez de um posto real.
FILLERS_LOCAL_DESCONHECIDO = {
    'situa-se', 'o mesmo', 'a mesma', 'conforme', 'acima', 'abaixo',
    'mencionado', 'descrito', 'indicado', 'especificado',
}


def _resolver_local_posto(texto: str):
    """
    Determina local_posto / tipo_local / avisos para o posto de trabalho.

    "Magnata / Sede" é um local VÁLIDO (comum para folguistas e colaboradores
    sem posto fixo) — não é tratado como erro nem reduz confiança.

    Retorna (local_posto, tipo_local, avisos_qualidade):
      - ("Magnata / Sede", "interno_empresa", [])      -> posto é a própria empresa/sede (válido)
      - ("Edifício Sky", "externo", [])                -> posto externo identificado
      - (None, "desconhecido", [aviso])                -> truncado, ambíguo, conflito ou indeterminado
      - (None, "desconhecido", [])                     -> nada encontrado no texto
    """
    avisos = []

    interno = any(re.search(p, texto, re.IGNORECASE) for p in PADROES_LOCAL_INTERNO)

    # Tenta extrair um candidato a posto externo
    m = re.search(
        r'(?:local de trabalho|prestar[áa]?\s+(?:os\s+)?servi[çc]os?\s+(?:em|no|na))\s*:?\s*'
        r'([A-Za-zÀ-ú0-9\s,./-]{2,80}?)\s*[,\.\n]',
        texto, re.IGNORECASE
    )
    candidato = None
    if m:
        bruto = re.sub(r'\s+', ' ', m.group(1)).strip(' .,-')
        # Remove prefixos de localização que não fazem parte do nome do posto
        bruto = re.sub(
            r'^(?:que\s+)?(?:situa-se|localiza-se|estabelecido\s+em|situado\s+em)\s*',
            '', bruto, flags=re.IGNORECASE
        ).strip(' .,-')
        candidato_valido = (
            len(bruto) >= 4
            and bruto.lower() not in FILLERS_LOCAL_DESCONHECIDO
            and re.search(r'[A-Za-zÀ-ú]{3,}', bruto)
            and not any(re.search(p, bruto, re.IGNORECASE) for p in PADROES_LOCAL_INTERNO)
        )
        if candidato_valido:
            candidato = bruto
        elif not interno:
            # Trecho encontrado, mas truncado/genérico demais para ser um posto real
            avisos.append(
                f'Local de trabalho extraído de forma truncada/confusa: "{bruto}" — revisar manualmente.'
            )

    if interno and candidato:
        # Contrato menciona "própria empresa/sede" E um posto externo nomeado —
        # o sistema não consegue determinar qual prevalece.
        avisos.append(
            f'Conflito entre indicação de posto externo ("{candidato}") e indicação de '
            'sede/própria empresa no contrato — revisar manualmente.'
        )
        return None, 'desconhecido', avisos

    if interno:
        return 'Magnata / Sede', 'interno_empresa', avisos

    if candidato:
        return candidato, 'externo', avisos

    return None, 'desconhecido', avisos


def extrair_dados_contrato(texto: str):
    """
    Extrai dados de um Contrato de Experiência / Contrato de Trabalho (Fase 5B).

    Heurísticas por regex, tolerantes — qualquer campo não encontrado retorna None.
    Não levanta exceção: na ausência de casamento, simplesmente omite o valor.

    Retorna (dados, avisos_qualidade):
      dados: dict com chaves (todas opcionais)
        nome_funcionario, cpf, data_admissao, cargo_funcao, local_posto,
        tipo_local, salario, jornada_escala, cnpj_empresa
      avisos_qualidade: lista de strings com alertas sobre extrações
        confusas/truncadas (não bloqueiam o resultado, apenas sinalizam).
    """
    resultado = {
        'nome_funcionario': None,
        'cpf': None,
        'data_admissao': None,
        'cargo_funcao': None,
        'local_posto': None,
        'tipo_local': 'desconhecido',
        'salario': None,
        'jornada_escala': None,
        'cnpj_empresa': None,
    }
    avisos_qualidade = []
    if not texto:
        return resultado, avisos_qualidade

    # CPF — reaproveita o extrator já validado para holerites
    resultado['cpf'] = extrair_cpf(texto)

    # CNPJ da empresa contratante
    m = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto)
    if m:
        resultado['cnpj_empresa'] = m.group()

    # Nome do funcionário/empregado — padrões comuns em contratos.
    # Captura só letras/espaços (sem quebra de linha) e para antes de termos
    # como "portador", "carteira de trabalho", "CTPS", "CPF", "RG", etc.
    _stop_nome = (
        r'(?:\n|,|\.|portador|portadora|carteira\s+de\s+trabalho|CTPS|'
        r'CPF|RG|residente|doravante)'
    )
    padroes_nome = [
        rf'(?:EMPREGAD[OA]|CONTRATAD[OA])\s*:?\s*\n?\s*([A-ZÀ-Ú][A-ZÀ-Ú ]{{3,59}}?)(?=\s*{_stop_nome}|$)',
        rf'Sr\.?\(?a?\)?\.?\s+([A-ZÀ-Ú][A-ZÀ-Ú ]{{3,59}}?),\s+(?:portador|inscrit[oa]|CPF)',
        rf'(?:nome|funcion[áa]rio)\s*:?\s*([A-ZÀ-Ú][A-ZÀ-Ú ]{{3,59}}?)(?=\s*{_stop_nome}|$)',
    ]
    for p in padroes_nome:
        m = re.search(p, texto, re.IGNORECASE)
        if m:
            nome = m.group(1).strip()
            if len(nome.split()) >= 2:
                resultado['nome_funcionario'] = nome
                break

    # Data de admissão
    padroes_data = [
        r'(?:admiss[ãa]o|admitid[oa]|a partir de)\D{0,20}(\d{2}/\d{2}/\d{4})',
        r'Admiss[ãa]o:\s*(\d{2}/\d{2}/\d{4})',
    ]
    for p in padroes_data:
        m = re.search(p, texto, re.IGNORECASE)
        if m:
            resultado['data_admissao'] = m.group(1)
            break

    # Cargo/função — para na pontuação OU em conectores/sufixos que indicam
    # que o texto deixou de falar do cargo (ex.: "..., doravante denominado...")
    m = re.search(
        r'fun[çc][ãa]o\s+(?:de|do cargo de)?\s*:?\s*([A-Za-zÀ-ú0-9\s/\-]{3,60}?)'
        r'(?:\s*[,\.\n]'
        r'|\s+(?:doravante|conforme|de acordo com|nos termos|na forma|'
        r'e mais|contratad[oa]|jornada|sal[áa]rio|remunera[çc][ãa]o))',
        texto, re.IGNORECASE
    )
    if m:
        cargo = re.sub(r'\s+', ' ', m.group(1)).strip(' .,-')
        cargo = re.sub(
            r'\s+(?:e|conforme|de acordo com|nos termos|na forma)\s*$',
            '', cargo, flags=re.IGNORECASE
        )
        resultado['cargo_funcao'] = cargo or None

    # Local/posto de trabalho — normaliza "própria empresa/sede" vs. posto externo
    local_posto, tipo_local, avisos_local = _resolver_local_posto(texto)
    resultado['local_posto'] = local_posto
    resultado['tipo_local'] = tipo_local
    avisos_qualidade.extend(avisos_local)

    # Salário — só aceita valor claramente associado a salário/remuneração/
    # ordenado/vencimento/R$. Aceita "1.234,56" (com centavos) ou valores
    # inteiros com 3+ dígitos (rejeita números isolados/incompatíveis como "8.2").
    m = re.search(
        r'(?:sal[áa]rio|remunera[çc][ãa]o|ordenado|vencimento)[^\d]{0,30}R?\$?\s*'
        r'([\d]{1,3}(?:\.\d{3})*,\d{2}|\d{3,}(?:\.\d{3})*)',
        texto, re.IGNORECASE
    )
    if m:
        valor_str = m.group(1)
        if ',' in valor_str:
            valor = parse_br_float(valor_str)
        else:
            try:
                valor = float(valor_str.replace('.', ''))
            except ValueError:
                valor = None
        resultado['salario'] = valor if valor and valor >= 100 else None

    # Jornada/escala
    m = re.search(
        r'(?:jornada|escala)\D{0,30}((?:\d{1,2}\s*(?:horas|h)\b[^\n,.]{0,30})|(?:\d{1,2}\s*x\s*\d{1,2}))',
        texto, re.IGNORECASE
    )
    if m:
        resultado['jornada_escala'] = m.group(1).strip()

    return resultado, avisos_qualidade


def construir_mapa_cpf(caminho_pdf: str) -> tuple[dict, int]:
    """
    Pass 1 — LEVE.
    Extrai CPF, nome, índice de página E valores financeiros por colaborador.
    Retorna: ({cpf: {'nome': str, 'paginas': [int], 'valores': dict}}, total_paginas)
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
                vals  = extrair_valores_holerite(texto)

                if not cpf:
                    cpf = f'sem_cpf_{i}'

                if cpf not in mapa:
                    mapa[cpf] = {'nome': nome, 'paginas': [], 'valores': {}}
                mapa[cpf]['paginas'].append(i)

                # Atualiza valores: só substitui se o novo for não-nulo (aceita zero)
                for k, v in vals.items():
                    if v is not None and k not in mapa[cpf]['valores']:
                        mapa[cpf]['valores'][k] = v

                del texto
                logger.info(
                    f'[P1] Pág {i+1:03d}/{total}: CPF={cpf} | Nome={nome} | Vals={vals}'
                )

            except Exception as exc:
                logger.warning(f'[P1] Pág {i+1}/{total}: erro → {exc}')
                mapa[f'sem_cpf_{i}'] = {
                    'nome': 'Erro extração', 'paginas': [i], 'valores': {}
                }

            if (i + 1) % 15 == 0:
                gc.collect()
                logger.info(f'[P1] GC executado | RAM: {_mem_mb()} MB')

    gc.collect()
    logger.info(f'[P1] Concluído: {len(mapa)} colaboradores | RAM: {_mem_mb()} MB')
    return mapa, total


def extrair_pdf_colaborador(caminho_pdf: str, indices: list) -> bytes:
    reader = PdfReader(caminho_pdf)
    writer = PdfWriter()
    for idx in indices:
        writer.add_page(reader.pages[idx])
    buf = io.BytesIO()
    writer.write(buf)
    resultado = buf.getvalue()
    del reader, writer, buf
    return resultado


def extrair_pdf_do_request() -> str:
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
    headers = {'Authorization': f'Bearer {AIRTABLE_API_KEY}'}
    cpf_num = re.sub(r'\D', '', cpf)
    formulas = [
        f'{{CPF}}="{cpf}"',
        f'{{CPF}}="{cpf_num}"',
        f'{{CPF}}={cpf_num}',
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
            logger.warning(f'[AT] Timeout CPF {cpf} (fórmula: {formula})')
            continue
        except Exception as exc:
            logger.warning(f'[AT] Erro CPF {cpf}: {exc}')
            continue
    return None, None


def criar_registro_holerite(nome, func_id, folha_mensal, data_str, mes_cont_id, valores=None, status='Concluído'):
    """Cria registro de holerite no Airtable, incluindo valores financeiros se disponíveis.

    'status' permite criar o registro como 'Concluído' (fluxo normal) ou
    'Revisão Manual' (sanitização — usado quando algum dado não pôde ser
    gravado/extraído com confiança). 'typecast=True' permite ao Airtable
    criar a opção "Revisão Manual" automaticamente no campo Status, se ainda
    não existir como opção do singleSelect.
    """
    campos = {
        F_HOL_NOME:     f'{nome} - {folha_mensal}',
        F_HOL_STATUS:   status,
        F_HOL_FUNC:     [func_id],
        F_HOL_DATA:     data_str,
        F_HOL_FOLHA:    folha_mensal,
    }
    # mes_cont_id pode vir None (mês de contabilidade não encontrado) — um
    # link [None] é rejeitado pelo Airtable (422), então omitimos o campo
    # nesse caso em vez de quebrar a criação do holerite.
    if mes_cont_id:
        campos[F_HOL_MES_CONT] = [mes_cont_id]
    if valores:
        if valores.get('total_vencimentos') is not None:
            campos[F_HOL_VENCIM]    = valores['total_vencimentos']
        if valores.get('total_descontos') is not None:
            campos[F_HOL_DESCONTOS] = valores['total_descontos']
        if valores.get('valor_liquido') is not None:
            campos[F_HOL_LIQUIDO]   = valores['valor_liquido']
        if valores.get('inss') is not None:
            campos[F_HOL_INSS]      = valores['inss']

    _at_throttle()
    r = requests.post(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_HOL}',
        headers=_at_headers(),
        json={'fields': campos, 'typecast': True},
        timeout=15,
    )
    _raise_for_airtable(r, f'criar holerite ({nome})')
    return r.json()['id']


def atualizar_valores_holerite(record_id: str, valores: dict):
    """Atualiza apenas os campos financeiros de um holerite existente."""
    campos = {}
    if valores.get('total_vencimentos') is not None:
        campos[F_HOL_VENCIM]    = valores['total_vencimentos']
    if valores.get('total_descontos') is not None:
        campos[F_HOL_DESCONTOS] = valores['total_descontos']
    if valores.get('valor_liquido') is not None:
        campos[F_HOL_LIQUIDO]   = valores['valor_liquido']
    if valores.get('inss') is not None:
        campos[F_HOL_INSS]      = valores['inss']

    if not campos:
        return None

    _at_throttle()
    r = requests.patch(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_HOL}/{record_id}',
        headers=_at_headers(),
        json={'fields': campos, 'typecast': True},
        timeout=15,
    )
    _raise_for_airtable(r, f'atualizar valores holerite {record_id}')
    return r.json()


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
    _raise_for_airtable(r, f'anexar PDF holerite {record_id}')
    return r.json()


# ── Helpers genéricos Airtable (Fase 2) ──────────────────────────────────────

def _criar_registro(table_id: str, fields: dict) -> str:
    _at_throttle()
    r = requests.post(
        f'https://api.airtable.com/v0/{BASE_ID}/{table_id}',
        headers=_at_headers(),
        json={'fields': fields, 'typecast': True},
        timeout=30,
    )
    _raise_for_airtable(r, f'create {table_id}')
    return r.json()['id']


def _buscar_por_campo(table_id: str, campo_nome: str, valor: str):
    """Busca o 1º registro onde {campo_nome} = valor. Retorna o registro ou None."""
    _at_throttle()
    valor_escapado = valor.replace('"', '\\"')
    formula = f'{{{campo_nome}}}="{valor_escapado}"'
    r = requests.get(
        f'https://api.airtable.com/v0/{BASE_ID}/{table_id}',
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
        params={'filterByFormula': formula, 'maxRecords': 1},
        timeout=30,
    )
    r.raise_for_status()
    records = r.json().get('records', [])
    return records[0] if records else None


def _anexar_attachment(table_id: str, record_id: str, field_id: str,
                        conteudo_bytes: bytes, filename: str,
                        content_type: str = 'application/pdf'):
    _at_throttle()
    url = f'https://content.airtable.com/v0/{BASE_ID}/{record_id}/{field_id}/uploadAttachment'
    r = requests.post(
        url,
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}', 'Content-Type': 'application/json'},
        json={
            'contentType': content_type,
            'filename': filename,
            'file': base64.b64encode(conteudo_bytes).decode('utf-8'),
        },
        timeout=60,
    )
    _raise_for_airtable(r, f'attach {table_id}/{record_id}')
    return r.json()


# ── Helpers Fase 4 — /processar-fila ─────────────────────────────────────────

def _atualizar_status_processar(record_id: str, status: str):
    _at_throttle()
    r = requests.patch(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_PROCESSAR}/{record_id}',
        headers=_at_headers(),
        json={'fields': {F_PROC_STATUS: status}, 'typecast': True},
        timeout=15,
    )
    _raise_for_airtable(r, f'update status {record_id}')
    return r.json()


def _criar_pendencia(arquivo_id: str, tipo_problema: str, observacao: str):
    return _criar_registro(TABLE_PENDENCIAS, {
        F_PEND_NOME:   f'{tipo_problema}: {arquivo_id}',
        F_PEND_STATUS: 'Pendente',
        F_PEND_TIPO:   tipo_problema,
        F_PEND_ORIGEM: [arquivo_id],
        F_PEND_OBS:    observacao[:500] if observacao else '',
        F_PEND_DATA:   datetime.now().isoformat(),
    })


def _buscar_funcionario_por_nome(nome: str):
    """Fallback de busca por Nome Completo (case-insensitive) quando não há CPF."""
    _at_throttle()
    nome_escapado = nome.replace('"', '\\"')
    r = requests.get(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}',
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
        params={
            'filterByFormula': f'LOWER({{Nome Completo}})=LOWER("{nome_escapado}")',
            'maxRecords': 1,
            'fields[]': ['Nome Completo'],
        },
        timeout=30,
    )
    if r.ok:
        records = r.json().get('records', [])
        if records:
            return records[0]['id'], records[0].get('fields', {}).get('Nome Completo', '')
    return None, None


def _buscar_contabilidade_mensal_por_nome(nome: str):
    _at_throttle()
    nome_escapado = nome.replace('"', '\\"')
    r = requests.get(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_CONT}',
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
        params={
            'filterByFormula': f'{{Mês - Contabilidade}}="{nome_escapado}"',
            'maxRecords': 1,
            'fields[]': ['Mês - Contabilidade'],
        },
        timeout=30,
    )
    if r.ok:
        records = r.json().get('records', [])
        if records:
            return records[0]['id']
    return None


def _buscar_holerite_existente(func_id: str, folha_mensal: str):
    """Procura holerite já criado para este funcionário nesta folha mensal."""
    _at_throttle()
    folha_escapada = folha_mensal.replace('"', '\\"')
    r = requests.get(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_HOL}',
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
        params={
            'filterByFormula': f'{{Folha Mensal}}="{folha_escapada}"',
            'returnFieldsByFieldId': 'true',
        },
        timeout=30,
    )
    r.raise_for_status()
    for rec in r.json().get('records', []):
        links = rec.get('fields', {}).get(F_HOL_FUNC) or []
        link_ids = [l['id'] if isinstance(l, dict) else l for l in links]
        if func_id in link_ids:
            return rec
    return None


def _verificar_anexo_em_lista(attachments: list, nome_arquivo: str, pdf_hash: str) -> str:
    """
    Verifica se já existe, numa lista de anexos (multipleAttachments), um
    arquivo com o mesmo nome.

    Retorna:
      'identico'   — já existe anexo com mesmo nome e mesmo hash (não duplicar)
      'conflito'   — já existe anexo com mesmo nome mas conteúdo diferente
                      (substituição precisa de autorização — não anexa)
      'novo'       — não há anexo com esse nome (pode anexar normalmente)
    """
    for att in attachments:
        if att.get('filename') != nome_arquivo:
            continue
        try:
            existente_bytes = requests.get(att['url'], timeout=60).content
            existente_hash = hashlib.sha256(existente_bytes).hexdigest()
        except Exception as exc:
            logger.warning(f'[FILA] Falha ao baixar anexo existente para comparar hash: {exc}')
            return 'conflito'
        return 'identico' if existente_hash == pdf_hash else 'conflito'
    return 'novo'


def _verificar_anexo_holerite(holerite_fields: dict, nome_arquivo: str, pdf_hash: str) -> str:
    """Verifica duplicidade de anexo no campo PDF Holerite (ver _verificar_anexo_em_lista)."""
    attachments = holerite_fields.get(F_HOL_PDF) or []
    return _verificar_anexo_em_lista(attachments, nome_arquivo, pdf_hash)


def _processar_holerite(ctx: dict, dry_run: bool) -> dict:
    """
    Handler de Holerite para /processar-fila.

    ctx: {proc_id, arquivo_id, pdf_bytes, pdf_hash, nome_arquivo, texto,
          folha_mensal, mes_cont_id, data_holerite}

    Retorno padronizado:
      {"acao": str, "status_final": "Concluído"|"Erro",
       "detalhes": dict, "pendencia": {"tipo":..., "observacao":...} | None}
    """
    texto = ctx['texto']
    folha_mensal = ctx['folha_mensal']
    mes_cont_id = ctx['mes_cont_id']

    # 1. Localizar funcionário por CPF, com fallback por nome extraído do PDF
    cpf = extrair_cpf(texto)
    func_id, nome = (None, None)
    if cpf:
        func_id, nome = buscar_funcionario_por_cpf(cpf)

    nome_pdf = extrair_nome_funcionario(texto)
    if not func_id and nome_pdf:
        func_id, nome = _buscar_funcionario_por_nome(nome_pdf)

    if not func_id:
        return {
            'acao': 'funcionario_nao_encontrado',
            'status_final': 'Erro',
            'detalhes': {
                'cpf_extraido': cpf,
                'nome_extraido': nome_pdf,
                'folha_mensal': folha_mensal,
            },
            'pendencia': {
                'tipo': 'Funcionário não encontrado',
                'observacao': (
                    f'CPF extraído: {cpf or "(nenhum)"} | '
                    f'Nome extraído: {nome_pdf or "(nenhum)"} | '
                    f'Folha: {folha_mensal}'
                ),
            },
        }

    # 2. Extrair valores financeiros do holerite
    valores = extrair_valores_holerite(texto)

    # 2b. Trava de segurança — valores financeiros inconsistentes
    v = valores.get('total_vencimentos')
    d = valores.get('total_descontos')
    liq = valores.get('valor_liquido')
    TOLERANCIA_CENTAVOS = 0.02
    valores_inconsistentes = False
    motivo_inconsistencia = None

    if v is not None and d is not None and liq is not None:
        if liq > 0 and v == d:
            valores_inconsistentes = True
            motivo_inconsistencia = (
                f'Total Vencimentos ({v}) igual a Total Descontos ({d}) com Valor Líquido ({liq}) > 0.'
            )
        elif v < liq:
            valores_inconsistentes = True
            motivo_inconsistencia = (
                f'Total Vencimentos ({v}) menor que Valor Líquido ({liq}).'
            )
        elif abs((v - d) - liq) > TOLERANCIA_CENTAVOS:
            valores_inconsistentes = True
            motivo_inconsistencia = (
                f'Total Vencimentos ({v}) - Total Descontos ({d}) = {v - d}, '
                f'diferente de Valor Líquido ({liq}) além da tolerância de R$ {TOLERANCIA_CENTAVOS}.'
            )

    if valores_inconsistentes:
        return {
            'acao': 'valores_inconsistentes',
            'status_final': 'Erro',
            'detalhes': {
                'funcionario_id': func_id,
                'funcionario_nome': nome,
                'cpf_extraido': cpf,
                'folha_mensal': folha_mensal,
                'valores': valores,
            },
            'pendencia': {
                'tipo': 'Valores inconsistentes',
                'observacao': (
                    f'{motivo_inconsistencia} '
                    f'Holerite NÃO atualizado, requer revisão manual.'
                ),
            },
        }

    # 3. Evitar duplicidade — checar se já existe holerite deste funcionário nesta folha
    existente = _buscar_holerite_existente(func_id, folha_mensal)

    if dry_run:
        pdf_ja_existia = False
        pdf_duplicado_evitado = False
        status_anexo = None

        if existente:
            status_anexo = _verificar_anexo_holerite(
                existente.get('fields', {}), ctx['nome_arquivo'], ctx['pdf_hash'],
            )
            if status_anexo == 'identico':
                pdf_ja_existia = True
                pdf_duplicado_evitado = True
                acao = 'atualizaria_holerite_existente_sem_duplicar_pdf'
            elif status_anexo == 'conflito':
                acao = 'atualizaria_holerite_existente_anexo_precisaria_autorizacao'
            else:  # 'novo'
                acao = 'atualizaria_holerite_existente_e_anexaria_pdf'
        else:
            acao = 'criaria_holerite'

        return {
            'acao': acao,
            'status_final': 'Concluído',
            'detalhes': {
                'funcionario_id': func_id,
                'funcionario_nome': nome,
                'cpf_extraido': cpf,
                'folha_mensal': folha_mensal,
                'valores': valores,
                'holerite_existente_id': existente['id'] if existente else None,
                'pdf_anexado': False,
                'pdf_ja_existia': pdf_ja_existia,
                'pdf_duplicado_evitado': pdf_duplicado_evitado,
                'status_anexo': status_anexo,
            },
            'pendencia': None,
        }

    pendencia = None
    status_final = 'Concluído'
    avisos_sanitizacao = []

    if existente:
        holerite_id = existente['id']

        try:
            atualizar_valores_holerite(holerite_id, valores)
        except AirtableError as exc:
            logger.error(f'[FILA] {ctx["proc_id"]}: erro ao atualizar valores do holerite {holerite_id}: {exc}')
            avisos_sanitizacao.append(f'Valores financeiros NÃO atualizados: {exc}')
            status_final = 'Erro'

        status_anexo = _verificar_anexo_holerite(
            existente.get('fields', {}), ctx['nome_arquivo'], ctx['pdf_hash'],
        )
        if status_anexo == 'novo':
            try:
                anexar_pdf_holerite(holerite_id, ctx['pdf_bytes'], ctx['nome_arquivo'])
                acao = 'holerite_atualizado' if not avisos_sanitizacao else 'holerite_atualizado_parcial'
            except AirtableError as exc:
                logger.error(f'[FILA] {ctx["proc_id"]}: erro ao anexar PDF no holerite {holerite_id}: {exc}')
                avisos_sanitizacao.append(f'PDF NÃO anexado: {exc}')
                acao = 'holerite_atualizado_parcial'
                status_final = 'Erro'
        elif status_anexo == 'identico':
            acao = 'holerite_atualizado_anexo_ja_existia' if not avisos_sanitizacao else 'holerite_atualizado_parcial'
        else:  # 'conflito'
            acao = 'holerite_atualizado_anexo_nao_substituido'
            avisos_sanitizacao.append(
                f'Holerite {holerite_id}: já existe anexo "{ctx["nome_arquivo"]}" com '
                f'conteúdo diferente do PDF processado. Anexo NÃO foi substituído — '
                f'requer autorização manual.'
            )

        if avisos_sanitizacao:
            pendencia = {
                'tipo': 'Holerite atualizado com pendências (revisão manual)',
                'observacao': f'Holerite {holerite_id}: ' + ' | '.join(avisos_sanitizacao),
            }
    else:
        try:
            holerite_id = criar_registro_holerite(
                nome, func_id, folha_mensal, ctx['data_holerite'], mes_cont_id, valores=valores,
            )
            anexar_pdf_holerite(holerite_id, ctx['pdf_bytes'], ctx['nome_arquivo'])
            acao = 'holerite_criado'
        except AirtableError as exc:
            # Sanitização: o payload completo (com valores financeiros) foi
            # rejeitado pelo Airtable. Em vez de perder o documento, tenta
            # novamente com um payload mínimo seguro (sem valores) e status
            # "Revisão Manual", preservando o PDF e registrando o erro exato
            # numa Pendência para correção manual posterior.
            logger.error(f'[FILA] {ctx["proc_id"]}: Airtable rejeitou criação do holerite (payload completo): {exc}')
            try:
                holerite_id = criar_registro_holerite(
                    nome, func_id, folha_mensal, ctx['data_holerite'], mes_cont_id,
                    valores=None, status='Revisão Manual',
                )
                anexar_pdf_holerite(holerite_id, ctx['pdf_bytes'], ctx['nome_arquivo'])
            except AirtableError as exc2:
                logger.error(f'[FILA] {ctx["proc_id"]}: Airtable rejeitou também o payload mínimo: {exc2}')
                return {
                    'acao': 'holerite_falhou',
                    'status_final': 'Erro',
                    'detalhes': {
                        'funcionario_id': func_id,
                        'funcionario_nome': nome,
                        'cpf_extraido': cpf,
                        'folha_mensal': folha_mensal,
                        'valores': valores,
                    },
                    'pendencia': {
                        'tipo': 'Erro Airtable ao criar Holerite',
                        'observacao': (
                            f'Falha ao criar holerite para {nome} ({folha_mensal}) mesmo com '
                            f'payload mínimo. Erro completo: {exc} | Erro do payload mínimo: {exc2}'
                        ),
                    },
                }
            acao = 'holerite_criado_revisao_manual'
            status_final = 'Concluído'
            pendencia = {
                'tipo': 'Holerite criado em Revisão Manual',
                'observacao': (
                    f'Holerite {holerite_id} ({nome} - {folha_mensal}) criado com status '
                    f'"Revisão Manual" — valores financeiros não foram gravados devido a '
                    f'erro do Airtable: {exc}. PDF anexado normalmente; preencher os '
                    f'valores manualmente.'
                ),
            }

    return {
        'acao': acao,
        'status_final': status_final,
        'detalhes': {
            'holerite_id': holerite_id,
            'funcionario_id': func_id,
            'funcionario_nome': nome,
            'cpf_extraido': cpf,
            'folha_mensal': folha_mensal,
            'valores': valores,
        },
        'pendencia': pendencia,
    }


CAMPOS_CONTRATO_OBRIGATORIOS = ['nome_funcionario', 'cpf', 'data_admissao']

# 'tipo_local' é metadado de classificação (sempre preenchido, mesmo que
# "desconhecido") e não entra no cálculo de confiança da extração.
CAMPOS_PARA_CONFIANCA = [
    'nome_funcionario', 'cpf', 'data_admissao', 'cargo_funcao',
    'local_posto', 'salario', 'jornada_escala', 'cnpj_empresa',
]

# ── Padrão genérico de decisão (reaproveitável para outros documentos) ──────
#
# Toda decisão automática de um handler de documento se encaixa em uma destas
# 5 categorias (ver função decidir_acao_documento):
#   - executar_automaticamente          -> ação principal sem revisão humana
#   - executar_com_status_intermediario -> registro/ação em estado de transição
#   - funcionario_ou_registro_ja_existente
#                                        -> já existe registro equivalente, nada a fazer
#   - enviar_para_revisao               -> Pendência, humano decide
#   - ignorar_documento                 -> documento não aplicável a este fluxo
#
# Automação é a regra; revisão manual é a exceção (erros, divergências,
# duplicidades, baixa confiança ou dados essenciais faltantes).
#
# Para contratos (Fase 5C) esse padrão se traduz em 'decisao_5c':
#   executar_automaticamente              -> cadastrar_ativo_automaticamente
#   executar_com_status_intermediario     -> criar_pre_cadastro_seguro
#   funcionario_ou_registro_ja_existente  -> funcionario_ja_existente
#   enviar_para_revisao                   -> enviar_para_revisao
#   ignorar_documento                     -> não usado nesta fase (reservado)
#
# ── Tipos de documento futuros (apenas previstos, SEM processamento real) ───
#
# Os tipos abaixo já existem como possíveis 'Tipo de Documento' em Processar
# Arquivos, mas continuam mapeados para None em PROCESSADORES_DOCUMENTO (ver
# registro de handlers mais abaixo) — /processar-fila retorna 400 "ainda não
# implementado" para eles, sem qualquer leitura/escrita adicional. Quando
# forem implementados, cada um receberá um handler próprio que também deverá
# produzir uma das 5 categorias genéricas acima, por exemplo:
#   - Folha de Ponto        -> tipicamente executar_automaticamente (registrar
#                              ponto) ou enviar_para_revisao (inconsistências
#                              de horário/falta).
#   - Certidões             -> executar_automaticamente (arquivar/atualizar
#                              validade) ou enviar_para_revisao (certidão
#                              vencida/divergente).
#   - Extrato da Folha      -> executar_com_status_intermediario (conciliação
#                              pendente de confirmação) ou enviar_para_revisao.
#   - FGTS Digital          -> executar_automaticamente (registrar guia/valor)
#                              ou enviar_para_revisao (divergência de valores).
#   - Guias/Boletos         -> executar_automaticamente (registrar pagamento)
#                              ou enviar_para_revisao (vencimento/valor
#                              inconsistente).
#   - Notas Fiscais         -> executar_automaticamente (registrar nota) ou
#                              enviar_para_revisao (dados fiscais incompletos).
#   - Outros docs por e-mail -> ignorar_documento (não aplicável) ou
#                              enviar_para_revisao (encaminhar para triagem).
# Nenhum desses handlers é implementado nesta etapa; nenhuma extração real,
# leitura adicional ou escrita é feita para esses tipos.

# Fase 5C — pré-cadastro/cadastro automático seguro em Funcionários
CONFIANCA_MINIMA_PRE_CADASTRO = 0.70   # abaixo disso -> enviar_para_revisao
CONFIANCA_ATIVO_AUTOMATICO = 0.85      # acima/igual -> cadastrar_ativo_automaticamente

# Campos do pré-cadastro: nome legível -> field ID em Funcionários.
# Somente campos de escrita simples e já existentes no schema (nenhum campo novo).
CAMPOS_FUNC_PRE_CADASTRO = {
    'Nome Completo':    F_FUNC_NOME,
    'CPF':              F_FUNC_CPF,
    'Status':           F_FUNC_STATUS,
    'Cargo':            F_FUNC_CARGO,
    'Data de Admissão': F_FUNC_ADMISSAO,
}

# Termos cujo aparecimento no nome extraído indicam resíduo de texto do
# contrato (regex capturou além do nome) — usados por _nome_suspeito().
_TERMOS_NOME_SUSPEITO = (
    'PORTADOR', 'PORTADORA', 'CARTEIRA', 'CTPS', 'RESIDENTE',
    'DORAVANTE', 'CONTRATO', 'CONTRATAD', 'EMPREGAD', 'EMPRESA',
)


def _nome_suspeito(nome):
    """
    Heurística para 'nome suspeito': vazio, muito curto, contendo dígitos
    ou termos residuais de contrato (sinal de captura incorreta pela regex).
    """
    if not nome:
        return True
    nome = nome.strip()
    if len(nome) < 5:
        return True
    if re.search(r'\d', nome):
        return True
    nome_upper = nome.upper()
    return any(termo in nome_upper for termo in _TERMOS_NOME_SUSPEITO)


def _data_br_para_iso(data_br):
    """Converte 'DD/MM/AAAA' para 'AAAA-MM-DD' (formato aceito pelo campo date). None se inválido."""
    if not data_br:
        return None
    try:
        return datetime.strptime(data_br, '%d/%m/%Y').strftime('%Y-%m-%d')
    except ValueError:
        return None


def decidir_acao_documento(*, erros_bloqueantes, avisos_qualidade, confianca,
                            confianca_minima, confianca_ativo,
                            registro_existente, divergencia):
    """
    Decisão genérica reaproveitável (ver comentário acima de
    CONFIANCA_MINIMA_PRE_CADASTRO) — produz uma das 5 categorias:
      - 'enviar_para_revisao'
      - 'funcionario_ou_registro_ja_existente'
      - 'executar_automaticamente'
      - 'executar_com_status_intermediario'
      ('ignorar_documento' não é produzido aqui — reservado para handlers
      futuros que precisem descartar um documento sem ação nenhuma).

    erros_bloqueantes: lista de motivos que, se não vazia, força revisão
        (dados essenciais inválidos/ausentes, local não identificado etc.).
    avisos_qualidade: lista de avisos da extração — também força revisão.
    registro_existente: True se já existe um registro equivalente (ex.: CPF
        já cadastrado em Funcionários).
    divergencia: motivo de divergência com o registro existente, ou None.
    """
    if erros_bloqueantes:
        return 'enviar_para_revisao', '; '.join(erros_bloqueantes)
    if avisos_qualidade:
        return 'enviar_para_revisao', 'Avisos de qualidade na extração: ' + '; '.join(avisos_qualidade)
    if confianca < confianca_minima:
        return 'enviar_para_revisao', (
            f'Confiança da extração ({confianca}) abaixo do mínimo '
            f'({confianca_minima}) para automação.'
        )
    if registro_existente:
        if divergencia:
            return 'enviar_para_revisao', divergencia
        return 'funcionario_ou_registro_ja_existente', (
            'Registro equivalente já existe e dados compatíveis — nenhuma ação necessária.'
        )
    if confianca >= confianca_ativo:
        return 'executar_automaticamente', (
            f'Dados essenciais válidos, sem avisos de qualidade e '
            f'confiança {confianca} >= {confianca_ativo} — apto para execução automática.'
        )
    return 'executar_com_status_intermediario', (
        f'Dados essenciais válidos, mas confiança {confianca} entre '
        f'{confianca_minima} e {confianca_ativo} — execução em estado intermediário de segurança.'
    )


def _montar_campos_pre_cadastro(dados: dict, status: str) -> dict:
    """
    Monta os campos (nome legível -> valor) do cadastro em Funcionários.

    'status' é "Ativo" (cadastrar_ativo_automaticamente) ou "Pré-cadastro"
    (criar_pre_cadastro_seguro), conforme decidido em _processar_contrato_stub.

    Inclui apenas campos mapeados e de escrita simples (Nome Completo, CPF,
    Status, Cargo, Data de Admissão). "Locais de trabalho" é um vínculo para
    a tabela Locais e "Origem do cadastro/Contrato de origem" não tem campo
    equivalente em Funcionários — nenhum dos dois é incluído aqui
    (ver 'observacoes' no retorno do handler).
    """
    campos = {
        'Nome Completo': dados['nome_funcionario'],
        'CPF': dados['cpf'],
        'Status': status,
    }
    if dados.get('cargo_funcao'):
        campos['Cargo'] = dados['cargo_funcao']
    data_iso = _data_br_para_iso(dados.get('data_admissao'))
    if data_iso:
        campos['Data de Admissão'] = data_iso
    return campos


def _criar_pre_cadastro_funcionario(campos_legiveis: dict) -> str:
    """Cria registro em Funcionários a partir dos campos mapeados (Status="Ativo" ou "Pré-cadastro")."""
    campos_at = {
        CAMPOS_FUNC_PRE_CADASTRO[nome]: valor
        for nome, valor in campos_legiveis.items()
        if nome in CAMPOS_FUNC_PRE_CADASTRO
    }
    return _criar_registro(TABLE_FUNC, campos_at)


def _processar_contrato_stub(ctx, dry_run):
    """
    Handler de Contrato de Experiência / Contrato de Trabalho (Fase 5B + 5C).

    Fase 5B: extrai dados do contrato e consulta (somente leitura) se o CPF já
    existe em Funcionários.

    Fase 5C: decisao_5c (padrão genérico reaproveitável — ver comentário acima de
    CONFIANCA_MINIMA_PRE_CADASTRO) ∈ {cadastrar_ativo_automaticamente,
    criar_pre_cadastro_seguro, funcionario_ja_existente, enviar_para_revisao}.
    Em dry_run=true apenas simula (nada gravado). Em dry_run=false executa a ação
    decidida — cria em Funcionários com Status="Ativo" ou "Pré-cadastro", ou cria
    Pendência. Nunca altera Status/cargo/local/etc. de um funcionário já existente
    — nesse caso apenas compara e reporta.
    """
    dados, avisos_qualidade = extrair_dados_contrato(ctx['texto'])

    cpf_num = re.sub(r'\D', '', dados['cpf'] or '')

    validacao = {
        'cpf_valido': bool(cpf_num) and _cpf_digitos_validos(cpf_num),
        'nome_presente': bool(dados['nome_funcionario']),
        'data_admissao_valida': bool(dados['data_admissao']),
    }

    campos_faltantes = [
        campo for campo in CAMPOS_CONTRATO_OBRIGATORIOS if not dados.get(campo)
    ]

    total_campos = len(CAMPOS_PARA_CONFIANCA)
    preenchidos = sum(1 for campo in CAMPOS_PARA_CONFIANCA if dados.get(campo) is not None)
    confianca = round(preenchidos / total_campos, 2) if total_campos else 0.0

    # Cada aviso de qualidade (local truncado/ambíguo/conflitante) reduz a
    # confiança — mas "Magnata / Sede" (interno_empresa) não gera aviso e,
    # portanto, não penaliza.
    confianca = round(max(0.0, confianca - 0.1 * len(avisos_qualidade)), 2)

    funcionario_existe = None
    nome_existente = None
    if dados['cpf']:
        func_id, nome_existente = buscar_funcionario_por_cpf(dados['cpf'])
        funcionario_existe = func_id is not None

    # ── Fase 5C — decisão de pré-cadastro / revisão ──────────────────────────
    divergencia = None
    if funcionario_existe and dados['nome_funcionario'] and nome_existente:
        if dados['nome_funcionario'].strip().upper() != nome_existente.strip().upper():
            divergencia = (
                f'Nome do contrato ("{dados["nome_funcionario"]}") difere do '
                f'cadastro existente em Funcionários ("{nome_existente}") para o mesmo CPF.'
            )

    nome_suspeito = _nome_suspeito(dados['nome_funcionario'])

    erros_bloqueantes = []
    if campos_faltantes:
        erros_bloqueantes.append(f'Campos obrigatórios faltando: {", ".join(campos_faltantes)}.')
    if not validacao['cpf_valido']:
        erros_bloqueantes.append('CPF inválido (dígitos verificadores não conferem).')
    if nome_suspeito:
        erros_bloqueantes.append(f'Nome do funcionário ausente ou suspeito: "{dados["nome_funcionario"]}".')
    if dados['tipo_local'] == 'desconhecido':
        erros_bloqueantes.append('Local de trabalho não identificado (tipo_local="desconhecido").')

    categoria_generica, motivo_decisao = decidir_acao_documento(
        erros_bloqueantes=erros_bloqueantes,
        avisos_qualidade=avisos_qualidade,
        confianca=confianca,
        confianca_minima=CONFIANCA_MINIMA_PRE_CADASTRO,
        confianca_ativo=CONFIANCA_ATIVO_AUTOMATICO,
        registro_existente=funcionario_existe,
        divergencia=divergencia,
    )

    # Mapeamento da categoria genérica para o vocabulário específico de
    # contratos (Fase 5C) — ver comentário acima de CONFIANCA_MINIMA_PRE_CADASTRO.
    _MAPA_CATEGORIA_PARA_DECISAO_5C = {
        'executar_automaticamente': 'cadastrar_ativo_automaticamente',
        'executar_com_status_intermediario': 'criar_pre_cadastro_seguro',
        'funcionario_ou_registro_ja_existente': 'funcionario_ja_existente',
        'enviar_para_revisao': 'enviar_para_revisao',
    }
    decisao_5c = _MAPA_CATEGORIA_PARA_DECISAO_5C[categoria_generica]

    origem_contrato = (
        f'Contrato: {ctx["tipo_documento"]}, arquivo "{ctx["nome_arquivo"]}" '
        f'(Processar Arquivos: {ctx["proc_id"]}, Arquivo: {ctx["arquivo_id"]}).'
    )

    pre_cadastro_simulado = None
    pre_cadastro_id = None
    pendencia_simulada = None

    if decisao_5c in ('cadastrar_ativo_automaticamente', 'criar_pre_cadastro_seguro'):
        status_destino = 'Ativo' if decisao_5c == 'cadastrar_ativo_automaticamente' else 'Pré-cadastro'
        campos_pre_cadastro = _montar_campos_pre_cadastro(dados, status_destino)
        observacoes = []
        if dados['local_posto']:
            observacoes.append(
                f'Local/Posto sugerido: "{dados["local_posto"]}" '
                f'(tipo_local={dados["tipo_local"]}) — campo "Locais de trabalho" é um '
                'vínculo para a tabela Locais e não é preenchido automaticamente; '
                'requer associação manual.'
            )
        observacoes.append(
            origem_contrato + ' Não há campo "Origem do cadastro"/"Contrato de origem" '
            'mapeado em Funcionários — referência mantida apenas neste relatório.'
        )
        pre_cadastro_simulado = {
            'campos': campos_pre_cadastro,
            'observacoes': observacoes,
        }
        if not dry_run:
            # Regra de segurança: rechecar CPF em Funcionários imediatamente
            # antes de criar, para nunca gerar duplicidade (ex.: requisição
            # duplicada criou o registro entre a decisão e a gravação).
            func_id_recheck, _ = buscar_funcionario_por_cpf(dados['cpf'])
            if func_id_recheck:
                decisao_5c = 'funcionario_ja_existente'
                motivo_decisao = (
                    f'CPF já existe em Funcionários (ID={func_id_recheck}), '
                    'detectado na rechecagem imediatamente antes da criação — '
                    'criação abortada para evitar duplicidade.'
                )
                pre_cadastro_simulado = None
            else:
                pre_cadastro_id = _criar_pre_cadastro_funcionario(campos_pre_cadastro)

    elif decisao_5c == 'enviar_para_revisao':
        partes_obs = [motivo_decisao]
        if dados['local_posto']:
            partes_obs.append(
                f'Local/Posto identificado: "{dados["local_posto"]}" (tipo_local={dados["tipo_local"]}).'
            )
        partes_obs.append(origem_contrato)
        pendencia_simulada = {
            'tipo': 'Contrato — revisão Fase 5C',
            'observacao': ' '.join(partes_obs),
        }

    proxima_acao = motivo_decisao

    detalhes = {
        'tipo_documento': ctx['tipo_documento'],
        'record_id': ctx['proc_id'],
        'arquivo_id': ctx['arquivo_id'],
        'nome_arquivo': ctx['nome_arquivo'],
        'dados_extraidos': dados,
        'local_posto': dados['local_posto'],
        'tipo_local': dados['tipo_local'],
        'avisos_qualidade': avisos_qualidade,
        'validacao': validacao,
        'campos_faltantes': campos_faltantes,
        'confianca': confianca,
        'funcionario_existe_em_funcionarios': funcionario_existe,
        'decisao_5c': decisao_5c,
        'pre_cadastro_simulado': pre_cadastro_simulado,
        'pre_cadastro_id': pre_cadastro_id,
        'pendencia_simulada': pendencia_simulada,
        'proxima_acao_sugerida': proxima_acao,
        'observacao': (
            'Fase 5B/5C. Em dry_run=true nada é gravado — "pre_cadastro_simulado" e '
            '"pendencia_simulada" mostram o que seria feito. Em dry_run=false, '
            'conforme "decisao_5c": cadastrar_ativo_automaticamente cria em '
            'Funcionários com Status="Ativo"; criar_pre_cadastro_seguro cria com '
            'Status="Pré-cadastro"; enviar_para_revisao cria Pendência. '
            'Funcionário existente nunca é sobrescrito.'
        ),
        'log_operacional': {
            'disponivel': False,
            'motivo': (
                'Tabela "Processar Arquivos" não possui campo de texto/observação '
                'para registrar decisão, ID do funcionário criado/encontrado ou erro '
                '(campos atuais: Name, Status, Tipo, Arquivos, Data Processo, '
                'PROCESSO IDA, Arquivos 2, Tipo de Documento). Nenhum campo novo foi '
                'criado; esta informação é retornada apenas neste JSON.'
            ),
        },
    }

    pendencia_retorno = pendencia_simulada if decisao_5c == 'enviar_para_revisao' else None

    return {
        'acao': 'contrato_extraido_sem_gravar',
        'status_final': ctx['status_atual'],
        'detalhes': detalhes,
        'pendencia': pendencia_retorno,
    }


def _processar_folha_ponto(ctx: dict, dry_run: bool) -> dict:
    """
    Handler de Folha de Ponto para /processar-fila (Fase 1 — anexação ao
    prontuário do funcionário).

    Ainda NÃO extrai horários/batidas do PDF (formato não mapeado). O que
    este handler faz é: identificar o funcionário pelo CPF (ou, na falta
    dele, pelo nome) presente no PDF e anexar o arquivo ao campo
    "PDF Folha Ponto" (prontuário, em Funcionários), evitando duplicar o
    mesmo arquivo. Itens sem funcionário identificável vão para "Revisão
    Manual" com Pendência, em vez de ficarem invisíveis.
    """
    texto = ctx['texto']

    cpf = extrair_cpf(texto)
    func_id, nome = (None, None)
    if cpf:
        func_id, nome = buscar_funcionario_por_cpf(cpf)

    nome_pdf = extrair_nome_funcionario(texto)
    if not func_id and nome_pdf and nome_pdf != 'Desconhecido':
        func_id, nome = _buscar_funcionario_por_nome(nome_pdf)

    if not func_id:
        detalhes = {
            'cpf_extraido': cpf,
            'nome_extraido': nome_pdf,
            'nome_arquivo': ctx['nome_arquivo'],
        }
        observacao = (
            f'Folha de Ponto "{ctx["nome_arquivo"]}" não pôde ser vinculada a um '
            f'funcionário. CPF extraído: {cpf or "(nenhum)"} | '
            f'Nome extraído: {nome_pdf or "(nenhum)"} '
            f'(Processar Arquivos: {ctx["proc_id"]}, Arquivo: {ctx["arquivo_id"]}).'
        )
        if dry_run:
            return {
                'acao': 'funcionario_nao_encontrado',
                'status_final': 'Revisão Manual',
                'detalhes': detalhes,
                'pendencia': None,
            }
        return {
            'acao': 'funcionario_nao_encontrado',
            'status_final': 'Revisão Manual',
            'detalhes': detalhes,
            'pendencia': {
                'tipo': 'Funcionário não encontrado (Folha de Ponto)',
                'observacao': observacao,
            },
        }

    # Verificar se este arquivo já está anexado ao prontuário (evitar duplicar)
    _at_throttle()
    r = requests.get(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}/{func_id}',
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
        params={'returnFieldsByFieldId': 'true'},
        timeout=30,
    )
    r.raise_for_status()
    func_fields = r.json().get('fields', {})
    attachments = func_fields.get(F_FUNC_PDF_FOLHA) or []
    status_anexo = _verificar_anexo_em_lista(attachments, ctx['nome_arquivo'], ctx['pdf_hash'])

    detalhes = {
        'funcionario_id': func_id,
        'funcionario_nome': nome,
        'cpf_extraido': cpf,
        'status_anexo': status_anexo,
    }

    if dry_run:
        acao = {
            'novo':     'anexaria_folha_ponto_ao_prontuario',
            'identico': 'folha_ponto_ja_anexada',
            'conflito': 'folha_ponto_conflito_precisaria_autorizacao',
        }[status_anexo]
        return {'acao': acao, 'status_final': 'Concluído', 'detalhes': detalhes, 'pendencia': None}

    if status_anexo == 'identico':
        return {'acao': 'folha_ponto_ja_anexada', 'status_final': 'Concluído', 'detalhes': detalhes, 'pendencia': None}

    if status_anexo == 'conflito':
        return {
            'acao': 'folha_ponto_conflito_anexo_nao_substituido',
            'status_final': 'Revisão Manual',
            'detalhes': detalhes,
            'pendencia': {
                'tipo': 'Conflito de anexo (Folha de Ponto)',
                'observacao': (
                    f'Já existe um anexo "{ctx["nome_arquivo"]}" no prontuário do funcionário '
                    f'{nome} ({func_id}) com conteúdo diferente. Anexo NÃO foi substituído — '
                    f'requer revisão manual.'
                ),
            },
        }

    # status_anexo == 'novo'
    try:
        _anexar_attachment(TABLE_FUNC, func_id, F_FUNC_PDF_FOLHA, ctx['pdf_bytes'], ctx['nome_arquivo'])
        return {'acao': 'folha_ponto_anexada_ao_prontuario', 'status_final': 'Concluído', 'detalhes': detalhes, 'pendencia': None}
    except AirtableError as exc:
        logger.error(f'[FILA] {ctx["proc_id"]}: erro ao anexar Folha de Ponto ao prontuário de {func_id}: {exc}')
        return {
            'acao': 'folha_ponto_falhou_anexo',
            'status_final': 'Revisão Manual',
            'detalhes': detalhes,
            'pendencia': {
                'tipo': 'Erro ao anexar Folha de Ponto',
                'observacao': f'Funcionário {func_id} ({nome}): {exc}',
            },
        }


def _processar_documento_sem_automacao(ctx: dict, dry_run: bool) -> dict:
    """
    Handler genérico (Fase 6 — sanitização) para tipos de documento sem
    processamento automático implementado ainda (Folha de Ponto, Férias,
    FGTS, Guia, Boleto, Nota Fiscal, Outro).

    Antes desta mudança, esses tipos ficavam mapeados para None em
    PROCESSADORES_DOCUMENTO e /processar-fila retornava 400 "ainda não
    implementado" para a requisição inteira — os itens correspondentes
    ficavam parados em "Pendente" em Processar Arquivos, sem nenhuma
    Pendência/visibilidade (ex.: e-mails com FGTS Digital "desapareciam").

    Agora cada item é marcado individualmente com status_final="Revisão
    Manual" e uma Pendência é criada apontando o Arquivo/PDF original, para
    que um humano trate o documento — em vez de o item ficar invisível
    indefinidamente.
    """
    tipo = ctx['tipo_documento']
    observacao = (
        f'Processamento automático de "{tipo}" ainda não implementado. '
        f'Arquivo "{ctx["nome_arquivo"]}" requer tratamento manual '
        f'(Processar Arquivos: {ctx["proc_id"]}, Arquivo: {ctx["arquivo_id"]}).'
    )
    detalhes = {
        'tipo_documento': tipo,
        'arquivo_id': ctx['arquivo_id'],
        'nome_arquivo': ctx['nome_arquivo'],
        'motivo': observacao,
    }

    if dry_run:
        return {
            'acao': 'marcaria_para_revisao_manual',
            'status_final': 'Revisão Manual',
            'detalhes': detalhes,
            'pendencia': None,
        }

    return {
        'acao': 'marcado_para_revisao_manual',
        'status_final': 'Revisão Manual',
        'detalhes': detalhes,
        'pendencia': {
            'tipo': f'Sem automação: {tipo}',
            'observacao': observacao,
        },
    }


# Registro de handlers por tipo de documento (Fase 4 / Fase 6).
# Tipos sem handler dedicado usam _processar_documento_sem_automacao, que
# marca o item como "Revisão Manual" + Pendência em vez de deixá-lo invisível
# (status_final="Revisão Manual" é criado automaticamente como nova opção do
# singleSelect "Status" via typecast=True, tanto em Processar Arquivos quanto
# em Holerites).
PROCESSADORES_DOCUMENTO = {
    'Holerite': _processar_holerite,
    'Folha de Ponto': _processar_folha_ponto,
    'Contrato de Experiência': _processar_contrato_stub,
    'Contrato de Trabalho': _processar_contrato_stub,
    'Férias': _processar_documento_sem_automacao,
    'FGTS': _processar_documento_sem_automacao,
    'Guia': _processar_documento_sem_automacao,
    'Boleto': _processar_documento_sem_automacao,
    'Nota Fiscal': _processar_documento_sem_automacao,
    'Outro': _processar_documento_sem_automacao,
}

# Tipos de documento para os quais o vocabulário de decisão 'decisao_5c'
# (Fase 5C) se aplica e que, portanto, exigem as restrições extras de
# dry_run=false abaixo (record_id específico + limit=1).
TIPOS_CONTRATO_5C = ('Contrato de Experiência', 'Contrato de Trabalho')


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'servico': 'magnata-holerite-splitter',
        'versao': '2.21',
        'ram_mb': _mem_mb(),
    })


@app.route('/separar', methods=['POST'])
def separar():
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
                'valores': dados.get('valores', {}),
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
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    etapa = 'init'
    try:
        if not AIRTABLE_API_KEY:
            return jsonify({
                'status': 'erro',
                'erro': 'AIRTABLE_API_KEY não configurada no servidor.',
                'etapa': etapa,
            }), 500

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
                    'erro': f'Contabilidade Mensal "{nome_mes_cont}" não encontrada. '
                            'Passe mes_cont_id manualmente.',
                    'etapa': etapa,
                }), 500

        ultimo_dia    = monthrange(ano, mes_num)[1]
        data_holerite = f'{ano}-{mes_num:02d}-{ultimo_dia:02d}'

        logger.info(
            f'[CONFIG] folha_mensal={folha_mensal} | data={data_holerite} | mes_cont_id={mes_cont_id}'
        )

        etapa = 'pass1_mapear_cpf'
        mapa, total_paginas = construir_mapa_cpf(caminho_pdf)

        if not mapa:
            return jsonify({
                'status': 'erro', 'erro': 'Nenhum CPF encontrado no PDF.', 'etapa': etapa,
            }), 422

        total_colab = len(mapa)
        logger.info(
            f'[P2] Iniciando criação | {total_colab} colaboradores | '
            f'{total_paginas} páginas | RAM: {_mem_mb()} MB'
        )

        criados: list = []
        erros:   list = []
        contador = 0

        for cpf, dados in mapa.items():
            contador += 1
            nome_pdf = dados['nome']
            paginas  = dados['paginas']
            valores  = dados.get('valores', {})
            tag      = f'[P2 {contador:02d}/{total_colab}]'

            if cpf.startswith('sem_cpf'):
                logger.warning(f'{tag} CPF não extraído | págs: {paginas}')
                erros.append({'cpf': 'N/A', 'nome': nome_pdf,
                              'motivo': 'CPF não extraído', 'paginas': paginas})
                continue

            etapa = f'buscar_funcionario:{cpf}'
            func_id, nome_at = buscar_funcionario_por_cpf(cpf)
            if not func_id:
                logger.warning(f'{tag} Funcionário não encontrado | CPF: {cpf}')
                erros.append({'cpf': cpf, 'nome': nome_pdf,
                              'motivo': 'Funcionário não encontrado no Airtable'})
                continue

            nome_final = nome_at or nome_pdf
            filename   = f'Holerite {folha_mensal} - {nome_final}.pdf'
            logger.info(
                f'{tag} {nome_final} (CPF: {cpf}) | págs: {paginas} | vals: {valores}'
            )

            pdf_ind = None
            try:
                etapa   = f'extrair_pdf:{cpf}'
                pdf_ind = extrair_pdf_colaborador(caminho_pdf, paginas)
                logger.info(f'{tag} PDF: {len(pdf_ind)//1024} KB | RAM: {_mem_mb()} MB')

                etapa     = f'criar_registro:{cpf}'
                record_id = criar_registro_holerite(
                    nome_final, func_id, folha_mensal, data_holerite, mes_cont_id, valores
                )
                logger.info(f'{tag} Registro criado: {record_id} | valores: {valores}')

                etapa = f'anexar_pdf:{cpf}'
                anexar_pdf_holerite(record_id, pdf_ind, filename)
                logger.info(f'{tag} PDF anexado ✓')

                criados.append({
                    'cpf': cpf, 'nome': nome_final,
                    'record_id': record_id, 'arquivo': filename,
                    'paginas': paginas, 'valores': valores,
                })

            except requests.HTTPError as exc:
                motivo = f'HTTP {exc.response.status_code}: {exc.response.text[:300]}'
                logger.error(f'{tag} ERRO Airtable: {motivo}')
                erros.append({'cpf': cpf, 'nome': nome_final,
                              'motivo': motivo, 'etapa': etapa})
            except Exception as exc:
                logger.exception(f'{tag} ERRO inesperado: {exc}')
                erros.append({'cpf': cpf, 'nome': nome_final,
                              'motivo': str(exc), 'etapa': etapa})
            finally:
                if pdf_ind is not None:
                    del pdf_ind
                gc.collect()

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


@app.route('/corrigir-valores', methods=['POST', 'OPTIONS'])
def corrigir_valores():
    """
    Atualiza valores financeiros de holerites já criados mas sem valores
    (ou com valores zerados), SEM criar registros novos — apenas PATCH.

    Fluxo:
      1. Busca holerites para folha_mensal + mes_contabilidade especificados,
         que estejam sem Total Vencimentos (BLANK ou 0)
      2. Para cada registro, baixa o PDF já anexado no Airtable
      3. Extrai valores financeiros via pdfplumber
      4. Atualiza (PATCH) apenas os campos financeiros do registro existente

    Parâmetros JSON:
      folha_mensal       — ex. "Maio 2026"   [obrigatório]
      mes_contabilidade  — ex. "Junho 2026"  [opcional, recomendado]
      dry_run            — true: apenas simula, NÃO grava nada no Airtable
      limit              — int: processa no máximo N registros (teste controlado)
    """
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if not AIRTABLE_API_KEY:
        return jsonify({'status': 'erro', 'erro': 'AIRTABLE_API_KEY não configurada'}), 500

    data = request.get_json(force=True, silent=True) or {}

    def _param(nome):
        return data.get(nome) if data.get(nome) is not None else request.args.get(nome)

    folha_mensal = _param('folha_mensal')
    mes_contabilidade = _param('mes_contabilidade')
    if not folha_mensal:
        return jsonify({'status': 'erro', 'erro': 'folha_mensal é obrigatório'}), 400

    dry_run_raw = _param('dry_run')
    dry_run = str(dry_run_raw).strip().lower() in ('1', 'true', 'yes', 'sim')

    limit = None
    limit_raw = _param('limit')
    if limit_raw is not None:
        try:
            limit = int(limit_raw)
            if limit <= 0:
                limit = None
        except (TypeError, ValueError):
            limit = None

    logger.info(
        f'[CORR] Iniciando correção | folha_mensal={folha_mensal} | '
        f'mes_contabilidade={mes_contabilidade or "(qualquer)"} | '
        f'dry_run={dry_run} | limit={limit if limit is not None else "(sem limite)"}'
    )

    # 1. Buscar holerites da folha/mês sem Total Vencimentos (BLANK ou 0)
    condicoes = [
        f'{{Folha Mensal}}="{folha_mensal}"',
        'OR({Total Vencimentos}=BLANK(), {Total Vencimentos}=0)',
    ]
    if mes_contabilidade:
        condicoes.append(f'FIND("{mes_contabilidade}", ARRAYJOIN({{Mês Contabilidade}}))')
    formula = 'AND(' + ', '.join(condicoes) + ')'

    todos: list = []
    offset = None
    pagina = 0
    while True:
        pagina += 1
        _at_throttle()
        params = {
            'filterByFormula': formula,
            'fields[]': [
                'Holerite', 'PDF HOLERITE', 'Folha Mensal',
                'Mês Contabilidade', 'Total Vencimentos',
            ],
            'pageSize': 100,
        }
        if offset:
            params['offset'] = offset
        r = requests.get(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_HOL}',
            headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
            params=params,
            timeout=30,
        )
        if not r.ok:
            return jsonify({
                'status': 'erro',
                'erro': f'Airtable list error: {r.status_code} {r.text[:300]}'
            }), 500

        body = r.json()
        todos.extend(body.get('records', []))
        offset = body.get('offset')
        logger.info(f'[CORR] Página {pagina}: {len(body.get("records", []))} registros')
        if not offset:
            break

    logger.info(f'[CORR] Total sem valores: {len(todos)}')
    if not todos:
        return jsonify({
            'status': 'concluido',
            'folha_mensal': folha_mensal,
            'mes_contabilidade': mes_contabilidade,
            'dry_run': dry_run,
            'total_sem_valores': 0,
            'atualizados': 0,
            'erros': 0,
            'detalhe': [],
        })

    total_encontrados = len(todos)
    if limit is not None:
        todos = todos[:limit]
        logger.info(f'[CORR] limit={limit} aplicado | processando {len(todos)} de {total_encontrados}')

    atualizados = 0
    erros_list: list = []
    processados: list = []

    for rec in todos:
        record_id = rec['id']
        nome_hol  = rec.get('fields', {}).get('Holerite', record_id)
        attachments = rec.get('fields', {}).get('PDF HOLERITE', [])

        if not attachments:
            logger.warning(f'[CORR] {nome_hol}: sem PDF anexado')
            erros_list.append({'record_id': record_id, 'nome': nome_hol,
                               'motivo': 'sem PDF anexado'})
            continue

        pdf_url = attachments[0].get('url')
        if not pdf_url:
            erros_list.append({'record_id': record_id, 'nome': nome_hol,
                               'motivo': 'URL do PDF não disponível'})
            continue

        # Baixar o PDF do Airtable CDN
        tmp_path = None
        try:
            resp = requests.get(pdf_url, timeout=30)
            resp.raise_for_status()
            tmp_path = f'/tmp/corr_{_uuid.uuid4().hex}.pdf'
            with open(tmp_path, 'wb') as f:
                f.write(resp.content)

            # Extrair texto e valores
            texto_completo = ''
            with pdfplumber.open(tmp_path) as pdf_doc:
                for pg in pdf_doc.pages:
                    texto_completo += (pg.extract_text() or '') + '\n'

            valores = extrair_valores_holerite(texto_completo)
            logger.info(f'[CORR] {nome_hol}: valores extraídos = {valores}')

            if not valores:
                erros_list.append({'record_id': record_id, 'nome': nome_hol,
                                   'motivo': 'valores não encontrados no PDF'})
                continue

            if dry_run:
                logger.info(f'[CORR] {nome_hol}: [DRY RUN] não gravado | valores = {valores}')
                processados.append({'record_id': record_id, 'nome': nome_hol,
                                     'valores': valores, 'gravado': False})
            else:
                # Atualizar no Airtable
                atualizar_valores_holerite(record_id, valores)
                logger.info(f'[CORR] {nome_hol}: atualizado ✓ | valores = {valores}')
                processados.append({'record_id': record_id, 'nome': nome_hol,
                                     'valores': valores, 'gravado': True})

            atualizados += 1

        except requests.HTTPError as exc:
            motivo = f'HTTP {exc.response.status_code} ao baixar PDF'
            logger.error(f'[CORR] {nome_hol}: {motivo}')
            erros_list.append({'record_id': record_id, 'nome': nome_hol, 'motivo': motivo})
        except Exception as exc:
            logger.exception(f'[CORR] {nome_hol}: erro inesperado')
            erros_list.append({'record_id': record_id, 'nome': nome_hol, 'motivo': str(exc)})
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            gc.collect()

    logger.info(
        f'[CORR] Concluído | dry_run={dry_run} | total_encontrados={total_encontrados} | '
        f'processados={len(todos)} | atualizados={atualizados} | erros={len(erros_list)}'
    )
    return jsonify({
        'status': 'concluido',
        'folha_mensal': folha_mensal,
        'mes_contabilidade': mes_contabilidade,
        'dry_run': dry_run,
        'limit': limit,
        'total_sem_valores': total_encontrados,
        'total_processados': len(todos),
        'atualizados': atualizados,
        'erros': len(erros_list),
        'detalhe_erros': erros_list,
        'detalhe_processados': processados,
    })


@app.route('/email/webhook', methods=['POST', 'OPTIONS'])
def email_webhook():
    """
    Fase 2 — Caixa de Entrada.

    Recebe e-mail + anexos (JSON) vindos do Google Apps Script, registra em
    Emails Savian / Arquivos / Processar Arquivos, classifica o tipo de
    documento e cria pendências quando necessário.

    Protegido por header X-API-KEY (variável de ambiente EMAIL_WEBHOOK_KEY).

    Payload esperado (JSON):
      {
        "message_id": "<...@mail.gmail.com>",   [obrigatório]
        "assunto": "...",
        "remetente": "...",
        "corpo": "...",
        "anexos": [{"nome_arquivo": "x.pdf", "conteudo_base64": "..."}],
        "dry_run": true
      }
    """
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    api_key = request.headers.get('X-API-KEY', '')
    if not EMAIL_WEBHOOK_KEY or api_key != EMAIL_WEBHOOK_KEY:
        return jsonify({'status': 'erro', 'erro': 'X-API-KEY inválida ou ausente'}), 401

    if not AIRTABLE_API_KEY:
        return jsonify({'status': 'erro', 'erro': 'AIRTABLE_API_KEY não configurada'}), 500

    data = request.get_json(force=True, silent=True) or {}

    message_id = data.get('message_id')
    if not message_id:
        return jsonify({'status': 'erro', 'erro': 'message_id é obrigatório'}), 400

    assunto   = data.get('assunto', '') or ''
    remetente = data.get('remetente', '') or ''
    corpo     = data.get('corpo', '') or ''
    anexos    = data.get('anexos', []) or []
    dry_run   = str(data.get('dry_run', False)).strip().lower() in ('1', 'true', 'yes', 'sim')

    logger.info(
        f'[EMAIL] message_id={message_id} | assunto={assunto!r} | '
        f'remetente={remetente!r} | anexos={len(anexos)} | dry_run={dry_run}'
    )

    resultado = {
        'status': 'ok',
        'dry_run': dry_run,
        'message_id': message_id,
        'anexos_processados': [],
    }

    # 1. Checar Message-ID duplicado — se já existe, não processa nada
    existente = _buscar_por_campo(TABLE_EMAILS, 'MESSAGE ID', message_id)
    if existente:
        resultado['email_savian'] = {
            'acao': 'duplicado_message_id', 'record_id': existente['id'], 'gravado': False,
        }
        logger.info(f'[EMAIL] Message-ID já existe em Emails Savian: {existente["id"]} → ignorando')
        return jsonify(resultado)

    email_savian_id = None
    if dry_run:
        resultado['email_savian'] = {'acao': 'criaria_novo', 'gravado': False}
    else:
        email_savian_id = _criar_registro(TABLE_EMAILS, {
            F_EMAIL_NAME:     f'{assunto or "(sem assunto)"} — {message_id[:40]}',
            F_EMAIL_STATUS:   'Recebido',
            F_EMAIL_ASSUNTO:  assunto,
            F_EMAIL_CONTEUDO: corpo,
            F_EMAIL_MSGID:    message_id,
        })
        resultado['email_savian'] = {'acao': 'criado', 'gravado': True, 'record_id': email_savian_id}
        logger.info(f'[EMAIL] Emails Savian criado: {email_savian_id}')

    # 2. Processar cada anexo
    for anexo in anexos:
        nome_arquivo = anexo.get('nome_arquivo', 'arquivo.pdf')
        b64 = anexo.get('conteudo_base64', '')
        item = {'nome_arquivo': nome_arquivo}

        try:
            conteudo = base64.b64decode(b64)
        except Exception as exc:
            item['erro'] = f'base64 inválido: {exc}'
            resultado['anexos_processados'].append(item)
            continue

        hash_anexo = hashlib.sha256(conteudo).hexdigest()
        item['hash'] = hash_anexo
        item['tamanho_bytes'] = len(conteudo)

        # Checar duplicidade pelo hash do anexo
        dup = _buscar_por_campo(TABLE_ARQUIVOS, 'Hash do Anexo', hash_anexo)
        if dup:
            item['duplicado'] = True
            item['arquivo_record_id'] = dup['id']
            resultado['anexos_processados'].append(item)
            logger.info(f'[EMAIL] Anexo {nome_arquivo} duplicado (hash já existe): {dup["id"]}')
            continue
        item['duplicado'] = False

        # Extrair texto (só PDFs) e classificar
        texto = ''
        if nome_arquivo.lower().endswith('.pdf'):
            tmp_path = f'/tmp/email_{_uuid.uuid4().hex}.pdf'
            try:
                with open(tmp_path, 'wb') as f:
                    f.write(conteudo)
                with pdfplumber.open(tmp_path) as pdf_doc:
                    for pg in pdf_doc.pages:
                        texto += (pg.extract_text() or '') + '\n'
            except Exception as exc:
                item['erro_extracao'] = str(exc)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        if not texto.strip():
            tipo_doc, confianca = 'Não Identificado', 0
            tipo_problema = 'PDF ilegível'
        else:
            tipo_doc, confianca = classificar_documento(texto)
            tipo_problema = 'Documento não reconhecido' if tipo_doc == 'Outro' else None

        item['tipo_documento'] = tipo_doc
        item['confianca'] = confianca
        item['trecho_texto'] = texto[:500]
        item['pendencia'] = tipo_problema

        if dry_run:
            item['acao'] = 'criaria_arquivo_e_processar' + (f'_e_pendencia({tipo_problema})' if tipo_problema else '')
            resultado['anexos_processados'].append(item)
            continue

        # Criar registro em Arquivos + anexar PDF
        arquivo_fields = {
            F_ARQ_NOME:     nome_arquivo,
            F_ARQ_NOME_ARQ: nome_arquivo,
            F_ARQ_HASH:     hash_anexo,
            F_ARQ_STATUS:   'Recebido',
            F_ARQ_DATA:     datetime.now().isoformat(),
        }
        if email_savian_id:
            arquivo_fields[F_ARQ_EMAILS] = [email_savian_id]
        arquivo_id = _criar_registro(TABLE_ARQUIVOS, arquivo_fields)
        _anexar_attachment(TABLE_ARQUIVOS, arquivo_id, F_ARQ_ATTACH, conteudo, nome_arquivo)
        item['arquivo_record_id'] = arquivo_id
        logger.info(f'[EMAIL] Arquivo criado: {arquivo_id} ({nome_arquivo})')

        # Criar registro em Processar Arquivos
        processar_id = _criar_registro(TABLE_PROCESSAR, {
            F_PROC_NAME:      nome_arquivo,
            F_PROC_STATUS:    'Pendente',
            F_PROC_TIPO_DOC:  tipo_doc,
            F_PROC_DATA:      datetime.now().isoformat(),
            F_PROC_ARQUIVOS2: [arquivo_id],
        })
        item['processar_record_id'] = processar_id
        logger.info(f'[EMAIL] Processar Arquivos criado: {processar_id} | tipo={tipo_doc}')

        # Criar pendência, se necessário
        if tipo_problema:
            pendencia_id = _criar_registro(TABLE_PENDENCIAS, {
                F_PEND_NOME:   f'{tipo_problema}: {nome_arquivo}',
                F_PEND_STATUS: 'Pendente',
                F_PEND_TIPO:   tipo_problema,
                F_PEND_ORIGEM: [arquivo_id],
                F_PEND_OBS:    texto[:500] if texto.strip() else '(sem texto extraído do PDF)',
                F_PEND_DATA:   datetime.now().isoformat(),
            })
            item['pendencia_record_id'] = pendencia_id
            logger.info(f'[EMAIL] Pendência criada: {pendencia_id} ({tipo_problema})')

        resultado['anexos_processados'].append(item)

    return jsonify(resultado)


@app.route('/processar-fila', methods=['POST', 'OPTIONS'])
def processar_fila():
    """
    Fase 4 — Processador genérico da fila "Processar Arquivos".

    Estrutura preparada para todos os tipos de TIPO_DOC_REGRAS + 'Outro', mas
    nesta implementação apenas 'Holerite' tem handler (demais retornam 400).

    Body JSON:
      {
        "tipo_documento": "Holerite",   [obrigatório]
        "dry_run": true,
        "limit": 1,
        "record_id": "rec...",          [opcional — processa só este registro]
        "folha_mensal": "Fevereiro 2026",  [opcional — senão usa mês anterior]
        "mes_cont_id": "rec..."         [opcional]
      }
    """
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    api_key = request.headers.get('X-API-KEY', '')
    if not EMAIL_WEBHOOK_KEY or api_key != EMAIL_WEBHOOK_KEY:
        return jsonify({'status': 'erro', 'erro': 'X-API-KEY inválida ou ausente'}), 401

    if not AIRTABLE_API_KEY:
        return jsonify({'status': 'erro', 'erro': 'AIRTABLE_API_KEY não configurada'}), 500

    data = request.get_json(force=True, silent=True) or {}

    tipo_documento = data.get('tipo_documento')
    if not tipo_documento:
        return jsonify({'status': 'erro', 'erro': 'tipo_documento é obrigatório'}), 400

    if tipo_documento not in PROCESSADORES_DOCUMENTO:
        return jsonify({
            'status': 'erro',
            'erro': f'tipo_documento desconhecido: {tipo_documento}',
            'tipos_validos': list(PROCESSADORES_DOCUMENTO.keys()),
        }), 400

    handler = PROCESSADORES_DOCUMENTO[tipo_documento]
    if handler is None:
        return jsonify({
            'status': 'erro',
            'erro': f'Processamento de "{tipo_documento}" ainda não implementado',
        }), 400

    dry_run = str(data.get('dry_run', False)).strip().lower() in ('1', 'true', 'yes', 'sim')
    limit = data.get('limit', 1)
    try:
        limit = max(1, int(limit))
    except (TypeError, ValueError):
        limit = 1
    record_id = data.get('record_id')

    # Regras de segurança 8 e 9 (Fase 5C): para Contrato de Experiência e
    # Contrato de Trabalho, dry_run=false só é aceito com um record_id
    # específico e limit=1 — nunca processando a fila geral. Não afeta
    # Holerite nem outros tipos.
    if tipo_documento in TIPOS_CONTRATO_5C and not dry_run:
        if not record_id or limit != 1:
            return jsonify({
                'status': 'erro',
                'erro': (
                    f'Para "{tipo_documento}" com dry_run=false é obrigatório '
                    'informar "record_id" de um registro específico e "limit"=1 '
                    '(processamento da fila geral não é permitido nesta fase).'
                ),
            }), 400

    # Resolver folha_mensal / mes_cont_id / data_holerite
    folha_mensal = data.get('folha_mensal')
    mes_cont_id = data.get('mes_cont_id')
    if not folha_mensal:
        nome_mes, ano, mes_num = mes_anterior_info()
        folha_mensal = f'{nome_mes} {ano}'
        data_holerite = f'{ano}-{mes_num:02d}-01'
    else:
        data_holerite = datetime.now().strftime('%Y-%m-%d')

    if not mes_cont_id:
        mes_cont_id = _buscar_contabilidade_mensal_por_nome(folha_mensal)
        if not mes_cont_id:
            mes_cont_id, _ = buscar_mes_contabilidade_atual()

    logger.info(
        f'[FILA] tipo_documento={tipo_documento} | dry_run={dry_run} | limit={limit} | '
        f'record_id={record_id} | folha_mensal={folha_mensal!r} | mes_cont_id={mes_cont_id}'
    )

    # Montar filtro
    if record_id:
        formula = f'RECORD_ID()="{record_id}"'
    else:
        formula = (
            f'AND('
            f'OR({{Status}}="Processando", {{Status}}="Pendente"), '
            f'{{Tipo de Documento}}="{tipo_documento}"'
            f')'
        )

    _at_throttle()
    r = requests.get(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_PROCESSAR}',
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
        params={
            'filterByFormula': formula,
            'maxRecords': limit,
            'sort[0][field]': 'Data Processo',
            'sort[0][direction]': 'asc',
            'returnFieldsByFieldId': 'true',
        },
        timeout=30,
    )
    r.raise_for_status()
    registros = r.json().get('records', [])

    resultado = {
        'status': 'ok',
        'dry_run': dry_run,
        'tipo_documento': tipo_documento,
        'folha_mensal': folha_mensal,
        'mes_cont_id': mes_cont_id,
        'registros_encontrados': len(registros),
        'processados': [],
    }

    for rec in registros:
        proc_id = rec['id']
        fields = rec.get('fields', {})
        item = {'processar_id': proc_id}

        tmp_path = None
        try:
            # Localizar Arquivo vinculado
            arquivos_link = fields.get(F_PROC_ARQUIVOS2) or []
            if not arquivos_link:
                item['erro'] = 'Nenhum Arquivo vinculado em "Arquivos 2"'
                if not dry_run:
                    _atualizar_status_processar(proc_id, 'Erro')
                    _criar_pendencia(proc_id, 'Arquivo não vinculado', item['erro'])
                item['status_final'] = 'Erro'
                resultado['processados'].append(item)
                logger.error(f'[FILA] {proc_id}: {item["erro"]}')
                continue

            primeiro_link = arquivos_link[0]
            arquivo_id = primeiro_link['id'] if isinstance(primeiro_link, dict) else primeiro_link
            item['arquivo_id'] = arquivo_id

            _at_throttle()
            r_arq = requests.get(
                f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_ARQUIVOS}/{arquivo_id}',
                headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
                params={'returnFieldsByFieldId': 'true'},
                timeout=30,
            )
            r_arq.raise_for_status()
            arquivo_fields = r_arq.json().get('fields', {})

            attachments = arquivo_fields.get(F_ARQ_ATTACH) or []
            if not attachments:
                item['erro'] = 'Arquivo sem anexo PDF'
                if not dry_run:
                    _atualizar_status_processar(proc_id, 'Erro')
                    _criar_pendencia(arquivo_id, 'Arquivo sem anexo', item['erro'])
                item['status_final'] = 'Erro'
                resultado['processados'].append(item)
                logger.error(f'[FILA] {proc_id}: {item["erro"]}')
                continue

            nome_arquivo = attachments[0].get('filename', 'arquivo.pdf')
            pdf_url = attachments[0]['url']
            pdf_bytes = requests.get(pdf_url, timeout=60).content

            # Extrair texto do PDF
            tmp_path = f'/tmp/fila_{_uuid.uuid4().hex}.pdf'
            with open(tmp_path, 'wb') as f:
                f.write(pdf_bytes)
            texto = ''
            with pdfplumber.open(tmp_path) as pdf_doc:
                for pg in pdf_doc.pages:
                    texto += (pg.extract_text() or '') + '\n'

            status_atual = fields.get(F_PROC_STATUS, 'Processando')

            ctx = {
                'proc_id': proc_id,
                'arquivo_id': arquivo_id,
                'pdf_bytes': pdf_bytes,
                'pdf_hash': hashlib.sha256(pdf_bytes).hexdigest(),
                'nome_arquivo': nome_arquivo,
                'texto': texto,
                'folha_mensal': folha_mensal,
                'mes_cont_id': mes_cont_id,
                'data_holerite': data_holerite,
                'tipo_documento': tipo_documento,
                'status_atual': status_atual,
            }

            resultado_handler = handler(ctx, dry_run)
            item['acao'] = resultado_handler['acao']
            item['status_final'] = resultado_handler['status_final']
            item['detalhes'] = resultado_handler['detalhes']

            if not dry_run:
                _atualizar_status_processar(proc_id, resultado_handler['status_final'])
                pendencia = resultado_handler.get('pendencia')
                if pendencia:
                    pend_id = _criar_pendencia(arquivo_id, pendencia['tipo'], pendencia['observacao'])
                    item['pendencia_id'] = pend_id

            logger.info(f'[FILA] {proc_id}: acao={item["acao"]} status_final={item["status_final"]}')

        except Exception as exc:
            logger.exception(f'[FILA] Erro ao processar {proc_id}')
            item['erro'] = str(exc)
            item['status_final'] = 'Erro'
            if not dry_run:
                _atualizar_status_processar(proc_id, 'Erro')
                _criar_pendencia(proc_id, 'Erro de processamento', str(exc))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        resultado['processados'].append(item)

    return jsonify(resultado)


# ── Diagnóstico de Distribuição (read-only) ──────────────────────────────────

def _at_listar_todos(table_id, field_names=None, filter_formula=None):
    """Lista TODOS os registros de uma tabela (paginação via offset). Somente leitura."""
    registros = []
    params = {}
    if field_names:
        params['fields[]'] = field_names
    if filter_formula:
        params['filterByFormula'] = filter_formula
    offset = None
    while True:
        if offset:
            params['offset'] = offset
        _at_throttle()
        r = requests.get(
            f'https://api.airtable.com/v0/{BASE_ID}/{table_id}',
            headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        registros.extend(data.get('records', []))
        offset = data.get('offset')
        if not offset:
            break
    return registros


def _diagnostico_holerites(folha_mensal=None, limit=None):
    """
    Diagnóstico read-only: classifica cada Holerite existente em
    'pronto_whatsapp_colaborador', 'pronto_pacote_cliente', 'pronto_ambos'
    ou 'pendente', conforme a diretriz de Distribuição Mensal de Documentos.

    Nenhuma escrita é feita — apenas leitura em Holerites, Funcionários,
    Locais e Clientes.
    """
    clientes = {
        rec['id']: {
            'nome': rec['fields'].get('Nome', ''),
            'email': rec['fields'].get('Email'),
        }
        for rec in _at_listar_todos(TABLE_CLIENTES, ['Nome', 'Email'])
    }

    locais = {
        rec['id']: {
            'nome': rec['fields'].get('Nome', ''),
            'cliente_ids': rec['fields'].get('Cliente', []),
        }
        for rec in _at_listar_todos(TABLE_LOCAIS, ['Nome', 'Cliente'])
    }

    funcionarios = {
        rec['id']: {
            'nome': rec['fields'].get('Nome Completo', ''),
            'whatsapp': rec['fields'].get('WhatsApp'),
            'locais_ids': rec['fields'].get('Locais de trabalho', []),
        }
        for rec in _at_listar_todos(TABLE_FUNC, ['Nome Completo', 'WhatsApp', 'Locais de trabalho'])
    }

    filtro = f'{{Folha Mensal}}="{folha_mensal}"' if folha_mensal else None
    holerite_fields = [
        'Holerite', 'Status', 'Funcionário', 'Data', 'Folha Mensal',
        'PDF HOLERITE', 'Envios de Documentos',
    ]
    holerites = _at_listar_todos(TABLE_HOL, holerite_fields, filtro)
    if limit:
        holerites = holerites[:limit]

    contagem = {
        'pronto_whatsapp_colaborador': 0,
        'pronto_pacote_cliente': 0,
        'pronto_ambos': 0,
        'pendente': 0,
    }
    motivos_pendencia = Counter()
    exemplos_prontos = []
    exemplos_pendentes = []
    com_envio_vinculado = 0
    sem_envio_vinculado = 0

    for rec in holerites:
        f = rec['fields']
        func_ids = f.get('Funcionário', []) or []
        func = funcionarios.get(func_ids[0]) if func_ids else None

        whatsapp = func.get('whatsapp') if func else None
        arquivo_ok = bool(f.get('PDF HOLERITE'))
        folha_ok = bool(f.get('Folha Mensal'))

        cliente_ids = set()
        if func:
            for local_id in func.get('locais_ids', []) or []:
                local = locais.get(local_id)
                if local:
                    cliente_ids.update(local.get('cliente_ids', []) or [])

        cliente_email = None
        cliente_nome = None
        if cliente_ids:
            primeiro = clientes.get(next(iter(cliente_ids)))
            if primeiro:
                cliente_nome = primeiro.get('nome')
                cliente_email = primeiro.get('email')

        motivos = []
        if not func_ids:
            motivos.append('funcionario_nao_identificado')
        if not whatsapp:
            motivos.append('whatsapp_ausente')
        if not arquivo_ok:
            motivos.append('arquivo_holerite_ausente')
        if not folha_ok:
            motivos.append('folha_mensal_ausente')
        if not cliente_ids:
            motivos.append('cliente_local_nao_identificado')
        elif not cliente_email:
            motivos.append('email_cliente_ausente')

        ok_whatsapp = (
            func_ids and whatsapp and arquivo_ok and folha_ok
        )
        ok_cliente = (
            cliente_ids and cliente_email and arquivo_ok and folha_ok
        )

        if ok_whatsapp and ok_cliente:
            situacao = 'pronto_ambos'
        elif ok_whatsapp:
            situacao = 'pronto_whatsapp_colaborador'
        elif ok_cliente:
            situacao = 'pronto_pacote_cliente'
        else:
            situacao = 'pendente'
            motivos_pendencia.update(motivos)

        contagem[situacao] += 1

        envios = f.get('Envios de Documentos', []) or []
        if envios:
            com_envio_vinculado += 1
        else:
            sem_envio_vinculado += 1

        exemplo = {
            'record_id': rec['id'],
            'holerite': f.get('Holerite'),
            'funcionario': func.get('nome') if func else None,
            'whatsapp': whatsapp,
            'cliente': cliente_nome,
            'email_cliente': cliente_email,
            'folha_mensal': f.get('Folha Mensal'),
            'situacao': situacao,
            'motivos': motivos or None,
        }
        if situacao == 'pendente':
            if len(exemplos_pendentes) < 5:
                exemplos_pendentes.append(exemplo)
        else:
            if len(exemplos_prontos) < 5:
                exemplos_prontos.append(exemplo)

    return {
        'total_holerites_analisados': len(holerites),
        'contagem': contagem,
        'principais_motivos_pendencia': motivos_pendencia.most_common(),
        'exemplos_prontos': exemplos_prontos,
        'exemplos_pendentes': exemplos_pendentes,
        'campos_tabelas_usados': {
            'Holerites': holerite_fields,
            'Funcionários': ['Nome Completo', 'WhatsApp', 'Locais de trabalho'],
            'Locais': ['Nome', 'Cliente'],
            'Clientes': ['Nome', 'Email'],
        },
        'campos_faltando_para_destravar': [
            'WhatsApp ausente em Funcionários' if motivos_pendencia.get('whatsapp_ausente') else None,
            'Cliente/Local não identificado a partir de Funcionários->Locais de trabalho->Cliente'
                if motivos_pendencia.get('cliente_local_nao_identificado') else None,
            'Email ausente em Clientes' if motivos_pendencia.get('email_cliente_ausente') else None,
            'Holerite sem Funcionário vinculado' if motivos_pendencia.get('funcionario_nao_identificado') else None,
            'Holerite sem PDF anexado' if motivos_pendencia.get('arquivo_holerite_ausente') else None,
            'Holerite sem Folha Mensal preenchida' if motivos_pendencia.get('folha_mensal_ausente') else None,
        ],
        'investigacao_tela_enviar_holerites': {
            'tabela_provavel': (
                f'Envios de Documentos ({TABLE_ENVIOS}) — possui campos Status, Tipo, '
                'Canal, Enviar (checkbox), Holerites (link), Email, Destinatário, Erro, '
                'ID da Mensagem, Tentativa, consistentes com uma fila de despacho.'
            ),
            'holerites_com_envio_vinculado': com_envio_vinculado,
            'holerites_sem_envio_vinculado': sem_envio_vinculado,
            'hipotese': (
                'A tela "Enviar Holerites" provavelmente lista registros da tabela '
                '"Envios de Documentos" (filtrados por Tipo/Status), não os Holerites '
                'diretamente. Holerites já existentes que nunca tiveram um registro '
                'correspondente criado em "Envios de Documentos" não apareceriam na '
                'tela, mesmo estando prontos.'
            ),
            'limitacoes': (
                'Esta API não tem acesso a automações, botões, views/filtros do '
                'Airtable nem a configurações de Make/Apps Script/Gmail — a hipótese '
                'acima é inferida apenas a partir do schema de dados (somente leitura). '
                'Confirmação definitiva requer inspeção manual da view/automação na '
                'interface do Airtable.'
            ),
        },
        'observacao': (
            'Diagnóstico 100% somente leitura. Nenhum WhatsApp ou e-mail foi enviado, '
            'nenhum registro foi criado/alterado em Holerites, Funcionários, Clientes, '
            'Locais, Envios de Documentos ou Pendências/Revisar.'
        ),
    }


@app.route('/diagnostico-holerites', methods=['GET', 'OPTIONS'])
def diagnostico_holerites():
    """
    Diagnóstico read-only dos Holerites existentes (Distribuição Mensal de
    Documentos — menor próximo passo seguro). Não envia WhatsApp/e-mail, não
    altera nada no Airtable.

    Query params opcionais:
      - folha_mensal: filtra Holerites por "Folha Mensal" (ex.: "Maio 2026")
      - limit: limita a quantidade de Holerites analisados
    """
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    api_key = request.headers.get('X-API-KEY', '')
    if not EMAIL_WEBHOOK_KEY or api_key != EMAIL_WEBHOOK_KEY:
        return jsonify({'status': 'erro', 'erro': 'X-API-KEY inválida ou ausente'}), 401

    if not AIRTABLE_API_KEY:
        return jsonify({'status': 'erro', 'erro': 'AIRTABLE_API_KEY não configurada'}), 500

    folha_mensal = request.args.get('folha_mensal')
    limit = request.args.get('limit')
    try:
        limit = int(limit) if limit else None
    except ValueError:
        limit = None

    resultado = _diagnostico_holerites(folha_mensal=folha_mensal, limit=limit)
    return jsonify(resultado)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
