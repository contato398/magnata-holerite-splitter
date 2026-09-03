"""Testes focados de `extracao_periodo_documental_ponto.py` (porta fiel
de app.py::_PERIODO_CARTAO_PONTO_RE — missão "IDENTIDADE TEMPORAL
DOCUMENTAL DA FOLHA/CARTÃO DE PONTO V1")."""
import datetime

from magnata_os.classificacao.extracao_periodo_documental_ponto import (
    extrair_periodo_cartao_ponto,
)


def test_extrai_periodo_com_acento_agudo_em_periodo():
    texto = 'CARTAO DE PONTO\nPeríodo: 29/05/2026 até 28/06/2026'
    assert extrair_periodo_cartao_ponto(texto) == (
        datetime.date(2026, 5, 29), datetime.date(2026, 6, 28),
    )


def test_extrai_periodo_sem_acento_variante_ate_sem_agudo():
    texto = 'Periodo: 29/05/2026 ate 28/06/2026'
    assert extrair_periodo_cartao_ponto(texto) == (
        datetime.date(2026, 5, 29), datetime.date(2026, 6, 28),
    )


def test_texto_vazio_ou_none_devolve_none():
    assert extrair_periodo_cartao_ponto('') is None
    assert extrair_periodo_cartao_ponto(None) is None


def test_sem_periodo_declarado_devolve_none():
    assert extrair_periodo_cartao_ponto('CARTAO DE PONTO qualquer coisa sem periodo') is None


def test_periodo_invertido_devolve_none():
    assert extrair_periodo_cartao_ponto('Período: 28/06/2026 até 29/05/2026') is None


def test_data_invalida_no_periodo_devolve_none():
    assert extrair_periodo_cartao_ponto('Período: 31/02/2026 até 28/06/2026') is None


def test_periodo_no_meio_de_texto_maior_ainda_e_extraido():
    texto = (
        'FUNCIONARIO: FULANO SINTETICO   N.FOLHA: 999\n'
        'Período: 29/05/2026 até 28/06/2026\n'
        '29/05/26 - Sex - C1 08:00 12:00 13:00 17:00\n'
        '30/05/26 - Sab - C1 FOLGA FOLGA FOLGA FOLGA FOLGA FOLGA'
    )
    assert extrair_periodo_cartao_ponto(texto) == (
        datetime.date(2026, 5, 29), datetime.date(2026, 6, 28),
    )


def test_mesmo_dia_inicio_e_fim_e_periodo_valido():
    assert extrair_periodo_cartao_ponto('Período: 01/06/2026 até 01/06/2026') == (
        datetime.date(2026, 6, 1), datetime.date(2026, 6, 1),
    )
