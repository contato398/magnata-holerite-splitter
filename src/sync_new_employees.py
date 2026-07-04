"""
src/sync_new_employees.py — Automação de cadastro de novos funcionários

Lê os dados cadastrais (Nome, Cargo, Data de Admissão, CPF) direto do
cabeçalho dos PDFs de holerite, completa/cria a linha do Funcionário no
Airtable e prepara a sincronização com o Ponto Web da Secullum.

NOTA SOBRE A "PASTA DE INSUMOS": este projeto não recebe holerites por uma
pasta local — eles chegam por e-mail/upload e ficam anexados na tabela
Holerites do Airtable (campo "PDF HOLERITE"). `listar_holerites_recentes`
varre essa tabela (mais recentes primeiro) em vez de um diretório local.

NOTA SOBRE O PIS: testado contra 2 holerites reais (Maio/2026 — Davi Leme
dos Santos e Leandro Faustino Silveira). O modelo de holerite da Magnata
NÃO imprime o número do PIS em lugar nenhum do documento. O regex de PIS
está implementado por completude, mas hoje sempre retorna None nesse
modelo — PIS precisa vir de outra fonte (carteira de trabalho, ficha de
registro, e-Social) se for obrigatório no cadastro.

Responsabilidades:
  1. Extração (regex no texto do PDF, via pdfplumber): Nome, CPF, Cargo,
     Data de Admissão (PIS quando o documento trouxer).
  2. Estruturação no Airtable: casa por CPF; cria a linha se não existir,
     completa campos vazios se já existir (nunca sobrescreve dado já
     preenchido). Tabela Funcionários ganhou 3 campos novos nesta entrega:
     "Grupo de Escala", "Status de Sincronização" e "Secullum ID".
  3. Sincronização Secullum: para quem está com Status de Sincronização =
     "Pendente" E Grupo de Escala preenchido, chama
     `secullum_ponto.sincronizar_funcionario`, grava o Id retornado em
     "Secullum ID" e muda o status para "Sincronizado".

ATENÇÃO (lição aprendida na integração /secullum): "Grupo de Escala" aqui é
uma INTENÇÃO definida na admissão (qual conjunto de dias a pessoa deve
trabalhar), não uma leitura de dado já existente — diferente do rótulo
PAR/ÍMPAR do Horario.Descricao da Secullum, que se mostrou não confiável
(funcionário rotulado "PAR" às vezes trabalha nos dias ÍMPARES de fato).
Depois que o Ponto Web começar a registrar batidas reais, confirme que a
escala efetivamente seguida bate com o grupo aqui definido.

Uso:
    python -m src.sync_new_employees --dry-run --limit 5
    python -m src.sync_new_employees --dry-run --cpf 397.529.068-42
"""

import os
import re
import io
import sys
import logging
import argparse
import traceback
import unicodedata

import requests
from flask import Blueprint, request, jsonify

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None

logger = logging.getLogger(__name__)

# ── Airtable (mesmos IDs/padrões do app.py e de secullum_ponto.py) ──────────────
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY', '')
BASE_ID    = 'appaCpIVj7Q97VhFy'
TABLE_FUNC = 'tblNd8G66kjwos3eP'   # Funcionários
TABLE_HOL  = 'tblVaUgZeFfa5zRcH'   # Holerites

F_FUNC_CPF        = 'fld0Y3bXdArkSIJxo'
F_FUNC_NOME       = 'fld2fSiomk9AOLGDb'   # Nome Completo
F_FUNC_CARGO      = 'fldK1lJS1L4tbZVmZ'
F_FUNC_ADMISSAO   = 'fld5L1djmJugvLe8c'   # Data de Admissão
F_FUNC_PIS        = 'fldNNWb5BLgdBdsJO'
F_FUNC_CODIGO     = 'fldCtZHUjJBi7JQXb'
F_FUNC_GRUPO_ESCALA  = 'fldMPI8FCJm33KFBC'   # "Grupo de Escala" (criado nesta entrega)
F_FUNC_STATUS_SYNC   = 'fldBwlxrtwnQmHQvh'   # "Status de Sincronização" (criado nesta entrega)
F_FUNC_SECULLUM_ID   = 'fldPh3AVURpYXA60r'   # "Secullum ID" (criado nesta entrega)

