"""E2E Postgres real/efêmero: persistência real das ações do plano
autorizado via a composição completa Prestação -> Orquestrador. Nunca
executa transporte.

Roda somente com ``MAGNATA_TEST_POSTGRES_REAL``. Reutiliza as migrations
canônicas 0001/0002/0003 e nunca executa rollback, DELETE ou DROP. Os
registros são sintéticos, determinísticos, não sensíveis e idempotentes.
"""
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

psycopg = pytest.importorskip('psycopg', reason='driver psycopg (v3) nao instalado')

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.pacote_prestacao import (
    EstadoPacotePrestacao,
    PacotePrestacaoCliente,
)
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.documental.modulo01.armazenamento import (
    ArmazenamentoArquivosEmMemoria,
)
from magnata_os.orquestrador.plano_comunicacao import ConteudoItem
from magnata_os.orquestrador.politica_comunicacao import (
    ItemComunicacao,
    hash_conteudo_comunicacao,
    montar_preview_comunicacao,
)
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoPostgres,
)
from magnata_os.orquestrador.wiring_prestacao_orquestrador_postgres_shadow import (
    materializar_prestacao_orquestrador_persistente_postgres_shadow,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get('MAGNATA_TEST_POSTGRES_REAL'),
    reason='E2E habilitado somente contra PostgreSQL real e controlado',
)

_RAIZ = Path(__file__).parent / 'magnata_os' / 'orquestrador' / 'migrations'
_MIGRATIONS = tuple(
    (_RAIZ / nome).read_text(encoding='utf-8')
    for nome in (
        '0001_repositorio_execucoes.sql',
        '0002_autorizacoes_gate.sql',
        '0003_acoes_execucao_plano.sql',
        '0004_envelope_execucao_autorizada.sql',
    )
)
_INSTANTE = datetime(2099, 3, 1, 12, 0, tzinfo=timezone.utc)
_TEXTO = 'E2E sintético da persistência real do executor do Orquestrador.'
_MIDIA = b'e2e-persistencia-midia-sintetica-v1'
_DESTINATARIO = 'destinatario:e2e:persistencia:sintetico'


def _aplicar_migrations_se_ausentes(conn):
    with conn.cursor() as cursor:
        for nome_tabela, migration in zip(
            ('execucoes', 'autorizacoes_gate', 'acoes_execucao_plano'),
            _MIGRATIONS[:3],
        ):
            cursor.execute(
                "SELECT to_regclass(%s)",
                (f'magnata_orquestrador.{nome_tabela}',),
            )
            if cursor.fetchone()[0] is None:
                cursor.execute(migration)
        cursor.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='magnata_orquestrador' "
            "AND table_name='acoes_execucao_plano' "
            "AND column_name='envelope_sha256'"
        )
        if cursor.fetchone() is None:
            cursor.execute(_MIGRATIONS[3])
    conn.commit()


def _pacote():
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-e2e-persistencia-sintetico')
    competencia = ReferenciaCanonica('COMPETENCIA', '2099-01')
    return PacotePrestacaoCliente(
        cliente=cliente,
        competencia=competencia,
        estado=EstadoPacotePrestacao.PRONTO,
        itens_incluidos=(ItemInventarioPrestacao(
            documento_id='documento-e2e-persistencia-sintetico',
            tipo_documental='DOCUMENTO_SINTETICO',
            cliente=cliente,
            competencia=competencia,
        ),),
        tipos_obrigatorios=('DOCUMENTO_SINTETICO',),
    )


def _kwargs():
    item = ItemComunicacao(
        'documento', 'e2e-persistencia-sintetico.bin',
        hash_conteudo_comunicacao(_MIDIA),
    )
    preview = montar_preview_comunicacao(
        destinatarios=(_DESTINATARIO,), texto=_TEXTO, itens=(item,),
        assinatura=False, comprovante=True,
    )
    return dict(
        pacote=_pacote(),
        destinatarios=(_DESTINATARIO,),
        texto=_TEXTO,
        itens=(item,),
        conteudos=(ConteudoItem('documento', 'e2e-persistencia-sintetico.bin', _MIDIA),),
        assinatura=False,
        comprovante=True,
        preview_id_autorizado=preview.preview_id,
        ator_referencia='ator:e2e:persistencia:sintetico',
        proveniencia_autorizacao='e2e_persistencia_shadow_v1',
        instante=_INSTANTE,
    )


def test_e2e_persistencia_real_idempotente_e_sem_transporte():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    armazenamento = ArmazenamentoArquivosEmMemoria()
    try:
        _aplicar_migrations_se_ausentes(conn)

        primeiro = materializar_prestacao_orquestrador_persistente_postgres_shadow(
            conexao_postgres=conn, armazenamento=armazenamento, **_kwargs(),
        )
        segundo = materializar_prestacao_orquestrador_persistente_postgres_shadow(
            conexao_postgres=conn, armazenamento=armazenamento, **_kwargs(),
        )

        assert len(primeiro.acoes) == 1
        assert primeiro.acoes[0].acao_execucao_id == segundo.acoes[0].acao_execucao_id
        assert primeiro.acoes[0].estado == EstadoAcaoExecucaoPlano.PENDING
        assert armazenamento.existe(primeiro.acoes[0].envelope_sha256)

        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM magnata_orquestrador.acoes_execucao_plano '
                'WHERE acao_execucao_id = %s',
                (primeiro.acoes[0].acao_execucao_id,),
            )
            (quantidade,) = cursor.fetchone()
        assert quantidade == 1  # reaplicacao nao duplicou a linha

        # A persistência recém-criada é utilizável pelo mesmo repositório
        # já testado isoladamente -- claim funciona sobre uma linha nascida
        # do caminho real de composição, não só de INSERT sintético de teste.
        repo = RepositorioAcoesExecucaoPlanoPostgres(conn)
        reivindicada = repo.reivindicar_proxima(
            event_id=primeiro.intencao.execucao.event_id,
            preview_id=primeiro.autorizacao.preview_id,
            claim_referencia='worker:e2e:persistencia',
            reivindicado_em=_INSTANTE,
        )
        assert reivindicada.acao_execucao_id == primeiro.acoes[0].acao_execucao_id
        assert reivindicada.estado == EstadoAcaoExecucaoPlano.EXECUTING
        finalizada = repo.marcar_sucesso(
            acao_execucao_id=reivindicada.acao_execucao_id,
            claim_referencia='worker:e2e:persistencia',
            atualizado_em=_INSTANTE,
        )
        assert finalizada.estado == EstadoAcaoExecucaoPlano.SUCCEEDED
    finally:
        conn.close()
