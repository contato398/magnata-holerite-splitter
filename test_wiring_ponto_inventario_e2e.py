"""Prova de composição SINTÉTICA, sem produção (missão "WIRING REAL DA
FOLHA/CARTÃO DE PONTO NO INVENTÁRIO DA PRESTAÇÃO"):

    Documento sintético (modulo01, já existente)
    -> resolução temporal já válida (resolucao_temporal_ponto.py, PR #127)
    -> alocação histórica sintética
    -> FonteInventarioPrestacaoPontoTemporal (novo)
    -> FonteInventarioPrestacaoComposta (já existente, reaproveitada)
    -> readiness (prestacao_readiness.py, já existente, reaproveitado)

Nenhuma escrita real. Nenhum nome real/CPF real."""
import ast
import datetime
import inspect

from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    DimensaoResolucao,
    EntradaResolucaoDocumento,
    EstadoResolucaoDimensao,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    RegraAplicabilidadeDimensao,
    ResolucaoDimensao,
)
from magnata_os.classificacao.fonte_inventario_composta import FonteInventarioPrestacaoComposta
from magnata_os.classificacao.fonte_inventario_prestacao_ponto_temporal import (
    FonteInventarioPrestacaoPontoTemporal,
)
from magnata_os.classificacao.prestacao_readiness import (
    EntradaPrestacaoReadiness,
    EstadoPrestacaoReadiness,
    RequisitoDocumentalPrestacao,
    avaliar_prestacao_readiness,
)
from magnata_os.classificacao.produtores_evidencia_ponto import TIPO_FOLHA_DE_PONTO
from magnata_os.classificacao.resolucao_semantica import compor_resolucao_semantica
from magnata_os.classificacao.resolucao_temporal_ponto import (
    AlocacaoHistorica,
    resolver_documento_ponto,
)

_CLIENTE_A = ReferenciaCanonica('CLIENTE', 'rec_cliente_a_sintetico')
_CLIENTE_B = ReferenciaCanonica('CLIENTE', 'rec_cliente_b_sintetico')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-06')


def resolucao_ancora_simples(cliente, competencia):
    """Mesma forma já usada em `test_magnata_os_classificacao_ciclo_
    prestacao.py::_resolucao_ancora` -- reaproveitada aqui, nunca
    reimplementada com semântica diferente."""
    perfil = PerfilAplicabilidadeResolucao(
        perfil_id='p', version='1', escopo_documental='teste',
        regras=(
            RegraAplicabilidadeDimensao(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
        ),
    )
    return compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id='doc-ancora', hash_sha256='a' * 64, resolver_id='r', resolver_version='1',
            politica_id='p', politica_version='1', contexto_fontes_fingerprint='teste',
        ),
        perfil=perfil,
        resolucoes=(
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(cliente,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(competencia,)),
        ),
    )


def _texto(periodo_inicio_txt, periodo_fim_txt):
    return f'CARTAO DE PONTO\nPeríodo: {periodo_inicio_txt} até {periodo_fim_txt}'


class _FonteAlocacaoEmMemoria:
    def __init__(self, alocacoes):
        self._alocacoes = tuple(alocacoes)

    def listar_para_colaborador(self, colaborador_id):
        return tuple(a for a in self._alocacoes if a.colaborador_id == colaborador_id)


class _FonteResolucoesEmMemoria:
    def __init__(self, resolucoes):
        self._resolucoes = tuple(resolucoes)

    def listar_todos(self):
        return self._resolucoes


class _FonteDocumentosExistentesEmMemoria:
    """Adapter mínimo: um conjunto de documento_id "existentes" --
    equivalente a `RepositorioDocumentos.buscar_por_id(...) is not
    None`, sem precisar instanciar o Documento completo aqui."""

    def __init__(self, documento_ids_existentes):
        self._existentes = frozenset(documento_ids_existentes)

    def existe(self, documento_id: str) -> bool:
        return documento_id in self._existentes


