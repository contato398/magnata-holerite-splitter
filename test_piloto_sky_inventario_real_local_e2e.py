"""Primeiro piloto COMPLETO do SKY Tatuí, local, com FIXTURES que
reproduzem o schema REAL já confirmado por leitura live (missão
"INVENTÁRIO DOCUMENTAL REAL DA PRESTAÇÃO + PREPARAÇÃO DO PRIMEIRO
PILOTO COMPLETO SKY", Fase 10). NENHUMA leitura live do Airtable
acontece aqui -- os "leitores" são fakes locais cujos dados imitam
exatamente os IDs de tabela/campo e o formato "Folha Mensal" já
confirmados live (ver docs/decisoes/piloto-real-prestacao-readonly-v1.md).

Prova, ponta-a-ponta:
  inventário (fonte composta: Extrato+FGTS+DCTF + Holerites)
  → readiness
  → Holerite por CARDINALIDADE colaborador (nunca contagem plana)
  → faltantes
  → pacote lógico

Cenário: 7 colaboradores esperados (o mesmo número confirmado live para
o cliente real SKY Tatuí), 6 Holerites presentes, 1 ausente -> pacote
INCOMPLETO. Base documental (Extrato/FGTS/DCTF) completa na competência
EFETIVA do SKY (base - 1 mês, regra inalterada).

LIMITAÇÃO TEMPORAL (Fase 11 da missão): os "colaboradores esperados"
usados aqui refletem o SNAPSHOT ATUAL confirmado por leitura live --
nunca tratado como certeza histórica para uma competência passada. Este
piloto roda com a MESMA composição para ambas competências (base e
SKY-deslocada) só porque nenhuma fonte de histórico existe -- registrado
como limitação, nunca escondido (ver ADR)."""
from magnata_os.classificacao.cadastro_requisitos_prestacao import (
    CADASTRO_REQUISITOS_PRESTACAO_V2,
)
from magnata_os.classificacao.ciclo_prestacao import executar_ciclo_prestacao
from magnata_os.classificacao.competencia_esperada_prestacao import (
    POLITICA_COMPETENCIA_PRESTACAO_V1,
    REFERENCIA_CLIENTE_SKY_TATUI,
    ContextoCicloPrestacao,
)
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
from magnata_os.classificacao.pacote_prestacao import EstadoPacotePrestacao
from magnata_os.classificacao.resolucao_semantica import compor_resolucao_semantica
from magnata_os.documental.importacao_lote.adapters.airtable_clientes_prestacao import (
    F_CLI_STATUS,
    FonteClientesPrestacaoAirtable,
)
from magnata_os.documental.importacao_lote.adapters.airtable_colaboradores_esperados_prestacao import (
    F_FUNC_STATUS,
    FonteColaboradoresEsperadosPrestacaoAirtableShadow,
)
from magnata_os.documental.importacao_lote.adapters.airtable_holerites_prestacao import (
    F_HOL_FUNC,
    TABLE_HOL,
    FonteInventarioHoleritesAirtableShadow,
)
from magnata_os.documental.importacao_lote.adapters.airtable_inventario_prestacao import (
    F_FGTS_CLIENTE,
    F_GUIA_TIPO,
    TABLE_FGTS,
    TABLE_GUIAS,
    FonteInventarioPrestacaoAirtableShadow,
)
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import (
    F_EXT_CLIENTE,
    TABLE_CLIENTES,
    TABLE_EXTRATO,
    TABLE_FUNC,
)
from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import (
    F_FUNC_LOCAIS,
    F_LOCAL_CLIENTE,
    TABLE_LOCAIS,
    FonteVinculosPrestacaoAirtableShadow,
)

_SKY = REFERENCIA_CLIENTE_SKY_TATUI  # recrqv5NvbC37WfSl -- mesmo id já confirmado live
_LOCAL_SKY = 'recV7A0c5mD96MD3O'  # mesmo Local real já confirmado live ("SKY RESIDENCE")
_CONTEXTO = ContextoCicloPrestacao(competencia_base=(2026, 7))
_COMPETENCIA_BASE = ReferenciaCanonica('COMPETENCIA', '2026-07')
_COMPETENCIA_SKY = ReferenciaCanonica('COMPETENCIA', '2026-06')  # base - 1 mês

_COLABORADORES = tuple(ReferenciaCanonica('COLABORADOR', f'rec_func_{i}') for i in range(7))


