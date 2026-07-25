"""
Testes do Modulo 01 (Documental), Fase 2 -- persistencia e armazenamento.

Nenhum destes testes acessa Postgres ou S3 reais. Os adapters sao
testados contra duplos de teste (fakes) que implementam a mesma
interface minima (DB-API 2.0 / cliente S3-like) que um driver real
exporia -- nunca importam psycopg2/psycopg/boto3.
"""
import hashlib
import io
import threading
from datetime import datetime, timezone
from urllib.parse import unquote

import pytest

from magnata_os.documental.modulo01.armazenamento import (
    ArmazenamentoArquivosEmMemoria,
    ArquivoNaoEncontrado,
    ConteudoDivergente,
    HashInconsistente,
)
from magnata_os.documental.modulo01.adapters.postgres_repositorio import (
    RepositorioDocumentosPostgres,
    RepositorioHistoricoPostgres,
)
from magnata_os.documental.modulo01.adapters.s3_armazenamento import ArmazenamentoArquivosS3
from magnata_os.documental.modulo01.dominio import StatusDocumento
from magnata_os.documental.modulo01.repositorio import (
    RepositorioDocumentosEmMemoria,
    RepositorioHistoricoEmMemoria,
)
from magnata_os.documental.modulo01.servico_entrada import FalhaPersistencia
from magnata_os.documental.modulo01.servico_entrada_persistente import (
    FalhaArmazenamento,
    registrar_entrada_com_armazenamento,
)


# ============================================================================
# Duplos de teste -- DB-API 2.0 falso (documentos + eventos_documentais)
# ============================================================================

class IntegrityError(Exception):
    """Mesmo NOME de classe que psycopg2/psycopg/sqlite3 usam para
    violacao de constraint (UNIQUE, FK) -- e disso que
    _e_violacao_de_integridade() no adapter real depende, sem importar
    nenhum driver."""


class _BancoFalso:
    """Estrutura compartilhada simulando os dados persistidos. Criar uma
    nova _ConexaoFalsa apontando para o MESMO _BancoFalso simula
    reconectar depois de uma reinicializacao -- os dados sobrevivem."""

    def __init__(self):
        self.documentos = {}           # documento_id -> tupla de colunas
        self.documentos_por_hash = {}  # hash_sha256 -> documento_id
        self.eventos = []              # lista de (evento_id, *colunas_evento)
        self._proximo_evento_id = 1
        self._lock = threading.Lock()


