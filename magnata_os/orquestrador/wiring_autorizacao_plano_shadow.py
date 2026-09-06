"""Wiring de autorizacao -> PlanoDisparo, V1 shadow, sem transporte.

Esta camada fecha o segundo encaixe do corredor de comunicacao:
uma intencao de Prestacao ja persistida em ``WAITING_GATE`` somente pode
materializar um ``PlanoDisparo`` se a autorizacao explicita corresponder
exatamente ao ``preview_id`` visto pelo operador.

Regras duras:
- exige que a intencao anterior exista no repositorio;
- exige estado ``WAITING_GATE``;
- revalida a autorizacao pela politica canonica existente;
- revalida o texto e os conteudos contra a previa;
- nao altera estado do Orquestrador;
- nao persiste conteudo sensivel;
- nao importa nem chama transporte, Evolution, Flask, Airtable ou requests.

A persistencia da autorizacao como fato operacional proprio fica fora desta V1:
este modulo prova a materializacao segura do plano sem inventar uma segunda
fila ou enfraquecer a maquina de estados atual.
"""
from __future__ import annotations

import dataclasses
from typing import Iterable

from .eventos import EstadoExecucao, TipoEvento
from .plano_comunicacao import ConteudoItem, PlanoDisparo, montar_plano_disparo
from .repositorio_execucoes import RepositorioExecucoes
from .wiring_prestacao_comunicacao_shadow import IntencaoComunicacaoPrestacao


class WiringAutorizacaoPlanoError(ValueError):
    """Autorizacao/plano incompatível com a intencao persistida."""


@dataclasses.dataclass(frozen=True)
class ResultadoAutorizacaoPlanoShadow:
    intencao_id: str
    pacote_id: str
    preview_id: str
    plano: PlanoDisparo


def materializar_plano_autorizado_shadow(
    *,
    intencao: IntencaoComunicacaoPrestacao,
    repositorio: RepositorioExecucoes,
    texto: str,
    conteudos: Iterable[ConteudoItem] = (),
    preview_id_autorizado: str | None,
    autorizacao_explicita: bool,
) -> ResultadoAutorizacaoPlanoShadow:
    """Materializa o plano exato autorizado e para antes do transporte."""

    event_id = f'comunicacao:{intencao.intencao_id}'
    registro = repositorio.buscar_por_event_id(event_id)
    if registro is None:
        raise WiringAutorizacaoPlanoError(
            'intencao de comunicacao nao encontrada no repositorio'
        )
    if registro.event_type != TipoEvento.COMUNICACAO_SOLICITADA.value:
        raise WiringAutorizacaoPlanoError(
            'registro encontrado nao corresponde a COMUNICACAO_SOLICITADA'
        )
    if registro.estado != EstadoExecucao.WAITING_GATE:
        raise WiringAutorizacaoPlanoError(
            f'intencao deve estar em WAITING_GATE; estado atual {registro.estado.value}'
        )

    plano = montar_plano_disparo(
        preview=intencao.preview,
        texto=texto,
        conteudos=conteudos,
        preview_id_autorizado=preview_id_autorizado,
        autorizacao_explicita=autorizacao_explicita,
    )

    return ResultadoAutorizacaoPlanoShadow(
        intencao_id=intencao.intencao_id,
        pacote_id=intencao.pacote_id,
        preview_id=intencao.preview.preview_id,
        plano=plano,
    )
