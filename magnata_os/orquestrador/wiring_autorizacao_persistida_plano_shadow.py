"""Fato de autorizacao de gate -> PlanoDisparo, V1 shadow.

Reutiliza o wiring do PR #137, mas remove do caller a possibilidade de declarar
um booleano solto como prova de autorizacao: o plano so e materializado a partir
de um RegistroAutorizacaoGate previamente registrado para o event_id/preview_id
exatos. Continua sem transporte e sem alterar WAITING_GATE.
"""
from __future__ import annotations

from typing import Iterable

from .autorizacao_gate import DecisaoGate, RegistroAutorizacaoGate
from .plano_comunicacao import ConteudoItem
from .wiring_autorizacao_plano_shadow import (
    ResultadoAutorizacaoPlanoShadow,
    WiringAutorizacaoPlanoError,
    materializar_plano_autorizado_shadow,
)
from .wiring_prestacao_comunicacao_shadow import IntencaoComunicacaoPrestacao
from .repositorio_execucoes import RepositorioExecucoes


def materializar_plano_com_autorizacao_persistida_shadow(
    *,
    intencao: IntencaoComunicacaoPrestacao,
    repositorio_execucoes: RepositorioExecucoes,
    autorizacao: RegistroAutorizacaoGate,
    texto: str,
    conteudos: Iterable[ConteudoItem] = (),
) -> ResultadoAutorizacaoPlanoShadow:
    """Materializa somente quando o fato autorizado pertence a esta intencao."""
    event_id_esperado = f'comunicacao:{intencao.intencao_id}'
    if autorizacao.event_id != event_id_esperado:
        raise WiringAutorizacaoPlanoError('autorizacao pertence a outro evento')
    if autorizacao.preview_id != intencao.preview.preview_id:
        raise WiringAutorizacaoPlanoError('autorizacao pertence a outra previa')
    if autorizacao.decisao != DecisaoGate.AUTORIZADO:
        raise WiringAutorizacaoPlanoError('gate nao foi autorizado')

    return materializar_plano_autorizado_shadow(
        intencao=intencao,
        repositorio=repositorio_execucoes,
        texto=texto,
        conteudos=conteudos,
        preview_id_autorizado=autorizacao.preview_id,
        autorizacao_explicita=True,
    )
