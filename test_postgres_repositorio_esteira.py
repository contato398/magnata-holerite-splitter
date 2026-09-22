"""
Testes dos adapters PostgreSQL de LoteDocumental/EstadoEsteiraDocumento
(Modulo 01, Fase 3).

Nenhum destes testes acessa Postgres real. Os adapters sao testados
contra um duplo de teste (fake) que implementa a mesma interface minima
DB-API 2.0 que um driver real expoe -- nunca importa psycopg2/psycopg.
Mesmo padrao de test_magnata_os_documental_modulo01_fase2.py (fake
duplicado aqui deliberadamente, por isolamento -- mesma convencao ja
usada no repositorio para cada familia de adapter)."""
import threading
from datetime import datetime, timezone

import pytest

from magnata_os.documental.modulo01.adapters.postgres_repositorio_esteira import (
    RepositorioEstadosEsteiraPostgres,
    RepositorioLotesPostgres,
)
from magnata_os.documental.modulo01.dominio_esteira import (
    EstadoEsteiraDocumento,
    EtapaEsteira,
    LoteDocumental,
    MotivoBloqueio,
    ProximaAcao,
    SituacaoEsteira,
    TipoProximaAcao,
)
from magnata_os.documental.modulo01.repositorio_esteira import (
    RepositorioEstadosEsteiraEmMemoria,
    RepositorioLotesEmMemoria,
)

AGORA = datetime(2099, 1, 1, tzinfo=timezone.utc)


class IntegrityError(Exception):
    """Mesmo NOME de classe que psycopg2/psycopg/sqlite3 usam para
    violacao de constraint -- e disso que _e_violacao_de_integridade()
    no adapter real depende, sem importar nenhum driver."""


class _BancoFalso:
    def __init__(self):
        self.lotes = {}                # lote_id -> tupla de colunas
        self.estados = {}              # documento_id -> tupla de colunas
        self.documentos_existentes = set()  # documento_id validos (FK)
        self._lock = threading.Lock()


