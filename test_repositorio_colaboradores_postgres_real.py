"""Cadastro de Colaborador PERSISTENTE V1 contra PostgreSQL REAL e
efêmero: migrations 0001-0003 (rh_admissao) e o adapter
`RepositorioColaboradoresPostgres`.

Mesma disciplina dos demais `*_real.py`: só roda com
`MAGNATA_TEST_POSTGRES_REAL=1` e conexão libpq (`PG*`) de um banco de
teste descartável; aplica as migrations só se a tabela correspondente
não existir; nunca faz DROP/TRUNCATE; ids aleatórios por teste. Dados
100% sintéticos.

Cobre, além do já existente (salvar/buscar/listar, idempotência,
correção de local de trabalho): cifra de CPF em repouso (valor gravado
no banco nunca é o CPF em claro; leitura de volta decifra
corretamente; ausência da chave é fail-closed) e o histórico
append-only real de correção de local de trabalho (migration 0003).
"""
import datetime as dt
import os
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get('MAGNATA_TEST_POSTGRES_REAL'),
    reason='E2E habilitado somente contra PostgreSQL real e controlado',
)

psycopg = pytest.importorskip('psycopg', reason='driver psycopg (v3) nao instalado')

from magnata_os.rh_admissao.adapters.repositorio_colaboradores_postgres import (  # noqa: E402
    RepositorioColaboradoresPostgres,
)
from magnata_os.rh_admissao.configuracao_cpf_colaborador import (  # noqa: E402
    ConfiguracaoSegredoCpfColaborador,
    SegredoCpfColaboradorAusente,
)
from magnata_os.rh_admissao.dominio_cadastro_colaborador import (  # noqa: E402
    EventoCorrecaoLocalTrabalho,
    SituacaoCadastroColaborador,
    aplicar_determinacao_local_trabalho,
    compor_colaborador_a_partir_do_kit,
)
from magnata_os.rh_admissao.gatilho_admissao import (  # noqa: E402
    DadosColaboradorKitAdmissao,
    DeterminacaoLocalTrabalho,
)

_RAIZ = Path(__file__).parent / 'magnata_os' / 'rh_admissao' / 'migrations'
CPF_SINTETICO = '900.000.000-01'

# Chave sintética, só para este teste -- nunca a variável de ambiente
# real de produção (que este teste nem lê: a configuração é sempre
# injetada explicitamente via `ConfiguracaoSegredoCpfColaborador`,
# nunca `os.environ`, para nunca depender de segredo real em CI).
_CHAVE_TESTE = ConfiguracaoSegredoCpfColaborador(
    ambiente={'MAGNATA_RH_ADMISSAO_CPF_FERNET_CHAVE': 'chave-sintetica-de-teste-nao-usar-em-producao'},
)


def _aplicar_migration_se_ausente(conn, nome_tabela, nome_arquivo):
    with conn.cursor() as cursor:
        cursor.execute('SELECT to_regclass(%s)', (nome_tabela,))
        if cursor.fetchone()[0] is None:
            cursor.execute((_RAIZ / nome_arquivo).read_text(encoding='utf-8'))
    conn.commit()


def _aplicar_migrations(conn):
    _aplicar_migration_se_ausente(conn, 'rh_admissao_colaboradores', '0001_criar_tabela_colaboradores.sql')
    # 0002 (cifrar CPF) é idempotente por instrução -- sempre roda,
    # mesmo se 0001 acabou de criar a tabela sem linha alguma (ordem
    # normal de uma aplicação real: 0001 depois 0002).
    with conn.cursor() as cursor:
        cursor.execute((_RAIZ / '0002_cifrar_cpf_colaboradores.sql').read_text(encoding='utf-8'))
    conn.commit()
    _aplicar_migration_se_ausente(
        conn, 'rh_admissao_historico_correcao_local_trabalho',
        '0003_criar_historico_correcao_local_trabalho.sql',
    )


@pytest.fixture
def conexao():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _aplicar_migrations(conn)
    try:
        yield conn
    finally:
        conn.close()


def _dados(colaborador_id):
    return DadosColaboradorKitAdmissao(colaborador_id, CPF_SINTETICO, 'colaborador sintetico teste', 'Vigia')


