"""E2E Postgres real/efêmero: persistência real do núcleo genérico de
Distribuição Documental (`wiring_distribuicao_documental_shadow.py`).
Nunca executa transporte.

Roda somente com ``MAGNATA_TEST_POSTGRES_REAL``. Reutiliza as migrations
canônicas 0001/0002/0003/0004 (mesmo padrão de
`test_repositorio_acoes_execucao_plano_postgres_real.py`/
`test_wiring_prestacao_orquestrador_persistente_shadow_real.py`) e nunca
executa rollback, DELETE ou DROP. Real: `RepositorioAutorizacoesGatePostgres`
+ `RepositorioAcoesExecucaoPlanoPostgres` (as únicas 2 dependências deste
wiring que de fato persistem em Postgres). Fake/em memória: `Documento`
(`RepositorioDocumentosEmMemoria`) e armazenamento (`ArmazenamentoArquivosEmMemoria`)
-- este teste prova persistência real, não integração com S3/Airtable.
Ramo sem assinatura: `materializador`/`porta_assinatura` são `None`
(aceito pelo núcleo quando `exigir_assinatura=False`), então nenhuma
chamada Airtable/HTTP acontece.
"""
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

psycopg = pytest.importorskip('psycopg', reason='driver psycopg (v3) nao instalado')

