"""J3 contra PostgreSQL REAL e efêmero: migration 0011, adapter do índice
documental e o ciclo da Prestação lendo/gravando o índice de verdade.

Mesma disciplina dos demais `*_real.py`: só roda com
`MAGNATA_TEST_POSTGRES_REAL=1` e conexão libpq (`PG*`) de um banco de
teste descartável; aplica as migrations necessárias só se a tabela não
existir; nunca faz DROP/TRUNCATE; ids aleatórios por teste. Dados 100%
sintéticos.
"""
import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get('MAGNATA_TEST_POSTGRES_REAL'),
    reason='E2E habilitado somente contra PostgreSQL real e controlado',
)

psycopg = pytest.importorskip('psycopg', reason='driver psycopg (v3) nao instalado')

from magnata_os.classificacao.contratos import ReferenciaCanonica  # noqa: E402
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao  # noqa: E402
from magnata_os.documental.modulo01.adapters.postgres_indice_documental_prestacao import (  # noqa: E402
    RepositorioIndiceDocumentalPrestacaoPostgres,
)
from magnata_os.documental.modulo01.adapters.postgres_repositorio import RepositorioDocumentosPostgres  # noqa: E402
from magnata_os.documental.modulo01.dominio import Documento, StatusDocumento  # noqa: E402

_RAIZ = Path(__file__).parent / 'magnata_os' / 'documental' / 'modulo01' / 'migrations'
_AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)


def _aplicar_migrations_se_ausentes(conn):
    with conn.cursor() as cursor:
        for tabela, arquivo in (
            ('documentos', '0001_criar_tabela_documentos.sql'),
            ('indice_documental_prestacao', '0011_criar_tabela_indice_documental_prestacao.sql'),
        ):
            cursor.execute('SELECT to_regclass(%s)', (tabela,))
            if cursor.fetchone()[0] is None:
                cursor.execute((_RAIZ / arquivo).read_text(encoding='utf-8'))
    conn.commit()


@pytest.fixture
def conexao():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _aplicar_migrations_se_ausentes(conn)
    try:
        yield conn
    finally:
        conn.close()


def _documento(conn):
    documento_id = f'doc-j3-{uuid.uuid4()}'
    RepositorioDocumentosPostgres(conn).salvar(Documento(
        documento_id=documento_id, arquivo_original='memoria://x', nome_original='x.pdf',
        mime_type='application/pdf', tamanho=1,
        hash_sha256=hashlib.sha256(documento_id.encode()).hexdigest(), origem='teste',
        recebido_em=_AGORA, lote_id=None, status=StatusDocumento.REGISTRADO, correlation_id='teste',
        criado_em=_AGORA, atualizado_em=_AGORA,
    ))
    return documento_id


def _item(documento_id, cliente, colaborador=None, tipo='Holerite'):
    return ItemInventarioPrestacao(
        documento_id=documento_id, tipo_documental=tipo,
        cliente=ReferenciaCanonica('CLIENTE', cliente),
        competencia=ReferenciaCanonica('COMPETENCIA', '2026-09'),
        colaborador=ReferenciaCanonica('COLABORADOR', colaborador) if colaborador else None,
    )


def test_gravar_e_listar_por_cliente_e_competencia(conexao):
    cliente = f'cli-{uuid.uuid4()}'
    doc_a, doc_b = _documento(conexao), _documento(conexao)
    indice = RepositorioIndiceDocumentalPrestacaoPostgres(conexao)

    novos = indice.adicionar_muitos((_item(doc_a, cliente, 'colab-1'), _item(doc_b, cliente, tipo='Extrato')))

    assert novos == 2
    itens = indice.listar(ReferenciaCanonica('CLIENTE', cliente), ReferenciaCanonica('COMPETENCIA', '2026-09'))
    assert {(i.documento_id, i.colaborador.entidade_id if i.colaborador else None, i.tipo_documental) for i in itens} == {
        (doc_a, 'colab-1', 'Holerite'), (doc_b, None, 'Extrato'),
    }
    assert indice.listar(ReferenciaCanonica('CLIENTE', cliente), ReferenciaCanonica('COMPETENCIA', '2026-08')) == ()


def test_regravar_e_idempotente_e_nao_colapsa_identidades_distintas(conexao):
    cliente = f'cli-{uuid.uuid4()}'
    doc = _documento(conexao)
    indice = RepositorioIndiceDocumentalPrestacaoPostgres(conexao)
    indice.adicionar_muitos((_item(doc, cliente, 'colab-1'),))

    assert indice.adicionar_muitos((_item(doc, cliente, 'colab-1'),)) == 0
    assert indice.adicionar_muitos((_item(doc, cliente, 'colab-2'),)) == 1  # fatiado por colaborador
    assert len(indice.listar(ReferenciaCanonica('CLIENTE', cliente), ReferenciaCanonica('COMPETENCIA', '2026-09'))) == 2


def test_documento_inexistente_falha_inteiro_sem_gravacao_parcial(conexao):
    cliente = f'cli-{uuid.uuid4()}'
    doc = _documento(conexao)
    indice = RepositorioIndiceDocumentalPrestacaoPostgres(conexao)

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        indice.adicionar_muitos((_item(doc, cliente, 'colab-1'), _item('doc-que-nao-existe', cliente, 'colab-2')))

    assert indice.listar(ReferenciaCanonica('CLIENTE', cliente), ReferenciaCanonica('COMPETENCIA', '2026-09')) == ()


def test_competencia_fora_do_formato_e_rejeitada_pelo_banco(conexao):
    doc = _documento(conexao)
    with conexao.cursor() as cursor, pytest.raises(psycopg.errors.CheckViolation):
        cursor.execute(
            "INSERT INTO indice_documental_prestacao (documento_id, cliente_id, competencia, tipo_documental) "
            "VALUES (%s, 'cli', '09/2026', 'Holerite')", (doc,),
        )
    conexao.rollback()


def test_rollback_da_migration_remove_so_o_indice(conexao):
    rollback = (_RAIZ / '0011_criar_tabela_indice_documental_prestacao_rollback.sql').read_text(encoding='utf-8')
    migration = (_RAIZ / '0011_criar_tabela_indice_documental_prestacao.sql').read_text(encoding='utf-8')
    with conexao.cursor() as cursor:
        cursor.execute(rollback)
        cursor.execute("SELECT to_regclass('indice_documental_prestacao'), to_regclass('documentos')")
        indice, documentos = cursor.fetchone()
        assert indice is None and documentos is not None
        cursor.execute(migration)  # reaplicável: deixa o banco como estava
        cursor.execute(migration)  # idempotente
    conexao.commit()
