"""Validação REAL da migration/adapter de `magnata_os/autenticacao/`
contra PostgreSQL de verdade (missão "AUTENTICAÇÃO ADMINISTRATIVA
COMPARTILHADA V1", FASE 6/9/11). Mesmo padrão de
`test_magnata_os_documental_alocacao_postgres_real.py` -- complementa
(nunca substitui) `test_magnata_os_autenticacao_auditoria_v1.py`, que
só prova a LÓGICA via SQLite; este arquivo prova a MIGRATION `.sql`
canônica (`auditoria_operacoes`, trigger append-only) e o adapter
`RepositorioAuditoriaPostgres` contra um banco de verdade.

Roda SÓ quando `MAGNATA_TEST_POSTGRES_REAL` está definida -- skip
limpo em qualquer outro ambiente. Em CI, reaproveita o MESMO job
`postgres-real` de `.github/workflows/magnata-testes.yml` (linha de
`run:` estendida para incluir este arquivo -- nenhum job novo criado).

Cada teste começa e termina com o schema desta migration REMOVIDO
(rollback idempotente) -- banco sempre descartável. Dados 100%
sintéticos -- nenhum e-mail real da Magnata em nenhum teste."""
import os
from pathlib import Path

import pytest

psycopg = pytest.importorskip('psycopg', reason='driver psycopg (v3) nao instalado')

from magnata_os.autenticacao.adapters.postgres_auditoria import RepositorioAuditoriaPostgres
from magnata_os.autenticacao.eventos import RESULTADO_ERRO, RESULTADO_SUCESSO, OperacaoAuditada, registrar_operacao
from magnata_os.autenticacao.identidade import Perfil, Sujeito

_SUJEITO_GESTOR = Sujeito(Perfil.GESTOR, sujeito_id='sub-pg-1', email='gestor-pg@exemplo.com', autenticado_por='google_oidc')

_POSTGRES_REAL_DISPONIVEL = bool(os.environ.get('MAGNATA_TEST_POSTGRES_REAL'))
pytestmark = pytest.mark.skipif(
    not _POSTGRES_REAL_DISPONIVEL,
    reason=(
        'MAGNATA_TEST_POSTGRES_REAL nao definida -- este arquivo so roda contra '
        'um PostgreSQL real e descartavel (ver job postgres-real em '
        '.github/workflows/magnata-testes.yml); skip limpo em qualquer outro ambiente.'
    ),
)

_MIGRATIONS_DIR = Path(__file__).parent / 'magnata_os' / 'autenticacao' / 'migrations'
_MIGRATION_SQL = (_MIGRATIONS_DIR / '0001_criar_auditoria_operacoes.sql').read_text(encoding='utf-8')
_ROLLBACK_SQL = (_MIGRATIONS_DIR / '0001_criar_auditoria_operacoes_rollback.sql').read_text(encoding='utf-8')


def _executar_script_sql(conn, sql_texto: str) -> None:
    """Ver docstring equivalente em
    test_magnata_os_documental_alocacao_postgres_real.py -- mesmo
    motivo (ClientCursor para scripts multi-statement com blocos
    `DO $$`/`CREATE FUNCTION`)."""
    with conn.cursor() as cur:
        cur.execute(sql_texto)
    conn.commit()


def _aplicar_migration(conn) -> None:
    _executar_script_sql(conn, _MIGRATION_SQL)


def _aplicar_rollback(conn) -> None:
    _executar_script_sql(conn, _ROLLBACK_SQL)


@pytest.fixture
def pg_conn():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _aplicar_rollback(conn)  # garante banco/schema vazio no inicio
    yield conn
    conn.rollback()
    _aplicar_rollback(conn)  # descartavel
    conn.close()


@pytest.fixture
def repo(pg_conn):
    _aplicar_migration(pg_conn)
    return RepositorioAuditoriaPostgres(pg_conn)


# ============================================================================
# Migration -- sobe do zero, idempotente, rollback, reaplicavel
# ============================================================================

