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


# =====================================================================
# Gate 1 -- registro canônico da obrigação de assinatura. A EXISTÊNCIA
# da obrigação é estado persistido nesta tabela, correlacionado ao
# `acao_execucao_id` opaco -- nunca tipo documental, tipo físico da ação
# ou conteúdo.
# =====================================================================

import hashlib  # noqa: E402
import threading  # noqa: E402
import uuid  # noqa: E402

from magnata_os.orquestrador.adapters.postgres_conclusao_obrigacao_assinatura import (  # noqa: E402
    RepositorioConclusaoObrigacaoAssinaturaEmMemoria,
)


class _CursorRoteirizado:
    """Registra SQL e devolve, em ordem, os `fetchone` roteirizados."""

    def __init__(self, conexao):
        self.conexao = conexao

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.conexao.executados.append((' '.join(sql.split()), params))
        if self.conexao.falhar_em and self.conexao.falhar_em in sql:
            raise RuntimeError('falha sintetica de banco')

    def fetchone(self):
        return self.conexao.fetchones.pop(0)

    def fetchall(self):
        return self.conexao.linhas


class _ConexaoRoteirizada(_Conexao):
    def __init__(self, fetchones=(), falhar_em=None, linhas=()):
        super().__init__(linhas=linhas)
        self.fetchones = list(fetchones)
        self.falhar_em = falhar_em

    def cursor(self):
        return _CursorRoteirizado(self)


def _inserts(conexao):
    return [sql for sql, _ in conexao.executados if sql.upper().startswith('INSERT')]


def test_marcador_inicial_sem_historico_trava_le_e_insere_aguardando():
    conexao = _ConexaoRoteirizada(fetchones=[None])
    repo = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao)
    gravou = repo.registrar_obrigacao_inicial(
        acao_execucao_id='a' * 64, correlacao_externa='recOBRIG', registrado_em=AGORA,
    )
    assert gravou is True
    (lock_sql, lock_params), (ultimo_sql, _), (insert_sql, insert_params) = conexao.executados
    assert lock_sql.startswith('SELECT pg_advisory_xact_lock(') and lock_params == (6006, 'a' * 64)
    assert 'ORDER BY id DESC LIMIT 1' in ultimo_sql
    assert insert_sql.startswith('INSERT')
    assert insert_params[:3] == ('a' * 64, 'AGUARDANDO_ASSINATURA', 'recOBRIG')
    assert conexao.commits == 1  # o commit libera o advisory lock transacional


@pytest.mark.parametrize('ultimo', ['AGUARDANDO_ASSINATURA', 'ASSINADO', 'CONCLUIDO'])
def test_marcador_inicial_com_historico_nunca_duplica_nem_regride(ultimo):
    conexao = _ConexaoRoteirizada(fetchones=[(ultimo,)])
    repo = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao)
    assert repo.registrar_obrigacao_inicial(
        acao_execucao_id='a' * 64, correlacao_externa='recOBRIG', registrado_em=AGORA,
    ) is False
    assert _inserts(conexao) == []
    assert conexao.commits == 1


def test_transicao_se_mudou_so_insere_quando_difere_do_ultimo():
    registro = RegistroConclusaoObrigacaoAssinatura(
        acao_execucao_id='a' * 64, estado='ASSINADO', correlacao_externa='rec1',
        evidencia_sha256=None, registrado_em=AGORA,
    )
    igual = _ConexaoRoteirizada(fetchones=[('ASSINADO',)])
    assert RepositorioConclusaoObrigacaoAssinaturaPostgres(igual).registrar_transicao_se_mudou(registro) is False
    assert _inserts(igual) == []
    diferente = _ConexaoRoteirizada(fetchones=[('AGUARDANDO_ASSINATURA',)])
    assert RepositorioConclusaoObrigacaoAssinaturaPostgres(diferente).registrar_transicao_se_mudou(registro) is True
    assert len(_inserts(diferente)) == 1


