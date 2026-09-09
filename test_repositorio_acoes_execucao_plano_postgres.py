"""Contrato das ações persistentes do PlanoDisparo, sempre sem transporte."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from magnata_os.orquestrador.autorizacao_gate import (
    DecisaoGate,
    RegistroAutorizacaoGate,
)
from magnata_os.orquestrador.plano_comunicacao import AcaoEnvio, PlanoDisparo
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoError,
    RepositorioAcoesExecucaoPlanoPostgres,
    criar_registro_acao_plano,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)


def _autorizacao(decisao=DecisaoGate.AUTORIZADO, preview='preview-1'):
    return RegistroAutorizacaoGate(
        autorizacao_id='auth-1', event_id='evento-1', preview_id=preview,
        decisao=decisao, ator_referencia='ator:sintetico', registrado_em=AGORA,
        proveniencia='teste:sintetico',
    )


def _plano(*, preview='preview-1', destinatario='dest:sintetico', conteudo=b'midia-a'):
    acao = AcaoEnvio(
        destinatario=destinatario, ordem=1, tipo='video', nome='video.bin',
        conteudo=conteudo, legenda='legenda sintetica',
    )
    return PlanoDisparo(
        preview_id=preview, destinatarios=(destinatario,), acoes=(acao,),
        mensagens_por_pessoa=1, total_notificacoes=1,
    )


def _registro(**kwargs):
    com_envelope = kwargs.pop('com_envelope', True)
    plano = kwargs.pop('plano', _plano())
    registro = criar_registro_acao_plano(
        event_id='evento-1', plano=plano,
        autorizacao=kwargs.pop('autorizacao', _autorizacao()),
        acao=plano.acoes[0], criado_em=kwargs.pop('criado_em', AGORA),
    )
    return dataclass_replace(
        registro, envelope_sha256=('e' * 64 if com_envelope else None),
    )


def _linha(registro):
    valores = list(registro.__dict__.values())
    valores[11] = registro.estado.value
    return tuple(valores)


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
        return self.conexao.respostas.pop(0)


class _Conexao:
    def __init__(self, respostas=()):
        self.respostas = list(respostas)
        self.executados = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
    def cursor(self):
        return _Cursor(self)
    def commit(self):
        self.commits += 1
    def rollback(self):
        self.rollbacks += 1
    def close(self):
        self.closed = True


def test_identidade_deterministica_e_sem_pii_em_claro():
    primeiro = _registro()
    segundo = _registro(criado_em=AGORA + timedelta(days=1))
    assert primeiro.acao_execucao_id == segundo.acao_execucao_id
    serializado = repr(primeiro)
    assert 'dest:sintetico' not in serializado
    assert 'legenda sintetica' not in serializado
    assert 'midia-a' not in serializado


def test_preview_conteudo_e_destinatario_alteram_identidade():
    base = _registro().acao_execucao_id
    preview = _registro(
        plano=_plano(preview='preview-2'),
        autorizacao=_autorizacao(preview='preview-2'),
    ).acao_execucao_id
    conteudo = _registro(plano=_plano(conteudo=b'midia-b')).acao_execucao_id
    destino = _registro(plano=_plano(destinatario='dest:outro')).acao_execucao_id
    assert len({base, preview, conteudo, destino}) == 4


def test_autorizacao_recusada_e_preview_divergente_bloqueiam():
    with pytest.raises(RepositorioAcoesExecucaoPlanoError, match='recusada'):
        _registro(autorizacao=_autorizacao(DecisaoGate.RECUSADO))
    with pytest.raises(RepositorioAcoesExecucaoPlanoError, match='preview diverge'):
        _registro(autorizacao=_autorizacao(preview='outro'))


def test_materializacao_exige_autorizacao_persistida_exata():
    conexao = _Conexao(respostas=(None, None))
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    with pytest.raises(RepositorioAcoesExecucaoPlanoError, match='nao encontrada'):
        repo.materializar_plano(
            event_id='evento-1', plano=_plano(), autorizacao=_autorizacao(),
            criado_em=AGORA,
        )
    sql = conexao.executados[0][0]
    assert 'ag.decisao = %s' in sql
    assert 'ON CONFLICT (acao_execucao_id) DO NOTHING' in sql
    assert conexao.rollbacks == 1


def test_materializacao_repetida_e_idempotente():
    registro = _registro(com_envelope=False)
    conexao = _Conexao(respostas=(None, _linha(registro)))
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    resultado = repo.materializar_plano(
        event_id='evento-1', plano=_plano(), autorizacao=_autorizacao(),
        criado_em=AGORA,
    )
    assert resultado == (registro,)
    assert conexao.commits == 1


def test_claim_e_cas_atomico_incrementam_attempt():
    executando = dataclass_replace(
        _registro(), estado=EstadoAcaoExecucaoPlano.EXECUTING, attempt=1,
        claim_sha256='0' * 64, reivindicado_em=AGORA,
    )
    conexao = _Conexao(respostas=(_linha(executando),))
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    assert repo.reivindicar_proxima(
        event_id='evento-1', preview_id='preview-1',
        claim_referencia='worker:sintetico', reivindicado_em=AGORA,
    ).attempt == 1
    sql = conexao.executados[0][0]
    assert 'FOR UPDATE SKIP LOCKED LIMIT 1' in sql
    assert 'attempt = attempt + 1' in sql
    assert 'estado IN (%s, %s)' in sql
    assert 'candidata.envelope_sha256 IS NOT NULL' in sql


def test_descoberta_sem_claim_e_claim_exato_excluem_legado_sem_envelope():
    conexao = _Conexao(respostas=(None, None))
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    assert repo.buscar_proxima_elegivel(
        event_id='evento-1', preview_id='preview-1', instante=AGORA,
    ) is None
    assert repo.reivindicar_acao_exata(
        acao_execucao_id='a' * 64, claim_referencia='worker:sintetico',
        reivindicado_em=AGORA,
    ) is None
    busca_sql = conexao.executados[0][0]
    claim_sql = conexao.executados[1][0]
    assert 'envelope_sha256 IS NOT NULL' in busca_sql
    assert 'candidata.acao_execucao_id = %s' in claim_sql
    assert 'a.acao_execucao_id = %s' in claim_sql
    assert 'a.envelope_sha256 IS NOT NULL' in claim_sql
    assert 'FOR UPDATE SKIP LOCKED' in claim_sql


def test_claim_exige_todas_as_anteriores_do_destinatario_succeeded():
    conexao = _Conexao(respostas=(None,))
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    assert repo.reivindicar_proxima(
        event_id='evento-1', preview_id='preview-1',
        claim_referencia='worker:sintetico', reivindicado_em=AGORA,
    ) is None
    sql, parametros = conexao.executados[0]
    assert 'NOT EXISTS (' in sql
    assert 'anterior.event_id = candidata.event_id' in sql
    assert 'anterior.preview_id = candidata.preview_id' in sql
    assert 'anterior.destinatario_sha256 =' in sql
    assert 'candidata.destinatario_sha256' in sql
    assert 'anterior.ordem < candidata.ordem' in sql
    assert 'anterior.estado <> %s' in sql
    assert EstadoAcaoExecucaoPlano.SUCCEEDED.value in parametros


def test_claim_nao_serializa_destinatarios_independentes():
    conexao = _Conexao(respostas=(None,))
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    repo.reivindicar_proxima(
        event_id='evento-1', preview_id='preview-1',
        claim_referencia='worker:sintetico', reivindicado_em=AGORA,
    )
    sql = conexao.executados[0][0]
    predicado = sql[sql.index('AND NOT EXISTS'):sql.index('ORDER BY candidata')]
    assert 'anterior.destinatario_sha256' in predicado
    assert 'anterior.ordem < candidata.ordem' in predicado
    assert 'anterior.event_id = candidata.event_id' in predicado
    assert 'anterior.preview_id = candidata.preview_id' in predicado


def test_sem_elegivel_inclui_sucesso_falha_final_e_executing_orfao():
    conexao = _Conexao(respostas=(None, None, None))
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    for _ in range(3):
        assert repo.reivindicar_proxima(
            event_id='evento-1', preview_id='preview-1',
            claim_referencia='worker:sintetico', reivindicado_em=AGORA,
        ) is None


def test_retry_so_reivindica_estado_e_data_elegiveis():
    conexao = _Conexao(respostas=(None,))
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    assert repo.reivindicar_proxima(
        event_id='evento-1', preview_id='preview-1',
        claim_referencia='worker:sintetico', reivindicado_em=AGORA,
    ) is None
    sql, parametros = conexao.executados[0]
    assert 'proxima_tentativa_em <= %s' in sql
    assert EstadoAcaoExecucaoPlano.FAILED_RETRYABLE.value in parametros


def test_finalizacao_e_cas_do_claim_sem_transporte():
    sucesso = dataclass_replace(
        _registro(), estado=EstadoAcaoExecucaoPlano.SUCCEEDED,
        attempt=1, claim_sha256='0' * 64, reivindicado_em=AGORA,
        concluido_em=AGORA,
    )
    conexao = _Conexao(respostas=(_linha(sucesso),))
    repo = RepositorioAcoesExecucaoPlanoPostgres(conexao)
    assert repo.marcar_sucesso(
        acao_execucao_id=sucesso.acao_execucao_id,
        claim_referencia='worker:sintetico', atualizado_em=AGORA,
        resultado_referencia='resultado:opaco', evidencia=b'evidencia',
    ).estado == EstadoAcaoExecucaoPlano.SUCCEEDED
    sql = conexao.executados[0][0]
    assert 'WHERE acao_execucao_id = %s AND estado = %s' in sql
    assert 'AND claim_sha256 = %s' in sql
    assert 'transporte' not in sql.lower()


def test_migration_e_inerte_minima_e_sem_pii_em_claro():
    caminho = Path(
        'magnata_os/orquestrador/migrations/0003_acoes_execucao_plano.sql'
    )
    sql = caminho.read_text(encoding='utf-8')
    assert 'INERTE' in sql
    assert sql.count('CREATE TABLE ') == 1
    assert 'CREATE TRIGGER' not in sql
    assert 'CREATE FUNCTION' not in sql
    assert "'PENDING', 'EXECUTING', 'SUCCEEDED'" in sql
    assert 'FOREIGN KEY (event_id, preview_id)' in sql
    assert "ag.decisao" not in sql  # gate e validado no INSERT do repositorio
    for proibido in ('telefone', 'destinatario TEXT', 'midia BYTEA', 'texto TEXT'):
        assert proibido not in sql


def test_rollback_e_destrutivo_e_nao_automatico():
    caminho = Path(
        'magnata_os/orquestrador/migrations/'
        '0003_acoes_execucao_plano_rollback.sql'
    )
    sql = caminho.read_text(encoding='utf-8')
    assert 'Destrutivo: nunca executar automaticamente' in sql
    assert 'DROP TABLE magnata_orquestrador.acoes_execucao_plano' in sql
    assert 'CASCADE' not in sql


def dataclass_replace(registro, **mudancas):
    from dataclasses import replace
    return replace(registro, **mudancas)