def test_migration_aplica_do_zero(pg_conn):
    _aplicar_migration(pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('auditoria_operacoes')")
        assert cur.fetchone()[0] is not None


def test_migration_reaplicada_e_idempotente(pg_conn):
    _aplicar_migration(pg_conn)
    _aplicar_migration(pg_conn)  # nunca deve levantar excecao
    with pg_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('auditoria_operacoes')")
        assert cur.fetchone()[0] is not None


def test_rollback_remove_a_tabela(pg_conn):
    _aplicar_migration(pg_conn)
    _aplicar_rollback(pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('auditoria_operacoes')")
        assert cur.fetchone()[0] is None


def test_migration_reaplicada_apos_rollback(pg_conn):
    _aplicar_migration(pg_conn)
    _aplicar_rollback(pg_conn)
    _aplicar_migration(pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('auditoria_operacoes')")
        assert cur.fetchone()[0] is not None


def test_trigger_append_only_bloqueia_update(repo, pg_conn):
    operacao_id = registrar_operacao(repo, OperacaoAuditada(
        sujeito=_SUJEITO_GESTOR, operacao='confirmar_alocacao', resultado=RESULTADO_SUCESSO,
        referencia_agregado='aloc-pg-1',
    ))
    with pytest.raises(Exception):
        with pg_conn.cursor() as cur:
            cur.execute(
                "UPDATE auditoria_operacoes SET resultado = 'ERRO' WHERE id = %s", (operacao_id,))
    pg_conn.rollback()  # a excecao deixa a transacao abortada -- limpa antes do teardown


def test_trigger_append_only_bloqueia_delete(repo, pg_conn):
    operacao_id = registrar_operacao(repo, OperacaoAuditada(
        sujeito=_SUJEITO_GESTOR, operacao='confirmar_alocacao', resultado=RESULTADO_SUCESSO,
        referencia_agregado='aloc-pg-2',
    ))
    with pytest.raises(Exception):
        with pg_conn.cursor() as cur:
            cur.execute("DELETE FROM auditoria_operacoes WHERE id = %s", (operacao_id,))
    pg_conn.rollback()


def test_resultado_invalido_e_rejeitado_pelo_check_constraint(repo, pg_conn):
    with pytest.raises(Exception):
        with pg_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO auditoria_operacoes (id, email, perfil, operacao, resultado) "
                "VALUES ('x', 'a@b.com', 'GESTOR', 'op', 'TALVEZ')")
    pg_conn.rollback()


# ============================================================================
# Adapter real -- insercao e consulta contra Postgres de verdade
# ============================================================================

def test_registrar_operacao_real_e_consultavel(repo):
    operacao_id = registrar_operacao(repo, OperacaoAuditada(
        sujeito=_SUJEITO_GESTOR, operacao='confirmar_alocacao', resultado=RESULTADO_SUCESSO,
        referencia_agregado='aloc-pg-3',
    ))
    registros = repo.listar_por_referencia('aloc-pg-3')
    assert len(registros) == 1
    assert registros[0].id == operacao_id
    assert registros[0].email == 'gestor-pg@exemplo.com'


def test_registrar_operacao_de_erro_real(repo):
    registrar_operacao(repo, OperacaoAuditada(
        sujeito=_SUJEITO_GESTOR, operacao='confirmar_alocacao', resultado=RESULTADO_ERRO,
        referencia_agregado='aloc-pg-4', erro_codigo='ConflitoTemporalEventoError',
    ))
    registros = repo.listar_por_referencia('aloc-pg-4')
    assert registros[0].resultado == RESULTADO_ERRO
    assert registros[0].erro_codigo == 'ConflitoTemporalEventoError'


def test_multiplas_tentativas_nunca_deduplicadas_contra_postgres(repo):
    for _ in range(3):
        registrar_operacao(repo, OperacaoAuditada(
            sujeito=_SUJEITO_GESTOR, operacao='confirmar_alocacao', resultado=RESULTADO_SUCESSO,
            referencia_agregado='aloc-pg-5',
        ))
    assert len(repo.listar_por_referencia('aloc-pg-5')) == 3
