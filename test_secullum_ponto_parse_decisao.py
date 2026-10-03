"""Testes de contrato puro para as funções de parse/decisão de
`src/services/secullum_ponto.py` — sem rede, sem Airtable, sem Secullum
real. Achado da auditoria "Testes, CI e observabilidade" (2026-10-03):
este módulo tinha 17% de cobertura (990 linhas) apesar de concentrar toda
a lógica de decisão de ponto (batida ímpar, desvio de carga, bônus de
assiduidade, classificação 12x36) usada em produção.

Decisão do coordenador (2026-10-03): fixture sintética derivada das
estruturas que o próprio código já faz parse (dict colunar do /Calcular),
nunca cassette contra o Secullum real — mantém o módulo isolado de rede,
como já é hoje.
"""
from src.services.secullum_ponto import (
    EXCEPTION_POSTO_IDS,
    _analisar_batidas,
    _avaliar_bonus_assiduidade,
    _classificar_dia_12x36,
    _contar_batidas,
    _descricao_batida_impar,
    _desvio_minutos,
    _dia_e_folga_teorica,
    _e_12x36,
    _faixa_declarada,
    _faltas_minutos,
    _funcao_e_solo,
    _hhmm_para_minutos,
    _horario_noturno,
    _minutos_para_hhmm,
    _normalizar_texto,
    _primeira_entrada_minutos,
    _so_digitos,
    _status_dia_escala,
    _tag_declarada,
    _tem_intervalo,
    _trabalhou,
    detectar_inconsistencia_escala,
    periodo_folha,
)


# ── _hhmm_para_minutos / _minutos_para_hhmm ──────────────────────────────────

def test_hhmm_para_minutos_vazio_e_none():
    assert _hhmm_para_minutos(None) is None
    assert _hhmm_para_minutos('') is None


def test_hhmm_para_minutos_numerico():
    assert _hhmm_para_minutos(90) == 90
    assert _hhmm_para_minutos(90.0) == 90
    assert _hhmm_para_minutos('90') == 90


def test_hhmm_para_minutos_formato_hhmm_com_sinal():
    assert _hhmm_para_minutos('02:30') == 150
    assert _hhmm_para_minutos('-01:15') == -75
    assert _hhmm_para_minutos('+01:15') == 75


def test_hhmm_para_minutos_numero_com_virgula():
    assert _hhmm_para_minutos('1,5') == 2  # round(1.5) == 2 (half-to-even)


def test_hhmm_para_minutos_invalido_retorna_none():
    assert _hhmm_para_minutos('abc') is None
    assert _hhmm_para_minutos('12:ab') is None


def test_minutos_para_hhmm_positivo_negativo_zero():
    assert _minutos_para_hhmm(150) == '02:30'
    assert _minutos_para_hhmm(-75) == '-01:15'
    assert _minutos_para_hhmm(0) == '00:00'


# ── _so_digitos / periodo_folha ───────────────────────────────────────────

def test_so_digitos():
    assert _so_digitos('123.456.789-01') == '12345678901'
    assert _so_digitos(None) == ''
    assert _so_digitos('') == ''


def test_periodo_folha_corte_dia_28():
    assert periodo_folha(2026, 6) == ('2026-05-28', '2026-06-28')


def test_periodo_folha_virada_de_ano():
    assert periodo_folha(2026, 1) == ('2025-12-28', '2026-01-28')


# ── _contar_batidas / _trabalhou ──────────────────────────────────────────

def test_contar_batidas_conta_so_horarios_validos():
    mapa = {
        'Entrada 1': '07:00', 'Saída 1': '12:00',
        'Entrada 2': '13:00', 'Saída 2': '16:00',
        'Faltas': '00:00',
    }
    assert _contar_batidas(mapa) == 4


def test_contar_batidas_ignora_marcador_nao_horario():
    mapa = {'Entrada 1': 'FOLGA', 'Saída 1': ''}
    assert _contar_batidas(mapa) == 0


def test_contar_batidas_aceita_coluna_sem_espaco():
    assert _contar_batidas({'Entrada1': '07:00', 'Saida1': '16:00'}) == 2


def test_trabalhou_true_com_batida():
    assert _trabalhou({'Entrada 1': '07:00'}) is True


def test_trabalhou_true_com_normais_sem_batida():
    assert _trabalhou({'Normais': '08:00'}) is True


def test_trabalhou_false_sem_batida_nem_normais():
    assert _trabalhou({}) is False


# ── _desvio_minutos / _faltas_minutos ─────────────────────────────────────

def test_desvio_minutos_base_faltas():
    mapa = {'Faltas': '01:00', 'Extras': '00:30'}
    assert _desvio_minutos(mapa, base='faltas') == 60


