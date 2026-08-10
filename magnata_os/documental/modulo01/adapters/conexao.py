"""
Conexao Postgres minima (Modulo 01, Fase 4 -- escrita real).

Le DATABASE_URL do ambiente e abre uma conexao compativel com a interface
DB-API 2.0 (PEP 249) ja assumida por postgres_repositorio.py e
postgres_execucao.py -- `.cursor()`, `.commit()`, `.rollback()`, etc.

Este e o UNICO modulo do pacote que importa `psycopg` por nome, e mesmo
aqui o import e local (dentro de abrir_conexao), nao no topo do arquivo --
nenhum repositorio, servico ou dominio acima dele fica acoplado ao driver
concreto (ver magnata_os/CLAUDE.md, "todo servico externo entra por
adapter"). `conectar` e injetavel para teste -- nenhum teste deste modulo
precisa do driver `psycopg` de verdade instalado.

Nunca expoe DATABASE_URL (pode conter senha) em excecao, log ou retorno --
qualquer falha de conexao e resumida por _sanitizar_mensagem_erro antes de
propagar.
"""
from __future__ import annotations

import os
import re
from typing import Callable, Optional

_PADRAO_URL_CREDENCIAL = re.compile(r'postgres(?:ql)?://[^\s]+', re.IGNORECASE)


class ConfiguracaoBancoAusente(Exception):
    """DATABASE_URL nao definida (ou vazia) no ambiente."""


class FalhaConexaoBanco(Exception):
    """Falha ao abrir a conexao -- mensagem sempre sanitizada, nunca inclui
    a DATABASE_URL nem credenciais na excecao."""


def _sanitizar_mensagem_erro(mensagem: str) -> str:
    """Remove qualquer trecho que pareca uma URL de conexao Postgres
    (esquema postgres://usuario:senha@host/...) de uma mensagem de erro
    antes de propaga-la -- nunca vaza credencial em excecao ou log."""
    return _PADRAO_URL_CREDENCIAL.sub('postgres://<sanitizado>', mensagem or '')


def ler_database_url(ambiente: Optional[dict] = None) -> str:
    """Le e valida DATABASE_URL. `ambiente` injetavel para teste (default:
    os.environ real). Levanta ConfiguracaoBancoAusente se ausente/vazia --
    nunca devolve string vazia silenciosamente."""
    fonte = ambiente if ambiente is not None else os.environ
    valor = (fonte.get('DATABASE_URL') or '').strip()
    if not valor:
        raise ConfiguracaoBancoAusente(
            'DATABASE_URL nao configurada -- a conexao Postgres real requer '
            'essa variavel de ambiente (ver render.yaml, databases/fromDatabase).'
        )
    return valor


def abrir_conexao(
    database_url: Optional[str] = None,
    conectar: Optional[Callable[[str], object]] = None,
    ambiente: Optional[dict] = None,
):
    """
    Abre e devolve uma conexao psycopg (v3) com autocommit=False -- mesma
    disciplina transacional dos adapters existentes (commit/rollback
    explicitos por operacao, ver postgres_repositorio.py).

    `database_url`: string de conexao explicita (senao le de `ambiente`/
    os.environ via ler_database_url).
    `conectar`: callable injetavel (assinatura `(url) -> conexao`) --
    quando None, importa e usa `psycopg.connect` de verdade. Testes SEMPRE
    passam um `conectar` fake; nenhum teste deste modulo depende do driver
    `psycopg` estar instalado.
    """
    url = database_url if database_url is not None else ler_database_url(ambiente)

    if conectar is None:
        import psycopg  # import local -- unico ponto de acoplamento ao driver
        conectar = psycopg.connect

    try:
        conexao = conectar(url)
    except Exception as exc:
        raise FalhaConexaoBanco(
            f'Falha ao conectar ao Postgres: {type(exc).__name__} -- '
            f'{_sanitizar_mensagem_erro(str(exc))}'
        ) from exc

    conexao.autocommit = False
    return conexao
