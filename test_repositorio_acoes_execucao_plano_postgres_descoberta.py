"""Descoberta somente leitura para o ciclo de produção: pares
(event_id, preview_id) elegíveis e ações já SUCCEEDED para observação.
Nenhum dos dois métodos faz claim nem altera estado.
"""
from datetime import datetime, timezone

from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoPostgres,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)


class _Cursor:
    def __init__(self, conexao):
        self.conexao = conexao

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.conexao.executados.append((sql, params))

    def fetchall(self):
        return self.conexao.linhas


class _Conexao:
    def __init__(self, linhas=()):
        self.linhas = list(linhas)
        self.executados = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _linha_succeeded(acao_execucao_id='a' * 64):
    return (
        acao_execucao_id, 'evento-1', 'preview-1', 'auth-1', 1, 'texto',
        'dest-hash', None, None, 'texto-hash', 'e' * 64,
        EstadoAcaoExecucaoPlano.SUCCEEDED.value, 1, None, None, AGORA,
        None, 'EVOLUTION-ID-1', 'ev' * 32, AGORA, AGORA, AGORA,
    )


def test_listar_pares_elegiveis_e_apenas_select_sem_claim():
    conexao = _Conexao(linhas=[('evento-1', 'preview-1'), ('evento-2', 'preview-9')])
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)

    pares = repo.listar_pares_elegiveis(instante=AGORA)

    assert pares == (('evento-1', 'preview-1'), ('evento-2', 'preview-9'))
    sql, _ = conexao.executados[0]
    assert sql.strip().upper().startswith('SELECT')
    assert 'DISTINCT' in sql.upper()
    assert conexao.commits == 0
    assert conexao.rollbacks == 0


def test_listar_pares_elegiveis_respeita_limite():
    conexao = _Conexao(linhas=[])
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    repo.listar_pares_elegiveis(instante=AGORA, limite=50)
    _, params = conexao.executados[0]
    assert 50 in params


def test_listar_succeeded_recentes_filtra_por_estado_e_tipo_texto():
    conexao = _Conexao(linhas=[_linha_succeeded()])
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)

    resultado = repo.listar_succeeded_recentes()

    assert len(resultado) == 1
    assert resultado[0].estado == EstadoAcaoExecucaoPlano.SUCCEEDED
    _, params = conexao.executados[0]
    assert EstadoAcaoExecucaoPlano.SUCCEEDED.value in params
    assert 'texto' in params


def test_listar_succeeded_recentes_e_apenas_select():
    conexao = _Conexao(linhas=[])
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    repo.listar_succeeded_recentes(limite=10)
    sql, params = conexao.executados[0]
    assert sql.strip().upper().startswith('SELECT')
    assert 10 in params
    assert conexao.commits == 0
