"""Comparação DIAGNÓSTICA, read-only, entre a autoridade histórica do
Magnata OS (shadow, Postgres) e a fotografia operacional atual do
Airtable -- FASE 6 da missão "CONFIRMAÇÃO DE ALOCAÇÃO SHADOW V1"
(`comparar_colaborador_shadow_com_airtable`, Funcionário -> Locais de
trabalho), estendida pela missão "SHADOW CLIENTE X POSTO AIRTABLE V1"
(`comparar_cliente_do_posto_shadow_com_airtable`, Posto -> Cliente via
`vigencia_cliente_por_posto`) -- mesma disciplina, novo par de fontes.

**Nunca reconciliação automática.** Esta comparação só PRODUZ um
estado explícito para leitura humana -- nunca corrige, nunca escreve
em nenhum dos dois lados, nunca decide qual lado está certo. Divergência
encontrada é sempre reportada, nunca resolvida sozinha (mesma
disciplina de CLAUDE.md raiz §4, "falha nunca é silenciosa" -- aqui
adaptado a "divergência nunca é corrigida silenciosamente").

Puro: `comparar_postos` não sabe o que é Airtable nem SQLite/Postgres,
Alocação nem Cliente -- só recebe 2 conjuntos de ids já apurados e
devolve um estado; reaproveitada por AMBAS as comparações deste módulo,
nunca duplicada. `comparar_colaborador_shadow_com_airtable` e
`comparar_cliente_do_posto_shadow_com_airtable` são as únicas funções
deste módulo que fazem I/O, e mesmo assim só delegam a 2 fontes já
injetadas (`repo` shadow + `snapshot_airtable`, duck-typed) -- nunca
importam driver nenhum diretamente."""
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


def comparar_cliente_do_posto_shadow_com_airtable(
    repo, snapshot_airtable, posto_id: str, data_referencia: date,
) -> EstadoComparacaoAirtable:
    """Mesma disciplina de `comparar_colaborador_shadow_com_airtable`,
    para a fundação temporal Posto<->Cliente (`vigencia_cliente_por_
    posto`, missão "SHADOW CLIENTE X POSTO AIRTABLE V1", frente 7 de
    redução de dependência do Airtable) -- nunca reconciliação
    automática, só diagnóstico read-only.

    Reaproveita 100% de `comparar_postos` (nenhum estado novo, nenhuma
    lógica de comparação nova) ao representar "o cliente vigente de um
    posto" como um `FrozenSet` de 0 ou 1 elemento -- a mesma forma que
    `comparar_postos` já sabe comparar.

    `repo`: duck-type com `cliente_vigente_do_posto(posto_id,
    data_referencia) -> Optional[str]` (shadow Postgres,
    `vigencia_cliente_por_posto`, já garante no máximo 1 cliente por
    posto por período via constraint `EXCLUDE` do banco).
    `snapshot_airtable`: duck-type com `clientes_atuais_do_posto
    (posto_id) -> FrozenSet[str]` (ver `clientes_atuais_do_posto` em
    `airtable_vinculos_prestacao.FonteVinculosPrestacaoAirtableShadow`);
    qualquer exceção levantada por essa chamada vira `AMBIGUO` aqui --
    mesma disciplina de nunca propagar falha do lado Airtable como erro
    do Magnata OS."""
    cliente_shadow = repo.cliente_vigente_do_posto(posto_id, data_referencia)
    clientes_shadow = frozenset({cliente_shadow}) if cliente_shadow else frozenset()
    try:
        clientes_airtable: Optional[FrozenSet[str]] = frozenset(
            snapshot_airtable.clientes_atuais_do_posto(posto_id))
    except Exception:
        clientes_airtable = None
    return comparar_postos(clientes_shadow, clientes_airtable)
