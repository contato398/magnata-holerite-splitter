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
from unittest import mock
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
from magnata_os.documental.alocacao.captura import (
    aplicar_alocacao_iniciada,
    aplicar_transferencia,
    aplicar_vinculo_encerrado,
    aplicar_vinculo_iniciado,
)
from magnata_os.documental.alocacao.comparacao_airtable import (
    EstadoComparacaoAirtable,
    comparar_colaborador_shadow_com_airtable,
)
from magnata_os.documental.alocacao.confirmacao import (
    ACAO_ADICIONAR_RATEIO,
    ACAO_ENCERRAR,
    ACAO_INICIAR,
    ACAO_TRANSFERIR,
    ColaboradorNaoIdentificadoError,
    SolicitacaoConfirmacaoAlocacao,
    aplicar_confirmacao_alocacao,
)
from magnata_os.documental.alocacao.eventos import (
    AlocacaoIniciada,
    ConflitoTemporalEventoError,
    VinculoEncerrado,
    VinculoIniciado,
)
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


# ============================================================================
# Missão "CAPTURA AUTOMÁTICA DE VÍNCULO E ALOCAÇÃO V1" -- eventos.py +
# captura.py contra Postgres real (subconjunto do que já é provado
# exaustivamente via SQLite em test_magnata_os_documental_alocacao_captura_v1.py;
# aqui só confirma que a mesma lógica funciona contra o banco de
# verdade -- idempotência real, transferência real, conflito real).
# ============================================================================

def test_admissao_real_e_idempotente_contra_postgres(repo):
    colab = 'colab-captura-pg-1'
    id1 = aplicar_vinculo_iniciado(repo, VinculoIniciado(colab, date(2026, 1, 1), 'sintetico'))
    id2 = aplicar_vinculo_iniciado(repo, VinculoIniciado(colab, date(2026, 1, 1), 'sintetico'))
    assert id1 == id2
    assert repo.vinculo_mais_recente_de(colab).id == id1


def test_transferencia_real_fecha_a_e_abre_b_contra_postgres(repo):
    colab = 'colab-captura-pg-2'
    aplicar_vinculo_iniciado(repo, VinculoIniciado(colab, date(2026, 1, 1), 'sintetico'))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(colab, 'posto-pg-cap-A', date(2026, 1, 1), 'sintetico'))
    aplicar_transferencia(repo, colab, 'posto-pg-cap-A', 'posto-pg-cap-B', date(2026, 6, 15), 'sintetico')

    vinculo = repo.vinculo_mais_recente_de(colab)
    a = repo.alocacao_mais_recente_de(vinculo.id, 'posto-pg-cap-A')
    b = repo.alocacao_mais_recente_de(vinculo.id, 'posto-pg-cap-B')
    assert a.vigente_ate == date(2026, 6, 15)
    assert b.vigente_de == date(2026, 6, 15)
    assert b.vigente_ate is None


def test_readmissao_real_cria_novo_vinculo_contra_postgres(repo):
    colab = 'colab-captura-pg-3'
    id1 = aplicar_vinculo_iniciado(repo, VinculoIniciado(colab, date(2025, 1, 1), 'sintetico'))
    aplicar_vinculo_encerrado(repo, VinculoEncerrado(colab, date(2025, 6, 30), 'sintetico'))
    id2 = aplicar_vinculo_iniciado(repo, VinculoIniciado(colab, date(2026, 1, 1), 'sintetico'))
    assert id1 != id2
    recente = repo.vinculo_mais_recente_de(colab)
    assert recente.id == id2
    assert recente.data_desligamento is None


def test_conflito_temporal_real_e_rejeitado_contra_postgres(repo):
    colab = 'colab-captura-pg-4'
    aplicar_vinculo_iniciado(repo, VinculoIniciado(colab, date(2026, 1, 1), 'sintetico'))
    aplicar_vinculo_encerrado(repo, VinculoEncerrado(colab, date(2026, 6, 30), 'sintetico'))
    with pytest.raises(ConflitoTemporalEventoError):
        aplicar_vinculo_encerrado(repo, VinculoEncerrado(colab, date(2026, 7, 15), 'sintetico'))


