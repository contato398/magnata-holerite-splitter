"""E2E Postgres real/efêmero: RepositorioLotesPostgres/RepositorioEstadosEsteiraPostgres
(Módulo 01, Fase 3) contra o schema real das migrations 0001/0005/0006.

Roda somente com ``MAGNATA_TEST_POSTGRES_REAL``. Reutiliza migrations
canônicas (mesmo padrão de test_wiring_distribuicao_documental_shadow_real.py)
e nunca executa DELETE/DROP/TRUNCATE -- só INSERT/UPDATE via os adapters.

Cobre também a integração real com ServicoCriacaoLote (porta oficial de
entrada), provando: Documento durável -> LoteDocumental durável ->
EstadoEsteiraDocumento durável, sem Airtable/Gmail.
"""
import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

psycopg = pytest.importorskip('psycopg', reason='driver psycopg (v3) nao instalado')

from magnata_os.documental.modulo01.adapters.postgres_repositorio import RepositorioDocumentosPostgres
from magnata_os.documental.modulo01.adapters.postgres_repositorio_esteira import (
    RepositorioEstadosEsteiraPostgres,
    RepositorioLotesPostgres,
)
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.dominio_esteira import (
    EstadoEsteiraDocumento,
    EtapaEsteira,
    LoteDocumental,
    MotivoBloqueio,
    ProximaAcao,
    SituacaoEsteira,
    TipoProximaAcao,
)
from magnata_os.documental.modulo01.servico_avanco_esteira import ServicoAvancoEsteira
from magnata_os.documental.modulo01.servico_entrada import ServicoEntradaDocumental
from magnata_os.documental.modulo01.servico_lote import ArquivoEntradaLote, ServicoCriacaoLote

pytestmark = pytest.mark.skipif(
    not os.environ.get('MAGNATA_TEST_POSTGRES_REAL'),
    reason='E2E habilitado somente contra PostgreSQL real e controlado',
)

_RAIZ = Path(__file__).parent / 'magnata_os' / 'documental' / 'modulo01' / 'migrations'
_INSTANTE = datetime(2099, 4, 1, 12, 0, tzinfo=timezone.utc)


def _aplicar_migrations_se_ausentes(conn):
    with conn.cursor() as cursor:
        for nome_tabela, arquivo in (
            ('documentos', '0001_criar_tabela_documentos.sql'),
            # 0002/0003: eventos_documentais + trigger append-only --
            # necessarias porque o teste de integracao com
            # ServicoCriacaoLote exercita RepositorioHistoricoPostgres.
            # registrar() de verdade (ServicoEntradaDocumental grava
            # historico a cada Documento novo), nao so RepositorioDocumentos.
            ('eventos_documentais', '0002_criar_tabela_eventos_documentais.sql'),
            ('lotes_documentais', '0005_criar_tabela_lotes_documentais.sql'),
            ('estados_esteira_documental', '0006_criar_tabela_estados_esteira_documental.sql'),
        ):
            cursor.execute("SELECT to_regclass(%s)", (nome_tabela,))
            if cursor.fetchone()[0] is None:
                sql = (_RAIZ / arquivo).read_text(encoding='utf-8')
                cursor.execute(sql)
        # A propria migration 0003 e idempotente (DROP TRIGGER IF EXISTS
        # antes de cada CREATE TRIGGER) -- sempre reaplicavel sem checagem
        # extra de existencia.
        cursor.execute((_RAIZ / '0003_trigger_eventos_append_only.sql').read_text(encoding='utf-8'))
    conn.commit()


def _lote(lote_id, metadados=None):
    return LoteDocumental(
        lote_id=lote_id, origem='teste_real', recebido_em=_INSTANTE, quantidade_arquivos=1,
        situacao=SituacaoEsteira.CONCLUIDO, correlation_id=f'corr-{lote_id}',
        criado_em=_INSTANTE, atualizado_em=_INSTANTE, metadados=metadados or {},
    )


def test_e2e_lote_round_trip_real():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    try:
        _aplicar_migrations_se_ausentes(conn)
        repo = RepositorioLotesPostgres(conn)
        lote = _lote('lote-e2e-real-1', metadados={'chave': {'aninhada': [1, 2, 3]}})

        repo.salvar(lote)
        recuperado = repo.buscar_por_id('lote-e2e-real-1')

        assert recuperado == lote

        # replay: salvar de novo nao duplica.
        repo.salvar(lote)
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM lotes_documentais WHERE lote_id = %s',
                ('lote-e2e-real-1',),
            )
            (quantidade,) = cursor.fetchone()
        assert quantidade == 1
    finally:
        conn.close()


