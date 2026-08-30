"""Pacote LÓGICO da Prestação de Contas por cliente (missão "CORREDOR
OPERACIONAL DA PRESTAÇÃO DE CONTAS", Fase 10).

NUNCA gera ZIP/PDF/arquivo físico — representação PURA, construída a
partir do `ResultadoPrestacaoReadiness` já existente
(`prestacao_readiness.py`, reaproveitado sem alteração) + o inventário
já consultado — nunca do filename ou de uma pasta. Reutiliza o
vocabulário de estado do readiness (PRONTO/FALTANDO/REVISAR/
DIVERGENTE) via um mapeamento 1:1 — nunca reimplementa a lógica de
decisão, só empresta um rótulo mais operacional para o conceito de
"pacote" (PRONTO/INCOMPLETO/EM_REVISAO/BLOQUEADO), que ainda não
existia como contrato.

O pacote é sempre formado a partir de INVENTÁRIO + POLÍTICA/READINESS —
nunca inventa item, nunca decide sozinho em caso de ambiguidade (herda
a mesma cautela do readiness: REVISAR vira EM_REVISAO, nunca PRONTO)."""
from __future__ import annotations

import dataclasses
import enum
from typing import Optional, Tuple

from .contratos import ReferenciaCanonica, ResultadoResolucaoSemantico
from .holerite_obrigatorio_prestacao import TIPO_HOLERITE, ResultadoObrigatoriedadeHolerite
from .inventario_prestacao import FonteInventarioPrestacao
from .politica_requisitos_prestacao import PoliticaRequisitosPrestacao
from .prestacao_readiness import (
    EntradaPrestacaoReadiness,
    EstadoPrestacaoReadiness,
    ItemInventarioPrestacao,
    ResultadoPrestacaoReadiness,
    avaliar_prestacao_readiness,
)


class EstadoPacotePrestacao(str, enum.Enum):
    PRONTO = 'PRONTO'
    INCOMPLETO = 'INCOMPLETO'
    EM_REVISAO = 'EM_REVISAO'
    BLOQUEADO = 'BLOQUEADO'


# Mapeamento 1:1, nunca uma decisão nova -- DIVERGENTE (competência
# incompatível) é tratado como BLOQUEADO (mais grave que "faltando":
# o que está presente nem corresponde ao ciclo pedido).
_ESTADO_PACOTE_POR_READINESS = {
    EstadoPrestacaoReadiness.PRONTO: EstadoPacotePrestacao.PRONTO,
    EstadoPrestacaoReadiness.FALTANDO: EstadoPacotePrestacao.INCOMPLETO,
    EstadoPrestacaoReadiness.REVISAR: EstadoPacotePrestacao.EM_REVISAO,
    EstadoPrestacaoReadiness.DIVERGENTE: EstadoPacotePrestacao.BLOQUEADO,
}


@dataclasses.dataclass(frozen=True)
class PacotePrestacaoCliente:
    """Representação LÓGICA (nunca física) do que existe/falta para UM
    cliente numa competência. `itens_incluidos` é sempre o inventário
    JÁ FILTRADO por cliente/competência (nunca reavaliado aqui)."""

    cliente: ReferenciaCanonica
    competencia: ReferenciaCanonica
    estado: EstadoPacotePrestacao
    itens_incluidos: Tuple[ItemInventarioPrestacao, ...]
    tipos_obrigatorios: Tuple[str, ...]
    tipos_faltantes: Tuple[str, ...] = ()
    motivos: Tuple[str, ...] = ()
    holerite: Optional[ResultadoObrigatoriedadeHolerite] = None
    """Adendo de Regra de Negócio (Holerite): detalhe da obrigatoriedade
    por cardinalidade colaborador, quando avaliada (ver `combinar_
    pacote_com_holerite`) -- `None` quando a avaliação não foi pedida
    (nunca confundir "não avaliado" com "completo")."""

    def __post_init__(self) -> None:
        if any(item.cliente != self.cliente for item in self.itens_incluidos):
            raise ValueError('itens_incluidos so pode conter itens do MESMO cliente do pacote')
        if any(item.competencia != self.competencia for item in self.itens_incluidos):
            raise ValueError('itens_incluidos so pode conter itens da MESMA competencia do pacote')


