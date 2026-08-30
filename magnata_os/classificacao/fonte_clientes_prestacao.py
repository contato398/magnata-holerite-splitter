"""Fonte CANÔNICA e SUBSTITUÍVEL de clientes ativos de um ciclo da
Prestação (missão "POLÍTICA OPERACIONAL REAL DE CLIENTES/REQUISITOS",
Fase 2).

Protocol pequeno e geral — nunca hardcoda cliente no motor documental
(cláusula pétrea #3). O motor/corredor nunca sabe "quantos clientes
existem"; só consulta esta porta. Identidade é sempre `ReferenciaCanonica
('CLIENTE', id_estavel)` — nunca o nome (cláusula pétrea, Fase 2: "não
transportar nome como identidade primária")."""
from __future__ import annotations

from typing import Protocol, Tuple

from .competencia_esperada_prestacao import ContextoCicloPrestacao
from .contratos import ReferenciaCanonica


class FonteClientesPrestacao(Protocol):
    """Fonte substituível, somente leitura, dos clientes elegíveis para
    um ciclo. Implementações possíveis: fixture em memória (testes),
    Airtable read-only (`airtable_clientes_prestacao.py`), ou qualquer
    cadastro futuro — o corredor nunca precisa saber qual."""

    def listar_ativos(
        self, contexto: ContextoCicloPrestacao,
    ) -> Tuple[ReferenciaCanonica, ...]: ...
