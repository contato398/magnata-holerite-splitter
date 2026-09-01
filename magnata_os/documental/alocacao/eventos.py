"""Eventos canônicos de Vínculo/Alocação (missão "CAPTURA AUTOMÁTICA DE
VÍNCULO E ALOCAÇÃO V1"). Puro -- sem I/O, sem driver de banco.

Só 4 primitivas -- nunca um evento por cenário de negócio. "Transferência"
(fecha posto A, abre posto B), "rateio" (abre um posto a mais sem
fechar os outros) e "remoção de 1 posto" (fecha só aquele) são todos
COMPOSIÇÕES de `AlocacaoIniciada`/`AlocacaoEncerrada` -- nunca tipos de
evento à parte (ver `captura.py::aplicar_transferencia`).

**Regra central desta missão:** `data_efetiva` é SEMPRE obrigatória e
validada na construção -- nunca `None`, nunca inferida de "hoje". Um
chamador que não tem uma data efetiva confiável simplesmente NÃO
CONSEGUE construir um evento válido -- a ausência de data vira exceção
imediata na fronteira, nunca um valor assumido silenciosamente."""
from __future__ import annotations

import dataclasses
from datetime import date


def _exigir_texto(valor: str, campo: str) -> None:
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f'{campo} deve ser texto nao vazio')


def _exigir_data(valor: object, campo: str) -> None:
    if not isinstance(valor, date):
        raise ValueError(
            f'{campo} deve ser uma data efetiva real (datetime.date) -- '
            f'nunca None, nunca string, nunca inferida de "hoje"')


@dataclasses.dataclass(frozen=True)
class VinculoIniciado:
    """Admissão -- data_efetiva é a Data de Admissão real, com evidência
    (ex.: extraída de um Holerite real, `origem_evidencia='holerite_data_admissao'`)."""

    colaborador_id: str
    data_efetiva: date
    origem_evidencia: str

    def __post_init__(self) -> None:
        _exigir_texto(self.colaborador_id, 'colaborador_id')
        _exigir_data(self.data_efetiva, 'data_efetiva')
        _exigir_texto(self.origem_evidencia, 'origem_evidencia')


@dataclasses.dataclass(frozen=True)
class VinculoEncerrado:
    """Desligamento -- data_efetiva é a Data de Rescisão/Desligamento
    real (ex.: extraída de um TRCT real)."""

    colaborador_id: str
    data_efetiva: date
    origem_evidencia: str

    def __post_init__(self) -> None:
        _exigir_texto(self.colaborador_id, 'colaborador_id')
        _exigir_data(self.data_efetiva, 'data_efetiva')
        _exigir_texto(self.origem_evidencia, 'origem_evidencia')


@dataclasses.dataclass(frozen=True)
class AlocacaoIniciada:
    """Início de alocação num posto -- exige vínculo já aberto para o
    colaborador (ver `captura.py`). `data_efetiva` precisa da mesma
    evidência real que qualquer outro evento -- nunca inferida."""

    colaborador_id: str
    posto_id: str
    data_efetiva: date
    origem_evidencia: str

    def __post_init__(self) -> None:
        _exigir_texto(self.colaborador_id, 'colaborador_id')
        _exigir_texto(self.posto_id, 'posto_id')
        _exigir_data(self.data_efetiva, 'data_efetiva')
        _exigir_texto(self.origem_evidencia, 'origem_evidencia')


@dataclasses.dataclass(frozen=True)
class AlocacaoEncerrada:
    """Fim de alocação num posto específico -- nunca fecha os demais
    postos do mesmo vínculo (rateio preservado)."""

    colaborador_id: str
    posto_id: str
    data_efetiva: date
    origem_evidencia: str

    def __post_init__(self) -> None:
        _exigir_texto(self.colaborador_id, 'colaborador_id')
        _exigir_texto(self.posto_id, 'posto_id')
        _exigir_data(self.data_efetiva, 'data_efetiva')
        _exigir_texto(self.origem_evidencia, 'origem_evidencia')


class EventoForaDeOrdemError(ValueError):
    """Evento pressupõe um estado anterior que não existe -- ex.:
    encerramento sem vínculo/alocação aberta correspondente. Nunca
    tratado silenciosamente; sempre propagado para quem orquestra a
    captura decidir (retry depois, fila de exceção, etc.)."""


class ConflitoTemporalEventoError(ValueError):
    """Evento diverge de um registro já existente para a mesma
    identidade (ex.: encerrar com uma data diferente da já registrada)
    -- nunca sobrescreve período antigo silenciosamente."""