F_HOL_PDF         = 'fldGXsgmuADtZIgtx'   # PDF HOLERITE (attachment)
F_HOL_FUNCIONARIO = 'fldTXMjeHfgyDas9f'   # Funcionário (link)
F_HOL_FOLHA       = 'fldqQZwNnMf8BGfyP'   # Folha Mensal (texto)

GRUPO_ESCALA_A = 'Escala A - Dias Pares'
GRUPO_ESCALA_B = 'Escala B - Dias Ímpares'
STATUS_PENDENTE      = 'Pendente'
STATUS_SINCRONIZADO  = 'Sincronizado'

# Cargo (Airtable) -> (funcaoDescricao, departamentoDescricao) na Secullum.
# Levantado em 27/06/2026 a partir dos 88 funcionários já cadastrados (GET
# /Funcionarios, ver /secullum/debug?listar_referencias=1).
#
# ACHADO IMPORTANTE: o endpoint POST /IntegracaoExterna/Funcionarios usa um
# schema PRÓPRIO (`FuncionarioIntegracaoExternaPost`, confirmado no Swagger
# oficial) — Função/Departamento são por TEXTO da descrição, não por Id (que
# só existe no shape de LEITURA do GET). Os primeiros 18 cadastros do
# saneamento de 27/06/2026 falharam com 400 "campo obrigatório" justamente
# por terem sido enviados com Ids em vez de descrição.
_MAPA_CARGO_SECULLUM = {
    'CONTROLADOR DE ACESSO': ('CONTROLADOR DE ACESSO', 'CONTROLADOR DE ACESSO'),
    'AUXILIAR DE LIMPEZA': ('Auxiliar de Limpeza', 'Auxiliar de Limpeza'),
    'SUPERVISOR DE PERIMETRO': ('SUPERVISOR DE PERIMETRO', 'SUPERVISOR DE PERIMETRO'),
    'JARDINEIRO': ('JARDINEIRO', 'JARDINEIRO'),
    'ZELADOR': ('ZELADOR', 'ZELADOR'),
    'SUPERVISOR': ('SUPERVISOR', 'SUPERVISOR'),
    'SERVICOS GERAIS': ('SERVIÇOS GERAIS', 'SERVIÇOS GERAIS'),
}
SECULLUM_EMPRESA_ID = 1   # única empresa cadastrada na Secullum (confirmado 27/06/2026)
# Horário padrão (fallback) — use GET /ingestao/secullum/horarios para listar
# os números disponíveis e preencha MAPA_CARGO_HORARIO em ingestao_secullum.py.
SECULLUM_HORARIO_NUMERO_PADRAO = int(os.environ.get('SECULLUM_HORARIO_NUMERO_PADRAO', '6'))


def _horario_para_cargo(cargo: str) -> int:
    """
    Escala Automática: retorna o horarioNumero correto para uso no POST
    de criação do funcionário na Secullum (funciona desde o 1º dia).

    Importa o mapa do módulo de ingestão para manter uma única fonte de verdade.
    Valores None no mapa indicam horários ainda a preencher — usa o padrão.
    """
    try:
        from src.ingestao_secullum import horario_para_cargo
        return horario_para_cargo(cargo)
    except Exception:
        return SECULLUM_HORARIO_NUMERO_PADRAO


def _normalizar_cargo(s: str) -> str:
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', s).strip().upper()


def _at_throttle_headers() -> dict:
    return {'Authorization': f'Bearer {AIRTABLE_API_KEY}', 'Content-Type': 'application/json'}


def _so_digitos(s: str) -> str:
    return re.sub(r'\D', '', s or '')


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ 1. EXTRAÇÃO — regex no header do holerite (testado contra 2 PDFs reais)   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# "347 DAVI LEME DOS SANTOS 517410 1 1"  →  Código Nome CBO Departamento Filial
_RE_CABECALHO_NOME = re.compile(r'^\s*\d+\s+(.+?)\s+\d{6}\s+\d+\s+\d+\s*$', re.MULTILINE)
# "CONTROLADOR DE ACESSO Admissão: 04/05/2026"
_RE_CARGO_ADMISSAO = re.compile(r'^(.+?)\s+Admiss[ãa]o:\s*(\d{2}/\d{2}/\d{4})', re.MULTILINE)
_RE_CPF = re.compile(r'\d{3}\.\d{3}\.\d{3}-\d{2}')
# Não aparece no modelo atual de holerite da Magnata; mantido por completude.
_RE_PIS = re.compile(r'PIS[:\s]*([\d.\-]{11,14})', re.IGNORECASE)


