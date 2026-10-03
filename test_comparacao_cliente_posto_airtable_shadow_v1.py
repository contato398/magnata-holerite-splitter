"""Testes da missão "SHADOW CLIENTE X POSTO AIRTABLE V1" (frente 7,
"Postgres e redução do Airtable"): comparação diagnóstica, read-only,
entre `vigencia_cliente_por_posto` (Postgres, shadow) e o snapshot
atual Local->Cliente do Airtable.

Cobre as 2 peças novas desta missão:
  1. `RepositorioAlocacaoPostgres.cliente_vigente_do_posto` (mock
     cursor DB-API 2.0, mesmo padrão de
     `test_vigencia_cliente_por_posto_v1.py` -- não acessa Postgres
     real);
  2. `comparar_cliente_do_posto_shadow_com_airtable` (puro, com fakes
     duck-typed, cobrindo os 5 estados reaproveitados de
     `comparar_postos`: consistente/diferente/magnata_sem_dado/
     airtable_sem_vinculo/ambiguo).

Nenhum teste aqui escreve em nenhum dos dois lados -- comparação é
sempre read-only."""
from __future__ import annotations

import datetime

from magnata_os.documental.alocacao.adapters.postgres_alocacao import RepositorioAlocacaoPostgres
from magnata_os.documental.alocacao.comparacao_airtable import (
    EstadoComparacaoAirtable,
    comparar_cliente_do_posto_shadow_com_airtable,
)


class _MockCursor:
    """Mock cursor DB-API 2.0 -- mesmo padrão de
    `test_vigencia_cliente_por_posto_v1.py`."""

    def __init__(self, rows):
        self.rows = rows
        self.last_query = None
        self.last_params = None

    def execute(self, query, params=None):
        self.last_query = query
        self.last_params = params or ()

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _MockConexao:
    def __init__(self, rows):
        self._cursor = _MockCursor(rows)

    def cursor(self):
        return self._cursor


# ── cliente_vigente_do_posto ───────────────────────────────────────

def test_cliente_vigente_do_posto_com_relacao_comprovada():
    repo = RepositorioAlocacaoPostgres(_MockConexao([("cliente-1",)]))
    assert repo.cliente_vigente_do_posto("posto-1", datetime.date(2026, 10, 1)) == "cliente-1"


def test_cliente_vigente_do_posto_sem_relacao_e_none():
    repo = RepositorioAlocacaoPostgres(_MockConexao([]))
    assert repo.cliente_vigente_do_posto("posto-1", datetime.date(2026, 10, 1)) is None


def test_cliente_vigente_do_posto_filtra_por_vigencia_na_query():
    conexao = _MockConexao([("cliente-1",)])
    repo = RepositorioAlocacaoPostgres(conexao)
    repo.cliente_vigente_do_posto("posto-1", datetime.date(2026, 10, 1))
    query = conexao._cursor.last_query.lower()
    assert "vigencia_cliente_por_posto" in query
    assert "vigente_de" in query and "vigente_ate" in query
    assert conexao._cursor.last_params == ("posto-1", datetime.date(2026, 10, 1), datetime.date(2026, 10, 1))


# ── comparar_cliente_do_posto_shadow_com_airtable (5 estados) ─────────

class _RepoFake:
    def __init__(self, cliente_shadow):
        self._cliente_shadow = cliente_shadow

    def cliente_vigente_do_posto(self, posto_id, data_referencia):
        return self._cliente_shadow


class _SnapshotFake:
    def __init__(self, clientes=None, levanta=False):
        self._clientes = clientes
        self._levanta = levanta

    def clientes_atuais_do_posto(self, posto_id):
        if self._levanta:
            raise RuntimeError("Airtable indisponível")
        return self._clientes


_DATA = datetime.date(2026, 10, 1)


def test_consistente_quando_ambos_tem_o_mesmo_cliente():
    estado = comparar_cliente_do_posto_shadow_com_airtable(
        _RepoFake("cliente-1"), _SnapshotFake(frozenset({"cliente-1"})), "posto-1", _DATA,
    )
    assert estado == EstadoComparacaoAirtable.CONSISTENTE


def test_consistente_quando_ambos_sem_cliente():
    estado = comparar_cliente_do_posto_shadow_com_airtable(
        _RepoFake(None), _SnapshotFake(frozenset()), "posto-1", _DATA,
    )
    assert estado == EstadoComparacaoAirtable.CONSISTENTE


def test_diferente_quando_clientes_divergem():
    estado = comparar_cliente_do_posto_shadow_com_airtable(
        _RepoFake("cliente-1"), _SnapshotFake(frozenset({"cliente-2"})), "posto-1", _DATA,
    )
    assert estado == EstadoComparacaoAirtable.DIFERENTE


def test_magnata_sem_dado_quando_so_airtable_tem_cliente():
    estado = comparar_cliente_do_posto_shadow_com_airtable(
        _RepoFake(None), _SnapshotFake(frozenset({"cliente-1"})), "posto-1", _DATA,
    )
    assert estado == EstadoComparacaoAirtable.MAGNATA_SEM_DADO


def test_airtable_sem_vinculo_quando_so_shadow_tem_cliente():
    estado = comparar_cliente_do_posto_shadow_com_airtable(
        _RepoFake("cliente-1"), _SnapshotFake(frozenset()), "posto-1", _DATA,
    )
    assert estado == EstadoComparacaoAirtable.AIRTABLE_SEM_VINCULO


def test_ambiguo_quando_airtable_levanta_excecao():
    estado = comparar_cliente_do_posto_shadow_com_airtable(
        _RepoFake("cliente-1"), _SnapshotFake(levanta=True), "posto-1", _DATA,
    )
    assert estado == EstadoComparacaoAirtable.AMBIGUO