from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.dominio import Documento, StatusDocumento
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoPostgres,
)
from magnata_os.orquestrador.repositorio_autorizacoes_gate_postgres import (
    RepositorioAutorizacoesGatePostgres,
)
from magnata_os.orquestrador.wiring_distribuicao_documental_shadow import (
    ItemDocumentoOrdem,
    OrdemDistribuicaoDocumental,
    derivar_identidade_ordem_distribuicao,
    materializar_distribuicao_documental_shadow,
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
_DESTINATARIO = 'destinatario:e2e:distribuicao:documental:sintetico'


def _aplicar_migrations_se_ausentes(conn):
    with conn.cursor() as cursor:
        for nome_tabela, migration in zip(
            ('execucoes', 'autorizacoes_gate', 'acoes_execucao_plano'),
            _MIGRATIONS[:3],
        ):
            cursor.execute("SELECT to_regclass(%s)", (f'magnata_orquestrador.{nome_tabela}',))
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


def _semear_execucao_se_ausente(conn, *, event_id):
    """`autorizacoes_gate.event_id` tem FK para `execucoes(event_id)` --
    o núcleo (`wiring_distribuicao_documental_shadow.py`) nunca cria essa
    linha (não é responsabilidade dele; quem ingere o evento original é
    quem povoa `execucoes`, fora do escopo deste wiring). Mesmo padrão
    de fixture já usado por `test_repositorio_acoes_execucao_plano_
    postgres_real.py::_preparar`/`_preparar_cenario` -- semeia o mínimo
    necessário para a FK, nunca testa lógica de `execucoes` aqui."""
    with conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO magnata_orquestrador.execucoes
               (event_id,event_type,estado,nivel_autonomia,acao,attempt,
                criado_em,atualizado_em)
               VALUES (%s,'DISTRIBUICAO_DOCUMENTAL_SOLICITADA','WAITING_GATE',0,'',0,%s,%s)
               ON CONFLICT (event_id) DO NOTHING""",
            (event_id, _INSTANTE, _INSTANTE),
        )
    conn.commit()


def _documento_e_bytes(repositorio_documentos, armazenamento, *, documento_id, conteudo):
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    documento = Documento(
        documento_id=documento_id, arquivo_original='origem.pdf', nome_original='arquivo.pdf',
        mime_type='application/pdf', tamanho=len(conteudo), hash_sha256=hash_sha256, origem='teste',
        recebido_em=_INSTANTE, lote_id=None, status=StatusDocumento.REGISTRADO,
        correlation_id='corr-e2e-distribuicao', criado_em=_INSTANTE, atualizado_em=_INSTANTE,
    )
    repositorio_documentos.salvar(documento)
    armazenamento.armazenar(hash_sha256, conteudo, documento.mime_type, documento.nome_original, documento.tamanho)
    return documento


def _ordem(documento):
    return OrdemDistribuicaoDocumental(
        documentos=(ItemDocumentoOrdem(documento_id=documento.documento_id, hash_sha256=documento.hash_sha256),),
        funcionario_id='colab-e2e-distribuicao-sintetico',
        destinatario=_DESTINATARIO, canal='WHATSAPP', preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA',
        tipo_documento='DOCUMENTO_SINTETICO', exigir_assinatura=False, exigir_comprovante=True,
        politica_agrupamento='UNITARIO', mensagem_texto='E2E sintético da distribuição documental real.',
    )


def test_e2e_persistencia_real_idempotente_sem_assinatura_sem_transporte():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    repositorio_documentos = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()
    try:
        _aplicar_migrations_se_ausentes(conn)
        documento = _documento_e_bytes(
            repositorio_documentos, armazenamento,
            documento_id='documento-e2e-distribuicao-sintetico',
            conteudo=b'e2e-distribuicao-documental-sintetico-v1',
        )
        ordem = _ordem(documento)
        _semear_execucao_se_ausente(conn, event_id=derivar_identidade_ordem_distribuicao(ordem))
        repositorio_autorizacoes = RepositorioAutorizacoesGatePostgres(conn)
        repositorio_acoes = RepositorioAcoesExecucaoPlanoPostgres(conn)

        kwargs = dict(
            ordem=ordem, repositorio_documentos=repositorio_documentos, armazenamento=armazenamento,
            materializador=None, porta_assinatura=None,
            repositorio_autorizacoes=repositorio_autorizacoes, repositorio_acoes=repositorio_acoes,
            ator_referencia='ator:e2e:distribuicao:sintetico', proveniencia='e2e_distribuicao_shadow_v1',
            instante=_INSTANTE,
        )

        primeiro = materializar_distribuicao_documental_shadow(**kwargs)
        segundo = materializar_distribuicao_documental_shadow(**kwargs)

        assert primeiro.event_id == segundo.event_id
        assert primeiro.acao_execucao_id == segundo.acao_execucao_id
        assert primeiro.assinatura_link is None
        assert armazenamento.existe(primeiro.envelope_sha256)

        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM magnata_orquestrador.acoes_execucao_plano '
                'WHERE acao_execucao_id = %s',
                (primeiro.acao_execucao_id,),
            )
            (quantidade,) = cursor.fetchone()
        assert quantidade == 1  # reaplicacao nao duplicou a linha

        # A ação recém-persistida é utilizável pelo repositório real --
        # claim funciona sobre uma linha nascida do caminho real de
        # composição, não só de INSERT sintético de teste. `preview_id`
        # não é devolvido por `ResultadoDistribuicaoDocumentalShadow`
        # (só `autorizacao_id`/`event_id`), então é lido diretamente da
        # linha persistida.
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT preview_id, estado FROM magnata_orquestrador.acoes_execucao_plano '
                'WHERE acao_execucao_id = %s',
                (primeiro.acao_execucao_id,),
            )
            preview_id_persistido, estado_persistido = cursor.fetchone()
        assert estado_persistido == EstadoAcaoExecucaoPlano.PENDING.value

        reivindicada = repositorio_acoes.reivindicar_proxima(
            event_id=primeiro.event_id, preview_id=preview_id_persistido,
            claim_referencia='worker:e2e:distribuicao', reivindicado_em=_INSTANTE,
        )
        assert reivindicada.acao_execucao_id == primeiro.acao_execucao_id
        assert reivindicada.estado == EstadoAcaoExecucaoPlano.EXECUTING
        finalizada = repositorio_acoes.marcar_sucesso(
            acao_execucao_id=reivindicada.acao_execucao_id,
            claim_referencia='worker:e2e:distribuicao', atualizado_em=_INSTANTE,
        )
        assert finalizada.estado == EstadoAcaoExecucaoPlano.SUCCEEDED
    finally:
        conn.close()
