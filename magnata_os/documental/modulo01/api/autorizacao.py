"""
Camada de autorizacao abstrata da API de esteira (Modulo 01, Fase 4).

SEM AUTENTICACAO REAL NESTA FASE: `Sujeito` e um portador de perfil
declarado pelo chamador, nao o resultado de validar uma sessao, token
ou senha -- isso e explicitamente fora do escopo (ver "Nao implementar
ainda" em MAGNATA_OS_DOCUMENTAL_MODULO01_FASE4.md). Quando uma fase
futura implementar autenticacao real, o unico ponto de integracao e
onde `Sujeito` e construido (fora deste modulo, no adapter web) -- toda
a logica de "quem pode consultar o que" already vive aqui e nao muda.

Cada handler DECLARA explicitamente qual conjunto de perfis exige
(constantes PERMISSAO_* em handlers.py) e chama `exigir_perfil()` como
a PRIMEIRA coisa que faz -- nunca None, nunca implicito.
"""
from __future__ import annotations

import dataclasses
from enum import Enum
from typing import FrozenSet

from .erros import PermissaoNegada


class Perfil(str, Enum):
    """Perfis operacionais abstratos desta fase. Nenhum perfil novo
    entra aqui sem decisao explicita."""

    OPERACIONAL = 'OPERACIONAL'
    GESTOR = 'GESTOR'
    AUDITOR = 'AUDITOR'


@dataclasses.dataclass(frozen=True)
class Sujeito:
    """Quem esta fazendo a chamada -- so o perfil, sem identidade real
    nesta fase (nenhum nome de usuario, e-mail ou token)."""

    perfil: Perfil


def exigir_perfil(sujeito: Sujeito, perfis_permitidos: FrozenSet[Perfil]) -> None:
    """Levanta PermissaoNegada se `sujeito.perfil` nao estiver em
    `perfis_permitidos`. Nunca aplica excecao a regra em silencio --
    toda consulta que chama isso declara explicitamente seu proprio
    conjunto de perfis permitidos (ver handlers.py)."""
    if sujeito.perfil not in perfis_permitidos:
        perfis_str = ', '.join(sorted(p.value for p in perfis_permitidos))
        raise PermissaoNegada(
            f'Perfil {sujeito.perfil.value} nao tem permissao para esta consulta '
            f'(permitido: {perfis_str}).'
        )
