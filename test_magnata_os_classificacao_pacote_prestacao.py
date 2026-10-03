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


# =====================================================================
# Pacote / Intenção de Distribuição de NÍVEL CLIENTE (Prestação upstream
# real V1). Tipos arbitrários -- nenhum nome documental real decide nada.
# =====================================================================

import dataclasses as _dc  # noqa: E402

from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao  # noqa: E402
from magnata_os.classificacao.pacote_prestacao import (  # noqa: E402
    DocumentoIntencaoCliente,
    IntencaoDistribuicaoCliente,
    IntencaoDistribuicaoClienteError,
    PapelDestinatarioOrganizacional,
    ResultadoComColaboradorNaIntencaoCliente,
    ResultadoDeOutroClienteOuCompetencia,
    montar_intencao_distribuicao_cliente,
)

_OUTRO_CLIENTE = ReferenciaCanonica('CLIENTE', 'rec_cliente_b')
_OUTRA_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-08')
_COLAB = ReferenciaCanonica('COLABORADOR', 'colab-x')


@_dc.dataclass(frozen=True)
class _Resultado:
    necessidade: NecessidadeDocumentoPrestacao
    documento_id: str
    hash_sha256: str


def _r(documento_id, tipo, *, cliente=_CLIENTE, competencia=_COMPETENCIA, colaborador=None, h=None):
    return _Resultado(
        necessidade=NecessidadeDocumentoPrestacao(
            cliente=cliente, competencia=competencia, tipo_documental=tipo,
            motivo_exigencia='teste-intencao-cliente', colaborador=colaborador,
        ),
        documento_id=documento_id, hash_sha256=h or (documento_id[-1] * 64),
    )


def _intencao(resultados):
    return montar_intencao_distribuicao_cliente(
        cliente=_CLIENTE, competencia=_COMPETENCIA, resultados_aquisicao=resultados,
    )


def test_intencao_cliente_agrupa_n_documentos_genericos_sem_funcionario_nem_canal():
    intencao = _intencao((_r('doc-b', 'DOCUMENTO_B'), _r('doc-a', 'DOCUMENTO_A')))

    assert intencao.documento_ids == ('doc-a', 'doc-b')
    assert intencao.papel_destinatario == PapelDestinatarioOrganizacional.CLIENTE_INSTITUCIONAL
    campos = {f.name for f in _dc.fields(IntencaoDistribuicaoCliente)}
    assert not campos & {'funcionario_id', 'colaborador', 'destinatario', 'canal', 'email', 'telefone'}


def test_intencao_cliente_mesmo_documento_para_duas_necessidades_aparece_uma_vez():
    intencao = _intencao((_r('doc-a', 'DOCUMENTO_B'), _r('doc-a', 'DOCUMENTO_A')))
    assert intencao.documentos == (
        DocumentoIntencaoCliente('doc-a', 'a' * 64, ('DOCUMENTO_A', 'DOCUMENTO_B')),
    )


def test_intencao_cliente_identidade_deterministica_e_independente_da_ordem():
    resultados = (_r('doc-a', 'DOCUMENTO_A'), _r('doc-b', 'DOCUMENTO_B'), _r('doc-c', 'DOCUMENTO_C'))
    ids = {_intencao(ordem).intencao_id for ordem in (resultados, resultados[::-1], resultados[1:] + resultados[:1])}
    assert len(ids) == 1
    assert len(next(iter(ids))) == 64
    # Conteúdo diferente -> identidade diferente (outro hash, outro documento, outro tipo).
    assert _intencao((_r('doc-a', 'DOCUMENTO_A', h='f' * 64),)).intencao_id != _intencao(
        (_r('doc-a', 'DOCUMENTO_A'),)).intencao_id
    assert _intencao((_r('doc-a', 'DOCUMENTO_Z'),)).intencao_id != _intencao(
        (_r('doc-a', 'DOCUMENTO_A'),)).intencao_id


def test_intencao_cliente_rejeita_necessidade_de_colaborador():
    with pytest.raises(ResultadoComColaboradorNaIntencaoCliente):
        _intencao((_r('doc-a', 'DOCUMENTO_A'), _r('doc-b', 'DOCUMENTO_B', colaborador=_COLAB)))


@pytest.mark.parametrize('extra', [
    {'cliente': _OUTRO_CLIENTE},
    {'competencia': _OUTRA_COMPETENCIA},
])
def test_intencao_cliente_rejeita_outro_cliente_ou_competencia(extra):
    with pytest.raises(ResultadoDeOutroClienteOuCompetencia):
        _intencao((_r('doc-a', 'DOCUMENTO_A'), _r('doc-b', 'DOCUMENTO_B', **extra)))


def test_intencao_cliente_sem_documento_e_erro_de_dominio():
    with pytest.raises(IntencaoDistribuicaoClienteError):
        _intencao(())


def test_intencao_cliente_invariantes_diretas():
    doc = DocumentoIntencaoCliente('doc-a', 'a' * 64, ('DOCUMENTO_A',))
    outro = DocumentoIntencaoCliente('doc-b', 'b' * 64, ('DOCUMENTO_B',))
    base = dict(cliente=_CLIENTE, competencia=_COMPETENCIA,
                papel_destinatario=PapelDestinatarioOrganizacional.CLIENTE_INSTITUCIONAL)
    with pytest.raises(IntencaoDistribuicaoClienteError):
        IntencaoDistribuicaoCliente(documentos=(outro, doc), **base)  # fora de ordem
    with pytest.raises(IntencaoDistribuicaoClienteError):
        IntencaoDistribuicaoCliente(documentos=(doc, doc), **base)  # repetido
    with pytest.raises(IntencaoDistribuicaoClienteError):
        IntencaoDistribuicaoCliente(**dict(base, cliente=_COLAB), documentos=(doc,))
    with pytest.raises(IntencaoDistribuicaoClienteError):
        IntencaoDistribuicaoCliente(**dict(base, papel_destinatario='CLIENTE_INSTITUCIONAL'), documentos=(doc,))
    with pytest.raises(IntencaoDistribuicaoClienteError):
        DocumentoIntencaoCliente('doc-a', 'a' * 64, ('B', 'A'))