def extrair_dados_holerite(texto: str) -> dict:
    """Extrai Nome, Cargo, Data de Admissão, CPF e PIS do header do holerite.

    Retorna chaves sempre presentes (None quando não encontrado). PIS é
    None no modelo atual de holerite da Magnata — não é falha de regex.
    """
    dados = {'nome': None, 'cargo': None, 'admissao': None, 'cpf': None, 'pis': None}
    m = _RE_CABECALHO_NOME.search(texto)
    if m:
        dados['nome'] = re.sub(r'\s+', ' ', m.group(1)).strip()
    m = _RE_CARGO_ADMISSAO.search(texto)
    if m:
        dados['cargo'] = re.sub(r'\s+', ' ', m.group(1)).strip()
        dados['admissao'] = m.group(2)
    m = _RE_CPF.search(texto)
    if m:
        dados['cpf'] = m.group(0)
    m = _RE_PIS.search(texto)
    if m:
        dados['pis'] = m.group(1)
    return dados


def extrair_texto_pdf(conteudo_bytes: bytes) -> str:
    """Texto da 1ª página do PDF (onde fica o cabeçalho do holerite)."""
    if pdfplumber is None:
        raise RuntimeError('pdfplumber não instalado — adicione ao requirements.txt')
    with pdfplumber.open(io.BytesIO(conteudo_bytes)) as pdf:
        return pdf.pages[0].extract_text() or ''


def listar_holerites_recentes(limit: int = 10) -> list:
    """Lista os N registros mais recentes da tabela Holerites (Created desc).

    Não existe pasta local de insumos nesta arquitetura — os PDFs chegam por
    e-mail/upload e ficam anexados aqui (ver nota no topo do módulo).
    """
    r = requests.get(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_HOL}',
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
        params={
            'pageSize': limit,
            'sort[0][field]': 'Created',
            'sort[0][direction]': 'desc',
            'fields[]': ['PDF HOLERITE', 'Funcionário', 'Folha Mensal'],
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get('records', [])


def processar_holerite_record(rec: dict) -> dict:
    """Baixa o PDF de um registro de Holerites e extrai os dados do header.

    Retorna {'holerite_id', 'arquivo', 'dados': {...}} ou {'erro': ...}.
    """
    fl = rec.get('fields', {})
    anexos = fl.get('PDF HOLERITE') or []
    if not anexos:
        return {'holerite_id': rec['id'], 'erro': 'sem PDF anexado'}
    anexo = anexos[0]
    try:
        resp = requests.get(anexo['url'], timeout=30)
        resp.raise_for_status()
        texto = extrair_texto_pdf(resp.content)
        dados = extrair_dados_holerite(texto)
    except Exception as exc:
        return {'holerite_id': rec['id'], 'arquivo': anexo.get('filename'), 'erro': str(exc)}
    return {'holerite_id': rec['id'], 'arquivo': anexo.get('filename'), 'dados': dados}


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ 2. ESTRUTURAÇÃO — dedup por CPF, cria ou completa no Airtable             ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def buscar_funcionario_por_cpf(cpf: str):
    """Retorna o registro do Funcionário (ou None) casando por CPF.

    O campo CPF no Airtable às vezes guarda com máscara ("397.529.068-42"),
    às vezes só dígitos — por isso tenta também o campo fórmula "num-cpf"
    (sempre normalizado), igual ao padrão já usado em secullum_ponto.py.
    Bug real encontrado em 27/06/2026: passar só dígitos sem esse terceiro
    formato fazia 16/20 CPFs "não encontrados" mesmo existindo no Airtable.
    """
    cpf_num = _so_digitos(cpf)
    for formula in (f'{{CPF}}="{cpf}"', f'{{CPF}}="{cpf_num}"', f'{{num-cpf}}={cpf_num}'):
        r = requests.get(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}',
            headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
            params={'filterByFormula': formula, 'maxRecords': 1},
            timeout=30,
        )
        if r.ok and r.json().get('records'):
            return r.json()['records'][0]
    return None


