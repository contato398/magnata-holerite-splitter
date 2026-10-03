"""Blueprint Flask da API de esteira (Modulo 01, Fase 4 -> exposicao
HTTP, Fase 5 "dados reais").

Este e o adapter web que o docstring de handlers.py ja previa ("um
adapter web futuro e quem traduz HTTP <-> estes tipos") -- traduz
querystring <-> filtros.py, JSON <-> contratos.py (via serializacao.py),
e sessao HTTP <-> Sujeito (via
magnata_os.autenticacao.adapters.blueprint_login.exigir_sessao_com_perfil,
o MESMO mecanismo ja usado por auth_bp -- nenhuma autenticacao nova
inventada aqui).

Registrado em app.py com o MESMO padrao ja usado por auth_bp/
secullum_bp/sync_bp/ingestao_bp: import + register_blueprint, nada mais
-- nenhuma logica de negocio entra em app.py.

Fonte dos dados: `RepositorioDocumentosPostgres`/`RepositorioHistoricoPostgres`/
`RepositorioLotesPostgres`/`RepositorioEstadosEsteiraPostgres` (adapters
Postgres ja existentes, Fase 2/3), abertos via
`magnata_os.documental.modulo01.adapters.conexao.abrir_conexao` (le
DATABASE_URL do ambiente). Se DATABASE_URL nao estiver configurada, o
blueprint responde 503 com um erro explicito -- NUNCA inventa dado
sintetico/mockado para parecer que ha dados reais quando nao ha (ver
`/CLAUDE.md` §4, "falha nunca e silenciosa").

`obter_contexto_api` e injetavel (`_fabrica_contexto`) -- todo teste
deste modulo injeta repositorios em memoria, nunca depende de
Postgres/psycopg de verdade nem de rede.
"""
from __future__ import annotations

from typing import Callable, Optional

from flask import Blueprint, jsonify, request

from magnata_os.autenticacao.adapters.blueprint_login import exigir_csrf, exigir_sessao_com_perfil
from magnata_os.autenticacao.identidade import Perfil

from ..dominio_esteira import EtapaEsteira, SituacaoEsteira
from ..repositorio import RepositorioDocumentosEmMemoria, RepositorioHistoricoEmMemoria
from ..repositorio_esteira import RepositorioEstadosEsteiraEmMemoria, RepositorioLotesEmMemoria
from .api_contexto import (
    ConfiguracaoBancoAusente,
    FalhaConexaoBanco,
    montar_contexto_api_postgres,
)
from ..api import handlers
from ..api.erros import ApiError, ErroInternoNaoExposto, tratar_erro_para_resposta
from ..api.filtros import FiltroDocumentos, FiltroLotes, Ordenacao, Paginacao
from ..api.serializacao import para_json

# Ingestao em lote (painel operacional, "eliminar dependencia de Shell/
# terminal") -- nucleo e composicao de dependencias reais vivem em
# `importacao_lote/servico_ingestao_lote_http.py` (mesmo modulo do
# nucleo de ingestao em si, PR #221); esta rota so traduz HTTP <-> essa
# funcao, igual a todas as outras rotas deste blueprint traduzem HTTP
# <-> handlers.py. Ver docs/decisoes/painel-ingestao-documentos-lote-ui-v1.md.
from magnata_os.documental.importacao_lote.servico_ingestao_lote_http import (
    executar_ingestao_lote_http,
)

esteira_bp = Blueprint('magnata_os_documental_esteira', __name__, url_prefix='/magnata-os/documental')

# Todo perfil autenticado pode ao menos tentar cada endpoint -- quem
# decide o perfil MINIMO necessario por consulta e o proprio handler
# (exigir_perfil dentro de handlers.py, PERMISSAO_LEITURA_GERAL /
# PERMISSAO_FILA_OPERACIONAL / PERMISSAO_AUDITORIA). Aqui, na borda
# HTTP, so exigimos "sessao valida, qualquer perfil conhecido" -- nunca
# duplicamos a regra fina de novo (fonte unica: handlers.py).
_QUALQUER_PERFIL_AUTENTICADO = frozenset({Perfil.OPERACIONAL, Perfil.GESTOR, Perfil.AUDITOR})

