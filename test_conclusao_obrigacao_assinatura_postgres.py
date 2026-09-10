"""RepositorioConclusaoObrigacaoAssinaturaPostgres: append-only, sem
UPDATE/DELETE, recuperável após restart só a partir do Postgres.

Testes com fake DB-API (unitários, sempre rodam) + teste real opcional
contra Postgres efêmero (MAGNATA_TEST_POSTGRES_REAL), mesmo padrão já
usado pelos outros `_real` do Orquestrador.
"""
import os
from datetime import datetime, timezone

import pytest

from magnata_os.orquestrador.adapters.postgres_conclusao_obrigacao_assinatura import (
    RegistroConclusaoObrigacaoAssinatura,
    RepositorioConclusaoObrigacaoAssinaturaPostgres,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)


class _Cursor:
    def __init__(self, conexao):
        self.conexao = conexao

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.conexao.executados.append((sql, params))

    def fetchall(self):
        return self.conexao.linhas


class _Conexao:
    def __init__(self, linhas=()):
        self.linhas = list(linhas)
        self.executados = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_registro_rejeita_estado_fora_do_vocabulario_fechado():
    with pytest.raises(ValueError):
        RegistroConclusaoObrigacaoAssinatura(
            acao_execucao_id='a' * 64, estado='ESTADO_INVENTADO',
            correlacao_externa=None, evidencia_sha256=None, registrado_em=AGORA,
        )


def test_registrar_transicao_faz_insert_e_commit_nunca_update():
    conexao = _Conexao()
    repo = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao)
    repo.registrar_transicao(RegistroConclusaoObrigacaoAssinatura(
        acao_execucao_id='a' * 64, estado='AGUARDANDO_ASSINATURA',
        correlacao_externa='rec1', evidencia_sha256=None, registrado_em=AGORA,
    ))
    sql, _ = conexao.executados[0]
    assert sql.strip().upper().startswith('INSERT')
    assert 'UPDATE' not in sql.upper()
    assert conexao.commits == 1


def test_estado_mais_recente_e_a_ultima_linha_nunca_a_primeira():
    conexao = _Conexao(linhas=[
        ('a' * 64, 'AGUARDANDO_ASSINATURA', 'rec1', None, AGORA),
        ('a' * 64, 'ASSINADO', 'rec1', None, AGORA),
        ('a' * 64, 'COMPROVANTE_VALIDADO', 'rec1', 'e' * 64, AGORA),
        ('a' * 64, 'CONCLUIDO', 'rec1', 'e' * 64, AGORA),
    ])
    repo = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao)
    assert repo.estado_mais_recente('a' * 64) == 'CONCLUIDO'


def test_estado_mais_recente_sem_historico_e_none():
    conexao = _Conexao(linhas=[])
    repo = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao)
    assert repo.estado_mais_recente('a' * 64) is None


# ---- validação real contra Postgres efêmero (opcional) -----------------

def _aplicar_migration_se_ausente(conexao, nome_arquivo, tabela_alvo):
    """Mesmo padrão já usado pelos outros `_real` do Orquestrador: checa
    `to_regclass` da tabela que a PRÓPRIA migration cria antes de
    reaplicar -- nunca presume que a cadeia inteira está consistente só
    porque a primeira migration está presente (o achado adversarial já
    documentado em `ativacao-persistencia-executor-orquestrador-v1.md`
    é exatamente checar a dependência errada)."""
    with conexao.cursor() as cursor:
        cursor.execute(f"SELECT to_regclass('{tabela_alvo}')")
        if cursor.fetchone()[0] is not None:
            return
    base = os.path.join(os.path.dirname(__file__), 'magnata_os', 'orquestrador', 'migrations')
    with open(os.path.join(base, nome_arquivo)) as arquivo, conexao.cursor() as cursor:
        cursor.execute(arquivo.read())
    conexao.commit()


