"""Avaliação GENÉRICA de obrigatoriedade documental por colaborador esperado.

Reutiliza o padrão já implementado em `holerite_obrigatorio_prestacao.py`:
compara colaboradores esperados vs. presentes no inventário para qualquer
tipo_documental (Holerite, Folha de Ponto, Extrato, etc.).

Função PURA, sem I/O: recebe inventário já calculado, nunca consulta fontes
ou adapters. Nunca inventa colaborador ou vínculo — colaborador vem sempre
de `ItemInventarioPrestacao.colaborador`, já sanitizado como `ReferenciaCanonica`.

Cardinalidade é POR TIPO — a mesma função serve documentos de granularidade
colaborador (Holerite, Folha de Ponto) e documentos globais (Extrato, FGTS)
conforme a configuração do motor de requisitos declara obrigatoriedade.
"""
from __future__ import annotations

import dataclasses
from typing import Tuple

from .contratos import ReferenciaCanonica
from .prestacao_readiness import ItemInventarioPrestacao


@dataclasses.dataclass(frozen=True)
class ResultadoObrigatoriedadeDocumental:
    """Resultado PURO da comparação: colaboradores esperados vs. presentes
    no inventário para um cliente/competência/tipo_documental específico.

    Nunca expõe CPF/nome: colaborador é sempre `ReferenciaCanonica
    ('COLABORADOR', id_interno)` — a mesma identidade sanitizada que
    `ItemInventarioPrestacao.colaborador` já carrega."""

    cliente: ReferenciaCanonica
    competencia: ReferenciaCanonica
    tipo_documental: str
    colaboradores_esperados: Tuple[ReferenciaCanonica, ...]
    colaboradores_presentes: Tuple[ReferenciaCanonica, ...]
    colaboradores_faltantes: Tuple[ReferenciaCanonica, ...]

    @property
    def completo(self) -> bool:
        """`True` só quando TODO colaborador esperado tem documento do tipo.

        Nenhum colaborador esperado é interpretado como ausência de expectativa
        para avaliar (não como "obrigação cumprida com louvor") — quem monta o
        pacote decide separadamente se isso é aceitável ou necessita revisão.
        Este módulo só relata o fato."""
        return len(self.colaboradores_faltantes) == 0


def avaliar_obrigatoriedade_por_tipo_documental(
    cliente: ReferenciaCanonica,
    competencia: ReferenciaCanonica,
    tipo_documental: str,
    colaboradores_esperados: Tuple[ReferenciaCanonica, ...],
    inventario: Tuple[ItemInventarioPrestacao, ...],
) -> ResultadoObrigatoriedadeDocumental:
    """Pura, sem I/O. Compara colaboradores esperados vs. presentes no inventário
    para um tipo_documental específico.

    Args:
        cliente: cliente canônico (já resolvido).
        competencia: competência canônica (já resolvida).
        tipo_documental: tipo procurado (ex.: 'Holerite', 'Folha de Ponto').
        colaboradores_esperados: colaboradores que deveriam ter documento.
        inventario: itens já inventariados (nunca calcula/filtra aqui).

    Returns:
        ResultadoObrigatoriedadeDocumental com presentes/faltantes.

    Invariantes:
        - Nunca inventa colaborador;
        - Colaborador vem sempre de item.colaborador (ReferenciaCanonica);
        - Nunca duplica se 2 documentos cobrem o mesmo colaborador (filtra
          para conjunto único);
        - Comparação é EXATA: cliente, competência, tipo, colaborador.
    """
    colaboradores_com_documento = {
        item.colaborador
        for item in inventario
        if item.tipo_documental == tipo_documental
        and item.cliente == cliente
        and item.competencia == competencia
        and item.colaborador is not None  # Nunca None em cardinalidade
    }
    presentes = tuple(
        c for c in colaboradores_esperados if c in colaboradores_com_documento
    )
    faltantes = tuple(
        c for c in colaboradores_esperados if c not in colaboradores_com_documento
    )
    return ResultadoObrigatoriedadeDocumental(
        cliente=cliente,
        competencia=competencia,
        tipo_documental=tipo_documental,
        colaboradores_esperados=colaboradores_esperados,
        colaboradores_presentes=presentes,
        colaboradores_faltantes=faltantes,
    )
