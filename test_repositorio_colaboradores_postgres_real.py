"""Cadastro de Colaborador PERSISTENTE V1 contra PostgreSQL REAL e
efêmero: migration 0001 (rh_admissao) e o adapter
`RepositorioColaboradoresPostgres`.

Mesma disciplina dos demais `*_real.py`: só roda com
`MAGNATA_TEST_POSTGRES_REAL=1` e conexão libpq (`PG*`) de um banco de
teste descartável; aplica a migration só se a tabela não existir; nunca
faz DROP/TRUNCATE; ids aleatórios por teste. Dados 100% sintéticos.
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
from magnata_os.rh_admissao.dominio_cadastro_colaborador import (  # noqa: E402
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


def _aplicar_migration_se_ausente(conn):
    with conn.cursor() as cursor:
        cursor.execute('SELECT to_regclass(%s)', ('rh_admissao_colaboradores',))
        if cursor.fetchone()[0] is None:
            cursor.execute((_RAIZ / '0001_criar_tabela_colaboradores.sql').read_text(encoding='utf-8'))
    conn.commit()


@pytest.fixture
def conexao():
    conn = psycopg.connect(cursor_factory=psycopg.ClientCursor)
    _aplicar_migration_se_ausente(conn)
    try:
        yield conn
    finally:
        conn.close()


def _dados(colaborador_id):
    return DadosColaboradorKitAdmissao(colaborador_id, CPF_SINTETICO, 'colaborador sintetico teste', 'Vigia')


def test_salvar_e_buscar_colaborador_pendente(conexao):
    colaborador_id = f'colab-real-{uuid.uuid4()}'
    repo = RepositorioColaboradoresPostgres(conexao)
    colaborador = compor_colaborador_a_partir_do_kit(
        _dados(colaborador_id), None, agora=dt.datetime.now(dt.timezone.utc),
    )

    repo.salvar(colaborador)
    persistido = repo.buscar_por_id(colaborador_id)

    assert persistido is not None
    assert persistido.situacao_cadastro == SituacaoCadastroColaborador.AGUARDANDO_LOCAL_TRABALHO
    assert persistido.local_trabalho is None


def test_salvar_e_idempotente_por_colaborador_id(conexao):
    colaborador_id = f'colab-real-{uuid.uuid4()}'
    repo = RepositorioColaboradoresPostgres(conexao)
    determinacao = DeterminacaoLocalTrabalho(
        'Escala A - Dias Pares', 'operador.rh@magnataservicos.com.br', dt.datetime.now(dt.timezone.utc),
    )
    colaborador = compor_colaborador_a_partir_do_kit(_dados(colaborador_id), determinacao, agora=dt.datetime.now(dt.timezone.utc))

    repo.salvar(colaborador)
    repo.salvar(colaborador)  # reprocessar o mesmo kit -- upsert, nunca duplica linha

    assert len([c for c in repo.listar() if c.colaborador_id == colaborador_id]) == 1


def test_correcao_de_local_trabalho_e_persistida(conexao):
    colaborador_id = f'colab-real-{uuid.uuid4()}'
    repo = RepositorioColaboradoresPostgres(conexao)
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
    repo = RepositorioColaboradoresPostgres(conexao)
    id_a, id_b = f'colab-real-{uuid.uuid4()}', f'colab-real-{uuid.uuid4()}'
    repo.salvar(compor_colaborador_a_partir_do_kit(_dados(id_a), None, agora=dt.datetime.now(dt.timezone.utc)))
    repo.salvar(compor_colaborador_a_partir_do_kit(_dados(id_b), None, agora=dt.datetime.now(dt.timezone.utc)))

    ids = {c.colaborador_id for c in repo.listar()}
    assert {id_a, id_b} <= ids
