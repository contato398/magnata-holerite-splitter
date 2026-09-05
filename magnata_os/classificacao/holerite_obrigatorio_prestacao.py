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
`ItemInventarioPrestacao.colaborador` já carrega.

COMPATIBILIDADE V2 (PR #128): Este módulo agora delega à capacidade
GENÉRICA de cardinalidade_colaborador_por_tipo.py. `ResultadoObrigatoriedadeHolerite`
mantém sua assinatura para não quebrar consumidores existentes (campo
`colaboradores_com_holerite` é alias para `colaboradores_presentes`)."""
from __future__ import annotations

import dataclasses
from typing import Tuple

from .cardinalidade_colaborador_por_tipo import (
    ResultadoObrigatoriedadeDocumental,
    avaliar_obrigatoriedade_por_tipo_documental,
)
from .contratos import ReferenciaCanonica
from .prestacao_readiness import ItemInventarioPrestacao

TIPO_HOLERITE = 'Holerite'


@dataclasses.dataclass(frozen=True)
class ResultadoObrigatoriedadeHolerite:
    """Wrapper compatível de ResultadoObrigatoriedadeDocumental para Holerite.

    Campo `colaboradores_com_holerite` é alias para `colaboradores_presentes`
    da estrutura genérica — ambos contêm o mesmo dado (colaboradores que têm
    Holerite), apenas nomeado especificamente para o contexto histórico do Holerite."""

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
    """Pura, sem I/O. Delega à capacidade genérica de cardinalidade.

    Compatibilidade 100%: resultado é identicamente o mesmo que a implementação
    anterior — mudança é somente interna (reutiliza `avaliar_obrigatoriedade_por_tipo_documental`).
    Campo `colaboradores_com_holerite` continua existindo, preenchido como antes."""
    resultado_generico = avaliar_obrigatoriedade_por_tipo_documental(
        cliente=cliente,
        competencia=competencia,
        tipo_documental=TIPO_HOLERITE,
        colaboradores_esperados=colaboradores_esperados,
        inventario=inventario,
    )
    return ResultadoObrigatoriedadeHolerite(
        cliente=resultado_generico.cliente,
        competencia=resultado_generico.competencia,
        colaboradores_esperados=resultado_generico.colaboradores_esperados,
        colaboradores_com_holerite=resultado_generico.colaboradores_presentes,
        colaboradores_faltantes=resultado_generico.colaboradores_faltantes,
    )
