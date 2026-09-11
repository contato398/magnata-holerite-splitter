"""Observador idempotente do ciclo de assinatura, por `acao_execucao_id`.

Só consulta (via `PortaObrigacaoAssinatura.consultar_por_correlacao`,
estritamente read-only) e registra transições duráveis
(`RepositorioConclusaoObrigacaoAssinaturaPostgres`, append-only). Nunca
cria obrigação, nunca envia WhatsApp, nunca altera a assinatura em si, e
nunca duplica uma transição já registrada -- idempotente por comparação
com o último estado persistido.

Mapeamento do legado (Pendente/Assinado + comprovante_existe) para o
vocabulário fechado da migration 0006: o legado hoje não distingui
"comprovante existe mas não validado" de "comprovante existe e válido" --
por isso `COMPROVANTE_VALIDADO` nunca é emitido por este observador na
V1 (documentado, não inventado); `CONCLUIDO` já implica comprovante
presente.
"""
from __future__ import annotations

from datetime import datetime

from .adapters.postgres_conclusao_obrigacao_assinatura import (
    RegistroConclusaoObrigacaoAssinatura,
    RepositorioConclusaoObrigacaoAssinaturaPostgres,
)
from .obrigacao_assinatura import ObrigacaoAssinatura, PortaObrigacaoAssinatura


def _mapear_estado(obrigacao: ObrigacaoAssinatura) -> str:
    if obrigacao.status != 'Assinado':
        return 'AGUARDANDO_ASSINATURA'
    return 'CONCLUIDO' if obrigacao.tem_comprovante else 'ASSINADO'


def observar_e_registrar_transicao(
    *,
    porta_assinatura: PortaObrigacaoAssinatura,
    repositorio_conclusao: RepositorioConclusaoObrigacaoAssinaturaPostgres,
    acao_execucao_id: str,
    instante: datetime,
) -> str | None:
    """Um ciclo de observação: consulta, compara com o último estado
    durável e só registra (append) se houve mudança real. Retorna o
    estado observado, ou None se a obrigação ainda não existe."""
    obrigacao = porta_assinatura.consultar_por_correlacao(
        acao_execucao_id=acao_execucao_id,
    )
    if obrigacao is None:
        return None

    novo_estado = _mapear_estado(obrigacao)
    estado_anterior = repositorio_conclusao.estado_mais_recente(acao_execucao_id)
    if novo_estado == estado_anterior:
        # Idempotente: nenhuma mudança real, nenhum registro novo --
        # nunca duplica histórico só porque foi consultado de novo.
        return novo_estado

    repositorio_conclusao.registrar_transicao(RegistroConclusaoObrigacaoAssinatura(
        acao_execucao_id=acao_execucao_id,
        estado=novo_estado,
        correlacao_externa=obrigacao.assinatura_id or None,
        evidencia_sha256=None,
        registrado_em=instante,
    ))
    return novo_estado