def criar_ou_completar_funcionario(dados: dict, dry_run: bool = True) -> dict:
    """Cria a linha do Funcionário se o CPF não existir; se existir, só
    completa os campos (Cargo/Admissão/PIS) que estiverem vazios — nunca
    sobrescreve um dado já preenchido manualmente.
    """
    if not dados.get('cpf'):
        return {'status': 'erro', 'motivo': 'CPF não extraído do holerite'}

    existente = buscar_funcionario_por_cpf(dados['cpf'])
    if existente:
        campos_atuais = existente.get('fields', {})
        a_completar = {}
        if not campos_atuais.get('Cargo') and dados.get('cargo'):
            a_completar[F_FUNC_CARGO] = dados['cargo']
        if not campos_atuais.get('Data de Admissão') and dados.get('admissao'):
            dia, mes, ano = dados['admissao'].split('/')
            a_completar[F_FUNC_ADMISSAO] = f'{ano}-{mes}-{dia}'
        if not campos_atuais.get('PIS') and dados.get('pis'):
            a_completar[F_FUNC_PIS] = dados['pis']
        if not a_completar:
            return {'status': 'existente_completo', 'id': existente['id']}
        if dry_run:
            return {'status': 'existente_a_completar', 'id': existente['id'], 'campos': a_completar}
        r = requests.patch(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}/{existente["id"]}',
            headers=_at_throttle_headers(),
            json={'fields': a_completar, 'typecast': True}, timeout=30,
        )
        r.raise_for_status()
        return {'status': 'completado', 'id': existente['id'], 'campos': a_completar}

    campos = {F_FUNC_CPF: dados['cpf'], F_FUNC_STATUS_SYNC: STATUS_PENDENTE}
    if dados.get('nome'):
        campos[F_FUNC_NOME] = dados['nome']
    if dados.get('cargo'):
        campos[F_FUNC_CARGO] = dados['cargo']
    if dados.get('admissao'):
        dia, mes, ano = dados['admissao'].split('/')
        campos[F_FUNC_ADMISSAO] = f'{ano}-{mes}-{dia}'
    if dados.get('pis'):
        campos[F_FUNC_PIS] = dados['pis']

    if dry_run:
        return {'status': 'novo_dry_run', 'campos': campos}
    r = requests.post(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}',
        headers=_at_throttle_headers(),
        json={'fields': campos, 'typecast': True}, timeout=30,
    )
    r.raise_for_status()
    return {'status': 'criado', 'id': r.json()['id'], 'campos': campos}


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ 3. SINCRONIZAÇÃO — Pendente + Grupo de Escala preenchido → Secullum       ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def listar_pendentes_sincronizacao() -> list:
    """Funcionários com Status de Sincronização=Pendente E Grupo de Escala
    preenchido — só esses estão prontos para virar cadastro na Secullum."""
    r = requests.get(
        f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}',
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
        params={
            'filterByFormula':
                f'AND({{Status de Sincronização}}="{STATUS_PENDENTE}", '
                f'{{Grupo de Escala}}!="")',
            'fields[]': ['CPF', 'Nome Completo', 'Código', 'PIS', 'Data de Admissão',
                         'Grupo de Escala'],
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get('records', [])


def sincronizar_lista_cpfs(cpfs: list, dry_run: bool = True) -> list:
    """Sincroniza uma lista explícita de CPFs com a Secullum, sem exigir
    Status de Sincronização="Pendente" nem Grupo de Escala preenchido.

    Uso: saneamento em massa de "invisíveis" (ativos no Airtable, ausentes
    no Ponto Web) — diretriz da diretoria de 27/06/2026. A Secullum exige
    empresaId/funcaoDescricao/departamentoDescricao/horarioNumero para criar
    (erro 400 sem eles); Função/Departamento vêm do Cargo do Airtable via
    `_MAPA_CARGO_SECULLUM`, Horário usa o placeholder
    `SECULLUM_HORARIO_NUMERO_PADRAO` (ajuste fino de escala é etapa
    posterior, deliberadamente separada). Admissão ausente usa a data de
    criação do registro no Airtable como aproximação (decisão da diretoria
    27/06/2026 — não inventa uma data arbitrária, usa a melhor referência
    disponível). Busca o registro do Airtable na hora (dados sempre
    atuais), grava o Id retornado em "Secullum ID" e marca "Sincronizado".
    """
    from src.services.secullum_ponto import sincronizar_funcionario

    resultados = []
    for cpf in cpfs:
        rec = buscar_funcionario_por_cpf(cpf)
        if not rec:
            resultados.append({'cpf': cpf, 'erro': 'CPF não encontrado no Airtable'})
            continue
        fl = rec.get('fields', {})
        nome = fl.get('Nome Completo')
        cargo_norm = _normalizar_cargo(fl.get('Cargo'))
        funcao_desc, departamento_desc = _MAPA_CARGO_SECULLUM.get(cargo_norm, (None, None))
        admissao = fl.get('Data de Admissão') or (rec.get('createdTime') or '')[:10] or None
        admissao_e_proxy = not fl.get('Data de Admissão') and bool(admissao)

        if funcao_desc is None:
            resultados.append({
                'id': rec['id'], 'nome': nome, 'cpf': cpf,
                'erro': f'Cargo "{fl.get("Cargo")}" sem mapeamento conhecido p/ '
                        f'funcaoDescricao/departamentoDescricao (ver _MAPA_CARGO_SECULLUM).',
            })
            continue

        horario_num = _horario_para_cargo(fl.get('Cargo', ''))

        if dry_run:
            resultados.append({
                'id': rec['id'], 'nome': nome, 'cpf': cpf, 'status': 'dry_run',
                'cargo': fl.get('Cargo'), 'funcao_descricao': funcao_desc,
                'departamento_descricao': departamento_desc,
                'horario_numero': horario_num,
                'pis': fl.get('PIS'), 'admissao': admissao, 'admissao_e_proxy': admissao_e_proxy,
            })
            continue
        try:
            resultado = sincronizar_funcionario(
                cpf=cpf, nome=nome, numero=fl.get('Código'),
                pis=fl.get('PIS'), admissao=admissao,
                empresa_id=SECULLUM_EMPRESA_ID, funcao_descricao=funcao_desc,
                departamento_descricao=departamento_desc,
                horario_numero=horario_num,
            )
            secullum_id = resultado.get('funcionario', {}).get('Id')
            r = requests.patch(
                f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}/{rec["id"]}',
                headers=_at_throttle_headers(),
                json={'fields': {
                    F_FUNC_SECULLUM_ID: str(secullum_id) if secullum_id is not None else '',
                    F_FUNC_STATUS_SYNC: STATUS_SINCRONIZADO,
                }, 'typecast': True}, timeout=30,
            )
            r.raise_for_status()
            resultados.append({'id': rec['id'], 'nome': nome, 'cpf': cpf,
                               'status': resultado.get('status'), 'secullum_id': secullum_id,
                               'admissao_e_proxy': admissao_e_proxy})
        except Exception as exc:
            logger.error('[SYNC] Falha sincronizando %s (CPF %s): %s', nome, cpf, exc)
            resultados.append({'id': rec['id'], 'nome': nome, 'cpf': cpf, 'erro': str(exc)})
    return resultados


