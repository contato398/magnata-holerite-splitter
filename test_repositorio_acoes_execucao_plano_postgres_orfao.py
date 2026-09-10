"""Bloqueio EXECUTING órfão: Caso A (liberação manual), Caso C (reconciliação
de envio confirmado) e Caso B (visão somente leitura, nunca decide).

Regra pétrea: worker morto ≠ mensagem não enviada -- nenhuma destas
funções pode ser chamada sem ator/motivo/evidência explícitos, e nenhuma
libera por timeout/idade sozinha.
"""
from datetime import datetime, timedelta, timezone

import pytest

from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoError,
    RepositorioAcoesExecucaoPlanoPostgres,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)
_COLUNAS = 21  # mesmo número de colunas de _COLUNAS_EXECUCAO em produção


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
        return self.conexao.respostas_one.pop(0)

    def fetchall(self):
        return self.conexao.respostas_all.pop(0)


class _Conexao:
    def __init__(self, respostas_one=(), respostas_all=()):
        self.respostas_one = list(respostas_one)
        self.respostas_all = list(respostas_all)
        self.executados = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _linha_executing(acao_execucao_id='a' * 64, claim='claimhash'):
    # Ordem exata de _COLUNAS em repositorio_acoes_execucao_plano_postgres.py
    return (
        acao_execucao_id, 'evento-1', 'preview-1', 'auth-1', 1, 'texto',
        'dest-hash', None, None, 'texto-hash', 'e' * 64,
        EstadoAcaoExecucaoPlano.FAILED_RETRYABLE.value, 1, None, claim, AGORA,
        None, None, None, AGORA, AGORA, None,
    )


# ---- Caso A: liberação manual sem prova de envio -----------------------

def test_liberar_apos_confirmacao_ausencia_envio_faz_cas_por_claim_atual():
    conexao = _Conexao(respostas_one=[_linha_executing()])
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)

    resultado = repo.liberar_apos_confirmacao_ausencia_envio(
        acao_execucao_id='a' * 64, claim_sha256_atual='claimhash', atualizado_em=AGORA,
    )

    sql, params = conexao.executados[0]
    assert 'claim_sha256' in sql
    assert 'claimhash' in params
    assert 'ORFAO_SEM_ENVIO_CONFIRMADO' in params
    assert EstadoAcaoExecucaoPlano.FAILED_RETRYABLE.value in params
    assert resultado is not None
    assert conexao.commits == 1


def test_liberar_apos_confirmacao_ausencia_envio_nunca_vira_succeeded():
    conexao = _Conexao(respostas_one=[_linha_executing()])
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    repo.liberar_apos_confirmacao_ausencia_envio(
        acao_execucao_id='a' * 64, claim_sha256_atual='claimhash', atualizado_em=AGORA,
    )
    _, params = conexao.executados[0]
    assert EstadoAcaoExecucaoPlano.SUCCEEDED.value not in params


def test_liberar_apos_confirmacao_ausencia_envio_cas_perdido_retorna_none():
    conexao = _Conexao(respostas_one=[None])  # UPDATE não afetou linha nenhuma
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    resultado = repo.liberar_apos_confirmacao_ausencia_envio(
        acao_execucao_id='a' * 64, claim_sha256_atual='claim-errado', atualizado_em=AGORA,
    )
    assert resultado is None


# ---- Caso C: reconciliação de envio confirmado -------------------------

def test_reconciliar_envio_confirmado_transiciona_para_succeeded_com_id_externo():
    conexao = _Conexao(respostas_one=[_linha_executing()])
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)

    resultado = repo.reconciliar_envio_confirmado(
        acao_execucao_id='a' * 64, claim_sha256_atual='claimhash',
        atualizado_em=AGORA, resultado_referencia='EVOLUTION-ID-123',
        evidencia=b'evidencia-opaca',
    )

    assert resultado is not None  # CAS bateu (fake devolveu a linha)
    sql, params = conexao.executados[0]
    assert EstadoAcaoExecucaoPlano.SUCCEEDED.value in params
    assert 'EVOLUTION-ID-123' in params


def test_reconciliar_envio_confirmado_nunca_chama_transporte():
    # Este teste documenta o contrato: reconciliar não tem acesso a
    # nenhuma porta de transporte -- é impossível reenviar por construção,
    # já que o método só recebe o repositório de ações.
    import inspect
    assinatura = inspect.signature(
        RepositorioAcoesExecucaoPlanoPostgres.reconciliar_envio_confirmado
    )
    nomes = set(assinatura.parameters)
    assert not ({'transporte', 'evolution', 'porta_execucao'} & nomes)


