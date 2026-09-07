"""Testes de scripts/verificar_credencial_worker_postgres.py.

Nenhum teste aqui abre conexao real nem le DATABASE_URL do ambiente --
`abrir_conexao_fn` e sempre um fake injetado (mesma disciplina de
magnata_os/documental/modulo01/adapters/conexao.py).
"""

from scripts.verificar_credencial_worker_postgres import (
    ProvaCredencialFalhou,
    verificar_credencial,
)


class _CursorFalso:
    def __init__(self, respostas):
        self._respostas = list(respostas)
        self.fechado = False

    def execute(self, sql):
        self._proxima = self._respostas.pop(0)

    def fetchone(self):
        return self._proxima

    def close(self):
        self.fechado = True


class _ConexaoFalsa:
    def __init__(self, respostas):
        self._cursor = _CursorFalso(respostas)
        self.rollback_chamado = False
        self.close_chamado = False

    def cursor(self):
        return self._cursor

    def rollback(self):
        self.rollback_chamado = True

    def close(self):
        self.close_chamado = True


def _fabrica_conexao(respostas):
    conexao = _ConexaoFalsa(respostas)

    def abrir_conexao_fn():
        return conexao

    return abrir_conexao_fn, conexao


def test_prova_completa_quando_banco_e_usuario_conferem():
    abrir_conexao_fn, conexao = _fabrica_conexao(
        [("magnata_os", "magnata_worker_rot2"), (1,)]
    )

    relatorio = verificar_credencial(
        banco_esperado="magnata_os",
        usuario_esperado="magnata_worker_rot2",
        abrir_conexao_fn=abrir_conexao_fn,
    )

    assert relatorio["prova_completa"] is True
    assert relatorio["current_database"] == "magnata_os"
    assert relatorio["current_user"] == "magnata_worker_rot2"
    assert relatorio["select_1_ok"] is True
    # somente leitura -- nunca deixa transacao aberta nem conexao pendurada
    assert conexao.rollback_chamado is True
    assert conexao.close_chamado is True


def test_falha_quando_usuario_e_o_antigo_revogado():
    abrir_conexao_fn, _ = _fabrica_conexao([("magnata_os", "magnata_os"), (1,)])

    try:
        verificar_credencial(
            banco_esperado="magnata_os",
            usuario_esperado="magnata_worker_rot2",
            abrir_conexao_fn=abrir_conexao_fn,
        )
        assert False, "deveria ter levantado ProvaCredencialFalhou"
    except ProvaCredencialFalhou as exc:
        mensagem = str(exc)
        assert "magnata_os" in mensagem
        assert "magnata_worker_rot2" in mensagem


def test_falha_quando_banco_nao_confere():
    abrir_conexao_fn, _ = _fabrica_conexao(
        [("outro_banco", "magnata_worker_rot2"), (1,)]
    )

    try:
        verificar_credencial(
            banco_esperado="magnata_os",
            usuario_esperado="magnata_worker_rot2",
            abrir_conexao_fn=abrir_conexao_fn,
        )
        assert False, "deveria ter levantado ProvaCredencialFalhou"
    except ProvaCredencialFalhou:
        pass


def test_nunca_expoe_database_url_no_relatorio():
    abrir_conexao_fn, _ = _fabrica_conexao(
        [("magnata_os", "magnata_worker_rot2"), (1,)]
    )

    relatorio = verificar_credencial(
        banco_esperado="magnata_os",
        usuario_esperado="magnata_worker_rot2",
        abrir_conexao_fn=abrir_conexao_fn,
    )

    assert "database_url" not in {chave.lower() for chave in relatorio}
    assert all("postgres://" not in str(valor) for valor in relatorio.values())
