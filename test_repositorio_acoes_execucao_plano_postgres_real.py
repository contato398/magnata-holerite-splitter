"""E2E PostgreSQL efêmero das ações do plano; nunca executa transporte."""
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

psycopg = pytest.importorskip('psycopg', reason='driver psycopg v3 nao instalado')

from magnata_os.orquestrador.autorizacao_gate import DecisaoGate, RegistroAutorizacaoGate
from magnata_os.orquestrador.plano_comunicacao import AcaoEnvio, PlanoDisparo
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoPostgres,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get('MAGNATA_TEST_POSTGRES_REAL'),
    reason='E2E habilitado somente contra PostgreSQL efemero controlado',
)

RAIZ = Path(__file__).parent / 'magnata_os' / 'orquestrador' / 'migrations'
AGORA = datetime(2099, 2, 1, tzinfo=timezone.utc)


def _preparar(conn):
    with conn.cursor() as cursor:
        cursor.execute("SELECT to_regclass('magnata_orquestrador.execucoes')")
        if cursor.fetchone()[0] is None:
            cursor.execute((RAIZ / '0001_repositorio_execucoes.sql').read_text())
        cursor.execute("SELECT to_regclass('magnata_orquestrador.autorizacoes_gate')")
        if cursor.fetchone()[0] is None:
            cursor.execute((RAIZ / '0002_autorizacoes_gate.sql').read_text())
        cursor.execute("SELECT to_regclass('magnata_orquestrador.acoes_execucao_plano')")
        if cursor.fetchone()[0] is None:
            cursor.execute((RAIZ / '0003_acoes_execucao_plano.sql').read_text())
        cursor.execute(
            """INSERT INTO magnata_orquestrador.execucoes
               (event_id,event_type,estado,nivel_autonomia,acao,attempt,
                criado_em,atualizado_em)
               VALUES (%s,'COMUNICACAO_SOLICITADA','WAITING_GATE',0,'',0,%s,%s)
               ON CONFLICT (event_id) DO NOTHING""",
            ('evento-acoes-e2e', AGORA, AGORA),
        )
        cursor.execute(
            """INSERT INTO magnata_orquestrador.autorizacoes_gate
               (autorizacao_id,event_id,preview_id,decisao,ator_referencia,
                registrado_em,proveniencia)
               VALUES (%s,%s,%s,'AUTORIZADO',%s,%s,%s)
               ON CONFLICT (event_id,preview_id) DO NOTHING""",
            ('auth-acoes-e2e', 'evento-acoes-e2e', 'preview-acoes-e2e',
             'ator:sintetico', AGORA, 'e2e:efemero'),
        )
    conn.commit()


def _autorizacao():
    return RegistroAutorizacaoGate(
        autorizacao_id='auth-acoes-e2e', event_id='evento-acoes-e2e',
        preview_id='preview-acoes-e2e', decisao=DecisaoGate.AUTORIZADO,
        ator_referencia='ator:sintetico', registrado_em=AGORA,
        proveniencia='e2e:efemero',
    )


def _plano():
    acao = AcaoEnvio(
        destinatario='destinatario:sintetico', ordem=1, tipo='video',
        nome='midia-sintetica.bin', conteudo=b'conteudo-sintetico',
        legenda='texto sintetico',
    )
    return PlanoDisparo(
        preview_id='preview-acoes-e2e',
        destinatarios=('destinatario:sintetico',), acoes=(acao,),
        mensagens_por_pessoa=1, total_notificacoes=1,
    )


