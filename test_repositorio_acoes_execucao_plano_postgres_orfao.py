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


# =======================================================================
# Gate 3 -- reconciliação humana de ENVIO EXTERNO INCERTO
# (FAILED_FINAL + ultimo_erro_classe=ENVIO_EXTERNO_INCERTO). Dados
# sintéticos; nenhum transporte; nenhum dado pessoal.
# =======================================================================

from magnata_os.orquestrador.autorrecuperacao import DecisaoRecuperacao  # noqa: E402
from magnata_os.orquestrador.politica_comunicacao import hash_conteudo_comunicacao  # noqa: E402
from magnata_os.orquestrador.reconciliacao_execucao_orfa import (  # noqa: E402
    confirmar_envio_incerto_como_enviado,
    liberar_envio_incerto_sem_envio_confirmado,
)
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (  # noqa: E402
    CLASSE_ENVIO_EXTERNO_INCERTO,
    CLASSE_ENVIO_INCERTO_LIBERADO_SEM_ENVIO,
    _linha_para_registro,
)
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria  # noqa: E402


def _linha_incerta(estado='FAILED_FINAL', classe=CLASSE_ENVIO_EXTERNO_INCERTO, attempt=2,
                   claim='claimhash'):
    concluido = AGORA if estado in ('SUCCEEDED', 'FAILED_FINAL') else None
    return (
        'a' * 64, 'evento-1', 'preview-1', 'auth-1', 1, 'texto',
        'dest-hash', None, None, 'texto-hash', 'e' * 64,
        estado, attempt, None, claim, AGORA,
        classe, None, None, AGORA, AGORA, concluido,
    )


def _linha_pos(estado, classe, resultado=None, evidencia=None, concluido=None):
    return (
        'a' * 64, 'evento-1', 'preview-1', 'auth-1', 1, 'texto',
        'dest-hash', None, None, 'texto-hash', 'e' * 64,
        estado, 2, None, 'claimhash', AGORA,
        classe, resultado, evidencia, AGORA, AGORA, concluido,
    )


# Posições dos parâmetros do UPDATE de _reconciliar_envio_incerto.
_P_ESTADO, _P_CLASSE, _P_RESULTADO, _P_EVIDENCIA, _P_ATUALIZADO, _P_CONCLUIDO = range(6)
_P_ID, _P_ESTADO_ESPERADO, _P_CLASSE_ESPERADA, _P_CLAIM, _P_ATTEMPT = range(6, 11)


def test_classe_incerta_e_a_do_classificador():
    from magnata_os.orquestrador.classificador_falha import ClasseFalha
    assert CLASSE_ENVIO_EXTERNO_INCERTO == ClasseFalha.ENVIO_EXTERNO_INCERTO.value
    assert CLASSE_ENVIO_INCERTO_LIBERADO_SEM_ENVIO != CLASSE_ENVIO_EXTERNO_INCERTO


def test_decisoes_de_auditoria_sao_proprias_e_nao_reaproveitam_retry():
    a = DecisaoRecuperacao.RECONCILIACAO_MANUAL_ENVIO_INCERTO_SEM_ENVIO.value
    b = DecisaoRecuperacao.RECONCILIACAO_MANUAL_ENVIO_INCERTO_ENVIADO.value
    assert a != b
    assert {a, b}.isdisjoint({
        DecisaoRecuperacao.RETRY_EXECUTADO.value,
        DecisaoRecuperacao.LIBERACAO_MANUAL_ACAO_SEM_ENVIO.value,
    })


def test_listar_envios_incertos_e_select_filtrado_sem_commit():
    conexao = _Conexao(respostas_all=[[_linha_incerta()]])
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)

    resultado = repo.listar_envios_incertos()

    sql, params = conexao.executados[0]
    assert sql.strip().upper().startswith('SELECT')
    assert params == ('FAILED_FINAL', CLASSE_ENVIO_EXTERNO_INCERTO)
    assert len(resultado) == 1
    assert resultado[0].ultimo_erro_classe == CLASSE_ENVIO_EXTERNO_INCERTO
    assert conexao.commits == 0 and conexao.rollbacks == 0


