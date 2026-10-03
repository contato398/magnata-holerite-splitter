"""Testes de contrato puro para os parsers de `src/ingestao_secullum.py`
(AFD, Espelho de Ponto em PDF, Relatório de Inconsistências) e para
`horario_para_cargo` — sem rede, sem Airtable. Achado da auditoria
"Testes, CI e observabilidade" (2026-10-03): este módulo tinha 18% de
cobertura apesar de ser o ponto de entrada de dado real de ponto
(AFD/PDF/relatório colado) para o Airtable.

O parser de PDF (`_parse_espelho_pdf`) usa `pdfplumber` sobre bytes reais
de PDF — igual ao padrão já usado em `test_servico_lote_roteamento_shadow.py`,
construímos o PDF sintético com `reportlab` e pulamos explicitamente (nunca
escondido como "passou") se `pdfplumber` estiver quebrado neste ambiente.
"""
import io

import pytest

from src.ingestao_secullum import (
    F_ENTRADA,
    F_RETORNO_AL,
    F_SAIDA,
    F_SAIDA_AL,
    HORARIO_PADRAO,
    _batidas_em_campos,
    _parse_afd,
    _parse_espelho_pdf,
    _parse_inconsistencias,
    horario_para_cargo,
)

try:
    import pdfplumber  # noqa: F401
    _PDFPLUMBER_FUNCIONAL = True
except BaseException:
    _PDFPLUMBER_FUNCIONAL = False

_MOTIVO_SKIP_PDFPLUMBER = (
    "pdfplumber quebrado neste ambiente (pyo3_runtime.PanicException / "
    "_cffi_backend ausente) — falha de ambiente pré-existente, não do código novo"
)


# ── horario_para_cargo ─────────────────────────────────────────────────────

def test_horario_para_cargo_mapeado_com_valor_confirmado():
    assert horario_para_cargo('Auxiliar de Limpeza') == 6
    assert horario_para_cargo('Serviços Gerais') == 6


def test_horario_para_cargo_mapeado_mas_ainda_sem_numero_cai_no_padrao():
    # 'CONTROLADOR DE ACESSO' está no mapa com valor None (ainda não
    # preenchido via GET /horarios) — cai no fallback, não em erro.
    assert horario_para_cargo('Controlador de Acesso') == HORARIO_PADRAO


def test_horario_para_cargo_nao_mapeado_cai_no_padrao():
    assert horario_para_cargo('Cargo Inexistente') == HORARIO_PADRAO


def test_horario_para_cargo_normaliza_acento_e_caixa():
    assert horario_para_cargo('zelador') == horario_para_cargo('ZELADOR')


# ── _parse_afd ───────────────────────────────────────────────────────────

def _linha_afd(data='20260601', hora='0700', pis='0000000123'):
    # Tipo 3 (marcação de ponto), Portaria 1.510/2009: 3 YYYYMMDD HHMM PIS...
    return f'3{data}{hora}{pis}0001'


def test_parse_afd_linha_tipo_3_valida():
    resultado = _parse_afd(_linha_afd())
    assert resultado == [{'pis': '0000000123', 'data': '2026-06-01', 'hora': '07:00'}]


def test_parse_afd_ignora_linhas_de_outro_tipo():
    conteudo = '1cabecalho_irrelevante_curta\n' + _linha_afd()
    resultado = _parse_afd(conteudo)
    assert len(resultado) == 1
    assert resultado[0]['hora'] == '07:00'


def test_parse_afd_ignora_linha_curta_demais():
    assert _parse_afd('3curtodemais') == []


def test_parse_afd_multiplas_linhas_mesmo_pis():
    conteudo = '\n'.join([
        _linha_afd(hora='0700'),
        _linha_afd(hora='1200'),
        _linha_afd(hora='1300'),
        _linha_afd(hora='1600'),
    ])
    resultado = _parse_afd(conteudo)
    assert [r['hora'] for r in resultado] == ['07:00', '12:00', '13:00', '16:00']


def test_parse_afd_conteudo_vazio():
    assert _parse_afd('') == []


# ── _parse_inconsistencias ─────────────────────────────────────────────────

def test_parse_inconsistencias_um_funcionario():
    texto = (
        'NOME: JOAO DA SILVA N.FOLHA: 123\n'
        'SUBTOTAL 01:30 00:15 02:00 05:00 01:00 00:30\n'
    )
    resultado = _parse_inconsistencias(texto)
    assert resultado == [{
        'nome': 'JOAO DA SILVA', 'n_folha': '123',
        'faltas': '01:30', 'atrasos': '00:15', 'extras': '02:00', 'banco': '05:00',
    }]


def test_parse_inconsistencias_varios_funcionarios():
    texto = (
        'NOME: JOAO DA SILVA N.FOLHA: 123\n'
        'SUBTOTAL 01:30 00:15 02:00 05:00 01:00 00:30\n'
        'NOME: MARIA SOUZA N.FOLHA: 456\n'
        'SUBTOTAL 00:00 00:00 00:00 00:00 00:00 00:00\n'
    )
    resultado = _parse_inconsistencias(texto)
    assert [f['n_folha'] for f in resultado] == ['123', '456']
    assert resultado[1]['faltas'] == '00:00'


def test_parse_inconsistencias_ignora_cabecalho_com_subtotal_ou_horario_no_nome():
    # Guard explícito no parser: uma linha NOME que contenha "SUBTOTAL" ou
    # "HORARIO" é cabeçalho de coluna, não um funcionário de verdade.
    texto = 'NOME: SUBTOTAL HORARIO N.FOLHA: 999\nNOME: JOAO DA SILVA N.FOLHA: 123\nSUBTOTAL 00:00 00:00 00:00 00:00 00:00 00:00\n'
    resultado = _parse_inconsistencias(texto)
    assert len(resultado) == 1
    assert resultado[0]['n_folha'] == '123'


