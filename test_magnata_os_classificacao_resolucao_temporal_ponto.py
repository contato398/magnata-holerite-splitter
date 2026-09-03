"""Testes focados de `resolucao_temporal_ponto.py` (validações de
construção — missão "IDENTIDADE TEMPORAL DOCUMENTAL DA FOLHA/CARTÃO DE
PONTO V1")."""
import datetime

import pytest

from magnata_os.classificacao.contratos import DimensaoResolucao, EstadoResolucaoDimensao, ResolucaoDimensao
from magnata_os.classificacao.resolucao_temporal_ponto import (
    AlocacaoHistorica,
    ResolucaoDocumentalTemporalPonto,
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