def test_liberar_envio_incerto_cas_completo_e_auditoria_na_mesma_transacao():
    conexao = _Conexao(respostas_one=[_linha_pos(
        'FAILED_RETRYABLE', CLASSE_ENVIO_INCERTO_LIBERADO_SEM_ENVIO)])
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    acao = _linha_para_registro(_linha_incerta())
    hooks = []

    resultado = repo.liberar_envio_incerto_para_retry(
        acao=acao, atualizado_em=AGORA,
        na_mesma_transacao=lambda cursor: hooks.append(conexao.commits),
    )

    sql, params = conexao.executados[0]
    assert sql.strip().upper().startswith('UPDATE')
    assert 'attempt = attempt' not in sql  # attempt nunca é tocado
    assert params[_P_ESTADO] == 'FAILED_RETRYABLE'
    assert params[_P_CLASSE] == CLASSE_ENVIO_INCERTO_LIBERADO_SEM_ENVIO
    assert params[_P_RESULTADO] is None and params[_P_EVIDENCIA] is None
    assert params[_P_CONCLUIDO] is None  # não-terminal: concluido_em limpo
    assert params[_P_ID] == 'a' * 64
    assert params[_P_ESTADO_ESPERADO] == 'FAILED_FINAL'
    assert params[_P_CLASSE_ESPERADA] == CLASSE_ENVIO_EXTERNO_INCERTO
    assert params[_P_CLAIM] == 'claimhash'
    assert params[_P_ATTEMPT] == 2
    assert hooks == [0]  # auditoria rodou uma vez, ANTES do commit
    assert conexao.commits == 1
    assert resultado.estado == EstadoAcaoExecucaoPlano.FAILED_RETRYABLE


def test_confirmar_envio_incerto_vira_succeeded_com_referencia_e_hash():
    conexao = _Conexao(respostas_one=[_linha_pos('SUCCEEDED', None, 'EXT-1', 'f' * 64, AGORA)])
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    acao = _linha_para_registro(_linha_incerta())

    resultado = repo.confirmar_envio_incerto_enviado(
        acao=acao, atualizado_em=AGORA, resultado_referencia='EXT-1',
        evidencia=b'evidencia-sintetica', na_mesma_transacao=lambda cursor: None,
    )

    _, params = conexao.executados[0]
    assert params[_P_ESTADO] == 'SUCCEEDED'
    assert params[_P_CLASSE] is None
    assert params[_P_RESULTADO] == 'EXT-1'
    assert params[_P_EVIDENCIA] == hash_conteudo_comunicacao(b'evidencia-sintetica')
    assert params[_P_CONCLUIDO] == AGORA
    assert params[_P_ESTADO_ESPERADO] == 'FAILED_FINAL'
    assert params[_P_CLASSE_ESPERADA] == CLASSE_ENVIO_EXTERNO_INCERTO
    assert resultado.estado == EstadoAcaoExecucaoPlano.SUCCEEDED


def test_cas_perdido_nao_roda_auditoria_e_retorna_none():
    conexao = _Conexao(respostas_one=[None])
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    chamadas = []
    resultado = repo.liberar_envio_incerto_para_retry(
        acao=_linha_para_registro(_linha_incerta()), atualizado_em=AGORA,
        na_mesma_transacao=chamadas.append,
    )
    assert resultado is None
    assert chamadas == []


def test_falha_na_auditoria_desfaz_a_mudanca_de_estado():
    conexao = _Conexao(respostas_one=[_linha_pos(
        'FAILED_RETRYABLE', CLASSE_ENVIO_INCERTO_LIBERADO_SEM_ENVIO)])
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)

    def _auditoria_quebrada(cursor):
        raise RuntimeError('auditoria indisponivel')

    with pytest.raises(RuntimeError):
        repo.liberar_envio_incerto_para_retry(
            acao=_linha_para_registro(_linha_incerta()), atualizado_em=AGORA,
            na_mesma_transacao=_auditoria_quebrada,
        )
    assert conexao.commits == 0 and conexao.rollbacks == 1


