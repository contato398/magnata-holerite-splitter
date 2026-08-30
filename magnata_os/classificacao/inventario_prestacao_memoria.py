"""Sink de inventário EM MEMÓRIA, append-only e idempotente (missão
"CORREDOR AUTÔNOMO PÓS-CLASSIFICAÇÃO V1", Fase 14/21).

Implementa `FonteInventarioPrestacao` (leitura, Protocol já existente,
`inventario_prestacao.py`) e adiciona `adicionar`/`adicionar_muitos`
(escrita local, nunca Airtable/Postgres/S3 — quando uma dessas existir
de verdade, ela também implementa o MESMO Protocol de leitura, sem
alterar nenhum consumidor). Referência local/piloto — não é a fonte de
registro final da prestação, é o que permite provar, localmente e em
teste, que "documento resolvido -> vira item de inventário -> readiness/
pacote automáticos" sem depender de nenhuma escrita externa.

Idempotência (Fase 21): deduplicação por `(documento_id, cliente)` --
NUNCA só `documento_id` sozinho: um documento broadcast (Fase 5/10,
"DCTF: broadcast quando estruturalmente aplicável") gera legitimamente
N itens de inventário para o MESMO `documento_id`, um por cliente
aplicável (`adaptador_inventario_prestacao.itens_para_clientes_
broadcast`, já existente) — deduplicar só por `documento_id` perderia
N-1 desses itens genuínos. Processar o MESMO documento (mesmo
`documento_id`, mesmo cliente) duas vezes nunca duplica o item; um
documento broadcast para 2 clientes gera 2 itens DISTINTOS, ambos
preservados.

Achado registrado, não corrigido aqui (fora do escopo desta missão):
`fonte_inventario_composta.FonteInventarioPrestacaoComposta` (missão
anterior) dedupa só por `documento_id` -- o mesmo latente problema
existiria lá se algum dia uma fonte real produzir broadcast através
dela. Não alterado nesta missão para não misturar uma correção não
pedida com o corredor novo; candidato a próxima macro-missão."""
from __future__ import annotations

from typing import Dict, Tuple

from .contratos import ReferenciaCanonica
from .prestacao_readiness import ItemInventarioPrestacao


class InventarioPrestacaoEmMemoria:
    """Implementa `FonteInventarioPrestacao` -- ver `inventario_
    prestacao.py`. Não duck-typed contra nenhum driver externo; puro
    Python em memória."""

    def __init__(self) -> None:
        self._itens: Dict[Tuple[str, ReferenciaCanonica], ItemInventarioPrestacao] = {}

    def adicionar(self, item: ItemInventarioPrestacao) -> bool:
        """Adiciona 1 item -- devolve `True` se foi uma inserção NOVA,
        `False` se `(documento_id, cliente)` já existia (idempotente,
        primeiro item prevalece, nunca sobrescreve silenciosamente com
        conteúdo divergente -- mesma cautela de "arquivo original é
        imutável", CLAUDE.md §4)."""
        chave = (item.documento_id, item.cliente)
        if chave in self._itens:
            return False
        self._itens[chave] = item
        return True

    def adicionar_muitos(self, itens: Tuple[ItemInventarioPrestacao, ...]) -> int:
        """Adiciona vários itens (ex.: múltiplos clientes do mesmo
        documento via vínculo múltiplo ou broadcast) -- devolve quantos
        foram efetivamente NOVOS."""
        return sum(1 for item in itens if self.adicionar(item))

    def listar(
        self, cliente: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> Tuple[ItemInventarioPrestacao, ...]:
        return tuple(
            item for item in self._itens.values()
            if item.cliente == cliente and item.competencia == competencia
        )

    def total_itens(self) -> int:
        """Observabilidade -- nunca usado para decisão, só métrica."""
        return len(self._itens)
