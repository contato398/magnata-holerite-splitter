from dataclasses import asdict, fields

import pytest

from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    ConfiancaResolucao,
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    EstadoResultadoSemantico,
    NivelConfianca,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    RegraAplicabilidadeDimensao,
    ResolucaoDimensao,
    ResultadoResolucaoSemantico,
)
from magnata_os.classificacao.prestacao_readiness import (
    EntradaPrestacaoReadiness,
    EstadoPrestacaoReadiness,
    ItemInventarioPrestacao,
    RequisitoDocumentalPrestacao,
    ResultadoPrestacaoReadiness,
    avaliar_prestacao_readiness,
)


CLIENTE = ReferenciaCanonica("CLIENTE", "cliente-1")
COMPETENCIA = ReferenciaCanonica("COMPETENCIA", "2026-07")
OUTRA_COMPETENCIA = ReferenciaCanonica("COMPETENCIA", "2026-06")


def _regra(dimensao):
    return RegraAplicabilidadeDimensao(
        dimensao=dimensao,
        aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA,
        cardinalidade=Cardinalidade(1, 1),
    )


def _dimensao(dimensao, referencia, estado=EstadoResolucaoDimensao.RESOLVIDA):
    return ResolucaoDimensao(
        dimensao=dimensao,
        estado=estado,
        valores_confirmados=(referencia,) if estado == EstadoResolucaoDimensao.RESOLVIDA else (),
        confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )


def _resolucao(estado_cliente=EstadoResolucaoDimensao.RESOLVIDA, competencia=COMPETENCIA):
    perfil = PerfilAplicabilidadeResolucao(
        perfil_id="prestacao-shadow",
        version="1",
        escopo_documental="prestacao-contas",
        regras=(
            _regra(DimensaoResolucao.CLIENTE),
            _regra(DimensaoResolucao.COMPETENCIA),
        ),
    )
    return ResultadoResolucaoSemantico(
        documento_id="inventario-prestacao-1",
        resolver_id="resolver-shadow",
        resolver_version="1",
        politica_id="prestacao-readiness",
        politica_version="1",
        perfil=perfil,
        resolucoes=(
            _dimensao(DimensaoResolucao.CLIENTE, CLIENTE, estado_cliente),
            _dimensao(DimensaoResolucao.COMPETENCIA, competencia),
        ),
        estado_consolidado=(
            EstadoResultadoSemantico.RESOLVIDA
            if estado_cliente == EstadoResolucaoDimensao.RESOLVIDA
            else EstadoResultadoSemantico.INCONCLUSIVA
        ),
        necessita_revisao_humana=(
            estado_cliente != EstadoResolucaoDimensao.RESOLVIDA
        ),
    )


def _item(documento_id, tipo, competencia=COMPETENCIA):
    return ItemInventarioPrestacao(
        documento_id=documento_id,
        tipo_documental=tipo,
        cliente=CLIENTE,
        competencia=competencia,
    )


def _entrada(inventario=(), resolucao=None):
    return EntradaPrestacaoReadiness(
        cliente=CLIENTE,
        competencia=COMPETENCIA,
        requisitos=(
            RequisitoDocumentalPrestacao("HOLERITE"),
            RequisitoDocumentalPrestacao("FGTS"),
        ),
        inventario=tuple(inventario),
        resolucao=resolucao or _resolucao(),
    )


def test_inventario_completo_e_coerente_resulta_pronto():
    resultado = avaliar_prestacao_readiness(
        _entrada((_item("doc-1", "HOLERITE"), _item("doc-2", "FGTS")))
    )
    assert resultado.estado == EstadoPrestacaoReadiness.PRONTO
    assert resultado.tipos_faltantes == ()


def test_requisito_ausente_resulta_faltando():
    resultado = avaliar_prestacao_readiness(_entrada((_item("doc-1", "HOLERITE"),)))
    assert resultado.estado == EstadoPrestacaoReadiness.FALTANDO
    assert resultado.tipos_faltantes == ("FGTS",)


def test_competencia_do_inventario_incompativel_resulta_divergente():
    resultado = avaliar_prestacao_readiness(
        _entrada(
            (
                _item("doc-1", "HOLERITE"),
                _item("doc-2", "FGTS", OUTRA_COMPETENCIA),
            )
        )
    )
    assert resultado.estado == EstadoPrestacaoReadiness.DIVERGENTE


def test_competencia_resolvida_incompativel_resulta_divergente():
    resultado = avaliar_prestacao_readiness(
        _entrada((), resolucao=_resolucao(competencia=OUTRA_COMPETENCIA))
    )
    assert resultado.estado == EstadoPrestacaoReadiness.DIVERGENTE


@pytest.mark.parametrize(
    "estado",
    [EstadoResolucaoDimensao.AMBIGUA, EstadoResolucaoDimensao.CONFLITO],
)
def test_ambiguidade_ou_conflito_resulta_revisar(estado):
    resultado = avaliar_prestacao_readiness(
        _entrada((), resolucao=_resolucao(estado_cliente=estado))
    )
    assert resultado.estado == EstadoPrestacaoReadiness.REVISAR


def test_resultado_e_deterministico_para_ordens_diferentes():
    requisitos_invertidos = tuple(reversed(_entrada().requisitos))
    itens = (_item("doc-1", "HOLERITE"), _item("doc-2", "FGTS"))
    primeira = avaliar_prestacao_readiness(_entrada(itens))
    segunda = avaliar_prestacao_readiness(
        EntradaPrestacaoReadiness(
            cliente=CLIENTE,
            competencia=COMPETENCIA,
            requisitos=requisitos_invertidos,
            inventario=tuple(reversed(itens)),
            resolucao=_resolucao(),
        )
    )
    assert primeira == segunda


def test_resultado_nao_expoe_pii_ou_conteudo_bruto():
    nomes = {campo.name for campo in fields(ResultadoPrestacaoReadiness)}
    assert nomes.isdisjoint(
        {"cpf", "cnpj", "nome", "email", "texto_bruto", "conteudo", "bytes"}
    )
    serializado = asdict(avaliar_prestacao_readiness(_entrada()))
    assert "texto_bruto" not in str(serializado)
