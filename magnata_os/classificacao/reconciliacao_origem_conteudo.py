"""Reconciliação origem declarada × resultado semântico (missão
"AUTOMAÇÃO DOCUMENTAL REAL V1", §12 — REGRA CRÍTICA: "O fato de um
documento estar na tabela 'Holerites' NÃO prova sozinho que ele é um
Holerite... quando houver conteúdo disponível, origem declarada vs.
resultado semântico devem ser comparados. Se concordarem: reforço. Se
divergirem: CONFLITO/revisão. Isso impede o Airtable de virar cérebro
semântico.").

Este módulo NUNCA decide um tipo sozinho — só COMPARA um `tipo_origem`
já atribuído por uma fonte externa (nome de tabela, campo de tipo do
Airtable, remetente, qualquer contexto — nunca conteúdo) com o
`tipo_documental` já RESOLVIDO pelo motor semântico único
(`resolver_tipo_documental`/`compor_resolucao_semantica`) para o MESMO
documento. Concordância vira `REFORCO` (nunca promove uma evidência
FRACA a FORTE sozinha — só confirma o que já era verdade); divergência
vira `CONFLITO` explícito, NUNCA uma reescrita silenciosa da origem
pelo conteúdo nem do conteúdo pela origem.

CORREÇÃO (ADENDO OBRIGATÓRIO, item 2): antes de comparar, os dois lados
são normalizados para o vocabulário canônico via `TRADUCAO_FAMILIA_B_
PARA_MOTOR_GERAL` (já existente, `normalizacao_requisitos_prestacao.py`
— nunca uma segunda tabela de tradução, nunca fuzzy matching, nunca
sinônimo inventado). Ex.: origem `'extrato_cliente'` (vocabulário
Família B) e conteúdo resolvido `'Extrato da Folha de Pagamento'`
(motor geral) são o MESMO tipo canônico — nunca um `CONFLITO` falso.
Só uma equivalência JÁ comprovada e registrada nessa tradução conta;
qualquer outra divergência de nome continua `CONFLITO`, como deve
ser."""
from __future__ import annotations

import dataclasses
import enum
from typing import Optional

from .contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ResolucaoDimensao,
    ResultadoResolucaoSemantico,
)
from .normalizacao_requisitos_prestacao import TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL


def _normalizar_para_vocabulario_canonico(tipo: str) -> str:
    """Traduz um tipo do vocabulário Família B para o motor geral
    quando existir equivalência JÁ comprovada — nunca inventa uma
    tradução nova, nunca aproxima por nome parecido."""
    return TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL.get(tipo, tipo)


class ResultadoReconciliacaoOrigem(str, enum.Enum):
    REFORCO = 'REFORCO'
    CONFLITO = 'CONFLITO'
    SEM_RESOLUCAO = 'SEM_RESOLUCAO'
    """O motor semântico ainda não RESOLVEU o tipo para este documento
    (AMBIGUA/NAO_ENCONTRADA/etc.) -- nada a reconciliar ainda; nunca
    confundido com REFORCO nem CONFLITO."""


@dataclasses.dataclass(frozen=True)
class ReconciliacaoOrigemConteudo:
    tipo_origem: str
    tipo_resolvido: Optional[str]
    resultado: ResultadoReconciliacaoOrigem


def reconciliar_origem_com_tipo_resolvido(
    tipo_origem: str, tipo_resolvido: Optional[str],
) -> ReconciliacaoOrigemConteudo:
    """Núcleo puro da reconciliação -- extraído (missão "INTEGRAÇÃO REAL
    DO CONTEÚDO DOCUMENTAL", Fase 5/7: "não duplicar decisão") para que
    qualquer ponto do corredor que só tenha o TIPO já resolvido em mãos
    (`Optional[str]`, `None` = motor ainda não resolveu — ex.: a ponte
    conteúdo->motor, que produz uma `ResolucaoDimensao` isolada antes de
    um `ResultadoResolucaoSemantico` completo existir) reaproveite a
    MESMA lógica, nunca uma segunda tabela de comparação. `tipo_origem`
    é sempre um valor já atribuído por fora (nome de tabela Airtable,
    campo de tipo, remetente etc.) -- este módulo nunca decide qual
    origem usar."""
    if not tipo_origem.strip():
        raise ValueError('tipo_origem deve ser texto nao vazio')
    if tipo_resolvido is None:
        return ReconciliacaoOrigemConteudo(
            tipo_origem=tipo_origem, tipo_resolvido=None,
            resultado=ResultadoReconciliacaoOrigem.SEM_RESOLUCAO,
        )
    concordam = (
        _normalizar_para_vocabulario_canonico(tipo_origem)
        == _normalizar_para_vocabulario_canonico(tipo_resolvido)
    )
    resultado = ResultadoReconciliacaoOrigem.REFORCO if concordam else ResultadoReconciliacaoOrigem.CONFLITO
    return ReconciliacaoOrigemConteudo(
        tipo_origem=tipo_origem, tipo_resolvido=tipo_resolvido, resultado=resultado,
    )


def tipo_resolvido_da_dimensao(resolucao: ResolucaoDimensao) -> Optional[str]:
    """Extrai o tipo documental já RESOLVIDO de uma `ResolucaoDimensao`
    isolada (dimensão TIPO_DOCUMENTAL, exatamente 1 valor confirmado) --
    extraído (missão "INTEGRAÇÃO REAL DO CONTEÚDO DOCUMENTAL", Fase 5:
    "não duplicar decisão") de dentro de `reconciliar_origem_com_
    resolucao_semantica` para que qualquer ponto do corredor que só
    tenha a `ResolucaoDimensao` isolada em mãos (ex.: `politica_
    classificacao_semantica.py`, que ainda não tem um `ResultadoResolucao
    Semantico` completo -- só a dimensão TIPO_DOCUMENTAL já resolvida
    pela ponte conteúdo->motor) reaproveite a MESMA extração, nunca uma
    segunda leitura de `valores_confirmados`. Qualquer outro estado
    (AMBIGUA/CONFLITO/NAO_ENCONTRADA/etc.) ou mais de 1 valor confirmado
    vira `None` -- nunca inventa um tipo a partir de um estado que não é
    RESOLVIDA."""
    if resolucao.estado != EstadoResolucaoDimensao.RESOLVIDA:
        return None
    if len(resolucao.valores_confirmados) != 1:
        return None
    return resolucao.valores_confirmados[0].entidade_id


def reconciliar_origem_com_resolucao_semantica(
    tipo_origem: str, resolucao: ResultadoResolucaoSemantico,
) -> ReconciliacaoOrigemConteudo:
    """Pura, sem I/O -- nunca consulta nada, só lê `resolucao` já
    composta. Extrai o tipo já RESOLVIDO (dimensão TIPO_DOCUMENTAL,
    exatamente 1 valor confirmado — qualquer outro estado vira `None`,
    tratado como `SEM_RESOLUCAO` por `reconciliar_origem_com_tipo_
    resolvido`) e delega a ele -- nunca duplica a comparação."""
    if not tipo_origem.strip():
        raise ValueError('tipo_origem deve ser texto nao vazio')

    resolucao_tipo = next(
        (r for r in resolucao.resolucoes if r.dimensao == DimensaoResolucao.TIPO_DOCUMENTAL), None,
    )
    tipo_resolvido = tipo_resolvido_da_dimensao(resolucao_tipo) if resolucao_tipo is not None else None

    return reconciliar_origem_com_tipo_resolvido(tipo_origem, tipo_resolvido)
