"""E2E Postgres real/efêmero do canário genérico de Distribuição
Documental (fechamento do gap de composição do canário genérico
WhatsApp V1).

Prova a cadeia completa, sem Airtable/Gmail obrigatórios e sem
transporte real:

    PDF (bytes)
    -> ServicoCriacaoLote.criar_lote()          [Documento durável, porta oficial]
    -> montar_ordem_distribuicao_documental      [distribuir_documento_v1.py, pura]
    -> registrar_evento_canonico_ordem_distribuicao_documental_shadow
       [núcleo -- execucoes/WAITING_GATE, SEM seed manual]
    -> materializar_distribuicao_documental_shadow
       [núcleo -- preview/autorizacoes_gate/PlanoDisparo/Envelope/PENDING]

Reutiliza diretamente as funções de composição já existentes em
`distribuir_documento_v1.py` (as mesmas que `main()` usa), só trocando
o armazenamento físico por `ArmazenamentoArquivosEmMemoria` (S3 real já
provado em separado, não é o que este teste precisa reprovar) -- nunca
contorna o CLI, nunca duplica lógica de composição.

Decisão registrada sobre o "Gap B" do Ultraplan: nenhum script novo de
ingestão foi criado. A porta oficial (`ServicoCriacaoLote`) já é
diretamente reutilizável por composição, como este teste demonstra --
criar um wrapper permanente antes de uma necessidade de produção real
seria antecipar arquitetura sem prova de necessidade.

Roda somente com ``MAGNATA_TEST_POSTGRES_REAL``. Reutiliza as migrations
canônicas do orquestrador (0001-0004) e do módulo 01 (0001-0003, para
Documento/histórico -- lote/esteira não são exigidos pela FK do
orquestrador e não são exercitados aqui para manter o teste focado).
"""
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

psycopg = pytest.importorskip('psycopg', reason='driver psycopg (v3) nao instalado')

from magnata_os.documental.modulo01.adapters.postgres_repositorio import (
    RepositorioDocumentosPostgres,
    RepositorioHistoricoPostgres,
)
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria
from magnata_os.documental.modulo01.repositorio_esteira import (
    RepositorioEstadosEsteiraEmMemoria,
    RepositorioLotesEmMemoria,
)
from magnata_os.documental.modulo01.servico_avanco_esteira import ServicoAvancoEsteira
from magnata_os.documental.modulo01.servico_entrada import ServicoEntradaDocumental
from magnata_os.documental.modulo01.servico_lote import ArquivoEntradaLote, ServicoCriacaoLote
from magnata_os.orquestrador.autorizacao_gate import DecisaoGate
from magnata_os.orquestrador.eventos import EstadoExecucao, TipoEvento
from magnata_os.orquestrador.repositorio_acoes_execucao_plano_postgres import (
    EstadoAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoPostgres,
)
from magnata_os.orquestrador.repositorio_autorizacoes_gate_postgres import (
    RepositorioAutorizacoesGatePostgres,
)
from magnata_os.orquestrador.repositorio_execucoes_postgres import RepositorioExecucoesPostgres
from magnata_os.orquestrador.distribuir_documento_v1 import montar_ordem_distribuicao_documental
from magnata_os.orquestrador.wiring_distribuicao_documental_shadow import (
    derivar_identidade_ordem_distribuicao,
    materializar_distribuicao_documental_shadow,
    registrar_evento_canonico_ordem_distribuicao_documental_shadow,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get('MAGNATA_TEST_POSTGRES_REAL'),
    reason='E2E habilitado somente contra PostgreSQL real e controlado',
)

_RAIZ_ORQUESTRADOR = Path(__file__).parent / 'magnata_os' / 'orquestrador' / 'migrations'
_RAIZ_MODULO01 = Path(__file__).parent / 'magnata_os' / 'documental' / 'modulo01' / 'migrations'
_INSTANTE = datetime(2099, 5, 1, 12, 0, tzinfo=timezone.utc)
_DESTINATARIO = 'destinatario:e2e:canario:generico:sintetico'