def test_parse_inconsistencias_funcionario_sem_subtotal_ainda_aparece_incompleto():
    # Um NOME sem SUBTOTAL correspondente (ex.: relatório colado truncado)
    # ainda deve aparecer na lista, sem os totais — nunca descartado em
    # silêncio (achado novo desta verificação: comportamento implícito do
    # loop final `if atual: funcionarios.append(atual)`, agora coberto).
    texto = 'NOME: JOAO DA SILVA N.FOLHA: 123\n'
    resultado = _parse_inconsistencias(texto)
    assert resultado == [{'nome': 'JOAO DA SILVA', 'n_folha': '123'}]


def test_parse_inconsistencias_texto_vazio():
    assert _parse_inconsistencias('') == []


# ── _batidas_em_campos ─────────────────────────────────────────────────────

def test_batidas_em_campos_uma_batida_so_entrada():
    campos = _batidas_em_campos('2026-06-01', ['07:00'])
    assert campos == {F_ENTRADA: '2026-06-01T07:00:00-03:00'}


def test_batidas_em_campos_duas_batidas_entrada_e_saida():
    campos = _batidas_em_campos('2026-06-01', ['07:00', '16:00'])
    assert campos == {
        F_ENTRADA: '2026-06-01T07:00:00-03:00',
        F_SAIDA: '2026-06-01T16:00:00-03:00',
    }


def test_batidas_em_campos_tres_batidas_jornada_truncada():
    campos = _batidas_em_campos('2026-06-01', ['07:00', '12:00', '13:00'])
    assert campos == {
        F_ENTRADA: '2026-06-01T07:00:00-03:00',
        F_SAIDA_AL: '2026-06-01T12:00:00-03:00',
        F_RETORNO_AL: '2026-06-01T13:00:00-03:00',
    }


def test_batidas_em_campos_quatro_batidas_jornada_completa():
    campos = _batidas_em_campos('2026-06-01', ['07:00', '12:00', '13:00', '16:00'])
    assert campos == {
        F_ENTRADA: '2026-06-01T07:00:00-03:00',
        F_SAIDA_AL: '2026-06-01T12:00:00-03:00',
        F_RETORNO_AL: '2026-06-01T13:00:00-03:00',
        F_SAIDA: '2026-06-01T16:00:00-03:00',
    }


def test_batidas_em_campos_cinco_batidas_ignora_extras():
    # 5ª+ batida (re-batida por erro) não tem campo próprio — mesmo
    # resultado que 4 batidas.
    campos_4 = _batidas_em_campos('2026-06-01', ['07:00', '12:00', '13:00', '16:00'])
    campos_5 = _batidas_em_campos('2026-06-01', ['07:00', '12:00', '13:00', '16:00', '17:30'])
    assert campos_5 == campos_4


def test_batidas_em_campos_sem_batida():
    assert _batidas_em_campos('2026-06-01', []) == {}


# ── _parse_espelho_pdf ──────────────────────────────────────────────────────

def _pdf_minimo_com_texto(linhas: list) -> bytes:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    y = 720
    for linha in linhas:
        c.drawString(72, y, linha)
        y -= 16
    c.save()
    return buffer.getvalue()


@pytest.mark.skipif(not _PDFPLUMBER_FUNCIONAL, reason=_MOTIVO_SKIP_PDFPLUMBER)
def test_parse_espelho_pdf_extrai_cabecalho_e_batidas():
    pdf_bytes = _pdf_minimo_com_texto([
        'FUNCIONARIO: JOAO DA SILVA N.FOLHA: 123',
        '01/06 SEG 07:00 12:00 13:00 16:00',
        '02/06 TER 07:05 12:00 13:00 16:10',
    ])
    registros = _parse_espelho_pdf(pdf_bytes)
    assert len(registros) == 2
    assert registros[0]['n_folha'] == '123'
    assert registros[0]['nome'] == 'JOAO DA SILVA'
    assert registros[0]['data_dm'] == '01/06'
    assert registros[0]['batidas'] == ['07:00', '12:00', '13:00', '16:00']
    assert registros[1]['data_dm'] == '02/06'


@pytest.mark.skipif(not _PDFPLUMBER_FUNCIONAL, reason=_MOTIVO_SKIP_PDFPLUMBER)
def test_parse_espelho_pdf_ignora_dia_de_falta_total_sem_batida():
    pdf_bytes = _pdf_minimo_com_texto([
        'FUNCIONARIO: JOAO DA SILVA N.FOLHA: 123',
        '01/06 SEG 07:00 12:00 13:00 16:00',
        '02/06 TER F',
    ])
    registros = _parse_espelho_pdf(pdf_bytes)
    assert len(registros) == 1
    assert registros[0]['data_dm'] == '01/06'


@pytest.mark.skipif(not _PDFPLUMBER_FUNCIONAL, reason=_MOTIVO_SKIP_PDFPLUMBER)
def test_parse_espelho_pdf_sem_cabecalho_nao_produz_registro():
    # Linha de dia antes de qualquer cabeçalho FUNCIONARIO/N.FOLHA é
    # descartada (n_folha_atual ainda None) — nunca cai no funcionário errado.
    pdf_bytes = _pdf_minimo_com_texto(['01/06 SEG 07:00 12:00 13:00 16:00'])
    assert _parse_espelho_pdf(pdf_bytes) == []


def test_parse_espelho_pdf_pdf_invalido_levanta_valueerror():
    with pytest.raises(ValueError):
        _parse_espelho_pdf(b'isto-nao-e-um-pdf')