def _montar_fonte(resolucoes, alocacoes, documento_ids_existentes):
    return FonteInventarioPrestacaoPontoTemporal(
        fonte_resolucoes=_FonteResolucoesEmMemoria(resolucoes),
        fonte_alocacao=_FonteAlocacaoEmMemoria(alocacoes),
        fonte_documentos=_FonteDocumentosExistentesEmMemoria(documento_ids_existentes),
    )


# ---------------------------------------------------------------------------
# Caso 1: 1 documento válido / 1 cliente
# ---------------------------------------------------------------------------

def test_caso1_documento_valido_1_cliente_produz_1_item():
    resolucao, _c = resolver_documento_ponto(
        'doc-1', _texto('29/05/2026', '28/06/2026'), 'func-1', _FonteAlocacaoEmMemoria(()),
    )
    alocacoes = (AlocacaoHistorica('func-1', 'rec_cliente_a_sintetico', datetime.date(2026, 1, 1), None),)
    fonte = _montar_fonte([resolucao], alocacoes, {'doc-1'})

    itens = fonte.listar(_CLIENTE_A, _COMPETENCIA)
    assert len(itens) == 1
    item = itens[0]
    assert item.documento_id == 'doc-1'
    assert item.tipo_documental == TIPO_FOLHA_DE_PONTO
    assert item.cliente == _CLIENTE_A
    assert item.competencia == _COMPETENCIA
    assert item.colaborador == ReferenciaCanonica('COLABORADOR', 'func-1')


# ---------------------------------------------------------------------------
# Caso 2: transferência entre 2 clientes dentro do período
# ---------------------------------------------------------------------------

def test_caso2_transferencia_entre_2_clientes_produz_item_para_cada_um_mesmo_documento_id():
    resolucao, _c = resolver_documento_ponto(
        'doc-2', _texto('29/05/2026', '28/06/2026'), 'func-2', _FonteAlocacaoEmMemoria(()),
    )
    alocacoes = (
        AlocacaoHistorica('func-2', 'rec_cliente_a_sintetico', datetime.date(2026, 1, 1), datetime.date(2026, 6, 10)),
        AlocacaoHistorica('func-2', 'rec_cliente_b_sintetico', datetime.date(2026, 6, 11), None),
    )
    fonte = _montar_fonte([resolucao], alocacoes, {'doc-2'})

    itens_a = fonte.listar(_CLIENTE_A, _COMPETENCIA)
    itens_b = fonte.listar(_CLIENTE_B, _COMPETENCIA)
    assert len(itens_a) == 1 and len(itens_b) == 1
    assert itens_a[0].documento_id == itens_b[0].documento_id == 'doc-2'  # mesma identidade fisica, 2 itens logicos


# ---------------------------------------------------------------------------
# Caso 3: documento sem competência resolvida
# ---------------------------------------------------------------------------

def test_caso3_documento_sem_competencia_resolvida_nunca_vira_item():
    resolucao, _c = resolver_documento_ponto(
        'doc-3', 'texto sem periodo declarado', 'func-3', _FonteAlocacaoEmMemoria(()),
    )
    assert resolucao.resolucao_competencia.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    alocacoes = (AlocacaoHistorica('func-3', 'rec_cliente_a_sintetico', datetime.date(2026, 1, 1), None),)
    fonte = _montar_fonte([resolucao], alocacoes, {'doc-3'})

    assert fonte.listar(_CLIENTE_A, _COMPETENCIA) == ()


# ---------------------------------------------------------------------------
# Caso 4: documento em CONFLITO
# ---------------------------------------------------------------------------

def test_caso4_documento_em_conflito_nunca_vira_item_falso_presente():
    resolucao_conflito = _resolucao_conflito('doc-4', 'func-4')
    alocacoes = (AlocacaoHistorica('func-4', 'rec_cliente_a_sintetico', datetime.date(2026, 1, 1), None),)
    fonte = _montar_fonte([resolucao_conflito], alocacoes, {'doc-4'})

    assert fonte.listar(_CLIENTE_A, _COMPETENCIA) == ()