# ============================================================================
# Missão "REVISÃO OBRIGATÓRIA PR #114 -- ATOMICIDADE DA TRANSFERÊNCIA" --
# contra Postgres real (transação real do banco, não simulada).
# ============================================================================

def test_falha_simulada_na_transferencia_mantem_a_aberta_contra_postgres_real(repo):
    colab = 'colab-captura-pg-5'
    aplicar_vinculo_iniciado(repo, VinculoIniciado(colab, date(2026, 1, 1), 'sintetico'))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(colab, 'posto-pg-atom-A', date(2026, 1, 1), 'sintetico'))

    with mock.patch.object(repo, 'registrar_alocacao', side_effect=RuntimeError('falha simulada na abertura de B')):
        with pytest.raises(RuntimeError):
            aplicar_transferencia(repo, colab, 'posto-pg-atom-A', 'posto-pg-atom-B', date(2026, 6, 15), 'sintetico')

    vinculo = repo.vinculo_mais_recente_de(colab)
    a = repo.alocacao_mais_recente_de(vinculo.id, 'posto-pg-atom-A')
    b = repo.alocacao_mais_recente_de(vinculo.id, 'posto-pg-atom-B')
    assert a.vigente_ate is None  # ROLLBACK real do Postgres reverteu o fechamento de A
    assert b is None


def test_retry_completo_apos_falha_real_no_postgres(repo):
    colab = 'colab-captura-pg-6'
    aplicar_vinculo_iniciado(repo, VinculoIniciado(colab, date(2026, 1, 1), 'sintetico'))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(colab, 'posto-pg-atom-C', date(2026, 1, 1), 'sintetico'))

    with mock.patch.object(repo, 'registrar_alocacao', side_effect=RuntimeError('falha simulada')):
        with pytest.raises(RuntimeError):
            aplicar_transferencia(repo, colab, 'posto-pg-atom-C', 'posto-pg-atom-D', date(2026, 6, 15), 'sintetico')

    aplicar_transferencia(repo, colab, 'posto-pg-atom-C', 'posto-pg-atom-D', date(2026, 6, 15), 'sintetico')

    vinculo = repo.vinculo_mais_recente_de(colab)
    c = repo.alocacao_mais_recente_de(vinculo.id, 'posto-pg-atom-C')
    d = repo.alocacao_mais_recente_de(vinculo.id, 'posto-pg-atom-D')
    assert c.vigente_ate == date(2026, 6, 15)
    assert d.vigente_de == date(2026, 6, 15)
    assert d.vigente_ate is None


# ============================================================================
# Missão "CONFIRMAÇÃO DE ALOCAÇÃO SHADOW V1" -- confirmacao.py contra
# Postgres real (FASE 9 da missão): confirmação, persistência,
# transferência atômica, rateio, idempotência, conflito e rollback --
# tudo sintético, reaproveitando o MESMO job/fixture `repo` já
# existente (nenhum job novo criado).
# ============================================================================

class _ResolverSinteticoPg:
    """Mesmo papel de `_ResolverSintetico` em
    `test_magnata_os_documental_alocacao_confirmacao_shadow_v1.py` --
    duplicado aqui (arquivo isolado, roda só sob
    `MAGNATA_TEST_POSTGRES_REAL`) para não criar um import cruzado
    entre os dois arquivos de teste."""

    def __init__(self, colaboradores_existentes: set, postos_existentes: set):
        self._colaboradores_existentes = colaboradores_existentes
        self._postos_existentes = postos_existentes

    def confirmar_colaborador_existe(self, colaborador_id: str) -> bool:
        return colaborador_id in self._colaboradores_existentes

    def confirmar_posto_existe(self, posto_id: str) -> bool:
        return posto_id in self._postos_existentes


def test_confirmacao_iniciar_e_idempotente_contra_postgres(repo):
    colab = 'colab-confirmacao-pg-1'
    resolver = _ResolverSinteticoPg({colab}, {'posto-conf-pg-A'})
    aplicar_vinculo_iniciado(repo, VinculoIniciado(colab, date(2026, 1, 1), 'sintetico'))
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=colab, posto_id='posto-conf-pg-A', data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao='confirmacao_humana_shadow',
    )
    id1 = aplicar_confirmacao_alocacao(repo, resolver, solicitacao)
    id2 = aplicar_confirmacao_alocacao(repo, resolver, solicitacao)
    assert id1 == id2
    vinculo = repo.vinculo_mais_recente_de(colab)
    assert repo.alocacao_mais_recente_de(vinculo.id, 'posto-conf-pg-A').id == id1


