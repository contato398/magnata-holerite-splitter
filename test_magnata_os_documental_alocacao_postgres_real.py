"""Validação REAL da migration/adapter de `magnata_os/documental/alocacao/`
contra PostgreSQL de verdade (missão "VALIDAÇÃO REAL POSTGRES DA
VIGÊNCIA HISTÓRICA V1"). Complementa (nunca substitui)
`test_magnata_os_documental_alocacao_vigencia_historica.py`, que só
prova a LÓGICA via SQLite -- este arquivo prova a MIGRATION `.sql`
canônica (extensão `btree_gist`, `EXCLUDE USING gist`, `daterange`,
blocos `DO $$`) e o adapter `RepositorioAlocacaoPostgres` contra um
banco de verdade.

Roda SÓ quando `MAGNATA_TEST_POSTGRES_REAL` está definida -- nunca por
padrão numa máquina de desenvolvedor nem numa sessão sem Postgres
disponível (skip limpo, nunca falha por ambiente ausente). Em CI,
definida pelo job `postgres-real` de
`.github/workflows/magnata-testes.yml`, junto com as variáveis padrão
de libpq (`PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD`/`PGDATABASE`) --
`psycopg.connect()` sem argumento nenhum já lê essas variáveis
automaticamente (nunca uma string de conexão única com usuário e senha
embutidos, separados por dois-pontos e seguidos de arroba, literal em
nenhum arquivo commitado -- esse formato é um padrão absoluto de
segredo no Gate 5 de governança deste repositório, propositalmente sem
exceção de placeholder, e corretamente bloqueou a primeira versão deste
arquivo). Aponta para um container de serviço
PostgreSQL EFÊMERO do próprio runner -- nunca um banco permanente,
nunca produção, credenciais fixas que só existem dentro desse job
descartável (nunca reais, nunca da Magnata).

Cada teste começa e termina com o schema desta migration REMOVIDO
(`_limpar_schema`, via o próprio rollback -- prova, de quebra, que o
rollback funciona e é seguro de rodar em banco vazio) -- banco sempre
descartável, nenhum dado sobrevive entre testes nem entre execuções.

Dados 100% sintéticos -- nenhum CPF, nome, cliente ou registro real da
Magnata em nenhum teste deste arquivo (inclusive o caso estruturalmente
equivalente ao SKY: usa IDs fabricados, nunca o record id real do SKY
Tatuí)."""
import os
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

psycopg = pytest.importorskip('psycopg', reason='driver psycopg (v3) nao instalado')

from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import DimensaoResolucao, EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.fonte_unidade_posto_com_prioridade_historica import (
    FonteUnidadePostoPrestacaoComPrioridadeHistorica,
)
from magnata_os.classificacao.resolucao_documento_prestacao import EstadoCorredorDocumentoPrestacao
from magnata_os.documental.alocacao.adapters.postgres_alocacao import RepositorioAlocacaoPostgres
from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import (
    F_FUNC_LOCAIS,
    F_LOCAL_CLIENTE,
    TABLE_FUNC,
    TABLE_LOCAIS,
)
from magnata_os.documental.importacao_lote.composicao_corredor_readonly import ExecucaoCorredorReadonly
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario

_POSTGRES_REAL_DISPONIVEL = bool(os.environ.get('MAGNATA_TEST_POSTGRES_REAL'))
pytestmark = pytest.mark.skipif(
    not _POSTGRES_REAL_DISPONIVEL,
    reason=(
        'MAGNATA_TEST_POSTGRES_REAL nao definida -- este arquivo so roda contra '
        'um PostgreSQL real e descartavel (ver job postgres-real em '
        '.github/workflows/magnata-testes.yml); skip limpo em qualquer outro ambiente.'
    ),
)

_MIGRATIONS_DIR = Path(__file__).parent / 'magnata_os' / 'documental' / 'alocacao' / 'migrations'
_MIGRATION_SQL = (_MIGRATIONS_DIR / '0001_criar_vinculo_trabalhista_e_alocacao.sql').read_text(encoding='utf-8')
_ROLLBACK_SQL = (_MIGRATIONS_DIR / '0001_criar_vinculo_trabalhista_e_alocacao_rollback.sql').read_text(encoding='utf-8')