class _CursorFalso:
    def __init__(self, banco: _BancoFalso, conexao: '_ConexaoFalsa | None' = None):
        self._banco = banco
        self._conexao = conexao
        self._resultado = []
        self._indice = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        if self._conexao is not None and self._conexao.falhar_no_proximo_execute:
            self._conexao.falhar_no_proximo_execute = False
            self._conexao._abortada = True
            raise ConnectionError('conexao com o banco perdida durante execute (simulado)')

        sql_norm = ' '.join(sql.split())
        banco = self._banco

        if sql_norm.startswith('SELECT') and 'FROM documentos WHERE hash_sha256' in sql_norm:
            doc_id = banco.documentos_por_hash.get(params[0])
            self._resultado = [banco.documentos[doc_id]] if doc_id else []

        elif sql_norm.startswith('SELECT') and 'FROM documentos WHERE documento_id' in sql_norm:
            self._resultado = [banco.documentos[params[0]]] if params[0] in banco.documentos else []

        elif sql_norm.startswith('SELECT') and 'FROM documentos ORDER BY' in sql_norm:
            self._resultado = sorted(banco.documentos.values(), key=lambda l: l[11])

        elif sql_norm.startswith('INSERT INTO documentos') and 'DO NOTHING RETURNING' in sql_norm:
            with banco._lock:
                documento_id, hash_sha256 = params[0], params[5]
                if hash_sha256 in banco.documentos_por_hash:
                    self._resultado = []
                else:
                    banco.documentos[documento_id] = tuple(params)
                    banco.documentos_por_hash[hash_sha256] = documento_id
                    self._resultado = [(documento_id,)]

        elif sql_norm.startswith('INSERT INTO documentos') and 'DO UPDATE SET' in sql_norm:
            documento_id, hash_sha256 = params[0], params[5]
            dono_atual = banco.documentos_por_hash.get(hash_sha256)
            if dono_atual is not None and dono_atual != documento_id:
                raise IntegrityError(
                    f'duplicate key value violates unique constraint '
                    f'"documentos_hash_sha256_unique" (hash_sha256={hash_sha256})'
                )
            banco.documentos[documento_id] = tuple(params)
            banco.documentos_por_hash[hash_sha256] = documento_id
            self._resultado = []

        elif sql_norm.startswith('DELETE FROM documentos'):
            linha = banco.documentos.pop(params[0], None)
            if linha:
                banco.documentos_por_hash.pop(linha[5], None)
            self._resultado = []

        elif sql_norm.startswith('INSERT INTO eventos_documentais'):
            documento_id = params[0]
            if documento_id not in banco.documentos:
                raise IntegrityError(
                    f'insert or update on table "eventos_documentais" violates foreign key '
                    f'constraint "eventos_documentais_documento_id_fkey" '
                    f'(documento_id={documento_id} nao existe em documentos)'
                )
            evento_id = banco._proximo_evento_id
            banco._proximo_evento_id += 1
            banco.eventos.append((evento_id,) + tuple(params))
            self._resultado = []

        elif sql_norm.startswith('SELECT') and 'FROM eventos_documentais WHERE documento_id' in sql_norm:
            linhas = [e for e in banco.eventos if e[1] == params[0]]
            linhas.sort(key=lambda e: (e[5], e[0]))
            self._resultado = [e[1:] for e in linhas]

        elif sql_norm.startswith('SELECT') and 'FROM eventos_documentais ORDER BY' in sql_norm:
            linhas = sorted(banco.eventos, key=lambda e: (e[5], e[0]))
            self._resultado = [e[1:] for e in linhas]

        elif 'UPDATE eventos_documentais' in sql_norm or 'DELETE FROM eventos_documentais' in sql_norm:
            # Simula a trigger da migration 0003 -- append-only a nivel de banco.
            raise IntegrityError('eventos_documentais e append-only: UPDATE/DELETE nao permitido')

        else:
            raise AssertionError(f'SQL nao reconhecido pelo fake DB-API: {sql_norm}')

        self._indice = 0

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
    """DB-API 2.0-like. Aponta para um _BancoFalso -- pode ser
    compartilhado entre 'conexoes' distintas para simular
    reinicializacao sem perda de dados."""

    def __init__(self, banco: _BancoFalso):
        self._banco = banco
        self.commits = 0
        self.rollbacks = 0
        self._abortada = False
        # Flags de injecao de falha, one-shot (resetadas ao disparar uma vez).
        self.falhar_no_proximo_execute = False
        self.falhar_no_proximo_commit = False

    def cursor(self):
        if self._abortada:
            raise RuntimeError(
                'current transaction is aborted, commands ignored until '
                'end of transaction block (simulado)'
            )
        return _CursorFalso(self._banco, self)

    def commit(self):
        if self._abortada:
            raise RuntimeError(
                'current transaction is aborted, commands ignored until '
                'end of transaction block (simulado)'
            )
        if self.falhar_no_proximo_commit:
            self.falhar_no_proximo_commit = False
            self._abortada = True
            raise ConnectionError('conexao com o banco perdida durante commit (simulado)')
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1
        self._abortada = False


class _ConexaoQueFalhaNoExecute:
    """Simula indisponibilidade do banco (nao IntegrityError -- outro
    tipo de falha, ex.: conexao caiu)."""

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def execute(self, *_a, **_kw):
        raise ConnectionError('conexao com o banco perdida (simulado)')

    def commit(self):
        pass

    def rollback(self):
        pass


# ============================================================================
# Duplos de teste -- cliente S3 falso
# ============================================================================

class ClientError(Exception):
    """Mesmo formato de .response que botocore.exceptions.ClientError."""

    def __init__(self, response, operation_name):
        self.response = response
        super().__init__(f'{operation_name}: {response}')


