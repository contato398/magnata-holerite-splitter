"""Testes focados de `ciclo_ponto_prestacao.py` (missão "FONTE DE
INVENTÁRIO DE FOLHA/CARTÃO DE PONTO V1")."""
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
_COMPETENCIA_JANEIRO_2027 = ReferenciaCanonica('COMPETENCIA', '2027-01')


def test_default_e_mes_civil_para_qualquer_cliente_sem_override():
    janela = POLITICA_CICLO_PONTO_PRESTACAO_V1.janela_para(_CLIENTE_A, _COMPETENCIA_JUNHO_2026)
    assert janela == JanelaCicloPonto(datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))


def test_override_produz_ciclo_deslocado_nao_coincidente_com_mes_civil():
    """Caso adversarial sintético pedido pela missão: competência
    junho/2026, ciclo de ponto 28/05/2026 a 28/06/2026 -- cliente
    SINTÉTICO, nunca SKY Tatuí (nenhuma exceção real de ciclo de Ponto
    está confirmada para nenhum cliente)."""
    politica = PoliticaCicloPontoPrestacao(
        version='teste',
        overrides=(CicloPontoClienteOverride(cliente=_CLIENTE_SINTETICO_CICLO_DESLOCADO, dia_corte=28),),
    )
    janela = politica.janela_para(_CLIENTE_SINTETICO_CICLO_DESLOCADO, _COMPETENCIA_JUNHO_2026)
    assert janela == JanelaCicloPonto(datetime.date(2026, 5, 28), datetime.date(2026, 6, 28))


def test_override_atravessa_virada_de_ano_corretamente():
    politica = PoliticaCicloPontoPrestacao(
        version='teste',
        overrides=(CicloPontoClienteOverride(cliente=_CLIENTE_SINTETICO_CICLO_DESLOCADO, dia_corte=28),),
    )
    janela = politica.janela_para(_CLIENTE_SINTETICO_CICLO_DESLOCADO, _COMPETENCIA_JANEIRO_2027)
    assert janela == JanelaCicloPonto(datetime.date(2026, 12, 28), datetime.date(2027, 1, 28))


def test_override_nao_afeta_outro_cliente():
    politica = PoliticaCicloPontoPrestacao(
        version='teste',
        overrides=(CicloPontoClienteOverride(cliente=_CLIENTE_SINTETICO_CICLO_DESLOCADO, dia_corte=28),),
    )
    janela = politica.janela_para(_CLIENTE_A, _COMPETENCIA_JUNHO_2026)
    assert janela == JanelaCicloPonto(datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))


def test_mes_civil_respeita_fevereiro_bissexto():
    janela = POLITICA_CICLO_PONTO_PRESTACAO_V1.janela_para(
        _CLIENTE_A, ReferenciaCanonica('COMPETENCIA', '2028-02'),
    )
    assert janela.data_fim == datetime.date(2028, 2, 29)


def test_janela_contem_e_nao_contem():
    janela = JanelaCicloPonto(datetime.date(2026, 5, 28), datetime.date(2026, 6, 28))
    assert janela.contem(datetime.date(2026, 5, 28))
    assert janela.contem(datetime.date(2026, 6, 28))
    assert janela.contem(datetime.date(2026, 6, 1))
    assert not janela.contem(datetime.date(2026, 5, 27))
    assert not janela.contem(datetime.date(2026, 6, 29))


def test_dia_corte_fora_do_intervalo_permitido_rejeitado():
    with pytest.raises(ValueError):
        CicloPontoClienteOverride(cliente=_CLIENTE_A, dia_corte=29)
    with pytest.raises(ValueError):
        CicloPontoClienteOverride(cliente=_CLIENTE_A, dia_corte=0)


def test_politica_rejeita_override_duplicado_do_mesmo_cliente():
    with pytest.raises(ValueError):
        PoliticaCicloPontoPrestacao(
            version='teste',
            overrides=(
                CicloPontoClienteOverride(cliente=_CLIENTE_A, dia_corte=28),
                CicloPontoClienteOverride(cliente=_CLIENTE_A, dia_corte=1),
            ),
        )


def test_janela_fim_antes_de_inicio_rejeitada():
    with pytest.raises(ValueError):
        JanelaCicloPonto(datetime.date(2026, 6, 28), datetime.date(2026, 5, 28))


def test_competencia_formato_invalido_rejeitada():
    with pytest.raises(ValueError):
        POLITICA_CICLO_PONTO_PRESTACAO_V1.janela_para(
            _CLIENTE_A, ReferenciaCanonica('COMPETENCIA', '2026-13'),
        )
