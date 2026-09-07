"""E2E Postgres real/efêmero da composição shadow, sem transporte.

Roda somente com ``MAGNATA_TEST_POSTGRES_REAL``. Reutiliza as migrations
canônicas 0001/0002 e nunca executa rollback, DELETE ou DROP. Os registros são
sintéticos, determinísticos, não sensíveis e idempotentes.
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
from magnata_os.orquestrador.eventos import EstadoExecucao
from magnata_os.orquestrador.plano_comunicacao import ConteudoItem
from magnata_os.orquestrador.politica_comunicacao import (
    ItemComunicacao,
    hash_conteudo_comunicacao,
    montar_preview_comunicacao,
)
from magnata_os.orquestrador.wiring_prestacao_orquestrador_postgres_shadow import (
    materializar_prestacao_orquestrador_postgres_shadow,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get('MAGNATA_TEST_POSTGRES_REAL'),
    reason='E2E habilitado somente contra PostgreSQL real e controlado',
)

_RAIZ = Path(__file__).parent / 'magnata_os' / 'orquestrador' / 'migrations'
_MIGRATIONS = tuple(
    (_RAIZ / nome).read_text(encoding='utf-8')
    for nome in ('0001_repositorio_execucoes.sql', '0002_autorizacoes_gate.sql')
)
_INSTANTE = datetime(2099, 1, 1, 12, 0, tzinfo=timezone.utc)
_TEXTO = 'E2E sintético do Orquestrador Postgres shadow.'
_MIDIA = b'e2e-postgres-midia-sintetica-v1'
_DESTINATARIO = 'destinatario:e2e:sintetico'


def _aplicar_migrations(conn):
    with conn.cursor() as cursor:
        for migration in _MIGRATIONS:
            cursor.execute(migration)
    conn.commit()


def _pacote():
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-e2e-sintetico')
    competencia = ReferenciaCanonica('COMPETENCIA', '2099-01')
    return PacotePrestacaoCliente(
        cliente=cliente,
        competencia=competencia,
        estado=EstadoPacotePrestacao.PRONTO,
        itens_incluidos=(ItemInventarioPrestacao(
            documento_id='documento-e2e-sintetico',
            tipo_documental='DOCUMENTO_SINTETICO',
            cliente=cliente,
            competencia=competencia,
        ),),
        tipos_obrigatorios=('DOCUMENTO_SINTETICO',),
    )


def _kwargs():
    item = ItemComunicacao(
        'documento', 'e2e-sintetico.bin', hash_conteudo_comunicacao(_MIDIA),
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
        conteudos=(ConteudoItem('documento', 'e2e-sintetico.bin', _MIDIA),),
        assinatura=False,
        comprovante=True,
        preview_id_autorizado=preview.preview_id,
        ator_referencia='ator:e2e:sintetico',
        proveniencia_autorizacao='e2e_postgres_shadow_v1',
        instante=_INSTANTE,
    )


def test_e2e_prestacao_postgres_waiting_gate_autorizacao_plano_stop():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    try:
        _aplicar_migrations(conn)
        primeiro = materializar_prestacao_orquestrador_postgres_shadow(
            conexao_postgres=conn, **_kwargs(),
        )
        segundo = materializar_prestacao_orquestrador_postgres_shadow(
            conexao_postgres=conn, **_kwargs(),
        )

        event_id = primeiro.intencao.execucao.event_id
        preview_id = primeiro.intencao.intencao.preview.preview_id
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT estado, attempt, acao, evento_json '
                'FROM magnata_orquestrador.execucoes WHERE event_id = %s',
                (event_id,),
            )
            estado, attempt, acao, envelope = cursor.fetchone()
            cursor.execute(
                'SELECT COUNT(*), MIN(decisao) '
                'FROM magnata_orquestrador.autorizacoes_gate '
                'WHERE event_id = %s AND preview_id = %s',
                (event_id, preview_id),
            )
            quantidade_autorizacoes, decisao = cursor.fetchone()

        assert primeiro.intencao.execucao.event_id == segundo.intencao.execucao.event_id
        assert primeiro.autorizacao == segundo.autorizacao
        assert estado == EstadoExecucao.WAITING_GATE.value
        assert attempt == 0
        assert acao == ''
        assert quantidade_autorizacoes == 1
        assert decisao == 'AUTORIZADO'
        assert primeiro.plano.plano == segundo.plano.plano
        assert primeiro.plano.plano.acoes[0].conteudo == _MIDIA
        for dado in (_DESTINATARIO, _TEXTO, _MIDIA.decode(), 'ator:e2e:sintetico'):
            assert dado not in envelope
    finally:
        conn.close()
