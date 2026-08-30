"""Estratégia de aquisição complementar (missão "AUTOMAÇÃO DOCUMENTAL
REAL V1", §17 + ADENDO OBRIGATÓRIO item 1: preparar a arquitetura para
que uma `NecessidadeDocumentoPrestacao` saiba qual é a PRÓXIMA fonte a
consultar — sem executar nenhuma busca live aqui, nenhum Gmail, nenhuma
automação externa nesta missão).

Reaproveita o campo já existente `NecessidadeDocumentoPrestacao.fontes_
ainda_nao_consultadas` (`ciclo_prestacao.py`) — nunca um campo novo.

CORREÇÃO (ADENDO OBRIGATÓRIO, item 1): a ordem de fallback NUNCA é uma
constante fixa gravada no motor com o Airtable em primeiro lugar — isso
criaria uma precedência estrutural do Airtable, contrariando a cláusula
pétrea "Airtable é bridge/fonte substituível, nunca cérebro nem
dependência preferencial do core" (§13/§0 da missão). A ordem é sempre
um parâmetro explícito (`ordem_fontes`), injetado por quem chama —
tipicamente uma política/config de composição, nunca hardcoded aqui.
Isso permite operar `Gmail -> storage`, `storage -> Gmail`, ou
qualquer conjunto permitido, sem alterar este módulo nem o domínio de
classificação. Uma ordem PADRÃO opcional continua disponível
(`ORDEM_FALLBACK_PADRAO_V1`) — mas é só uma sugestão de composição,
nunca aplicada automaticamente por `proxima_fonte_a_consultar` quando
uma ordem explícita é informada."""
from __future__ import annotations

from typing import Optional, Sequence

from .ciclo_prestacao import NecessidadeDocumentoPrestacao

# Sugestão de composição, NUNCA uma prioridade estrutural do motor --
# quem monta o corredor real escolhe se usa esta ordem, uma diferente,
# ou nenhuma (informando `ordem_fontes` explicitamente sempre que a
# composição real divergir desta sugestão).
ORDEM_FALLBACK_PADRAO_V1: Sequence[str] = ('airtable', 'gmail', 'armazenamento_documental')


def proxima_fonte_a_consultar(
    necessidade: NecessidadeDocumentoPrestacao,
    ordem_fontes: Sequence[str] = ORDEM_FALLBACK_PADRAO_V1,
) -> Optional[str]:
    """Devolve a PRÓXIMA fonte (a primeira, em `ordem_fontes` — SEMPRE
    informada por quem chama, nunca uma constante estrutural do
    domínio — que ainda está em `fontes_ainda_nao_consultadas`) —
    `None` quando todas já foram tentadas (nesse ponto, a necessidade
    só pode ir para revisão humana; nunca inventa uma fonte fora de
    `ordem_fontes`). Nunca executa a busca em si — só decide qual fonte
    tentar a seguir, dentro do conjunto/ordem que a composição real
    autorizou para este ciclo."""
    for fonte in ordem_fontes:
        if fonte in necessidade.fontes_ainda_nao_consultadas:
            return fonte
    return None