def _resolucao_conflito(documento_id, colaborador_id):
    from magnata_os.classificacao.resolucao_temporal_ponto import ResolucaoDocumentalTemporalPonto
    resolucao_conflito_dim = ResolucaoDimensao(
        dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.CONFLITO,
    )
    return ResolucaoDocumentalTemporalPonto(
        documento_id=documento_id, tipo_documental=TIPO_FOLHA_DE_PONTO, colaborador_id=colaborador_id,
        periodo_inicio=None, periodo_fim=None, resolucao_competencia=resolucao_conflito_dim,
    )


# ---------------------------------------------------------------------------
# Caso 5: colaborador sem alocação
# ---------------------------------------------------------------------------

def test_caso5_colaborador_sem_alocacao_nunca_vira_item():
    resolucao, _c = resolver_documento_ponto(
        'doc-5', _texto('29/05/2026', '28/06/2026'), 'func-5-sem-alocacao', _FonteAlocacaoEmMemoria(()),
    )
    fonte = _montar_fonte([resolucao], (), {'doc-5'})
    assert fonte.listar(_CLIENTE_A, _COMPETENCIA) == ()


# ---------------------------------------------------------------------------
# Caso 6: resolução inexistente
# ---------------------------------------------------------------------------

def test_caso6_nenhuma_resolucao_persistida_produz_inventario_vazio():
    fonte = _montar_fonte([], (), set())
    assert fonte.listar(_CLIENTE_A, _COMPETENCIA) == ()


# ---------------------------------------------------------------------------
# Caso 7: documento inexistente (resolução órfã)
# ---------------------------------------------------------------------------

def test_caso7_resolucao_com_documento_inexistente_nunca_vira_item():
    resolucao, _c = resolver_documento_ponto(
        'doc-7-orfao', _texto('29/05/2026', '28/06/2026'), 'func-7', _FonteAlocacaoEmMemoria(()),
    )
    alocacoes = (AlocacaoHistorica('func-7', 'rec_cliente_a_sintetico', datetime.date(2026, 1, 1), None),)
    # documento_ids_existentes VAZIO -- resolução aponta para um Documento que nao existe
    fonte = _montar_fonte([resolucao], alocacoes, set())
    assert fonte.listar(_CLIENTE_A, _COMPETENCIA) == ()


# ---------------------------------------------------------------------------
# Caso 8: reprocessamento equivalente não duplica item
# ---------------------------------------------------------------------------

def test_caso8_resolucao_repetida_na_listagem_nunca_duplica_item():
    """Simula 2 leituras do mesmo estado persistido (idempotência a
    montante, PR #127) -- a fonte de inventário, dado o MESMO conjunto
    de resoluções, nunca produz itens duplicados."""
    resolucao, _c = resolver_documento_ponto(
        'doc-8', _texto('29/05/2026', '28/06/2026'), 'func-8', _FonteAlocacaoEmMemoria(()),
    )
    alocacoes = (AlocacaoHistorica('func-8', 'rec_cliente_a_sintetico', datetime.date(2026, 1, 1), None),)
    fonte = _montar_fonte([resolucao], alocacoes, {'doc-8'})  # 1 unica resolucao persistida (UNIQUE(documento_id))

    itens_1 = fonte.listar(_CLIENTE_A, _COMPETENCIA)
    itens_2 = fonte.listar(_CLIENTE_A, _COMPETENCIA)
    assert len(itens_1) == 1
    assert itens_1 == itens_2


# ---------------------------------------------------------------------------
# Caso 9: ordem determinística
# ---------------------------------------------------------------------------

