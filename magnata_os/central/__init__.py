"""Contratos centrais do Magnata OS.

Este pacote é infraestrutura de domínio puro: não conhece Airtable,
WhatsApp, e-mail, Flask, Render ou qualquer fornecedor externo.
"""

from .distribuicao import (
    CanalDistribuicao,
    EstadoDistribuicao,
    OrdemDistribuicao,
    encaminhar_para_fallback_manual,
    transicionar,
)

__all__ = [
    "CanalDistribuicao",
    "EstadoDistribuicao",
    "OrdemDistribuicao",
    "encaminhar_para_fallback_manual",
    "transicionar",
]
