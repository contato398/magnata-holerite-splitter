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

from .contratos import DimensaoResolucao, EstadoResolucaoDimensao, ResultadoResolucaoSemantico
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


def reconciliar_origem_com_resolucao_semantica(
    tipo_origem: str, resolucao: ResultadoResolucaoSemantico,
) -> ReconciliacaoOrigemConteudo:
    """Pura, sem I/O -- nunca consulta nada, só lê `resolucao` já
    composta. `tipo_origem` é sempre um valor já atribuído por fora
    (nome de tabela Airtable, campo de tipo, remetente etc.) -- este
    módulo nunca decide qual origem usar."""
    if not tipo_origem.strip():
        raise ValueError('tipo_origem deve ser texto nao vazio')

    resolucao_tipo = next(
        (r for r in resolucao.resolucoes if r.dimensao == DimensaoResolucao.TIPO_DOCUMENTAL), None,
    )
    if (
        resolucao_tipo is None
        or resolucao_tipo.estado != EstadoResolucaoDimensao.RESOLVIDA
        or len(resolucao_tipo.valores_confirmados) != 1
    ):
        return ReconciliacaoOrigemConteudo(
            tipo_origem=tipo_origem, tipo_resolvido=None,
            resultado=ResultadoReconciliacaoOrigem.SEM_RESOLUCAO,
        )

    tipo_resolvido = resolucao_tipo.valores_confirmados[0].entidade_id
    concordam = (
        _normalizar_para_vocabulario_canonico(tipo_origem)
        == _normalizar_para_vocabulario_canonico(tipo_resolvido)
    )
    resultado = ResultadoReconciliacaoOrigem.REFORCO if concordam else ResultadoReconciliacaoOrigem.CONFLITO
    return ReconciliacaoOrigemConteudo(
        tipo_origem=tipo_origem, tipo_resolvido=tipo_resolvido, resultado=resultado,
    )
