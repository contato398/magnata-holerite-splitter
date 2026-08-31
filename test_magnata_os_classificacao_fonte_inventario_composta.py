"""Testes de `FonteInventarioPrestacaoComposta` (missão "INVENTÁRIO
DOCUMENTAL REAL DA PRESTAÇÃO", Fase 2/9)."""
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.fonte_inventario_composta import FonteInventarioPrestacaoComposta
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao

_CLIENTE = ReferenciaCanonica('CLIENTE', 'rec_cliente')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')


class _FonteFixa:
    def __init__(self, itens):
        self._itens = itens

    def listar(self, cliente, competencia):
        return tuple(i for i in self._itens if i.cliente == cliente and i.competencia == competencia)


def test_agrega_itens_de_multiplas_fontes():
    item_a = ItemInventarioPrestacao('doc-a', 'FGTS', _CLIENTE, _COMPETENCIA)
    item_b = ItemInventarioPrestacao('doc-b', 'Holerite', _CLIENTE, _COMPETENCIA)
    composta = FonteInventarioPrestacaoComposta((_FonteFixa((item_a,)), _FonteFixa((item_b,))))
    itens = composta.listar(_CLIENTE, _COMPETENCIA)
    assert {i.documento_id for i in itens} == {'doc-a', 'doc-b'}


def test_deduplica_por_documento_id_primeiro_prevalece():
    item_1 = ItemInventarioPrestacao('doc-x', 'FGTS', _CLIENTE, _COMPETENCIA)
    item_2 = ItemInventarioPrestacao('doc-x', 'Guia DCTFWeb/DARF', _CLIENTE, _COMPETENCIA)
    composta = FonteInventarioPrestacaoComposta((_FonteFixa((item_1,)), _FonteFixa((item_2,))))
    itens = composta.listar(_CLIENTE, _COMPETENCIA)
    assert len(itens) == 1
    assert itens[0].tipo_documental == 'FGTS'  # primeira fonte prevalece, nunca merge


def test_traduz_vocabulario_familia_b_para_motor_geral():
    """`extrato_cliente` (Família B, adapter Airtable-shadow já
    existente) vira `Extrato da Folha de Pagamento` (motor geral) --
    sem isso, nunca bateria com o requisito canônico do cadastro V2."""
    item = ItemInventarioPrestacao('doc-extrato', 'extrato_cliente', _CLIENTE, _COMPETENCIA)
    composta = FonteInventarioPrestacaoComposta((_FonteFixa((item,)),))
    itens = composta.listar(_CLIENTE, _COMPETENCIA)
    assert itens[0].tipo_documental == 'Extrato da Folha de Pagamento'


def test_tipos_ja_no_vocabulario_geral_nunca_sao_alterados():
    item = ItemInventarioPrestacao('doc-fgts', 'FGTS', _CLIENTE, _COMPETENCIA)
    composta = FonteInventarioPrestacaoComposta((_FonteFixa((item,)),))
    itens = composta.listar(_CLIENTE, _COMPETENCIA)
    assert itens[0].tipo_documental == 'FGTS'


def test_sem_fontes_devolve_tupla_vazia():
    assert FonteInventarioPrestacaoComposta(()).listar(_CLIENTE, _COMPETENCIA) == ()


def test_preserva_colaborador_sanitizado_ao_traduzir_tipo():
    colaborador = ReferenciaCanonica('COLABORADOR', 'rec_colab')
    item = ItemInventarioPrestacao('doc-holerite', 'Holerite', _CLIENTE, _COMPETENCIA, colaborador=colaborador)
    composta = FonteInventarioPrestacaoComposta((_FonteFixa((item,)),))
    itens = composta.listar(_CLIENTE, _COMPETENCIA)
    assert itens[0].colaborador == colaborador


# ============================================================================
# Adendo substitutivo ao PR #105, §15 -- dedupe por identidade lógica
# (documento_id + cliente + colaborador), nunca só documento_id.
# ============================================================================

def test_mesmo_documento_mesmo_cliente_colaboradores_distintos_nunca_colapsam():
    """Fatiamento por colaborador (ex.: relatório de benefícios) do
    MESMO documento físico, MESMO cliente -- 2 parcelas lógicas
    distintas, ambas preservadas (nunca dedupadas como se fossem o
    mesmo item)."""
    colaborador_1 = ReferenciaCanonica('COLABORADOR', 'rec_colab_1')
    colaborador_2 = ReferenciaCanonica('COLABORADOR', 'rec_colab_2')
    item_1 = ItemInventarioPrestacao(
        'doc-beneficios', 'Relatório de Benefícios', _CLIENTE, _COMPETENCIA, colaborador=colaborador_1,
    )
    item_2 = ItemInventarioPrestacao(
        'doc-beneficios', 'Relatório de Benefícios', _CLIENTE, _COMPETENCIA, colaborador=colaborador_2,
    )
    composta = FonteInventarioPrestacaoComposta((_FonteFixa((item_1, item_2)),))
    itens = composta.listar(_CLIENTE, _COMPETENCIA)
    assert len(itens) == 2
    assert {i.colaborador for i in itens} == {colaborador_1, colaborador_2}


def test_mesmo_documento_clientes_distintos_broadcast_nunca_colapsam():
    cliente_b = ReferenciaCanonica('CLIENTE', 'rec_cliente_b')
    item_a = ItemInventarioPrestacao('doc-dctf', 'Guia DCTFWeb/DARF', _CLIENTE, _COMPETENCIA)
    item_b = ItemInventarioPrestacao('doc-dctf', 'Guia DCTFWeb/DARF', cliente_b, _COMPETENCIA)
    composta = FonteInventarioPrestacaoComposta((_FonteFixa((item_a, item_b)),))
    assert len(composta.listar(_CLIENTE, _COMPETENCIA)) == 1
    assert len(composta.listar(cliente_b, _COMPETENCIA)) == 1