def test_e2e_estado_round_trip_e_fk_real():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    try:
        _aplicar_migrations_se_ausentes(conn)
        repo_documentos = RepositorioDocumentosPostgres(conn)
        repo_lotes = RepositorioLotesPostgres(conn)
        repo_estados = RepositorioEstadosEsteiraPostgres(conn)

        from magnata_os.documental.modulo01.dominio import Documento, StatusDocumento
        conteudo_hash = hashlib.sha256(b'e2e-esteira-real').hexdigest()
        documento = Documento(
            documento_id='doc-e2e-esteira-real', arquivo_original='origem.pdf',
            nome_original='arquivo.pdf', mime_type='application/pdf', tamanho=10,
            hash_sha256=conteudo_hash, origem='teste_real', recebido_em=_INSTANTE,
            lote_id=None, status=StatusDocumento.REGISTRADO, correlation_id='corr-doc-e2e',
            criado_em=_INSTANTE, atualizado_em=_INSTANTE,
        )
        repo_documentos.salvar(documento)
        repo_lotes.salvar(_lote('lote-e2e-esteira-real'))

        motivo = MotivoBloqueio(
            codigo='TESTE', descricao='motivo sintetico', detalhe_tecnico=None,
            resolvivel_automaticamente=True,
        )
        proxima = ProximaAcao(acao='revisar', tipo=TipoProximaAcao.HUMANA, prazo=_INSTANTE, responsavel='qa@magnata')
        estado = EstadoEsteiraDocumento(
            documento_id='doc-e2e-esteira-real', lote_id='lote-e2e-esteira-real',
            etapa_atual=EtapaEsteira.VALIDACAO, situacao=SituacaoEsteira.BLOQUEADO,
            motivo_bloqueio=motivo, proxima_acao=proxima,
            entrou_na_etapa_em=_INSTANTE, atualizado_em=_INSTANTE, correlation_id='corr-estado-e2e',
        )

        repo_estados.salvar(estado)
        recuperado = repo_estados.buscar_por_documento_id('doc-e2e-esteira-real')
        assert recuperado == estado

        # FK real: documento_id inexistente deve ser rejeitado pelo proprio banco.
        estado_invalido = EstadoEsteiraDocumento(
            documento_id='doc-que-nao-existe', lote_id=None, etapa_atual=EtapaEsteira.ENTRADA,
            situacao=SituacaoEsteira.AGUARDANDO, motivo_bloqueio=None, proxima_acao=None,
            entrou_na_etapa_em=_INSTANTE, atualizado_em=_INSTANTE, correlation_id='corr-invalido',
        )
        with pytest.raises(Exception):
            repo_estados.salvar(estado_invalido)

        # criar_se_ausente idempotente sobre a mesma linha ja existente.
        _, criado = repo_estados.criar_se_ausente(
            'doc-e2e-esteira-real', lambda: estado,
        )
        assert criado is False
    finally:
        conn.close()


def test_e2e_servico_criacao_lote_com_adapters_postgres_sem_airtable_sem_gmail():
    """Prova a cadeia completa via a PORTA OFICIAL de entrada
    (ServicoCriacaoLote): Documento durável -> LoteDocumental durável ->
    EstadoEsteiraDocumento durável, com os dois adapters novos + o
    adapter já existente de Documento, todos contra Postgres real.
    `fonte_candidatos_funcionario=None` -- nenhuma dependência de
    Airtable/Gmail em nenhum ponto desta chamada."""
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    try:
        _aplicar_migrations_se_ausentes(conn)
        from magnata_os.documental.modulo01.adapters.postgres_repositorio import (
            RepositorioHistoricoPostgres,
        )
        repositorio_documentos = RepositorioDocumentosPostgres(conn)
        repositorio_historico = RepositorioHistoricoPostgres(conn)
        repositorio_lotes = RepositorioLotesPostgres(conn)
        repositorio_estados = RepositorioEstadosEsteiraPostgres(conn)
        armazenamento = ArmazenamentoArquivosEmMemoria()

        servico_entrada = ServicoEntradaDocumental(repositorio_documentos, repositorio_historico)
        servico_avanco = ServicoAvancoEsteira(repositorio_estados, repositorio_historico)
        servico_lote = ServicoCriacaoLote(
            repositorio_lotes, servico_entrada, servico_avanco,
            fonte_candidatos_funcionario=None,
        )

        # Conteudo unico por execucao (nunca fixo): este teste roda
        # contra um banco persistente entre execucoes (sem DROP/DELETE
        # permitido) -- conteudo fixo colidiria por hash na 2a execucao
        # e o proprio sistema, corretamente, marcaria como duplicado
        # (nao seria um bug do adapter, so um teste nao-reexecutavel).
        conteudo = f'e2e-servico-criacao-lote-real-v1-{uuid.uuid4()}'.encode('utf-8')
        resumo = servico_lote.criar_lote(
            origem='teste_real_canario',
            arquivos=(
                ArquivoEntradaLote(conteudo=conteudo, nome_original='canario.pdf', mime_type='application/pdf'),
            ),
        )

        assert resumo.quantidade_sucesso == 1
        assert resumo.quantidade_erro == 0
        item = resumo.itens[0]
        assert item.sucesso is True
        documento_id = item.documento_id

        documento = repositorio_documentos.buscar_por_id(documento_id)
        assert documento is not None
        assert documento.hash_sha256 == hashlib.sha256(conteudo).hexdigest()

        lote = repositorio_lotes.buscar_por_id(resumo.lote_id)
        assert lote is not None
        assert lote.quantidade_arquivos == 1

        estado = repositorio_estados.buscar_por_documento_id(documento_id)
        assert estado is not None
        assert estado.lote_id == resumo.lote_id
        assert estado.etapa_atual == EtapaEsteira.REGISTRO
    finally:
        conn.close()