def _executar_script_sql(conn, sql_texto: str) -> None:
    """Executa um script `.sql` com múltiplos statements (incl. blocos
    `DO $$ ... $$`) numa única chamada. O `Cursor` padrão do psycopg 3
    usa o protocolo ESTENDIDO (via `PQsendQueryParams`), que NÃO aceita
    múltiplos statements num só `execute()` -- diferença real em
    relação ao psycopg2, documentada pelo próprio driver. `ClientCursor`
    (bind client-side, protocolo simples) é o mecanismo do psycopg 3
    para exatamente este caso -- migrations/scripts multi-statement.
    `cursor_factory` é atributo da CONEXÃO (setado em `psycopg.connect()`,
    ver fixture `pg_conn`), nunca argumento de `.cursor()` -- achado real
    de CI (`TypeError: Connection.cursor() got an unexpected keyword
    argument 'cursor_factory'`), corrigido aqui."""
    with conn.cursor() as cur:
        cur.execute(sql_texto)
    conn.commit()


def _aplicar_migration(conn) -> None:
    _executar_script_sql(conn, _MIGRATION_SQL)


def _aplicar_rollback(conn) -> None:
    _executar_script_sql(conn, _ROLLBACK_SQL)


@pytest.fixture
def pg_conn():
    # Sem argumento de conexão -- psycopg/libpq leem PGHOST/PGPORT/PGUSER/
    # PGPASSWORD/PGDATABASE do ambiente automaticamente (ver docstring do
    # módulo). `cursor_factory=ClientCursor` para TODA a conexão (nunca
    # por-cursor -- ver `_executar_script_sql`): permite tanto os scripts
    # multi-statement da migration quanto as queries com `%s`/parâmetros
    # do adapter usarem a MESMA conexão sem trocar de tipo de cursor.
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _aplicar_rollback(conn)  # garante banco/schema vazio no INICIO (idempotente, IF EXISTS)
    yield conn
    conn.rollback()
    _aplicar_rollback(conn)  # descartavel: nao deixa rastro para a proxima execucao
    conn.close()


@pytest.fixture
def repo(pg_conn):
    _aplicar_migration(pg_conn)
    return RepositorioAlocacaoPostgres(pg_conn)


# ============================================================================
# FASE 2 -- migration real: sobe do zero, idempotente, rollback, reaplicavel
# ============================================================================

