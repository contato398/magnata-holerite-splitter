"""Classificação fina do motivo de não-avanço automático + métrica de
automação (missão "AUTOMAÇÃO DOCUMENTAL REAL V1", §14/§20).

NUNCA recalcula RESOLVIDA/PARCIAL/INCONCLUSIVA/... — essa decisão já
existe e é única (`resolucao_semantica.compor_resolucao_semantica`,
`ResultadoResolucaoSemantico.estado_consolidado`/`necessita_revisao_
humana`/`pronto_para_routing_logico`). Este módulo só CLASSIFICA, para
observabilidade e métrica, qual dos motivos abaixo levou um resultado a
não avançar sozinho — inspecionando os estados já existentes de cada
`ResolucaoDimensao` (nunca um score numérico novo — reusa `NivelConfianca`/
`EstadoResolucaoDimensao`, já qualitativos, cláusula pétrea da missão:
"não reduzir o sistema a um score universal simplista se os contratos
existentes já modelam força/confiança qualitativa").

Política (§14):
  RESOLVIDA (estado_consolidado) -> AVANCA_AUTOMATICO, sempre — a única
    fonte de verdade sobre "resolvido" continua sendo `compor_resolucao_
    semantica`, nunca recalculada aqui.
  Não resolvida -> classificada pelo estado mais grave entre as
    dimensões, nesta ordem (mais grave nunca mascarado por um estado
    menos grave que também exista): ERRO_TECNICO > CONFLITO > AMBIGUA >
    NAO_ENCONTRADA (desconhecido) > revisão genérica (INVALIDA e
    quaisquer outros casos residuais)."""
from __future__ import annotations

import dataclasses
import enum
from typing import Tuple

from .contratos import EstadoResolucaoDimensao, EstadoResultadoSemantico, ResultadoResolucaoSemantico


class DecisaoAutomacao(str, enum.Enum):
    AVANCA_AUTOMATICO = 'AVANCA_AUTOMATICO'
    REVISAO_HUMANA = 'REVISAO_HUMANA'
    AMBIGUO = 'AMBIGUO'
    CONFLITO = 'CONFLITO'
    RETRY_TECNICO = 'RETRY_TECNICO'
    DESCONHECIDO = 'DESCONHECIDO'


def decidir_proxima_acao(resultado: ResultadoResolucaoSemantico) -> DecisaoAutomacao:
    """Pura, sem I/O. Nunca inventa uma decisão a partir de um estado
    que a própria composição semântica não expôs."""
    if resultado.estado_consolidado == EstadoResultadoSemantico.RESOLVIDA:
        return DecisaoAutomacao.AVANCA_AUTOMATICO
    if resultado.estado_consolidado == EstadoResultadoSemantico.ERRO_TECNICO:
        return DecisaoAutomacao.RETRY_TECNICO

    estados = {r.estado for r in resultado.resolucoes}
    if EstadoResolucaoDimensao.ERRO_TECNICO in estados:
        return DecisaoAutomacao.RETRY_TECNICO
    if EstadoResolucaoDimensao.CONFLITO in estados:
        return DecisaoAutomacao.CONFLITO
    if EstadoResolucaoDimensao.AMBIGUA in estados:
        return DecisaoAutomacao.AMBIGUO
    if EstadoResolucaoDimensao.NAO_ENCONTRADA in estados:
        return DecisaoAutomacao.DESCONHECIDO
    return DecisaoAutomacao.REVISAO_HUMANA


@dataclasses.dataclass(frozen=True)
class MetricasAutomacao:
    total: int
    auto_resolvidos: int
    revisao: int
    ambiguos: int
    conflitos: int
    erros: int
    desconhecidos: int

    def __post_init__(self) -> None:
        soma = self.auto_resolvidos + self.revisao + self.ambiguos + self.conflitos + self.erros + self.desconhecidos
        if soma != self.total:
            raise ValueError('soma das categorias deve ser igual ao total -- nunca perder nem duplicar um resultado')

    @property
    def percentual_automacao(self) -> float:
        if self.total == 0:
            return 0.0
        return round(100.0 * self.auto_resolvidos / self.total, 2)


_CAMPO_POR_DECISAO = {
    DecisaoAutomacao.AVANCA_AUTOMATICO: 'auto_resolvidos',
    DecisaoAutomacao.REVISAO_HUMANA: 'revisao',
    DecisaoAutomacao.AMBIGUO: 'ambiguos',
    DecisaoAutomacao.CONFLITO: 'conflitos',
    DecisaoAutomacao.RETRY_TECNICO: 'erros',
    DecisaoAutomacao.DESCONHECIDO: 'desconhecidos',
}


def calcular_metricas_automacao(resultados: Tuple[ResultadoResolucaoSemantico, ...]) -> MetricasAutomacao:
    """Agrega `decidir_proxima_acao` sobre um lote -- nunca reavalia
    nenhum resultado individualmente além de classificá-lo."""
    contagens = {campo: 0 for campo in _CAMPO_POR_DECISAO.values()}
    for resultado in resultados:
        contagens[_CAMPO_POR_DECISAO[decidir_proxima_acao(resultado)]] += 1
    return MetricasAutomacao(total=len(resultados), **contagens)