def test_confirmacao_rateio_dois_postos_abertos_contra_postgres(repo):
    colab = 'colab-confirmacao-pg-2'
    resolver = _ResolverSinteticoPg({colab}, {'posto-conf-pg-A', 'posto-conf-pg-B'})
    aplicar_vinculo_iniciado(repo, VinculoIniciado(colab, date(2026, 1, 1), 'sintetico'))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=colab, posto_id='posto-conf-pg-A', data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao='confirmacao_humana_shadow',
    ))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=colab, posto_id='posto-conf-pg-B', data_efetiva=date(2026, 2, 1),
        acao=ACAO_ADICIONAR_RATEIO, origem_confirmacao='confirmacao_humana_shadow',
    ))
    vinculo = repo.vinculo_mais_recente_de(colab)
    a = repo.alocacao_mais_recente_de(vinculo.id, 'posto-conf-pg-A')
    b = repo.alocacao_mais_recente_de(vinculo.id, 'posto-conf-pg-B')
    assert a.vigente_ate is None
    assert b.vigente_ate is None


def test_confirmacao_transferencia_atomica_contra_postgres(repo):
    colab = 'colab-confirmacao-pg-3'
    resolver = _ResolverSinteticoPg({colab}, {'posto-conf-pg-C', 'posto-conf-pg-D'})
    aplicar_vinculo_iniciado(repo, VinculoIniciado(colab, date(2026, 1, 1), 'sintetico'))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=colab, posto_id='posto-conf-pg-C', data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao='confirmacao_humana_shadow',
    ))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=colab, posto_id='posto-conf-pg-C', data_efetiva=date(2026, 6, 15),
        acao=ACAO_TRANSFERIR, origem_confirmacao='confirmacao_humana_shadow',
        posto_destino_id='posto-conf-pg-D',
    ))
    vinculo = repo.vinculo_mais_recente_de(colab)
    c = repo.alocacao_mais_recente_de(vinculo.id, 'posto-conf-pg-C')
    d = repo.alocacao_mais_recente_de(vinculo.id, 'posto-conf-pg-D')
    assert c.vigente_ate == date(2026, 6, 15)
    assert d.vigente_de == date(2026, 6, 15)
    assert d.vigente_ate is None


def test_confirmacao_transferencia_com_falha_real_faz_rollback_contra_postgres(repo):
    colab = 'colab-confirmacao-pg-4'
    resolver = _ResolverSinteticoPg({colab}, {'posto-conf-pg-E', 'posto-conf-pg-F'})
    aplicar_vinculo_iniciado(repo, VinculoIniciado(colab, date(2026, 1, 1), 'sintetico'))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=colab, posto_id='posto-conf-pg-E', data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao='confirmacao_humana_shadow',
    ))
    transferencia = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=colab, posto_id='posto-conf-pg-E', data_efetiva=date(2026, 6, 15),
        acao=ACAO_TRANSFERIR, origem_confirmacao='confirmacao_humana_shadow',
        posto_destino_id='posto-conf-pg-F',
    )
    with mock.patch.object(repo, 'registrar_alocacao', side_effect=RuntimeError('falha simulada na abertura de F')):
        with pytest.raises(RuntimeError):
            aplicar_confirmacao_alocacao(repo, resolver, transferencia)

    vinculo = repo.vinculo_mais_recente_de(colab)
    e = repo.alocacao_mais_recente_de(vinculo.id, 'posto-conf-pg-E')
    f = repo.alocacao_mais_recente_de(vinculo.id, 'posto-conf-pg-F')
    assert e.vigente_ate is None  # ROLLBACK real do Postgres reverteu o fechamento de E
    assert f is None

    # retry, sem a falha -- completa normalmente
    aplicar_confirmacao_alocacao(repo, resolver, transferencia)
    e = repo.alocacao_mais_recente_de(vinculo.id, 'posto-conf-pg-E')
    f = repo.alocacao_mais_recente_de(vinculo.id, 'posto-conf-pg-F')
    assert e.vigente_ate == date(2026, 6, 15)
    assert f.vigente_de == date(2026, 6, 15)


