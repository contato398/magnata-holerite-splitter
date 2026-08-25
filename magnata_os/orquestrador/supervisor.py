"""Supervisor periodico e fail-safe do Grande Orquestrador.

O supervisor transforma health, DLQ e estados persistidos em um snapshot
operacional unico. O modo padrao e SHADOW: observa e relata, sem registrar
auditoria, reivindicar retry ou chamar qualquer Acao.

O modo ACTIVE reutiliza ``CoordenadorAutorrecuperacao`` e exige uma
autorizacao explicita no ponto de composicao. Isso impede que uma simples
variavel de ambiente transforme observabilidade em execucao consequencial.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from .autorrecuperacao import CoordenadorAutorrecuperacao, ResultadoRecuperacao
from .eventos import EstadoExecucao, agora
from .fila_desistencia import VisaoFilaDesistenciaPersistente
from .repositorio_execucoes import RepositorioExecucoes
from .saude_motor import EstadoSaudemotor, MonitorSaudemotorPersistente


class ModoSupervisor(str, Enum):
    SHADOW = 'SHADOW'
    ACTIVE = 'ACTIVE'


class PermissaoSupervisorAtivoAusente(RuntimeError):
    """O modo ativo foi solicitado sem gate explicito no ponto de composicao."""


@dataclasses.dataclass(frozen=True)
class SnapshotSupervisor:
    """Leitura operacional deterministica de um ciclo do supervisor."""

    modo: ModoSupervisor
    gerado_em: datetime
    saude: EstadoSaudemotor
    estados: Dict[str, int]
    dlq_ativa_event_ids: Tuple[str, ...]
    retry_vencido_event_ids: Tuple[str, ...]
    eventos_em_andamento_event_ids: Tuple[str, ...]
    recuperacoes: Tuple[ResultadoRecuperacao, ...] = ()

    def resumo_json(self) -> Dict:
        return {
            'modo': self.modo.value,
            'gerado_em': self.gerado_em.isoformat(),
            'saude': self.saude.resumo_json(),
            'estados': dict(self.estados),
            'dlq_ativa_total': len(self.dlq_ativa_event_ids),
            'dlq_ativa_event_ids': list(self.dlq_ativa_event_ids),
            'retry_vencido_total': len(self.retry_vencido_event_ids),
            'retry_vencido_event_ids': list(self.retry_vencido_event_ids),
            'eventos_em_andamento_total': len(self.eventos_em_andamento_event_ids),
            'eventos_em_andamento_event_ids': list(
                self.eventos_em_andamento_event_ids
            ),
            'recuperacoes_total': len(self.recuperacoes),
            'recuperacoes': [
                {
                    'event_id': resultado.event_id,
                    'decisao': resultado.decisao.value,
                    'estado_observado': resultado.estado_observado.value,
                    'estado_final': resultado.estado_final.value,
                    'motivo': resultado.motivo,
                    'evidencia': resultado.evidencia,
                }
                for resultado in self.recuperacoes
            ],
        }


class SupervisorOrquestrador:
    """Executa um ciclo observacional ou de recuperacao explicitamente ativo."""

    _ESTADOS_EM_ANDAMENTO = (
        EstadoExecucao.RECEIVED,
        EstadoExecucao.VALIDATED,
        EstadoExecucao.CLASSIFIED,
        EstadoExecucao.EXECUTING,
    )

    def __init__(
        self,
        repositorio: RepositorioExecucoes,
        modo: ModoSupervisor = ModoSupervisor.SHADOW,
        coordenador: Optional[CoordenadorAutorrecuperacao] = None,
        autorizar_execucao_ativa: bool = False,
        relogio: Callable[[], datetime] = agora,
    ) -> None:
        self._repositorio = repositorio
        self._modo = modo
        self._coordenador = coordenador
        self._autorizar_execucao_ativa = autorizar_execucao_ativa
        self._relogio = relogio

    def executar_ciclo(self) -> SnapshotSupervisor:
        instante = self._relogio()
        recuperacoes: Tuple[ResultadoRecuperacao, ...] = ()
        if self._modo == ModoSupervisor.ACTIVE:
            if not self._autorizar_execucao_ativa:
                raise PermissaoSupervisorAtivoAusente(
                    'supervisor ACTIVE exige autorizar_execucao_ativa=True'
                )
            if self._coordenador is None:
                raise PermissaoSupervisorAtivoAusente(
                    'supervisor ACTIVE exige CoordenadorAutorrecuperacao'
                )
            recuperacoes = tuple(self._coordenador.executar_ciclo())

        # O snapshot e sempre reconstruido depois do eventual ciclo ativo.
        # Assim estados, health e DLQ pertencem ao mesmo ponto logico e nao
        # misturam contagens anteriores ao retry com resultados posteriores.
        registros = sorted(
            (r for r in self._repositorio.listar_todos() if r is not None),
            key=lambda r: (r.criado_em, r.event_id),
        )
        estados: Dict[str, int] = {}
        retries_vencidos: List[str] = []
        em_andamento: List[str] = []

        for registro in registros:
            estados[registro.estado.value] = estados.get(registro.estado.value, 0) + 1
            if (
                registro.estado == EstadoExecucao.FAILED_RETRYABLE
                and registro.next_retry_at is not None
                and registro.next_retry_at <= instante
            ):
                retries_vencidos.append(registro.event_id)
            if registro.estado in self._ESTADOS_EM_ANDAMENTO:
                em_andamento.append(registro.event_id)

        dlq = VisaoFilaDesistenciaPersistente(self._repositorio)
        return SnapshotSupervisor(
            modo=self._modo,
            gerado_em=instante,
            saude=MonitorSaudemotorPersistente(self._repositorio).obter_saude(),
            estados=estados,
            dlq_ativa_event_ids=tuple(item.event_id for item in dlq.listar_todos()),
            retry_vencido_event_ids=tuple(retries_vencidos),
            eventos_em_andamento_event_ids=tuple(em_andamento),
            recuperacoes=recuperacoes,
        )