def test_desvio_minutos_base_extras():
    mapa = {'Faltas': '01:00', 'Extras': '00:30'}
    assert _desvio_minutos(mapa, base='extras') == 30


def test_desvio_minutos_base_ambos_eh_diferenca_absoluta():
    mapa = {'Faltas': '01:00', 'Extras': '00:30'}
    assert _desvio_minutos(mapa, base='ambos') == 30


def test_desvio_minutos_sem_desvio_retorna_none():
    assert _desvio_minutos({}, base='faltas') is None


def test_faltas_minutos():
    assert _faltas_minutos({'Faltas': '00:45'}) == 45
    assert _faltas_minutos({}) == 0


# ── _horario_noturno / _normalizar_texto ──────────────────────────────────

def test_horario_noturno_true_para_turno_que_vira_a_noite():
    func = {'Horario': {'Descricao': '12x36 19h - 07h IMPAR'}}
    assert _horario_noturno(func) is True


def test_horario_noturno_false_para_turno_diurno():
    func = {'Horario': {'Descricao': 'Comercial 07h-16h'}}
    assert _horario_noturno(func) is False


def test_normalizar_texto_remove_acento_e_colapsa_separadores():
    assert _normalizar_texto('Serviços  Gerais') == 'SERVICOS GERAIS'
    assert _normalizar_texto('Auxiliar - de_ Limpeza') == 'AUXILIAR DE LIMPEZA'


# ── _funcao_e_solo / _tem_intervalo ───────────────────────────────────────

def test_funcao_e_solo_controlador_de_acesso():
    assert _funcao_e_solo('Controlador de Acesso') is True


def test_funcao_e_solo_falso_para_limpeza():
    assert _funcao_e_solo('Auxiliar de Limpeza') is False


def test_tem_intervalo_posto_de_excecao_sempre_true():
    posto_excecao = next(iter(EXCEPTION_POSTO_IDS))
    assert _tem_intervalo({posto_excecao}, 'Controlador de Acesso') is True


def test_tem_intervalo_funcao_solo_sem_posto_excecao_eh_false():
    assert _tem_intervalo(set(), 'Controlador de Acesso') is False


def test_tem_intervalo_funcao_comum_sem_posto_excecao_eh_true():
    assert _tem_intervalo(set(), 'Auxiliar de Limpeza') is True


# ── _dia_e_folga_teorica ───────────────────────────────────────────────────

def test_dia_e_folga_teorica_marcador_folga():
    assert _dia_e_folga_teorica({'Entrada 1': 'FOLGA'}) is True


def test_dia_e_folga_teorica_marcador_feriado_case_insensitive():
    assert _dia_e_folga_teorica({'Entrada 1': 'Feriado'}) is True


def test_dia_e_folga_teorica_falso_com_horario_real():
    assert _dia_e_folga_teorica({'Entrada 1': '07:00'}) is False


# ── _tag_declarada / _faixa_declarada / _primeira_entrada_minutos ────────

def test_tag_declarada_impar_tem_prioridade_sobre_substring_par():
    assert _tag_declarada('Turno IMPAR') == 'IMPAR'


def test_tag_declarada_par():
    assert _tag_declarada('Turno PAR') == 'PAR'


def test_tag_declarada_nenhuma():
    assert _tag_declarada('Comercial') is None


def test_faixa_declarada_extrai_horas():
    assert _faixa_declarada('12x36 19h - 07h IMPAR') == (19, 7)


def test_faixa_declarada_sem_faixa_retorna_none_none():
    assert _faixa_declarada('Comercial') == (None, None)


def test_primeira_entrada_minutos_usa_entrada_1_nao_o_minimo():
    # Turno noturno: Entrada 2 (volta do intervalo, 01h) é numericamente
    # menor que Entrada 1 (19h) sem ser o início do turno.
    mapa = {'Entrada 1': '19:00', 'Entrada 2': '01:00', 'Saída 1': '20:00'}
    assert _primeira_entrada_minutos(mapa) == 19 * 60


def test_primeira_entrada_minutos_sem_entrada_retorna_none():
    assert _primeira_entrada_minutos({'Saída 1': '16:00'}) is None


# ── detectar_inconsistencia_escala ────────────────────────────────────────

def _dias_status_alternados(trabalho_em_dias_pares: bool) -> dict:
    status = {}
    for dia in range(1, 11):
        data = f'2026-06-{dia:02d}'
        par = dia % 2 == 0
        trabalha = par if trabalho_em_dias_pares else not par
        status[data] = 'trabalho' if trabalha else 'folga'
    return status