def test_confirmacao_conflito_temporal_real_e_rejeitado_contra_postgres(repo):
    colab = 'colab-confirmacao-pg-5'
    resolver = _ResolverSinteticoPg({colab}, {'posto-conf-pg-G'})
    aplicar_vinculo_iniciado(repo, VinculoIniciado(colab, date(2026, 1, 1), 'sintetico'))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=colab, posto_id='posto-conf-pg-G', data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao='confirmacao_humana_shadow',
    ))
    with pytest.raises(ConflitoTemporalEventoError):
        aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
            colaborador_id=colab, posto_id='posto-conf-pg-G', data_efetiva=date(2026, 3, 1),
            acao=ACAO_INICIAR, origem_confirmacao='confirmacao_humana_shadow',
        ))


def test_confirmacao_colaborador_nao_identificado_nao_escreve_nada_no_postgres(repo):
    resolver = _ResolverSinteticoPg(set(), {'posto-conf-pg-H'})
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id='colab-confirmacao-pg-6', posto_id='posto-conf-pg-H', data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao='confirmacao_humana_shadow',
    )
    with pytest.raises(ColaboradorNaoIdentificadoError):
        aplicar_confirmacao_alocacao(repo, resolver, solicitacao)
    assert repo.vinculo_mais_recente_de('colab-confirmacao-pg-6') is None


def test_comparacao_shadow_airtable_consistente_contra_postgres(repo):
    colab = 'colab-confirmacao-pg-7'
    resolver = _ResolverSinteticoPg({colab}, {'posto-conf-pg-I'})
    aplicar_vinculo_iniciado(repo, VinculoIniciado(colab, date(2026, 1, 1), 'sintetico'))
    aplicar_confirmacao_alocacao(repo, resolver, SolicitacaoConfirmacaoAlocacao(
        colaborador_id=colab, posto_id='posto-conf-pg-I', data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao='confirmacao_humana_shadow',
    ))

    class _SnapshotSintetico:
        def postos_atuais_do_colaborador(self, colaborador_id: str):
            return frozenset({'posto-conf-pg-I'})

    estado = comparar_colaborador_shadow_com_airtable(repo, _SnapshotSintetico(), colab, date(2026, 3, 1))
    assert estado == EstadoComparacaoAirtable.CONSISTENTE


# ============================================================================
# Missão "FUNDAÇÃO TEMPORAL POSTO ↔ CLIENTE V1" -- Migration 0002 +
# resolvedor temporal contra Postgres real (validação de migration real,
# constraints, LEFT JOIN semântica, segmentação temporal com lacunas).
# ============================================================================

_MIGRATION_SQL_0002 = (Path(__file__).parent / 'magnata_os' / 'documental' / 'alocacao' / 'migrations' / '0002_criar_vigencia_cliente_por_posto.sql').read_text(encoding='utf-8')
_ROLLBACK_SQL_0002 = (Path(__file__).parent / 'magnata_os' / 'documental' / 'alocacao' / 'migrations' / '0002_criar_vigencia_cliente_por_posto_rollback.sql').read_text(encoding='utf-8')


def _aplicar_migration_0002(conn) -> None:
    _executar_script_sql(conn, _MIGRATION_SQL_0002)


def _aplicar_rollback_0002(conn) -> None:
    _executar_script_sql(conn, _ROLLBACK_SQL_0002)


@pytest.fixture
def pg_conn_com_vigencia_cliente(pg_conn):
    """Estende pg_conn com migration 0002 aplicada (vigencia_cliente_por_posto)."""
    _aplicar_rollback_0002(pg_conn)  # garantir banco/schema vazio no inicio
    _aplicar_migration_0002(pg_conn)
    yield pg_conn
    pg_conn.rollback()
    _aplicar_rollback_0002(pg_conn)
    pg_conn.close()


def test_migration_0002_cria_tabela_vigencia_cliente_por_posto(pg_conn_com_vigencia_cliente):
    """Migration 0002 cria tabela vigencia_cliente_por_posto com schema correto."""
    with pg_conn_com_vigencia_cliente.cursor() as cur:
        cur.execute("SELECT to_regclass('vigencia_cliente_por_posto')")
        assert cur.fetchone()[0] is not None


