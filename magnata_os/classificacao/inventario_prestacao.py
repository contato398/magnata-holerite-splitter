"""Porta neutra de leitura do inventario documental de prestacao."""

from __future__ import annotations

from typing import Protocol

from .contratos import ReferenciaCanonica
from .prestacao_readiness import ItemInventarioPrestacao


class FonteInventarioPrestacao(Protocol):
    """Fonte substituivel e somente leitura para o readiness shadow."""

    def listar(
        self,
        cliente: ReferenciaCanonica,
        competencia: ReferenciaCanonica,
    ) -> tuple[ItemInventarioPrestacao, ...]: ...
