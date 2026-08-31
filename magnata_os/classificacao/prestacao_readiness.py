"""Avaliacao pura de readiness para Prestacao de Contas em shadow mode.

Recebe apenas referencias canonicas e inventario previamente observado. Nao
consulta fontes, nao monta pacote e nao produz qualquer efeito externo.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Optional, Tuple

from .contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResultadoResolucaoSemantico,
)


class EstadoPrestacaoReadiness(str, Enum):
    PRONTO = "PRONTO"
    FALTANDO = "FALTANDO"
    DIVERGENTE = "DIVERGENTE"
    REVISAR = "REVISAR"


@dataclasses.dataclass(frozen=True)
class RequisitoDocumentalPrestacao:
    tipo_documental: str
    quantidade_minima: int = 1

    def __post_init__(self) -> None:
        if not self.tipo_documental.strip():
            raise ValueError("tipo_documental deve ser texto nao vazio")
        if isinstance(self.quantidade_minima, bool) or self.quantidade_minima < 1:
            raise ValueError("quantidade_minima deve ser inteira positiva")


@dataclasses.dataclass(frozen=True)
class ItemInventarioPrestacao:
    documento_id: str
    tipo_documental: str
    cliente: ReferenciaCanonica
    competencia: ReferenciaCanonica
    colaborador: Optional[ReferenciaCanonica] = None
    """Campo aditivo (Adendo de Regra de Negócio -- Holerite, missão
    "CADASTRO CANÔNICO REAL DE REQUISITOS DA PRESTAÇÃO"): identidade
    SANITIZADA (`ReferenciaCanonica('COLABORADOR', id_interno)`, nunca
    CPF/nome) do colaborador dono do documento, quando aplicável
    (Holerite e outros documentos de granularidade colaborador).
    `None` para documentos sem colaborador (Extrato, FGTS, DCTFWeb,
    Certidão etc.) -- default preserva 100% o comportamento anterior
    para quem já constrói este DTO sem este campo."""

    def __post_init__(self) -> None:
        if not self.documento_id.strip():
            raise ValueError("documento_id deve ser texto nao vazio")
        if not self.tipo_documental.strip():
            raise ValueError("tipo_documental deve ser texto nao vazio")
        if self.colaborador is not None and self.colaborador.tipo_entidade != "COLABORADOR":
            raise ValueError("colaborador deve ser referencia canonica de COLABORADOR")

    @property
    def identidade_logica(self) -> tuple:
        """Identidade LÓGICA CANÔNICA de um item de inventário (Adendo
        substitutivo ao PR #105, §15: "a regra deve acompanhar a
        IDENTIDADE LÓGICA CANÔNICA existente, não uma tupla
        improvisada"). Um `documento_id` físico pode gerar N itens
        lógicos legítimos e distintos: broadcast (mesmo documento, 1
        item por cliente aplicável) e vínculo múltiplo/fatiamento por
        colaborador (mesmo documento, 1 item por colaborador/cliente
        derivado -- ex.: relatório de benefícios fatiado). `cliente`
        sozinho distingue broadcast; `colaborador` distingue itens
        fatiados por colaborador dentro do MESMO cliente (nunca
        colapsados). Reaproveitada por toda fonte de inventário que
        precise decidir "isto já existe ou é um item novo" --
        `FonteInventarioPrestacaoComposta` e `InventarioPrestacaoEm
        Memoria`, nunca uma tupla ad-hoc duplicada em cada uma."""
        return (self.documento_id, self.cliente, self.colaborador)


@dataclasses.dataclass(frozen=True)
class EntradaPrestacaoReadiness:
    cliente: ReferenciaCanonica
    competencia: ReferenciaCanonica
    requisitos: Tuple[RequisitoDocumentalPrestacao, ...]
    inventario: Tuple[ItemInventarioPrestacao, ...]
    resolucao: ResultadoResolucaoSemantico

    def __post_init__(self) -> None:
        tipos = [item.tipo_documental for item in self.requisitos]
        if len(tipos) != len(set(tipos)):
            raise ValueError("requisitos nao podem repetir tipo_documental")
        documentos = [item.documento_id for item in self.inventario]
        if len(documentos) != len(set(documentos)):
            raise ValueError("inventario nao pode repetir documento_id")


@dataclasses.dataclass(frozen=True)
class ResultadoPrestacaoReadiness:
    cliente: ReferenciaCanonica
    competencia: ReferenciaCanonica
    estado: EstadoPrestacaoReadiness
    tipos_faltantes: Tuple[str, ...] = ()
    contagens_observadas: Tuple[Tuple[str, int], ...] = ()
    motivos: Tuple[str, ...] = ()


def _resolucao_da_dimensao(
    resultado: ResultadoResolucaoSemantico,
    dimensao: DimensaoResolucao,
):
    return next(
        (item for item in resultado.resolucoes if item.dimensao == dimensao),
        None,
    )


def avaliar_prestacao_readiness(
    entrada: EntradaPrestacaoReadiness,
) -> ResultadoPrestacaoReadiness:
    """Classifica um cliente/competencia sem I/O e sem mutacao."""

    cliente_resolvido = _resolucao_da_dimensao(
        entrada.resolucao, DimensaoResolucao.CLIENTE
    )
    competencia_resolvida = _resolucao_da_dimensao(
        entrada.resolucao, DimensaoResolucao.COMPETENCIA
    )
    dimensoes = (cliente_resolvido, competencia_resolvida)
    estados_revisao = {
        EstadoResolucaoDimensao.AMBIGUA,
        EstadoResolucaoDimensao.CONFLITO,
        EstadoResolucaoDimensao.NAO_AVALIADA,
        EstadoResolucaoDimensao.NAO_ENCONTRADA,
        EstadoResolucaoDimensao.INVALIDA,
        EstadoResolucaoDimensao.ERRO_TECNICO,
        EstadoResolucaoDimensao.NAO_APLICAVEL,
    }

    motivos_revisao = []
    if entrada.resolucao.necessita_revisao_humana:
        motivos_revisao.append("resolucao_requer_revisao_humana")
    if any(item is None for item in dimensoes):
        motivos_revisao.append("dimensao_obrigatoria_ausente")
    elif any(item.estado in estados_revisao for item in dimensoes):
        motivos_revisao.append("resolucao_ambigua_conflitante_ou_inconclusiva")
    elif any(len(item.valores_confirmados) != 1 for item in dimensoes):
        motivos_revisao.append("resolucao_sem_referencia_unica")
    elif cliente_resolvido.valores_confirmados[0] != entrada.cliente:
        motivos_revisao.append("cliente_resolvido_incompativel")

    if any(item.cliente != entrada.cliente for item in entrada.inventario):
        motivos_revisao.append("inventario_de_outro_cliente")

    contagens: dict[str, int] = {}
    for item in entrada.inventario:
        contagens[item.tipo_documental] = contagens.get(item.tipo_documental, 0) + 1
    contagens_ordenadas = tuple(sorted(contagens.items()))

    if motivos_revisao:
        return ResultadoPrestacaoReadiness(
            cliente=entrada.cliente,
            competencia=entrada.competencia,
            estado=EstadoPrestacaoReadiness.REVISAR,
            contagens_observadas=contagens_ordenadas,
            motivos=tuple(sorted(set(motivos_revisao))),
        )

    competencia_confirmada = competencia_resolvida.valores_confirmados[0]
    if competencia_confirmada != entrada.competencia or any(
        item.competencia != entrada.competencia for item in entrada.inventario
    ):
        return ResultadoPrestacaoReadiness(
            cliente=entrada.cliente,
            competencia=entrada.competencia,
            estado=EstadoPrestacaoReadiness.DIVERGENTE,
            contagens_observadas=contagens_ordenadas,
            motivos=("competencia_incompativel",),
        )

    faltantes = tuple(
        sorted(
            requisito.tipo_documental
            for requisito in entrada.requisitos
            if contagens.get(requisito.tipo_documental, 0)
            < requisito.quantidade_minima
        )
    )
    if faltantes:
        return ResultadoPrestacaoReadiness(
            cliente=entrada.cliente,
            competencia=entrada.competencia,
            estado=EstadoPrestacaoReadiness.FALTANDO,
            tipos_faltantes=faltantes,
            contagens_observadas=contagens_ordenadas,
            motivos=("requisito_documental_ausente",),
        )

    return ResultadoPrestacaoReadiness(
        cliente=entrada.cliente,
        competencia=entrada.competencia,
        estado=EstadoPrestacaoReadiness.PRONTO,
        contagens_observadas=contagens_ordenadas,
    )