def test_falha_no_insert_faz_rollback_e_propaga():
    conexao = _ConexaoRoteirizada(fetchones=[None], falhar_em='INSERT')
    repo = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao)
    with pytest.raises(RuntimeError):
        repo.registrar_obrigacao_inicial(acao_execucao_id='a' * 64, correlacao_externa=None, registrado_em=AGORA)
    assert conexao.rollbacks == 1 and conexao.commits == 0


def test_selecao_do_observador_parte_das_obrigacoes_e_nunca_do_tipo_da_acao():
    conexao = _ConexaoRoteirizada(linhas=[('b' * 64,), ('c' * 64,)])
    ids = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao).listar_acoes_para_observacao(limite=50)
    assert ids == ('b' * 64, 'c' * 64)
    ((sql, params),) = conexao.executados
    assert 'conclusao_obrigacao_assinatura' in sql and 'DISTINCT ON' in sql
    assert '.tipo' not in sql and ' tipo ' not in sql
    assert params == ('CONCLUIDO', 'SUCCEEDED', 50)


def test_selecao_do_observador_faz_rollback_em_falha():
    conexao = _ConexaoRoteirizada(falhar_em='DISTINCT ON')
    with pytest.raises(RuntimeError):
        RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao).listar_acoes_para_observacao()
    assert conexao.rollbacks == 1


def test_em_memoria_tem_a_mesma_semantica_de_registro_e_selecao():
    repo = RepositorioConclusaoObrigacaoAssinaturaEmMemoria()
    for _ in range(3):  # replay
        repo.registrar_obrigacao_inicial(acao_execucao_id='a' * 64, correlacao_externa='r', registrado_em=AGORA)
    assert [r.estado for r in repo.listar_historico('a' * 64)] == ['AGUARDANDO_ASSINATURA']
    repo.registrar_transicao_se_mudou(RegistroConclusaoObrigacaoAssinatura(
        acao_execucao_id='a' * 64, estado='ASSINADO', correlacao_externa='r', evidencia_sha256=None,
        registrado_em=AGORA,
    ))
    assert repo.registrar_obrigacao_inicial(
        acao_execucao_id='a' * 64, correlacao_externa='r', registrado_em=AGORA,
    ) is False
    assert repo.estado_mais_recente('a' * 64) == 'ASSINADO'  # replay nunca regride
    repo.registrar_obrigacao_inicial(acao_execucao_id='b' * 64, correlacao_externa='r', registrado_em=AGORA)
    repo.registrar_obrigacao_inicial(acao_execucao_id='c' * 64, correlacao_externa='r', registrado_em=AGORA)
    repo.registrar_transicao(RegistroConclusaoObrigacaoAssinatura(
        acao_execucao_id='c' * 64, estado='CONCLUIDO', correlacao_externa='r', evidencia_sha256=None,
        registrado_em=AGORA,
    ))
    estados = {'a' * 64: 'SUCCEEDED', 'b' * 64: 'PENDING', 'c' * 64: 'SUCCEEDED'}
    assert repo.listar_acoes_para_observacao(estado_da_acao=estados.get) == ('a' * 64,)


# ---- Gate 1 contra Postgres real/efêmero (CI: job postgres-real) --------

_REAL = pytest.mark.skipif(
    not os.environ.get('MAGNATA_TEST_POSTGRES_REAL'),
    reason='requer MAGNATA_TEST_POSTGRES_REAL=1 e variáveis PG* padrão de libpq',
)


def _h(*partes):
    return hashlib.sha256('|'.join(partes).encode('utf-8')).hexdigest()


