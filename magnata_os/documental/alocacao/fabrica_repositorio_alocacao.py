"""Composição explícita do backend do repositório de Alocação (missão
"ENTRADA OPERACIONAL + POSTGRES PRÓPRIO V1", FASE 5).

Mesma disciplina de `magnata_os.orquestrador.fabrica_repositorio_execucoes`:
nenhum fallback silencioso entre backends. **Airtable nunca é um
backend aceito por esta fábrica** -- não por convenção documentada, mas
estruturalmente: `BackendAlocacao` só tem 2 valores, nenhum deles
Airtable. A regra pétrea desta missão ("Airtable nunca pode substituir
o banco histórico em caso de falha do Postgres") é garantida pelo
próprio tipo, não por um comentário que alguém poderia ignorar depois.

Reaproveita `magnata_os.documental.modulo01.adapters.conexao`
(`abrir_conexao`/`ler_database_url`) para abrir a conexão Postgres --
nunca reimplementado aqui. **Decisão registrada:** isto cria uma
dependência de import entre os módulos `alocacao` e `modulo01`, uma
exceção deliberada à regra geral "módulos desacoplados, um módulo nunca
importa o interno de outro" (CLAUDE.md raiz §3). Motivo: `conexao.py`
não tem NENHUMA lógica específica de Módulo 01 (é glue DB-API 2.0 puro,
leitura de `DATABASE_URL`, sanitização de credencial em erro) --
duplicar essa lógica sensível a segredo em 2 lugares seria um risco de
segurança maior do que o acoplamento entre módulos que a missão FASE 5
pede explicitamente para evitar ("reutilizar adapters existentes...
não espalhar `DATABASE_URL` pelo domínio"). Se um dia isso incomodar, a
correção é promover `conexao.py` para um local verdadeiramente
compartilhado -- decisão arquitetural própria, fora do escopo desta
missão.

`DATABASE_URL` já está declarada em `render.yaml` (banco `magnata-os-db`,
Postgres gerenciado no Render, ainda NÃO provisionado) para os serviços
`web`/`worker` -- mesma variável, mesmo banco, nenhuma nova. Esta
fábrica não lê `DATABASE_URL` sozinha: só repassa para `conexao.py`
quando o backend POSTGRES é explicitamente escolhido pelo chamador."""
from __future__ import annotations

import dataclasses
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from magnata_os.documental.modulo01.adapters.conexao import abrir_conexao

from .adapters.postgres_alocacao import RepositorioAlocacaoPostgres
from .adapters.sqlite_alocacao import RepositorioAlocacaoSQLite


class BackendAlocacao(str, Enum):
    SQLITE = 'SQLITE'
    POSTGRES = 'POSTGRES'


class ConfiguracaoRepositorioAlocacaoInvalida(ValueError):
    """Configuração incompleta ou ambígua -- nunca aciona fallback."""


@dataclasses.dataclass(frozen=True)
class ConfiguracaoRepositorioAlocacao:
    backend: BackendAlocacao
    caminho_sqlite: Optional[Path] = None


def construir_repositorio_alocacao(
    configuracao: ConfiguracaoRepositorioAlocacao,
    *,
    database_url: Optional[str] = None,
    conectar: Optional[Callable[[str], object]] = None,
    ambiente: Optional[dict] = None,
):
    """`database_url`/`conectar`/`ambiente`: repassados sem alteração
    para `conexao.abrir_conexao` -- mesma injeção, mesmos testes nunca
    dependentes de `psycopg` real nem de uma `DATABASE_URL` real (ver
    docstring de `conexao.abrir_conexao`)."""
    if configuracao.backend == BackendAlocacao.SQLITE:
        if configuracao.caminho_sqlite is None:
            raise ConfiguracaoRepositorioAlocacaoInvalida(
                'SQLITE exige caminho_sqlite explicito')
        if database_url is not None or conectar is not None:
            raise ConfiguracaoRepositorioAlocacaoInvalida(
                'SQLITE nao aceita database_url/conectar')
        return RepositorioAlocacaoSQLite(configuracao.caminho_sqlite)

    if configuracao.backend == BackendAlocacao.POSTGRES:
        if configuracao.caminho_sqlite is not None:
            raise ConfiguracaoRepositorioAlocacaoInvalida(
                'POSTGRES nao aceita caminho_sqlite')
        conexao = abrir_conexao(database_url=database_url, conectar=conectar, ambiente=ambiente)
        return RepositorioAlocacaoPostgres(conexao)

    raise ConfiguracaoRepositorioAlocacaoInvalida(
        f'backend de alocacao desconhecido: {configuracao.backend!r}')
