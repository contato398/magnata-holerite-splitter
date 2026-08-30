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
"""Base HISTÓRICA (Família B / corredor Airtable-shadow já em uso --
`inventario_prestacao_resultados.py`, `airtable_inventario_prestacao.py`,
`scripts/prestacao_readiness_shadow_real.py`). 'extrato_cliente' é o
valor de `TipoDocumental.EXTRATO_CLIENTE` (importacao_lote/contratos.py),
DIFERENTE do valor produzido pelo motor geral novo ('Extrato da Folha
de Pagamento', `classificador_documental.py`) -- os dois vocabulários
NÃO foram unificados (decisão registrada, missão "CORREDOR OPERACIONAL
DA PRESTAÇÃO DE CONTAS": mudar esta constante quebraria os testes
estáveis do corredor Família B já em produção-shadow). Nunca editar
esta tupla para o corredor novo -- usar `requisitos_base` (abaixo) para
compor uma política com o vocabulário do motor geral."""


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
    requisitos_base: tuple[RequisitoDocumentalPrestacao, ...] = REQUISITOS_BASE_PRESTACAO
    """Base configurável (Fase "CORREDOR OPERACIONAL DA PRESTAÇÃO DE
    CONTAS") -- por padrão, EXATAMENTE `REQUISITOS_BASE_PRESTACAO`
    (comportamento 100% preservado para quem já usa esta classe sem
    passar este campo). Um chamador que compõe inventário a partir do
    motor geral novo (`resolver_tipo_documental`/`compor_resolucao_
    semantica`) passa sua PRÓPRIA base, com o vocabulário de tipo do
    motor novo -- nunca editar `REQUISITOS_BASE_PRESTACAO` para isso."""

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
            for requisito in self.requisitos_base
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
        return self.requisitos_base + tuple(
            sorted(
                adicionais,
                key=lambda item: (
                    item.tipo_documental,
                    item.quantidade_minima,
                ),
            )
        )