def _semear_acoes(conexao, especificacoes):
    """Cria 1 evento/autorização únicos por execução e as ações pedidas:
    [(rotulo, tipo, estado)] -> {rotulo: acao_execucao_id}. Ids únicos por
    execução: a tabela 0006 é append-only e nunca é limpa entre testes."""
    execucao = uuid.uuid4().hex
    event_id = f'ev-gate1-{execucao}'
    preview_id = f'pv-gate1-{execucao}'
    autorizacao_id = f'au-gate1-{execucao}'
    ids = {'__evento__': (event_id, preview_id, autorizacao_id)}
    with conexao.cursor() as cursor:
        cursor.execute(
            "INSERT INTO magnata_orquestrador.execucoes "
            "(event_id, event_type, estado, nivel_autonomia, acao, attempt, criado_em, atualizado_em) "
            "VALUES (%s, 'COMUNICACAO_SOLICITADA', 'SUCCEEDED', 0, 'x', 0, now(), now())",
            (event_id,),
        )
        cursor.execute(
            "INSERT INTO magnata_orquestrador.autorizacoes_gate "
            "(autorizacao_id, event_id, preview_id, decisao, ator_referencia, registrado_em, proveniencia) "
            "VALUES (%s, %s, %s, 'AUTORIZADO', 'ator:teste', now(), 'teste')",
            (autorizacao_id, event_id, preview_id),
        )
        for ordem, (rotulo, tipo, estado) in enumerate(especificacoes, start=1):
            ids[rotulo] = _h(execucao, rotulo)
            concluido = 'now()' if estado in ('SUCCEEDED', 'FAILED_FINAL') else 'NULL'
            cursor.execute(
                "INSERT INTO magnata_orquestrador.acoes_execucao_plano "
                "(acao_execucao_id, event_id, preview_id, autorizacao_id, ordem, tipo, destinatario_sha256, "
                "texto_sha256, conteudo_sha256, estado, attempt, criado_em, atualizado_em, concluido_em) "
                f"VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, now(), now(), {concluido})",
                (
                    ids[rotulo], event_id, preview_id, autorizacao_id, ordem, tipo,
                    _h(execucao, 'destinatario'),
                    _h(execucao, rotulo, 'texto') if tipo == 'texto' else None,
                    None if tipo == 'texto' else _h(execucao, rotulo, 'conteudo'),
                    estado,
                ),
            )
    conexao.commit()
    return ids


def _conectar_com_migrations():
    import psycopg
    conexao = psycopg.connect(autocommit=False)
    _aplicar_migrations_se_ausentes(conexao)
    return conexao


@_REAL
def test_real_marcador_inicial_idempotente_nunca_regride_e_exige_fk():
    conexao = _conectar_com_migrations()
    ids = _semear_acoes(conexao, [('assinada', 'texto', 'SUCCEEDED')])
    repo = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao)
    gravacoes = [
        repo.registrar_obrigacao_inicial(acao_execucao_id=ids['assinada'], correlacao_externa='recX', registrado_em=AGORA)
        for _ in range(3)
    ]
    assert gravacoes == [True, False, False]
    repo.registrar_transicao_se_mudou(RegistroConclusaoObrigacaoAssinatura(
        acao_execucao_id=ids['assinada'], estado='ASSINADO', correlacao_externa='recX',
        evidencia_sha256=None, registrado_em=AGORA,
    ))
    assert repo.registrar_obrigacao_inicial(
        acao_execucao_id=ids['assinada'], correlacao_externa='recX', registrado_em=AGORA,
    ) is False
    assert [r.estado for r in repo.listar_historico(ids['assinada'])] == ['AGUARDANDO_ASSINATURA', 'ASSINADO']

    with pytest.raises(Exception):  # FK: nunca marcador de obrigação sem ação persistida
        repo.registrar_obrigacao_inicial(
            acao_execucao_id=_h('inexistente', uuid.uuid4().hex), correlacao_externa=None, registrado_em=AGORA,
        )
    conexao.close()


