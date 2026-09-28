"""Contrato central de distribuição do Magnata OS.

A distribuição não cria uma segunda máquina de estados: reutiliza o ciclo
canônico de execução do Grande Orquestrador. Canais são extensíveis e não
carregam regra de negócio.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
)


# Alias explícito: a Central não pode inventar um segundo ciclo operacional.
EstadoDistribuicao = EstadoAcaoExecucaoPlano
CanalDistribuicao = str


@dataclass(frozen=True)
class OrdemDistribuicao:
    """Intenção idempotente de distribuição, independente do canal."""

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
        if not self.document_version:
            raise ValueError("document_version é obrigatória")
        if not str(self.channel).strip():
            raise ValueError("channel é obrigatório")
        if self.attempt_count < 0:
            raise ValueError("attempt_count não pode ser negativo")
        if self.created_at is None:
            now = datetime.now(timezone.utc)
            object.__setattr__(self, "created_at", now)
            object.__setattr__(self, "updated_at", now)


_TRANSICOES_PERMITIDAS = {
    EstadoDistribuicao.PENDING: {EstadoDistribuicao.EXECUTING},
    EstadoDistribuicao.EXECUTING: {
        EstadoDistribuicao.SUCCEEDED,
        EstadoDistribuicao.FAILED_RETRYABLE,
        EstadoDistribuicao.FAILED_FINAL,
    },
    EstadoDistribuicao.FAILED_RETRYABLE: {EstadoDistribuicao.EXECUTING},
    EstadoDistribuicao.SUCCEEDED: set(),
    EstadoDistribuicao.FAILED_FINAL: set(),
}


def transicionar(
    ordem: OrdemDistribuicao,
    novo_estado: EstadoDistribuicao,
    *,
    erro: str | None = None,
    evidence_id: str | None = None,
    fallback_required: bool | None = None,
    incrementar_tentativa: bool = False,
) -> OrdemDistribuicao:
    """Aplica somente transições já autorizadas pelo ciclo do Orquestrador."""

    if novo_estado not in _TRANSICOES_PERMITIDAS[ordem.state]:
        raise ValueError(
            f"transição não permitida: {ordem.state.value} -> {novo_estado.value}"
        )

    agora = datetime.now(timezone.utc)
    return replace(
        ordem,
        state=novo_estado,
        attempt_count=ordem.attempt_count + (1 if incrementar_tentativa else 0),
        last_error=erro,
        evidence_id=evidence_id if evidence_id is not None else ordem.evidence_id,
        fallback_required=(
            fallback_required
            if fallback_required is not None
            else ordem.fallback_required
        ),
        updated_at=agora,
    )


def encaminhar_para_fallback_manual(
    ordem: OrdemDistribuicao,
    *,
    motivo: str,
) -> OrdemDistribuicao:
    """Marca fallback sem inventar um novo estado de execução.

    O Orquestrador continua dono do estado; a camada de política/painel pode
    oferecer a ação manual assistida conforme a marca persistida.
    """

    motivo_limpo = (motivo or "").strip()
    if not motivo_limpo:
        raise ValueError("motivo do fallback manual é obrigatório")
    return replace(
        ordem,
        fallback_required=True,
        last_error=motivo_limpo,
        updated_at=datetime.now(timezone.utc),
    )
