"""E2E do executor V1 em Postgres efêmero e storage em memória, sem rede."""
import dataclasses
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

psycopg = pytest.importorskip('psycopg', reason='driver psycopg v3 nao instalado')

from magnata_os.documental.modulo01.armazenamento import (
    ArmazenamentoArquivosEmMemoria,
)
from magnata_os.orquestrador.autorizacao_gate import (
    DecisaoGate,
    RegistroAutorizacaoGate,
)
from magnata_os.orquestrador.envelope_execucao_autorizada import (
    armazenar_acao_e_envelope_v1,
)
from magnata_os.orquestrador.executor_persistente_fake import (
    ResultadoExecucaoPorta,
    executar_proxima_acao_persistente,
)
from magnata_os.orquestrador.plano_comunicacao import AcaoEnvio, PlanoDisparo
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoPostgres,
    criar_registro_acao_plano,
)
from magnata_os.orquestrador.repositorio_autorizacoes_gate_postgres import (
    RepositorioAutorizacoesGatePostgres,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get('MAGNATA_TEST_POSTGRES_REAL'),
    reason='E2E habilitado somente contra PostgreSQL efemero controlado',
)

RAIZ = Path(__file__).parent / 'magnata_os' / 'orquestrador' / 'migrations'
AGORA = datetime(2099, 6, 1, tzinfo=timezone.utc)
EVENTO = 'evento-envelope-executor-real-v1'
PREVIEW = 'preview-envelope-executor-real-v1'
AUTORIZACAO = 'auth-envelope-executor-real-v1'


def _preparar(conn, *, event_id=EVENTO, preview_id=PREVIEW,
              autorizacao_id=AUTORIZACAO):
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
            (event_id, AGORA, AGORA),
        )
        cursor.execute(
            """INSERT INTO magnata_orquestrador.autorizacoes_gate
               (autorizacao_id,event_id,preview_id,decisao,ator_referencia,
                registrado_em,proveniencia)
               VALUES (%s,%s,%s,'AUTORIZADO',%s,%s,%s)
               ON CONFLICT (event_id,preview_id) DO NOTHING""",
            (autorizacao_id, event_id, preview_id, 'ator:sintetico', AGORA,
             'e2e:executor-fake'),
        )
    conn.commit()


def _autorizacao(*, event_id=EVENTO, preview_id=PREVIEW,
                 autorizacao_id=AUTORIZACAO):
    return RegistroAutorizacaoGate(
        autorizacao_id=autorizacao_id, event_id=event_id,
        preview_id=preview_id,
        decisao=DecisaoGate.AUTORIZADO,
        ator_referencia='ator:sintetico', registrado_em=AGORA,
        proveniencia='e2e:executor-fake',
    )


def _materializar(
    conn, armazenamento, *, event_id=EVENTO, preview_id=PREVIEW,
    autorizacao_id=AUTORIZACAO,
):
    acao = AcaoEnvio(
        destinatario='destinatario:sintetico:e2e', ordem=1,
        tipo='documento', nome='documento-sintetico.bin',
        conteudo=b'conteudo-sintetico-e2e', legenda='legenda sintetica e2e',
    )
    plano = PlanoDisparo(
        preview_id=preview_id, destinatarios=(acao.destinatario,), acoes=(acao,),
        mensagens_por_pessoa=1, total_notificacoes=1,
    )
    registro = criar_registro_acao_plano(
        event_id=event_id, plano=plano,
        autorizacao=_autorizacao(
            event_id=event_id, preview_id=preview_id,
            autorizacao_id=autorizacao_id,
        ),
        acao=acao, criado_em=AGORA,
    )
    envelope = armazenar_acao_e_envelope_v1(
        armazenamento=armazenamento, registro=registro, acao=acao,
    )
    registro = dataclasses.replace(registro, envelope_sha256=envelope)
    return RepositorioAcoesExecucaoPlanoPostgres(conn).materializar_registros(
        registros=(registro,), autorizacao=_autorizacao(
            event_id=event_id, preview_id=preview_id,
            autorizacao_id=autorizacao_id,
        ),
    )[0]