class _ClienteS3Falso:
    def __init__(self):
        self.objetos = {}
        self.chamadas_put_object = 0

    def head_object(self, Bucket, Key):
        chave = (Bucket, Key)
        if chave not in self.objetos:
            raise ClientError({'Error': {'Code': '404', 'Message': 'Not Found'}}, 'HeadObject')
        obj = self.objetos[chave]
        # ETag real (MD5 hex entre aspas, como upload de parte unica) --
        # recalculado a partir do Body ATUAL, para que uma adulteracao
        # direta de objetos[...]['Body'] (usada nos testes de corrupcao)
        # mude o ETag exatamente como aconteceria num S3 real.
        etag = hashlib.md5(obj['Body']).hexdigest()
        return {
            'ContentLength': len(obj['Body']),
            'ContentType': obj['ContentType'],
            'ETag': f'"{etag}"',
        }

    def put_object(self, Bucket, Key, Body, ContentType, Metadata):
        self.chamadas_put_object += 1
        self.objetos[(Bucket, Key)] = {
            'Body': bytes(Body), 'ContentType': ContentType, 'Metadata': Metadata,
        }

    def get_object(self, Bucket, Key):
        chave = (Bucket, Key)
        if chave not in self.objetos:
            raise ClientError({'Error': {'Code': 'NoSuchKey', 'Message': 'Not Found'}}, 'GetObject')
        obj = self.objetos[chave]
        return {'Body': io.BytesIO(obj['Body']), 'ContentType': obj['ContentType']}

    def delete_object(self, Bucket, Key):
        self.objetos.pop((Bucket, Key), None)


# ============================================================================
# armazenamento em memoria
# ============================================================================

def test_armazenamento_em_memoria_idempotente_por_hash():
    armazenamento = ArmazenamentoArquivosEmMemoria()
    conteudo = b'conteudo'
    h = _sha(conteudo)
    ref1 = armazenamento.armazenar(h, conteudo, 'application/pdf', 'a.pdf', len(conteudo))
    ref2 = armazenamento.armazenar(h, conteudo, 'application/pdf', 'a.pdf', len(conteudo))
    assert ref1 == ref2
    assert armazenamento.existe(h)


def test_armazenamento_em_memoria_conteudo_diferente_mesma_chave_rejeitado():
    """Um segundo armazenar() legitimo nunca alcanca mais ConteudoDivergente
    por si so -- o hash informado e sempre validado contra o conteudo desta
    chamada primeiro (HashInconsistente cobre esse caso, ver teste
    especifico abaixo). ConteudoDivergente agora so e alcancavel quando o
    objeto JA armazenado foi corrompido/adulterado depois do fato -- aqui
    simulado adulterando o backing store diretamente."""
    armazenamento = ArmazenamentoArquivosEmMemoria()
    conteudo = b'conteudo original mesmo tamanho'
    corrompido = b'conteudo alterado mesmo tamanho'
    assert len(corrompido) == len(conteudo)
    h = _sha(conteudo)

    armazenamento.armazenar(h, conteudo, 'application/pdf', 'a.pdf', len(conteudo))
    armazenamento._objetos[h] = corrompido  # simula corrupcao do objeto ja armazenado

    with pytest.raises(ConteudoDivergente):
        armazenamento.armazenar(h, conteudo, 'application/pdf', 'a.pdf', len(conteudo))


def test_armazenamento_em_memoria_hash_informado_diferente_do_conteudo_rejeitado():
    armazenamento = ArmazenamentoArquivosEmMemoria()
    with pytest.raises(HashInconsistente):
        armazenamento.armazenar('0' * 64, b'conteudo qualquer', 'application/pdf', 'a.pdf', 17)


def test_armazenamento_em_memoria_leitura_por_streaming():
    armazenamento = ArmazenamentoArquivosEmMemoria()
    conteudo = b'conteudo para streaming'
    h = _sha(conteudo)
    armazenamento.armazenar(h, conteudo, 'application/pdf', 'a.pdf', len(conteudo))
    stream = armazenamento.abrir_leitura(h)
    assert hasattr(stream, 'read')
    assert stream.read() == b'conteudo para streaming'


def test_armazenamento_em_memoria_arquivo_nao_encontrado():
    armazenamento = ArmazenamentoArquivosEmMemoria()
    with pytest.raises(ArquivoNaoEncontrado):
        armazenamento.abrir_leitura('inexistente' * 6)


