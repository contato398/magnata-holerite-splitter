"""
Teste local (offline) para a Fase 2 da automação de Folha de Ponto ("Cartão
Ponto" — formato Secullum Ponto Web).

NÃO está conectado ao pipeline de produção ainda. Objetivo: validar
`extrair_cartao_ponto()` contra um texto baseado no PDF real de exemplo
("Cartão Ponto adriano angarten.pdf").

Rodar: python test_leitura_ponto.py
"""

import app


# ── Texto baseado no PDF real "Cartão Ponto adriano angarten.pdf" ─────────────
TEXTO_CARTAO_PONTO_REAL = """
MAGNATA PORTARIA E SERVIÇOS LTDA
CNPJ: 17.987.187/0001-61

CPF: ADMISSÃO:
123.456.789-00

ADRIANO DE ALBUQUERQUE ANGARTEN

Período: 28/04/2026 até 28/05/2026

28/04/26 - Ter - C2 FOLGA FOLGA FOLGA FOLGA FOLGA FOLGA
29/04/26 - Qua - C1 18:56 01:00 01:53 09:05
30/04/26 - Qui - C1 18:50 00:58 01:50 09:02

LEGENDA DOS CICLOS
Ciclo 1  19:00  01:00  02:00  07:00
Ciclo 2  FOLGA  FOLGA  FOLGA  FOLGA
"""


# ── Texto sem nenhuma linha reconhecida (PDF não reconhecido) ─────────────────
TEXTO_SEM_CARTAO = """
RELATÓRIO GERENCIAL - SEM DADOS DE PONTO
Nenhuma informação disponível para este período.
"""


def test_dias_normais_extraidos_corretamente():
    resultado = app.extrair_cartao_ponto(TEXTO_CARTAO_PONTO_REAL)
    dias = resultado['dias']
    assert len(dias) == 3

    dia29 = dias[1]
    assert dia29['data'] == '29/04/2026'
    assert dia29['dia_semana'] == 'Qua'
    assert dia29['ciclo'] == 'C1'
    assert dia29['folga'] is False
    assert dia29['entrada_1'] == '18:56'
    assert dia29['saida_1'] == '01:00'
    assert dia29['entrada_2'] == '01:53'
    assert dia29['saida_2'] == '09:05'
    assert dia29['entrada_3'] is None
    assert dia29['saida_3'] is None
    print('OK: dia normal (turno noturno) extraído corretamente')


def test_dia_folga_detectado():
    resultado = app.extrair_cartao_ponto(TEXTO_CARTAO_PONTO_REAL)
    dia28 = resultado['dias'][0]
    assert dia28['data'] == '28/04/2026'
    assert dia28['dia_semana'] == 'Ter'
    assert dia28['ciclo'] == 'C2'
    assert dia28['folga'] is True
    assert dia28['entrada_1'] is None
    assert dia28['saida_3'] is None
    print('OK: dia de FOLGA detectado, horários ficam None')


def test_legenda_dos_ciclos_nao_e_confundida_com_dia():
    resultado = app.extrair_cartao_ponto(TEXTO_CARTAO_PONTO_REAL)
    datas = [d['data'] for d in resultado['dias']]
    assert len(resultado['dias']) == 3
    assert '28/04/2026' in datas and '29/04/2026' in datas and '30/04/2026' in datas
    print('OK: linhas da "LEGENDA DOS CICLOS" não são confundidas com dias')


def test_periodo_extraido():
    resultado = app.extrair_cartao_ponto(TEXTO_CARTAO_PONTO_REAL)
    assert resultado['periodo_inicio'] == '28/04/2026'
    assert resultado['periodo_fim'] == '28/05/2026'
    print('OK: período de referência extraído')


def test_cpf_extraido():
    resultado = app.extrair_cartao_ponto(TEXTO_CARTAO_PONTO_REAL)
    assert resultado['cpf'] == '123.456.789-00'
    print('OK: CPF extraído via extrair_cpf existente')


def test_texto_sem_cartao_retorna_vazio():
    resultado = app.extrair_cartao_ponto(TEXTO_SEM_CARTAO)
    assert resultado['dias'] == []
    assert resultado['cpf'] is None
    assert resultado['periodo_inicio'] is None
    print('OK: texto sem cartão de ponto retorna dias=[] e campos None, sem erro')


if __name__ == '__main__':
    test_dias_normais_extraidos_corretamente()
    test_dia_folga_detectado()
    test_legenda_dos_ciclos_nao_e_confundida_com_dia()
    test_periodo_extraido()
    test_cpf_extraido()
    test_texto_sem_cartao_retorna_vazio()
    print('\nTodos os testes (Fase 2 - Cartão Ponto) passaram.')
