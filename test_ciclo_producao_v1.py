"""Ciclo único de produção -- lock, composição fake-vs-real, ordem
sequencial executor->observador, tolerância a falha e ausência de PII no
log. Todas as dependências (Postgres, storage, portas) são fakes/mocks --
nenhum efeito real, nenhuma rede, nenhuma credencial.
"""
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from magnata_os.orquestrador import ciclo_producao_v1 as ciclo
from magnata_os.orquestrador.executor_persistente_fake import (
    ExecutorAcaoDryRun,
    ResultadoCicloExecutorPersistente,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)


class _CursorLock:
    def __init__(self, conexao):
        self.conexao = conexao
        self._ultimo = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.conexao.chamadas.append((sql, params))
        if 'pg_try_advisory_lock' in sql:
            self._ultimo = (self.conexao.lock_adquirido,)
        elif 'pg_advisory_unlock' in sql:
            self._ultimo = None

    def fetchone(self):
        return self._ultimo


class _ConexaoLock:
    """Fake mínimo -- só entende as duas queries de advisory lock. Os
    repositórios reais nunca são instanciados nestes testes (são
    substituídos por fakes), então esta conexão nunca precisa entender
    nenhuma outra SQL."""

    def __init__(self, lock_adquirido=True):
        self.lock_adquirido = lock_adquirido
        self.chamadas = []

    def cursor(self):
        return _CursorLock(self)


class _RepoAcoesFake:
    """Substitui `RepositorioAcoesExecucaoPlanoPostgres` inteiro -- os
    testes deste módulo validam composição/orquestração, não a SQL do
    repositório (isso já é validado em
    test_repositorio_acoes_execucao_plano_postgres_descoberta.py)."""

    def __init__(self, conexao):
        self.conexao = conexao

    pares = ()
    succeeded = ()

    def listar_pares_elegiveis(self, *, instante, limite=200):
        return self.pares

    def listar_succeeded_recentes(self, *, limite=200):
        return self.succeeded


def _fabrica_repo_acoes(pares=(), succeeded=()):
    class _Repo(_RepoAcoesFake):
        pass
    _Repo.pares = pares
    _Repo.succeeded = succeeded
    return _Repo


class _RepoAutorizacoesFake:
    def __init__(self, conexao):
        self.conexao = conexao


class _RepoConclusaoFake:
    def __init__(self, conexao):
        self.conexao = conexao


def _patches(repo_acoes_cls, executar_mock=None, observar_mock=None):
    """Contexto único com todos os pontos de composição substituídos."""
    return (
        patch.object(ciclo, 'RepositorioAcoesExecucaoPlanoPostgres', repo_acoes_cls),
        patch.object(ciclo, 'RepositorioAutorizacoesGatePostgres', _RepoAutorizacoesFake),
        patch.object(ciclo, 'RepositorioConclusaoObrigacaoAssinaturaPostgres', _RepoConclusaoFake),
        patch.object(ciclo, 'executar_proxima_acao_persistente', executar_mock),
        patch.object(ciclo, 'observar_e_registrar_transicao', observar_mock),
    )


def _entrar(patches):
    for p in patches:
        p.start()


def _sair(patches):
    for p in patches:
        p.stop()


# ---------------------------------------------------------------------
# Lock
# ---------------------------------------------------------------------

def test_lock_negado_nao_processa_nada():
    conexao = _ConexaoLock(lock_adquirido=False)
    chamado = {'n': 0}

    def _executar(**kw):
        chamado['n'] += 1
        raise AssertionError('não deve ser chamado sem o lock')

    patches = _patches(_fabrica_repo_acoes(), executar_mock=_executar, observar_mock=None)
    _entrar(patches)
    try:
        resultado = ciclo.executar_um_ciclo_producao(
            conexao_postgres=conexao,
            armazenamento=object(),
            porta_execucao=ExecutorAcaoDryRun(),
            porta_obrigacao_assinatura=object(),
            instante=AGORA,
            claim_referencia='ciclo-teste',
        )
    finally:
        _sair(patches)

    assert resultado.lock_adquirido is False
    assert resultado.acoes_processadas == ()
    assert resultado.observacoes == ()
    assert chamado['n'] == 0
    # nunca tenta liberar um lock que nunca adquiriu
    assert not any('pg_advisory_unlock' in sql for sql, _ in conexao.chamadas)


