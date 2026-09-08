"""Execução persistente de um ciclo de Prestação de Contas.

Representação de uma execução CONCRETA do processo de Prestação,
criada ANTES de qualquer ação filha, persistida e recuperável após restart.

Identidade: execucao_prestacao_id (opaco, único por execução).

Competência: baseada em competencia_base (ano/mês do ciclo).

Estado: INICIADA, CONCLUIDA, FALHA (mínimo necessário).

Timestamp: criado_em (não é parte da identidade).

Essa fundação permite que ações filhas futuras (Busca Complementar,
conferência, geração de pacote, envio) referenciem via correlation_id
do Evento a execução pai concreta.
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Protocol


@dataclasses.dataclass(frozen=True)
class ExecucaoPrestacao:
    """Uma execução específica de Prestação de Contas.

    Imutável (frozen=True) conforme padrão de Documento/RegistroExecucao.
    """

    execucao_prestacao_id: str
    """Identificador opaco único da execução. Gerado UMA VEZ na criação,
    antes de qualquer ação filha."""

    competencia_base: str
    """Competência base (ano-mês), ex: "2026-09".
    Formato: AAAA-MM (ISO 8601)."""

    estado: str
    """Estado da execução: INICIADA, CONCLUIDA, FALHA."""

    origem: str
    """Quem iniciou a execução (ex: app.py, CLI, scheduler)."""

    criado_em: datetime
    """Timestamp de criação (UTC com timezone)."""

    atualizado_em: datetime
    """Timestamp de última atualização (UTC com timezone)."""

    concluido_em: Optional[datetime] = None
    """Timestamp de conclusão, se finalizada."""

    def __post_init__(self) -> None:
        if self.estado not in ('INICIADA', 'CONCLUIDA', 'FALHA'):
            raise ValueError(f'estado inválido: {self.estado}')
        if self.concluido_em and self.estado not in ('CONCLUIDA', 'FALHA'):
            raise ValueError(
                'concluido_em deve ser NULL se estado não é CONCLUIDA/FALHA'
            )
        if self.criado_em.tzinfo is None or self.atualizado_em.tzinfo is None:
            raise ValueError('timestamps devem ter timezone')


def criar_execucao_prestacao(
    competencia_base: str,
    origem: str = 'operacional',
) -> ExecucaoPrestacao:
    """Factory para criar uma execução nova.

    Gera execucao_prestacao_id opaco (UUID).
    """
    agora = datetime.now(timezone.utc)
    execucao_id = str(uuid.uuid4())
    return ExecucaoPrestacao(
        execucao_prestacao_id=execucao_id,
        competencia_base=competencia_base,
        estado='INICIADA',
        origem=origem,
        criado_em=agora,
        atualizado_em=agora,
    )


class RepositorioExecucoesPrestacao(Protocol):
    """Interface para persistência de execuções de Prestação.

    Padrão: Protocol (abstrato) permite trocar implementação
    (memória para teste, Postgres para produção) sem alterar Motor.
    """

    def criar(self, execucao: ExecucaoPrestacao) -> None:
        """Persiste uma execução nova."""
        ...

    def buscar_por_id(
        self, execucao_prestacao_id: str,
    ) -> Optional[ExecucaoPrestacao]:
        """Recupera execução por ID."""
        ...

    def atualizar_estado(
        self,
        execucao_prestacao_id: str,
        novo_estado: str,
        concluido_em: Optional[datetime] = None,
    ) -> None:
        """Atualiza estado e concluido_em se aplicável."""
        ...

    def listar_por_competencia(self, competencia_base: str) -> List[ExecucaoPrestacao]:
        """Lista todas as execuções de uma competência."""
        ...

    def listar_todas(self) -> List[ExecucaoPrestacao]:
        """Lista todas as execuções (sem limite)."""
        ...


class RepositorioExecucoesPrestacaoMemoria:
    """Implementação em memória para testes.

    Padrão: mesmo de RepositorioExecucoesEmMemoria (Orquestrador).
    """

    def __init__(self) -> None:
        self._dados: dict[str, ExecucaoPrestacao] = {}

    def criar(self, execucao: ExecucaoPrestacao) -> None:
        if execucao.execucao_prestacao_id in self._dados:
            raise ValueError('execução já existe')
        self._dados[execucao.execucao_prestacao_id] = execucao

    def buscar_por_id(
        self, execucao_prestacao_id: str,
    ) -> Optional[ExecucaoPrestacao]:
        return self._dados.get(execucao_prestacao_id)

    def atualizar_estado(
        self,
        execucao_prestacao_id: str,
        novo_estado: str,
        concluido_em: Optional[datetime] = None,
    ) -> None:
        execucao = self._dados.get(execucao_prestacao_id)
        if not execucao:
            raise ValueError('execução não encontrada')
        self._dados[execucao_prestacao_id] = dataclasses.replace(
            execucao,
            estado=novo_estado,
            concluido_em=concluido_em,
            atualizado_em=datetime.now(timezone.utc),
        )

    def listar_por_competencia(self, competencia_base: str) -> List[ExecucaoPrestacao]:
        return [
            e for e in self._dados.values()
            if e.competencia_base == competencia_base
        ]

    def listar_todas(self) -> List[ExecucaoPrestacao]:
        return list(self._dados.values())