def test_salvar_e_buscar_colaborador_pendente(conexao):
    colaborador_id = f'colab-real-{uuid.uuid4()}'
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CHAVE_TESTE)
    colaborador = compor_colaborador_a_partir_do_kit(
        _dados(colaborador_id), None, agora=dt.datetime.now(dt.timezone.utc),
    )

    repo.salvar(colaborador)
    persistido = repo.buscar_por_id(colaborador_id)

    assert persistido is not None
    assert persistido.situacao_cadastro == SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO
    assert persistido.local_trabalho is None
    assert persistido.cpf == CPF_SINTETICO


def test_salvar_e_idempotente_por_colaborador_id(conexao):
    colaborador_id = f'colab-real-{uuid.uuid4()}'
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CHAVE_TESTE)
    determinacao = DeterminacaoLocalTrabalho(
        'Escala A - Dias Pares', 'operador.rh@magnataservicos.com.br', dt.datetime.now(dt.timezone.utc),
    )
    colaborador = compor_colaborador_a_partir_do_kit(_dados(colaborador_id), determinacao, agora=dt.datetime.now(dt.timezone.utc))

    repo.salvar(colaborador)
    repo.salvar(colaborador)  # reprocessar o mesmo kit -- upsert, nunca duplica linha

    assert len([c for c in repo.listar() if c.colaborador_id == colaborador_id]) == 1


def test_correcao_de_local_trabalho_e_persistida(conexao):
    colaborador_id = f'colab-real-{uuid.uuid4()}'
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CHAVE_TESTE)
    primeira = DeterminacaoLocalTrabalho(
        'Escala A - Dias Pares', 'operador.rh@magnataservicos.com.br', dt.datetime.now(dt.timezone.utc),
    )
    colaborador = compor_colaborador_a_partir_do_kit(_dados(colaborador_id), primeira, agora=dt.datetime.now(dt.timezone.utc))
    repo.salvar(colaborador)

    segunda = DeterminacaoLocalTrabalho(
        'Escala B - Dias Impares', 'operador.rh@magnataservicos.com.br', dt.datetime.now(dt.timezone.utc),
    )
    existente = repo.buscar_por_id(colaborador_id)
    atualizado, evento = aplicar_determinacao_local_trabalho(
        existente, segunda, motivo_correcao='Colaborador transferido de posto',
    )
    repo.salvar(atualizado)

    persistido = repo.buscar_por_id(colaborador_id)
    assert persistido.local_trabalho == 'Escala B - Dias Impares'
    assert evento.local_trabalho_anterior == 'Escala A - Dias Pares'


def test_listar_devolve_todos_os_cadastrados_por_este_teste(conexao):
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CHAVE_TESTE)
    id_a, id_b = f'colab-real-{uuid.uuid4()}', f'colab-real-{uuid.uuid4()}'
    repo.salvar(compor_colaborador_a_partir_do_kit(_dados(id_a), None, agora=dt.datetime.now(dt.timezone.utc)))
    repo.salvar(compor_colaborador_a_partir_do_kit(_dados(id_b), None, agora=dt.datetime.now(dt.timezone.utc)))

    ids = {c.colaborador_id for c in repo.listar()}
    assert {id_a, id_b} <= ids


# ---- Cifra de CPF em repouso (item 1 da correção do PR #215) ----

def test_cpf_gravado_no_banco_nunca_e_texto_puro(conexao):
    colaborador_id = f'colab-real-{uuid.uuid4()}'
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CHAVE_TESTE)
    colaborador = compor_colaborador_a_partir_do_kit(
        _dados(colaborador_id), None, agora=dt.datetime.now(dt.timezone.utc),
    )
    repo.salvar(colaborador)

    with conexao.cursor() as cursor:
        cursor.execute(
            'SELECT cpf_cifrado FROM rh_admissao_colaboradores WHERE colaborador_id = %s',
            (colaborador_id,),
        )
        (cpf_cifrado,) = cursor.fetchone()

    cpf_cifrado_bytes = bytes(cpf_cifrado)
    assert CPF_SINTETICO.encode('utf-8') not in cpf_cifrado_bytes
    assert cpf_cifrado_bytes != CPF_SINTETICO.encode('utf-8')


def test_cpf_decifrado_na_leitura_bate_com_o_valor_original(conexao):
    colaborador_id = f'colab-real-{uuid.uuid4()}'
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CHAVE_TESTE)
    colaborador = compor_colaborador_a_partir_do_kit(
        _dados(colaborador_id), None, agora=dt.datetime.now(dt.timezone.utc),
    )
    repo.salvar(colaborador)

    persistido = repo.buscar_por_id(colaborador_id)
    assert persistido.cpf == CPF_SINTETICO

    (listado,) = [c for c in repo.listar() if c.colaborador_id == colaborador_id]
    assert listado.cpf == CPF_SINTETICO


