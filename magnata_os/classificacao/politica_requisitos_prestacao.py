"""Politica pura e versionada de requisitos da Prestacao de Contas."""

from __future__ import annotations

import dataclasses

from .contratos import ReferenciaCanonica
from .prestacao_readiness import RequisitoDocumentalPrestacao


REQUISITOS_BASE_PRESTACAO = (
    RequisitoDocumentalPrestacao("DCTFWeb - Declaração"),
    RequisitoDocumentalPrestacao("DCTFWeb - Recibo de Entrega"),
    RequisitoDocumentalPrestacao("Guia DCTFWeb/DARF"),
    RequisitoDocumentalPrestacao("FGTS"),
    RequisitoDocumentalPrestacao("extrato_cliente"),
)


@dataclasses.dataclass(frozen=True)
class OverrideRequisitosPrestacao:
    cliente: ReferenciaCanonica
    competencia: ReferenciaCanonica
    requisitos_adicionais: tuple[RequisitoDocumentalPrestacao, ...]

    def __post_init__(self) -> None:
        if self.cliente.tipo_entidade != "CLIENTE":
            raise ValueError("cliente deve ser referencia canonica de CLIENTE")
        if self.competencia.tipo_entidade != "COMPETENCIA":
            raise ValueError(
                "competencia deve ser referencia canonica de COMPETENCIA"
            )
        tipos = [item.tipo_documental for item in self.requisitos_adicionais]
        if len(tipos) != len(set(tipos)):
            raise ValueError("override nao pode repetir tipo_documental")


@dataclasses.dataclass(frozen=True)
class PoliticaRequisitosPrestacao:
    version: str
    overrides: tuple[OverrideRequisitosPrestacao, ...] = ()

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("version deve ser texto nao vazio")
        chaves = [
            (item.cliente, item.competencia)
            for item in self.overrides
        ]
        if len(chaves) != len(set(chaves)):
            raise ValueError("politica nao pode repetir override")
        tipos_base = {
            requisito.tipo_documental
            for requisito in REQUISITOS_BASE_PRESTACAO
        }
        if any(
            requisito.tipo_documental in tipos_base
            for override in self.overrides
            for requisito in override.requisitos_adicionais
        ):
            raise ValueError("override nao pode repetir requisito base")

    def requisitos_para(
        self,
        cliente: ReferenciaCanonica,
        competencia: ReferenciaCanonica,
    ) -> tuple[RequisitoDocumentalPrestacao, ...]:
        adicionais = next(
            (
                item.requisitos_adicionais
                for item in self.overrides
                if item.cliente == cliente and item.competencia == competencia
            ),
            (),
        )
        return REQUISITOS_BASE_PRESTACAO + tuple(
            sorted(
                adicionais,
                key=lambda item: (
                    item.tipo_documental,
                    item.quantidade_minima,
                ),
            )
        )