def test_migration_aplica_do_zero(pg_conn):
    _aplicar_migration(pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('vinculo_trabalhista'), to_regclass('alocacao')")
        vinculo, alocacao = cur.fetchone()
    assert vinculo is not None
    assert alocacao is not None


def test_btree_gist_instalada_pela_migration(pg_conn):
    _aplicar_migration(pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'btree_gist'")
        assert cur.fetchone() is not None


def test_constraints_check_e_exclude_presentes(pg_conn):
    _aplicar_migration(pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT conname, contype FROM pg_constraint "
            "WHERE conrelid IN ('vinculo_trabalhista'::regclass, 'alocacao'::regclass)"
        )
        constraints = dict(cur.fetchall())
    assert constraints.get('vinculo_trabalhista_sem_sobreposicao') == 'x'  # EXCLUDE
    assert constraints.get('alocacao_sem_sobreposicao_mesmo_posto') == 'x'
    assert constraints.get('vinculo_trabalhista_desligamento_apos_admissao') == 'c'  # CHECK
    assert constraints.get('alocacao_vigencia_valida') == 'c'


def test_fk_alocacao_vinculo_trabalhista_presente(pg_conn):
    _aplicar_migration(pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_constraint "
            "WHERE contype = 'f' AND conrelid = 'alocacao'::regclass"
        )
        assert cur.fetchone()[0] == 1


def test_indices_presentes(pg_conn):
    _aplicar_migration(pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename IN ('vinculo_trabalhista', 'alocacao')"
        )
        nomes = {r[0] for r in cur.fetchall()}
    assert 'idx_vinculo_trabalhista_colaborador_id' in nomes
    assert 'idx_alocacao_vinculo_trabalhista_id' in nomes
    assert 'idx_alocacao_vigencia' in nomes


def test_migration_reaplicada_e_idempotente_de_verdade(pg_conn):
    _aplicar_migration(pg_conn)
    _aplicar_migration(pg_conn)  # nunca deve levantar excecao (blocker 2 do PR #112, agora provado real)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('alocacao')")
        assert cur.fetchone()[0] is not None


def test_rollback_remove_so_as_2_tabelas_desta_migration(pg_conn):
    _aplicar_migration(pg_conn)
    _aplicar_rollback(pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('vinculo_trabalhista'), to_regclass('alocacao')")
        vinculo, alocacao = cur.fetchone()
    assert vinculo is None
    assert alocacao is None


def test_migration_reaplicada_apos_rollback(pg_conn):
    _aplicar_migration(pg_conn)
    _aplicar_rollback(pg_conn)
    _aplicar_migration(pg_conn)  # nunca deve levantar excecao
    with pg_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('vinculo_trabalhista')")
        assert cur.fetchone()[0] is not None


# ============================================================================
# FASE 3/4 -- temporalidade + adapter real (RepositorioAlocacaoPostgres,
# NUNCA mockado -- conexao real ao Postgres do container de servico)
# ============================================================================

def test_vinculo_aberto_e_encontrado(repo):
    repo.registrar_vinculo('v-aberto', 'colab-pg-1', date(2026, 1, 1))
    assert repo.vinculos_vigentes_em('colab-pg-1', date(2026, 6, 1), date(2026, 6, 30)) == ('v-aberto',)


def test_vinculo_encerrado_fora_da_janela_nao_encontrado(repo):
    repo.registrar_vinculo('v-encerrado', 'colab-pg-2', date(2025, 1, 1), date(2025, 12, 31))
    assert repo.vinculos_vigentes_em('colab-pg-2', date(2026, 6, 1), date(2026, 6, 30)) == ()


def test_readmissao_posterior_ao_encerramento_e_aceita(repo):
    repo.registrar_vinculo('v-antigo', 'colab-pg-3', date(2025, 1, 1), date(2025, 6, 30))
    repo.registrar_vinculo('v-novo', 'colab-pg-3', date(2026, 1, 1))  # nunca deve levantar
    assert repo.vinculos_vigentes_em('colab-pg-3', date(2026, 6, 1), date(2026, 6, 30)) == ('v-novo',)


def test_dois_vinculos_temporalmente_sobrepostos_falha(repo):
    repo.registrar_vinculo('v1', 'colab-pg-4', date(2026, 1, 1))
    with pytest.raises(Exception):
        repo.registrar_vinculo('v2', 'colab-pg-4', date(2026, 3, 1))


def test_alocacao_aberta_encontrada(repo):
    repo.registrar_vinculo('v-aloc-1', 'colab-pg-5', date(2026, 1, 1))
    repo.registrar_alocacao('a1', 'v-aloc-1', 'posto-pg-A', date(2026, 1, 1))
    assert repo.postos_vigentes_em('v-aloc-1', date(2026, 6, 1), date(2026, 6, 30)) == ('posto-pg-A',)


def test_alocacao_encerrada_fora_da_janela(repo):
    repo.registrar_vinculo('v-aloc-2', 'colab-pg-6', date(2026, 1, 1))
    repo.registrar_alocacao('a1', 'v-aloc-2', 'posto-pg-A', date(2026, 1, 1), date(2026, 5, 31))
    assert repo.postos_vigentes_em('v-aloc-2', date(2026, 6, 1), date(2026, 6, 30)) == ()


def test_transferencia_no_meio_do_mes_retorna_os_2_postos(repo):
    repo.registrar_vinculo('v-transf', 'colab-pg-7', date(2026, 1, 1))
    repo.registrar_alocacao('a1', 'v-transf', 'posto-pg-A', date(2026, 1, 1), date(2026, 6, 14))
    repo.registrar_alocacao('a2', 'v-transf', 'posto-pg-B', date(2026, 6, 15))
    postos = repo.postos_vigentes_em('v-transf', date(2026, 6, 1), date(2026, 6, 30))
    assert set(postos) == {'posto-pg-A', 'posto-pg-B'}


def test_rateio_simultaneo_entre_postos_diferentes_funciona(repo):
    repo.registrar_vinculo('v-rateio', 'colab-pg-8', date(2026, 1, 1))
    repo.registrar_alocacao('a1', 'v-rateio', 'posto-pg-A', date(2026, 6, 1), date(2026, 6, 30))
    repo.registrar_alocacao('a2', 'v-rateio', 'posto-pg-B', date(2026, 6, 1), date(2026, 6, 30))  # nunca deve levantar
    postos = repo.postos_vigentes_em('v-rateio', date(2026, 6, 1), date(2026, 6, 30))
    assert set(postos) == {'posto-pg-A', 'posto-pg-B'}


def test_sobreposicao_do_mesmo_vinculo_no_mesmo_posto_falha(repo):
    repo.registrar_vinculo('v-dup', 'colab-pg-9', date(2026, 1, 1))
    repo.registrar_alocacao('a1', 'v-dup', 'posto-pg-A', date(2026, 1, 1), date(2026, 6, 30))
    with pytest.raises(Exception):
        repo.registrar_alocacao('a2', 'v-dup', 'posto-pg-A', date(2026, 6, 1), date(2026, 12, 31))


def test_fk_invalida_falha(repo):
    with pytest.raises(Exception):
        repo.registrar_alocacao('a-orfa', 'vinculo-inexistente', 'posto-pg-A', date(2026, 1, 1))


def test_competencia_sem_alocacao_e_honestamente_nao_encontrada(repo):
    repo.registrar_vinculo('v-sem-aloc', 'colab-pg-10', date(2026, 1, 1))
    resultado = repo.resolver_unidade_posto(
        ReferenciaCanonica('COLABORADOR', 'colab-pg-10'), ReferenciaCanonica('COMPETENCIA', '2026-06'))
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


# ============================================================================
# FASE 5 -- integracao real do corredor com Postgres real (dados 100%
# sinteticos -- estruturalmente equivalente ao SKY, nunca o SKY real)
# ============================================================================

def test_corredor_real_resolve_unidade_posto_historica_via_postgres_real(repo):
    func_id = 'colaborador-estrutural-pg'
    cliente_sintetico_id = 'cliente-estrutural-pg'

    repo.registrar_vinculo('vinculo-estrutural-pg', func_id, date(2025, 1, 1))
    repo.registrar_alocacao('aloc-estrutural-pg', 'vinculo-estrutural-pg', 'posto-estrutural-pg', date(2026, 1, 1))

    def _listar_registros(**kwargs):
        table = kwargs.get('table_id')
        if table == TABLE_FUNC:
            return [{'id': func_id, 'fields': {F_FUNC_LOCAIS: ['local-estrutural-pg']}}]
        if table == TABLE_LOCAIS:
            return [{'id': 'local-estrutural-pg', 'fields': {F_LOCAL_CLIENTE: [cliente_sintetico_id]}}]
        return []

    leitor = Mock()
    leitor.listar_registros.side_effect = _listar_registros
    leitor.listar_clientes.return_value = []

    fonte_corrente_fake = Mock()

    # Ciclo BASE = Junho/2026, igual à competência declarada no texto --
    # deliberado: sem `cliente_do_ciclo`, `competencia_esperada` cai para
    # `ciclo.competencia_base` (nunca precisa de política de deslocamento
    # tipo SKY para este teste, que prova só alocação->UNIDADE_POSTO, não
    # a política de competência -- essa já provada à parte, com SKY real,
    # em test_sky_ciclo_base_julho_snapshot_comprovado... e no live real).
    # Achado real do primeiro run deste teste em CI: usar ciclo (2026, 7)
    # sem cliente_do_ciclo fazia competencia_esperada cair em Julho,
    # divergindo do texto (Junho) e travando CLIENTE/UNIDADE_POSTO a
    # montante -- corrigido alinhando o ciclo à competência do documento.
    execucao = ExecucaoCorredorReadonly(
        leitor, ContextoCicloPrestacao((2026, 6)),
        fonte_unidade_posto_override=FonteUnidadePostoPrestacaoComPrioridadeHistorica(repo, fonte_corrente_fake),
    )
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 06/2026\nCPF: 999.888.777-11'
    resultados = execucao.processar_documento(
        'doc-estrutural-pg', 'a' * 64, texto=texto,
        candidatos_colaborador=[CandidatoFuncionario(func_id=func_id, cpf='99988877711', nome_normalizado='ESTRUTURAL')],
    )
    resultado = resultados[0].resultado_corredor
    dimensoes = {r.dimensao: r for r in resultado.resolucao_semantica.resolucoes}

    assert dimensoes[DimensaoResolucao.UNIDADE_POSTO].estado == EstadoResolucaoDimensao.RESOLVIDA
    assert dimensoes[DimensaoResolucao.UNIDADE_POSTO].valores_confirmados == (
        ReferenciaCanonica('UNIDADE_POSTO', 'posto-estrutural-pg'),
    )
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    fonte_corrente_fake.resolver_unidade_posto.assert_not_called()
