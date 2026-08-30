"""Fonte CANÔNICA e SUBSTITUÍVEL de colaboradores esperados por cliente
(Adendo de Regra de Negócio — Holerite, missão "CADASTRO CANÔNICO REAL
DE REQUISITOS DA PRESTAÇÃO").

Protocol pequeno e geral, mesma família de `FonteClientesPrestacao`/
`FonteRequisitosPrestacao`/`FonteInventarioPrestacao`/`FonteVinculosPrestacao`
— nunca hardcoda colaborador no motor documental. Resolve a direção
INVERSA de `FonteVinculosPrestacao` (que resolve COLABORADOR→CLIENTE);
aqui a pergunta é "quais colaboradores este cliente espera nesta
competência" — informação que nenhuma fonte existente hoje expõe (ver
ADR desta missão), por isso um Protocol novo, na mesma família."""
from __future__ import annotations

from typing import Protocol, Tuple

from .competencia_esperada_prestacao import ContextoCicloPrestacao
from .contratos import ReferenciaCanonica


class FonteColaboradoresEsperadosPrestacao(Protocol):
    """Fonte substituível, somente leitura, dos colaboradores que um
    cliente espera ter documentação (Holerite) nesta competência.
    Identidade sempre `ReferenciaCanonica('COLABORADOR', id_interno)`
    — nunca CPF/nome (mesma disciplina de todas as fontes desta
    família)."""

    def colaboradores_esperados_para(
        self, cliente: ReferenciaCanonica, contexto: ContextoCicloPrestacao,
    ) -> Tuple[ReferenciaCanonica, ...]: ...