def test_armazenamento_em_memoria_concorrencia_por_hash():
    """Confirma que armazenar() concorrente com o mesmo hash nunca
    levanta ConteudoDivergente (mesmo conteudo) e sempre devolve a
    mesma referencia."""
    armazenamento = ArmazenamentoArquivosEmMemoria()
    conteudo = b'conteudo concorrente identico'
    h = _sha(conteudo)
    n = 20
    barreira = threading.Barrier(n)
    referencias = []
    erros = []
    lock = threading.Lock()

    def _tentar():
        try:
            barreira.wait(timeout=5)
            ref = armazenamento.armazenar(h, conteudo, 'application/pdf', 'a.pdf', len(conteudo))
            with lock:
                referencias.append(ref)
        except Exception as exc:
            with lock:
                erros.append(exc)

    threads = [threading.Thread(target=_tentar) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert erros == []
    assert len(referencias) == n
    assert len(set(referencias)) == 1


# ============================================================================
# adapter S3
# ============================================================================

def test_s3_armazenar_idempotente_nao_reenvia():
    cliente = _ClienteS3Falso()
    adapter = ArmazenamentoArquivosS3(cliente, bucket='meu-bucket')
    conteudo = b'conteudo s3'
    h = _sha(conteudo)
    ref1 = adapter.armazenar(h, conteudo, 'application/pdf', 'a.pdf', len(conteudo))
    ref2 = adapter.armazenar(h, conteudo, 'application/pdf', 'a.pdf', len(conteudo))
    assert ref1 == ref2
    assert cliente.chamadas_put_object == 1  # segunda chamada nao reenviou


def test_s3_conteudo_diferente_mesma_chave_rejeitado():
    """Mesma logica do teste equivalente em memoria: so alcancavel via
    corrupcao do objeto ja gravado no S3 (ETag muda), nunca por uma
    chamada legitima de armazenar() (que agora sempre valida o hash
    informado contra o conteudo desta chamada primeiro)."""
    cliente = _ClienteS3Falso()
    adapter = ArmazenamentoArquivosS3(cliente, bucket='meu-bucket')
    conteudo = b'conteudo original mesmo tamanho'
    corrompido = b'conteudo alterado mesmo tamanho'
    assert len(corrompido) == len(conteudo)
    h = _sha(conteudo)

    adapter.armazenar(h, conteudo, 'application/pdf', 'a.pdf', len(conteudo))
    cliente.objetos[('meu-bucket', f'documentos/{h}')]['Body'] = corrompido

    with pytest.raises(ConteudoDivergente):
        adapter.armazenar(h, conteudo, 'application/pdf', 'a.pdf', len(conteudo))


def test_s3_hash_informado_diferente_do_conteudo_rejeitado():
    cliente = _ClienteS3Falso()
    adapter = ArmazenamentoArquivosS3(cliente, bucket='meu-bucket')
    with pytest.raises(HashInconsistente):
        adapter.armazenar('0' * 64, b'conteudo qualquer s3', 'application/pdf', 'a.pdf', 20)
    assert cliente.chamadas_put_object == 0


def test_s3_leitura_por_streaming():
    cliente = _ClienteS3Falso()
    adapter = ArmazenamentoArquivosS3(cliente, bucket='meu-bucket')
    conteudo = b'conteudo para stream s3'
    h = _sha(conteudo)
    adapter.armazenar(h, conteudo, 'application/pdf', 'a.pdf', len(conteudo))
    stream = adapter.abrir_leitura(h)
    assert hasattr(stream, 'read')
    assert stream.read() == b'conteudo para stream s3'


def test_s3_existe_false_quando_nao_armazenado():
    cliente = _ClienteS3Falso()
    adapter = ArmazenamentoArquivosS3(cliente, bucket='meu-bucket')
    assert adapter.existe('inexistente' * 6) is False


def test_s3_remover_e_so_compensacao_nunca_automatico():
    cliente = _ClienteS3Falso()
    adapter = ArmazenamentoArquivosS3(cliente, bucket='meu-bucket')
    conteudo = b'conteudo removivel'
    h = _sha(conteudo)
    adapter.armazenar(h, conteudo, 'application/pdf', 'a.pdf', len(conteudo))
    assert adapter.existe(h)
    adapter.remover(h)
    assert not adapter.existe(h)


def test_s3_chave_baseada_no_hash():
    cliente = _ClienteS3Falso()
    adapter = ArmazenamentoArquivosS3(cliente, bucket='meu-bucket', prefixo='docs/')
    conteudo = b'x'
    h = _sha(conteudo)
    ref = adapter.armazenar(h, conteudo, 'application/pdf', 'a.pdf', len(conteudo))
    assert ref == f's3://meu-bucket/docs/{h}'
    assert (('meu-bucket', f'docs/{h}')) in cliente.objetos


def test_s3_nome_original_com_acentos_codificado_com_seguranca_nos_metadados():
    cliente = _ClienteS3Falso()
    adapter = ArmazenamentoArquivosS3(cliente, bucket='meu-bucket')
    nome = 'contracheque – João Ação (março).pdf'
    conteudo = b'conteudo com nome acentuado'
    h = _sha(conteudo)

    adapter.armazenar(h, conteudo, 'application/pdf', nome, len(conteudo))

    metadata = cliente.objetos[('meu-bucket', f'documentos/{h}')]['Metadata']
    valor_codificado = metadata['nome-original']
    assert valor_codificado.isascii()
    assert unquote(valor_codificado) == nome


# ============================================================================
# adapter Postgres -- documentos
# ============================================================================

def test_postgres_salvar_se_ausente_por_hash_cria_uma_vez():
    banco = _BancoFalso()
    repo = RepositorioDocumentosPostgres(_ConexaoFalsa(banco))
    chamadas = []

    def fabricar():
        chamadas.append(1)
        return _documento_teste('doc-pg-1', 'hashpg1' * 8)

    doc1, criado1 = repo.salvar_se_ausente_por_hash('hashpg1' * 8, fabricar)
    doc2, criado2 = repo.salvar_se_ausente_por_hash('hashpg1' * 8, fabricar)

    assert criado1 is True
    assert criado2 is False
    assert doc1.documento_id == doc2.documento_id
    assert len(repo.listar_todos()) == 1


def test_postgres_violacao_unique_constraint_simulada():
    """Chamar salvar() diretamente com um documento_id novo mas hash ja
    usado por outro documento_id -- constraint UNIQUE(hash_sha256) do
    banco rejeita, mesmo fora do caminho salvar_se_ausente_por_hash."""
    banco = _BancoFalso()
    repo = RepositorioDocumentosPostgres(_ConexaoFalsa(banco))
    h = 'hashunique' * 6

    repo.salvar(_documento_teste('doc-a', h))
    with pytest.raises(IntegrityError):
        repo.salvar(_documento_teste('doc-b', h))  # documento_id diferente, mesmo hash


def test_postgres_busca_por_id_e_por_hash():
    banco = _BancoFalso()
    repo = RepositorioDocumentosPostgres(_ConexaoFalsa(banco))
    h = 'hashbusca' * 7
    original = _documento_teste('doc-busca', h)
    repo.salvar(original)

    assert repo.buscar_por_id('doc-busca') == original
    assert repo.buscar_por_hash(h) == original
    assert repo.buscar_por_id('inexistente') is None
    assert repo.buscar_por_hash('0' * 64) is None


def test_postgres_falha_generica_no_banco_propaga():
    """Falha que NAO e IntegrityError (ex.: conexao caiu) deve propagar,
    nunca ser tratada como duplicidade."""
    repo = RepositorioDocumentosPostgres(_ConexaoQueFalhaNoExecute())
    with pytest.raises(ConnectionError):
        repo.salvar_se_ausente_por_hash('qualquerhash' * 5, lambda: _documento_teste('x', 'h'))


def test_postgres_concorrencia_por_hash_multiplas_threads():
    banco = _BancoFalso()
    h = 'hashconcorrencia' * 4
    n = 15
    barreira = threading.Barrier(n)
    resultados = []
    lock = threading.Lock()

    def _tentar(indice):
        repo = RepositorioDocumentosPostgres(_ConexaoFalsa(banco))
        barreira.wait(timeout=5)
        doc, criado = repo.salvar_se_ausente_por_hash(
            h, lambda i=indice: _documento_teste(f'doc-conc-{i}', h),
        )
        with lock:
            resultados.append((doc.documento_id, criado))

    threads = [threading.Thread(target=_tentar, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    ids_criados = {doc_id for doc_id, criado in resultados if criado}
    assert len(ids_criados) == 1  # so um documento_id venceu a corrida
    assert sum(1 for _, criado in resultados if criado) == 1
    assert sum(1 for _, criado in resultados if not criado) == n - 1
    assert len(RepositorioDocumentosPostgres(_ConexaoFalsa(banco)).listar_todos()) == 1


def test_postgres_reinicializacao_simulada_dados_sobrevivem():
    """Nova 'conexao' apontando para o MESMO banco de fundo encontra os
    dados persistidos por uma conexao anterior -- ao contrario do
    repositorio em memoria (Fase 1), que perde tudo."""
    banco = _BancoFalso()
    h = 'hashreinicio' * 5

    repo_antes_reiniciar = RepositorioDocumentosPostgres(_ConexaoFalsa(banco))
    original = _documento_teste('doc-sobrevive', h)
    repo_antes_reiniciar.salvar(original)

    # simula reinicializacao: nova conexao, mesmo banco de fundo
    repo_depois_reiniciar = RepositorioDocumentosPostgres(_ConexaoFalsa(banco))
    assert repo_depois_reiniciar.buscar_por_id('doc-sobrevive') == original
    assert repo_depois_reiniciar.buscar_por_hash(h) == original

    # contraste: um banco de fundo NOVO (diferente) nao tem os dados
    banco_diferente = _BancoFalso()
    repo_banco_diferente = RepositorioDocumentosPostgres(_ConexaoFalsa(banco_diferente))
    assert repo_banco_diferente.buscar_por_id('doc-sobrevive') is None


# ============================================================================
# adapter Postgres -- rollback explicito em falha (correcao BLOCKING da
# revisao do commit a44bb10)
# ============================================================================

def test_postgres_salvar_execute_falha_aciona_rollback_e_propaga():
    banco = _BancoFalso()
    conexao = _ConexaoFalsa(banco)
    repo = RepositorioDocumentosPostgres(conexao)

    conexao.falhar_no_proximo_execute = True
    with pytest.raises(ConnectionError):
        repo.salvar(_documento_teste('doc-exec-falha', 'hashexecfalha' * 5))

    assert conexao.rollbacks == 1
    assert conexao.commits == 0


def test_postgres_salvar_commit_falha_aciona_rollback_e_propaga():
    banco = _BancoFalso()
    conexao = _ConexaoFalsa(banco)
    repo = RepositorioDocumentosPostgres(conexao)

    conexao.falhar_no_proximo_commit = True
    with pytest.raises(ConnectionError):
        repo.salvar(_documento_teste('doc-commit-falha', 'hashcommitfalha' * 4))

    assert conexao.rollbacks == 1


def test_postgres_remover_execute_falha_aciona_rollback_e_propaga():
    banco = _BancoFalso()
    conexao = _ConexaoFalsa(banco)
    repo = RepositorioDocumentosPostgres(conexao)
    repo.salvar(_documento_teste('doc-remover-falha', 'hashremoverfalha' * 4))

    conexao.falhar_no_proximo_execute = True
    with pytest.raises(ConnectionError):
        repo.remover('doc-remover-falha')

    assert conexao.rollbacks == 1
    # documento nao foi removido -- o DELETE nunca foi efetivado (o fake
    # simula a falha ANTES de mutar o banco, ver _CursorFalso.execute)
    assert repo.buscar_por_id('doc-remover-falha') is not None


def test_postgres_fake_conexao_bloqueada_ate_rollback_explicito():
    """Prova a fidelidade do duplo de teste: uma falha de execute deixa a
    'conexao' em estado abortado, bloqueando qualquer operacao seguinte
    ate um rollback() explicito -- exatamente o comportamento real do
    Postgres que motivou adicionar try/except com rollback explicito em
    RepositorioDocumentosPostgres.salvar()/remover() e
    RepositorioHistoricoPostgres.registrar() (revisao do commit a44bb10).
    Este teste opera diretamente na conexao falsa, sem passar pelo
    rollback automatico do adapter, para isolar o comportamento do fake."""
    banco = _BancoFalso()
    conexao = _ConexaoFalsa(banco)

    conexao.falhar_no_proximo_execute = True
    with pytest.raises(ConnectionError):
        with conexao.cursor() as cur:
            cur.execute('INSERT INTO documentos (documento_id) VALUES (%s)', ('x',))

    with pytest.raises(RuntimeError, match='aborted'):
        conexao.cursor()
    with pytest.raises(RuntimeError, match='aborted'):
        conexao.commit()

    conexao.rollback()
    assert conexao.cursor() is not None  # nao levanta mais apos rollback()


def test_postgres_nova_operacao_funciona_apos_rollback_automatico_do_adapter():
    """Ao contrario do teste acima (que prova o bloqueio no nivel do
    fake), este prova que o rollback automatico DENTRO do adapter
    (salvar/remover/registrar) e suficiente -- o chamador nao precisa
    fazer nada alem de tratar a excecao propagada; a proxima operacao na
    MESMA conexao ja funciona normalmente."""
    banco = _BancoFalso()
    conexao = _ConexaoFalsa(banco)
    repo = RepositorioDocumentosPostgres(conexao)

    conexao.falhar_no_proximo_execute = True
    with pytest.raises(ConnectionError):
        repo.salvar(_documento_teste('doc-falha-1', 'hashfalha1' * 6))

    assert conexao.rollbacks == 1  # rollback ja aconteceu, sem intervencao externa

    repo.salvar(_documento_teste('doc-ok-depois', 'hashokdepois' * 5))
    assert repo.buscar_por_id('doc-ok-depois') is not None


# ============================================================================
# adapter Postgres -- historico
# ============================================================================

def test_postgres_historico_chave_estrangeira_obrigatoria():
    banco = _BancoFalso()
    repo_hist = RepositorioHistoricoPostgres(_ConexaoFalsa(banco))
    evento = _evento_teste('documento-que-nao-existe')
    with pytest.raises(IntegrityError):
        repo_hist.registrar(evento)


def test_postgres_historico_append_only_rejeita_update_delete():
    banco = _BancoFalso()
    conexao = _ConexaoFalsa(banco)
    with conexao.cursor() as cur:
        with pytest.raises(IntegrityError):
            cur.execute('UPDATE eventos_documentais SET evento = %s WHERE evento_id = %s', ('X', 1))
        with pytest.raises(IntegrityError):
            cur.execute('DELETE FROM eventos_documentais WHERE evento_id = %s', (1,))


def test_postgres_historico_ordenacao_por_timestamp():
    banco = _BancoFalso()
    repo_docs = RepositorioDocumentosPostgres(_ConexaoFalsa(banco))
    repo_hist = RepositorioHistoricoPostgres(_ConexaoFalsa(banco))
    doc = _documento_teste('doc-ordem', 'hashordem' * 6)
    repo_docs.salvar(doc)

    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
    repo_hist.registrar(_evento_teste('doc-ordem', evento='SEGUNDO', timestamp=t2))
    repo_hist.registrar(_evento_teste('doc-ordem', evento='PRIMEIRO', timestamp=t1))

    eventos = repo_hist.listar_por_documento('doc-ordem')
    assert [e.evento for e in eventos] == ['PRIMEIRO', 'SEGUNDO']


def test_postgres_historico_correlation_id_preservado():
    banco = _BancoFalso()
    repo_docs = RepositorioDocumentosPostgres(_ConexaoFalsa(banco))
    repo_hist = RepositorioHistoricoPostgres(_ConexaoFalsa(banco))
    repo_docs.salvar(_documento_teste('doc-corr', 'hashcorr' * 8))
    repo_hist.registrar(_evento_teste('doc-corr', correlation_id='corr-pg-123'))

    eventos = repo_hist.listar_por_documento('doc-corr')
    assert eventos[0].correlation_id == 'corr-pg-123'


def test_postgres_historico_registrar_execute_falha_aciona_rollback_e_propaga():
    banco = _BancoFalso()
    conexao = _ConexaoFalsa(banco)
    repo_docs = RepositorioDocumentosPostgres(conexao)
    repo_hist = RepositorioHistoricoPostgres(conexao)
    repo_docs.salvar(_documento_teste('doc-hist-exec-falha', 'hashhistexecfalha' * 3))

    conexao.falhar_no_proximo_execute = True
    with pytest.raises(ConnectionError):
        repo_hist.registrar(_evento_teste('doc-hist-exec-falha'))

    assert conexao.rollbacks == 1

    # nova operacao (documento diferente) na mesma conexao funciona
    # imediatamente apos o rollback automatico do adapter
    repo_docs.salvar(_documento_teste('doc-hist-exec-falha-2', 'hashhistexecfalha2' * 2))
    repo_hist.registrar(_evento_teste('doc-hist-exec-falha-2'))
    assert len(repo_hist.listar_por_documento('doc-hist-exec-falha-2')) == 1


# ============================================================================
# operacao de entrada da Fase 2 (storage + Fase 1)
# ============================================================================

def test_entrada_com_armazenamento_persiste_arquivo_documento_e_historico():
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()

    documento = registrar_entrada_com_armazenamento(
        repo_docs, repo_hist, armazenamento,
        b'conteudo entrada persistente', 'holerite.pdf', 'application/pdf', 'upload_manual',
    )

    assert documento.status == StatusDocumento.REGISTRADO
    assert armazenamento.existe(documento.hash_sha256)
    assert documento.arquivo_original == armazenamento.referencia(documento.hash_sha256)
    eventos = repo_hist.listar_por_documento(documento.documento_id)
    assert [e.evento for e in eventos] == ['DOCUMENTO_RECEBIDO', 'DOCUMENTO_REGISTRADO']


def test_entrada_com_armazenamento_falha_no_armazenamento_nao_cria_documento():
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()

    class _ArmazenamentoQueFalha:
        def armazenar(self, *_a, **_kw):
            raise RuntimeError('S3 indisponivel (simulado)')

    with pytest.raises(FalhaArmazenamento):
        registrar_entrada_com_armazenamento(
            repo_docs, repo_hist, _ArmazenamentoQueFalha(),
            b'conteudo que nao sera armazenado', 'x.pdf', 'application/pdf', 'upload_manual',
        )

    assert repo_docs.listar_todos() == []
    assert repo_hist.listar_todos() == []


def test_entrada_com_armazenamento_compensacao_arquivo_permanece_apos_falha_no_documento():
    """Armazenamento tem sucesso; o registro do Documento falha (banco
    fora do ar). O arquivo permanece armazenado -- nao e removido
    automaticamente -- e uma nova tentativa com o mesmo conteudo
    reaproveita o arquivo ja armazenado."""
    armazenamento = ArmazenamentoArquivosEmMemoria()
    conteudo = b'conteudo com falha no documento mas armazenado'

    class _RepoDocumentosQueFalha:
        def buscar_por_hash(self, hash_sha256):
            return None

        def buscar_por_id(self, documento_id):
            return None

        def salvar(self, documento):
            pass

        def salvar_se_ausente_por_hash(self, hash_sha256, fabricar_documento):
            raise RuntimeError('banco indisponivel (simulado)')

        def remover(self, documento_id):
            pass

        def listar_todos(self):
            return []

    repo_hist = RepositorioHistoricoEmMemoria()

    with pytest.raises(FalhaPersistencia):
        registrar_entrada_com_armazenamento(
            _RepoDocumentosQueFalha(), repo_hist, armazenamento,
            conteudo, 'y.pdf', 'application/pdf', 'upload_manual',
        )

    hash_sha256 = _sha(conteudo)
    assert armazenamento.existe(hash_sha256)  # arquivo NAO foi removido

    # nova tentativa (com repositorio funcional) reaproveita o arquivo ja armazenado
    repo_docs_ok = RepositorioDocumentosEmMemoria()
    documento = registrar_entrada_com_armazenamento(
        repo_docs_ok, RepositorioHistoricoEmMemoria(), armazenamento,
        conteudo, 'y.pdf', 'application/pdf', 'upload_manual',
    )
    assert documento.status == StatusDocumento.REGISTRADO


def test_entrada_com_armazenamento_nunca_cria_dois_documentos_para_mesmo_hash():
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()
    conteudo = b'conteudo idempotente entrada persistente'

    doc1 = registrar_entrada_com_armazenamento(
        repo_docs, repo_hist, armazenamento, conteudo, 'a.pdf', 'application/pdf', 'upload_manual',
    )
    doc2 = registrar_entrada_com_armazenamento(
        repo_docs, repo_hist, armazenamento, conteudo, 'b.pdf', 'application/pdf', 'outra_origem',
    )

    assert doc1.documento_id == doc2.documento_id
    assert len(repo_docs.listar_todos()) == 1


# ============================================================================
# helpers
# ============================================================================

def _sha(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def _documento_teste(documento_id, hash_sha256):
    from magnata_os.documental.modulo01.dominio import Documento
    agora = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Documento(
        documento_id=documento_id,
        arquivo_original=f'pendente-armazenamento://{hash_sha256}',
        nome_original='teste.pdf',
        mime_type='application/pdf',
        tamanho=100,
        hash_sha256=hash_sha256,
        origem='upload_manual',
        recebido_em=agora,
        lote_id=None,
        status=StatusDocumento.RECEBIDO,
        correlation_id='corr-teste',
        criado_em=agora,
        atualizado_em=agora,
    )


def _evento_teste(documento_id, evento='EVENTO_TESTE', correlation_id='corr-teste',
                   timestamp=None):
    from magnata_os.documental.modulo01.dominio import EventoHistorico
    return EventoHistorico(
        documento_id=documento_id,
        evento=evento,
        status_anterior=None,
        status_novo=StatusDocumento.RECEBIDO,
        timestamp=timestamp or datetime(2026, 1, 1, tzinfo=timezone.utc),
        correlation_id=correlation_id,
        detalhes={},
    )
