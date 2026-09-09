"""Executor recuperavel V1 com porta de efeito injetada.

Este modulo nao importa transporte, WhatsApp, Evolution nem Airtable. Ele
descobre uma acao sem claim, recupera e verifica seu envelope, faz CAS da
acao exata e entrega a ``AcaoEnvio`` ja verificada a uma porta injetada.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Protocol

from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivos

from .autorizacao_gate import RepositorioAutorizacoesGate
from .classificador_falha import ClasseFalha, classificar
from .envelope_execucao_autorizada import (
    calcular_identidades_acao,
    recuperar_acao_verificada_v1,
)
from .motor import BACKOFF_BASE_SEGUNDOS, MAX_TENTATIVAS
from .plano_comunicacao import AcaoEnvio
from .repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
    RegistroAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoError,
    RepositorioAcoesExecucaoPlanoPostgres,
)


@dataclasses.dataclass(frozen=True)
class ResultadoExecucaoPorta:
    """Evidencia opaca retornada pela porta, nunca o payload executado."""

    resultado_referencia: str
    evidencia: bytes


class PortaExecucaoAcao(Protocol):
    def executar(self, acao: AcaoEnvio) -> ResultadoExecucaoPorta: ...


@dataclasses.dataclass(frozen=True)
class ResultadoCicloExecutorPersistente:
    situacao: str
    acao_execucao_id: Optional[str]
    registro_final: Optional[RegistroAcaoExecucaoPlano]


class ExecutorAcaoDryRun:
    """Porta deterministica sem I/O, destinada somente a testes/shadow."""

    def executar(self, acao: AcaoEnvio) -> ResultadoExecucaoPorta:
        hashes = calcular_identidades_acao(acao)
        identidade = json.dumps(
            {
                'ordem': acao.ordem,
                'tipo': acao.tipo,
                'destinatario_sha256': hashes.destinatario_sha256,
                'nome_sha256': hashes.nome_sha256,
                'conteudo_sha256': hashes.conteudo_sha256,
                'texto_sha256': hashes.texto_sha256,
            },
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        referencia = hashlib.sha256(identidade).hexdigest()
        return ResultadoExecucaoPorta(
            resultado_referencia=f'dry-run:{referencia}',
            evidencia=b'executor-dry-run-v1',
        )


def _snapshot_identidade(registro: RegistroAcaoExecucaoPlano) -> tuple:
    """Campos imutaveis que o claim nao pode trocar depois da verificacao."""
    return (
        registro.acao_execucao_id,
        registro.event_id,
        registro.preview_id,
        registro.autorizacao_id,
        registro.ordem,
        registro.tipo,
        registro.destinatario_sha256,
        registro.nome_sha256,
        registro.conteudo_sha256,
        registro.texto_sha256,
        registro.envelope_sha256,
    )


def executar_proxima_acao_persistente(
    *,
    repositorio_acoes: RepositorioAcoesExecucaoPlanoPostgres,
    repositorio_autorizacoes: RepositorioAutorizacoesGate,
    armazenamento: ArmazenamentoArquivos,
    porta_execucao: PortaExecucaoAcao,
    event_id: str,
    preview_id: str,
    claim_referencia: str,
    instante: datetime,
) -> ResultadoCicloExecutorPersistente:
    """Executa no maximo uma acao pelo ciclo verificar -> claim exato -> CAS."""
    candidata = repositorio_acoes.buscar_proxima_elegivel(
        event_id=event_id, preview_id=preview_id, instante=instante,
    )
    if candidata is None:
        return ResultadoCicloExecutorPersistente('SEM_ACAO_ELEGIVEL', None, None)

    autorizacao = repositorio_autorizacoes.buscar(
        candidata.event_id, candidata.preview_id,
    )
    if autorizacao is None:
        raise RepositorioAcoesExecucaoPlanoError(
            'autorizacao persistida exata nao encontrada'
        )
    # Todo payload e validado antes do claim. Se qualquer leitura/hash falhar,
    # a linha permanece em seu estado anterior.
    acao = recuperar_acao_verificada_v1(
        armazenamento=armazenamento,
        registro=candidata,
        autorizacao=autorizacao,
    )

    reivindicada = repositorio_acoes.reivindicar_acao_exata(
        acao_execucao_id=candidata.acao_execucao_id,
        claim_referencia=claim_referencia,
        reivindicado_em=instante,
    )
    if reivindicada is None:
        return ResultadoCicloExecutorPersistente(
            'CLAIM_PERDIDO', candidata.acao_execucao_id, None,
        )
    if _snapshot_identidade(reivindicada) != _snapshot_identidade(candidata):
        final = repositorio_acoes.marcar_falha(
            acao_execucao_id=reivindicada.acao_execucao_id,
            claim_referencia=claim_referencia,
            atualizado_em=instante,
            erro_classe='IDENTIDADE_DIVERGENTE_APOS_CLAIM',
            retentavel=False,
        )
        if final is None:
            raise RepositorioAcoesExecucaoPlanoError(
                'claim perdeu titularidade ao bloquear identidade divergente'
            )
        return ResultadoCicloExecutorPersistente(
            'BLOQUEADO_IDENTIDADE_DIVERGENTE',
            reivindicada.acao_execucao_id,
            final,
        )

    try:
        resultado = porta_execucao.executar(acao)
    except Exception as exc:
        classe = classificar(exc)
        retentavel = (
            classe == ClasseFalha.TRANSIENT
            and reivindicada.attempt < MAX_TENTATIVAS
        )
        proxima = None
        if retentavel:
            proxima = instante + timedelta(
                seconds=BACKOFF_BASE_SEGUNDOS
                * (2 ** (reivindicada.attempt - 1))
            )
        final = repositorio_acoes.marcar_falha(
            acao_execucao_id=reivindicada.acao_execucao_id,
            claim_referencia=claim_referencia,
            atualizado_em=instante,
            erro_classe=classe.value,
            retentavel=retentavel,
            proxima_tentativa_em=proxima,
        )
        if final is None:
            raise RepositorioAcoesExecucaoPlanoError(
                'claim perdeu titularidade antes do checkpoint de falha'
            )
        return ResultadoCicloExecutorPersistente(
            'FAILED_RETRYABLE' if retentavel else 'FAILED_FINAL',
            reivindicada.acao_execucao_id,
            final,
        )

    final = repositorio_acoes.marcar_sucesso(
        acao_execucao_id=reivindicada.acao_execucao_id,
        claim_referencia=claim_referencia,
        atualizado_em=instante,
        resultado_referencia=resultado.resultado_referencia,
        evidencia=resultado.evidencia,
    )
    if final is None:
        raise RepositorioAcoesExecucaoPlanoError(
            'claim perdeu titularidade antes do checkpoint de sucesso'
        )
    return ResultadoCicloExecutorPersistente(
        'SUCCEEDED', reivindicada.acao_execucao_id, final,
    )