def test_lock_adquirido_e_sempre_liberado_mesmo_sem_pares():
    conexao = _ConexaoLock(lock_adquirido=True)
    patches = _patches(_fabrica_repo_acoes(pares=(), succeeded=()))
    _entrar(patches)
    try:
        resultado = ciclo.executar_um_ciclo_producao(
            conexao_postgres=conexao,
            armazenamento=object(),
            porta_execucao=ExecutorAcaoDryRun(),
            porta_obrigacao_assinatura=object(),
            instante=AGORA,
            claim_referencia='ciclo-teste',
        )
    finally:
        _sair(patches)

    assert resultado.lock_adquirido is True
    assert any('pg_advisory_unlock' in sql for sql, _ in conexao.chamadas)


def test_lock_e_liberado_mesmo_quando_o_executor_lanca_falha_postgres():
    """Falha do Postgres/repos durante o processamento nunca deve deixar
    o lock preso -- crash/restart depende disso."""
    conexao = _ConexaoLock(lock_adquirido=True)

    def _executar(**kw):
        raise RuntimeError('conexão Postgres perdida no meio do ciclo')

    patches = _patches(
        _fabrica_repo_acoes(pares=(('evt-1', 'prev-1'),)),
        executar_mock=_executar,
    )
    _entrar(patches)
    try:
        with pytest.raises(RuntimeError):
            ciclo.executar_um_ciclo_producao(
                conexao_postgres=conexao,
                armazenamento=object(),
                porta_execucao=ExecutorAcaoDryRun(),
                porta_obrigacao_assinatura=object(),
                instante=AGORA,
                claim_referencia='ciclo-teste',
            )
    finally:
        _sair(patches)

    assert any('pg_advisory_unlock' in sql for sql, _ in conexao.chamadas)


def test_lock_e_liberado_mesmo_quando_storage_falha():
    """Falha de storage (S3) durante a recuperação do envelope propaga
    através de `executar_proxima_acao_persistente` -- mesma garantia de
    liberação de lock, nunca mascarada como sucesso."""
    conexao = _ConexaoLock(lock_adquirido=True)

    def _executar(**kw):
        raise ConnectionError('S3 indisponível')

    patches = _patches(
        _fabrica_repo_acoes(pares=(('evt-1', 'prev-1'),)),
        executar_mock=_executar,
    )
    _entrar(patches)
    try:
        with pytest.raises(ConnectionError):
            ciclo.executar_um_ciclo_producao(
                conexao_postgres=conexao,
                armazenamento=object(),
                porta_execucao=ExecutorAcaoDryRun(),
                porta_obrigacao_assinatura=object(),
                instante=AGORA,
                claim_referencia='ciclo-teste',
            )
    finally:
        _sair(patches)

    assert any('pg_advisory_unlock' in sql for sql, _ in conexao.chamadas)


# ---------------------------------------------------------------------
# Sequência executor -> observador
# ---------------------------------------------------------------------

def test_observador_roda_estritamente_depois_do_executor():
    ordem = []

    def _executar(*, event_id, preview_id, **kw):
        ordem.append(('EXEC', event_id))
        return ResultadoCicloExecutorPersistente('SEM_ACAO_ELEGIVEL', None, None)

    def _observar(*, acao_execucao_id, **kw):
        ordem.append(('OBS', acao_execucao_id))
        return 'CONCLUIDO'

    succeeded = (
        SimpleNamespace(acao_execucao_id='a' * 64),
        SimpleNamespace(acao_execucao_id='b' * 64),
    )
    conexao = _ConexaoLock(lock_adquirido=True)
    patches = _patches(
        _fabrica_repo_acoes(pares=(('evt-1', 'p1'), ('evt-2', 'p2')), succeeded=succeeded),
        executar_mock=_executar,
        observar_mock=_observar,
    )
    _entrar(patches)
    try:
        resultado = ciclo.executar_um_ciclo_producao(
            conexao_postgres=conexao,
            armazenamento=object(),
            porta_execucao=ExecutorAcaoDryRun(),
            porta_obrigacao_assinatura=object(),
            instante=AGORA,
            claim_referencia='ciclo-teste',
        )
    finally:
        _sair(patches)

    indices_exec = [i for i, (tipo, _) in enumerate(ordem) if tipo == 'EXEC']
    indices_obs = [i for i, (tipo, _) in enumerate(ordem) if tipo == 'OBS']
    assert indices_exec and indices_obs
    assert max(indices_exec) < min(indices_obs)
    assert resultado.observacoes == (('a' * 64, 'CONCLUIDO'), ('b' * 64, 'CONCLUIDO'))


