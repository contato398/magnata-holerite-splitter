"""Composicao explicita do backend do RepositorioExecucoes.

Nao existe fallback silencioso: solicitar Postgres sem fornecer uma conexao
ja autenticada falha antes de criar o Orquestrador. Secrets e conexao vivem
fora do dominio e continuam sob gate de infraestrutura.
"""
from __future__ import annotations

import dataclasses
from enum import Enum
from pathlib import Path
from typing import Optional

from .repositorio_execucoes import (
    RepositorioExecucoes,
    RepositorioExecucoesEmMemoria,
    RepositorioExecucoesSQLite,
)
from .repositorio_execucoes_postgres import RepositorioExecucoesPostgres


class BackendExecucoes(str, Enum):
    MEMORIA = 'MEMORIA'
    SQLITE = 'SQLITE'
    POSTGRES = 'POSTGRES'


class ConfiguracaoRepositorioInvalida(ValueError):
    """Configuracao incompleta ou ambigua; nunca aciona fallback."""


@dataclasses.dataclass(frozen=True)
class ConfiguracaoRepositorioExecucoes:
    backend: BackendExecucoes
    caminho_sqlite: Optional[Path] = None


def construir_repositorio_execucoes(
    configuracao: ConfiguracaoRepositorioExecucoes,
    *,
    conexao_postgres=None,
) -> RepositorioExecucoes:
    if configuracao.backend == BackendExecucoes.MEMORIA:
        if configuracao.caminho_sqlite is not None or conexao_postgres is not None:
            raise ConfiguracaoRepositorioInvalida(
                'MEMORIA nao aceita caminho SQLite nem conexao Postgres'
            )
        return RepositorioExecucoesEmMemoria()

    if configuracao.backend == BackendExecucoes.SQLITE:
        if configuracao.caminho_sqlite is None:
            raise ConfiguracaoRepositorioInvalida(
                'SQLITE exige caminho_sqlite explicito'
            )
        if conexao_postgres is not None:
            raise ConfiguracaoRepositorioInvalida(
                'SQLITE nao aceita conexao Postgres'
            )
        return RepositorioExecucoesSQLite(configuracao.caminho_sqlite)

    if configuracao.backend == BackendExecucoes.POSTGRES:
        if configuracao.caminho_sqlite is not None:
            raise ConfiguracaoRepositorioInvalida(
                'POSTGRES nao aceita caminho SQLite'
            )
        if conexao_postgres is None:
            raise ConfiguracaoRepositorioInvalida(
                'POSTGRES exige conexao autenticada injetada explicitamente'
            )
        return RepositorioExecucoesPostgres(conexao_postgres)

    raise ConfiguracaoRepositorioInvalida(
        f'backend de execucoes desconhecido: {configuracao.backend!r}'
    )
