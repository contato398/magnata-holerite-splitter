"""Testes de `estrategia_aquisicao_documental.py` (missão "AUTOMAÇÃO
DOCUMENTAL REAL V1", §17)."""
from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.estrategia_aquisicao_documental import proxima_fonte_a_consultar

_CLIENTE = ReferenciaCanonica('CLIENTE', 'rec_cliente')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')


def _necessidade(fontes):
    return NecessidadeDocumentoPrestacao(
        cliente=_CLIENTE, competencia=_COMPETENCIA, tipo_documental='FGTS',
        motivo_exigencia='teste', fontes_ainda_nao_consultadas=fontes,
    )


def test_ordem_fixa_airtable_primeiro():
    necessidade = _necessidade(('airtable', 'gmail', 'armazenamento_documental'))
    assert proxima_fonte_a_consultar(necessidade) == 'airtable'


def test_pula_fontes_ja_consultadas():
    necessidade = _necessidade(('gmail', 'armazenamento_documental'))
    assert proxima_fonte_a_consultar(necessidade) == 'gmail'


def test_todas_fontes_esgotadas_devolve_none():
    necessidade = _necessidade(())
    assert proxima_fonte_a_consultar(necessidade) is None


def test_nunca_inventa_fonte_fora_da_ordem_fixa():
    necessidade = _necessidade(('fonte_desconhecida',))
    assert proxima_fonte_a_consultar(necessidade) is None
