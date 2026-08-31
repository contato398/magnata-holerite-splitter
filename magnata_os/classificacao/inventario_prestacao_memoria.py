"""Sink de inventário EM MEMÓRIA, append-only e idempotente (missão
"CORREDOR AUTÔNOMO PÓS-CLASSIFICAÇÃO V1", Fase 14/21; dedupe corrigido
pelo Adendo substitutivo ao PR #105, §15).

Implementa `FonteInventarioPrestacao` (leitura, Protocol já existente,
`inventario_prestacao.py`) e adiciona `adicionar`/`adicionar_muitos`
(escrita local, nunca Airtable/Postgres/S3 — quando uma dessas existir
de verdade, ela também implementa o MESMO Protocol de leitura, sem
alterar nenhum consumidor). Referência local/piloto — não é a fonte de
registro final da prestação, é o que permite provar, localmente e em
teste, que "documento resolvido -> vira item de inventário -> readiness/
pacote automáticos" sem depender de nenhuma escrita externa.

Idempotência: deduplicação por `ItemInventarioPrestacao.identidade_
logica` (`documento_id`+`cliente`+`colaborador` -- a identidade lógica
CANÔNICA já definida no próprio contrato, `prestacao_readiness.py`,
nunca uma tupla improvisada aqui). Um documento broadcast (DCTF) gera
legitimamente N itens do MESMO `documento_id`, um por cliente aplicável;
um documento fatiado por colaborador (Holerite com vínculo múltiplo,
relatório de benefícios) gera N itens do MESMO `documento_id` e
`cliente`, um por colaborador -- nenhum dos dois casos é colapsado.
Processar o MESMO documento (mesma identidade lógica completa) duas
vezes nunca duplica o item."""
from __future__ import annotations

from typing import Dict, Tuple

from .contratos import ReferenciaCanonica
from .prestacao_readiness import ItemInventarioPrestacao


class InventarioPrestacaoEmMemoria:
    """Implementa `FonteInventarioPrestacao` -- ver `inventario_
    prestacao.py`. Não duck-typed contra nenhum driver externo; puro
    Python em memória."""

    def __init__(self) -> None:
        self._itens: Dict[tuple, ItemInventarioPrestacao] = {}

    def adicionar(self, item: ItemInventarioPrestacao) -> bool:
        """Adiciona 1 item -- devolve `True` se foi uma inserção NOVA,
        `False` se a `identidade_logica` já existia (idempotente,
        primeiro item prevalece, nunca sobrescreve silenciosamente com
        conteúdo divergente -- mesma cautela de "arquivo original é
        imutável", CLAUDE.md §4)."""
        chave = item.identidade_logica
        if chave in self._itens:
            return False
        self._itens[chave] = item
        return True

    def adicionar_muitos(self, itens: Tuple[ItemInventarioPrestacao, ...]) -> int:
        """Adiciona vários itens (ex.: múltiplos clientes do mesmo
        documento via vínculo múltiplo, broadcast ou fatiamento por
        colaborador) -- devolve quantos foram efetivamente NOVOS."""
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