def _aplicar_migrations_se_ausentes(conn):
    with conn.cursor() as cursor:
        cursor.execute("SELECT to_regclass('documentos')")
        if cursor.fetchone()[0] is None:
            cursor.execute((_RAIZ_MODULO01 / '0001_criar_tabela_documentos.sql').read_text(encoding='utf-8'))
        cursor.execute("SELECT to_regclass('eventos_documentais')")
        if cursor.fetchone()[0] is None:
            cursor.execute((_RAIZ_MODULO01 / '0002_criar_tabela_eventos_documentais.sql').read_text(encoding='utf-8'))
        cursor.execute((_RAIZ_MODULO01 / '0003_trigger_eventos_append_only.sql').read_text(encoding='utf-8'))

        for nome_tabela, arquivo in (
            ('execucoes', '0001_repositorio_execucoes.sql'),
            ('autorizacoes_gate', '0002_autorizacoes_gate.sql'),
            ('acoes_execucao_plano', '0003_acoes_execucao_plano.sql'),
        ):
            cursor.execute("SELECT to_regclass(%s)", (f'magnata_orquestrador.{nome_tabela}',))
            if cursor.fetchone()[0] is None:
                cursor.execute((_RAIZ_ORQUESTRADOR / arquivo).read_text(encoding='utf-8'))
        cursor.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='magnata_orquestrador' "
            "AND table_name='acoes_execucao_plano' AND column_name='envelope_sha256'"
        )
        if cursor.fetchone() is None:
            cursor.execute((_RAIZ_ORQUESTRADOR / '0004_envelope_execucao_autorizada.sql').read_text(encoding='utf-8'))
    conn.commit()


def _registrar_documento_via_servico_criacao_lote(conn, *, conteudo: bytes, nome_original: str):
    """Passo 1 da cadeia -- porta oficial (`ServicoCriacaoLote`), sem
    Airtable/Gmail (`fonte_candidatos_funcionario=None`). Lote/esteira
    em memória aqui deliberadamente (não é o que este teste prova --
    ver `test_postgres_repositorio_esteira_real.py` para a versão com
    os dois duráveis em Postgres); `Documento` é o único que precisa
    ser real para a Ordem resolvê-lo depois."""
    repositorio_documentos = RepositorioDocumentosPostgres(conn)
    repositorio_historico = RepositorioHistoricoPostgres(conn)
    servico_entrada = ServicoEntradaDocumental(repositorio_documentos, repositorio_historico)
    servico_avanco = ServicoAvancoEsteira(RepositorioEstadosEsteiraEmMemoria(), repositorio_historico)
    servico_lote = ServicoCriacaoLote(
        RepositorioLotesEmMemoria(), servico_entrada, servico_avanco,
        fonte_candidatos_funcionario=None,
    )
    resumo = servico_lote.criar_lote(
        origem='teste_real_canario_generico',
        arquivos=(ArquivoEntradaLote(conteudo=conteudo, nome_original=nome_original, mime_type='application/pdf'),),
    )
    assert resumo.quantidade_erro == 0, resumo.itens
    (item,) = resumo.itens
    documento = repositorio_documentos.buscar_por_id(item.documento_id)
    return documento


