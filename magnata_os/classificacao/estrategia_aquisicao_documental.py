"""Estratégia de aquisição complementar (missão "AUTOMAÇÃO DOCUMENTAL
REAL V1", §17: preparar a arquitetura para que uma
`NecessidadeDocumentoPrestacao` saiba qual é a PRÓXIMA fonte a
consultar — sem executar nenhuma busca live aqui, nenhum Gmail, nenhuma
automação externa nesta missão).

Reaproveita o campo já existente `NecessidadeDocumentoPrestacao.fontes_
ainda_nao_consultadas` (`ciclo_prestacao.py`) — nunca um campo novo.
Ordem de fallback FIXA e documentada (nunca inventada por chamada):
Airtable -> Gmail -> armazenamento documental -> humano (quando as
fontes se esgotam, cláusula pétrea: nunca inventar uma fonte nova)."""
from __future__ import annotations

from typing import Optional

from .ciclo_prestacao import NecessidadeDocumentoPrestacao

ORDEM_FALLBACK_AQUISICAO = ('airtable', 'gmail', 'armazenamento_documental')


def proxima_fonte_a_consultar(necessidade: NecessidadeDocumentoPrestacao) -> Optional[str]:
    """Devolve a PRÓXIMA fonte (a primeira, na ordem fixa acima, que
    ainda está em `fontes_ainda_nao_consultadas`) — `None` quando todas
    já foram tentadas (nesse ponto, a necessidade só pode ir para
    revisão humana; nunca inventa uma fonte fora da ordem fixa). Nunca
    executa a busca em si — só decide qual fonte tentar a seguir."""
    for fonte in ORDEM_FALLBACK_AQUISICAO:
        if fonte in necessidade.fontes_ainda_nao_consultadas:
            return fonte
    return None
