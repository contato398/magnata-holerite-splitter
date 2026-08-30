"""Fonte COMPOSTA de inventário (missão "INVENTÁRIO DOCUMENTAL REAL DA
PRESTAÇÃO + PREPARAÇÃO DO PRIMEIRO PILOTO COMPLETO SKY").

Agrega N fontes `FonteInventarioPrestacao` já existentes (Extrato/FGTS/
DCTF via `FonteInventarioPrestacaoAirtableShadow`, Holerite via
`FonteInventarioHoleritesAirtableShadow`, ou qualquer outra fonte futura
que implemente o mesmo Protocol) num único inventário por cliente/
competência. NUNCA reimplementa lógica por família (nenhum `if
Holerite... elif Extrato...` aqui) -- cada fonte específica já sabe
produzir o MESMO contrato (`ItemInventarioPrestacao`); esta classe só
une e deduplica (cláusula pétrea #2 da missão: "não criar inventário
específico de Holerite, depois outro de Extrato, depois outro de FGTS
como pipelines separados").

Deduplicação por `documento_id` -- identidade documental determinística,
NUNCA filename (cláusula pétrea #9 do corredor). Se 2 fontes devolverem
o MESMO `documento_id` (não deveria acontecer entre tabelas Airtable
distintas, cujos record ids já são globalmente únicos, mas defendido
mesmo assim), o primeiro item encontrado prevalece -- nunca inventa
merge de campos entre os dois.

Traduz vocabulário Família B -> motor geral quando aplicável, reusando
`TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL` (já existente,
`normalizacao_requisitos_prestacao.py` -- nunca uma segunda tabela de
tradução): sem isso, um item com `tipo_documental='extrato_cliente'`
(vocabulário do adapter Airtable-shadow já existente) nunca bateria com
o requisito canônico `'Extrato da Folha de Pagamento'` do cadastro V2."""
from __future__ import annotations

import dataclasses
from typing import Tuple

from .contratos import ReferenciaCanonica
from .inventario_prestacao import FonteInventarioPrestacao
from .normalizacao_requisitos_prestacao import TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL
from .prestacao_readiness import ItemInventarioPrestacao


class FonteInventarioPrestacaoComposta:
    """Implementa `FonteInventarioPrestacao` agregando outras fontes do
    MESMO Protocol -- nunca sabe o schema/origem de nenhuma delas."""

    def __init__(self, fontes: Tuple[FonteInventarioPrestacao, ...]):
        self._fontes = tuple(fontes)

    def listar(
        self, cliente: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> Tuple[ItemInventarioPrestacao, ...]:
        vistos: dict = {}
        for fonte in self._fontes:
            for item in fonte.listar(cliente, competencia):
                if item.documento_id in vistos:
                    continue
                tipo_traduzido = TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL.get(
                    item.tipo_documental, item.tipo_documental)
                if tipo_traduzido != item.tipo_documental:
                    item = dataclasses.replace(item, tipo_documental=tipo_traduzido)
                vistos[item.documento_id] = item
        return tuple(vistos[chave] for chave in sorted(vistos))
