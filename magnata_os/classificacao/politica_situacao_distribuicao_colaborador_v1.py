"""Política pura de classificação de situação de distribuição mensal
(Holerite / Folha de Ponto) para um colaborador.

Extrai, como função testável isolada, a decisão hoje duplicada em
`app.py` por `_classificar_holerite_distribuicao` e
`_classificar_folha_ponto_distribuicao` -- as duas calculam a mesma
árvore de decisão (`pronto_ambos` / `pronto_whatsapp_colaborador` /
`pronto_pacote_cliente` / `pendente`) a partir de critérios quase
idênticos, cada uma com sua própria cópia da lógica.

Este módulo não substitui as duas funções em `app.py` (legado
protegido, CLAUDE.md raiz §7) -- app.py não foi tocado. É o primeiro
passo de uma convergência incremental (strangler pattern): código novo,
testado, sem integração ainda. Ver
`/mnt/project-files/magnata-os/orquestrador.md` para a sequência
completa de PRs proposta.

Nunca importa Flask, Airtable, driver de banco ou cliente HTTP -- só
tipo Python puro, conforme `magnata_os/CLAUDE.md`.
"""
from __future__ import annotations

import dataclasses
from typing import Mapping, Tuple

__all__ = [
    'SITUACAO_PRONTO_AMBOS',
    'SITUACAO_PRONTO_WHATSAPP_COLABORADOR',
    'SITUACAO_PRONTO_PACOTE_CLIENTE',
    'SITUACAO_PENDENTE',
    'CriteriosDistribuicaoColaborador',
    'ResultadoClassificacaoDistribuicao',
    'classificar_situacao_distribuicao',
]

SITUACAO_PRONTO_AMBOS = 'pronto_ambos'
SITUACAO_PRONTO_WHATSAPP_COLABORADOR = 'pronto_whatsapp_colaborador'
SITUACAO_PRONTO_PACOTE_CLIENTE = 'pronto_pacote_cliente'
SITUACAO_PENDENTE = 'pendente'


@dataclasses.dataclass(frozen=True)
class CriteriosDistribuicaoColaborador:
    """Critérios já resolvidos pelo chamador (identificação de
    funcionário/cliente, disponibilidade de WhatsApp/e-mail) -- este
    módulo nunca busca nem resolve nada, só decide a partir do que
    recebe.

    `requisitos_documentais` mapeia motivo -> satisfeito. Cada chave
    insatisfeita (valor `False`) entra em `motivos` com o próprio nome
    da chave. Permite generalizar Holerite (2 requisitos: arquivo +
    folha mensal) e Folha de Ponto (1 requisito: anexo) sem duplicar a
    árvore de decisão.
    """

    funcionario_identificado: bool
    whatsapp_disponivel: bool
    requisitos_documentais: Mapping[str, bool]
    cliente_identificado: bool
    email_cliente_disponivel: bool


@dataclasses.dataclass(frozen=True)
class ResultadoClassificacaoDistribuicao:
    situacao: str
    ok_whatsapp: bool
    ok_cliente: bool
    motivos: Tuple[str, ...]


def classificar_situacao_distribuicao(
    criterios: CriteriosDistribuicaoColaborador,
) -> ResultadoClassificacaoDistribuicao:
    """Mesma árvore de decisão hoje duplicada em `app.py`:

    - `pronto_ambos`: WhatsApp do colaborador E pacote do cliente, os
      dois com todo requisito documental satisfeito;
    - `pronto_whatsapp_colaborador`: só o envio direto ao colaborador;
    - `pronto_pacote_cliente`: só o pacote ao cliente;
    - `pendente`: nenhum dos dois caminhos está pronto.

    Documentos ausentes/incompletos bloqueiam os dois caminhos por
    igual -- um requisito documental insatisfeito nunca libera só
    metade do fluxo.
    """
    documentos_ok = all(criterios.requisitos_documentais.values())

    motivos = []
    if not criterios.funcionario_identificado:
        motivos.append('funcionario_nao_identificado')
    if not criterios.whatsapp_disponivel:
        motivos.append('whatsapp_ausente')
    motivos.extend(
        motivo
        for motivo, satisfeito in criterios.requisitos_documentais.items()
        if not satisfeito
    )
    if not criterios.cliente_identificado:
        motivos.append('cliente_local_nao_identificado')
    elif not criterios.email_cliente_disponivel:
        motivos.append('email_cliente_ausente')

    ok_whatsapp = bool(
        criterios.funcionario_identificado
        and criterios.whatsapp_disponivel
        and documentos_ok
    )
    ok_cliente = bool(
        criterios.cliente_identificado
        and criterios.email_cliente_disponivel
        and documentos_ok
    )

    if ok_whatsapp and ok_cliente:
        situacao = SITUACAO_PRONTO_AMBOS
    elif ok_whatsapp:
        situacao = SITUACAO_PRONTO_WHATSAPP_COLABORADOR
    elif ok_cliente:
        situacao = SITUACAO_PRONTO_PACOTE_CLIENTE
    else:
        situacao = SITUACAO_PENDENTE

    return ResultadoClassificacaoDistribuicao(
        situacao=situacao,
        ok_whatsapp=ok_whatsapp,
        ok_cliente=ok_cliente,
        motivos=tuple(motivos),
    )
