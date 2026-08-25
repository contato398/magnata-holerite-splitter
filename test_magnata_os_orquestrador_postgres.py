"""Contrato do adapter Postgres do Grande Orquestrador.

Os testes usam um duplo DB-API: nenhum banco, rede, secret ou migration real.
"""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from magnata_os.orquestrador.eventos import EstadoExecucao
from magnata_os.orquestrador.fabrica_repositorio_execucoes import (
    BackendExecucoes,
    ConfiguracaoRepositorioExecucoes,
    ConfiguracaoRepositorioInvalida,
    construir_repositorio_execucoes,
)
from magnata_os.orquestrador.repositorio_execucoes import (
    RegistroExecucao,
    RegistroRecuperacao,
    RepositorioExecucoesEmMemoria,
    RepositorioExecucoesSQLite,
)
from magnata_os.orquestrador.repositorio_execucoes_postgres import (
    RepositorioExecucoesPostgres,
)


INSTANTE = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)


def _registro(event_id='evt-1', estado=EstadoExecucao.RECEIVED):
    return RegistroExecucao(
        event_id=event_id,
        event_type='GIT_MAIN_AVANCOU',
        estado=estado,
        nivel_autonomia=4,
        acao='atualizar_auto_fact',
        resultado=None,
        evidencia='sha-publico',
        attempt=1,
        next_retry_at=None,
        last_error_classe=None,
        last_error_at=None,
        criado_em=INSTANTE,
        atualizado_em=INSTANTE,
        evento_json='{"event_id":"evt-1"}',
    )


def _linha(registro=None):
    registro = registro or _registro()
    return (
        registro.event_id,
        registro.event_type,
        registro.estado.value,
        registro.nivel_autonomia,
        registro.acao,
        registro.resultado,
        registro.evidencia,
        registro.attempt,
        registro.next_retry_at,
        registro.last_error_classe,
        registro.last_error_at,
        registro.criado_em,
        registro.atualizado_em,
        registro.evento_json,
        registro.manualmente_reiniciado_por,
        registro.manualmente_reiniciado_em,
        registro.motivo_reinicio_manual,
    )


class _CursorRoteado:
    def __init__(self, conexao):
        self._conexao = conexao
        self._resultado = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        resposta = self._conexao.respostas.pop(0) if self._conexao.respostas else []
        self._conexao.chamadas.append((' '.join(sql.split()), tuple(params)))
        if isinstance(resposta, Exception):
            raise resposta
        self._resultado = list(resposta)

    def fetchone(self):
        return self._resultado.pop(0) if self._resultado else None

    def fetchall(self):
        resultado = list(self._resultado)
        self._resultado.clear()
        return resultado