class _CursorFalso:
    def __init__(self, banco: _BancoFalso, conexao=None):
        self._banco = banco
        self._conexao = conexao
        self._resultado = []
        self._indice = 0

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def execute(self, sql, params=()):
        sql_norm = ' '.join(sql.split())
        banco = self._banco

        # ---- lotes_documentais ----
        if sql_norm.startswith('SELECT') and 'FROM lotes_documentais WHERE lote_id' in sql_norm:
            linha = banco.lotes.get(params[0])
            self._resultado = [linha] if linha else []

        elif sql_norm.startswith('INSERT INTO lotes_documentais') and 'DO UPDATE SET' in sql_norm:
            lote_id = params[0]
            banco.lotes[lote_id] = tuple(params)
            self._resultado = []

        elif sql_norm.startswith('SELECT') and 'FROM lotes_documentais ORDER BY criado_em DESC LIMIT' in sql_norm:
            limite = params[0]
            linhas = sorted(banco.lotes.values(), key=lambda l: l[6], reverse=True)
            self._resultado = linhas[:limite]

        elif sql_norm.startswith('SELECT') and 'FROM lotes_documentais ORDER BY criado_em ASC' in sql_norm:
            self._resultado = sorted(banco.lotes.values(), key=lambda l: l[6])

        # ---- estados_esteira_documental ----
        elif sql_norm.startswith('SELECT') and 'FROM estados_esteira_documental WHERE documento_id' in sql_norm:
            linha = banco.estados.get(params[0])
            self._resultado = [linha] if linha else []

        elif sql_norm.startswith('INSERT INTO estados_esteira_documental') and 'DO NOTHING RETURNING' in sql_norm:
            with banco._lock:
                documento_id, lote_id = params[0], params[1]
                self._checar_fk(documento_id, lote_id)
                if documento_id in banco.estados:
                    self._resultado = []
                else:
                    banco.estados[documento_id] = tuple(params)
                    self._resultado = [(documento_id,)]

        elif sql_norm.startswith('INSERT INTO estados_esteira_documental') and 'DO UPDATE SET' in sql_norm:
            documento_id, lote_id = params[0], params[1]
            self._checar_fk(documento_id, lote_id)
            banco.estados[documento_id] = tuple(params)
            self._resultado = []

        elif sql_norm.startswith('SELECT') and 'FROM estados_esteira_documental ORDER BY entrou_na_etapa_em ASC' in sql_norm:
            self._resultado = sorted(banco.estados.values(), key=lambda l: l[12])

        elif sql_norm.startswith('SELECT') and 'FROM estados_esteira_documental WHERE lote_id' in sql_norm:
            self._resultado = [l for l in banco.estados.values() if l[1] == params[0]]

        elif sql_norm.startswith('SELECT') and 'FROM estados_esteira_documental WHERE etapa_atual' in sql_norm:
            self._resultado = [l for l in banco.estados.values() if l[2] == params[0]]

        elif sql_norm.startswith('SELECT') and 'FROM estados_esteira_documental WHERE situacao' in sql_norm:
            self._resultado = [l for l in banco.estados.values() if l[3] == params[0]]

        else:
            raise AssertionError(f'SQL nao reconhecido pelo fake DB-API: {sql_norm}')

        self._indice = 0

    def _checar_fk(self, documento_id, lote_id):
        banco = self._banco
        if documento_id not in banco.documentos_existentes:
            raise IntegrityError(
                f'insert or update on table "estados_esteira_documental" violates foreign key '
                f'constraint "estados_esteira_documental_documento_id_fkey" '
                f'(documento_id={documento_id} nao existe em documentos)'
            )
        if lote_id is not None and lote_id not in banco.lotes:
            raise IntegrityError(
                f'insert or update on table "estados_esteira_documental" violates foreign key '
                f'constraint "estados_esteira_documental_lote_id_fkey" '
                f'(lote_id={lote_id} nao existe em lotes_documentais)'
            )

    def fetchone(self):
        if self._indice < len(self._resultado):
            linha = self._resultado[self._indice]
            self._indice += 1
            return linha
        return None

    def fetchall(self):
        resultado = self._resultado[self._indice:]
        self._indice = len(self._resultado)
        return resultado


