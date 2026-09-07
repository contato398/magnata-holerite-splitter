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


def _preparar_cenario(conn, *, event_id, preview_id, autorizacao_id):
    with conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO magnata_orquestrador.execucoes
               (event_id,event_type,estado,nivel_autonomia,acao,attempt,
                criado_em,atualizado_em)
               VALUES (%s,'COMUNICACAO_SOLICITADA','WAITING_GATE',0,'',0,%s,%s)""",
            (event_id, AGORA, AGORA),
        )
        cursor.execute(
            """INSERT INTO magnata_orquestrador.autorizacoes_gate
               (autorizacao_id,event_id,preview_id,decisao,ator_referencia,
                registrado_em,proveniencia)
               VALUES (%s,%s,%s,'AUTORIZADO',%s,%s,%s)""",
            (autorizacao_id, event_id, preview_id, 'ator:sintetico',
             AGORA, 'e2e:ordenacao-efemero'),
        )
    conn.commit()
    return RegistroAutorizacaoGate(
        autorizacao_id=autorizacao_id, event_id=event_id,
        preview_id=preview_id, decisao=DecisaoGate.AUTORIZADO,
        ator_referencia='ator:sintetico', registrado_em=AGORA,
        proveniencia='e2e:ordenacao-efemero',
    )


def _plano_ordenado(preview_id, destinatarios=('dest:A', 'dest:B'), passos=3):
    acoes = tuple(
        AcaoEnvio(
            destinatario=destinatario, ordem=ordem, tipo='video',
            nome=f'midia-{ordem}.bin',
            conteudo=f'conteudo-{ordem}'.encode(),
            legenda=f'legenda-{ordem}',
        )
        for destinatario in destinatarios
        for ordem in range(1, passos + 1)
    )
    return PlanoDisparo(
        preview_id=preview_id, destinatarios=destinatarios, acoes=acoes,
        mensagens_por_pessoa=passos,
        total_notificacoes=len(destinatarios) * passos,
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


def test_ordem_por_destinatario_retry_restart_e_concorrencia_segura():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _preparar(conn)
    event_id = 'evento-ordem-destinatario-e2e'
    preview_id = 'preview-ordem-destinatario-e2e'
    autorizacao = _preparar_cenario(
        conn, event_id=event_id, preview_id=preview_id,
        autorizacao_id='auth-ordem-destinatario-e2e',
    )
    plano = _plano_ordenado(preview_id)
    repo = RepositorioAcoesExecucaoPlanoPostgres(conn)
    registros = repo.materializar_plano(
        event_id=event_id, plano=plano, autorizacao=autorizacao,
        criado_em=AGORA,
    )
    por_id = {registro.acao_execucao_id: registro for registro in registros}

    # Dois claims simultâneos vencem em destinatários diferentes, ambos ordem 1.
    resultados = []
    barreira = threading.Barrier(2)

    def reivindicar(numero):
        conexao = psycopg.connect(cursor_factory=psycopg.ClientCursor)
        try:
            barreira.wait()
            resultado = RepositorioAcoesExecucaoPlanoPostgres(
                conexao
            ).reivindicar_proxima(
                event_id=event_id, preview_id=preview_id,
                claim_referencia=f'worker:ordem:{numero}',
                reivindicado_em=AGORA,
            )
            resultados.append((numero, resultado))
        finally:
            conexao.close()

    threads = [threading.Thread(target=reivindicar, args=(i,)) for i in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    vencedores = [(numero, item) for numero, item in resultados if item is not None]
    assert len(vencedores) == 2
    assert {item.ordem for _, item in vencedores} == {1}
    assert len({item.destinatario_sha256 for _, item in vencedores}) == 2
    assert {item.attempt for _, item in vencedores} == {1}

    numero_a, a1 = vencedores[0]
    numero_b, b1 = vencedores[1]

    # A1 EXECUTING e B1 EXECUTING bloqueiam A2/B2; SKIP LOCKED não ultrapassa.
    assert repo.reivindicar_proxima(
        event_id=event_id, preview_id=preview_id,
        claim_referencia='worker:nao-ultrapassa', reivindicado_em=AGORA,
    ) is None

    # Retry futuro de A1 continua bloqueando A2; B1 concluída libera só B2.
    futuro = AGORA + timedelta(hours=1)
    falha_a1 = repo.marcar_falha(
        acao_execucao_id=a1.acao_execucao_id,
        claim_referencia=f'worker:ordem:{numero_a}', atualizado_em=AGORA,
        erro_classe='FalhaSintetica', retentavel=True,
        proxima_tentativa_em=futuro,
    )
    assert falha_a1.estado == EstadoAcaoExecucaoPlano.FAILED_RETRYABLE
    assert repo.marcar_sucesso(
        acao_execucao_id=b1.acao_execucao_id,
        claim_referencia=f'worker:ordem:{numero_b}', atualizado_em=AGORA,
    ).estado == EstadoAcaoExecucaoPlano.SUCCEEDED
    b2 = repo.reivindicar_proxima(
        event_id=event_id, preview_id=preview_id,
        claim_referencia='worker:b2', reivindicado_em=AGORA,
    )
    assert b2.destinatario_sha256 == b1.destinatario_sha256
    assert b2.ordem == 2
    assert repo.marcar_sucesso(
        acao_execucao_id=b2.acao_execucao_id,
        claim_referencia='worker:b2', atualizado_em=AGORA,
    ).estado == EstadoAcaoExecucaoPlano.SUCCEEDED

    # Restart conserva A1 em retry futuro e não libera A2; B3 segue independente.
    conn.close()
    reaberta = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    repo = RepositorioAcoesExecucaoPlanoPostgres(reaberta)
    b3 = repo.reivindicar_proxima(
        event_id=event_id, preview_id=preview_id,
        claim_referencia='worker:b3', reivindicado_em=AGORA,
    )
    assert b3.destinatario_sha256 == b1.destinatario_sha256
    assert b3.ordem == 3
    assert repo.marcar_sucesso(
        acao_execucao_id=b3.acao_execucao_id,
        claim_referencia='worker:b3', atualizado_em=AGORA,
    ).estado == EstadoAcaoExecucaoPlano.SUCCEEDED
    assert repo.reivindicar_proxima(
        event_id=event_id, preview_id=preview_id,
        claim_referencia='worker:antes-retry', reivindicado_em=AGORA,
    ) is None

    # Ao vencer o prazo, A1 é obrigatoriamente reivindicada antes de A2.
    retry_a1 = repo.reivindicar_proxima(
        event_id=event_id, preview_id=preview_id,
        claim_referencia='worker:retry-a1', reivindicado_em=futuro,
    )
    assert retry_a1.acao_execucao_id == a1.acao_execucao_id
    assert retry_a1.attempt == 2
    assert repo.reivindicar_proxima(
        event_id=event_id, preview_id=preview_id,
        claim_referencia='worker:nao-pula-retry', reivindicado_em=futuro,
    ) is None
    assert repo.marcar_sucesso(
        acao_execucao_id=retry_a1.acao_execucao_id,
        claim_referencia='worker:retry-a1', atualizado_em=futuro,
    ).estado == EstadoAcaoExecucaoPlano.SUCCEEDED
    a2 = repo.reivindicar_proxima(
        event_id=event_id, preview_id=preview_id,
        claim_referencia='worker:a2', reivindicado_em=futuro,
    )
    assert a2.destinatario_sha256 == a1.destinatario_sha256
    assert a2.ordem == 2

    # Falha final de A2 é terminal e bloqueia A3 definitivamente.
    assert repo.marcar_falha(
        acao_execucao_id=a2.acao_execucao_id,
        claim_referencia='worker:a2', atualizado_em=futuro,
        erro_classe='FalhaFinalSintetica', retentavel=False,
    ).estado == EstadoAcaoExecucaoPlano.FAILED_FINAL
    assert repo.reivindicar_proxima(
        event_id=event_id, preview_id=preview_id,
        claim_referencia='worker:a3-bloqueado',
        reivindicado_em=futuro + timedelta(days=1),
    ) is None

    with reaberta.cursor() as cursor:
        cursor.execute(
            """SELECT ordem, estado, attempt
                 FROM magnata_orquestrador.acoes_execucao_plano
                WHERE event_id = %s AND destinatario_sha256 = %s
                ORDER BY ordem""",
            (event_id, a1.destinatario_sha256),
        )
        sequencia_a = cursor.fetchall()
    assert sequencia_a == [
        (1, 'SUCCEEDED', 2),
        (2, 'FAILED_FINAL', 1),
        (3, 'PENDING', 0),
    ]
    assert all(registro.acao_execucao_id in por_id for registro in registros)
    reaberta.close()
