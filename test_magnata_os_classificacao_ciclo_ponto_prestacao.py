"""Testes focados de `ciclo_ponto_prestacao.py` (missão "FONTE DE
INVENTÁRIO DE FOLHA/CARTÃO DE PONTO V1" + revisão independente:
correção da regra de fechamento do ciclo).

REGRA CONFIRMADA: o ciclo fecha no dia `dia_fechamento`, INCLUSIVE; o
dia seguinte ao fechamento inicia o próximo ciclo. Ex.: fechamento=28,
competência junho/2026 -> ciclo 29/05/2026 a 28/06/2026 (nunca
28/05 a 28/06 -- essa era a modelagem incorreta corrigida aqui)."""
import datetime

import pytest

from magnata_os.classificacao.ciclo_ponto_prestacao import (
    POLITICA_CICLO_PONTO_PRESTACAO_V1,
    CicloPontoClienteOverride,
    JanelaCicloPonto,
    PoliticaCicloPontoPrestacao,
)
from magnata_os.classificacao.contratos import ReferenciaCanonica

_CLIENTE_A = ReferenciaCanonica('CLIENTE', 'rec_cliente_a')
_CLIENTE_SINTETICO_CICLO_DESLOCADO = ReferenciaCanonica('CLIENTE', 'rec_cliente_ciclo_deslocado')
_COMPETENCIA_JUNHO_2026 = ReferenciaCanonica('COMPETENCIA', '2026-06')
_COMPETENCIA_JULHO_2026 = ReferenciaCanonica('COMPETENCIA', '2026-07')
_COMPETENCIA_JANEIRO_2027 = ReferenciaCanonica('COMPETENCIA', '2027-01')

_POLITICA_FECHAMENTO_28 = PoliticaCicloPontoPrestacao(
    version='teste',
    overrides=(CicloPontoClienteOverride(cliente=_CLIENTE_SINTETICO_CICLO_DESLOCADO, dia_fechamento=28),),
)


def test_default_e_mes_civil_para_qualquer_cliente_sem_override():
    janela = POLITICA_CICLO_PONTO_PRESTACAO_V1.janela_para(_CLIENTE_A, _COMPETENCIA_JUNHO_2026)
    assert janela == JanelaCicloPonto(datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))


def test_ciclo_junho_2026_fecha_28_comeca_29_maio():
    """Caso adversarial confirmado pela revisão: competência junho/2026
    -> ciclo 29/05/2026 a 28/06/2026 -- cliente SINTÉTICO, nunca SKY
    Tatuí (nenhuma exceção real de ciclo de Ponto está confirmada)."""
    janela = _POLITICA_FECHAMENTO_28.janela_para(_CLIENTE_SINTETICO_CICLO_DESLOCADO, _COMPETENCIA_JUNHO_2026)
    assert janela == JanelaCicloPonto(datetime.date(2026, 5, 29), datetime.date(2026, 6, 28))


def test_ciclo_julho_2026_fecha_28_comeca_29_junho():
    janela = _POLITICA_FECHAMENTO_28.janela_para(_CLIENTE_SINTETICO_CICLO_DESLOCADO, _COMPETENCIA_JULHO_2026)
    assert janela == JanelaCicloPonto(datetime.date(2026, 6, 29), datetime.date(2026, 7, 28))


def test_nenhum_dia_pertence_a_dois_ciclos_consecutivos():
    ciclo_junho = _POLITICA_FECHAMENTO_28.janela_para(_CLIENTE_SINTETICO_CICLO_DESLOCADO, _COMPETENCIA_JUNHO_2026)
    ciclo_julho = _POLITICA_FECHAMENTO_28.janela_para(_CLIENTE_SINTETICO_CICLO_DESLOCADO, _COMPETENCIA_JULHO_2026)
    dia = ciclo_junho.data_inicio
    while dia <= ciclo_junho.data_fim:
        assert ciclo_junho.contem(dia)
        assert not ciclo_julho.contem(dia)
        dia += datetime.timedelta(days=1)


def test_nenhum_dia_fica_sem_pertencer_a_um_ciclo():
    """Continuidade: o dia seguinte ao fim de um ciclo é SEMPRE o
    início do próximo -- nenhuma lacuna."""
    ciclo_junho = _POLITICA_FECHAMENTO_28.janela_para(_CLIENTE_SINTETICO_CICLO_DESLOCADO, _COMPETENCIA_JUNHO_2026)
    ciclo_julho = _POLITICA_FECHAMENTO_28.janela_para(_CLIENTE_SINTETICO_CICLO_DESLOCADO, _COMPETENCIA_JULHO_2026)
    assert ciclo_julho.data_inicio == ciclo_junho.data_fim + datetime.timedelta(days=1)


