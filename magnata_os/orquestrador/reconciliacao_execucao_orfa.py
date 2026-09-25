"""Reconciliação humana de ações presas em `EXECUTING` (bloqueio EXECUTING
órfão). Regra pétrea: worker morto ≠ mensagem não enviada -- nenhuma
função aqui é chamada por scheduler, cron ou timeout; todas exigem
`ator_referencia` e `motivo` explícitos, sem default, e todas passam pelo
mesmo CAS já existente em `RepositorioAcoesExecucaoPlanoPostgres`.

Caso B (não sabemos se houve envio) não tem função aqui de propósito: a
ausência de mecanismo É a garantia -- ver `listar_em_execucao_reivindicadas_antes_de`
para a visão somente leitura que só lista, nunca decide.

Caso D (reenvio deliberado apesar da incerteza) também não tem função
aqui: por desenho, ele nunca toca a ação antiga -- reaproveita
integralmente o pipeline já existente de intenção → prévia → autorização
→ novo plano, com um `acao_execucao_id` novo. Ver ADR do wiring para o
motivo dessa escolha.

Gate 3 (fim do módulo): reconciliação humana de ações em `FAILED_FINAL`
com `ultimo_erro_classe = ENVIO_EXTERNO_INCERTO` -- ver
`docs/decisoes/reconciliacao-envio-incerto-v1.md`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from .autorrecuperacao import DecisaoRecuperacao
from .repositorio_acoes_execucao_plano_postgres import (
    CLASSE_ENVIO_EXTERNO_INCERTO,
    EstadoAcaoExecucaoPlano,
    RegistroAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoError,
    RepositorioAcoesExecucaoPlanoPostgres,
)
from .repositorio_execucoes import RegistroRecuperacao, RepositorioExecucoes


def _exigir_texto_nao_vazio(valor: str, nome_campo: str) -> str:
    limpo = str(valor or '').strip()
    if not limpo:
        raise RepositorioAcoesExecucaoPlanoError(
            f'{nome_campo} é obrigatório para reconciliação manual -- '
            'nunca automática'
        )
    return limpo


def liberar_acao_orfa_sem_envio_confirmado(
    *,
    repositorio_acoes: RepositorioAcoesExecucaoPlanoPostgres,
    repositorio_execucoes: RepositorioExecucoes,
    acao: RegistroAcaoExecucaoPlano,
    ator_referencia: str,
    motivo: str,
    evidencia_ausencia_envio: str,
    instante: datetime,
) -> Optional[RegistroAcaoExecucaoPlano]:
    """Caso A: um humano confirmou, fora de banda, que a ação em EXECUTING
    não teve side effect externo. Libera para FAILED_RETRYABLE (nunca para
    SUCCEEDED) e registra, no mesmo golpe, uma `RegistroRecuperacao`
    (tabela já existente `auditoria_recuperacao`) com quem autorizou e por
    quê -- nunca só a liberação silenciosa do claim."""
    ator_referencia = _exigir_texto_nao_vazio(ator_referencia, 'ator_referencia')
    motivo = _exigir_texto_nao_vazio(motivo, 'motivo')
    evidencia_ausencia_envio = _exigir_texto_nao_vazio(
        evidencia_ausencia_envio, 'evidencia_ausencia_envio',
    )

    resultado = repositorio_acoes.liberar_apos_confirmacao_ausencia_envio(
        acao_execucao_id=acao.acao_execucao_id,
        claim_sha256_atual=acao.claim_sha256,
        atualizado_em=instante,
    )
    if resultado is None:
        # CAS perdeu titularidade (ação já não está mais EXECUTING com o
        # mesmo claim) -- nunca insiste, nunca finge que liberou.
        return None

    repositorio_execucoes.registrar_recuperacao(RegistroRecuperacao(
        event_id=acao.event_id,
        decisao=DecisaoRecuperacao.LIBERACAO_MANUAL_ACAO_SEM_ENVIO.value,
        estado_observado='EXECUTING',
        registrado_em=instante,
        motivo=f'ator={ator_referencia}; acao_execucao_id={acao.acao_execucao_id}; {motivo}',
        evidencia=evidencia_ausencia_envio,
    ))
    return resultado


def reconciliar_acao_orfa_com_envio_confirmado(
    *,
    repositorio_acoes: RepositorioAcoesExecucaoPlanoPostgres,
    repositorio_execucoes: RepositorioExecucoes,
    acao: RegistroAcaoExecucaoPlano,
    ator_referencia: str,
    resultado_referencia_externo: str,
    evidencia: bytes,
    instante: datetime,
) -> Optional[RegistroAcaoExecucaoPlano]:
    """Caso C: evidência externa (ex.: log/painel da Evolution) confirma
    que a mensagem foi entregue. Reconcilia para SUCCEEDED com o ID
    externo -- nunca reenvia."""
    ator_referencia = _exigir_texto_nao_vazio(ator_referencia, 'ator_referencia')
    resultado_referencia_externo = _exigir_texto_nao_vazio(
        resultado_referencia_externo, 'resultado_referencia_externo',
    )

    resultado = repositorio_acoes.reconciliar_envio_confirmado(
        acao_execucao_id=acao.acao_execucao_id,
        claim_sha256_atual=acao.claim_sha256,
        atualizado_em=instante,
        resultado_referencia=resultado_referencia_externo,
        evidencia=evidencia,
    )
    if resultado is None:
        return None

    repositorio_execucoes.registrar_recuperacao(RegistroRecuperacao(
        event_id=acao.event_id,
        decisao=DecisaoRecuperacao.RETRY_EXECUTADO.value,
        estado_observado='EXECUTING',
        registrado_em=instante,
        motivo=(
            f'ator={ator_referencia}; acao_execucao_id={acao.acao_execucao_id}; '
            'reconciliação: envio já confirmado externamente, sem reenvio'
        ),
        evidencia=resultado_referencia_externo,
    ))
    return resultado


# ---------------------------------------------------------------------------
# Gate 3 -- reconciliação humana de ENVIO EXTERNO INCERTO.
#
# Escopo exclusivo: ação em `FAILED_FINAL` com
# `ultimo_erro_classe = ENVIO_EXTERNO_INCERTO`. Qualquer outro estado ou
# classe é rejeitado aqui (fail-closed) E pelo CAS no banco. Nenhuma
# heurística sobre texto de erro; nenhuma chamada de transporte; nenhum
# retry automático. O "caso C" (continua incerto) não tem função: a ação
# fica como está e segue bloqueando as posteriores do mesmo destinatário
# -- a ausência de mecanismo "prosseguir mesmo assim" é a garantia.
# ---------------------------------------------------------------------------


def _exigir_envio_incerto(acao: RegistroAcaoExecucaoPlano) -> None:
    if (
        acao.estado != EstadoAcaoExecucaoPlano.FAILED_FINAL
        or acao.ultimo_erro_classe != CLASSE_ENVIO_EXTERNO_INCERTO
    ):
        raise RepositorioAcoesExecucaoPlanoError(
            'reconciliação de envio incerto só se aplica a FAILED_FINAL com '
            f'ultimo_erro_classe={CLASSE_ENVIO_EXTERNO_INCERTO}; '
            f'observado estado={getattr(acao.estado, "value", acao.estado)} '
            f'classe={acao.ultimo_erro_classe}'
        )


def _hook_auditoria(
    repositorio_execucoes: RepositorioExecucoes, registro: RegistroRecuperacao,
):
    def _gravar(cursor) -> None:
        repositorio_execucoes.registrar_recuperacao_na_transacao(cursor, registro)
    return _gravar


def liberar_envio_incerto_sem_envio_confirmado(
    *,
    repositorio_acoes: RepositorioAcoesExecucaoPlanoPostgres,
    repositorio_execucoes: RepositorioExecucoes,
    acao: RegistroAcaoExecucaoPlano,
    ator_referencia: str,
    motivo: str,
    evidencia_ausencia_envio: str,
    instante: datetime,
) -> Optional[RegistroAcaoExecucaoPlano]:
    """Caso A: um humano tem evidência de que o envio incerto NÃO ocorreu.
    `FAILED_FINAL` -> `FAILED_RETRYABLE` (nunca SUCCEEDED), com a trilha
    humana gravada na MESMA transação. `attempt` preservado; o próximo
    claim real incrementa e `MAX_TENTATIVAS` continua valendo. As ações
    posteriores continuam bloqueadas até esta chegar a SUCCEEDED.
    Retorna None se o CAS perdeu (outra decisão/estado mudou) -- nunca
    insiste."""
    ator_referencia = _exigir_texto_nao_vazio(ator_referencia, 'ator_referencia')
    motivo = _exigir_texto_nao_vazio(motivo, 'motivo')
    evidencia_ausencia_envio = _exigir_texto_nao_vazio(
        evidencia_ausencia_envio, 'evidencia_ausencia_envio',
    )
    _exigir_envio_incerto(acao)

    registro = RegistroRecuperacao(
        event_id=acao.event_id,
        decisao=DecisaoRecuperacao.RECONCILIACAO_MANUAL_ENVIO_INCERTO_SEM_ENVIO.value,
        estado_observado=EstadoAcaoExecucaoPlano.FAILED_FINAL.value,
        registrado_em=instante,
        motivo=(
            f'ator={ator_referencia}; acao_execucao_id={acao.acao_execucao_id}; '
            f'attempt={acao.attempt}; {motivo}'
        ),
        evidencia=evidencia_ausencia_envio,
    )
    return repositorio_acoes.liberar_envio_incerto_para_retry(
        acao=acao, atualizado_em=instante,
        na_mesma_transacao=_hook_auditoria(repositorio_execucoes, registro),
    )


def confirmar_envio_incerto_como_enviado(
    *,
    repositorio_acoes: RepositorioAcoesExecucaoPlanoPostgres,
    repositorio_execucoes: RepositorioExecucoes,
    acao: RegistroAcaoExecucaoPlano,
    ator_referencia: str,
    motivo: str,
    resultado_referencia_externo: str,
    evidencia_envio: str,
    instante: datetime,
) -> Optional[RegistroAcaoExecucaoPlano]:
    """Caso B: evidência externa suficiente de que o envio incerto
    OCORREU. `FAILED_FINAL` -> `SUCCEEDED` sem reenvio, com o id externo e
    o hash da evidência; a trilha humana nasce na mesma transação. A
    próxima ação do destinatário fica elegível pelo predicado sequencial
    já existente. Retorna None se o CAS perdeu."""
    ator_referencia = _exigir_texto_nao_vazio(ator_referencia, 'ator_referencia')
    motivo = _exigir_texto_nao_vazio(motivo, 'motivo')
    resultado_referencia_externo = _exigir_texto_nao_vazio(
        resultado_referencia_externo, 'resultado_referencia_externo',
    )
    evidencia_envio = _exigir_texto_nao_vazio(evidencia_envio, 'evidencia_envio')
    _exigir_envio_incerto(acao)

    registro = RegistroRecuperacao(
        event_id=acao.event_id,
        decisao=DecisaoRecuperacao.RECONCILIACAO_MANUAL_ENVIO_INCERTO_ENVIADO.value,
        estado_observado=EstadoAcaoExecucaoPlano.FAILED_FINAL.value,
        registrado_em=instante,
        motivo=(
            f'ator={ator_referencia}; acao_execucao_id={acao.acao_execucao_id}; '
            f'attempt={acao.attempt}; resultado_referencia={resultado_referencia_externo}; '
            f'{motivo}'
        ),
        evidencia=evidencia_envio,
    )
    return repositorio_acoes.confirmar_envio_incerto_enviado(
        acao=acao, atualizado_em=instante,
        resultado_referencia=resultado_referencia_externo,
        evidencia=evidencia_envio.encode('utf-8'),
        na_mesma_transacao=_hook_auditoria(repositorio_execucoes, registro),
    )
