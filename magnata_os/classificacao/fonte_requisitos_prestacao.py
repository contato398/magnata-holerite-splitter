"""Fonte CANÔNICA e SUBSTITUÍVEL de requisitos adicionais por cliente
(missão "POLÍTICA OPERACIONAL REAL DE CLIENTES/REQUISITOS", Fase 3).

Princípio central (cláusula pétrea #5): "política de cliente é dado/
configuração validada, não lógica espalhada". Esta fonte devolve DADOS
BRUTOS (`RegistroRequisitoExterno`, forma neutra — nunca um dict
Airtable cru) — quem INTERPRETA continua sendo `PoliticaRequisitosPrestacao`
(reaproveitada sem alteração de contrato, só do campo aditivo
`requisitos_base` já criado no corredor operacional). Os dados brutos
passam por `normalizacao_requisitos_prestacao.py` ANTES de virarem
`OverrideRequisitosPrestacao` — nunca direto da fonte para a política."""
from __future__ import annotations

from typing import Protocol, Tuple

from .competencia_esperada_prestacao import ContextoCicloPrestacao
from .contratos import ReferenciaCanonica
from .normalizacao_requisitos_prestacao import RegistroRequisitoExterno


class FonteRequisitosPrestacao(Protocol):
    """Fonte substituível, somente leitura, dos requisitos ADICIONAIS
    configurados para um cliente (além da base universal). Devolve
    registros BRUTOS, nunca já convertidos em `RequisitoDocumentalPrestacao`
    — a validação/normalização é responsabilidade de quem consome (ver
    `normalizacao_requisitos_prestacao.normalizar_requisitos`), nunca
    desta fonte."""

    def registros_para(
        self, cliente: ReferenciaCanonica, contexto: ContextoCicloPrestacao,
    ) -> Tuple[RegistroRequisitoExterno, ...]: ...