def test_override_atravessa_virada_de_ano_sem_sobreposicao_nem_lacuna():
    ciclo_dezembro = _POLITICA_FECHAMENTO_28.janela_para(
        _CLIENTE_SINTETICO_CICLO_DESLOCADO, ReferenciaCanonica('COMPETENCIA', '2026-12'),
    )
    ciclo_janeiro = _POLITICA_FECHAMENTO_28.janela_para(_CLIENTE_SINTETICO_CICLO_DESLOCADO, _COMPETENCIA_JANEIRO_2027)
    assert ciclo_dezembro == JanelaCicloPonto(datetime.date(2026, 11, 29), datetime.date(2026, 12, 28))
    assert ciclo_janeiro == JanelaCicloPonto(datetime.date(2026, 12, 29), datetime.date(2027, 1, 28))
    assert ciclo_janeiro.data_inicio == ciclo_dezembro.data_fim + datetime.timedelta(days=1)


def test_override_fevereiro_nao_bissexto_rola_corretamente_para_marco():
    """Fechamento=28 em fevereiro não-bissexto (28 dias): o ciclo de
    março começa no dia seguinte ao fechamento de fevereiro (28/02),
    ou seja, 01/03 -- nunca um dia inexistente."""
    ciclo_marco = _POLITICA_FECHAMENTO_28.janela_para(
        _CLIENTE_SINTETICO_CICLO_DESLOCADO, ReferenciaCanonica('COMPETENCIA', '2027-03'),
    )
    assert ciclo_marco == JanelaCicloPonto(datetime.date(2027, 3, 1), datetime.date(2027, 3, 28))


def test_override_fevereiro_bissexto_inclui_dia_29():
    """Fechamento=28 em fevereiro bissexto (29 dias): o dia 29/02
    pertence ao ciclo de MARÇO (dia seguinte ao fechamento de
    fevereiro), nunca fica sem ciclo."""
    ciclo_marco = _POLITICA_FECHAMENTO_28.janela_para(
        _CLIENTE_SINTETICO_CICLO_DESLOCADO, ReferenciaCanonica('COMPETENCIA', '2028-03'),
    )
    assert ciclo_marco.data_inicio == datetime.date(2028, 2, 29)
    assert ciclo_marco.contem(datetime.date(2028, 2, 29))


def test_override_nao_afeta_outro_cliente():
    janela = _POLITICA_FECHAMENTO_28.janela_para(_CLIENTE_A, _COMPETENCIA_JUNHO_2026)
    assert janela == JanelaCicloPonto(datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))


def test_mes_civil_respeita_fevereiro_bissexto():
    janela = POLITICA_CICLO_PONTO_PRESTACAO_V1.janela_para(
        _CLIENTE_A, ReferenciaCanonica('COMPETENCIA', '2028-02'),
    )
    assert janela.data_fim == datetime.date(2028, 2, 29)


def test_janela_contem_e_nao_contem():
    janela = JanelaCicloPonto(datetime.date(2026, 5, 29), datetime.date(2026, 6, 28))
    assert janela.contem(datetime.date(2026, 5, 29))
    assert janela.contem(datetime.date(2026, 6, 28))
    assert janela.contem(datetime.date(2026, 6, 1))
    assert not janela.contem(datetime.date(2026, 5, 28))
    assert not janela.contem(datetime.date(2026, 6, 29))


def test_determinismo_mesma_entrada_mesmo_resultado():
    primeira = _POLITICA_FECHAMENTO_28.janela_para(_CLIENTE_SINTETICO_CICLO_DESLOCADO, _COMPETENCIA_JUNHO_2026)
    segunda = _POLITICA_FECHAMENTO_28.janela_para(_CLIENTE_SINTETICO_CICLO_DESLOCADO, _COMPETENCIA_JUNHO_2026)
    assert primeira == segunda


def test_dia_fechamento_fora_do_intervalo_permitido_rejeitado():
    with pytest.raises(ValueError):
        CicloPontoClienteOverride(cliente=_CLIENTE_A, dia_fechamento=29)
    with pytest.raises(ValueError):
        CicloPontoClienteOverride(cliente=_CLIENTE_A, dia_fechamento=0)


def test_politica_rejeita_override_duplicado_do_mesmo_cliente():
    with pytest.raises(ValueError):
        PoliticaCicloPontoPrestacao(
            version='teste',
            overrides=(
                CicloPontoClienteOverride(cliente=_CLIENTE_A, dia_fechamento=28),
                CicloPontoClienteOverride(cliente=_CLIENTE_A, dia_fechamento=1),
            ),
        )


def test_janela_fim_antes_de_inicio_rejeitada():
    with pytest.raises(ValueError):
        JanelaCicloPonto(datetime.date(2026, 6, 28), datetime.date(2026, 5, 29))


def test_competencia_formato_invalido_rejeitada():
    with pytest.raises(ValueError):
        POLITICA_CICLO_PONTO_PRESTACAO_V1.janela_para(
            _CLIENTE_A, ReferenciaCanonica('COMPETENCIA', '2026-13'),
        )
