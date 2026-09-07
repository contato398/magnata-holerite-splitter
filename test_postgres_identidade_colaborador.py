"""Testes do adapter `postgres_identidade_colaborador.py`. Usa uma
conexão FAKE (nunca rede/Postgres real) que imita a interface DB-API
2.0 mínima -- mesmo padrão de `test_postgres_resolucao_temporal.py`."""
from datetime import datetime, timezone

import pytest

from magnata_os.documental.alocacao.adapters.postgres_identidade_colaborador import (
    RepositorioIdentidadeColaboradorPostgres,
)
from magnata_os.documental.alocacao.identidade_colaborador import (
    ConflitoIdentidadeColaborador,
    IdentidadeColaboradorObservada,
)


class IntegrityError(Exception):
    """Nome EXATO que `_e_violacao_de_integridade` detecta por
    `__mro__` (duck-typing por nome de classe, mesmo padrão de
    `postgres_repositorio.py`/`postgres_resolucao_temporal.py`) --
    nunca importa um driver real."""


def _identidade(colaborador_id: str, hash_: str = 'hash_a') -> IdentidadeColaboradorObservada:
    agora = datetime(2026, 9, 6, tzinfo=timezone.utc)
    return IdentidadeColaboradorObservada(
        tipo_identificador='CPF', identificador_hash=hash_, colaborador_id=colaborador_id,
        origem='teste', versao_chave='v1', criado_em=agora, atualizado_em=agora,
    )


class _CursorFake:
    def __init__(self, conexao):
        self._conexao = conexao

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        comando = sql.strip().split()[0]
        self._conexao.execucoes.append((comando, params))
        if self._conexao.levantar_integrity_error_no_insert and comando == 'INSERT':
            raise IntegrityError('duplicate key value violates unique constraint')

    def fetchone(self):
        return self._conexao.linha_existente

    def fetchall(self):
        return self._conexao.linhas_existentes


class _ConexaoFake:
    def __init__(self, linha_existente=None, levantar_integrity_error_no_insert=False):
        self.execucoes = []
        self.commits = 0
        self.rollbacks = 0
        self.linha_existente = linha_existente
        self.linhas_existentes = [linha_existente] if linha_existente else []
        self.levantar_integrity_error_no_insert = levantar_integrity_error_no_insert

    def cursor(self):
        return _CursorFake(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_buscar_por_identificador_ausente_devolve_none():
    conexao = _ConexaoFake(linha_existente=None)
    repo = RepositorioIdentidadeColaboradorPostgres(conexao)

    assert repo.buscar_por_identificador('CPF', 'hash_a') is None
    assert conexao.execucoes[0][0] == 'SELECT'


def test_criar_se_ausente_insere_quando_nao_existe_e_comita():
    conexao = _ConexaoFake(linha_existente=None)
    repo = RepositorioIdentidadeColaboradorPostgres(conexao)

    persistida, criada = repo.criar_se_ausente(_identidade('func_1'))

    assert criada is True
    assert persistida.colaborador_id == 'func_1'
    comandos = [c for c, _ in conexao.execucoes]
    assert comandos == ['SELECT', 'INSERT']
    assert conexao.commits == 1
    assert conexao.rollbacks == 0


def test_criar_se_ausente_idempotente_quando_mesmo_colaborador_ja_existe():
    linha = ('CPF', 'hash_a', 'func_1', 'teste', 'v1',
             datetime(2026, 9, 6, tzinfo=timezone.utc), datetime(2026, 9, 6, tzinfo=timezone.utc))
    conexao = _ConexaoFake(linha_existente=linha)
    repo = RepositorioIdentidadeColaboradorPostgres(conexao)

    persistida, criada = repo.criar_se_ausente(_identidade('func_1'))

    assert criada is False
    assert persistida.colaborador_id == 'func_1'
    # Nunca chega a tentar INSERT -- SELECT já resolveu o caso idempotente.
    comandos = [c for c, _ in conexao.execucoes]
    assert comandos == ['SELECT']
    assert conexao.commits == 0


def test_criar_se_ausente_levanta_conflito_quando_colaborador_diferente_ja_existe():
    linha = ('CPF', 'hash_a', 'func_1', 'teste', 'v1',
             datetime(2026, 9, 6, tzinfo=timezone.utc), datetime(2026, 9, 6, tzinfo=timezone.utc))
    conexao = _ConexaoFake(linha_existente=linha)
    repo = RepositorioIdentidadeColaboradorPostgres(conexao)

    with pytest.raises(ConflitoIdentidadeColaborador) as exc_info:
        repo.criar_se_ausente(_identidade('func_2'))

    assert exc_info.value.colaborador_id_existente == 'func_1'
    assert exc_info.value.colaborador_id_tentativa == 'func_2'
    # Nunca tenta escrever nada.
    comandos = [c for c, _ in conexao.execucoes]
    assert 'INSERT' not in comandos
    assert conexao.commits == 0


def test_criar_se_ausente_trata_corrida_de_insert_concorrente_como_idempotente():
    """SELECT inicial não achou nada (linha_existente=None), mas o
    INSERT falha por violação de integridade (outra transação venceu a
    corrida) -- relê e, se o colaborador_id bate, trata como
    idempotente, nunca propaga a IntegrityError crua."""
    linha_apos_corrida = ('CPF', 'hash_a', 'func_1', 'teste', 'v1',
                           datetime(2026, 9, 6, tzinfo=timezone.utc), datetime(2026, 9, 6, tzinfo=timezone.utc))

    class _ConexaoComCorrida(_ConexaoFake):
        def cursor(self):
            # Primeira leitura (dentro de buscar_por_identificador
            # antes do INSERT): ainda não existe. Após o INSERT falhar,
            # a releitura (segunda chamada a buscar_por_identificador)
            # já encontra a linha inserida pela transação concorrente.
            self._chamadas_cursor = getattr(self, '_chamadas_cursor', 0) + 1
            if self._chamadas_cursor >= 3:
                self.linha_existente = linha_apos_corrida
            return _CursorFake(self)

    conexao = _ConexaoComCorrida(linha_existente=None, levantar_integrity_error_no_insert=True)
    repo = RepositorioIdentidadeColaboradorPostgres(conexao)

    persistida, criada = repo.criar_se_ausente(_identidade('func_1'))

    assert criada is False
    assert persistida.colaborador_id == 'func_1'
    assert conexao.rollbacks == 1


def test_listar_todos_converte_todas_as_linhas():
    linha = ('CPF', 'hash_a', 'func_1', 'teste', 'v1',
             datetime(2026, 9, 6, tzinfo=timezone.utc), datetime(2026, 9, 6, tzinfo=timezone.utc))
    conexao = _ConexaoFake()
    conexao.linhas_existentes = [linha]
    repo = RepositorioIdentidadeColaboradorPostgres(conexao)

    resultado = repo.listar_todos()

    assert len(resultado) == 1
    assert resultado[0].colaborador_id == 'func_1'