def test_para_no_primeiro_sem_acao_elegivel_por_par():
    chamadas_por_par = {'evt-1': 0}

    def _executar(*, event_id, preview_id, **kw):
        chamadas_por_par[event_id] += 1
        return ResultadoCicloExecutorPersistente('SEM_ACAO_ELEGIVEL', None, None)

    conexao = _ConexaoLock(lock_adquirido=True)
    patches = _patches(
        _fabrica_repo_acoes(pares=(('evt-1', 'p1'),)),
        executar_mock=_executar,
    )
    _entrar(patches)
    try:
        ciclo.executar_um_ciclo_producao(
            conexao_postgres=conexao,
            armazenamento=object(),
            porta_execucao=ExecutorAcaoDryRun(),
            porta_obrigacao_assinatura=object(),
            instante=AGORA,
            claim_referencia='ciclo-teste',
        )
    finally:
        _sair(patches)

    assert chamadas_por_par['evt-1'] == 1


def test_respeita_max_acoes_por_par():
    contagem = {'n': 0}

    def _executar(**kw):
        contagem['n'] += 1
        return ResultadoCicloExecutorPersistente('SUCCEEDED', 'x' * 64, None)

    conexao = _ConexaoLock(lock_adquirido=True)
    patches = _patches(
        _fabrica_repo_acoes(pares=(('evt-1', 'p1'),)),
        executar_mock=_executar,
    )
    _entrar(patches)
    try:
        ciclo.executar_um_ciclo_producao(
            conexao_postgres=conexao,
            armazenamento=object(),
            porta_execucao=ExecutorAcaoDryRun(),
            porta_obrigacao_assinatura=object(),
            instante=AGORA,
            claim_referencia='ciclo-teste',
            max_acoes_por_par=3,
        )
    finally:
        _sair(patches)

    assert contagem['n'] == 3


# ---------------------------------------------------------------------
# Falha do observador nunca é silenciosa nem falsa
# ---------------------------------------------------------------------

def test_falha_do_observador_nao_propaga_e_nao_registra_falso_estado():
    def _executar(**kw):
        return ResultadoCicloExecutorPersistente('SEM_ACAO_ELEGIVEL', None, None)

    chamados = []

    def _observar(*, acao_execucao_id, **kw):
        chamados.append(acao_execucao_id)
        raise RuntimeError('Airtable fora do ar')

    succeeded = (SimpleNamespace(acao_execucao_id='c' * 64),)
    conexao = _ConexaoLock(lock_adquirido=True)
    patches = _patches(
        _fabrica_repo_acoes(pares=(), succeeded=succeeded),
        executar_mock=_executar,
        observar_mock=_observar,
    )
    _entrar(patches)
    try:
        resultado = ciclo.executar_um_ciclo_producao(
            conexao_postgres=conexao,
            armazenamento=object(),
            porta_execucao=ExecutorAcaoDryRun(),
            porta_obrigacao_assinatura=object(),
            instante=AGORA,
            claim_referencia='ciclo-teste',
        )
    finally:
        _sair(patches)

    # não propagou (o ciclo inteiro não falha por causa de uma obrigação)
    assert resultado.lock_adquirido is True
    # não registrou nenhum estado -- nem verdadeiro nem falso -- para a
    # ação cujo observador falhou; permanece elegível no próximo ciclo
    assert resultado.observacoes == ()
    assert chamados == ['c' * 64]


# ---------------------------------------------------------------------
# Ausência de PII no log estruturado
# ---------------------------------------------------------------------