# ---- Caso B: visão somente leitura, nunca decide -----------------------

def test_listar_em_execucao_suspeitas_nao_altera_nada():
    conexao = _Conexao(respostas_all=[[_linha_executing()]])
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)

    resultado = repo.listar_em_execucao_reivindicadas_antes_de(
        instante_limite=AGORA + timedelta(minutes=15),
    )

    assert len(resultado) == 1
    assert conexao.commits == 0  # SELECT puro, nenhum commit
    assert conexao.rollbacks == 0


def test_listar_em_execucao_suspeitas_e_apenas_select():
    conexao = _Conexao(respostas_all=[[]])
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    repo.listar_em_execucao_reivindicadas_antes_de(instante_limite=AGORA)
    sql, _ = conexao.executados[0]
    assert sql.strip().upper().startswith('SELECT')


# ---- reconciliacao_execucao_orfa.py: exige ator/motivo/evidência -------

def test_liberacao_manual_exige_ator_motivo_e_evidencia_sem_default():
    from magnata_os.orquestrador.reconciliacao_execucao_orfa import (
        liberar_acao_orfa_sem_envio_confirmado,
    )
    import inspect
    assinatura = inspect.signature(liberar_acao_orfa_sem_envio_confirmado)
    for campo in ('ator_referencia', 'motivo', 'evidencia_ausencia_envio'):
        assert assinatura.parameters[campo].default is inspect.Parameter.empty


def test_liberacao_manual_rejeita_ator_vazio():
    from magnata_os.orquestrador.reconciliacao_execucao_orfa import (
        liberar_acao_orfa_sem_envio_confirmado,
    )
    from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
        _linha_para_registro,
    )
    registro = _linha_para_registro(_linha_executing())
    with pytest.raises(RepositorioAcoesExecucaoPlanoError):
        liberar_acao_orfa_sem_envio_confirmado(
            repositorio_acoes=None, repositorio_execucoes=None,
            acao=registro, ator_referencia='   ', motivo='algo',
            evidencia_ausencia_envio='algo', instante=AGORA,
        )


def test_liberacao_manual_registra_auditoria_apos_liberar():
    from magnata_os.orquestrador.reconciliacao_execucao_orfa import (
        liberar_acao_orfa_sem_envio_confirmado,
    )
    from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
        _linha_para_registro,
    )

    registro = _linha_para_registro(_linha_executing())

    class _RepoAcoesFake:
        def liberar_apos_confirmacao_ausencia_envio(self, **kwargs):
            return registro

    class _RepoExecucoesFake:
        def __init__(self):
            self.registrados = []

        def registrar_recuperacao(self, registro_recuperacao):
            self.registrados.append(registro_recuperacao)

    repo_execucoes = _RepoExecucoesFake()
    resultado = liberar_acao_orfa_sem_envio_confirmado(
        repositorio_acoes=_RepoAcoesFake(), repositorio_execucoes=repo_execucoes,
        acao=registro, ator_referencia='rh:joao', motivo='confirmado no painel Evolution',
        evidencia_ausencia_envio='print painel 2026-09-10', instante=AGORA,
    )

    assert resultado is registro
    assert len(repo_execucoes.registrados) == 1
    auditoria = repo_execucoes.registrados[0]
    assert 'rh:joao' in auditoria.motivo
    assert auditoria.decisao == 'LIBERACAO_MANUAL_ACAO_SEM_ENVIO'


def test_liberacao_manual_nao_registra_auditoria_se_cas_falhar():
    from magnata_os.orquestrador.reconciliacao_execucao_orfa import (
        liberar_acao_orfa_sem_envio_confirmado,
    )
    from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
        _linha_para_registro,
    )

    registro = _linha_para_registro(_linha_executing())

    class _RepoAcoesFake:
        def liberar_apos_confirmacao_ausencia_envio(self, **kwargs):
            return None  # CAS perdeu titularidade

    class _RepoExecucoesFake:
        def __init__(self):
            self.registrados = []

        def registrar_recuperacao(self, registro_recuperacao):
            self.registrados.append(registro_recuperacao)

    repo_execucoes = _RepoExecucoesFake()
    resultado = liberar_acao_orfa_sem_envio_confirmado(
        repositorio_acoes=_RepoAcoesFake(), repositorio_execucoes=repo_execucoes,
        acao=registro, ator_referencia='rh:joao', motivo='x', evidencia_ausencia_envio='y',
        instante=AGORA,
    )
    assert resultado is None
    assert repo_execucoes.registrados == []
