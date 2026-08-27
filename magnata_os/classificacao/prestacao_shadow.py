"""Coordenacao sem efeitos do readiness shadow da Prestacao de Contas."""

from __future__ import annotations

from .contratos import ReferenciaCanonica, ResultadoResolucaoSemantico
from .inventario_prestacao import FonteInventarioPrestacao
from .politica_requisitos_prestacao import PoliticaRequisitosPrestacao
from .prestacao_readiness import (
    EntradaPrestacaoReadiness,
    ResultadoPrestacaoReadiness,
    avaliar_prestacao_readiness,
)


def avaliar_prestacao_shadow(
    cliente: ReferenciaCanonica,
    competencia: ReferenciaCanonica,
    resolucao: ResultadoResolucaoSemantico,
    fonte_inventario: FonteInventarioPrestacao,
    politica: PoliticaRequisitosPrestacao,
) -> ResultadoPrestacaoReadiness:
    """Compoe politica, inventario e readiness sem mutacao ou efeito externo."""

    requisitos = politica.requisitos_para(cliente, competencia)
    inventario = fonte_inventario.listar(cliente, competencia)
    return avaliar_prestacao_readiness(
        EntradaPrestacaoReadiness(
            cliente=cliente,
            competencia=competencia,
            requisitos=requisitos,
            inventario=inventario,
            resolucao=resolucao,
        )
    )
