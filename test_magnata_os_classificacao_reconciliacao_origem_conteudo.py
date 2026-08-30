"""Testes de `reconciliacao_origem_conteudo.py` (missão "AUTOMAÇÃO
DOCUMENTAL REAL V1", §12)."""
import pytest

from magnata_os.classificacao.classificador_documental import classificar_documento
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
from magnata_os.classificacao.produtores_evidencia_documental import hipoteses_textuais_de_classificacao
from magnata_os.classificacao.reconciliacao_origem_conteudo import (
    ResultadoReconciliacaoOrigem,
    reconciliar_origem_com_resolucao_semantica,
)
from magnata_os.classificacao.resolucao_semantica import compor_resolucao_semantica
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental

_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')
_CLIENTE = ReferenciaCanonica('CLIENTE', 'rec_cliente')


def _perfil():
    return PerfilAplicabilidadeResolucao(
        perfil_id='p', version='1', escopo_documental='teste',
        regras=(
            RegraAplicabilidadeDimensao(DimensaoResolucao.TIPO_DOCUMENTAL, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COLABORADOR, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.UNIDADE_POSTO, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.VINCULO, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
        ),
    )


def _resolucao_para_texto(texto, documento_id='doc'):
    resolucao_tipo = resolver_tipo_documental(hipoteses_textuais_de_classificacao(classificar_documento(texto)))
    return compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id=documento_id, hash_sha256='a' * 64, resolver_id='r', resolver_version='1',
            politica_id='p', politica_version='1', contexto_fontes_fingerprint='teste-reconciliacao',
        ),
        perfil=_perfil(),
        resolucoes=(
            resolucao_tipo,
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
    )


def test_origem_e_conteudo_concordam_e_reforcam():
    resolucao = _resolucao_para_texto('Guia do FGTS Digital -- Total FGTS')
    reconciliacao = reconciliar_origem_com_resolucao_semantica('FGTS', resolucao)
    assert reconciliacao.resultado == ResultadoReconciliacaoOrigem.REFORCO
    assert reconciliacao.tipo_resolvido == 'FGTS'


def test_origem_declara_um_tipo_mas_conteudo_resolve_outro_vira_conflito():
    """REGRA CRÍTICA (§12): estar na tabela 'Holerites' nunca prova
    sozinho que o documento é um Holerite -- se o conteúdo resolve para
    outro tipo, é CONFLITO, nunca a origem vencendo silenciosamente."""
    resolucao = _resolucao_para_texto('Guia do FGTS Digital -- Total FGTS')
    reconciliacao = reconciliar_origem_com_resolucao_semantica('Holerite', resolucao)
    assert reconciliacao.resultado == ResultadoReconciliacaoOrigem.CONFLITO
    assert reconciliacao.tipo_origem == 'Holerite'
    assert reconciliacao.tipo_resolvido == 'FGTS'


def test_conteudo_sem_resolucao_nunca_vira_reforco_nem_conflito():
    resolucao = _resolucao_para_texto('texto totalmente generico sem nenhum sinal')
    reconciliacao = reconciliar_origem_com_resolucao_semantica('Holerite', resolucao)
    assert reconciliacao.resultado == ResultadoReconciliacaoOrigem.SEM_RESOLUCAO
    assert reconciliacao.tipo_resolvido is None


def test_tipo_origem_vazio_e_rejeitado():
    resolucao = _resolucao_para_texto('Guia do FGTS Digital -- Total FGTS')
    with pytest.raises(ValueError):
        reconciliar_origem_com_resolucao_semantica('', resolucao)