def test_migration_0002_check_vigente_ate_valido(pg_conn_com_vigencia_cliente):
    """CHECK constraint rejeita vigente_ate < vigente_de."""
    with pg_conn_com_vigencia_cliente.cursor() as cur:
        with pytest.raises(Exception):  # psycopg levanta exceção de constraint
            cur.execute(
                "INSERT INTO vigencia_cliente_por_posto (id, posto_id, cliente_id, vigente_de, vigente_ate, origem_evidencia) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                ('vc-check-err', 'p1', 'c1', date(2026, 6, 30), date(2026, 6, 1), 'teste'),
            )
        pg_conn_com_vigencia_cliente.rollback()


def test_migration_0002_exclude_rejeita_sobreposicao_mesmo_posto(pg_conn_com_vigencia_cliente):
    """EXCLUDE constraint rejeita dois clientes DIFERENTES sobrepostos no MESMO POSTO."""
    with pg_conn_com_vigencia_cliente.cursor() as cur:
        # Inserir primeiro cliente
        cur.execute(
            "INSERT INTO vigencia_cliente_por_posto (id, posto_id, cliente_id, vigente_de, vigente_ate, origem_evidencia) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            ('vc1', 'posto-exclus', 'cliente-A', date(2026, 6, 1), date(2026, 6, 30), 'teste'),
        )
        pg_conn_com_vigencia_cliente.commit()

        # Tentar inserir segundo cliente sobrepostoño mesmo posto
        with pytest.raises(Exception):  # EXCLUDE levanta erro
            cur.execute(
                "INSERT INTO vigencia_cliente_por_posto (id, posto_id, cliente_id, vigente_de, vigente_ate, origem_evidencia) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                ('vc2', 'posto-exclus', 'cliente-B', date(2026, 6, 15), date(2026, 7, 15), 'teste'),
            )
        pg_conn_com_vigencia_cliente.rollback()


def test_migration_0002_multiplos_postos_simultaneos_permitidos(pg_conn_com_vigencia_cliente):
    """Múltiplos postos podem ter clientes vigentes simultaneamente (rateio)."""
    with pg_conn_com_vigencia_cliente.cursor() as cur:
        cur.execute(
            "INSERT INTO vigencia_cliente_por_posto (id, posto_id, cliente_id, vigente_de, vigente_ate, origem_evidencia) "
            "VALUES (%s, %s, %s, %s, %s, %s), (%s, %s, %s, %s, %s, %s)",
            ('vc-multi-1', 'posto-A', 'cliente-X', date(2026, 6, 1), date(2026, 12, 31), 'teste',
             'vc-multi-2', 'posto-B', 'cliente-X', date(2026, 6, 1), date(2026, 12, 31), 'teste'),
        )
        pg_conn_com_vigencia_cliente.commit()

        cur.execute("SELECT COUNT(*) FROM vigencia_cliente_por_posto WHERE cliente_id = 'cliente-X'")
        assert cur.fetchone()[0] == 2


def test_left_join_sem_cliente_retorna_alocacao_com_null(pg_conn_com_vigencia_cliente, repo):
    """LEFT JOIN sem match em vigencia_cliente_por_posto retorna alocacao com cliente_id=NULL."""
    # Preparar dados: vínculo + alocação, mas SEM entrada em vigencia_cliente_por_posto
    repo.registrar_vinculo('v-left-join', 'colab-left-join', date(2026, 1, 1))
    repo.registrar_alocacao('a-left-join', 'v-left-join', 'posto-left-join', date(2026, 6, 1), date(2026, 6, 30))

    # Consultar com listar_alocacoes_com_clientes_para_colaborador
    resultado = repo.listar_alocacoes_com_clientes_para_colaborador(
        'colab-left-join',
        date(2026, 6, 1),
        date(2026, 6, 30)
    )

    # LEFT JOIN sem match = 1 row com cliente_id=NULL
    assert len(resultado) == 1
    assert resultado[0].cliente_id is None
    assert resultado[0].alocacao_vigente_de == date(2026, 6, 1)