def test_e2e_pdf_ate_pending_sem_airtable_sem_gmail_sem_seed_manual():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    armazenamento = ArmazenamentoArquivosEmMemoria()
    try:
        _aplicar_migrations_se_ausentes(conn)

        conteudo = f'e2e-canario-generico-v1-{os.urandom(8).hex()}'.encode('utf-8')
        hash_sha256 = hashlib.sha256(conteudo).hexdigest()
        documento = _registrar_documento_via_servico_criacao_lote(
            conn, conteudo=conteudo, nome_original='canario.pdf',
        )
        assert documento is not None
        assert documento.hash_sha256 == hash_sha256
        # storage físico: o núcleo lê do armazenamento pelo hash, não do
        # que ServicoCriacaoLote usou -- espelha o mesmo conteúdo aqui
        # (mesmo padrão de outros testes `_real` desta sessão, que usam
        # armazenamento em memória para não depender de S3 real).
        armazenamento.armazenar(hash_sha256, conteudo, documento.mime_type, documento.nome_original, documento.tamanho)

        ordem = montar_ordem_distribuicao_documental(
            documentos=((documento.documento_id, documento.hash_sha256),),
            funcionario_id='colab-e2e-canario-generico',
            destinatario=_DESTINATARIO,
            canal='whatsapp',
            preset_id='DOCUMENTO_UNITARIO_SEM_ASSINATURA',
            tipo_documento='CANARIO_GENERICO_SINTETICO',
            exigir_assinatura=False,
            exigir_comprovante=True,
            politica_agrupamento='UNITARIO',
            mensagem_texto='E2E sintético do canário genérico.',
        )

        repositorio_documentos = RepositorioDocumentosPostgres(conn)
        repositorio_execucoes = RepositorioExecucoesPostgres(conn)
        repositorio_autorizacoes = RepositorioAutorizacoesGatePostgres(conn)
        repositorio_acoes = RepositorioAcoesExecucaoPlanoPostgres(conn)

        # ---- evento canônico (SEM seed manual de execucoes) ----
        execucao = registrar_evento_canonico_ordem_distribuicao_documental_shadow(
            ordem=ordem, repositorio_execucoes=repositorio_execucoes, instante=_INSTANTE,
        )
        assert execucao.estado == EstadoExecucao.WAITING_GATE
        assert execucao.event_type == TipoEvento.COMUNICACAO_SOLICITADA.value
        event_id_esperado = derivar_identidade_ordem_distribuicao(ordem)
        assert execucao.event_id == event_id_esperado

        # ---- núcleo: preview -> autorização -> plano -> envelope -> PENDING ----
        kwargs = dict(
            ordem=ordem,
            repositorio_documentos=repositorio_documentos,
            armazenamento=armazenamento,
            materializador=None,
            porta_assinatura=None,
            repositorio_autorizacoes=repositorio_autorizacoes,
            repositorio_acoes=repositorio_acoes,
            ator_referencia='ator:e2e:canario:generico',
            proveniencia='e2e_canario_generico_v1',
            instante=_INSTANTE,
        )
        primeiro = materializar_distribuicao_documental_shadow(**kwargs)
        segundo = materializar_distribuicao_documental_shadow(**kwargs)  # replay

        assert primeiro.event_id == segundo.event_id == event_id_esperado
        assert primeiro.acao_execucao_id == segundo.acao_execucao_id
        assert primeiro.assinatura_link is None

        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM magnata_orquestrador.execucoes WHERE event_id = %s',
                (event_id_esperado,),
            )
            (quantidade_execucoes,) = cursor.fetchone()
        assert quantidade_execucoes == 1  # replay nao duplicou execucoes

        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT decisao FROM magnata_orquestrador.autorizacoes_gate WHERE event_id = %s',
                (event_id_esperado,),
            )
            linhas_autorizacao = cursor.fetchall()
        assert len(linhas_autorizacao) == 1  # replay nao duplicou autorizacao
        assert linhas_autorizacao[0][0] == DecisaoGate.AUTORIZADO.value

        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*), MAX(estado) FROM magnata_orquestrador.acoes_execucao_plano '
                'WHERE acao_execucao_id = %s',
                (primeiro.acao_execucao_id,),
            )
            quantidade_acoes, estado_acao = cursor.fetchone()
        assert quantidade_acoes == 1  # replay nao duplicou a acao PENDING
        assert estado_acao == EstadoAcaoExecucaoPlano.PENDING.value
        assert primeiro.envelope_sha256 is not None
        assert armazenamento.existe(primeiro.envelope_sha256)
    finally:
        conn.close()