def test_caso9_ordem_deterministica_entre_multiplos_documentos():
    resolucao_z, _ = resolver_documento_ponto('doc-z', _texto('29/05/2026', '28/06/2026'), 'func-9a', _FonteAlocacaoEmMemoria(()))
    resolucao_a, _ = resolver_documento_ponto('doc-a', _texto('29/05/2026', '28/06/2026'), 'func-9b', _FonteAlocacaoEmMemoria(()))
    alocacoes = (
        AlocacaoHistorica('func-9a', 'rec_cliente_a_sintetico', datetime.date(2026, 1, 1), None),
        AlocacaoHistorica('func-9b', 'rec_cliente_a_sintetico', datetime.date(2026, 1, 1), None),
    )
    fonte_ordem_1 = _montar_fonte([resolucao_z, resolucao_a], alocacoes, {'doc-z', 'doc-a'})
    fonte_ordem_2 = _montar_fonte([resolucao_a, resolucao_z], alocacoes, {'doc-z', 'doc-a'})

    itens_1 = fonte_ordem_1.listar(_CLIENTE_A, _COMPETENCIA)
    itens_2 = fonte_ordem_2.listar(_CLIENTE_A, _COMPETENCIA)
    assert [i.documento_id for i in itens_1] == ['doc-a', 'doc-z']  # sempre ordenado por documento_id
    assert itens_1 == itens_2


# ---------------------------------------------------------------------------
# Caso 10: composição com outra fonte já existente (FonteInventarioPrestacaoComposta)
# ---------------------------------------------------------------------------

class _FonteInventarioExtraSintetica:
    """Fonte sintética simples do MESMO Protocol (FonteInventarioPrestacao)
    -- simula uma família documental já existente (ex.: Extrato),
    provando que a fonte nova compõe sem alteração no contrato central."""

    def listar(self, cliente, competencia):
        from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
        if cliente != _CLIENTE_A or competencia != _COMPETENCIA:
            return ()
        return (ItemInventarioPrestacao(
            documento_id='doc-extrato-sintetico', tipo_documental='Extrato da Folha de Pagamento',
            cliente=cliente, competencia=competencia,
        ),)


def test_caso10_compoe_com_fonte_inventario_prestacao_composta_sem_alterar_contrato():
    resolucao, _c = resolver_documento_ponto(
        'doc-10', _texto('29/05/2026', '28/06/2026'), 'func-10', _FonteAlocacaoEmMemoria(()),
    )
    alocacoes = (AlocacaoHistorica('func-10', 'rec_cliente_a_sintetico', datetime.date(2026, 1, 1), None),)
    fonte_ponto = _montar_fonte([resolucao], alocacoes, {'doc-10'})
    fonte_composta = FonteInventarioPrestacaoComposta((fonte_ponto, _FonteInventarioExtraSintetica()))

    itens = fonte_composta.listar(_CLIENTE_A, _COMPETENCIA)
    tipos = {item.tipo_documental for item in itens}
    assert TIPO_FOLHA_DE_PONTO in tipos
    assert 'Extrato da Folha de Pagamento' in tipos
    assert len(itens) == 2


# ---------------------------------------------------------------------------
# Caso 11: readiness continua usando o motor existente
# ---------------------------------------------------------------------------

def test_caso11_readiness_usa_o_motor_existente_pacote_pronto_com_ponto_presente():
    resolucao, _c = resolver_documento_ponto(
        'doc-11', _texto('29/05/2026', '28/06/2026'), 'func-11', _FonteAlocacaoEmMemoria(()),
    )
    alocacoes = (AlocacaoHistorica('func-11', 'rec_cliente_a_sintetico', datetime.date(2026, 1, 1), None),)
    fonte = _montar_fonte([resolucao], alocacoes, {'doc-11'})
    inventario = fonte.listar(_CLIENTE_A, _COMPETENCIA)

    resultado = avaliar_prestacao_readiness(EntradaPrestacaoReadiness(
        cliente=_CLIENTE_A, competencia=_COMPETENCIA,
        requisitos=(RequisitoDocumentalPrestacao(tipo_documental=TIPO_FOLHA_DE_PONTO, quantidade_minima=1),),
        inventario=inventario,
        resolucao=resolucao_ancora_simples(_CLIENTE_A, _COMPETENCIA),
    ))
    assert resultado.estado == EstadoPrestacaoReadiness.PRONTO
    assert TIPO_FOLHA_DE_PONTO not in resultado.tipos_faltantes


