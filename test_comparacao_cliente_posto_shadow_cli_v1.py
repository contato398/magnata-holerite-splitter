"""Testes da frente G ("saída progressiva do Airtable"), 2 peças novas:

  1. `RepositorioAlocacaoPostgres.postos_com_vigencia_cliente_registrada`
     (mock cursor DB-API 2.0, mesmo padrão de
     `test_comparacao_cliente_posto_airtable_shadow_v1.py` -- não acessa
     Postgres real);
  2. `comparacao_cliente_posto_shadow_cli.rodar_comparacao` (pura, com
     fakes duck-typed, injeção de repo/snapshot -- nenhum teste aqui
     chama `main()`/lê `DATABASE_URL`/`AIRTABLE_API_KEY` reais).

Nenhum teste aqui escreve em nenhum dos dois lados -- comparação é
sempre read-only, mesma disciplina de `comparacao_airtable.py`."""
from __future__ import annotations

import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))

from magnata_os.documental.alocacao.adapters.postgres_alocacao import RepositorioAlocacaoPostgres

from comparacao_cliente_posto_shadow_cli import (  # noqa: E402
    CredencialAusente,
    _ler_airtable_api_key,
    rodar_comparacao,
)


class _MockCursor:
    def __init__(self, rows):
        self.rows = rows
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _MockConexao:
    def __init__(self, rows):
        self._cursor = _MockCursor(rows)

    def cursor(self):
        return self._cursor


# ── postos_com_vigencia_cliente_registrada ──────────────────────────

def test_postos_com_vigencia_cliente_registrada_lista_distintos():
    repo = RepositorioAlocacaoPostgres(_MockConexao([("posto-1",), ("posto-2",)]))
    assert repo.postos_com_vigencia_cliente_registrada() == ("posto-1", "posto-2")


def test_postos_com_vigencia_cliente_registrada_vazia_e_valida():
    repo = RepositorioAlocacaoPostgres(_MockConexao([]))
    assert repo.postos_com_vigencia_cliente_registrada() == ()


def test_postos_com_vigencia_cliente_registrada_usa_distinct_na_query():
    conexao = _MockConexao([])
    RepositorioAlocacaoPostgres(conexao).postos_com_vigencia_cliente_registrada()
    query = conexao._cursor.last_query.lower()
    assert "distinct posto_id" in query
    assert "vigencia_cliente_por_posto" in query


# ── _ler_airtable_api_key ─────────────────────────────────────────────

def test_ler_airtable_api_key_ausente_levanta():
    try:
        _ler_airtable_api_key(ambiente={})
    except CredencialAusente:
        pass
    else:
        raise AssertionError("deveria levantar CredencialAusente")


def test_ler_airtable_api_key_presente():
    assert _ler_airtable_api_key(ambiente={"AIRTABLE_API_KEY": "fake"}) == "fake"


# ── rodar_comparacao ──────────────────────────────────────────────────

class _RepoFake:
    def __init__(self, clientes_por_posto):
        self._clientes_por_posto = clientes_por_posto

    def cliente_vigente_do_posto(self, posto_id, data_referencia):
        return self._clientes_por_posto.get(posto_id)


class _SnapshotFake:
    def __init__(self, clientes_por_posto):
        self._clientes_por_posto = clientes_por_posto

    def clientes_atuais_do_posto(self, posto_id):
        return self._clientes_por_posto.get(posto_id, frozenset())


_DATA = datetime.date(2026, 10, 1)


def test_rodar_comparacao_resume_por_estado():
    repo = _RepoFake({"posto-1": "cliente-1", "posto-2": "cliente-9"})
    snapshot = _SnapshotFake({
        "posto-1": frozenset({"cliente-1"}),  # consistente
        "posto-2": frozenset({"cliente-2"}),  # diferente
    })
    relatorio = rodar_comparacao(("posto-1", "posto-2"), _DATA, repo, snapshot)
    assert relatorio["total_postos"] == 2
    assert relatorio["resumo_por_estado"] == {"consistente": 1, "diferente": 1}
    assert relatorio["por_posto"] == {"posto-1": "consistente", "posto-2": "diferente"}
    assert relatorio["data_referencia"] == "2026-10-01"


def test_rodar_comparacao_lista_vazia_e_valida():
    relatorio = rodar_comparacao((), _DATA, _RepoFake({}), _SnapshotFake({}))
    assert relatorio["total_postos"] == 0
    assert relatorio["resumo_por_estado"] == {}
    assert relatorio["por_posto"] == {}