def test_detectar_inconsistencia_escala_paridade_invertida():
    # Rótulo diz IMPAR, mas quem de fato trabalha são os dias PARES.
    dias_status = _dias_status_alternados(trabalho_em_dias_pares=True)
    resultado = detectar_inconsistencia_escala('12x36 ... IMPAR', dias_status, {})
    assert resultado['tag_declarada'] == 'IMPAR'
    assert resultado['inconsistencias']
    assert 'paridade' in resultado['inconsistencias'][0].lower()


def test_detectar_inconsistencia_escala_paridade_consistente_sem_achado():
    # Rótulo diz PAR e quem trabalha são de fato os dias pares — sem inconsistência.
    dias_status = _dias_status_alternados(trabalho_em_dias_pares=True)
    resultado = detectar_inconsistencia_escala('12x36 ... PAR', dias_status, {})
    assert resultado['inconsistencias'] == []


def test_detectar_inconsistencia_escala_faixa_de_horario_diferente_do_real():
    dias_status = {f'2026-06-{d:02d}': 'trabalho' for d in range(1, 6)}
    dias = {d: {'Entrada 1': '19:00'} for d in dias_status}
    resultado = detectar_inconsistencia_escala('Comercial 07h - 16h', dias_status, dias)
    assert resultado['faixa_declarada_inicio'] == 7
    assert resultado['inconsistencias']
    assert 'turno' in resultado['inconsistencias'][0].lower() or 'horário' in resultado['inconsistencias'][0].lower()


def test_detectar_inconsistencia_escala_sem_tag_nem_faixa_nao_acusa_nada():
    dias_status = {'2026-06-01': 'trabalho'}
    resultado = detectar_inconsistencia_escala('Horário Especial', dias_status, {})
    assert resultado['tag_declarada'] is None
    assert resultado['faixa_declarada_inicio'] is None
    assert resultado['inconsistencias'] == []


# ── _analisar_batidas / _descricao_batida_impar ───────────────────────────

def test_analisar_batidas_completa_e_par():
    mapa = {'Entrada 1': '07:00', 'Saída 1': '12:00', 'Entrada 2': '13:00', 'Saída 2': '16:00'}
    resultado = _analisar_batidas(mapa)
    assert resultado == {'n': 4, 'impar': False, 'lado_faltante': None}


def test_analisar_batidas_impar_falta_saida():
    # Última marcação registrada (maior número) é uma ENTRADA → faltou a SAÍDA.
    mapa = {'Entrada 1': '07:00', 'Saída 1': '12:00', 'Entrada 2': '13:00'}
    resultado = _analisar_batidas(mapa)
    assert resultado == {'n': 3, 'impar': True, 'lado_faltante': 'saida'}


def test_analisar_batidas_impar_falta_entrada():
    # Única marcação é uma SAÍDA → faltou a ENTRADA.
    mapa = {'Saída 1': '16:00'}
    resultado = _analisar_batidas(mapa)
    assert resultado == {'n': 1, 'impar': True, 'lado_faltante': 'entrada'}


def test_analisar_batidas_sem_nenhuma_marcacao():
    assert _analisar_batidas({}) == {'n': 0, 'impar': False, 'lado_faltante': None}


def test_descricao_batida_impar_diurno_falta_saida():
    ab = {'n': 3, 'impar': True, 'lado_faltante': 'saida'}
    texto = _descricao_batida_impar(ab, noturno=False, data_dia='2026-06-10')
    assert '3 batida(s) no dia 2026-06-10' in texto
    assert 'SAÍDA' in texto
    assert 'noite do dia anterior' not in texto


def test_descricao_batida_impar_noturno_falta_entrada():
    ab = {'n': 1, 'impar': True, 'lado_faltante': 'entrada'}
    texto = _descricao_batida_impar(ab, noturno=True, data_dia='2026-06-10')
    assert 'ENTRADA' in texto
    assert 'noite do dia anterior' in texto


# ── _avaliar_bonus_assiduidade ─────────────────────────────────────────────

def test_avaliar_bonus_assiduidade_elegivel_sem_ocorrencia():
    dias_status = {'2026-06-01': 'trabalho', '2026-06-02': 'folga'}
    dias = {
        '2026-06-01': {'Entrada 1': '07:00', 'Saída 1': '16:00', 'Atras.': '00:00', 'Adian.': '00:00'},
        '2026-06-02': {},
    }
    resultado = _avaliar_bonus_assiduidade(dias_status, dias)
    assert resultado['elegivel'] is True
    assert resultado['motivos'] == []


def test_avaliar_bonus_assiduidade_perde_por_atraso_acima_da_tolerancia():
    dias_status = {'2026-06-01': 'trabalho'}
    dias = {'2026-06-01': {'Entrada 1': '07:10', 'Saída 1': '16:00', 'Atras.': '00:10'}}
    resultado = _avaliar_bonus_assiduidade(dias_status, dias)
    assert resultado['elegivel'] is False
    assert any('Atraso' in m for m in resultado['motivos'])