def test_e2e_idempotencia_claim_concorrencia_retry_restart_e_terminais():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _preparar(conn)
    repo = RepositorioAcoesExecucaoPlanoPostgres(conn)
    primeira = repo.materializar_plano(
        event_id='evento-acoes-e2e', plano=_plano(),
        autorizacao=_autorizacao(), criado_em=AGORA,
    )[0]
    segunda = repo.materializar_plano(
        event_id='evento-acoes-e2e', plano=_plano(),
        autorizacao=_autorizacao(), criado_em=AGORA + timedelta(minutes=1),
    )[0]
    assert primeira.acao_execucao_id == segunda.acao_execucao_id
    assert segunda.estado == EstadoAcaoExecucaoPlano.PENDING

    resultados = []
    barreira = threading.Barrier(2)

    def reivindicar(numero):
        conexao = psycopg.connect(cursor_factory=psycopg.ClientCursor)
        try:
            barreira.wait()
            resultado = RepositorioAcoesExecucaoPlanoPostgres(conexao).reivindicar_proxima(
                event_id='evento-acoes-e2e', preview_id='preview-acoes-e2e',
                claim_referencia=f'worker:{numero}', reivindicado_em=AGORA,
            )
            resultados.append(resultado)
        finally:
            conexao.close()

    threads = [threading.Thread(target=reivindicar, args=(i,)) for i in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    vencedores = [r for r in resultados if r is not None]
    assert len(vencedores) == 1
    assert vencedores[0].attempt == 1

    # EXECUTING órfão sobrevive ao restart e nunca é reivindicado de novo.
    conn.close()
    reaberta = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    repo = RepositorioAcoesExecucaoPlanoPostgres(reaberta)
    persistida = repo.buscar(primeira.acao_execucao_id)
    assert persistida.estado == EstadoAcaoExecucaoPlano.EXECUTING
    assert repo.reivindicar_proxima(
        event_id='evento-acoes-e2e', preview_id='preview-acoes-e2e',
        claim_referencia='worker:recuperacao', reivindicado_em=AGORA,
    ) is None

    # Somente o claim vencedor pode marcar retry; retry incrementa attempt.
    # Descobre de forma opaca qual referência ganhou, sem persistir o valor.
    for candidato in ('worker:1', 'worker:2'):
        falha = repo.marcar_falha(
            acao_execucao_id=primeira.acao_execucao_id,
            claim_referencia=candidato, atualizado_em=AGORA,
            erro_classe='FalhaSintetica', retentavel=True,
            proxima_tentativa_em=AGORA,
        )
        if falha is not None:
            break
    assert falha.estado == EstadoAcaoExecucaoPlano.FAILED_RETRYABLE
    retry = repo.reivindicar_proxima(
        event_id='evento-acoes-e2e', preview_id='preview-acoes-e2e',
        claim_referencia='worker:retry', reivindicado_em=AGORA,
    )
    assert retry.attempt == 2
    sucesso = repo.marcar_sucesso(
        acao_execucao_id=retry.acao_execucao_id,
        claim_referencia='worker:retry', atualizado_em=AGORA,
        resultado_referencia='resultado:opaco', evidencia=b'evidencia-sintetica',
    )
    assert sucesso.estado == EstadoAcaoExecucaoPlano.SUCCEEDED
    assert repo.reivindicar_proxima(
        event_id='evento-acoes-e2e', preview_id='preview-acoes-e2e',
        claim_referencia='worker:terminal', reivindicado_em=AGORA,
    ) is None

    with reaberta.cursor() as cursor:
        cursor.execute(
            'SELECT destinatario_sha256,texto_sha256,conteudo_sha256,estado,attempt '
            'FROM magnata_orquestrador.acoes_execucao_plano '
            'WHERE acao_execucao_id=%s', (primeira.acao_execucao_id,),
        )
        destino_hash, texto_hash, conteudo_hash, estado, attempt = cursor.fetchone()
    assert len(destino_hash) == len(texto_hash) == len(conteudo_hash) == 64
    assert estado == 'SUCCEEDED'
    assert attempt == 2
    reaberta.close()


def test_autorizacao_ausente_nao_persiste_acao():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _preparar(conn)
    repo = RepositorioAcoesExecucaoPlanoPostgres(conn)
    ausente = RegistroAutorizacaoGate(
        autorizacao_id='auth-inexistente', event_id='evento-acoes-e2e',
        preview_id='preview-acoes-e2e', decisao=DecisaoGate.AUTORIZADO,
        ator_referencia='ator:sintetico', registrado_em=AGORA,
        proveniencia='e2e:efemero',
    )
    with pytest.raises(ValueError, match='nao encontrada'):
        repo.materializar_plano(
            event_id='evento-acoes-e2e', plano=_plano(),
            autorizacao=ausente, criado_em=AGORA,
        )
    conn.close()
