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
from .snapshot import SnapshotCentral, construir_snapshot_central

__all__ = [
    "CanalDistribuicao",
    "EstadoDistribuicao",
    "OrdemDistribuicao",
    "SnapshotCentral",
    "construir_snapshot_central",
    "encaminhar_para_fallback_manual",
    "transicionar",
]