class _LeitorAirtableFake:
    """Um único fake reproduzindo TODAS as tabelas do schema real já
    confirmado live -- nunca uma chamada de rede."""

    def __init__(self, tabelas: dict):
        self._tabelas = tabelas
        self.chamadas = []

    def listar_registros(self, table_id, fields, filter_by_formula=None):
        self.chamadas.append((table_id, tuple(fields), filter_by_formula))
        return self._tabelas.get(table_id, [])


def _montar_leitor():
    tabelas = {
        TABLE_CLIENTES: [{'id': _SKY.entidade_id, 'fields': {F_CLI_STATUS: 'Ativo'}}],
        TABLE_LOCAIS: [{'id': _LOCAL_SKY, 'fields': {F_LOCAL_CLIENTE: [_SKY.entidade_id]}}],
        TABLE_FUNC: [
            {'id': c.entidade_id, 'fields': {F_FUNC_LOCAIS: [_LOCAL_SKY], F_FUNC_STATUS: 'Ativo'}}
            for c in _COLABORADORES
        ],
        # Base documental completa na competência EFETIVA do SKY (Junho 2026).
        TABLE_EXTRATO: [{'id': 'rec_extrato_sky', 'fields': {F_EXT_CLIENTE: [_SKY.entidade_id]}}],
        TABLE_FGTS: [{'id': 'rec_fgts_sky', 'fields': {F_FGTS_CLIENTE: [_SKY.entidade_id]}}],
        TABLE_GUIAS: [
            {'id': 'rec_dctf_declaracao', 'fields': {F_GUIA_TIPO: 'DCTFWeb - Declaração'}},
            {'id': 'rec_dctf_recibo', 'fields': {F_GUIA_TIPO: 'DCTFWeb - Recibo de Entrega'}},
            {'id': 'rec_guia_dctf_darf', 'fields': {F_GUIA_TIPO: 'Guia DCTFWeb/DARF'}},
        ],
        # 6 dos 7 colaboradores esperados têm Holerite -- 1 ausente, de propósito.
        TABLE_HOL: [
            {'id': f'rec_holerite_{i}', 'fields': {F_HOL_FUNC: [c.entidade_id]}}
            for i, c in enumerate(_COLABORADORES[:6])
        ],
    }
    return _LeitorAirtableFake(tabelas)


def _perfil_ancora():
    return PerfilAplicabilidadeResolucao(
        perfil_id='ancora-sky-v1', version='1', escopo_documental='prestacao-contas',
        regras=(
            RegraAplicabilidadeDimensao(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
        ),
    )


def _resolucao_ancora_sky():
    return compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id='ancora-sky', hash_sha256='a' * 64, resolver_id='piloto-sky-e2e',
            resolver_version='1', politica_id='ancora-sky-v1', politica_version='1',
            contexto_fontes_fingerprint='piloto-sky-inventario-real-local',
        ),
        perfil=_perfil_ancora(),
        resolucoes=(
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(_SKY,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(_COMPETENCIA_SKY,)),
        ),
    )


class _FonteClientesSoSky:
    def listar_ativos(self, contexto):
        return (_SKY,)


class _FonteRequisitosVazia:
    def registros_para(self, cliente, contexto):
        return ()


