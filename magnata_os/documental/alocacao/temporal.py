"""Aritmética temporal PURA para Alocação (missão "IMPLEMENTAÇÃO
ESTRUTURAL DA ENTIDADE alocacao COM VIGÊNCIA HISTÓRICA").

Nenhum I/O, nenhum import de driver de banco -- reaproveitado tanto
pelo adapter Postgres (validação defensiva antes de confiar na
constraint `EXCLUDE` do banco) quanto pelo adapter SQLite (que não
suporta `EXCLUDE USING gist`, então precisa impor a mesma invariante em
Python -- ver adapters/sqlite_alocacao.py). Fonte única da regra, nunca
duas implementações divergentes da mesma aritmética."""
from __future__ import annotations

import calendar
import dataclasses
from datetime import date
from typing import Optional, Tuple


def intervalo_do_mes(ano: int, mes: int) -> Tuple[date, date]:
    """Primeiro e último dia do mês -- mesma janela usada para decidir
    "vigente durante a competência" (nunca um único dia-âncora, que
    esconderia uma transferência no meio do mês -- §2 da missão:
    "mudança no meio da competência deve permanecer representável")."""
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, 1), date(ano, mes, ultimo_dia)


def intervalos_se_sobrepoem(
    inicio_a: date, fim_a: Optional[date], inicio_b: date, fim_b: Optional[date],
) -> bool:
    """`fim=None` significa "em aberto" (vigente até hoje/infinito) --
    mesma semântica de `vigente_ate IS NULL` no schema. Sobreposição
    inclusiva nos dois extremos (`'[]'` no `daterange` do Postgres,
    mesmo comportamento reproduzido aqui)."""
    fim_a_efetivo = fim_a if fim_a is not None else date.max
    fim_b_efetivo = fim_b if fim_b is not None else date.max
    return inicio_a <= fim_b_efetivo and fim_a_efetivo >= inicio_b


@dataclasses.dataclass(frozen=True)
class RegistroVinculo:
    """Forma pura de 1 linha de `vinculo_trabalhista` -- nunca exposta
    como dict cru fora dos adapters."""

    id: str
    colaborador_id: str
    data_admissao: date
    data_desligamento: Optional[date] = None


@dataclasses.dataclass(frozen=True)
class RegistroAlocacao:
    """Forma pura de 1 linha de `alocacao`."""

    id: str
    vinculo_trabalhista_id: str
    posto_id: str
    vigente_de: date
    vigente_ate: Optional[date] = None


class SobreposicaoVinculoError(ValueError):
    """Levantado pelo adapter SQLite (aplicação) quando um novo vínculo
    sobrepõe outro já registrado do MESMO colaborador -- mesma
    invariante que a constraint `EXCLUDE` do Postgres impõe a nível de
    banco; aqui precisa ser imposta em Python porque SQLite não suporta
    `EXCLUDE USING gist`."""


class SobreposicaoAlocacaoError(ValueError):
    """Levantado pelo adapter SQLite quando uma nova alocação sobrepõe
    outra já registrada do MESMO vínculo NO MESMO posto -- rateio entre
    postos DIFERENTES nunca levanta este erro (ver nota de reconciliação
    na migration 0001)."""
