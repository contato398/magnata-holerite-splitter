"""Comparação DIAGNÓSTICA, read-only, entre a autoridade histórica do
Magnata OS (`alocacao`/`vinculo_trabalhista`, shadow) e a fotografia
operacional atual do Airtable (Funcionário -> Locais de trabalho) --
FASE 6 da missão "CONFIRMAÇÃO DE ALOCAÇÃO SHADOW V1".

**Nunca reconciliação automática.** Esta comparação só PRODUZ um
estado explícito para leitura humana -- nunca corrige, nunca escreve
em nenhum dos dois lados, nunca decide qual lado está certo. Divergência
encontrada é sempre reportada, nunca resolvida sozinha (mesma
disciplina de CLAUDE.md raiz §4, "falha nunca é silenciosa" -- aqui
adaptado a "divergência nunca é corrigida silenciosamente").

Puro: `comparar_postos` não sabe o que é Airtable nem SQLite/Postgres --
só recebe 2 conjuntos de `posto_id` já apurados e devolve um estado.
`comparar_colaborador_shadow_com_airtable` é a única função deste
módulo que faz I/O, e mesmo assim só delega a 2 fontes já injetadas
(`repo` shadow + `snapshot_airtable`, duck-typed) -- nunca importa
driver nenhum diretamente."""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import FrozenSet, Optional


class EstadoComparacaoAirtable(str, Enum):
    """5 estados exigidos pela missão -- nunca um sexto criado por
    conveniência, nunca dois fundidos."""

    CONSISTENTE = 'consistente'
    DIFERENTE = 'diferente'
    MAGNATA_SEM_DADO = 'magnata_sem_dado'
    AIRTABLE_SEM_VINCULO = 'airtable_sem_vinculo'
    AMBIGUO = 'ambiguo'


def comparar_postos(
    postos_shadow: FrozenSet[str], postos_airtable: Optional[FrozenSet[str]],
) -> EstadoComparacaoAirtable:
    """`postos_airtable=None` sinaliza que o lado Airtable não pôde ser
    apurado com confiança (ex.: identidade ambígua no cadastro) --
    nunca tratado como "vazio", que teria um significado diferente
    (Airtable sabe que não há vínculo nenhum)."""
    if postos_airtable is None:
        return EstadoComparacaoAirtable.AMBIGUO
    if not postos_shadow and not postos_airtable:
        return EstadoComparacaoAirtable.CONSISTENTE  # nada dos dois lados -- nada diverge
    if not postos_shadow and postos_airtable:
        return EstadoComparacaoAirtable.MAGNATA_SEM_DADO
    if postos_shadow and not postos_airtable:
        return EstadoComparacaoAirtable.AIRTABLE_SEM_VINCULO
    if postos_shadow == postos_airtable:
        return EstadoComparacaoAirtable.CONSISTENTE
    return EstadoComparacaoAirtable.DIFERENTE


def comparar_colaborador_shadow_com_airtable(
    repo, snapshot_airtable, colaborador_id: str, data_referencia: date,
) -> EstadoComparacaoAirtable:
    """`repo`: mesmo duck-type de `captura.py`
    (`vinculo_mais_recente_de`, `postos_vigentes_em`) -- shadow sempre.
    `snapshot_airtable`: precisa expor `postos_atuais_do_colaborador
    (colaborador_id) -> FrozenSet[str]` (ver
    `ResolverIdentidadeAlocacaoAirtableShadow` em
    `airtable_resolver_identidade_alocacao.py`); qualquer exceção
    levantada por essa chamada (ex.: `ColaboradorAmbiguoError`, ou
    Airtable indisponível) vira `AMBIGUO` aqui -- esta função de
    diagnóstico nunca propaga uma falha do lado Airtable como se fosse
    um erro do Magnata OS; ela reporta a incerteza como um estado,
    nunca derruba quem a chamou."""
    vinculo = repo.vinculo_mais_recente_de(colaborador_id)
    postos_shadow = (
        frozenset(repo.postos_vigentes_em(vinculo.id, data_referencia, data_referencia))
        if vinculo is not None
        else frozenset()
    )
    try:
        postos_airtable: Optional[FrozenSet[str]] = frozenset(
            snapshot_airtable.postos_atuais_do_colaborador(colaborador_id))
    except Exception:
        postos_airtable = None
    return comparar_postos(postos_shadow, postos_airtable)