def test_sem_chave_de_cifra_e_fail_closed_nunca_grava_nem_le(conexao):
    colaborador_id = f'colab-real-{uuid.uuid4()}'
    configuracao_sem_chave = ConfiguracaoSegredoCpfColaborador(ambiente={})
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=configuracao_sem_chave)
    colaborador = compor_colaborador_a_partir_do_kit(
        _dados(colaborador_id), None, agora=dt.datetime.now(dt.timezone.utc),
    )

    with pytest.raises(SegredoCpfColaboradorAusente):
        repo.salvar(colaborador)

    with conexao.cursor() as cursor:
        cursor.execute(
            'SELECT 1 FROM rh_admissao_colaboradores WHERE colaborador_id = %s',
            (colaborador_id,),
        )
        assert cursor.fetchone() is None  # nenhuma escrita parcial

    # buscar/listar também são fail-closed -- nunca leem sem chave,
    # mesmo que já exista alguma linha de outro teste na tabela.
    with pytest.raises(SegredoCpfColaboradorAusente):
        repo.buscar_por_id(colaborador_id)
    with pytest.raises(SegredoCpfColaboradorAusente):
        repo.listar()


# ---- Histórico append-only de correção de local de trabalho (item 2) ----

def test_correcao_registra_evento_no_historico_append_only(conexao):
    colaborador_id = f'colab-real-{uuid.uuid4()}'
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CHAVE_TESTE)
    primeira = DeterminacaoLocalTrabalho(
        'Escala A - Dias Pares', 'operador.rh@magnataservicos.com.br', dt.datetime.now(dt.timezone.utc),
    )
    colaborador = compor_colaborador_a_partir_do_kit(_dados(colaborador_id), primeira, agora=dt.datetime.now(dt.timezone.utc))
    repo.salvar(colaborador)

    segunda = DeterminacaoLocalTrabalho(
        'Escala B - Dias Impares', 'operador.rh@magnataservicos.com.br', dt.datetime.now(dt.timezone.utc),
    )
    existente = repo.buscar_por_id(colaborador_id)
    atualizado, evento = aplicar_determinacao_local_trabalho(
        existente, segunda, motivo_correcao='Colaborador transferido de posto',
    )
    repo.salvar(atualizado)
    repo.registrar_evento_correcao_local_trabalho(evento)

    historico = repo.listar_historico_correcao_local_trabalho(colaborador_id)
    assert len(historico) == 1
    assert historico[0].local_trabalho_anterior == 'Escala A - Dias Pares'
    assert historico[0].local_trabalho_novo == 'Escala B - Dias Impares'
    assert historico[0].motivo_correcao == 'Colaborador transferido de posto'


def test_historico_e_append_only_update_e_delete_sao_bloqueados_pelo_banco(conexao):
    colaborador_id = f'colab-real-{uuid.uuid4()}'
    repo = RepositorioColaboradoresPostgres(conexao, configuracao_segredo_cpf=_CHAVE_TESTE)
    colaborador = compor_colaborador_a_partir_do_kit(
        _dados(colaborador_id), None, agora=dt.datetime.now(dt.timezone.utc),
    )
    repo.salvar(colaborador)
    evento = EventoCorrecaoLocalTrabalho(
        colaborador_id=colaborador_id,
        local_trabalho_anterior='Escala A - Dias Pares',
        local_trabalho_novo='Escala B - Dias Impares',
        motivo_correcao='Teste de trigger append-only',
        determinado_por='operador.rh@magnataservicos.com.br',
        determinado_em=dt.datetime.now(dt.timezone.utc),
    )
    repo.registrar_evento_correcao_local_trabalho(evento)

    with pytest.raises(Exception):
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE rh_admissao_historico_correcao_local_trabalho "
                "SET motivo_correcao = 'adulterado' WHERE colaborador_id = %s",
                (colaborador_id,),
            )
    conexao.rollback()

    with pytest.raises(Exception):
        with conexao.cursor() as cursor:
            cursor.execute(
                'DELETE FROM rh_admissao_historico_correcao_local_trabalho WHERE colaborador_id = %s',
                (colaborador_id,),
            )
    conexao.rollback()

    historico = repo.listar_historico_correcao_local_trabalho(colaborador_id)
    assert len(historico) == 1
    assert historico[0].motivo_correcao == 'Teste de trigger append-only'