def test_reconciliacao_incerta_nao_recebe_transporte():
    import inspect
    for funcao in (
        RepositorioAcoesExecucaoPlanoPostgres.liberar_envio_incerto_para_retry,
        RepositorioAcoesExecucaoPlanoPostgres.confirmar_envio_incerto_enviado,
        liberar_envio_incerto_sem_envio_confirmado,
        confirmar_envio_incerto_como_enviado,
    ):
        nomes = set(inspect.signature(funcao).parameters)
        assert not ({'transporte', 'evolution', 'porta_execucao', 'executor'} & nomes)


# ---- Camada de domínio ------------------------------------------------

class _RepoAcoesSemUso:
    """Qualquer chamada é erro: a rejeição tem que acontecer antes."""

    def __getattr__(self, nome):
        raise AssertionError(f'repositório não devia ser chamado: {nome}')


def _kwargs_a(acao, **extra):
    base = dict(
        repositorio_acoes=_RepoAcoesSemUso(),
        repositorio_execucoes=RepositorioExecucoesEmMemoria(),
        acao=acao, ator_referencia='operador:sintetico', motivo='conferido no painel',
        evidencia_ausencia_envio='painel sem registro de envio', instante=AGORA,
    )
    base.update(extra)
    return base


def _kwargs_b(acao, **extra):
    base = dict(
        repositorio_acoes=_RepoAcoesSemUso(),
        repositorio_execucoes=RepositorioExecucoesEmMemoria(),
        acao=acao, ator_referencia='operador:sintetico', motivo='conferido no painel',
        resultado_referencia_externo='EXT-1', evidencia_envio='painel mostra entrega',
        instante=AGORA,
    )
    base.update(extra)
    return base


@pytest.mark.parametrize('estado,classe', [
    ('FAILED_FINAL', 'PERMANENT'),
    ('FAILED_FINAL', 'INVALID_INPUT'),
    ('FAILED_FINAL', 'HUMAN_GATE'),
    ('FAILED_FINAL', 'TRANSIENT'),
    ('FAILED_FINAL', None),
    ('FAILED_FINAL', 'ORFAO_SEM_ENVIO_CONFIRMADO'),
    ('FAILED_FINAL', CLASSE_ENVIO_INCERTO_LIBERADO_SEM_ENVIO),
    ('FAILED_FINAL', 'envio_externo_incerto'),  # sem heurística/normalização
    ('SUCCEEDED', CLASSE_ENVIO_EXTERNO_INCERTO),
    ('PENDING', CLASSE_ENVIO_EXTERNO_INCERTO),
    ('FAILED_RETRYABLE', CLASSE_ENVIO_EXTERNO_INCERTO),
    ('EXECUTING', CLASSE_ENVIO_EXTERNO_INCERTO),
])
def test_dominio_rejeita_tudo_que_nao_e_failed_final_incerto(estado, classe):
    acao = _linha_para_registro(_linha_incerta(estado=estado, classe=classe))
    with pytest.raises(RepositorioAcoesExecucaoPlanoError):
        liberar_envio_incerto_sem_envio_confirmado(**_kwargs_a(acao))
    with pytest.raises(RepositorioAcoesExecucaoPlanoError):
        confirmar_envio_incerto_como_enviado(**_kwargs_b(acao))


@pytest.mark.parametrize('campo', ['ator_referencia', 'motivo', 'evidencia_ausencia_envio'])
def test_dominio_caso_a_exige_campos_humanos(campo):
    acao = _linha_para_registro(_linha_incerta())
    with pytest.raises(RepositorioAcoesExecucaoPlanoError):
        liberar_envio_incerto_sem_envio_confirmado(**_kwargs_a(acao, **{campo: '  '}))


@pytest.mark.parametrize(
    'campo', ['ator_referencia', 'motivo', 'resultado_referencia_externo', 'evidencia_envio'],
)
def test_dominio_caso_b_exige_campos_humanos(campo):
    acao = _linha_para_registro(_linha_incerta())
    with pytest.raises(RepositorioAcoesExecucaoPlanoError):
        confirmar_envio_incerto_como_enviado(**_kwargs_b(acao, **{campo: ''}))


