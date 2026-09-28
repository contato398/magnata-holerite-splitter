"""Modelo de domínio para distribuição de documentos no Magnata OS.

O contrato separa estado operacional de canal e de fallback. Nenhuma
integração externa é importada aqui; adapters executam as ordens depois.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import FrozenSet


class CanalDistribuicao(str, Enum):
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"


class EstadoDistribuicao(str, Enum):
    PENDING = "PENDING"
    PREPARANDO = "PREPARANDO"
    PRONTO = "PRONTO"
    ENVIANDO = "ENVIANDO"
    ENTREGUE = "ENTREGUE"
    ASSINATURA_PENDENTE = "ASSINATURA_PENDENTE"
    CONCLUIDO = "CONCLUIDO"
    BLOQUEADO = "BLOQUEADO"
    ERRO_RETRY = "ERRO_RETRY"
    FALLBACK_MANUAL = "FALLBACK_MANUAL"
    CANCELADO = "CANCELADO"


class AcaoFallback(str, Enum):
    ABRIR_DOCUMENTO = "ABRIR_DOCUMENTO"
    COPIAR_MENSAGEM = "COPIAR_MENSAGEM"
    ABRIR_CANAL = "ABRIR_CANAL"
    CONFIRMAR_RESULTADO = "CONFIRMAR_RESULTADO"


_TRANSICOES_PERMITIDAS: dict[EstadoDistribuicao, FrozenSet[EstadoDistribuicao]] = {
    EstadoDistribuicao.PENDING: frozenset({EstadoDistribuicao.PREPARANDO, EstadoDistribuicao.BLOQUEADO, EstadoDistribuicao.CANCELADO}),
    EstadoDistribuicao.PREPARANDO: frozenset({EstadoDistribuicao.PRONTO, EstadoDistribuicao.BLOQUEADO, EstadoDistribuicao.CANCELADO}),
    EstadoDistribuicao.PRONTO: frozenset({EstadoDistribuicao.ENVIANDO, EstadoDistribuicao.FALLBACK_MANUAL, EstadoDistribuicao.CANCELADO}),
    EstadoDistribuicao.ENVIANDO: frozenset({EstadoDistribuicao.ENTREGUE, EstadoDistribuicao.ERRO_RETRY, EstadoDistribuicao.FALLBACK_MANUAL}),
    EstadoDistribuicao.ENTREGUE: frozenset({EstadoDistribuicao.ASSINATURA_PENDENTE, EstadoDistribuicao.CONCLUIDO}),
    EstadoDistribuicao.ASSINATURA_PENDENTE: frozenset({EstadoDistribuicao.CONCLUIDO, EstadoDistribuicao.FALLBACK_MANUAL}),
    EstadoDistribuicao.ERRO_RETRY: frozenset({EstadoDistribuicao.ENVIANDO, EstadoDistribuicao.FALLBACK_MANUAL, EstadoDistribuicao.CANCELADO}),
    EstadoDistribuicao.FALLBACK_MANUAL: frozenset({EstadoDistribuicao.ENTREGUE, EstadoDistribuicao.CONCLUIDO, EstadoDistribuicao.CANCELADO}),
    EstadoDistribuicao.BLOQUEADO: frozenset({EstadoDistribuicao.PENDING, EstadoDistribuicao.CANCELADO}),
    EstadoDistribuicao.CONCLUIDO: frozenset(),
    EstadoDistribuicao.CANCELADO: frozenset(),
}


@dataclass(frozen=True)
class OrdemDistribuicao:
    """Ordem idempotente que pode ser executada por qualquer canal adapter."""

    intent_id: str
    document_id: str
    document_version: str
    recipient_id: str
    channel: CanalDistribuicao
    state: EstadoDistribuicao = EstadoDistribuicao.PENDING
    attempt_count: int = 0
    last_error: str | None = None
    evidence_id: str | None = None
    fallback_required: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.intent_id or not self.document_id or not self.recipient_id:
            raise ValueError("intent_id, document_id e recipient_id são obrigatórios")
        if self.attempt_count < 0:
            raise ValueError("attempt_count não pode ser negativo")
        if self.created_at is None:
            now = datetime.now(timezone.utc)
            object.__setattr__(self, "created_at", now)
            object.__setattr__(self, "updated_at", now)


def transicionar(
    ordem: OrdemDistribuicao,
    novo_estado: EstadoDistribuicao,
    *,
    erro: str | None = None,
    evidence_id: str | None = None,
    fallback_required: bool | None = None,
    incrementar_tentativa: bool = False,
) -> OrdemDistribuicao:
    """Aplica uma transição explicitamente permitida e devolve nova ordem."""

    permitidos = _TRANSICOES_PERMITIDAS[ordem.state]
    if novo_estado not in permitidos:
        raise ValueError(f"transição não permitida: {ordem.state.value} -> {novo_estado.value}")

    agora = datetime.now(timezone.utc)
    return replace(
        ordem,
        state=novo_estado,
        attempt_count=ordem.attempt_count + (1 if incrementar_tentativa else 0),
        last_error=erro,
        evidence_id=evidence_id if evidence_id is not None else ordem.evidence_id,
        fallback_required=(
            fallback_required if fallback_required is not None else ordem.fallback_required
        ),
        updated_at=agora,
    )
