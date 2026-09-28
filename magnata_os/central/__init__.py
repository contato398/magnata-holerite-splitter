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
from .localizacao import (
    ConsultaFonte,
    DecisaoLocalizacao,
    FonteNomeada,
    ResultadoLocalizacao,
    StatusConsultaFonte,
    localizar_documento,
)
from .snapshot import SnapshotCentral, construir_snapshot_central

__all__ = [
    "CanalDistribuicao",
    "ConsultaFonte",
    "DecisaoLocalizacao",
    "EstadoDistribuicao",
    "FonteNomeada",
    "OrdemDistribuicao",
    "ResultadoLocalizacao",
    "SnapshotCentral",
    "StatusConsultaFonte",
    "construir_snapshot_central",
    "encaminhar_para_fallback_manual",
    "localizar_documento",
    "transicionar",
]
