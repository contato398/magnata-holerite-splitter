"""Testes de `automacao_por_confianca.py` (missão "AUTOMAÇÃO DOCUMENTAL
REAL V1", §14/§20)."""
import pytest

from magnata_os.classificacao.automacao_por_confianca import (
    DecisaoAutomacao,
    calcular_metricas_automacao,
    decidir_proxima_acao,
)
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
from magnata_os.classificacao.resolucao_semantica import compor_resolucao_semantica
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental

_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')


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


def _resolucao(resolucao_tipo, documento_id='doc'):
    return compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id=documento_id, hash_sha256='a' * 64, resolver_id='r', resolver_version='1',
            politica_id='p', politica_version='1', contexto_fontes_fingerprint='teste-automacao',
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


def _resolucao_de_texto(texto, **kwargs):
    resolucao_tipo = resolver_tipo_documental(hipoteses_textuais_de_classificacao(classificar_documento(texto)))
    return _resolucao(resolucao_tipo, **kwargs)


def test_resolvida_avanca_automatico():
    resolucao = _resolucao_de_texto('Guia do FGTS Digital -- Total FGTS')
    assert decidir_proxima_acao(resolucao) == DecisaoAutomacao.AVANCA_AUTOMATICO


def test_nao_encontrada_vira_desconhecido():
    resolucao = _resolucao_de_texto('texto totalmente generico sem nenhum sinal conhecido')
    assert decidir_proxima_acao(resolucao) == DecisaoAutomacao.DESCONHECIDO


def test_ambigua_nunca_avanca_automatico():
    resolucao_tipo = ResolucaoDimensao(
        dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.AMBIGUA,
        candidatos=(ReferenciaCanonica('TIPO_DOCUMENTAL', 'FGTS'), ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite')),
    )
    assert decidir_proxima_acao(_resolucao(resolucao_tipo)) == DecisaoAutomacao.AMBIGUO


def test_conflito_nunca_avanca_automatico():
    resolucao_tipo = ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.CONFLITO)
    assert decidir_proxima_acao(_resolucao(resolucao_tipo)) == DecisaoAutomacao.CONFLITO


def test_erro_tecnico_vira_retry():
    resolucao_tipo = ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.ERRO_TECNICO)
    assert decidir_proxima_acao(_resolucao(resolucao_tipo)) == DecisaoAutomacao.RETRY_TECNICO


def test_erro_tecnico_nunca_vira_revisao_humana_direta():
    """ADENDO OBRIGATÓRIO item 4: ERRO_TECNICO sempre vira RETRY_TECNICO
    -- só a política de retry/esgotamento (fora deste módulo) decide
    quando virar exceção humana; esta função nunca pula direto para
    REVISAO_HUMANA."""
    resolucao_tipo = ResolucaoDimensao(dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.ERRO_TECNICO)
    decisao = decidir_proxima_acao(_resolucao(resolucao_tipo))
    assert decisao == DecisaoAutomacao.RETRY_TECNICO
    assert decisao != DecisaoAutomacao.REVISAO_HUMANA


def test_resolvida_nunca_recalcula_apenas_le_estado_consolidado_existente():
    """ADENDO OBRIGATÓRIO item 4: 'não duplicar decisão' -- AVANCA_
    AUTOMATICO só acontece porque `compor_resolucao_semantica` já
    decidiu RESOLVIDA (todas as exigências do compositor já passaram);
    este teste prova que uma dimensão TIPO_DOCUMENTAL isoladamente
    RESOLVIDA, mas com o resultado consolidado marcado como PARCIAL
    (ex.: outra dimensão pendente), NUNCA avança automático -- a
    decisão é sempre do `estado_consolidado`, nunca de uma dimensão
    isolada."""
    from magnata_os.classificacao.contratos import EstadoResultadoSemantico
    import dataclasses

    resolucao_tipo = ResolucaoDimensao(
        dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(ReferenciaCanonica('TIPO_DOCUMENTAL', 'FGTS'),),
    )
    resultado = _resolucao(resolucao_tipo)
    resultado_parcial = dataclasses.replace(
        resultado, estado_consolidado=EstadoResultadoSemantico.PARCIAL, necessita_revisao_humana=True,
        pronto_para_routing_logico=False,
    )
    assert decidir_proxima_acao(resultado_parcial) != DecisaoAutomacao.AVANCA_AUTOMATICO


def test_metricas_agregam_lote_e_percentual_correto():
    resolvida = _resolucao_de_texto('Guia do FGTS Digital -- Total FGTS', documento_id='d1')
    desconhecida = _resolucao_de_texto('texto totalmente generico sem sinal', documento_id='d2')
    ambigua = _resolucao(ResolucaoDimensao(
        dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.AMBIGUA,
        candidatos=(ReferenciaCanonica('TIPO_DOCUMENTAL', 'FGTS'), ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite')),
    ), documento_id='d3')

    metricas = calcular_metricas_automacao((resolvida, desconhecida, ambigua))
    assert metricas.total == 3
    assert metricas.auto_resolvidos == 1
    assert metricas.desconhecidos == 1
    assert metricas.ambiguos == 1
    assert metricas.percentual_automacao == pytest.approx(33.33, abs=0.01)


def test_metricas_lote_vazio_nunca_quebra():
    metricas = calcular_metricas_automacao(())
    assert metricas.total == 0
    assert metricas.percentual_automacao == 0.0


def test_metricas_rejeita_soma_inconsistente():
    with pytest.raises(ValueError):
        from magnata_os.classificacao.automacao_por_confianca import MetricasAutomacao
        MetricasAutomacao(total=5, auto_resolvidos=1, revisao=1, ambiguos=1, conflitos=1, erros=0, desconhecidos=0)