class _ConexaoFalsa:
    def __init__(self, banco: _BancoFalso):
        self._banco = banco
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _CursorFalso(self._banco, self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _ConexaoEnumInvalido:
    """Simula uma linha no banco com valor fora do vocabulario do enum
    Python -- prova fail-closed na leitura, sem depender de nenhum
    Postgres real."""

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def execute(self, sql, params=()):
        self._linha = (
            'doc-1', None, 'ETAPA_QUE_NAO_EXISTE', 'CONCLUIDO',
            None, None, None, None, None, None, None, None,
            AGORA, AGORA, 'corr-1',
        )

    def fetchone(self):
        return self._linha


def _lote(lote_id='lote-1', situacao=SituacaoEsteira.CONCLUIDO, metadados=None):
    return LoteDocumental(
        lote_id=lote_id, origem='teste', recebido_em=AGORA, quantidade_arquivos=1,
        situacao=situacao, correlation_id='corr-lote-1', criado_em=AGORA, atualizado_em=AGORA,
        metadados=metadados or {},
    )


def _estado(
    documento_id='doc-1', lote_id='lote-1', motivo_bloqueio=None, proxima_acao=None,
    situacao=SituacaoEsteira.CONCLUIDO,
):
    return EstadoEsteiraDocumento(
        documento_id=documento_id, lote_id=lote_id, etapa_atual=EtapaEsteira.REGISTRO,
        situacao=situacao, motivo_bloqueio=motivo_bloqueio, proxima_acao=proxima_acao,
        entrou_na_etapa_em=AGORA, atualizado_em=AGORA, correlation_id='corr-estado-1',
    )


# ---------------------------------------------------------------------
# RepositorioLotesPostgres
# ---------------------------------------------------------------------

def test_lote_round_trip_completo():
    conexao = _ConexaoFalsa(_BancoFalso())
    repo = RepositorioLotesPostgres(conexao)
    lote = _lote(metadados={'origem_detalhe': 'email', 'quantidade': 3})

    repo.salvar(lote)
    recuperado = repo.buscar_por_id('lote-1')

    assert recuperado == lote
    assert conexao.commits == 1


def test_lote_metadados_jsonb_estrutura_aninhada():
    conexao = _ConexaoFalsa(_BancoFalso())
    repo = RepositorioLotesPostgres(conexao)
    metadados = {'nivel1': {'nivel2': ['a', 'b', 3]}, 'vazio': {}}
    lote = _lote(metadados=metadados)

    repo.salvar(lote)
    recuperado = repo.buscar_por_id('lote-1')

    assert dict(recuperado.metadados) == metadados


def test_lote_salvar_e_upsert_sem_duplicar():
    conexao = _ConexaoFalsa(_BancoFalso())
    repo = RepositorioLotesPostgres(conexao)
    lote = _lote(situacao=SituacaoEsteira.EM_PROCESSAMENTO)

    repo.salvar(lote)
    lote_atualizado = _lote(situacao=SituacaoEsteira.CONCLUIDO)
    repo.salvar(lote_atualizado)

    recuperado = repo.buscar_por_id('lote-1')
    assert recuperado.situacao == SituacaoEsteira.CONCLUIDO
    assert len(repo.listar_todos()) == 1


def test_lote_buscar_por_id_ausente_retorna_none():
    conexao = _ConexaoFalsa(_BancoFalso())
    repo = RepositorioLotesPostgres(conexao)
    assert repo.buscar_por_id('nao-existe') is None


def test_lote_listar_recentes_ordem_desc():
    conexao = _ConexaoFalsa(_BancoFalso())
    repo = RepositorioLotesPostgres(conexao)
    from datetime import timedelta
    repo.salvar(_lote(lote_id='lote-antigo'))
    lote_recente = LoteDocumental(
        lote_id='lote-recente', origem='teste', recebido_em=AGORA + timedelta(hours=1),
        quantidade_arquivos=1, situacao=SituacaoEsteira.CONCLUIDO, correlation_id='corr-2',
        criado_em=AGORA + timedelta(hours=1), atualizado_em=AGORA + timedelta(hours=1), metadados={},
    )
    repo.salvar(lote_recente)

    recentes = repo.listar_recentes(limite=10)
    assert recentes[0].lote_id == 'lote-recente'


def test_lote_listar_todos_ordem_asc():
    conexao = _ConexaoFalsa(_BancoFalso())
    repo = RepositorioLotesPostgres(conexao)
    repo.salvar(_lote(lote_id='lote-1'))
    todos = repo.listar_todos()
    assert [l.lote_id for l in todos] == ['lote-1']


def test_lote_salvar_falha_aciona_rollback_e_propaga():
    class _ConexaoQueFalha:
        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def execute(self, *_a, **_kw):
            raise ConnectionError('conexao perdida (simulado)')

        def commit(self):
            raise AssertionError('nao deveria commitar apos falha')

        def rollback(self):
            self.rollbacks = getattr(self, 'rollbacks', 0) + 1

    conexao = _ConexaoQueFalha()
    repo = RepositorioLotesPostgres(conexao)
    with pytest.raises(ConnectionError):
        repo.salvar(_lote())
    assert conexao.rollbacks == 1


# ---------------------------------------------------------------------
# RepositorioEstadosEsteiraPostgres
# ---------------------------------------------------------------------

def _banco_com_documento_e_lote(documento_id='doc-1', lote_id='lote-1'):
    banco = _BancoFalso()
    banco.documentos_existentes.add(documento_id)
    conexao = _ConexaoFalsa(banco)
    RepositorioLotesPostgres(conexao).salvar(_lote(lote_id=lote_id))
    return banco, conexao


def test_estado_round_trip_motivo_bloqueio_none_proxima_acao_none():
    _banco, conexao = _banco_com_documento_e_lote()
    repo = RepositorioEstadosEsteiraPostgres(conexao)
    estado = _estado(motivo_bloqueio=None, proxima_acao=None)

    repo.salvar(estado)
    recuperado = repo.buscar_por_documento_id('doc-1')

    assert recuperado == estado
    assert recuperado.motivo_bloqueio is None
    assert recuperado.proxima_acao is None


def test_estado_round_trip_motivo_bloqueio_preenchido():
    _banco, conexao = _banco_com_documento_e_lote()
    repo = RepositorioEstadosEsteiraPostgres(conexao)
    motivo = MotivoBloqueio(
        codigo='CPF_ILEGIVEL', descricao='CPF nao legivel no documento',
        detalhe_tecnico='OCR confidence 0.12', resolvivel_automaticamente=False,
    )
    estado = _estado(motivo_bloqueio=motivo, situacao=SituacaoEsteira.BLOQUEADO)

    repo.salvar(estado)
    recuperado = repo.buscar_por_documento_id('doc-1')

    assert recuperado.motivo_bloqueio == motivo


def test_estado_round_trip_proxima_acao_preenchida():
    _banco, conexao = _banco_com_documento_e_lote()
    repo = RepositorioEstadosEsteiraPostgres(conexao)
    proxima = ProximaAcao(acao='revisar_cpf', tipo=TipoProximaAcao.HUMANA, prazo=AGORA, responsavel='dp@magnata')
    estado = _estado(proxima_acao=proxima)

    repo.salvar(estado)
    recuperado = repo.buscar_por_documento_id('doc-1')

    assert recuperado.proxima_acao == proxima


def test_estado_lote_id_none_e_aceito():
    banco = _BancoFalso()
    banco.documentos_existentes.add('doc-legado')
    conexao = _ConexaoFalsa(banco)
    repo = RepositorioEstadosEsteiraPostgres(conexao)
    estado = _estado(documento_id='doc-legado', lote_id=None)

    repo.salvar(estado)
    recuperado = repo.buscar_por_documento_id('doc-legado')
    assert recuperado.lote_id is None


def test_estado_criar_se_ausente_cria_uma_vez():
    _banco, conexao = _banco_com_documento_e_lote()
    repo = RepositorioEstadosEsteiraPostgres(conexao)
    fabricado = []

    def _fabricar():
        fabricado.append(1)
        return _estado()

    estado1, criado1 = repo.criar_se_ausente('doc-1', _fabricar)
    estado2, criado2 = repo.criar_se_ausente('doc-1', _fabricar)

    assert criado1 is True
    assert criado2 is False
    assert estado1 == estado2
    assert len(fabricado) == 2  # fabricar_estado sempre chamada, mesmo padrao do precedente


def test_estado_criar_se_ausente_nunca_sobrescreve():
    _banco, conexao = _banco_com_documento_e_lote()
    repo = RepositorioEstadosEsteiraPostgres(conexao)
    repo.criar_se_ausente('doc-1', lambda: _estado(situacao=SituacaoEsteira.EM_PROCESSAMENTO))
    estado_depois, criado = repo.criar_se_ausente('doc-1', lambda: _estado(situacao=SituacaoEsteira.CONCLUIDO))

    assert criado is False
    assert estado_depois.situacao == SituacaoEsteira.EM_PROCESSAMENTO


def test_estado_criar_se_ausente_concorrencia_real_apenas_um_vence():
    """Corrida real de threads contra o fake -- prova que o lock do
    _BancoFalso (mesmo padrao de _BancoFalso.lock em test_magnata_os_
    documental_modulo01_fase2.py) fecha a janela de corrida do jeito que
    a constraint PRIMARY KEY fecharia num Postgres real."""
    _banco, conexao = _banco_com_documento_e_lote()
    repo = RepositorioEstadosEsteiraPostgres(conexao)
    n_threads = 8
    barreira = threading.Barrier(n_threads)
    resultados = []

    def _tentar():
        barreira.wait()
        resultados.append(repo.criar_se_ausente('doc-1', lambda: _estado()))

    threads = [threading.Thread(target=_tentar) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    criacoes = [criado for _estado_, criado in resultados if criado]
    assert len(criacoes) == 1
    assert len(repo.listar_todos()) == 1


def test_estado_salvar_fk_documento_inexistente_propaga_erro():
    banco = _BancoFalso()  # documento_id nunca adicionado a documentos_existentes
    conexao = _ConexaoFalsa(banco)
    RepositorioLotesPostgres(conexao).salvar(_lote())
    repo = RepositorioEstadosEsteiraPostgres(conexao)

    with pytest.raises(IntegrityError):
        repo.salvar(_estado(documento_id='doc-inexistente'))
    assert conexao.rollbacks == 1


def test_estado_salvar_fk_lote_inexistente_propaga_erro():
    banco = _BancoFalso()
    banco.documentos_existentes.add('doc-1')
    conexao = _ConexaoFalsa(banco)
    repo = RepositorioEstadosEsteiraPostgres(conexao)

    with pytest.raises(IntegrityError):
        repo.salvar(_estado(documento_id='doc-1', lote_id='lote-inexistente'))


def test_estado_listar_por_lote_etapa_situacao():
    banco = _BancoFalso()
    banco.documentos_existentes.update({'doc-1', 'doc-2'})
    conexao = _ConexaoFalsa(banco)
    RepositorioLotesPostgres(conexao).salvar(_lote(lote_id='lote-a'))
    RepositorioLotesPostgres(conexao).salvar(_lote(lote_id='lote-b'))
    repo = RepositorioEstadosEsteiraPostgres(conexao)
    repo.salvar(_estado(documento_id='doc-1', lote_id='lote-a', situacao=SituacaoEsteira.CONCLUIDO))
    repo.salvar(_estado(documento_id='doc-2', lote_id='lote-b', situacao=SituacaoEsteira.BLOQUEADO))

    assert [e.documento_id for e in repo.listar_por_lote('lote-a')] == ['doc-1']
    assert [e.documento_id for e in repo.listar_por_etapa(EtapaEsteira.REGISTRO)] == ['doc-1', 'doc-2']
    assert [e.documento_id for e in repo.listar_por_situacao(SituacaoEsteira.BLOQUEADO)] == ['doc-2']


def test_estado_enum_invalido_falha_fechado_na_leitura():
    repo = RepositorioEstadosEsteiraPostgres(_ConexaoEnumInvalido())
    with pytest.raises(ValueError):
        repo.buscar_por_documento_id('doc-1')


def test_estado_salvar_falha_aciona_rollback_e_propaga():
    class _ConexaoQueFalha:
        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def execute(self, *_a, **_kw):
            raise ConnectionError('conexao perdida (simulado)')

        def commit(self):
            raise AssertionError('nao deveria commitar apos falha')

        def rollback(self):
            self.rollbacks = getattr(self, 'rollbacks', 0) + 1

    conexao = _ConexaoQueFalha()
    repo = RepositorioEstadosEsteiraPostgres(conexao)
    with pytest.raises(ConnectionError):
        repo.salvar(_estado())
    assert conexao.rollbacks == 1


# ---------------------------------------------------------------------
# Regressao dos repositorios em memoria (nenhuma alteracao esperada)
# ---------------------------------------------------------------------

def test_regressao_repositorio_lotes_em_memoria_continua_funcionando():
    repo = RepositorioLotesEmMemoria()
    lote = _lote()
    repo.salvar(lote)
    assert repo.buscar_por_id('lote-1') == lote
    assert repo.listar_todos() == [lote]


def test_regressao_repositorio_estados_esteira_em_memoria_continua_funcionando():
    repo = RepositorioEstadosEsteiraEmMemoria()
    estado, criado = repo.criar_se_ausente('doc-1', lambda: _estado())
    assert criado is True
    assert repo.buscar_por_documento_id('doc-1') == estado