def test_resolvedor_segmentos_com_2_clientes_e_lacuna(pg_conn_com_vigencia_cliente, repo):
    """Cenário obrigatório: alocação 01/06→31/07 + A (01/06→30/06) + B (05/07→31/07).
    Resolvedor materializa 3 segmentos: A-COMPROVADO, LACUNA, B-COMPROVADO.
    """
    from magnata_os.documental.alocacao.resolucao_segmentos_temporais import materializar_segmentos_alocacao_com_cliente
    from datetime import timedelta

    # Preparar dados
    repo.registrar_vinculo('v-cenario', 'colab-cenario', date(2026, 1, 1))
    repo.registrar_alocacao('a-cenario', 'v-cenario', 'posto-cenario', date(2026, 6, 1), date(2026, 7, 31))

    # Registrar vigências de cliente
    with pg_conn_com_vigencia_cliente.cursor() as cur:
        cur.execute(
            "INSERT INTO vigencia_cliente_por_posto (id, posto_id, cliente_id, vigente_de, vigente_ate, origem_evidencia) "
            "VALUES (%s, %s, %s, %s, %s, %s), (%s, %s, %s, %s, %s, %s)",
            ('vc-cenario-A', 'posto-cenario', 'cliente-A', date(2026, 6, 1), date(2026, 6, 30), 'teste',
             'vc-cenario-B', 'posto-cenario', 'cliente-B', date(2026, 7, 5), date(2026, 7, 31), 'teste'),
        )
        pg_conn_com_vigencia_cliente.commit()

    # Obter tuplas via adapter
    tuplas = repo.listar_alocacoes_com_clientes_para_colaborador(
        'colab-cenario',
        date(2026, 6, 1),
        date(2026, 7, 31)
    )

    # Materializar segmentos
    segmentos = materializar_segmentos_alocacao_com_cliente(
        alocacao_id='a-cenario',
        posto_id='posto-cenario',
        vigente_de=date(2026, 6, 1),
        vigente_ate=date(2026, 7, 31),
        janela_inicio=date(2026, 6, 1),
        janela_fim=date(2026, 7, 31),
        tuplas_do_adapter=tuplas
    )

    # Validar 3 segmentos: A, LACUNA, B
    assert len(segmentos) == 3

    # Segmento 1: Cliente A (01/06 → 30/06)
    assert segmentos[0].cliente_id == 'cliente-A'
    assert segmentos[0].segmento_de == date(2026, 6, 1)
    assert segmentos[0].segmento_ate == date(2026, 6, 30)
    assert str(segmentos[0].status) == 'StatusSegmentoTemporal.COMPROVADO'

    # Segmento 2: Lacuna (01/07 → 04/07)
    assert segmentos[1].cliente_id is None
    assert segmentos[1].segmento_de == date(2026, 7, 1)
    assert segmentos[1].segmento_ate == date(2026, 7, 4)
    assert str(segmentos[1].status) == 'StatusSegmentoTemporal.HISTORICO_NAO_COMPROVADO'

    # Segmento 3: Cliente B (05/07 → 31/07)
    assert segmentos[2].cliente_id == 'cliente-B'
    assert segmentos[2].segmento_de == date(2026, 7, 5)
    assert segmentos[2].segmento_ate == date(2026, 7, 31)
    assert str(segmentos[2].status) == 'StatusSegmentoTemporal.COMPROVADO'

    # Validar cobertura integral
    soma_dias = (
        (segmentos[0].segmento_ate - segmentos[0].segmento_de).days + 1 +
        (segmentos[1].segmento_ate - segmentos[1].segmento_de).days + 1 +
        (segmentos[2].segmento_ate - segmentos[2].segmento_de).days + 1
    )
    esperado_dias = (date(2026, 7, 31) - date(2026, 6, 1)).days + 1
    assert soma_dias == esperado_dias


def test_migration_0002_rollback_remove_vigencia_cliente_por_posto(pg_conn_com_vigencia_cliente):
    """Rollback 0002 remove tabela vigencia_cliente_por_posto."""
    _aplicar_rollback_0002(pg_conn_com_vigencia_cliente)
    with pg_conn_com_vigencia_cliente.cursor() as cur:
        cur.execute("SELECT to_regclass('vigencia_cliente_por_posto')")
        assert cur.fetchone()[0] is None
