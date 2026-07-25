"""
Filtros, paginacao e ordenacao da API de esteira (Modulo 01, Fase 4).

Toda validacao aqui e "fail loud": um filtro/ordenacao/paginacao
invalido levanta a excecao correspondente (erros.py) imediatamente --
nunca e silenciosamente ignorado nem corrigido por adivinhacao.

"Ordenacao segura" significa: o campo pedido e sempre conferido contra
um allowlist fixo por endpoint (CAMPOS_ORDENACAO_*) antes de ser usado
-- nunca um getattr/lookup dinamico direto sobre um nome de campo vindo
de fora, o que poderia expor atributos internos nao pensados para
ordenacao ou levantar AttributeError revelando forma interna dos
objetos.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import FrozenSet, Optional

from ..dominio_esteira import EtapaEsteira, SituacaoEsteira
from .erros import FiltroInvalido, OrdenacaoInvalida, PaginacaoInvalida

TAMANHO_PAGINA_PADRAO = 20
TAMANHO_PAGINA_MAXIMO = 200


@dataclasses.dataclass(frozen=True)
class FiltroDocumentos:
    etapa: Optional[EtapaEsteira] = None
    situacao: Optional[SituacaoEsteira] = None
    lote_id: Optional[str] = None
    origem: Optional[str] = None
    bloqueado: Optional[bool] = None
    acao_humana: Optional[bool] = None
    recebido_de: Optional[datetime] = None
    recebido_ate: Optional[datetime] = None
    tempo_minimo_parado_segundos: Optional[float] = None


@dataclasses.dataclass(frozen=True)
class FiltroLotes:
    origem: Optional[str] = None
    situacao: Optional[SituacaoEsteira] = None
    recebido_de: Optional[datetime] = None
    recebido_ate: Optional[datetime] = None


@dataclasses.dataclass(frozen=True)
class Paginacao:
    pagina: int = 1
    tamanho_pagina: int = TAMANHO_PAGINA_PADRAO


@dataclasses.dataclass(frozen=True)
class Ordenacao:
    campo: str
    direcao: str = 'desc'  # 'asc' | 'desc'


# Allowlists por endpoint -- unica fonte de verdade sobre quais campos
# podem ser usados em `ordenacao.campo` (ver validar_ordenacao). Cada
# handlers.py mapeia estes nomes para uma funcao extratora segura, nunca
# para um getattr dinamico direto.
CAMPOS_ORDENACAO_DOCUMENTOS: FrozenSet[str] = frozenset({
    'atualizado_em', 'entrou_na_etapa_em', 'recebido_em', 'documento_id', 'tempo_na_etapa_segundos',
})
CAMPOS_ORDENACAO_LOTES: FrozenSet[str] = frozenset({
    'criado_em', 'recebido_em', 'quantidade_arquivos', 'lote_id',
})
CAMPOS_ORDENACAO_BLOQUEIOS: FrozenSet[str] = frozenset({
    'tempo_bloqueado_segundos', 'documento_id',
})


def validar_paginacao(paginacao: Paginacao) -> None:
    if paginacao.pagina < 1:
        raise PaginacaoInvalida(f'pagina deve ser >= 1 (recebido: {paginacao.pagina}).')
    if paginacao.tamanho_pagina < 1:
        raise PaginacaoInvalida(f'tamanho_pagina deve ser >= 1 (recebido: {paginacao.tamanho_pagina}).')
    if paginacao.tamanho_pagina > TAMANHO_PAGINA_MAXIMO:
        raise PaginacaoInvalida(
            f'tamanho_pagina nao pode exceder {TAMANHO_PAGINA_MAXIMO} (recebido: {paginacao.tamanho_pagina}).'
        )


def validar_ordenacao(ordenacao: Ordenacao, campos_permitidos: FrozenSet[str]) -> None:
    if ordenacao.campo not in campos_permitidos:
        permitidos_str = ', '.join(sorted(campos_permitidos))
        raise OrdenacaoInvalida(
            f'campo de ordenacao invalido: {ordenacao.campo!r} (permitido: {permitidos_str}).'
        )
    if ordenacao.direcao not in ('asc', 'desc'):
        raise OrdenacaoInvalida(
            f'direcao de ordenacao invalida: {ordenacao.direcao!r} (permitido: asc, desc).'
        )


def _validar_intervalo_recebido(recebido_de: Optional[datetime], recebido_ate: Optional[datetime]) -> None:
    if recebido_de is not None and recebido_ate is not None and recebido_de > recebido_ate:
        raise FiltroInvalido('recebido_de nao pode ser posterior a recebido_ate.')


def validar_filtro_documentos(filtro: FiltroDocumentos) -> None:
    _validar_intervalo_recebido(filtro.recebido_de, filtro.recebido_ate)
    if filtro.tempo_minimo_parado_segundos is not None and filtro.tempo_minimo_parado_segundos < 0:
        raise FiltroInvalido('tempo_minimo_parado_segundos nao pode ser negativo.')


def validar_filtro_lotes(filtro: FiltroLotes) -> None:
    _validar_intervalo_recebido(filtro.recebido_de, filtro.recebido_ate)