def sincronizar_pendentes(dry_run: bool = True, limit: int = None) -> list:
    """Envia os Funcionários pendentes (com escala definida) para a Secullum.

    Reaproveita `secullum_ponto.sincronizar_funcionario` (já trata
    cadastro/duplicidade no Ponto Web). Grava o Id retornado em "Secullum ID"
    e muda o status para "Sincronizado".
    """
    from src.services.secullum_ponto import sincronizar_funcionario

    pendentes = listar_pendentes_sincronizacao()
    if limit:
        pendentes = pendentes[:limit]

    resultados = []
    for rec in pendentes:
        fl = rec.get('fields', {})
        cpf = fl.get('CPF')
        nome = fl.get('Nome Completo')
        if dry_run:
            resultados.append({'id': rec['id'], 'nome': nome, 'cpf': cpf, 'status': 'dry_run'})
            continue
        try:
            resultado = sincronizar_funcionario(
                cpf=cpf, nome=nome, numero=fl.get('Código'),
                pis=fl.get('PIS'), admissao=fl.get('Data de Admissão'),
            )
            secullum_id = resultado.get('funcionario', {}).get('Id')
            r = requests.patch(
                f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_FUNC}/{rec["id"]}',
                headers=_at_throttle_headers(),
                json={'fields': {
                    F_FUNC_SECULLUM_ID: str(secullum_id) if secullum_id is not None else '',
                    F_FUNC_STATUS_SYNC: STATUS_SINCRONIZADO,
                }, 'typecast': True}, timeout=30,
            )
            r.raise_for_status()
            resultados.append({'id': rec['id'], 'nome': nome, 'cpf': cpf,
                               'status': resultado.get('status'), 'secullum_id': secullum_id})
        except Exception as exc:
            logger.error('[SYNC] Falha sincronizando %s (CPF %s): %s', nome, cpf, exc)
            resultados.append({'id': rec['id'], 'nome': nome, 'cpf': cpf, 'erro': str(exc)})
    return resultados


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ CLI                                                                        ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