@_REAL
def test_real_marcador_na_transacao_da_acao_nasce_e_morre_junto_com_ela():
    """Ação e marcador na MESMA transação: rollback desfaz os dois (nunca
    ação enviável sem marcador); commit grava os dois."""
    conexao = _conectar_com_migrations()
    repo = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao)
    for confirmar in (False, True):
        execucao = uuid.uuid4().hex
        event_id, preview_id, autorizacao_id = _semear_acoes(conexao, [])['__evento__']  # só evento/autorização
        acao_id = _h(execucao, 'atomica')
        with conexao.cursor() as cursor:
            cursor.execute(
                "INSERT INTO magnata_orquestrador.acoes_execucao_plano "
                "(acao_execucao_id, event_id, preview_id, autorizacao_id, ordem, tipo, destinatario_sha256, "
                "texto_sha256, estado, attempt, criado_em, atualizado_em) "
                "VALUES (%s, %s, %s, %s, 1, 'texto', %s, %s, 'PENDING', 0, now(), now())",
                (acao_id, event_id, preview_id, autorizacao_id, _h(execucao, 'd'), _h(execucao, 't')),
            )
            assert repo.registrar_obrigacao_inicial_na_transacao(
                cursor, acao_execucao_id=acao_id, correlacao_externa='recT', registrado_em=AGORA,
            ) is True
        if confirmar:
            conexao.commit()
        else:
            conexao.rollback()
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM magnata_orquestrador.acoes_execucao_plano WHERE acao_execucao_id = %s",
                (acao_id,),
            )
            (acoes,) = cursor.fetchone()
        conexao.commit()
        marcadores = len(repo.listar_historico(acao_id))
        assert (acoes, marcadores) == ((1, 1) if confirmar else (0, 0))
    conexao.close()


@_REAL
def test_real_concorrencia_varios_processos_um_unico_marcador():
    """8 conexões independentes registram o marcador da MESMA ação ao
    mesmo tempo: o advisory lock transacional garante exatamente 1 linha."""
    import psycopg
    semeadora = _conectar_com_migrations()
    ids = _semear_acoes(semeadora, [('concorrente', 'texto', 'SUCCEEDED')])
    semeadora.close()
    barreira, resultados, erros = threading.Barrier(8), [], []

    def _registrar():
        try:
            conexao = psycopg.connect(autocommit=False)
            repo = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao)
            barreira.wait()
            resultados.append(repo.registrar_obrigacao_inicial(
                acao_execucao_id=ids['concorrente'], correlacao_externa='recC', registrado_em=AGORA,
            ))
            conexao.close()
        except Exception as exc:  # pragma: no cover - reportado pela asserção
            erros.append(exc)

    threads = [threading.Thread(target=_registrar) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert erros == []
    assert sorted(resultados) == [False] * 7 + [True]
    leitora = psycopg.connect(autocommit=False)
    assert len(RepositorioConclusaoObrigacaoAssinaturaPostgres(leitora).listar_historico(ids['concorrente'])) == 1
    leitora.close()


@_REAL
def test_real_selecao_canonica_so_acoes_succeeded_com_obrigacao_nao_concluida():
    conexao = _conectar_com_migrations()
    ids = _semear_acoes(conexao, [
        ('texto_sem_obrigacao', 'texto', 'SUCCEEDED'),
        ('documento_sem_obrigacao', 'documento', 'SUCCEEDED'),
        ('texto_aguardando', 'texto', 'SUCCEEDED'),
        ('documento_com_obrigacao', 'documento', 'SUCCEEDED'),  # id opaco: tipo físico irrelevante
        ('assinado_sem_comprovante', 'texto', 'SUCCEEDED'),
        ('concluido', 'texto', 'SUCCEEDED'),
        ('pendente_com_obrigacao', 'texto', 'PENDING'),
    ])
    repo = RepositorioConclusaoObrigacaoAssinaturaPostgres(conexao)
    for rotulo in ('texto_aguardando', 'documento_com_obrigacao', 'assinado_sem_comprovante',
                   'concluido', 'pendente_com_obrigacao'):
        repo.registrar_obrigacao_inicial(acao_execucao_id=ids[rotulo], correlacao_externa='r', registrado_em=AGORA)
    for rotulo, estado in (('assinado_sem_comprovante', 'ASSINADO'), ('concluido', 'ASSINADO'),
                           ('concluido', 'CONCLUIDO')):
        repo.registrar_transicao_se_mudou(RegistroConclusaoObrigacaoAssinatura(
            acao_execucao_id=ids[rotulo], estado=estado, correlacao_externa='r',
            evidencia_sha256=None, registrado_em=AGORA,
        ))

    selecionadas = set(repo.listar_acoes_para_observacao(limite=10_000)) & set(ids.values())
    assert selecionadas == {
        ids['texto_aguardando'], ids['documento_com_obrigacao'], ids['assinado_sem_comprovante'],
    }
    conexao.close()
