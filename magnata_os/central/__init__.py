"""Contratos centrais do Magnata OS.

Este pacote é infraestrutura de domínio puro: não conhece Airtable,
WhatsApp, e-mail, Flask, Render ou qualquer fornecedor externo.
"""

from .distribuicao import (
    AcaoFallback,
    CanalDistribuicao,
    EstadoDistribuicao,
    OrdemDistribuicao,
    transicionar,
)

__all__ = [
    "AcaoFallback",
    "CanalDistribuicao",
    "EstadoDistribuicao",
    "OrdemDistribuicao",
    "transicionar",
]