class _PortaFake:
    def __init__(self):
        self.acoes = []

    def executar(self, acao):
        self.acoes.append(acao)
        return ResultadoExecucaoPorta('fake:e2e:opaco', b'evidencia-e2e-fake')


def test_e2e_restart_verificacao_claim_exato_fake_checkpoint_e_constraint():
    armazenamento = ArmazenamentoArquivosEmMemoria()
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _preparar(conn)
    registro = _materializar(conn, armazenamento)
    conn.close()

    # Novo adapter/conexao simula restart; o payload vem do storage, nao da RAM
    # do materializador nem de uma copia na tabela operacional.
    reaberta = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    porta = _PortaFake()
    resultado = executar_proxima_acao_persistente(
        repositorio_acoes=RepositorioAcoesExecucaoPlanoPostgres(reaberta),
        repositorio_autorizacoes=RepositorioAutorizacoesGatePostgres(reaberta),
        armazenamento=armazenamento,
        porta_execucao=porta,
        event_id=EVENTO,
        preview_id=PREVIEW,
        claim_referencia='worker:e2e:envelope-v1',
        instante=AGORA,
    )
    assert resultado.situacao == 'SUCCEEDED'
    assert resultado.acao_execucao_id == registro.acao_execucao_id
    assert resultado.registro_final.estado == EstadoAcaoExecucaoPlano.SUCCEEDED
    assert len(porta.acoes) == 1

    # Terminal nunca reaparece e a tabela nao contem os valores claros.
    repetido = executar_proxima_acao_persistente(
        repositorio_acoes=RepositorioAcoesExecucaoPlanoPostgres(reaberta),
        repositorio_autorizacoes=RepositorioAutorizacoesGatePostgres(reaberta),
        armazenamento=armazenamento, porta_execucao=porta,
        event_id=EVENTO, preview_id=PREVIEW,
        claim_referencia='worker:e2e:repetido', instante=AGORA,
    )
    assert repetido.situacao == 'SEM_ACAO_ELEGIVEL'
    assert len(porta.acoes) == 1
    with reaberta.cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_constraintdef(oid) "
            "FROM pg_constraint "
            "WHERE conname='ck_acoes_execucao_plano_envelope_sha256'"
        )
        assert '[0-9a-f]{64}' in cursor.fetchone()[0]
        cursor.execute(
            "SELECT destinatario_sha256,texto_sha256,nome_sha256,"
            "conteudo_sha256,envelope_sha256 "
            "FROM magnata_orquestrador.acoes_execucao_plano "
            "WHERE acao_execucao_id=%s",
            (registro.acao_execucao_id,),
        )
        assert all(len(valor) == 64 for valor in cursor.fetchone())
    reaberta.close()


def test_claim_exato_concorrente_tem_um_unico_vencedor():
    event_id = 'evento-envelope-executor-concorrencia-v1'
    preview_id = 'preview-envelope-executor-concorrencia-v1'
    autorizacao_id = 'auth-envelope-executor-concorrencia-v1'
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _preparar(
        conn, event_id=event_id, preview_id=preview_id,
        autorizacao_id=autorizacao_id,
    )
    armazenamento = ArmazenamentoArquivosEmMemoria()
    registro = _materializar(
        conn, armazenamento, event_id=event_id, preview_id=preview_id,
        autorizacao_id=autorizacao_id,
    )
    assert registro.estado == EstadoAcaoExecucaoPlano.PENDING
    conn.close()

    barreira = threading.Barrier(2)
    resultados = []

    def claim(numero):
        concorrente = psycopg.connect(cursor_factory=psycopg.ClientCursor)
        try:
            barreira.wait()
            resultados.append(
                RepositorioAcoesExecucaoPlanoPostgres(
                    concorrente
                ).reivindicar_acao_exata(
                    acao_execucao_id=registro.acao_execucao_id,
                    claim_referencia=f'worker:concorrente:{numero}',
                    reivindicado_em=AGORA,
                )
            )
        finally:
            concorrente.close()

    threads = [threading.Thread(target=claim, args=(n,)) for n in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    vencedores = [item for item in resultados if item is not None]
    assert len(vencedores) == 1
    assert vencedores[0].attempt == 1