class _ConexaoRoteada:
    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas = []
        self.commits = 0
        self.rollbacks = 0
        self.fechada = False

    def cursor(self):
        return _CursorRoteado(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.fechada = True


def test_buscar_e_listar_mapeiam_o_mesmo_contrato_do_sqlite():
    reg_2 = _registro('evt-2', EstadoExecucao.SUCCEEDED)
    conexao = _ConexaoRoteada([_linha()], [_linha(), _linha(reg_2)])
    repo = RepositorioExecucoesPostgres(conexao)

    encontrado = repo.buscar_por_event_id('evt-1')
    todos = repo.listar_todos()

    assert encontrado == _registro()
    assert [registro.event_id for registro in todos] == ['evt-1', 'evt-2']
    assert todos[1].estado == EstadoExecucao.SUCCEEDED
    assert all('magnata_orquestrador.execucoes' in sql for sql, _ in conexao.chamadas)


def test_salvar_faz_upsert_sem_reescrever_identidade_do_evento():
    conexao = _ConexaoRoteada([])
    repo = RepositorioExecucoesPostgres(conexao)

    repo.salvar(_registro())

    sql, parametros = conexao.chamadas[0]
    assert 'ON CONFLICT (event_id) DO UPDATE' in sql
    trecho_update = sql.split('DO UPDATE SET', 1)[1]
    assert 'event_id = EXCLUDED.event_id' not in trecho_update
    assert 'event_type = EXCLUDED.event_type' not in trecho_update
    assert 'criado_em = EXCLUDED.criado_em' not in trecho_update
    assert parametros[0] == 'evt-1'
    assert conexao.commits == 1
    assert conexao.rollbacks == 0


@pytest.mark.parametrize(('retorno', 'esperado'), [([('evt-1',)], True), ([], False)])
def test_criar_se_novo_usa_claim_atomico_por_primary_key(retorno, esperado):
    conexao = _ConexaoRoteada(retorno)
    repo = RepositorioExecucoesPostgres(conexao)

    assert repo.criar_se_novo(_registro()) is esperado

    sql, _ = conexao.chamadas[0]
    assert 'ON CONFLICT (event_id) DO NOTHING RETURNING event_id' in sql
    assert conexao.commits == 1


def test_retry_e_claim_e_auditoria_atomicos_na_mesma_instrucao():
    reivindicado = _registro('evt-retry', EstadoExecucao.EXECUTING)
    reivindicado.attempt = 2
    conexao = _ConexaoRoteada([_linha(reivindicado)])
    repo = RepositorioExecucoesPostgres(conexao)

    resultado = repo.reivindicar_retry('evt-retry', INSTANTE)

    sql, parametros = conexao.chamadas[0]
    assert sql.startswith('WITH reivindicado AS ( UPDATE')
    assert 'AND estado = %s' in sql
    assert 'INSERT INTO magnata_orquestrador.auditoria' in sql
    assert parametros[0] == EstadoExecucao.EXECUTING.value
    assert parametros[3] == EstadoExecucao.FAILED_RETRYABLE.value
    assert resultado.estado == EstadoExecucao.EXECUTING
    assert resultado.attempt == 2
    assert conexao.commits == 1


def test_retry_perdido_nao_reexecuta_e_retorna_none():
    conexao = _ConexaoRoteada([])
    repo = RepositorioExecucoesPostgres(conexao)

    assert repo.reivindicar_retry('evt-ja-reivindicado', INSTANTE) is None
    assert conexao.commits == 1
    assert len(conexao.chamadas) == 1


def test_falha_de_escrita_faz_rollback_e_propaga():
    conexao = _ConexaoRoteada(ConnectionError('postgres indisponivel'))
    repo = RepositorioExecucoesPostgres(conexao)

    with pytest.raises(ConnectionError, match='postgres indisponivel'):
        repo.salvar(_registro())

    assert conexao.commits == 0
    assert conexao.rollbacks == 1


def test_auditorias_sao_append_only_e_ordenadas_pelo_id():
    recuperacao = RegistroRecuperacao(
        event_id='evt-1',
        decisao='ESCALAR_HUMANO',
        estado_observado='EXECUTING',
        registrado_em=INSTANTE,
        motivo='worker possivelmente interrompido',
        evidencia='sem replay automatico',
    )
    conexao = _ConexaoRoteada(
        [],
        [('evt-1', 'RECEIVED', 'VALIDATED', INSTANTE, 'valido')],
        [],
        [(
            recuperacao.event_id, recuperacao.decisao,
            recuperacao.estado_observado, recuperacao.registrado_em,
            recuperacao.motivo, recuperacao.evidencia,
        )],
    )
    repo = RepositorioExecucoesPostgres(conexao)

    repo.registrar_auditoria('evt-1', 'RECEIVED', 'VALIDATED', INSTANTE, 'valido')
    auditoria = repo.listar_auditoria('evt-1')
    repo.registrar_recuperacao(recuperacao)
    recuperacoes = repo.listar_recuperacoes('evt-1')

    assert auditoria[0].estado_novo == 'VALIDATED'
    assert recuperacoes == [recuperacao]
    assert 'ORDER BY id ASC' in conexao.chamadas[1][0]
    assert 'ORDER BY id ASC' in conexao.chamadas[3][0]
    assert conexao.commits == 2


def test_fechar_delega_para_conexao_sem_efeito_externo():
    conexao = _ConexaoRoteada()
    RepositorioExecucoesPostgres(conexao).fechar()
    assert conexao.fechada is True


def test_fabrica_exige_backend_e_dependencias_explicitas(tmp_path):
    memoria = construir_repositorio_execucoes(
        ConfiguracaoRepositorioExecucoes(BackendExecucoes.MEMORIA)
    )
    sqlite = construir_repositorio_execucoes(
        ConfiguracaoRepositorioExecucoes(
            BackendExecucoes.SQLITE,
            caminho_sqlite=tmp_path / 'execucoes.db',
        )
    )
    conexao = _ConexaoRoteada()
    postgres = construir_repositorio_execucoes(
        ConfiguracaoRepositorioExecucoes(BackendExecucoes.POSTGRES),
        conexao_postgres=conexao,
    )

    assert isinstance(memoria, RepositorioExecucoesEmMemoria)
    assert isinstance(sqlite, RepositorioExecucoesSQLite)
    assert isinstance(postgres, RepositorioExecucoesPostgres)
    sqlite.fechar()


def test_fabrica_postgres_falha_sem_conexao_e_nunca_cai_para_sqlite():
    with pytest.raises(
        ConfiguracaoRepositorioInvalida,
        match='conexao autenticada injetada explicitamente',
    ):
        construir_repositorio_execucoes(
            ConfiguracaoRepositorioExecucoes(BackendExecucoes.POSTGRES)
        )


def test_fabrica_rejeita_configuracao_ambigua(tmp_path):
    with pytest.raises(ConfiguracaoRepositorioInvalida, match='nao aceita caminho SQLite'):
        construir_repositorio_execucoes(
            ConfiguracaoRepositorioExecucoes(
                BackendExecucoes.POSTGRES,
                caminho_sqlite=tmp_path / 'nao-usar.db',
            ),
            conexao_postgres=_ConexaoRoteada(),
        )


def test_migration_e_inerte_namespaced_e_append_only():
    raiz = Path(__file__).parent
    migration = (
        raiz / 'magnata_os/orquestrador/migrations/0001_repositorio_execucoes.sql'
    ).read_text(encoding='utf-8')
    rollback = (
        raiz
        / 'magnata_os/orquestrador/migrations/0001_repositorio_execucoes_rollback.sql'
    ).read_text(encoding='utf-8')

    assert 'CREATE SCHEMA IF NOT EXISTS magnata_orquestrador' in migration
    assert 'REFERENCES magnata_orquestrador.execucoes(event_id)' in migration
    assert migration.count('BEFORE UPDATE OR DELETE') == 2
    assert 'nenhum modulo aplica esta migration automaticamente' in migration
    assert 'DROP SCHEMA magnata_orquestrador CASCADE' in rollback
    assert 'nunca executar automaticamente' in rollback