def montar_pacote_logico(
    readiness: ResultadoPrestacaoReadiness,
    requisitos: Tuple,
    inventario: Tuple[ItemInventarioPrestacao, ...],
) -> PacotePrestacaoCliente:
    """Traduz um `ResultadoPrestacaoReadiness` (já calculado, nunca
    reavaliado aqui) num `PacotePrestacaoCliente`. `requisitos` e
    `inventario` são os MESMOS já usados para calcular `readiness` --
    este módulo nunca torna a consultar política/fonte de inventário."""
    return PacotePrestacaoCliente(
        cliente=readiness.cliente,
        competencia=readiness.competencia,
        estado=_ESTADO_PACOTE_POR_READINESS[readiness.estado],
        itens_incluidos=inventario,
        tipos_obrigatorios=tuple(sorted(r.tipo_documental for r in requisitos)),
        tipos_faltantes=readiness.tipos_faltantes,
        motivos=readiness.motivos,
    )


def avaliar_e_montar_pacote(
    cliente: ReferenciaCanonica,
    competencia: ReferenciaCanonica,
    resolucao: ResultadoResolucaoSemantico,
    fonte_inventario: FonteInventarioPrestacao,
    politica: PoliticaRequisitosPrestacao,
) -> PacotePrestacaoCliente:
    """Orquestração ponta-a-ponta: política + inventário + resolução →
    readiness (`avaliar_prestacao_readiness`, sem alteração) → pacote
    lógico. Mesma composição de `prestacao_shadow.avaliar_prestacao_
    shadow`, só que devolvendo o pacote em vez do readiness cru --
    NUNCA duplica a lógica daquela função, monta a MESMA entrada uma
    única vez."""
    requisitos = politica.requisitos_para(cliente, competencia)
    inventario = fonte_inventario.listar(cliente, competencia)
    readiness = avaliar_prestacao_readiness(
        EntradaPrestacaoReadiness(
            cliente=cliente, competencia=competencia, requisitos=requisitos,
            inventario=inventario, resolucao=resolucao,
        )
    )
    return montar_pacote_logico(readiness, requisitos, inventario)


def combinar_pacote_com_holerite(
    pacote: PacotePrestacaoCliente,
    resultado_holerite: ResultadoObrigatoriedadeHolerite,
) -> PacotePrestacaoCliente:
    """Adendo de Regra de Negócio (Holerite): combina um pacote JÁ
    MONTADO (via `montar_pacote_logico`/`avaliar_e_montar_pacote`, sem
    nenhuma alteração) com a obrigatoriedade do Holerite por
    cardinalidade colaborador. Nunca upgrada um pacote já problemático
    (BLOQUEADO/EM_REVISAO continuam como estavam); só rebaixa PRONTO
    para INCOMPLETO quando falta Holerite de algum colaborador esperado
    -- nunca o inverso (Holerite completo nunca promove um pacote já
    incompleto/bloqueado por outro motivo)."""
    if resultado_holerite.completo:
        return dataclasses.replace(pacote, holerite=resultado_holerite)
    novo_estado = pacote.estado
    if novo_estado == EstadoPacotePrestacao.PRONTO:
        novo_estado = EstadoPacotePrestacao.INCOMPLETO
    tipos_faltantes = pacote.tipos_faltantes
    if TIPO_HOLERITE not in tipos_faltantes:
        tipos_faltantes = tuple(sorted(tipos_faltantes + (TIPO_HOLERITE,)))
    return dataclasses.replace(
        pacote, estado=novo_estado, tipos_faltantes=tipos_faltantes, holerite=resultado_holerite,
    )