# Contexto de teste/desenvolvimento (repositorios em memoria, sempre
# vazios) -- usado SOMENTE se _fabrica_contexto for explicitamente
# trocada por um teste; em producao real, `obter_contexto_api` sempre
# tenta Postgres primeiro.
_contexto_em_memoria = None


def _contexto_padrao_em_memoria():
    global _contexto_em_memoria
    if _contexto_em_memoria is None:
        _contexto_em_memoria = handlers.ContextoApi(
            repositorio_documentos=RepositorioDocumentosEmMemoria(),
            repositorio_historico=RepositorioHistoricoEmMemoria(),
            repositorio_lotes=RepositorioLotesEmMemoria(),
            repositorio_estados=RepositorioEstadosEsteiraEmMemoria(),
        )
    return _contexto_em_memoria


# Injetavel por teste: `esteira_bp` nao guarda estado de fabrica em
# modulo global mutavel exceto este ponto unico, documentado.
_fabrica_contexto: Callable[[], handlers.ContextoApi] = None


def configurar_fabrica_contexto(fabrica: Optional[Callable[[], handlers.ContextoApi]]) -> None:
    """Troca a fabrica de ContextoApi usada por toda rota deste
    blueprint. `None` restaura o comportamento padrao (Postgres real via
    DATABASE_URL, com fallback em memoria SEM dados -- nunca dado
    fabricado -- se DATABASE_URL nao estiver configurada). Usado por
    testes; producao nunca chama isto."""
    global _fabrica_contexto
    _fabrica_contexto = fabrica


class BancoNaoConfigurado(ApiError):
    """DATABASE_URL ausente -- a API nao tem de onde ler dado real.
    Nunca degradamos para dado mockado/sintetico nesta resposta: o
    cliente recebe um erro explicito, nunca um "200 vazio" que pareca
    ausencia real de documentos."""

    codigo = 'BANCO_NAO_CONFIGURADO'
    status_http = 503


def obter_contexto_api() -> handlers.ContextoApi:
    if _fabrica_contexto is not None:
        return _fabrica_contexto()
    try:
        return montar_contexto_api_postgres()
    except ConfiguracaoBancoAusente as exc:
        raise BancoNaoConfigurado(
            'DATABASE_URL nao configurada -- sem banco Postgres real conectado, '
            'a API nao expoe nenhum dado (nunca mockado).'
        ) from exc
    except FalhaConexaoBanco as exc:
        raise ErroInternoNaoExposto() from exc


def _resposta_erro(erro: ApiError):
    corpo = tratar_erro_para_resposta(erro)
    return jsonify(para_json(corpo)), erro.status_http


def _int_query(nome: str, padrao: int) -> int:
    valor = request.args.get(nome)
    if valor is None or valor == '':
        return padrao
    try:
        return int(valor)
    except ValueError:
        from ..api.erros import FiltroInvalido
        raise FiltroInvalido(f'{nome} precisa ser um inteiro (recebido: {valor!r}).')


def _float_query(nome: str, padrao: Optional[float] = None) -> Optional[float]:
    valor = request.args.get(nome)
    if valor is None or valor == '':
        return padrao
    try:
        return float(valor)
    except ValueError:
        from ..api.erros import FiltroInvalido
        raise FiltroInvalido(f'{nome} precisa ser numerico (recebido: {valor!r}).')


def _bool_query(nome: str) -> Optional[bool]:
    valor = request.args.get(nome)
    if valor is None or valor == '':
        return None
    if valor.lower() in ('1', 'true', 'verdadeiro'):
        return True
    if valor.lower() in ('0', 'false', 'falso'):
        return False
    from ..api.erros import FiltroInvalido
    raise FiltroInvalido(f'{nome} precisa ser booleano (recebido: {valor!r}).')


