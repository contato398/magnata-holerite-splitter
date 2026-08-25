"""Coordenador de autorrecuperacao segura sobre o health persistente.

O coordenador nao cria um segundo motor e nao executa replay automatico.
Ele observa o estado persistido, aplica politica de recuperacao, respeita
backoff e usa o proprio ``MotorOrquestrador`` para a retentativa.

Fail-safe:
- health VERMELHO abre o circuito para novos retries automaticos;
- evento preso apos crash nunca e retomado automaticamente;
- FAILED_FINAL e WAITING_GATE sempre escalam;
- politica ausente, evento sem envelope ou Acao nao-idempotente escalam;
- toda decisao fica na trilha append-only de recuperacao.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, List, Optional

from .eventos import EstadoExecucao, TipoEvento, agora
from .motor import MotorOrquestrador
from .politica_recuperacao import politica_recuperacao_para
from .repositorio_execucoes import (
    RegistroExecucao,
    RegistroRecuperacao,
    RepositorioExecucoes,
)
from .saude_motor import MonitorSaudemotorPersistente


class DecisaoRecuperacao(str, Enum):
    RETRY_EXECUTADO = 'RETRY_EXECUTADO'
    AGUARDAR_BACKOFF = 'AGUARDAR_BACKOFF'
    CIRCUITO_ABERTO = 'CIRCUITO_ABERTO'
    ESCALAR_HUMANO = 'ESCALAR_HUMANO'
    IGNORADO_CONCORRENCIA = 'IGNORADO_CONCORRENCIA'


@dataclasses.dataclass(frozen=True)
class ResultadoRecuperacao:
    event_id: str
    decisao: DecisaoRecuperacao
    estado_observado: EstadoExecucao
    estado_final: EstadoExecucao
    motivo: str
    evidencia: Optional[str] = None


class CoordenadorAutorrecuperacao:
    """Executa um ciclo deterministico de avaliacao e recuperacao."""

    _ESTADOS_EM_ANDAMENTO = (
        EstadoExecucao.RECEIVED,
        EstadoExecucao.VALIDATED,
        EstadoExecucao.CLASSIFIED,
        EstadoExecucao.EXECUTING,
    )

    def __init__(
        self,
        repositorio: RepositorioExecucoes,
        motor: MotorOrquestrador,
        relogio: Callable[[], datetime] = agora,
        limite_evento_em_andamento: timedelta = timedelta(minutes=15),
        observador: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self._repo = repositorio
        self._motor = motor
        self._relogio = relogio
        self._limite_evento_em_andamento = limite_evento_em_andamento
        self._observador = observador

    def _emitir(self, nome: str, **campos) -> None:
        if self._observador is not None:
            self._observador(nome, campos)

    def _registrar(
        self,
        registro: RegistroExecucao,
        decisao: DecisaoRecuperacao,
        motivo: str,
        evidencia: Optional[str] = None,
        instante: Optional[datetime] = None,
        estado_observado: Optional[EstadoExecucao] = None,
    ) -> ResultadoRecuperacao:
        quando = instante or self._relogio()
        observado = estado_observado or registro.estado
        atual = self._repo.buscar_por_event_id(registro.event_id) or registro
        novo_registro = RegistroRecuperacao(
            event_id=registro.event_id,
            decisao=decisao.value,
            estado_observado=observado.value,
            registrado_em=quando,
            motivo=motivo,
            evidencia=evidencia,
        )
        anteriores = self._repo.listar_recuperacoes(registro.event_id)
        ultimo = anteriores[-1] if anteriores else None
        if ultimo is None or (
            ultimo.decisao,
            ultimo.estado_observado,
            ultimo.motivo,
            ultimo.evidencia,
        ) != (
            novo_registro.decisao,
            novo_registro.estado_observado,
            novo_registro.motivo,
            novo_registro.evidencia,
        ):
            self._repo.registrar_recuperacao(novo_registro)
        self._emitir(
            'decisao_autorrecuperacao',
            event_id=registro.event_id,
            decisao=decisao.value,
            estado_observado=observado.value,
            estado_final=atual.estado.value,
        )
        return ResultadoRecuperacao(
            event_id=registro.event_id,
            decisao=decisao,
            estado_observado=observado,
            estado_final=atual.estado,
            motivo=motivo,
            evidencia=evidencia,
        )

    def executar_ciclo(self) -> List[ResultadoRecuperacao]:
        """Avalia o snapshot atual uma vez, sem loop nem scheduler proprio."""
        instante = self._relogio()
        saude = MonitorSaudemotorPersistente(self._repo).obter_saude()
        resultados: List[ResultadoRecuperacao] = []

        registros = sorted(
            (r for r in self._repo.listar_todos() if r is not None),
            key=lambda r: (r.criado_em, r.event_id),
        )
        for registro in registros:
            resultado = self._avaliar(registro, instante, saude.saude)
            if resultado is not None:
                resultados.append(resultado)
        return resultados

    def _avaliar(
        self,
        registro: RegistroExecucao,
        instante: datetime,
        saude: str,
    ) -> Optional[ResultadoRecuperacao]:
        estado = registro.estado

        if estado == EstadoExecucao.FAILED_RETRYABLE:
            if saude == 'VERMELHO':
                return self._registrar(
                    registro,
                    DecisaoRecuperacao.CIRCUITO_ABERTO,
                    'health persistente VERMELHO; retry automatico suspenso',
                    instante=instante,
                )

            try:
                event_type = TipoEvento(registro.event_type)
            except (TypeError, ValueError):
                return self._registrar(
                    registro,
                    DecisaoRecuperacao.ESCALAR_HUMANO,
                    'event_type invalido ou desconhecido para recuperacao',
                    instante=instante,
                )

            politica = politica_recuperacao_para(event_type)
            if not politica.permite_retry_seguro:
                return self._registrar(
                    registro,
                    DecisaoRecuperacao.ESCALAR_HUMANO,
                    politica.justificativa,
                    instante=instante,
                )

            if registro.next_retry_at is None:
                return self._registrar(
                    registro,
                    DecisaoRecuperacao.ESCALAR_HUMANO,
                    'falha retentavel sem next_retry_at; estado inconsistente',
                    instante=instante,
                )

            if instante < registro.next_retry_at:
                return self._registrar(
                    registro,
                    DecisaoRecuperacao.AGUARDAR_BACKOFF,
                    'janela de backoff ainda nao venceu',
                    evidencia=f'next_retry_at={registro.next_retry_at.isoformat()}',
                    instante=instante,
                )

            try:
                evento = self._motor.carregar_evento(registro.event_id)
            except (TypeError, ValueError, KeyError):
                return self._registrar(
                    registro,
                    DecisaoRecuperacao.ESCALAR_HUMANO,
                    'envelope persistido ausente ou invalido; retry bloqueado',
                    instante=instante,
                )

            # Registrar a autorizacao antes de executar. Se esta escrita
            # falhar, a excecao interrompe o ciclo e nenhum side effect e
            # iniciado sem trilha persistente.
            self._repo.registrar_recuperacao(
                RegistroRecuperacao(
                    event_id=registro.event_id,
                    decisao='RETRY_AUTORIZADO',
                    estado_observado=registro.estado.value,
                    registrado_em=instante,
                    motivo=politica.justificativa,
                )
            )

            attempt_observado = registro.attempt
            try:
                resultado = self._motor.processar(evento)
            except Exception as exc:  # motor persiste o estado antes de propagar
                atual = self._repo.buscar_por_event_id(registro.event_id) or registro
                return self._registrar(
                    atual,
                    DecisaoRecuperacao.ESCALAR_HUMANO,
                    'retry automatico terminou com excecao controlada',
                    evidencia=type(exc).__name__,
                    instante=instante,
                )

            if resultado.estado == EstadoExecucao.EXECUTING or (
                resultado.estado == EstadoExecucao.FAILED_RETRYABLE
                and resultado.attempt <= attempt_observado
            ):
                return self._registrar(
                    registro,
                    DecisaoRecuperacao.IGNORADO_CONCORRENCIA,
                    'outro worker reivindicou a retentativa',
                    instante=instante,
                    estado_observado=EstadoExecucao.FAILED_RETRYABLE,
                )

            if resultado.estado in (
                EstadoExecucao.WAITING_GATE,
                EstadoExecucao.FAILED_FINAL,
            ):
                return self._registrar(
                    resultado,
                    DecisaoRecuperacao.ESCALAR_HUMANO,
                    f'retry bloqueado ou terminou em {resultado.estado.value}',
                    evidencia=f'attempt={resultado.attempt}',
                    instante=instante,
                    estado_observado=EstadoExecucao.FAILED_RETRYABLE,
                )

            return self._registrar(
                registro,
                DecisaoRecuperacao.RETRY_EXECUTADO,
                'retry automatico executado pelo motor sob politica idempotente',
                evidencia=f'estado_final={resultado.estado.value};attempt={resultado.attempt}',
                instante=instante,
                estado_observado=EstadoExecucao.FAILED_RETRYABLE,
            )

        if estado in (EstadoExecucao.FAILED_FINAL, EstadoExecucao.WAITING_GATE):
            return self._registrar(
                registro,
                DecisaoRecuperacao.ESCALAR_HUMANO,
                f'estado {estado.value} nunca recebe replay automatico',
                instante=instante,
            )

        if estado in self._ESTADOS_EM_ANDAMENTO:
            if instante - registro.atualizado_em >= self._limite_evento_em_andamento:
                return self._registrar(
                    registro,
                    DecisaoRecuperacao.ESCALAR_HUMANO,
                    'evento em andamento excedeu limite; confirmar morte do worker antes de replay',
                    instante=instante,
                )
            return None

        return None
