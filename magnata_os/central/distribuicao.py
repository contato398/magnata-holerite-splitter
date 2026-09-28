"""Contrato central de distribuição do Magnata OS.

A distribuição não cria uma segunda máquina de estados: reutiliza o ciclo
canônico de execução do Grande Orquestrador. A Ordem é genérica para 1..N
documentos e 1..N destinatários; canais e assinatura são políticas/capacidades,
não tipos de documento.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
)


EstadoDistribuicao = EstadoAcaoExecucaoPlano
CanalDistribuicao = str


@dataclass(frozen=True)
class OrdemDistribuicao:
    """Intenção idempotente de distribuição, independente do canal."""

    intent_id: str
    document_ids: tuple[str, ...]
    document_versions: tuple[str, ...]
    recipient_ids: tuple[str, ...]
    channel: CanalDistribuicao
    signature_required: bool = False
    receipt_required: bool = False
    state: EstadoDistribuicao = EstadoDistribuicao.PENDING
    attempt_count: int = 0
    last_error: str | None = None
    evidence_id: str | None = None
    fallback_required: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.intent_id:
            raise ValueError("intent_id é obrigatório")
        if not self.document_ids:
            raise ValueError("ao menos 1 documento é obrigatório")
        if len(self.document_ids) != len(self.document_versions):
            raise ValueError("document_ids e document_versions devem ter o mesmo tamanho")
        if not self.recipient_ids:
            raise ValueError("ao menos 1 destinatário é obrigatório")
        if any(not value for value in self.document_ids):
            raise ValueError("document_id vazio não é permitido")
        if any(not value for value in self.document_versions):
            raise ValueError("document_version vazia não é permitida")
        if any(not value for value in self.recipient_ids):
            raise ValueError("recipient_id vazio não é permitido")
        if not str(self.channel).strip():
            raise ValueError("channel é obrigatório")
        if not isinstance(self.signature_required, bool) or not isinstance(self.receipt_required, bool):
            raise ValueError("signature_required e receipt_required devem ser booleanos")
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
    """Aplica somente transições já autorizadas pelo ciclo do Orquestrador.

    Se a transição não fornece novo erro, preserva o último erro conhecido;
    isso mantém a evidência de uma falha transitória durante o retry.
    """

    if novo_estado not in _TRANSICOES_PERMITIDAS[ordem.state]:
        raise ValueError(
            f"transição não permitida: {ordem.state.value} -> {novo_estado.value}"
        )

    agora = datetime.now(timezone.utc)
    return replace(
        ordem,
        state=novo_estado,
        attempt_count=ordem.attempt_count + (1 if incrementar_tentativa else 0),
        last_error=erro if erro is not None else ordem.last_error,
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
    """Marca fallback sem inventar um novo estado de execução."""

    motivo_limpo = (motivo or "").strip()
    if not motivo_limpo:
        raise ValueError("motivo do fallback manual é obrigatório")
    return replace(
        ordem,
        fallback_required=True,
        last_error=motivo_limpo,
        updated_at=datetime.now(timezone.utc),
    )
