"""Testes do adapter `postgres_contato_colaborador.py`. Usa uma conexão
FAKE (nunca rede/Postgres real) que imita a interface DB-API 2.0
mínima -- mesmo padrão de `test_postgres_identidade_colaborador.py`."""
from datetime import datetime, timezone

import pytest

from magnata_os.documental.alocacao.adapters.postgres_contato_colaborador import (
    RepositorioContatoColaboradorPostgres,
)
from magnata_os.documental.alocacao.contato_colaborador import (
    CANAL_WHATSAPP,
    ConflitoContatoColaborador,
    RegistroContatoColaborador,
)


class IntegrityError(Exception):
    """Nome EXATO que `_e_violacao_de_integridade` detecta por
    `__mro__` (duck-typing por nome de classe) -- nunca importa um
    driver real."""


def _registro(colaborador_id: str = 'func_1', hash_: str = 'hash_a', valor_cifrado: bytes = b'token-cifrado') -> RegistroContatoColaborador:
    agora = datetime(2026, 9, 21, tzinfo=timezone.utc)
    return RegistroContatoColaborador(
        colaborador_id=colaborador_id, canal=CANAL_WHATSAPP, valor_cifrado=valor_cifrado,
        hash_auxiliar=hash_, versao_chave='v1', origem='teste', criado_em=agora, atualizado_em=agora,
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


def test_buscar_por_colaborador_ausente_devolve_none():
    conexao = _ConexaoFake(linha_existente=None)
    repo = RepositorioContatoColaboradorPostgres(conexao)

    assert repo.buscar_por_colaborador('func_1', CANAL_WHATSAPP) is None
    assert conexao.execucoes[0][0] == 'SELECT'


def test_criar_ou_confirmar_insere_quando_nao_existe_e_comita():
    conexao = _ConexaoFake(linha_existente=None)
    repo = RepositorioContatoColaboradorPostgres(conexao)

    persistido, criado = repo.criar_ou_confirmar(_registro())

    assert criado is True
    assert persistido.colaborador_id == 'func_1'
    comandos = [c for c, _ in conexao.execucoes]
    assert comandos == ['SELECT', 'INSERT']
    assert conexao.commits == 1
    assert conexao.rollbacks == 0


def test_criar_ou_confirmar_e_idempotente_quando_mesmo_hash_ja_existe():
    linha = ('func_1', CANAL_WHATSAPP, b'token-cifrado', 'hash_a', 'v1', 'teste',
              datetime(2026, 9, 21, tzinfo=timezone.utc), datetime(2026, 9, 21, tzinfo=timezone.utc))
    conexao = _ConexaoFake(linha_existente=linha)
    repo = RepositorioContatoColaboradorPostgres(conexao)

    persistido, criado = repo.criar_ou_confirmar(_registro())

    assert criado is False
    assert persistido.colaborador_id == 'func_1'
    comandos = [c for c, _ in conexao.execucoes]
    assert comandos == ['SELECT']
    assert conexao.commits == 0


def test_criar_ou_confirmar_levanta_conflito_quando_hash_diferente_ja_existe():
    """Telefone alterado para o mesmo colaborador/canal -- fail-closed,
    nunca sobrescreve."""
    linha = ('func_1', CANAL_WHATSAPP, b'token-antigo', 'hash_antigo', 'v1', 'teste',
              datetime(2026, 9, 21, tzinfo=timezone.utc), datetime(2026, 9, 21, tzinfo=timezone.utc))
    conexao = _ConexaoFake(linha_existente=linha)
    repo = RepositorioContatoColaboradorPostgres(conexao)

    with pytest.raises(ConflitoContatoColaborador) as exc_info:
        repo.criar_ou_confirmar(_registro(hash_='hash_novo'))

    assert exc_info.value.hash_auxiliar_existente == 'hash_antigo'
    assert exc_info.value.hash_auxiliar_tentativa == 'hash_novo'
    comandos = [c for c, _ in conexao.execucoes]
    assert 'INSERT' not in comandos
    assert conexao.commits == 0


def test_criar_ou_confirmar_trata_corrida_de_insert_concorrente_como_idempotente():
    linha_apos_corrida = ('func_1', CANAL_WHATSAPP, b'token-cifrado', 'hash_a', 'v1', 'teste',
                            datetime(2026, 9, 21, tzinfo=timezone.utc), datetime(2026, 9, 21, tzinfo=timezone.utc))

    class _ConexaoComCorrida(_ConexaoFake):
        def cursor(self):
            self._chamadas_cursor = getattr(self, '_chamadas_cursor', 0) + 1
            if self._chamadas_cursor >= 3:
                self.linha_existente = linha_apos_corrida
            return _CursorFake(self)

    conexao = _ConexaoComCorrida(linha_existente=None, levantar_integrity_error_no_insert=True)
    repo = RepositorioContatoColaboradorPostgres(conexao)

    persistido, criado = repo.criar_ou_confirmar(_registro())

    assert criado is False
    assert persistido.colaborador_id == 'func_1'
    assert conexao.rollbacks == 1


def test_listar_todos_converte_todas_as_linhas():
    linha = ('func_1', CANAL_WHATSAPP, b'token-cifrado', 'hash_a', 'v1', 'teste',
              datetime(2026, 9, 21, tzinfo=timezone.utc), datetime(2026, 9, 21, tzinfo=timezone.utc))
    conexao = _ConexaoFake()
    conexao.linhas_existentes = [linha]
    repo = RepositorioContatoColaboradorPostgres(conexao)

    resultado = repo.listar_todos()

    assert len(resultado) == 1
    assert resultado[0].colaborador_id == 'func_1'
    assert resultado[0].valor_cifrado == b'token-cifrado'
