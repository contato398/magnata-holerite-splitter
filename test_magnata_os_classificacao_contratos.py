from dataclasses import fields
from datetime import datetime, timezone

import pytest

from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    ConfiancaResolucao,
    DimensaoResolucao,
    EntradaResolucaoDocumento,
    EstadoResolucaoDimensao,
    EstadoResultadoSemantico,
    EvidenciaSanitizada,
    MetadadosExecucaoResolucao,
    NivelConfianca,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    RegraAplicabilidadeDimensao,
    ResolucaoDimensao,
    ResultadoResolucaoSemantico,
)


HASH = "a" * 64


def _regra(
    dimensao=DimensaoResolucao.CLIENTE,
    aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA,
    cardinalidade=Cardinalidade(1, 1),
):
    return RegraAplicabilidadeDimensao(
        dimensao=dimensao,
        aplicabilidade=aplicabilidade,
        cardinalidade=cardinalidade,
    )


def _perfil(perfil_id="perfil-padrao"):
    return PerfilAplicabilidadeResolucao(
        perfil_id=perfil_id,
        version="1",
        escopo_documental="escopo-de-teste",
        regras=(_regra(),),
    )


def _evidencia(referencia="fonte:1"):
    return EvidenciaSanitizada(
        tipo_evidencia="identificador_canonico",
        fonte="cadastro",
        referencia_fonte=referencia,
        metodo="id_exato",
        forca=NivelConfianca.FORTE,
    )


def _resolucao(evidencias=(), candidatos=()):
    return ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE,
        estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(ReferenciaCanonica("CLIENTE", "cliente-1"),),
        candidatos=tuple(candidatos),
        evidencias=tuple(evidencias),
        metodo="id_exato",
        confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )


def _resultado(perfil=None, resolucao=None):
    return ResultadoResolucaoSemantico(
        documento_id="documento-1",
        resolver_id="resolver-shadow",
        resolver_version="1",
        politica_id="politica-shadow",
        politica_version="1",
        perfil=perfil or _perfil(),
        resolucoes=(resolucao or _resolucao(),),
        estado_consolidado=EstadoResultadoSemantico.RESOLVIDA,
        necessita_revisao_humana=False,
        pronto_para_routing_logico=True,
    )


@pytest.mark.parametrize(
    "estado",
    [EstadoResolucaoDimensao.AMBIGUA, EstadoResolucaoDimensao.CONFLITO],
)
def test_ambiguidade_e_conflito_nao_aceitam_valor_confirmado(estado):
    with pytest.raises(ValueError, match="nao possui valor confirmado"):
        ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE,
            estado=estado,
            valores_confirmados=(ReferenciaCanonica("CLIENTE", "cliente-1"),),
        )


def test_nao_aplicavel_e_compativel_com_regra_nao_aplicavel():
    regra = _regra(
        aplicabilidade=AplicabilidadeDimensao.NAO_APLICAVEL,
        cardinalidade=Cardinalidade(0, 0),
    )
    resolucao = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE,
        estado=EstadoResolucaoDimensao.NAO_APLICAVEL,
    )
    resolucao.validar_contra(regra)


@pytest.mark.parametrize(
    "minima,maxima",
    [(-1, 1), (2, 1)],
)
def test_cardinalidade_invalida_e_rejeitada(minima, maxima):
    with pytest.raises(ValueError, match="cardinalidade"):
        Cardinalidade(minima, maxima)


def test_score_sem_escala_ou_origem_e_rejeitado():
    with pytest.raises(ValueError, match="escala_score"):
        ConfiancaResolucao(NivelConfianca.FORTE, score=10)
    with pytest.raises(ValueError, match="estrategia_origem"):
        ConfiancaResolucao(
            NivelConfianca.FORTE,
            score=10,
            escala_score="hits",
        )


def test_ordem_de_evidencias_e_candidatos_nao_muda_identidade_semantica():
    evidencias = (_evidencia("fonte:1"), _evidencia("fonte:2"))
    candidatos = (
        ReferenciaCanonica("CLIENTE", "cliente-1"),
        ReferenciaCanonica("CLIENTE", "cliente-2"),
    )
    primeiro = _resultado(resolucao=_resolucao(evidencias, candidatos))
    segundo = _resultado(
        resolucao=_resolucao(tuple(reversed(evidencias)), tuple(reversed(candidatos)))
    )
    assert primeiro.semantic_result_id == segundo.semantic_result_id


def test_metadados_variaveis_nao_mudam_semantic_result_id():
    resultado = _resultado()
    metadados_a = MetadadosExecucaoResolucao(
        execution_idempotency_key=HASH,
        correlation_id="corr-a",
        attempt_id="attempt-a",
        observado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    metadados_b = MetadadosExecucaoResolucao(
        execution_idempotency_key=HASH,
        correlation_id="corr-b",
        attempt_id="attempt-b",
        observado_em=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    assert metadados_a != metadados_b
    assert resultado.semantic_result_id == _resultado().semantic_result_id


@pytest.mark.parametrize(
    "campo,novo_valor",
    [
        ("resolver_version", "2"),
        ("politica_version", "2"),
        ("contexto_fontes_fingerprint", "contexto-2"),
    ],
)
def test_mudanca_de_resolver_politica_ou_contexto_muda_execution_key(
    campo, novo_valor
):
    base = dict(
        documento_id="documento-1",
        hash_sha256=HASH,
        resolver_id="resolver-shadow",
        resolver_version="1",
        politica_id="politica-shadow",
        politica_version="1",
        contexto_fontes_fingerprint="contexto-1",
    )
    original = EntradaResolucaoDocumento(**base)
    alterada = EntradaResolucaoDocumento(**{**base, campo: novo_valor})
    assert original.execution_idempotency_key != alterada.execution_idempotency_key


def test_perfil_diferente_pode_mudar_semantic_result_id():
    assert _resultado(_perfil("perfil-a")).semantic_result_id != _resultado(
        _perfil("perfil-b")
    ).semantic_result_id


def test_execution_key_independe_de_perfil_e_metadados_de_tentativa():
    nomes = {campo.name for campo in fields(EntradaResolucaoDocumento)}
    assert "perfil" not in nomes
    assert "correlation_id" not in nomes
    assert "attempt_id" not in nomes
    assert "observado_em" not in nomes


def test_contratos_persistiveis_nao_exigem_pii_bruta():
    nomes = {
        campo.name
        for tipo in (
            EvidenciaSanitizada,
            ResolucaoDimensao,
            ResultadoResolucaoSemantico,
        )
        for campo in fields(tipo)
    }
    assert nomes.isdisjoint({"cpf", "cnpj", "nome", "texto_bruto", "conteudo"})
    assert _resultado().semantic_result_id