sync_bp = Blueprint('sync_new_employees', __name__, url_prefix='/sync-funcionarios')


@sync_bp.route('/importar-cpfs', methods=['POST', 'OPTIONS'])
def rota_importar_cpfs():
    """Sincroniza uma lista explícita de CPFs com a Secullum (saneamento de
    cadastros "invisíveis" — diretriz da diretoria, 27/06/2026).

    Body JSON: {"cpfs": ["12345678900", ...], "dry_run": true}
    """
    if request.method == 'OPTIONS':
        return ('', 204)
    body = request.get_json(silent=True) or {}
    cpfs = body.get('cpfs') or []
    if not cpfs:
        return jsonify({'erro': 'Informe "cpfs": [lista de CPFs].'}), 400
    try:
        resultados = sincronizar_lista_cpfs(cpfs, dry_run=bool(body.get('dry_run', True)))
        sucesso = [r for r in resultados if not r.get('erro')]
        erro = [r for r in resultados if r.get('erro')]
        return jsonify({
            'total': len(resultados), 'sucesso': len(sucesso), 'erro': len(erro),
            'resultados': resultados,
        }), 200
    except Exception as exc:
        logger.exception('[SYNC] Erro na importação em massa')
        return jsonify({
            'erro': type(exc).__name__, 'detalhe': str(exc),
            'traceback': traceback.format_exc().splitlines()[-8:],
        }), 500


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true', help='Só relata, não grava no Airtable/Secullum.')
    ap.add_argument('--limit', type=int, default=5, help='Quantos holerites recentes processar.')
    ap.add_argument('--cpf', help='Processa só o holerite cujo Funcionário vinculado tem este CPF.')
    ap.add_argument('--sincronizar', action='store_true',
                    help='Também executa a etapa 3 (envio à Secullum) dos pendentes.')
    args = ap.parse_args()

    registros = listar_holerites_recentes(limit=max(args.limit, 20) if args.cpf else args.limit)
    for rec in registros:
        if args.cpf:
            funcs = rec.get('fields', {}).get('Funcionário') or []
            # filtro leve por CPF feito após baixar/extrair (ver loop abaixo)
        resultado = processar_holerite_record(rec)
        dados = resultado.get('dados') or {}
        if args.cpf and _so_digitos(dados.get('cpf', '')) != _so_digitos(args.cpf):
            continue
        print(f"--- {resultado.get('arquivo', resultado['holerite_id'])} ---")
        if resultado.get('erro'):
            print(f"  ERRO: {resultado['erro']}")
            continue
        print(f"  Nome:     {dados.get('nome')}")
        print(f"  CPF:      {dados.get('cpf')}")
        print(f"  Cargo:    {dados.get('cargo')}")
        print(f"  Admissão: {dados.get('admissao')}")
        print(f"  PIS:      {dados.get('pis')} {'(não impresso neste modelo de holerite)' if not dados.get('pis') else ''}")
        resultado_at = criar_ou_completar_funcionario(dados, dry_run=args.dry_run)
        print(f"  Airtable: {resultado_at}")

    if args.sincronizar:
        print('\n--- Sincronização Secullum (pendentes com escala definida) ---')
        for r in sincronizar_pendentes(dry_run=args.dry_run, limit=args.limit):
            print(' ', r)


if __name__ == '__main__':
    main()