def test_avaliar_bonus_assiduidade_falta_nao_perdoada():
    dias_status = {'2026-06-01': 'trabalho'}
    dias = {'2026-06-01': {'Faltas': '08:00'}}
    resultado = _avaliar_bonus_assiduidade(dias_status, dias)
    assert resultado['elegivel'] is False
    assert 'Falta em 2026-06-01' in resultado['motivos']


def test_avaliar_bonus_assiduidade_falta_perdoada_preserva_bonus():
    dias_status = {'2026-06-01': 'trabalho'}
    dias = {'2026-06-01': {'Faltas': '08:00'}}
    resultado = _avaliar_bonus_assiduidade(dias_status, dias, perdoados={'2026-06-01'})
    assert resultado['elegivel'] is True


def test_avaliar_bonus_assiduidade_zelo_perdido():
    dias_status = {'2026-06-01': 'trabalho'}
    dias = {'2026-06-01': {'Entrada 1': '07:00', 'Saída 1': '16:00'}}
    resultado = _avaliar_bonus_assiduidade(dias_status, dias, zelo_perdido={'2026-06-01'})
    assert resultado['elegivel'] is False
    assert any('falta de zelo' in m for m in resultado['motivos'])


# ── _e_12x36 / _status_dia_escala / _classificar_dia_12x36 ───────────────

def test_e_12x36():
    assert _e_12x36('12x36 Diurno') is True
    assert _e_12x36('5x2 Comercial') is False


def test_status_dia_escala_feriado_folga_trabalho():
    assert _status_dia_escala({'Entrada 1': 'FERIADO'}) == 'feriado'
    assert _status_dia_escala({'Entrada 1': 'FOLGA'}) == 'folga'
    assert _status_dia_escala({'Entrada 1': '07:00'}) == 'trabalho'


def test_classificar_dia_12x36_feriado_sem_batidas():
    classificacao, status, obs = _classificar_dia_12x36(
        '2026-06-10', {'Entrada 1': 'FERIADO'}, prev_status='folga',
    )
    assert classificacao == 'FERIADO_ESCALA_REVISAR'
    assert status == 'feriado'
    assert 'sem batidas' in obs


def test_classificar_dia_12x36_folga_sem_trabalho_eh_normal_silencioso():
    classificacao, status, obs = _classificar_dia_12x36(
        '2026-06-10', {'Entrada 1': 'FOLGA'}, prev_status='trabalho',
    )
    assert (classificacao, status, obs) == ('NORMAL', 'folga', '')


def test_classificar_dia_12x36_atraso_sem_acao():
    mapa = {'Entrada 1': '07:10', 'Saída 1': '16:00', 'Atras.': '00:10'}
    classificacao, status, obs = _classificar_dia_12x36('2026-06-10', mapa, prev_status='folga')
    assert classificacao == 'ATRASO_NORMAL_SEM_ACAO'
    assert status == 'trabalho'
    assert 'ATENÇÃO' not in obs


def test_classificar_dia_12x36_atraso_consecutivo_alerta_na_observacao():
    mapa = {'Entrada 1': '07:10', 'Saída 1': '16:00', 'Atras.': '00:10'}
    _, _, obs = _classificar_dia_12x36('2026-06-10', mapa, prev_status='trabalho')
    assert 'ATENÇÃO' in obs


def test_classificar_dia_12x36_alternancia_quebrada():
    mapa = {'Entrada 1': '07:00', 'Saída 1': '16:00'}
    classificacao, status, obs = _classificar_dia_12x36('2026-06-10', mapa, prev_status='trabalho')
    assert classificacao == 'ALTERNANCIA_QUEBRADA_URGENTE'
    assert status == 'trabalho'


def test_classificar_dia_12x36_batida_faltante():
    mapa = {'Entrada 1': '07:00'}
    classificacao, status, obs = _classificar_dia_12x36('2026-06-10', mapa, prev_status='folga')
    assert classificacao == 'BATIDA_FALTANTE'
    assert 'SAÍDA' in obs


def test_classificar_dia_12x36_folga_trabalhada():
    mapa = {'Entrada 1': 'FOLGA', 'Entrada 2': '07:00', 'Saída 2': '16:00'}
    classificacao, status, obs = _classificar_dia_12x36('2026-06-10', mapa, prev_status='folga')
    assert classificacao == 'NORMAL'
    assert status == 'folga'
    assert 'Folga trabalhada' in obs


def test_classificar_dia_12x36_dia_normal():
    mapa = {'Entrada 1': '07:00', 'Saída 1': '16:00'}
    classificacao, status, obs = _classificar_dia_12x36('2026-06-10', mapa, prev_status='folga')
    assert (classificacao, status, obs) == ('NORMAL', 'trabalho', '')
