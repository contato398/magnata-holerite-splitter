"""Testes do adapter `postgres_resolucao_temporal.py` (missão
"IDENTIDADE TEMPORAL DOCUMENTAL DA FOLHA/CARTÃO DE PONTO V1"). Usa uma
conexão FAKE (nunca rede/Postgres real) que imita a interface DB-API
2.0 mínima — prova o formato dos INSERTs e, principalmente, o GATE DE
ATOMICIDADE: se o segundo INSERT (evento) falhar, `rollback()` é
chamado e NENHUM `commit()` acontece — o INSERT da resolução, já
executado no cursor, nunca é confirmado."""
import datetime

import pytest

from magnata_os.classificacao.contratos import EstadoResolucaoDimensao
from magnata_os.classificacao.resolucao_temporal_ponto import resolver_documento_ponto
from magnata_os.documental.modulo01.adapters.postgres_resolucao_temporal import (
    RepositorioResolucaoTemporalPostgres,
)
from magnata_os.documental.modulo01.dominio import EventoHistorico, gerar_correlation_id


class _CursorFake:
    def __init__(self, conexao):
        self._conexao = conexao

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self._conexao.execucoes.append((sql.strip().split()[0], params))
        if self._conexao.falhar_na_execucao_numero is not None:
            if len(self._conexao.execucoes) == self._conexao.falhar_na_execucao_numero:
                raise RuntimeError('falha simulada de execução SQL')

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _ConexaoFake:
    """Conexão DB-API 2.0 mínima, sem rede — só registra execuções e
    commits/rollbacks para inspeção pelo teste."""

    def __init__(self, falhar_na_execucao_numero=None):
        self.execucoes = []
        self.commits = 0
        self.rollbacks = 0
        self.falhar_na_execucao_numero = falhar_na_execucao_numero

    def cursor(self):
        return _CursorFake(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _evento(documento_id: str) -> EventoHistorico:
    return EventoHistorico(
        documento_id=documento_id, evento='RESOLUCAO_TEMPORAL_PONTO_REGISTRADA',
        status_anterior=None, status_novo=None,
        timestamp=datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc),
        correlation_id=gerar_correlation_id(), detalhes={},
    )


def _resolucao_valida():
    texto = 'Período: 29/05/2026 até 28/06/2026'
    resolucao, _cliente = resolver_documento_ponto('doc-pg-1', texto, 'func-pg-1', _FonteVazia())
    return resolucao


class _FonteVazia:
    def listar_para_colaborador(self, colaborador_id):
        return ()


def test_salvar_com_evento_faz_2_inserts_e_1_commit_quando_tudo_ok():
    conexao = _ConexaoFake()
    repo = RepositorioResolucaoTemporalPostgres(conexao)
    repo.salvar_com_evento(_resolucao_valida(), lambda: _evento('doc-pg-1'))

    comandos = [c for c, _ in conexao.execucoes]
    assert comandos == ['INSERT', 'INSERT']
    assert conexao.commits == 1
    assert conexao.rollbacks == 0


def test_falha_no_insert_do_evento_reverte_tudo_gate_de_atomicidade():
    """2ª execução (INSERT do evento) falha -- rollback deve acontecer,
    ZERO commits -- o INSERT da resolução, já enviado ao cursor, nunca é
    confirmado."""
    conexao = _ConexaoFake(falhar_na_execucao_numero=2)
    repo = RepositorioResolucaoTemporalPostgres(conexao)

    with pytest.raises(RuntimeError):
        repo.salvar_com_evento(_resolucao_valida(), lambda: _evento('doc-pg-1'))

    assert conexao.commits == 0  # NUNCA um commit parcial
    assert conexao.rollbacks == 1


def test_falha_no_insert_da_resolucao_tambem_reverte_e_nunca_tenta_o_evento():
    conexao = _ConexaoFake(falhar_na_execucao_numero=1)
    repo = RepositorioResolucaoTemporalPostgres(conexao)

    with pytest.raises(RuntimeError):
        repo.salvar_com_evento(_resolucao_valida(), lambda: _evento('doc-pg-1'))

    assert conexao.commits == 0
    assert conexao.rollbacks == 1
    assert len(conexao.execucoes) == 1  # nunca chegou a tentar o evento
