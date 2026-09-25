"""E2E PostgreSQL efêmero das ações do plano; nunca executa transporte."""
import dataclasses
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
    criar_registro_acao_plano,
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
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='magnata_orquestrador' "
            "AND table_name='acoes_execucao_plano' "
            "AND column_name='envelope_sha256'"
        )
        if cursor.fetchone() is None:
            cursor.execute(
                (RAIZ / '0004_envelope_execucao_autorizada.sql').read_text()
            )
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


def _materializar_com_envelope(
    repo, *, event_id, plano, autorizacao, criado_em,
):
    registros = tuple(
        dataclasses.replace(
            criar_registro_acao_plano(
                event_id=event_id, plano=plano, autorizacao=autorizacao,
                acao=acao, criado_em=criado_em,
            ),
            envelope_sha256='e' * 64,
        )
        for acao in plano.acoes
    )
    return repo.materializar_registros(
        registros=registros, autorizacao=autorizacao,
    )


def test_e2e_idempotencia_claim_concorrencia_retry_restart_e_terminais():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _preparar(conn)
    repo = RepositorioAcoesExecucaoPlanoPostgres(conn)
    primeira = _materializar_com_envelope(repo,
        event_id='evento-acoes-e2e', plano=_plano(),
        autorizacao=_autorizacao(), criado_em=AGORA,
    )[0]
    segunda = _materializar_com_envelope(repo,
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
        _materializar_com_envelope(repo,
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
    registros = _materializar_com_envelope(repo,
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


# =======================================================================
# Gate 3 -- reconciliação humana de ENVIO EXTERNO INCERTO contra Postgres
# real. Documentos genéricos (DOCUMENTO_A/B), destinatários sintéticos,
# nenhum transporte. Ids únicos por execução.
# =======================================================================

import uuid  # noqa: E402

from magnata_os.orquestrador.reconciliacao_execucao_orfa import (  # noqa: E402
    confirmar_envio_incerto_como_enviado,
    liberar_envio_incerto_sem_envio_confirmado,
)
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (  # noqa: E402
    CLASSE_ENVIO_EXTERNO_INCERTO,
    CLASSE_ENVIO_INCERTO_LIBERADO_SEM_ENVIO,
    RepositorioAcoesExecucaoPlanoError,
)
from magnata_os.orquestrador.repositorio_execucoes_postgres import (  # noqa: E402
    RepositorioExecucoesPostgres,
)

_DECISOES_G3 = (
    'RECONCILIACAO_MANUAL_ENVIO_INCERTO_SEM_ENVIO',
    'RECONCILIACAO_MANUAL_ENVIO_INCERTO_ENVIADO',
)


def _plano_documental(preview_id, destinatarios):
    acoes = tuple(
        AcaoEnvio(
            destinatario=destinatario, ordem=ordem, tipo='documento',
            nome=f'{documento}.bin', conteudo=f'{documento}-sintetico'.encode(),
            legenda=f'legenda {documento}',
        )
        for destinatario in destinatarios
        for ordem, documento in enumerate(('DOCUMENTO_A', 'DOCUMENTO_B'), start=1)
    )
    return PlanoDisparo(
        preview_id=preview_id, destinatarios=destinatarios, acoes=acoes,
        mensagens_por_pessoa=2, total_notificacoes=2 * len(destinatarios),
    )


def _cenario_incerto(conn, rotulo, destinatarios=('dest:A', 'dest:B')):
    """Materializa o plano e leva a ação 1 do primeiro destinatário a
    FAILED_FINAL + ENVIO_EXTERNO_INCERTO pelo caminho real (claim +
    marcar_falha, como o executor faz). Devolve (repo, ids, incerta)."""
    sufixo = uuid.uuid4().hex[:12]
    event_id = f'evento-g3-{rotulo}-{sufixo}'
    preview_id = f'preview-g3-{rotulo}-{sufixo}'
    autorizacao = _preparar_cenario(
        conn, event_id=event_id, preview_id=preview_id,
        autorizacao_id=f'auth-g3-{rotulo}-{sufixo}',
    )
    repo = RepositorioAcoesExecucaoPlanoPostgres(conn)
    plano = _plano_documental(preview_id, destinatarios)
    registros = _materializar_com_envelope(
        repo, event_id=event_id, plano=plano, autorizacao=autorizacao, criado_em=AGORA,
    )
    ids = {
        (acao.destinatario, acao.ordem): criar_registro_acao_plano(
            event_id=event_id, plano=plano, autorizacao=autorizacao,
            acao=acao, criado_em=AGORA,
        ).acao_execucao_id
        for acao in plano.acoes
    }
    assert set(ids.values()) == {r.acao_execucao_id for r in registros}
    ids['__evento__'] = (event_id, preview_id)

    alvo = ids[(destinatarios[0], 1)]
    claim = f'worker:g3:{sufixo}'
    assert repo.reivindicar_acao_exata(
        acao_execucao_id=alvo, claim_referencia=claim, reivindicado_em=AGORA,
    ) is not None
    incerta = repo.marcar_falha(
        acao_execucao_id=alvo, claim_referencia=claim, atualizado_em=AGORA,
        erro_classe=CLASSE_ENVIO_EXTERNO_INCERTO, retentavel=False,
    )
    assert incerta.estado == EstadoAcaoExecucaoPlano.FAILED_FINAL
    assert incerta.concluido_em is not None
    return repo, ids, incerta


def _claim(repo, acao_execucao_id, referencia, quando=AGORA):
    return repo.reivindicar_acao_exata(
        acao_execucao_id=acao_execucao_id, claim_referencia=referencia, reivindicado_em=quando,
    )


def _trilha_g3(conn, event_id):
    return [
        r for r in RepositorioExecucoesPostgres(conn).listar_recuperacoes(event_id)
        if r.decisao in _DECISOES_G3
    ]


def _kwargs_humanos_a():
    return dict(ator_referencia='operador:sintetico', motivo='conferido no painel',
                evidencia_ausencia_envio='painel sem registro de envio')


def _kwargs_humanos_b():
    return dict(ator_referencia='operador:sintetico', motivo='conferido no painel',
                resultado_referencia_externo='EXT-SINTETICO-1',
                evidencia_envio='painel mostra entrega')


def test_g3_incerta_bloqueia_so_o_proprio_destinatario_e_aparece_na_visao():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _preparar(conn)
    repo, ids, incerta = _cenario_incerto(conn, 'visao')

    assert incerta.acao_execucao_id in {r.acao_execucao_id for r in repo.listar_envios_incertos()}
    # Caso C (continua incerto): nada muda -- A2 segue bloqueada, sempre.
    assert _claim(repo, ids[('dest:A', 2)], 'worker:a2') is None
    assert _claim(repo, ids[('dest:A', 2)], 'worker:a2', AGORA + timedelta(days=30)) is None
    # Isolamento por destinatário: B segue normalmente.
    b1 = _claim(repo, ids[('dest:B', 1)], 'worker:b1')
    assert b1 is not None
    assert repo.marcar_sucesso(
        acao_execucao_id=b1.acao_execucao_id, claim_referencia='worker:b1', atualizado_em=AGORA,
    ).estado == EstadoAcaoExecucaoPlano.SUCCEEDED
    assert _claim(repo, ids[('dest:B', 2)], 'worker:b2') is not None
    conn.close()


def test_g3_caso_a_libera_para_retry_atomico_e_mantem_bloqueio_ate_sucesso():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _preparar(conn)
    repo, ids, incerta = _cenario_incerto(conn, 'caso-a')
    event_id = ids['__evento__'][0]

    liberada = liberar_envio_incerto_sem_envio_confirmado(
        repositorio_acoes=repo, repositorio_execucoes=RepositorioExecucoesPostgres(conn),
        acao=incerta, instante=AGORA + timedelta(minutes=5), **_kwargs_humanos_a(),
    )
    assert liberada.estado == EstadoAcaoExecucaoPlano.FAILED_RETRYABLE
    assert liberada.concluido_em is None
    assert liberada.proxima_tentativa_em is None
    assert liberada.attempt == incerta.attempt  # nunca resetado nem incrementado
    assert liberada.ultimo_erro_classe == CLASSE_ENVIO_INCERTO_LIBERADO_SEM_ENVIO
    trilha = _trilha_g3(conn, event_id)
    assert [(r.decisao, r.estado_observado) for r in trilha] == [
        ('RECONCILIACAO_MANUAL_ENVIO_INCERTO_SEM_ENVIO', 'FAILED_FINAL'),
    ]
    assert incerta.acao_execucao_id not in {r.acao_execucao_id for r in repo.listar_envios_incertos()}

    # Mesma decisão repetida com o snapshot antigo: CAS perde, sem nova trilha.
    with pytest.raises(RepositorioAcoesExecucaoPlanoError):
        liberar_envio_incerto_sem_envio_confirmado(
            repositorio_acoes=repo, repositorio_execucoes=RepositorioExecucoesPostgres(conn),
            acao=liberada, instante=AGORA, **_kwargs_humanos_a(),
        )
    assert liberar_envio_incerto_sem_envio_confirmado(
        repositorio_acoes=repo, repositorio_execucoes=RepositorioExecucoesPostgres(conn),
        acao=incerta, instante=AGORA, **_kwargs_humanos_a(),
    ) is None
    assert len(_trilha_g3(conn, event_id)) == 1

    # A2 continua bloqueada enquanto A1 não é SUCCEEDED.
    assert _claim(repo, ids[('dest:A', 2)], 'worker:a2') is None
    retry = _claim(repo, incerta.acao_execucao_id, 'worker:retry')
    assert retry.attempt == incerta.attempt + 1
    assert _claim(repo, ids[('dest:A', 2)], 'worker:a2') is None
    assert repo.marcar_sucesso(
        acao_execucao_id=retry.acao_execucao_id, claim_referencia='worker:retry',
        atualizado_em=AGORA,
    ).estado == EstadoAcaoExecucaoPlano.SUCCEEDED
    # Liberação após sucesso.
    assert _claim(repo, ids[('dest:A', 2)], 'worker:a2') is not None
    conn.close()


def test_g3_caso_a_nova_falha_incerta_volta_a_final_e_limite_fica_humano():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _preparar(conn)
    repo, ids, incerta = _cenario_incerto(conn, 'refalha')
    liberada = liberar_envio_incerto_sem_envio_confirmado(
        repositorio_acoes=repo, repositorio_execucoes=RepositorioExecucoesPostgres(conn),
        acao=incerta, instante=AGORA, **_kwargs_humanos_a(),
    )
    retry = _claim(repo, liberada.acao_execucao_id, 'worker:retry')
    de_novo = repo.marcar_falha(
        acao_execucao_id=retry.acao_execucao_id, claim_referencia='worker:retry',
        atualizado_em=AGORA, erro_classe=CLASSE_ENVIO_EXTERNO_INCERTO, retentavel=False,
    )
    # Volta a FAILED_FINAL; nenhuma nova tentativa sem nova decisão humana.
    assert de_novo.estado == EstadoAcaoExecucaoPlano.FAILED_FINAL
    assert de_novo.attempt == incerta.attempt + 1
    assert _claim(repo, de_novo.acao_execucao_id, 'worker:outro', AGORA + timedelta(days=1)) is None
    # O snapshot antigo (attempt anterior) não serve para reconciliar o novo incidente.
    assert liberar_envio_incerto_sem_envio_confirmado(
        repositorio_acoes=repo, repositorio_execucoes=RepositorioExecucoesPostgres(conn),
        acao=incerta, instante=AGORA, **_kwargs_humanos_a(),
    ) is None
    # Snapshot idêntico ao atual exceto `attempt`: só o attempt derruba o CAS.
    so_attempt_velho = dataclasses.replace(de_novo, attempt=incerta.attempt)
    assert so_attempt_velho.claim_sha256 == de_novo.claim_sha256
    assert confirmar_envio_incerto_como_enviado(
        repositorio_acoes=repo, repositorio_execucoes=RepositorioExecucoesPostgres(conn),
        acao=so_attempt_velho, instante=AGORA, **_kwargs_humanos_b(),
    ) is None
    assert repo.buscar(de_novo.acao_execucao_id).estado == EstadoAcaoExecucaoPlano.FAILED_FINAL
    assert _claim(repo, ids[('dest:A', 2)], 'worker:a2') is None
    conn.close()


def test_g3_caso_b_confirma_enviado_sem_reenvio_e_libera_a_proxima():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _preparar(conn)
    repo, ids, incerta = _cenario_incerto(conn, 'caso-b')
    event_id = ids['__evento__'][0]

    confirmada = confirmar_envio_incerto_como_enviado(
        repositorio_acoes=repo, repositorio_execucoes=RepositorioExecucoesPostgres(conn),
        acao=incerta, instante=AGORA + timedelta(minutes=5), **_kwargs_humanos_b(),
    )
    assert confirmada.estado == EstadoAcaoExecucaoPlano.SUCCEEDED
    assert confirmada.resultado_referencia == 'EXT-SINTETICO-1'
    assert confirmada.evidencia_sha256 is not None and len(confirmada.evidencia_sha256) == 64
    assert confirmada.ultimo_erro_classe is None
    assert confirmada.concluido_em == AGORA + timedelta(minutes=5)
    assert confirmada.attempt == incerta.attempt
    assert [r.decisao for r in _trilha_g3(conn, event_id)] == [
        'RECONCILIACAO_MANUAL_ENVIO_INCERTO_ENVIADO',
    ]
    # Nunca reenvia: a própria ação é terminal e não é reivindicável.
    assert _claim(repo, incerta.acao_execucao_id, 'worker:reenvio') is None
    # A próxima do mesmo destinatário fica elegível naturalmente.
    assert _claim(repo, ids[('dest:A', 2)], 'worker:a2') is not None
    conn.close()


def test_g3_rejeita_failed_final_generico_no_banco_real():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _preparar(conn)
    repo, ids, _ = _cenario_incerto(conn, 'generico')
    b1 = _claim(repo, ids[('dest:B', 1)], 'worker:b1')
    permanente = repo.marcar_falha(
        acao_execucao_id=b1.acao_execucao_id, claim_referencia='worker:b1',
        atualizado_em=AGORA, erro_classe='PERMANENT', retentavel=False,
    )
    for funcao, extras in (
        (liberar_envio_incerto_sem_envio_confirmado, _kwargs_humanos_a()),
        (confirmar_envio_incerto_como_enviado, _kwargs_humanos_b()),
    ):
        with pytest.raises(RepositorioAcoesExecucaoPlanoError):
            funcao(repositorio_acoes=repo,
                   repositorio_execucoes=RepositorioExecucoesPostgres(conn),
                   acao=permanente, instante=AGORA, **extras)
        # Mesmo forjando o snapshot como "incerto", o CAS no banco recusa.
        forjada = dataclasses.replace(permanente, ultimo_erro_classe=CLASSE_ENVIO_EXTERNO_INCERTO)
        assert funcao(repositorio_acoes=repo,
                      repositorio_execucoes=RepositorioExecucoesPostgres(conn),
                      acao=forjada, instante=AGORA, **extras) is None
    atual = repo.buscar(permanente.acao_execucao_id)
    assert (atual.estado, atual.ultimo_erro_classe) == (EstadoAcaoExecucaoPlano.FAILED_FINAL, 'PERMANENT')
    assert _trilha_g3(conn, ids['__evento__'][0]) == []
    conn.close()


def test_g3_decisoes_conflitantes_concorrentes_so_uma_vence():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _preparar(conn)
    repo, ids, incerta = _cenario_incerto(conn, 'corrida')
    event_id = ids['__evento__'][0]
    barreira = threading.Barrier(2)
    resultados = {}
    erros = []

    def decidir(nome, funcao, extras):
        conexao = psycopg.connect(cursor_factory=psycopg.ClientCursor)
        try:
            barreira.wait()
            resultados[nome] = funcao(
                repositorio_acoes=RepositorioAcoesExecucaoPlanoPostgres(conexao),
                repositorio_execucoes=RepositorioExecucoesPostgres(conexao),
                acao=incerta, instante=AGORA, **extras,
            )
        except Exception as exc:  # noqa: BLE001 -- registrado e verificado
            erros.append(exc)
        finally:
            conexao.close()

    threads = [
        threading.Thread(target=decidir, args=(
            'sem_envio', liberar_envio_incerto_sem_envio_confirmado, _kwargs_humanos_a())),
        threading.Thread(target=decidir, args=(
            'enviado', confirmar_envio_incerto_como_enviado, _kwargs_humanos_b())),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert erros == []
    vencedores = {nome: r for nome, r in resultados.items() if r is not None}
    assert len(vencedores) == 1
    (nome, vencedor), = vencedores.items()
    trilha = _trilha_g3(conn, event_id)
    assert len(trilha) == 1  # só o vencedor deixou trilha
    atual = repo.buscar(incerta.acao_execucao_id)
    if nome == 'sem_envio':
        assert atual.estado == EstadoAcaoExecucaoPlano.FAILED_RETRYABLE
        assert atual.concluido_em is None
        assert trilha[0].decisao == 'RECONCILIACAO_MANUAL_ENVIO_INCERTO_SEM_ENVIO'
        assert _claim(repo, ids[('dest:A', 2)], 'worker:a2') is None
    else:
        assert atual.estado == EstadoAcaoExecucaoPlano.SUCCEEDED
        assert trilha[0].decisao == 'RECONCILIACAO_MANUAL_ENVIO_INCERTO_ENVIADO'
        assert _claim(repo, ids[('dest:A', 2)], 'worker:a2') is not None
    conn.close()


def test_g3_isolamento_por_evento_mesmo_destinatario():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _preparar(conn)
    repo, ids_x, _ = _cenario_incerto(conn, 'evento-x', destinatarios=('dest:A',))
    # Outro evento, mesmo destinatário sintético: segue independente.
    sufixo = uuid.uuid4().hex[:12]
    event_y, preview_y = f'evento-g3-y-{sufixo}', f'preview-g3-y-{sufixo}'
    autorizacao_y = _preparar_cenario(
        conn, event_id=event_y, preview_id=preview_y, autorizacao_id=f'auth-g3-y-{sufixo}',
    )
    registros_y = _materializar_com_envelope(
        repo, event_id=event_y, plano=_plano_documental(preview_y, ('dest:A',)),
        autorizacao=autorizacao_y, criado_em=AGORA,
    )
    y1 = next(r for r in registros_y if r.ordem == 1)
    y2 = next(r for r in registros_y if r.ordem == 2)
    assert _claim(repo, y1.acao_execucao_id, 'worker:y1') is not None
    repo.marcar_sucesso(acao_execucao_id=y1.acao_execucao_id, claim_referencia='worker:y1',
                        atualizado_em=AGORA)
    assert _claim(repo, y2.acao_execucao_id, 'worker:y2') is not None
    assert _claim(repo, ids_x[('dest:A', 2)], 'worker:x2') is None
    conn.close()
