"""Utilitários PUROS e pequenos, compartilhados entre adapters Airtable
read-only deste pacote (missão "...ADAPTERS REAIS DE PRODUÇÃO — FONTE
UNIDADE_POSTO + FONTE CANDIDATOS DE RELAÇÃO V1").

PROMOVIDOS de `airtable_vinculos_prestacao.py` (onde viviam como
funções privadas, `_ids_vinculados`/`_escapar_formula`/`_filtro_ids`)
para este módulo neutro, novo, quando um segundo adapter
(`airtable_unidade_posto_prestacao.py`) precisou da MESMA lógica de
parsing de campo de link do Airtable e de montagem de filtro por
RECORD_ID -- nunca duplicada, mesmo princípio já usado no repositório
para `_extrair_texto_pdf` (promovida de `importacao_lote/orquestrador.py`
para `classificacao/roteamento_documental.py` quando um segundo
consumidor precisou dela). Deliberadamente um módulo NOVO, não uma
edição de `airtable_leitura.py` (arquivo com múltiplos consumidores já
existentes e disciplina própria documentada em seu próprio CLAUDE.md)
-- menor superfície de risco para esta promoção."""
from __future__ import annotations


def ids_vinculados(valor: object) -> tuple[str, ...]:
    """Extrai os `record_id` de um campo de LINK do Airtable -- aceita
    tanto a forma `['recXXX', ...]` (strings soltas) quanto
    `[{'id': 'recXXX', ...}, ...]` (`returnFieldsByFieldId`). Qualquer
    outro formato (campo vazio, não-lista) devolve tupla vazia --
    nunca levanta exceção por um campo ausente/mal formado."""
    if not isinstance(valor, list):
        return ()
    ids = {
        item if isinstance(item, str) else item.get('id')
        for item in valor
        if isinstance(item, str) or (isinstance(item, dict) and isinstance(item.get('id'), str))
    }
    return tuple(sorted(item for item in ids if item))


def escapar_formula(valor: str) -> str:
    """Escapa um valor para uso literal dentro de uma `filterByFormula`
    do Airtable -- só barra invertida e aspas duplas, os únicos
    caracteres que quebram a sintaxe de string da fórmula."""
    return valor.replace('\\', '\\\\').replace('"', '\\"')


def filtro_ids(ids: tuple[str, ...]) -> str:
    """Monta uma `filterByFormula` que casa qualquer um dos
    `RECORD_ID()` informados -- `OR(...)` só quando há mais de um id,
    a expressão simples quando há exatamente um."""
    expressoes = tuple(f'RECORD_ID()="{escapar_formula(record_id)}"' for record_id in ids)
    if len(expressoes) == 1:
        return expressoes[0]
    return f'OR({",".join(expressoes)})'
