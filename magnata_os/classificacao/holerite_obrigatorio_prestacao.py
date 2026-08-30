"""Obrigatoriedade do Holerite por CARDINALIDADE colaborador (Adendo
de Regra de Negócio — Holerite, missão "CADASTRO CANÔNICO REAL DE
REQUISITOS DA PRESTAÇÃO").

Correção canônica autorizada pelo negócio: "HOLERITE É OBRIGATÓRIO EM
TODA PRESTAÇÃO DE CONTAS" — nunca condicional, nunca NAO_CONFIGURADO.
Mas a MERA presença do tipo 'Holerite' no inventário NÃO basta (ponto 6
do adendo): a obrigação real é

    CLIENTE → colaboradores esperados → 1 Holerite esperado por
    colaborador aplicável

— uma cardinalidade que a contagem plana de `PoliticaRequisitosPrestacao`/
`avaliar_prestacao_readiness` (que só soma "quantos itens deste tipo
existem para o cliente", sem saber QUAL colaborador cada um cobre) não
representa. Por isso este módulo é uma avaliação SEPARADA, ADITIVA
(nunca substitui a leitura de FGTS/Extrato/DCTFWeb, que continuam bem
servidos pela contagem plana) — combinada ao pacote lógico por
`pacote_prestacao.py`.

Nunca expõe CPF/nome: colaborador é sempre `ReferenciaCanonica
('COLABORADOR', id_interno)` — a mesma identidade sanitizada que
`ItemInventarioPrestacao.colaborador` já carrega."""
from __future__ import annotations

import dataclasses
from typing import Tuple

from .contratos import ReferenciaCanonica
from .prestacao_readiness import ItemInventarioPrestacao

TIPO_HOLERITE = 'Holerite'


@dataclasses.dataclass(frozen=True)
class ResultadoObrigatoriedadeHolerite:
    cliente: ReferenciaCanonica
    competencia: ReferenciaCanonica
    colaboradores_esperados: Tuple[ReferenciaCanonica, ...]
    colaboradores_com_holerite: Tuple[ReferenciaCanonica, ...]
    colaboradores_faltantes: Tuple[ReferenciaCanonica, ...]

    @property
    def completo(self) -> bool:
        """`True` só quando TODO colaborador esperado tem Holerite --
        nenhum colaborador esperado é o mesmo que `completo` (uma lista
        vazia de esperados nunca é lida como "obrigação cumprida com
        louvor", é só a ausência de expectativa para avaliar; quem
        monta o pacote decide separadamente se isso é aceitável ou
        NECESSITA REVISÃO -- este módulo só relata o fato)."""
        return len(self.colaboradores_faltantes) == 0


def avaliar_obrigatoriedade_holerite(
    cliente: ReferenciaCanonica,
    competencia: ReferenciaCanonica,
    colaboradores_esperados: Tuple[ReferenciaCanonica, ...],
    inventario: Tuple[ItemInventarioPrestacao, ...],
) -> ResultadoObrigatoriedadeHolerite:
    """Pura, sem I/O. `colaboradores_esperados` e `inventario` já vêm
    prontos de fora (fonte + fonte de inventário, nunca calculados
    aqui) -- nunca inventa colaborador nem vínculo."""
    colaboradores_com_holerite = {
        item.colaborador for item in inventario
        if item.tipo_documental == TIPO_HOLERITE
        and item.cliente == cliente
        and item.competencia == competencia
        and item.colaborador is not None
    }
    presentes = tuple(c for c in colaboradores_esperados if c in colaboradores_com_holerite)
    faltantes = tuple(c for c in colaboradores_esperados if c not in colaboradores_com_holerite)
    return ResultadoObrigatoriedadeHolerite(
        cliente=cliente, competencia=competencia,
        colaboradores_esperados=colaboradores_esperados,
        colaboradores_com_holerite=presentes,
        colaboradores_faltantes=faltantes,
    )
