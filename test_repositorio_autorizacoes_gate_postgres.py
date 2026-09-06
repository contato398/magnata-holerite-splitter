"""Persistencia Postgres de autorizacoes de gate: contrato e migration inerte."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from magnata_os.orquestrador.autorizacao_gate import (
    ConflitoDecisaoGateError,
    DecisaoGate,
    RegistroAutorizacaoGate,
)
from magnata_os.orquestrador.repositorio_autorizacoes_gate_postgres import (
    RepositorioAutorizacoesGatePostgres,
)

_INSTANTE = datetime(2026, 9, 6, 21, 30, tzinfo=timezone.utc)


def _registro(decisao=DecisaoGate.AUTORIZADO):
    return RegistroAutorizacaoGate(
        autorizacao_id='auth-001' if decisao == DecisaoGate.AUTORIZADO else 'auth-002',
        event_id='comunicacao:intencao-001',
        preview_id='preview-001',
        decisao=decisao,
        ator_referencia='sujeito:gestor-001',
        registrado_em=_INSTANTE,
        proveniencia='magnata_os:sessao_autenticada',
    )


def _linha(registro):
    return (
        registro.autorizacao_id,
        registro.event_id,
        registro.preview_id,
        registro.decisao.value,
        registro.ator_referencia,
        registro.registrado_em,
        registro.proveniencia,
    )


class _Cursor:
    def __init__(self, conexao):
        self.conexao = conexao

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        self.conexao.executados.append((sql, params))

    def fetchone(self):
        return self.conexao.fetchone_respostas.pop(0)

    def fetchall(self):
        return self.conexao.fetchall_respostas.pop(0)


class _Conexao:
    def __init__(self, *, fetchone=(), fetchall=()):
        self.fetchone_respostas = list(fetchone)
        self.fetchall_respostas = list(fetchall)
        self.executados = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def test_insert_novo_e_atomico_por_evento_preview():
    registro = _registro()
    conexao = _Conexao(fetchone=(_linha(registro),))
    repo = RepositorioAutorizacoesGatePostgres(conexao)

    assert repo.registrar_se_novo(registro) is True
    assert conexao.commits == 1
    assert conexao.rollbacks == 0
    sql = conexao.executados[0][0]
    assert 'ON CONFLICT (event_id, preview_id) DO NOTHING' in sql
    assert 'UPDATE' not in sql.upper()


def test_mesma_decisao_e_idempotente_sem_update():
    registro = _registro()
    conexao = _Conexao(fetchone=(None, _linha(registro)))
    repo = RepositorioAutorizacoesGatePostgres(conexao)

    assert repo.registrar_se_novo(registro) is False
    assert conexao.commits == 1
    assert conexao.rollbacks == 0
    assert len(conexao.executados) == 2
    assert all('UPDATE' not in sql.upper() for sql, _ in conexao.executados)


def test_decisao_conflitante_falha_e_faz_rollback():
    existente = _registro(DecisaoGate.RECUSADO)
    pretendido = _registro(DecisaoGate.AUTORIZADO)
    conexao = _Conexao(fetchone=(None, _linha(existente)))
    repo = RepositorioAutorizacoesGatePostgres(conexao)

    with pytest.raises(ConflitoDecisaoGateError):
        repo.registrar_se_novo(pretendido)

    assert conexao.commits == 0
    assert conexao.rollbacks == 1


def test_busca_e_listagem_reconstroem_registro_canonico():
    registro = _registro()
    conexao_busca = _Conexao(fetchone=(_linha(registro),))
    repo_busca = RepositorioAutorizacoesGatePostgres(conexao_busca)
    assert repo_busca.buscar(registro.event_id, registro.preview_id) == registro

    conexao_lista = _Conexao(fetchall=((_linha(registro),),))
    repo_lista = RepositorioAutorizacoesGatePostgres(conexao_lista)
    assert repo_lista.listar_por_evento(registro.event_id) == [registro]


def test_migration_e_append_only_e_inerte():
    caminho = Path('magnata_os/orquestrador/migrations/0002_autorizacoes_gate.sql')
    sql = caminho.read_text(encoding='utf-8')

    assert 'INERTE' in sql
    assert 'CREATE TABLE magnata_orquestrador.autorizacoes_gate' in sql
    assert "CHECK (decisao IN ('AUTORIZADO', 'RECUSADO'))" in sql
    assert 'UNIQUE (event_id, preview_id)' in sql
    assert 'BEFORE UPDATE OR DELETE' in sql
    assert 'REFERENCES magnata_orquestrador.execucoes(event_id)' in sql


def test_rollback_e_explicito_e_destrutivo_sem_execucao_automatica():
    caminho = Path('magnata_os/orquestrador/migrations/0002_autorizacoes_gate_rollback.sql')
    sql = caminho.read_text(encoding='utf-8')

    assert 'Destrutivo: nunca executar automaticamente' in sql
    assert 'DROP TABLE magnata_orquestrador.autorizacoes_gate' in sql