def _enum_query(nome: str, enum_cls):
    valor = request.args.get(nome)
    if valor is None or valor == '':
        return None
    try:
        return enum_cls(valor)
    except ValueError:
        from ..api.erros import FiltroInvalido
        permitidos = ', '.join(item.value for item in enum_cls)
        raise FiltroInvalido(f'{nome} invalido: {valor!r} (permitido: {permitidos}).')


def _paginacao_da_querystring() -> Paginacao:
    return Paginacao(
        pagina=_int_query('pagina', Paginacao().pagina),
        tamanho_pagina=_int_query('tamanho_pagina', Paginacao().tamanho_pagina),
    )


def _ordenacao_da_querystring(campo_padrao: str, direcao_padrao: str) -> Ordenacao:
    return Ordenacao(
        campo=request.args.get('ordenar_por', campo_padrao),
        direcao=request.args.get('direcao', direcao_padrao),
    )


def _filtro_documentos_da_querystring() -> FiltroDocumentos:
    return FiltroDocumentos(
        etapa=_enum_query('etapa', EtapaEsteira),
        situacao=_enum_query('situacao', SituacaoEsteira),
        lote_id=request.args.get('lote_id') or None,
        origem=request.args.get('origem') or None,
        bloqueado=_bool_query('bloqueado'),
        acao_humana=_bool_query('acao_humana'),
        tempo_minimo_parado_segundos=_float_query('tempo_minimo_parado_segundos'),
    )


def _filtro_lotes_da_querystring() -> FiltroLotes:
    return FiltroLotes(
        origem=request.args.get('origem') or None,
        situacao=_enum_query('situacao', SituacaoEsteira),
    )


@esteira_bp.route('/esteira/resumo', methods=['GET'])
@exigir_sessao_com_perfil(_QUALQUER_PERFIL_AUTENTICADO)
def resumo_esteira(sujeito):
    try:
        limite = _float_query('limite_parado_segundos', handlers.LIMITE_PARADO_PADRAO_SEGUNDOS)
        resultado = handlers.obter_resumo_esteira(obter_contexto_api(), sujeito, limite)
    except ApiError as erro:
        return _resposta_erro(erro)
    return jsonify(para_json(resultado)), 200


@esteira_bp.route('/lotes', methods=['GET'])
@exigir_sessao_com_perfil(_QUALQUER_PERFIL_AUTENTICADO)
def lotes(sujeito):
    try:
        resultado = handlers.listar_lotes(
            obter_contexto_api(), sujeito,
            filtro=_filtro_lotes_da_querystring(),
            paginacao=_paginacao_da_querystring(),
            ordenacao=_ordenacao_da_querystring('criado_em', 'desc'),
        )
    except ApiError as erro:
        return _resposta_erro(erro)
    return jsonify(para_json(resultado)), 200


@esteira_bp.route('/lotes/<lote_id>', methods=['GET'])
@exigir_sessao_com_perfil(_QUALQUER_PERFIL_AUTENTICADO)
def lote(sujeito, lote_id):
    try:
        resultado = handlers.obter_lote(obter_contexto_api(), sujeito, lote_id)
    except ApiError as erro:
        return _resposta_erro(erro)
    return jsonify(para_json(resultado)), 200


@esteira_bp.route('/documentos', methods=['GET'])
@exigir_sessao_com_perfil(_QUALQUER_PERFIL_AUTENTICADO)
def documentos(sujeito):
    try:
        resultado = handlers.listar_documentos(
            obter_contexto_api(), sujeito,
            filtro=_filtro_documentos_da_querystring(),
            paginacao=_paginacao_da_querystring(),
            ordenacao=_ordenacao_da_querystring('atualizado_em', 'desc'),
        )
    except ApiError as erro:
        return _resposta_erro(erro)
    return jsonify(para_json(resultado)), 200


