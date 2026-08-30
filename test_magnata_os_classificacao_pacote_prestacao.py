"""Testes do pacote lógico da Prestação (Fase 10 da missão "CORREDOR
OPERACIONAL DA PRESTAÇÃO DE CONTAS")."""
import pytest

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.pacote_prestacao import (
    EstadoPacotePrestacao,
    PacotePrestacaoCliente,
    avaliar_e_montar_pacote,
    montar_pacote_logico,
)
from magnata_os.classificacao.politica_requisitos_prestacao import PoliticaRequisitosPrestacao
from magnata_os.classificacao.prestacao_readiness import (
    EstadoPrestacaoReadiness,
    ItemInventarioPrestacao,
    ResultadoPrestacaoReadiness,
    RequisitoDocumentalPrestacao,
)

_CLIENTE = ReferenciaCanonica('CLIENTE', 'rec_cliente_a')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')


def _readiness(estado, tipos_faltantes=(), motivos=()):
    return ResultadoPrestacaoReadiness(
        cliente=_CLIENTE, competencia=_COMPETENCIA, estado=estado,
        tipos_faltantes=tipos_faltantes, motivos=motivos,
    )


@pytest.mark.parametrize('estado_readiness,estado_pacote_esperado', [
    (EstadoPrestacaoReadiness.PRONTO, EstadoPacotePrestacao.PRONTO),
    (EstadoPrestacaoReadiness.FALTANDO, EstadoPacotePrestacao.INCOMPLETO),
    (EstadoPrestacaoReadiness.REVISAR, EstadoPacotePrestacao.EM_REVISAO),
    (EstadoPrestacaoReadiness.DIVERGENTE, EstadoPacotePrestacao.BLOQUEADO),
])
def test_mapeamento_readiness_para_pacote_e_1_para_1(estado_readiness, estado_pacote_esperado):
    pacote = montar_pacote_logico(_readiness(estado_readiness), requisitos=(), inventario=())
    assert pacote.estado == estado_pacote_esperado


def test_pacote_carrega_tipos_faltantes_do_readiness_sem_reinterpretar():
    pacote = montar_pacote_logico(
        _readiness(EstadoPrestacaoReadiness.FALTANDO, tipos_faltantes=('FGTS', 'Holerite')),
        requisitos=(RequisitoDocumentalPrestacao('FGTS'), RequisitoDocumentalPrestacao('Holerite')),
        inventario=(),
    )
    assert pacote.tipos_faltantes == ('FGTS', 'Holerite')
    assert pacote.tipos_obrigatorios == ('FGTS', 'Holerite')


def test_pacote_rejeita_item_de_outro_cliente():
    item_errado = ItemInventarioPrestacao(
        documento_id='doc-1', tipo_documental='Holerite',
        cliente=ReferenciaCanonica('CLIENTE', 'outro'), competencia=_COMPETENCIA,
    )
    with pytest.raises(ValueError):
        PacotePrestacaoCliente(
            cliente=_CLIENTE, competencia=_COMPETENCIA, estado=EstadoPacotePrestacao.PRONTO,
            itens_incluidos=(item_errado,), tipos_obrigatorios=(),
        )


def test_avaliar_e_montar_pacote_orquestra_politica_inventario_e_readiness():
    from magnata_os.classificacao.contratos import (
        AplicabilidadeDimensao, Cardinalidade, DimensaoResolucao, EntradaResolucaoDocumento,
        EstadoResolucaoDimensao, PerfilAplicabilidadeResolucao, RegraAplicabilidadeDimensao,
        ResolucaoDimensao,
    )
    from magnata_os.classificacao.resolucao_semantica import compor_resolucao_semantica

    class _FonteInventarioFake:
        def listar(self, cliente, competencia):
            return (ItemInventarioPrestacao(
                documento_id='doc-1', tipo_documental='Holerite', cliente=cliente, competencia=competencia,
            ),)

    perfil = PerfilAplicabilidadeResolucao(
        perfil_id='p', version='1', escopo_documental='teste',
        regras=(
            RegraAplicabilidadeDimensao(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
        ),
    )
    resolucao = compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id='doc-1', hash_sha256='a' * 64, resolver_id='r', resolver_version='1',
            politica_id='p', politica_version='1', contexto_fontes_fingerprint='teste',
        ),
        perfil=perfil,
        resolucoes=(
            ResolucaoDimensao(
                dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
                valores_confirmados=(_CLIENTE,),
            ),
            ResolucaoDimensao(
                dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.RESOLVIDA,
                valores_confirmados=(_COMPETENCIA,),
            ),
        ),
    )
    politica = PoliticaRequisitosPrestacao(
        version='1', requisitos_base=(RequisitoDocumentalPrestacao('Holerite'),),
    )
    pacote = avaliar_e_montar_pacote(_CLIENTE, _COMPETENCIA, resolucao, _FonteInventarioFake(), politica)
    assert pacote.estado == EstadoPacotePrestacao.PRONTO
    assert len(pacote.itens_incluidos) == 1
