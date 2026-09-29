"""Falha de um destinatário nunca para a fila inteira (ex.: Davi ok,
Alcione falha, Emileide e Inara ok) -- e nunca é silenciosa."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from magnata_os.orquestrador import ciclo_producao_v1 as ciclo
from magnata_os.orquestrador.executor_persistente_fake import ExecutorAcaoDryRun

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)


class _Cursor:
    def __init__(self, conexao):
        self.conexao = conexao

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.conexao.sql.append(sql)

    def fetchone(self):
        return (True,)


class _Conexao:
    def __init__(self):
        self.sql = []
        self.rollbacks = 0

    def cursor(self):
        return _Cursor(self)

    def rollback(self):
        self.rollbacks += 1


PARES = (("evt-davi", "p"), ("evt-alcione", "p"), ("evt-emileide", "p"), ("evt-inara", "p"))


class _RepoAcoes:
    def __init__(self, conexao):
        pass

    def listar_pares_elegiveis(self, *, instante, limite=200):
        return PARES


class _RepoConclusao:
    def __init__(self, conexao):
        pass

    def listar_acoes_para_observacao(self, *, limite=200):
        return ("acao-observada",)


def test_falha_de_um_destinatario_nao_impede_os_demais_e_ciclo_termina_com_erro(caplog):
    executados, observados, chamadas = [], [], {}

    def executar(*, event_id, **kw):
        chamadas[event_id] = chamadas.get(event_id, 0) + 1
        if event_id == "evt-alcione":
            raise ConnectionError("envelope ilegivel")
        if chamadas[event_id] > 1:
            return SimpleNamespace(acao_execucao_id=None, situacao="SEM_ACAO_ELEGIVEL")
        executados.append(event_id)
        return SimpleNamespace(acao_execucao_id=f"acao-{event_id}", situacao="SUCCEEDED")

    def observar(*, acao_execucao_id, **kw):
        observados.append(acao_execucao_id)
        return "PENDENTE"

    with patch.object(ciclo, "RepositorioAcoesExecucaoPlanoPostgres", _RepoAcoes), \
         patch.object(ciclo, "RepositorioAutorizacoesGatePostgres", lambda c: object()), \
         patch.object(ciclo, "RepositorioConclusaoObrigacaoAssinaturaPostgres", _RepoConclusao), \
         patch.object(ciclo, "executar_proxima_acao_persistente", executar), \
         patch.object(ciclo, "observar_e_registrar_transicao", observar):
        conexao = _Conexao()
        with pytest.raises(ConnectionError):
            ciclo.executar_um_ciclo_producao(
                conexao_postgres=conexao, armazenamento=object(), porta_execucao=ExecutorAcaoDryRun(),
                porta_obrigacao_assinatura=object(), instante=AGORA, claim_referencia="teste",
            )

    assert executados == ["evt-davi", "evt-emileide", "evt-inara"]
    assert observados == ["acao-observada"]  # observador também roda
    assert conexao.rollbacks == 1
    assert any("pg_advisory_unlock" in sql for sql in conexao.sql)
    assert "evt-alcione" in caplog.text and "ConnectionError" in caplog.text
    assert "envelope ilegivel" not in caplog.text  # só a classe, nunca a mensagem


def test_sem_falha_o_ciclo_devolve_resultado_normalmente():
    def executar(*, event_id, **kw):
        return SimpleNamespace(acao_execucao_id=None, situacao="SEM_ACAO_ELEGIVEL")

    with patch.object(ciclo, "RepositorioAcoesExecucaoPlanoPostgres", _RepoAcoes), \
         patch.object(ciclo, "RepositorioAutorizacoesGatePostgres", lambda c: object()), \
         patch.object(ciclo, "RepositorioConclusaoObrigacaoAssinaturaPostgres", _RepoConclusao), \
         patch.object(ciclo, "executar_proxima_acao_persistente", executar), \
         patch.object(ciclo, "observar_e_registrar_transicao", lambda **kw: "PENDENTE"):
        resultado = ciclo.executar_um_ciclo_producao(
            conexao_postgres=_Conexao(), armazenamento=object(), porta_execucao=ExecutorAcaoDryRun(),
            porta_obrigacao_assinatura=object(), instante=AGORA, claim_referencia="teste",
        )

    assert resultado.lock_adquirido and len(resultado.acoes_processadas) == len(PARES)
