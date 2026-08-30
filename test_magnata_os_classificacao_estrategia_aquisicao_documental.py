"""Testes de `estrategia_aquisicao_documental.py` (missão "AUTOMAÇÃO
DOCUMENTAL REAL V1", §17 + ADENDO OBRIGATÓRIO item 1: a ordem de
fontes é SEMPRE injetada por quem chama, nunca uma constante estrutural
do domínio com o Airtable em primeiro lugar)."""
from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.estrategia_aquisicao_documental import (
    ORDEM_FALLBACK_PADRAO_V1,
    proxima_fonte_a_consultar,
)

_CLIENTE = ReferenciaCanonica('CLIENTE', 'rec_cliente')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')


def _necessidade(fontes):
    return NecessidadeDocumentoPrestacao(
        cliente=_CLIENTE, competencia=_COMPETENCIA, tipo_documental='FGTS',
        motivo_exigencia='teste', fontes_ainda_nao_consultadas=fontes,
    )


def test_ordem_padrao_e_so_uma_sugestao_nao_obrigatoria():
    necessidade = _necessidade(('airtable', 'gmail', 'armazenamento_documental'))
    assert proxima_fonte_a_consultar(necessidade) == 'airtable'  # usa a ordem padrão só quando nenhuma outra foi informada


def test_pula_fontes_ja_consultadas():
    necessidade = _necessidade(('gmail', 'armazenamento_documental'))
    assert proxima_fonte_a_consultar(necessidade) == 'gmail'


def test_todas_fontes_esgotadas_devolve_none():
    necessidade = _necessidade(())
    assert proxima_fonte_a_consultar(necessidade) is None


def test_nunca_inventa_fonte_fora_da_ordem_informada():
    necessidade = _necessidade(('fonte_desconhecida',))
    assert proxima_fonte_a_consultar(necessidade) is None


# ============================================================================
# ADENDO OBRIGATÓRIO, item 5.A/5.B — nenhuma precedência estrutural do
# Airtable: a estratégia funciona com QUALQUER conjunto/ordem de fontes
# injetada, sem tocar o domínio.
# ============================================================================

def test_a_estrategia_funciona_sem_airtable_na_lista():
    """Fontes disponíveis = só Gmail + armazenamento (Airtable nem
    existe neste ciclo) -- funciona normalmente, nenhuma dependência
    estrutural do Airtable."""
    necessidade = _necessidade(('gmail', 'armazenamento_documental'))
    assert proxima_fonte_a_consultar(necessidade, ordem_fontes=('gmail', 'armazenamento_documental')) == 'gmail'


def test_b_ordem_configurada_armazenamento_antes_de_gmail():
    """Composição real escolheu armazenamento -> Gmail (inverso da
    sugestão padrão) -- respeitado sem qualquer mudança neste módulo
    nem no domínio de classificação."""
    necessidade = _necessidade(('gmail', 'armazenamento_documental'))
    resultado = proxima_fonte_a_consultar(
        necessidade, ordem_fontes=('armazenamento_documental', 'gmail'))
    assert resultado == 'armazenamento_documental'


def test_ordem_padrao_v1_e_so_uma_constante_de_sugestao_nunca_hardcoded_na_funcao():
    """A função aceita QUALQUER ordem -- `ORDEM_FALLBACK_PADRAO_V1` é
    só o valor default do parâmetro, nunca uma lógica interna fixa."""
    necessidade = _necessidade(('airtable', 'gmail'))
    # Uma ordem que NUNCA inclui 'airtable' -- prova que o Airtable não
    # tem tratamento especial algum dentro da função.
    assert proxima_fonte_a_consultar(necessidade, ordem_fontes=('gmail',)) == 'gmail'
    assert ORDEM_FALLBACK_PADRAO_V1[0] == 'airtable'  # sugestão default documentada, nunca obrigatória
