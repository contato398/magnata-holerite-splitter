"""Testes focados de `resolucao_temporal_ponto.py` (validações de
construção — missão "IDENTIDADE TEMPORAL DOCUMENTAL DA FOLHA/CARTÃO DE
PONTO V1")."""
import datetime

import pytest

from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.classificacao.resolucao_temporal_ponto import (
    AlocacaoHistorica,
    ResolucaoDocumentalTemporalPonto,
    TransicaoResolucaoTemporal,
    classificar_transicao_resolucao,
    resolucao_a_persistir_para_transicao,
    resolucoes_equivalentes,
)

_RESOLVIDA_JUNHO = ResolucaoDimensao(
    dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.RESOLVIDA,
    valores_confirmados=(ReferenciaCanonica('COMPETENCIA', '2026-06'),),
)
_RESOLVIDA_JULHO = ResolucaoDimensao(
    dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.RESOLVIDA,
    valores_confirmados=(ReferenciaCanonica('COMPETENCIA', '2026-07'),),
)
_NAO_ENCONTRADA = ResolucaoDimensao(dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA)


def _res(competencia_resolucao, periodo_inicio=None, periodo_fim=None, documento_id='doc-x', colaborador_id='func-x'):
    return ResolucaoDocumentalTemporalPonto(
        documento_id=documento_id, tipo_documental='Folha de Ponto', colaborador_id=colaborador_id,
        periodo_inicio=periodo_inicio, periodo_fim=periodo_fim, resolucao_competencia=competencia_resolucao,
    )


def test_alocacao_rejeita_colaborador_id_vazio():
    with pytest.raises(ValueError):
        AlocacaoHistorica('', 'cliente-A', datetime.date(2026, 1, 1), None)


def test_alocacao_rejeita_cliente_id_vazio():
    with pytest.raises(ValueError):
        AlocacaoHistorica('func-1', '', datetime.date(2026, 1, 1), None)


def test_alocacao_rejeita_vigente_ate_antes_de_vigente_de():
    with pytest.raises(ValueError):
        AlocacaoHistorica('func-1', 'cliente-A', datetime.date(2026, 6, 1), datetime.date(2026, 1, 1))


def test_alocacao_intersecta_com_fim_aberto():
    a = AlocacaoHistorica('func-1', 'cliente-A', datetime.date(2026, 6, 1), None)
    assert a.intersecta(datetime.date(2026, 5, 29), datetime.date(2026, 6, 5))
    assert not a.intersecta(datetime.date(2026, 1, 1), datetime.date(2026, 5, 31))


def test_alocacao_intersecta_com_fim_fechado():
    a = AlocacaoHistorica('func-1', 'cliente-A', datetime.date(2026, 1, 1), datetime.date(2026, 6, 10))
    assert a.intersecta(datetime.date(2026, 5, 29), datetime.date(2026, 6, 28))  # cruza a borda
    assert not a.intersecta(datetime.date(2026, 6, 11), datetime.date(2026, 6, 30))  # comeca 1 dia depois do fim


def test_resolucao_documental_rejeita_documento_id_vazio():
    resolucao_competencia = ResolucaoDimensao(
        dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
    )
    with pytest.raises(ValueError):
        ResolucaoDocumentalTemporalPonto(
            documento_id='', tipo_documental='Folha de Ponto', colaborador_id='func-1',
            periodo_inicio=None, periodo_fim=None, resolucao_competencia=resolucao_competencia,
        )


def test_resolucao_documental_rejeita_dimensao_errada():
    resolucao_cliente_errada = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
    )
    with pytest.raises(ValueError):
        ResolucaoDocumentalTemporalPonto(
            documento_id='doc-1', tipo_documental='Folha de Ponto', colaborador_id='func-1',
            periodo_inicio=None, periodo_fim=None, resolucao_competencia=resolucao_cliente_errada,
        )


# ---------------------------------------------------------------------------
# classificar_transicao_resolucao / resolucoes_equivalentes /
# resolucao_a_persistir_para_transicao (revisão independente pós-PR #127)
# ---------------------------------------------------------------------------

def test_classificar_nenhuma_resolucao_anterior_e_sempre_nova():
    novo = _res(_RESOLVIDA_JUNHO, periodo_inicio=None, periodo_fim=None)
    assert classificar_transicao_resolucao(None, novo) == TransicaoResolucaoTemporal.NOVA


def test_classificar_resolucoes_identicas_sao_equivalentes():
    import datetime
    a = _res(_RESOLVIDA_JUNHO, datetime.date(2026, 5, 29), datetime.date(2026, 6, 28))
    b = _res(_RESOLVIDA_JUNHO, datetime.date(2026, 5, 29), datetime.date(2026, 6, 28))
    assert resolucoes_equivalentes(a, b)
    assert classificar_transicao_resolucao(a, b) == TransicaoResolucaoTemporal.EQUIVALENTE


def test_classificar_correcao_nao_encontrada_para_resolvida_e_atualizacao_nunca_conflito():
    anterior = _res(_NAO_ENCONTRADA)
    novo = _res(_RESOLVIDA_JUNHO)
    assert not resolucoes_equivalentes(anterior, novo)
    assert classificar_transicao_resolucao(anterior, novo) == TransicaoResolucaoTemporal.ATUALIZACAO


def test_classificar_duas_resolvidas_diferentes_e_conflito():
    anterior = _res(_RESOLVIDA_JUNHO)
    novo = _res(_RESOLVIDA_JULHO)
    assert classificar_transicao_resolucao(anterior, novo) == TransicaoResolucaoTemporal.CONFLITO


def test_classificar_resolvida_para_nao_encontrada_e_atualizacao_nunca_conflito():
    """Regressão para NAO_ENCONTRADA não é uma disputa entre 2 valores
    confiantes -- é só uma atualização (o novo resultado é menos
    confiante que o anterior, mas isso não é CONFLITO por definição)."""
    anterior = _res(_RESOLVIDA_JUNHO)
    novo = _res(_NAO_ENCONTRADA)
    assert classificar_transicao_resolucao(anterior, novo) == TransicaoResolucaoTemporal.ATUALIZACAO


def test_aplicar_transicao_nova_e_atualizacao_preservam_o_novo_sem_alteracao():
    novo = _res(_RESOLVIDA_JUNHO)
    assert resolucao_a_persistir_para_transicao(TransicaoResolucaoTemporal.NOVA, novo) is novo
    assert resolucao_a_persistir_para_transicao(TransicaoResolucaoTemporal.ATUALIZACAO, novo) is novo


def test_aplicar_transicao_conflito_nunca_escolhe_um_valor_rebaixa_para_conflito_e_limpa_periodo():
    import datetime
    novo = _res(_RESOLVIDA_JULHO, datetime.date(2026, 6, 29), datetime.date(2026, 7, 28))
    persistida = resolucao_a_persistir_para_transicao(TransicaoResolucaoTemporal.CONFLITO, novo)

    assert persistida.resolucao_competencia.estado == EstadoResolucaoDimensao.CONFLITO
    assert persistida.resolucao_competencia.valores_confirmados == ()
    assert persistida.periodo_inicio is None
    assert persistida.periodo_fim is None
    assert persistida.documento_id == novo.documento_id
    assert persistida.colaborador_id == novo.colaborador_id