def test_dominio_campos_humanos_sem_default():
    import inspect
    for funcao, campos in (
        (liberar_envio_incerto_sem_envio_confirmado,
         ('ator_referencia', 'motivo', 'evidencia_ausencia_envio')),
        (confirmar_envio_incerto_como_enviado,
         ('ator_referencia', 'motivo', 'resultado_referencia_externo', 'evidencia_envio')),
    ):
        parametros = inspect.signature(funcao).parameters
        for campo in campos:
            assert parametros[campo].default is inspect.Parameter.empty


class _RepoAcoesCas:
    """Simula o CAS: roda o hook de auditoria só se vencer."""

    def __init__(self, vence=True):
        self.vence = vence
        self.chamadas = []

    def _rodar(self, nome, kwargs, retorno):
        self.chamadas.append((nome, kwargs))
        if not self.vence:
            return None
        kwargs['na_mesma_transacao'](object())
        return retorno

    def liberar_envio_incerto_para_retry(self, **kwargs):
        return self._rodar('liberar', kwargs, 'liberada')

    def confirmar_envio_incerto_enviado(self, **kwargs):
        return self._rodar('confirmar', kwargs, 'confirmada')


def test_dominio_caso_a_audita_com_decisao_propria():
    acao = _linha_para_registro(_linha_incerta())
    repo_exec = RepositorioExecucoesEmMemoria()
    repo_acoes = _RepoAcoesCas()

    resultado = liberar_envio_incerto_sem_envio_confirmado(
        **_kwargs_a(acao, repositorio_acoes=repo_acoes, repositorio_execucoes=repo_exec))

    assert resultado == 'liberada'
    assert repo_acoes.chamadas[0][1]['acao'] is acao
    trilha = repo_exec.listar_recuperacoes('evento-1')
    assert len(trilha) == 1
    assert trilha[0].decisao == 'RECONCILIACAO_MANUAL_ENVIO_INCERTO_SEM_ENVIO'
    assert trilha[0].estado_observado == 'FAILED_FINAL'
    assert 'operador:sintetico' in trilha[0].motivo and 'attempt=2' in trilha[0].motivo
    assert trilha[0].evidencia == 'painel sem registro de envio'


def test_dominio_caso_b_audita_com_decisao_propria():
    acao = _linha_para_registro(_linha_incerta())
    repo_exec = RepositorioExecucoesEmMemoria()
    repo_acoes = _RepoAcoesCas()

    resultado = confirmar_envio_incerto_como_enviado(
        **_kwargs_b(acao, repositorio_acoes=repo_acoes, repositorio_execucoes=repo_exec))

    assert resultado == 'confirmada'
    kwargs = repo_acoes.chamadas[0][1]
    assert kwargs['resultado_referencia'] == 'EXT-1'
    assert kwargs['evidencia'] == b'painel mostra entrega'
    trilha = repo_exec.listar_recuperacoes('evento-1')
    assert [r.decisao for r in trilha] == ['RECONCILIACAO_MANUAL_ENVIO_INCERTO_ENVIADO']
    assert 'resultado_referencia=EXT-1' in trilha[0].motivo


def test_dominio_cas_perdido_nao_audita():
    acao = _linha_para_registro(_linha_incerta())
    repo_exec = RepositorioExecucoesEmMemoria()
    assert liberar_envio_incerto_sem_envio_confirmado(**_kwargs_a(
        acao, repositorio_acoes=_RepoAcoesCas(vence=False), repositorio_execucoes=repo_exec,
    )) is None
    assert confirmar_envio_incerto_como_enviado(**_kwargs_b(
        acao, repositorio_acoes=_RepoAcoesCas(vence=False), repositorio_execucoes=repo_exec,
    )) is None
    assert repo_exec.listar_recuperacoes('evento-1') == []


def test_nao_existe_funcao_de_prosseguir_com_incerteza():
    import magnata_os.orquestrador.reconciliacao_execucao_orfa as modulo
    publicas = {
        n for n in dir(modulo) if not n.startswith('_') and callable(getattr(modulo, n))
    }
    proibidas = {
        n for n in publicas
        if any(p in n for p in ('prosseguir', 'forcar', 'ignorar', 'pular'))
    }
    assert proibidas == set()