def test_piloto_sky_completo_local_com_schema_real_via_fixtures():
    leitor = _montar_leitor()
    fonte_clientes = FonteClientesPrestacaoAirtable(leitor)
    fonte_vinculos = FonteVinculosPrestacaoAirtableShadow(leitor)
    fonte_colaboradores_esperados = FonteColaboradoresEsperadosPrestacaoAirtableShadow(leitor)
    fonte_inventario = FonteInventarioPrestacaoComposta((
        FonteInventarioPrestacaoAirtableShadow(leitor),
        FonteInventarioHoleritesAirtableShadow(leitor, fonte_vinculos),
    ))

    # ---- Fonte de clientes real (corrigida nesta missão) confirma SKY Ativo ----
    assert fonte_clientes.listar_ativos(_CONTEXTO) == (_SKY,)

    # ---- Colaboradores esperados reais (mesma contagem já confirmada live: 7) ----
    esperados = fonte_colaboradores_esperados.colaboradores_esperados_para(_SKY, _CONTEXTO)
    assert set(esperados) == set(_COLABORADORES)
    assert len(esperados) == 7

    # ---- Competência efetiva do SKY: base - 1 mês (regra inalterada) ----
    competencia_esperada_sky = POLITICA_COMPETENCIA_PRESTACAO_V1.competencia_esperada_para(
        _CONTEXTO, _SKY, 'FGTS')
    assert competencia_esperada_sky == (2026, 6)

    # ---- Inventário agregado (composto) na competência EFETIVA ----
    itens = fonte_inventario.listar(_SKY, _COMPETENCIA_SKY)
    tipos_presentes = {item.tipo_documental for item in itens}
    assert tipos_presentes == {
        'Extrato da Folha de Pagamento', 'FGTS',
        'DCTFWeb - Declaração', 'DCTFWeb - Recibo de Entrega', 'Guia DCTFWeb/DARF',
        'Holerite',
    }
    holerites = [item for item in itens if item.tipo_documental == 'Holerite']
    assert len(holerites) == 6
    assert all(item.colaborador is not None for item in holerites)

    # ---- Ciclo completo: readiness + Holerite por cardinalidade + pacote ----
    resultado_ciclo = executar_ciclo_prestacao(
        contexto=_CONTEXTO,
        fonte_clientes=fonte_clientes,
        fonte_requisitos=_FonteRequisitosVazia(),
        fonte_inventario=fonte_inventario,
        requisitos_base=CADASTRO_REQUISITOS_PRESTACAO_V2.requisitos_base_documentais(),
        resolucoes_ancora={_SKY: _resolucao_ancora_sky()},
        competencias_por_cliente={_SKY: _COMPETENCIA_SKY},
        fonte_colaboradores_esperados=fonte_colaboradores_esperados,
    )

    assert len(resultado_ciclo.resultados_por_cliente) == 1
    resultado = resultado_ciclo.resultados_por_cliente[0]
    assert resultado.competencia == _COMPETENCIA_SKY

    # Base documental completa -- só falta Holerite (por cardinalidade, nunca por contagem plana).
    assert resultado.pacote.estado == EstadoPacotePrestacao.INCOMPLETO
    assert resultado.pacote.tipos_faltantes == ('Holerite',)
    assert resultado.pacote.holerite is not None
    assert len(resultado.pacote.holerite.colaboradores_faltantes) == 1
    assert resultado.pacote.holerite.colaboradores_faltantes[0] == _COLABORADORES[6]

    necessidades_holerite = [n for n in resultado.necessidades if n.tipo_documental == 'Holerite']
    assert len(necessidades_holerite) == 1
    assert necessidades_holerite[0].colaborador == _COLABORADORES[6]
    # sanitizado -- nunca CPF (pontuação) nem nome (espaço).
    assert '.' not in necessidades_holerite[0].colaborador.entidade_id
    assert ' ' not in necessidades_holerite[0].colaborador.entidade_id


def test_piloto_sky_holerite_completo_fica_pronto():
    """Variante: 7/7 Holerites presentes -> pacote PRONTO (prova que a
    cardinalidade completa nunca é confundida com incompleto)."""
    leitor = _montar_leitor()
    leitor._tabelas[TABLE_HOL] = [
        {'id': f'rec_holerite_{i}', 'fields': {F_HOL_FUNC: [c.entidade_id]}}
        for i, c in enumerate(_COLABORADORES)
    ]
    fonte_vinculos = FonteVinculosPrestacaoAirtableShadow(leitor)
    fonte_colaboradores_esperados = FonteColaboradoresEsperadosPrestacaoAirtableShadow(leitor)
    fonte_inventario = FonteInventarioPrestacaoComposta((
        FonteInventarioPrestacaoAirtableShadow(leitor),
        FonteInventarioHoleritesAirtableShadow(leitor, fonte_vinculos),
    ))

    resultado_ciclo = executar_ciclo_prestacao(
        contexto=_CONTEXTO,
        fonte_clientes=_FonteClientesSoSky(),
        fonte_requisitos=_FonteRequisitosVazia(),
        fonte_inventario=fonte_inventario,
        requisitos_base=CADASTRO_REQUISITOS_PRESTACAO_V2.requisitos_base_documentais(),
        resolucoes_ancora={_SKY: _resolucao_ancora_sky()},
        competencias_por_cliente={_SKY: _COMPETENCIA_SKY},
        fonte_colaboradores_esperados=fonte_colaboradores_esperados,
    )
    resultado = resultado_ciclo.resultados_por_cliente[0]
    assert resultado.pacote.estado == EstadoPacotePrestacao.PRONTO
    assert resultado.pacote.tipos_faltantes == ()
    assert resultado.pacote.holerite.completo