def test_logging_do_ciclo_nao_contem_pii(caplog):
    def _executar(**kw):
        # registro_final carregaria, em produção, um envelope opaco --
        # nunca telefone/CPF/nome; aqui simulamos um valor de PII para
        # provar que o ciclo NUNCA formata esse campo no log.
        registro_com_pii = SimpleNamespace(telefone='+5511999999999', cpf='11122233344')
        return ResultadoCicloExecutorPersistente('SUCCEEDED', 'd' * 64, registro_com_pii)

    conexao = _ConexaoLock(lock_adquirido=True)
    patches = _patches(
        _fabrica_repo_acoes(pares=(('evt-1', 'p1'),), succeeded=()),
        executar_mock=_executar,
    )
    _entrar(patches)
    try:
        with caplog.at_level(logging.INFO, logger='magnata_os.orquestrador.ciclo_producao_v1'):
            ciclo.executar_um_ciclo_producao(
                conexao_postgres=conexao,
                armazenamento=object(),
                porta_execucao=ExecutorAcaoDryRun(),
                porta_obrigacao_assinatura=object(),
                instante=AGORA,
                claim_referencia='ciclo-teste',
                max_acoes_por_par=1,
            )
    finally:
        _sair(patches)

    texto_completo = '\n'.join(rec.getMessage() for rec in caplog.records)
    assert '+5511999999999' not in texto_completo
    assert '11122233344' not in texto_completo


# ---------------------------------------------------------------------
# Composição fake-vs-real (nenhuma chamada Evolution com barreira fechada)
# ---------------------------------------------------------------------

def test_compor_porta_execucao_e_dry_run_por_padrao():
    porta = ciclo.compor_porta_execucao()
    assert isinstance(porta, ExecutorAcaoDryRun)


def test_compor_porta_execucao_e_dry_run_mesmo_com_transporte_evolution_informado():
    """Ter um `transporte_evolution` disponível não basta -- sem as três
    barreiras abertas, o transporte real nunca é composto."""
    porta = ciclo.compor_porta_execucao(
        autorizar_transporte_real=False, transporte_evolution=object(),
    )
    assert isinstance(porta, ExecutorAcaoDryRun)


def test_compor_porta_execucao_exige_transporte_evolution_quando_real_habilitado():
    with patch.object(ciclo, 'transporte_real_habilitado', return_value=True):
        with pytest.raises(ValueError):
            ciclo.compor_porta_execucao(autorizar_transporte_real=True, transporte_evolution=None)


def test_compor_porta_execucao_retorna_evolution_legado_apenas_com_as_tres_barreiras():
    transporte_fake = object()
    with patch.object(ciclo, 'transporte_real_habilitado', return_value=True), \
         patch('magnata_os.orquestrador.adapters.executor_evolution_legado.ExecutorEvolutionLegado') as _Cls:
        instancia_fake = object()
        _Cls.return_value = instancia_fake
        porta = ciclo.compor_porta_execucao(
            autorizar_transporte_real=True, transporte_evolution=transporte_fake,
        )
    assert porta is instancia_fake
    _Cls.assert_called_once_with(transporte=transporte_fake)


def test_compor_porta_execucao_default_do_parametro_e_false_literal():
    import inspect
    assinatura = inspect.signature(ciclo.compor_porta_execucao)
    assert assinatura.parameters['autorizar_transporte_real'].default is False


# ---------------------------------------------------------------------
# Composição a partir do ambiente (entrypoint do Cron Job) -- fail-closed
# por ausência de configuração, nunca um default inventado.
# ---------------------------------------------------------------------

def test_compor_armazenamento_a_partir_do_ambiente_falha_sem_bucket():
    with patch.dict('os.environ', {}, clear=False):
        import os as _os
        _os.environ.pop('ORQUESTRADOR_S3_BUCKET', None)
        with pytest.raises(RuntimeError):
            ciclo._compor_armazenamento_a_partir_do_ambiente()


def test_compor_obrigacao_assinatura_a_partir_do_ambiente_falha_sem_config():
    with patch.dict('os.environ', {}, clear=False):
        import os as _os
        _os.environ.pop('ORQUESTRADOR_ASSINATURA_BASE_URL', None)
        _os.environ.pop('ORQUESTRADOR_ASSINATURA_API_KEY', None)
        with pytest.raises(RuntimeError):
            ciclo._compor_obrigacao_assinatura_a_partir_do_ambiente()


def test_main_nunca_autoriza_transporte_real_por_configuracao():
    """Prova estática: `main()` chama `compor_porta_execucao` com o
    literal `autorizar_transporte_real=False` -- nunca lido de variável
    de ambiente neste entrypoint (barreira 1 é sempre código, nunca
    configuração de deploy)."""
    import inspect
    codigo_fonte = inspect.getsource(ciclo.main)
    assert 'compor_porta_execucao(autorizar_transporte_real=False)' in codigo_fonte
