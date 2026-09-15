"""Testes do script one-shot do canário nominal (Incremento 3, missão
"IMPLEMENTAÇÃO LOCAL CONTROLADA — EXTRAÇÃO EVOLUTION + CANÁRIO NOMINAL
V1"). Nenhuma rede real -- todas as dependências (Postgres, storage,
portas, assinatura) são dublês em memória."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from magnata_os.orquestrador import executar_canario_v1 as canario
from magnata_os.orquestrador.executor_persistente_fake import ResultadoCicloExecutorPersistente

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)
EVENT_ID = 'event-canario-1'
PREVIEW_ID = 'preview-canario-1'


def _resultado(situacao, acao_execucao_id='acao-1'):
    return ResultadoCicloExecutorPersistente(situacao, acao_execucao_id, None)


class _RepoAcoesFakeSemListarPares:
    """Deliberadamente SEM `listar_pares_elegiveis` -- se
    `executar_canario_nominal` chamar esse método por engano, o teste
    falha com AttributeError, prova mais forte que só verificar
    "não foi chamado"."""

    def __init__(self, conexao):
        self.conexao = conexao


class _RepoAutorizacoesFake:
    def __init__(self, conexao):
        self.conexao = conexao


class _RepoConclusaoFake:
    def __init__(self, conexao):
        self.conexao = conexao


def _patches(executar_mock, observar_mock=None):
    return (
        patch.object(canario, 'RepositorioAcoesExecucaoPlanoPostgres', _RepoAcoesFakeSemListarPares),
        patch.object(canario, 'RepositorioAutorizacoesGatePostgres', _RepoAutorizacoesFake),
        patch.object(canario, 'RepositorioConclusaoObrigacaoAssinaturaPostgres', _RepoConclusaoFake),
        patch.object(canario, 'executar_proxima_acao_persistente', executar_mock),
        patch.object(canario, 'observar_e_registrar_transicao', observar_mock),
    )


def _observar_noop(**kw):
    return 'CONCLUIDO'


def _rodar(executar_mock, observar_mock=_observar_noop, event_id=EVENT_ID, preview_id=PREVIEW_ID, limite_acoes=5):
    patches = _patches(executar_mock, observar_mock)
    for p in patches:
        p.start()
    try:
        return canario.executar_canario_nominal(
            event_id=event_id, preview_id=preview_id,
            conexao_postgres=object(), armazenamento=object(),
            porta_execucao=object(), porta_obrigacao_assinatura=object(),
            instante=AGORA, claim_referencia='canario-teste', limite_acoes=limite_acoes,
        )
    finally:
        for p in patches:
            p.stop()


# ---------------------------------------------------------------------
# Import isolado
# ---------------------------------------------------------------------

def test_import_isolado_nunca_inicializa_flask_airtable_sessao():
    modulos_antes = set(sys.modules)
    import importlib
    importlib.reload(canario)
    modulos_depois = set(sys.modules)
    novos = modulos_depois - modulos_antes
    assert 'flask' not in novos
    assert 'app' not in novos


# ---------------------------------------------------------------------
# Placeholders/IDs ausentes -- fail closed
# ---------------------------------------------------------------------

def test_event_id_ausente_falha_fechado():
    with pytest.raises(canario.CanarioNaoConfiguradoError):
        _rodar(executar_mock=lambda **kw: pytest.fail('nunca deveria ser chamado'), event_id='')


def test_preview_id_ausente_falha_fechado():
    with pytest.raises(canario.CanarioNaoConfiguradoError):
        _rodar(executar_mock=lambda **kw: pytest.fail('nunca deveria ser chamado'), preview_id='')


def test_main_falha_fechado_enquanto_placeholders_sao_none():
    assert canario.EVENT_ID_CANARIO_NOMINAL is None
    assert canario.PREVIEW_ID_CANARIO_NOMINAL is None
    with pytest.raises(canario.CanarioNaoConfiguradoError):
        canario.main()


# ---------------------------------------------------------------------
# Nunca processa par diferente / nunca lista pares elegíveis
# ---------------------------------------------------------------------

def test_sempre_usa_o_mesmo_par_nominal_em_toda_chamada():
    pares_vistos = []

    def _executar(**kw):
        pares_vistos.append((kw['event_id'], kw['preview_id']))
        return _resultado('SEM_ACAO_ELEGIVEL')

    _rodar(executar_mock=_executar)
    assert pares_vistos == [(EVENT_ID, PREVIEW_ID)]


def test_nunca_chama_listar_pares_elegiveis():
    # _RepoAcoesFakeSemListarPares não define o método -- se
    # executar_canario_nominal tentasse chamá-lo, levantaria
    # AttributeError, nunca silenciosamente ignorado.
    _rodar(executar_mock=lambda **kw: _resultado('SEM_ACAO_ELEGIVEL'))


# ---------------------------------------------------------------------
# Múltiplas ações do mesmo par -- ordem e limite
# ---------------------------------------------------------------------

def test_multiplas_acoes_processadas_ate_sem_acao_elegivel():
    chamadas = {'n': 0}
    sequencia = [_resultado('SUCCEEDED', 'acao-1'), _resultado('SUCCEEDED', 'acao-2'), _resultado('SEM_ACAO_ELEGIVEL', None)]

    def _executar(**kw):
        resultado = sequencia[chamadas['n']]
        chamadas['n'] += 1
        return resultado

    resultado = _rodar(executar_mock=_executar)
    assert chamadas['n'] == 3
    assert [r.situacao for r in resultado.acoes_processadas] == ['SUCCEEDED', 'SUCCEEDED', 'SEM_ACAO_ELEGIVEL']
    assert resultado.todas_sucedidas is True


def test_limite_de_acoes_e_respeitado_mesmo_sem_sem_acao_elegivel():
    chamadas = {'n': 0}

    def _executar(**kw):
        chamadas['n'] += 1
        return _resultado('SUCCEEDED', f'acao-{chamadas["n"]}')

    resultado = _rodar(executar_mock=_executar, limite_acoes=3)
    assert chamadas['n'] == 3
    assert len(resultado.acoes_processadas) == 3
    # Achado MÉDIO do Ultrareview multiagente (Agente D): bater no limite
    # sem nunca ver SEM_ACAO_ELEGIVEL deixa incerto se há ação pendente
    # não processada -- por isso NUNCA pode contar como "todas sucedidas",
    # mesmo que toda ação tentada até aqui tenha sido SUCCEEDED. Este
    # assert faltava; sem ele, uma regressão que trocasse a condição por
    # `all(r.situacao == 'SUCCEEDED' for r in resultado.acoes_processadas)`
    # (sem exigir o término via SEM_ACAO_ELEGIVEL) passaria despercebida.
    assert resultado.todas_sucedidas is False


# ---------------------------------------------------------------------
# ENVIO_EXTERNO_INCERTO (FAILED_FINAL) -- interrompe sem retry
# ---------------------------------------------------------------------

def test_falha_final_interrompe_imediatamente_sem_retry():
    chamadas = {'n': 0}

    def _executar(**kw):
        chamadas['n'] += 1
        return _resultado('FAILED_FINAL', 'acao-incerta')

    resultado = _rodar(executar_mock=_executar)
    assert chamadas['n'] == 1  # nunca uma segunda tentativa
    assert resultado.todas_sucedidas is False


def test_claim_perdido_interrompe_sem_continuar():
    chamadas = {'n': 0}

    def _executar(**kw):
        chamadas['n'] += 1
        return _resultado('CLAIM_PERDIDO', 'acao-x')

    resultado = _rodar(executar_mock=_executar)
    assert chamadas['n'] == 1
    assert resultado.todas_sucedidas is False


# ---------------------------------------------------------------------
# Observador nunca roda prematuramente
# ---------------------------------------------------------------------

def test_observador_nao_roda_se_alguma_acao_falhou():
    chamado = {'vezes': 0}

    def _observar(**kw):
        chamado['vezes'] += 1
        return 'CONCLUIDO'

    def _executar(**kw):
        return _resultado('FAILED_FINAL', 'acao-incerta')

    resultado = _rodar(executar_mock=_executar, observar_mock=_observar)
    assert chamado['vezes'] == 0
    assert resultado.observacao is None


def test_observador_nao_roda_se_nenhuma_acao_foi_processada():
    def _observar(**kw):
        pytest.fail('nunca deveria ser chamado sem nenhuma acao processada')

    def _executar(**kw):
        return _resultado('SEM_ACAO_ELEGIVEL', None)

    resultado = _rodar(executar_mock=_executar, observar_mock=_observar)
    assert resultado.todas_sucedidas is False
    assert resultado.observacao is None


def test_observador_roda_somente_apos_todas_as_acoes_sucedidas():
    chamado = {'vezes': 0, 'acao_execucao_id': None}

    def _observar(*, porta_assinatura, repositorio_conclusao, acao_execucao_id, instante):
        chamado['vezes'] += 1
        chamado['acao_execucao_id'] = acao_execucao_id
        return 'CONCLUIDO'

    sequencia = [_resultado('SUCCEEDED', 'acao-1'), _resultado('SEM_ACAO_ELEGIVEL', None)]
    chamadas = {'n': 0}

    def _executar(**kw):
        resultado = sequencia[chamadas['n']]
        chamadas['n'] += 1
        return resultado

    resultado = _rodar(executar_mock=_executar, observar_mock=_observar)
    assert chamado['vezes'] == 1
    assert chamado['acao_execucao_id'] == 'acao-1'
    assert resultado.observacao == ('acao-1', 'CONCLUIDO')