def test_caso11b_readiness_marca_faltando_quando_ponto_ausente():
    resultado = avaliar_prestacao_readiness(EntradaPrestacaoReadiness(
        cliente=_CLIENTE_A, competencia=_COMPETENCIA,
        requisitos=(RequisitoDocumentalPrestacao(tipo_documental=TIPO_FOLHA_DE_PONTO, quantidade_minima=1),),
        inventario=(),
        resolucao=resolucao_ancora_simples(_CLIENTE_A, _COMPETENCIA),
    ))
    assert resultado.estado == EstadoPrestacaoReadiness.FALTANDO
    assert TIPO_FOLHA_DE_PONTO in resultado.tipos_faltantes


# ---------------------------------------------------------------------------
# Caso 12: nenhum item fabricado quando a resolução é insuficiente
# (já coberto pelos casos 3, 4, 5, 7 -- reafirmado aqui de forma agregada)
# ---------------------------------------------------------------------------

def test_caso12_nenhum_item_fabricado_para_qualquer_resolucao_insuficiente():
    sem_competencia, _ = resolver_documento_ponto('doc-12a', 'sem periodo', 'func-12a', _FonteAlocacaoEmMemoria(()))
    conflito = _resolucao_conflito('doc-12b', 'func-12b')
    sem_alocacao, _ = resolver_documento_ponto('doc-12c', _texto('29/05/2026', '28/06/2026'), 'func-12c-sem-alocacao', _FonteAlocacaoEmMemoria(()))
    orfao, _ = resolver_documento_ponto('doc-12d', _texto('29/05/2026', '28/06/2026'), 'func-12d', _FonteAlocacaoEmMemoria(()))
    alocacoes = (AlocacaoHistorica('func-12d', 'rec_cliente_a_sintetico', datetime.date(2026, 1, 1), None),)

    fonte = _montar_fonte(
        [sem_competencia, conflito, sem_alocacao, orfao], alocacoes,
        {'doc-12a', 'doc-12b', 'doc-12c'},  # doc-12d (orfao) deliberadamente ausente
    )
    assert fonte.listar(_CLIENTE_A, _COMPETENCIA) == ()


# ---------------------------------------------------------------------------
# Casos 13-15: isolamento (AST)
# ---------------------------------------------------------------------------

def test_caso13_14_15_nucleo_novo_nunca_importa_airtable_app_py_ou_hardcoda_sky():
    import magnata_os.classificacao.fonte_inventario_prestacao_ponto_temporal as modulo
    codigo_fonte = inspect.getsource(modulo)
    arvore = ast.parse(codigo_fonte)

    for no in ast.walk(arvore):
        if isinstance(no, (ast.Import, ast.ImportFrom)):
            nomes = [no.module] if isinstance(no, ast.ImportFrom) else [a.name for a in no.names]
            for nome in nomes:
                if not nome:
                    continue
                proibido = nome.lower() == 'requests' or 'airtable' in nome.lower() or nome == 'app' or nome.startswith('app.')
                assert not proibido, f'import proibido: {nome!r}'

    nos_de_docstring = {
        id(no.value) for no in ast.walk(arvore)
        if isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant) and isinstance(no.value.value, str)
    }
    literais = {
        no.value.lower() for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in nos_de_docstring
    }
    for termo in ('sky', 'tatui'):
        achados = {s for s in literais if termo in s}
        assert not achados, f'termo proibido em literal de codigo: {termo!r} em {achados!r}'