def _aplicar_migrations_se_ausentes(conexao):
    for nome, tabela in (
        ('0001_repositorio_execucoes.sql', 'magnata_orquestrador.execucoes'),
        ('0002_autorizacoes_gate.sql', 'magnata_orquestrador.autorizacoes_gate'),
        ('0003_acoes_execucao_plano.sql', 'magnata_orquestrador.acoes_execucao_plano'),
        ('0006_conclusao_obrigacao_assinatura.sql', 'magnata_orquestrador.conclusao_obrigacao_assinatura'),
    ):
        _aplicar_migration_se_ausente(conexao, nome, tabela)
    # 0004 só adiciona uma coluna a uma tabela já existente -- checagem
    # própria, não por to_regclass de tabela.
    with conexao.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='magnata_orquestrador' "
            "AND table_name='acoes_execucao_plano' AND column_name='envelope_sha256'"
        )
        if cursor.fetchone() is None:
            base = os.path.join(os.path.dirname(__file__), 'magnata_os', 'orquestrador', 'migrations')
            with open(os.path.join(base, '0004_envelope_execucao_autorizada.sql')) as arquivo:
                cursor.execute(arquivo.read())
            conexao.commit()


@pytest.mark.skipif(
    not os.environ.get('MAGNATA_TEST_POSTGRES_REAL'),
    reason='requer MAGNATA_TEST_POSTGRES_REAL=1 e variáveis PG* padrão de libpq',
)
def test_real_append_only_e_recuperavel_apos_reconectar():
    import psycopg

    # Mesma convenção já usada por todos os outros `_real` do repositório
    # (ver .github/workflows/magnata-testes.yml): psycopg.connect() sem
    # argumento nenhum lê PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE.
    # MAGNATA_TEST_POSTGRES_REAL é só o flag liga/desliga, nunca uma URL.
    conexao = psycopg.connect(autocommit=False)
    _aplicar_migrations_se_ausentes(conexao)

    with conexao.cursor() as cursor:
        cursor.execute(
            "INSERT INTO magnata_orquestrador.execucoes "
            "(event_id, event_type, estado, nivel_autonomia, acao, attempt, criado_em, atualizado_em) "
            "VALUES ('ev-real-1','COMUNICACAO_SOLICITADA','SUCCEEDED',0,'x',0, now(), now()) "
            "ON CONFLICT (event_id) DO NOTHING"
        )
        cursor.execute(
            "INSERT INTO magnata_orquestrador.autorizacoes_gate "
            "(autorizacao_id, event_id, preview_id, decisao, ator_referencia, registrado_em, proveniencia) "
            "VALUES ('auth-real-1','ev-real-1','preview-real-1','AUTORIZADO','ator:teste', now(), 'teste') "
            "ON CONFLICT (autorizacao_id) DO NOTHING"
        )
        cursor.execute(
            "INSERT INTO magnata_orquestrador.acoes_execucao_plano "
            "(acao_execucao_id, event_id, preview_id, autorizacao_id, ordem, tipo, "
            "destinatario_sha256, texto_sha256, estado, attempt, criado_em, atualizado_em, concluido_em) "
            "VALUES (%s, 'ev-real-1', 'preview-real-1', 'auth-real-1', 1, 'texto', %s, %s, "
            "'SUCCEEDED', 1, now(), now(), now()) ON CONFLICT (acao_execucao_id) DO NOTHING",
            ('f' * 64, 'b' * 64, 'c' * 64),
        )
    conexao.commit()

    repo = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao)
    repo.registrar_transicao(RegistroConclusaoObrigacaoAssinatura(
        acao_execucao_id='f' * 64, estado='AGUARDANDO_ASSINATURA',
        correlacao_externa='rec-real', evidencia_sha256=None,
        registrado_em=datetime.now(timezone.utc),
    ))
    repo.registrar_transicao(RegistroConclusaoObrigacaoAssinatura(
        acao_execucao_id='f' * 64, estado='CONCLUIDO',
        correlacao_externa='rec-real', evidencia_sha256='e' * 64,
        registrado_em=datetime.now(timezone.utc),
    ))

    with pytest.raises(Exception):
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE magnata_orquestrador.conclusao_obrigacao_assinatura SET estado='ASSINADO'"
            )
    conexao.rollback()

    # Reabre uma conexão nova -- simula restart do processo -- e confirma
    # que o estado é recuperável só a partir do Postgres.
    conexao2 = psycopg.connect(autocommit=False)
    repo2 = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao2)
    assert repo2.estado_mais_recente('f' * 64) == 'CONCLUIDO'
    conexao2.close()
    conexao.close()