@esteira_bp.route('/documentos/<documento_id>', methods=['GET'])
@exigir_sessao_com_perfil(_QUALQUER_PERFIL_AUTENTICADO)
def documento(sujeito, documento_id):
    try:
        resultado = handlers.obter_documento(obter_contexto_api(), sujeito, documento_id)
    except ApiError as erro:
        return _resposta_erro(erro)
    return jsonify(para_json(resultado)), 200


@esteira_bp.route('/documentos/<documento_id>/historico', methods=['GET'])
@exigir_sessao_com_perfil(_QUALQUER_PERFIL_AUTENTICADO)
def historico_documento(sujeito, documento_id):
    try:
        resultado = handlers.obter_historico_documento(obter_contexto_api(), sujeito, documento_id)
    except ApiError as erro:
        return _resposta_erro(erro)
    return jsonify(para_json(resultado)), 200


@esteira_bp.route('/bloqueios', methods=['GET'])
@exigir_sessao_com_perfil(_QUALQUER_PERFIL_AUTENTICADO)
def bloqueios(sujeito):
    try:
        resultado = handlers.listar_bloqueios(
            obter_contexto_api(), sujeito,
            paginacao=_paginacao_da_querystring(),
            ordenacao=_ordenacao_da_querystring('tempo_bloqueado_segundos', 'desc'),
        )
    except ApiError as erro:
        return _resposta_erro(erro)
    return jsonify(para_json(resultado)), 200


@esteira_bp.route('/acoes-humanas', methods=['GET'])
@exigir_sessao_com_perfil(_QUALQUER_PERFIL_AUTENTICADO)
def acoes_humanas(sujeito):
    try:
        resultado = handlers.listar_acoes_humanas(
            obter_contexto_api(), sujeito,
            paginacao=_paginacao_da_querystring(),
            ordenacao=_ordenacao_da_querystring('atualizado_em', 'desc'),
        )
    except ApiError as erro:
        return _resposta_erro(erro)
    return jsonify(para_json(resultado)), 200


@esteira_bp.route('/parados', methods=['GET'])
@exigir_sessao_com_perfil(_QUALQUER_PERFIL_AUTENTICADO)
def parados(sujeito):
    try:
        tempo_minimo = _float_query('tempo_minimo_segundos', 0.0) or 0.0
        resultado = handlers.listar_documentos_parados(
            obter_contexto_api(), sujeito, tempo_minimo,
            paginacao=_paginacao_da_querystring(),
            ordenacao=_ordenacao_da_querystring('entrou_na_etapa_em', 'asc'),
        )
    except ApiError as erro:
        return _resposta_erro(erro)
    return jsonify(para_json(resultado)), 200


@esteira_bp.route('/ingestao-lote', methods=['POST'])
@exigir_sessao_com_perfil(_QUALQUER_PERFIL_AUTENTICADO)
@exigir_csrf
def ingestao_lote(sujeito):
    """Dispara, a partir de um clique no painel (nunca do Shell/
    terminal -- decisao de produto, ver docs/decisoes/
    painel-ingestao-documentos-lote-ui-v1.md), a MESMA ingestao real em
    lote do PR #221 (`scripts/ingerir_documentos_lote_real_cli.py`),
    para 1 cliente + 1 competencia. Primeira rota de ESCRITA deste
    blueprint -- por isso e a primeira a usar `exigir_csrf` (mecanismo
    ja existente em blueprint_login.py, nunca antes aplicado; GET
    continua sem CSRF, convencao padrao).

    SINCRONA E BLOQUEANTE (limitacao declarada, aceita para V1): a
    resposta HTTP so volta quando TODOS os documentos do cliente+
    competencia tiverem sido processados -- pode demorar minutos para
    um lote grande. Nenhum worker assincrono/fila foi construido nesta
    missao."""
    corpo = request.get_json(silent=True) or {}
    cliente_id = corpo.get('cliente')
    competencia_base = corpo.get('competencia')
    try:
        resultado = executar_ingestao_lote_http(sujeito, cliente_id, competencia_base)
    except ApiError as erro:
        return _resposta_erro(erro)
    return jsonify(resultado), 200
