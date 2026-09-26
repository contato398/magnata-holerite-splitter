"""J3 contra PostgreSQL real/efêmero (CI: job postgres-real).

Prova no banco o que o schema promete: FK para `documentos` (nenhum
record-id externo), `UNIQUE (relacao_id, origem, sequencia)`, append-only,
idempotência de replay, concorrência sem duplicidade, relações legítimas
1:N coexistindo, histórico revisão -> resolvido, rollback reversível, e o
consumidor devolvendo Documento INTERNO. Termina com o ciclo real da
Prestação (corredor real, sem patch) lendo candidatos SÓ do índice
Postgres até readiness PRONTO / EM_REVISAO, Ordens por colaborador e
intenção de cliente separada.

Ids, clientes e colaboradores únicos por teste (o job reusa o mesmo banco
entre arquivos). Dados sintéticos; nenhuma rede além do Postgres local do
job; nenhum transporte.
"""
import hashlib
import os
import threading
import uuid
from datetime import datetime, timezone

import pytest

from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.classificacao.correlacao_documento_prestacao import (
    ORIGEM_CORREDOR_PRESTACAO,
    EstadoCorrelacao,
    chave_relacao,
)
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.documental.modulo01.dominio import Documento

_REAL = pytest.mark.skipif(
    not os.environ.get('MAGNATA_TEST_POSTGRES_REAL'),
    reason='requer MAGNATA_TEST_POSTGRES_REAL=1 e variáveis PG* padrão de libpq',
)
pytestmark = _REAL

AGORA = datetime(2099, 3, 1, tzinfo=timezone.utc)
_RAIZ = os.path.dirname(__file__)
_MIG_ORQ = os.path.join(_RAIZ, 'magnata_os', 'orquestrador', 'migrations')
_MIG_DOC = os.path.join(_RAIZ, 'magnata_os', 'documental', 'modulo01', 'migrations')
_TABELA = 'magnata_orquestrador.correlacao_documento_prestacao'


# ---------------------------------------------------------------------
# Infra do teste
# ---------------------------------------------------------------------

def _existe(conexao, regclass):
    # Mesmo formato já provado nos demais `_real` (literal constante do teste).
    with conexao.cursor() as cursor:
        cursor.execute(f"SELECT to_regclass('{regclass}')")
        existe = cursor.fetchone()[0] is not None
    conexao.commit()
    return existe


def _executar_arquivo(conexao, caminho):
    with open(caminho, encoding='utf-8') as arquivo, conexao.cursor() as cursor:
        cursor.execute(arquivo.read())
    conexao.commit()


def _garantir_migrations(conexao):
    if not _existe(conexao, 'magnata_orquestrador.execucoes'):
        _executar_arquivo(conexao, os.path.join(_MIG_ORQ, '0001_repositorio_execucoes.sql'))
    if not _existe(conexao, 'documentos'):
        _executar_arquivo(conexao, os.path.join(_MIG_DOC, '0001_criar_tabela_documentos.sql'))
    if not _existe(conexao, _TABELA):
        _executar_arquivo(conexao, os.path.join(_MIG_ORQ, '0007_correlacao_documento_prestacao.sql'))


_CONEXOES_ABERTAS = []


@pytest.fixture(autouse=True)
def _fechar_conexoes():
    """Toda conexão aberta por um teste é fechada no teardown, mesmo se
    o teste falhar -- nenhuma transação ociosa segura lock e bloqueia o
    DDL do teste de rollback."""
    yield
    while _CONEXOES_ABERTAS:
        conexao = _CONEXOES_ABERTAS.pop()
        try:
            conexao.close()
        except Exception:  # noqa: BLE001 -- teardown best effort
            pass


def _conectar():
    import psycopg
    conexao = psycopg.connect(autocommit=False)
    _CONEXOES_ABERTAS.append(conexao)
    _garantir_migrations(conexao)
    return conexao


def _sufixo():
    return uuid.uuid4().hex[:12]


def _documento(documento_id, conteudo):
    return Documento(
        documento_id=documento_id, arquivo_original=f'{documento_id}.pdf', nome_original=f'{documento_id}.pdf',
        mime_type='application/pdf', tamanho=len(conteudo), hash_sha256=hashlib.sha256(conteudo).hexdigest(),
        origem='teste-j3', recebido_em=AGORA, lote_id=None, status='RECEBIDO',
        correlation_id=f'corr-{documento_id}', criado_em=AGORA, atualizado_em=AGORA,
    )


def _salvar_documento(conexao, documento_id=None, conteudo=None):
    from magnata_os.documental.modulo01.adapters.postgres_repositorio import RepositorioDocumentosPostgres
    documento_id = documento_id or f'doc-j3-{_sufixo()}'
    documento = _documento(documento_id, conteudo or f'conteudo-{documento_id}'.encode())
    RepositorioDocumentosPostgres(conexao).salvar(documento)
    return documento


def _item(documento_id, cliente, competencia='2026-07', tipo='DOCUMENTO_A', colaborador=None):
    return ItemInventarioPrestacao(
        documento_id=documento_id, tipo_documental=tipo,
        cliente=ReferenciaCanonica('CLIENTE', cliente),
        competencia=ReferenciaCanonica('COMPETENCIA', competencia),
        colaborador=ReferenciaCanonica('COLABORADOR', colaborador) if colaborador else None,
    )


def _indice(conexao):
    from magnata_os.classificacao.adapters.postgres_correlacao_documento_prestacao import (
        RepositorioCorrelacaoDocumentoPrestacaoPostgres,
    )
    return RepositorioCorrelacaoDocumentoPrestacaoPostgres(conexao)


def _registrar(indice, documento_id, itens, origem=ORIGEM_CORREDOR_PRESTACAO):
    return indice.registrar_relacoes_do_documento(
        documento_id=documento_id, origem=origem, itens=tuple(itens),
        evidencia_sha256=None, registrado_em=AGORA,
    )


def _linhas(conexao, documento_id):
    with conexao.cursor() as cursor:
        cursor.execute(
            f'SELECT relacao_id, sequencia, estado FROM {_TABELA} WHERE documento_id = %s '
            'ORDER BY relacao_id, sequencia', (documento_id,),
        )
        linhas = cursor.fetchall()
    conexao.commit()
    return linhas


# ---------------------------------------------------------------------
# Schema, constraints, transação
# ---------------------------------------------------------------------

def test_real_fk_rejeita_documento_inexistente_e_nada_fica_gravado():
    import psycopg
    conexao = _conectar()
    registro_externo = f'rec{_sufixo()}'  # forma de record-id do Airtable, não é Documento interno
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _registrar(_indice(conexao), registro_externo, [_item(registro_externo, f'cli-{_sufixo()}')])
    assert _linhas(conexao, registro_externo) == []
    conexao.close()


def test_real_replay_nao_duplica_e_relacoes_legitimas_coexistem():
    conexao = _conectar()
    documento = _salvar_documento(conexao)
    cli_a, cli_b = f'cli-a-{_sufixo()}', f'cli-b-{_sufixo()}'
    itens = [_item(documento.documento_id, cli_a), _item(documento.documento_id, cli_b)]
    indice = _indice(conexao)

    primeiro = _registrar(indice, documento.documento_id, itens)
    segundo = _registrar(indice, documento.documento_id, list(reversed(itens)))

    assert (primeiro.novas, segundo.gravadas, segundo.inalteradas) == (2, 0, 2)
    assert len(_linhas(conexao, documento.documento_id)) == 2
    for cliente in (cli_a, cli_b):
        assert [i.documento_id for i in indice.listar(
            ReferenciaCanonica('CLIENTE', cliente), ReferenciaCanonica('COMPETENCIA', '2026-07'),
        )] == [documento.documento_id]
    conexao.close()


def test_real_revisao_e_nova_evidencia_preservam_historico_append_only():
    conexao = _conectar()
    documento = _salvar_documento(conexao)
    cliente = f'cli-{_sufixo()}'
    indice = _indice(conexao)
    item = _item(documento.documento_id, cliente, colaborador=f'col-{_sufixo()}')

    _registrar(indice, documento.documento_id, [item])
    _registrar(indice, documento.documento_id, [])        # revisão
    vazio = indice.listar(item.cliente, item.competencia)
    _registrar(indice, documento.documento_id, [item])    # resolvido de novo

    assert vazio == ()
    assert [(o.estado, o.sequencia) for o in indice.historico_do_documento(documento.documento_id)] == [
        (EstadoCorrelacao.VIGENTE, 1), (EstadoCorrelacao.SUPERADA, 2), (EstadoCorrelacao.VIGENTE, 3),
    ]
    assert indice.listar(item.cliente, item.competencia) == (item,)
    conexao.close()


def test_real_append_only_e_versao_unica_impostos_pelo_banco():
    import psycopg
    conexao = _conectar()
    documento = _salvar_documento(conexao)
    item = _item(documento.documento_id, f'cli-{_sufixo()}')
    _registrar(_indice(conexao), documento.documento_id, [item])

    with pytest.raises(psycopg.errors.RaiseException):
        with conexao.cursor() as cursor:
            cursor.execute(f"UPDATE {_TABELA} SET estado = 'SUPERADA' WHERE documento_id = %s",
                           (documento.documento_id,))
    conexao.rollback()
    with pytest.raises(psycopg.errors.RaiseException):
        with conexao.cursor() as cursor:
            cursor.execute(f'DELETE FROM {_TABELA} WHERE documento_id = %s', (documento.documento_id,))
    conexao.rollback()
    with pytest.raises(psycopg.errors.UniqueViolation):
        with conexao.cursor() as cursor:
            cursor.execute(
                f'INSERT INTO {_TABELA} (relacao_id, sequencia, documento_id, cliente_id, competencia, '
                'tipo_documental, colaborador_id, estado, origem, evidencia_sha256, registrado_em) '
                "VALUES (%s, 1, %s, %s, '2026-07', 'DOCUMENTO_A', NULL, 'VIGENTE', %s, NULL, %s)",
                (chave_relacao(item), documento.documento_id, item.cliente.entidade_id,
                 ORIGEM_CORREDOR_PRESTACAO, AGORA),
            )
    conexao.rollback()
    assert len(_linhas(conexao, documento.documento_id)) == 1
    conexao.close()


@pytest.mark.parametrize('competencia', ['07/2026', '2026-13', '2026-7'])
def test_real_check_de_competencia(competencia):
    import psycopg
    conexao = _conectar()
    documento = _salvar_documento(conexao)
    with pytest.raises(psycopg.errors.CheckViolation):
        with conexao.cursor() as cursor:
            cursor.execute(
                f'INSERT INTO {_TABELA} (relacao_id, sequencia, documento_id, cliente_id, competencia, '
                'tipo_documental, colaborador_id, estado, origem, evidencia_sha256, registrado_em) '
                "VALUES (%s, 1, %s, 'cli', %s, 'DOCUMENTO_A', NULL, 'VIGENTE', 'o', NULL, %s)",
                ('a' * 64, documento.documento_id, competencia, AGORA),
            )
    conexao.rollback()
    conexao.close()


def test_real_concorrencia_mesmo_documento_nunca_duplica_versao():
    conexao = _conectar()
    documento = _salvar_documento(conexao)
    itens = [_item(documento.documento_id, f'cli-{_sufixo()}')]
    barreira = threading.Barrier(6)
    resultados, erros = [], []

    def _processar():
        outra = _conectar()
        try:
            barreira.wait()
            resultados.append(_registrar(_indice(outra), documento.documento_id, itens).novas)
        except Exception as exc:  # noqa: BLE001 -- verificado abaixo
            erros.append(exc)
        finally:
            outra.close()

    threads = [threading.Thread(target=_processar) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert erros == []
    assert sorted(resultados) == [0, 0, 0, 0, 0, 1]
    assert len(_linhas(conexao, documento.documento_id)) == 1
    conexao.close()


def test_real_consumidor_devolve_documento_interno_para_a_necessidade_exata():
    from magnata_os.classificacao.adapters.postgres_correlacao_documento_prestacao import (
        construir_fonte_candidatos_por_necessidade_postgres,
    )
    conexao = _conectar()
    cliente, colab = f'cli-{_sufixo()}', f'col-{_sufixo()}'
    doc_pessoa = _salvar_documento(conexao)
    doc_cliente = _salvar_documento(conexao)
    indice = _indice(conexao)
    _registrar(indice, doc_pessoa.documento_id, [_item(doc_pessoa.documento_id, cliente, colaborador=colab)])
    _registrar(indice, doc_cliente.documento_id, [_item(doc_cliente.documento_id, cliente, tipo='DOCUMENTO_C')])
    fonte = construir_fonte_candidatos_por_necessidade_postgres(conexao)

    def _ids(tipo='DOCUMENTO_A', cliente_id=cliente, competencia='2026-07', colaborador=colab):
        return [d.documento_id for d in fonte.candidatos_para(NecessidadeDocumentoPrestacao(
            cliente=ReferenciaCanonica('CLIENTE', cliente_id),
            competencia=ReferenciaCanonica('COMPETENCIA', competencia), tipo_documental=tipo,
            motivo_exigencia='teste-j3-real',
            colaborador=ReferenciaCanonica('COLABORADOR', colaborador) if colaborador else None,
        ))]

    assert _ids() == [doc_pessoa.documento_id]
    candidato = fonte.candidatos_para(NecessidadeDocumentoPrestacao(
        cliente=ReferenciaCanonica('CLIENTE', cliente), competencia=ReferenciaCanonica('COMPETENCIA', '2026-07'),
        tipo_documental='DOCUMENTO_A', motivo_exigencia='x', colaborador=ReferenciaCanonica('COLABORADOR', colab),
    ))[0]
    assert isinstance(candidato, Documento) and candidato.hash_sha256 == doc_pessoa.hash_sha256
    assert _ids(cliente_id=f'outro-{_sufixo()}') == []
    assert _ids(competencia='2026-08') == []
    assert _ids(tipo='DOCUMENTO_B') == []
    assert _ids(colaborador=f'outro-{_sufixo()}') == []
    assert _ids(tipo='DOCUMENTO_C', colaborador=None) == [doc_cliente.documento_id]
    assert _ids(tipo='DOCUMENTO_A', colaborador=None) == []
    conexao.close()


def test_real_ponto_temporal_ligado_a_dois_clientes_sem_duplicar_documento():
    import datetime as dt

    from magnata_os.classificacao.correlacao_documento_prestacao import registrar_correlacoes_de_ponto
    from magnata_os.classificacao.resolucao_temporal_ponto import AlocacaoHistorica, resolver_documento_ponto

    conexao = _conectar()
    documento = _salvar_documento(conexao)
    cli_a, cli_b, colab = f'cli-a-{_sufixo()}', f'cli-b-{_sufixo()}', f'col-{_sufixo()}'

    class _Alocacoes:
        def listar_para_colaborador(self, colaborador_id):
            return (
                AlocacaoHistorica(colab, cli_a, dt.date(2026, 1, 1), dt.date(2026, 6, 10)),
                AlocacaoHistorica(colab, cli_b, dt.date(2026, 6, 11), None),
            )

    resolucao, clientes = resolver_documento_ponto(
        documento.documento_id, 'Cartão de Ponto\nPeríodo: 29/05/2026 até 28/06/2026', colab, _Alocacoes(),
    )
    indice = _indice(conexao)
    assert registrar_correlacoes_de_ponto(
        indice, resolucao_documental=resolucao, resolucao_cliente=clientes, registrado_em=AGORA,
    ).novas == 2
    comp = ReferenciaCanonica('COMPETENCIA', '2026-06')
    for cliente in (cli_a, cli_b):
        assert [i.documento_id for i in indice.listar(ReferenciaCanonica('CLIENTE', cliente), comp)] == [
            documento.documento_id,
        ]
    with conexao.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM documentos WHERE documento_id = %s', (documento.documento_id,))
        assert cursor.fetchone()[0] == 1
    conexao.commit()
    conexao.close()


# ---------------------------------------------------------------------
# Ciclo real da Prestação lendo candidatos SÓ do índice Postgres
# ---------------------------------------------------------------------

def _texto_holerite(cpf_formatado, marca):
    return (f'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026\n'
            f'CPF: {cpf_formatado}\nControle: {marca}')


def _texto_extrato(cnpj, marca):
    return f'Extrato Mensal\nCNPJ: {cnpj}\nCompetência: 07/2026\nControle: {marca}'


def _pdf(texto):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.set_creation_date(AGORA)
    pdf.add_page()
    pdf.set_font('Helvetica', size=12)
    pdf.multi_cell(0, 10, text=texto)
    return bytes(pdf.output())


class _Fontes:
    """Fontes de referência sintéticas, parametrizadas por cliente (o
    banco é compartilhado entre testes)."""

    def __init__(self, cliente, colaboradores, cnpj):
        self.cliente = cliente
        self.colaboradores = colaboradores
        self.cnpj = cnpj

    # FonteClientesPrestacao
    def listar_ativos(self, contexto=None):
        return (self.cliente,)

    # FonteRequisitosPrestacao
    def registros_para(self, cliente, contexto):
        return ()

    # FonteColaboradoresEsperadosPrestacao
    def colaboradores_esperados_para(self, cliente, contexto):
        return self.colaboradores if cliente == self.cliente else ()

    # FonteVinculosPrestacao
    def resolver_clientes(self, origem, competencia):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(self.cliente,),
        )

    # FonteUnidadePostoPrestacao
    def resolver_unidade_posto(self, colaborador, competencia):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(ReferenciaCanonica('UNIDADE_POSTO', f'posto-{self.cliente.entidade_id}'),),
        )

    # FonteClienteDiretoDocumento
    def resolver_cliente_direto(self, texto_documento):
        return self.cliente if self.cnpj in texto_documento else None


class _RepositorioExecucoesPrestacaoMemoria:
    def criar(self, execucao):
        pass

    def buscar_por_id(self, execucao_prestacao_id):
        return None

    def atualizar_estado(self, **kwargs):
        pass


def montar_cenario_ciclo(repositorio_documentos, indice, fonte_candidatos, *, com_extrato=True, com_holerite_b=True):
    """Ingestão (corredor real -> produtor -> índice) e contexto do ciclo
    com candidatos vindos SÓ do índice. Reutilizável com o twin em
    memória (mesmo comportamento) -- validação local do cenário."""
    from magnata_os.classificacao.competencia_esperada_prestacao import (
        POLITICA_COMPETENCIA_PRESTACAO_V1,
        ContextoCicloPrestacao,
    )
    from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import ContextoComposicaoPrestacao
    from magnata_os.classificacao.correlacao_documento_prestacao import registrar_correlacoes_do_corredor
    from magnata_os.classificacao.holerite_obrigatorio_prestacao import TIPO_HOLERITE
    from magnata_os.classificacao.inventario_prestacao_memoria import InventarioPrestacaoEmMemoria
    from magnata_os.classificacao.orquestrador_corredor_readonly import (
        ContextoExecucaoCorredorPrestacao,
        executar_documento_readonly,
    )
    from magnata_os.classificacao.prestacao_readiness import RequisitoDocumentalPrestacao
    from magnata_os.documental.extracao_texto import extrair_texto_pdf
    from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario
    from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria

    marca = _sufixo()
    cliente = ReferenciaCanonica('CLIENTE', f'cli-{marca}')
    col_a = ReferenciaCanonica('COLABORADOR', f'col-a-{marca}')
    col_b = ReferenciaCanonica('COLABORADOR', f'col-b-{marca}')
    cnpj = '11.222.333/0001-44'
    fontes = _Fontes(cliente, (col_a, col_b), cnpj)
    candidatos = (
        CandidatoFuncionario(func_id=col_a.entidade_id, cpf='11122233344', nome_normalizado='FULANO SINTETICO'),
        CandidatoFuncionario(func_id=col_b.entidade_id, cpf='22233344455', nome_normalizado='BELTRANO SINTETICO'),
    )
    textos = {f'doc-a-{marca}': _texto_holerite('111.222.333-44', marca)}
    if com_holerite_b:
        textos[f'doc-b-{marca}'] = _texto_holerite('222.333.444-55', marca)
    if com_extrato:
        textos[f'doc-ext-{marca}'] = _texto_extrato(cnpj, marca)

    armazenamento = ArmazenamentoArquivosEmMemoria()
    for documento_id, texto in textos.items():
        conteudo = _pdf(texto)
        documento = _documento(documento_id, conteudo)
        repositorio_documentos.salvar(documento)
        armazenamento.armazenar(documento.hash_sha256, conteudo, 'application/pdf',
                                documento.nome_original, len(conteudo))
        contexto_corredor = ContextoExecucaoCorredorPrestacao(
            documento_id=documento_id, hash_sha256=documento.hash_sha256,
            paginas=(extrair_texto_pdf(conteudo),), ciclo=ContextoCicloPrestacao((2026, 7)),
            cliente_do_ciclo=None, politica_competencia=POLITICA_COMPETENCIA_PRESTACAO_V1,
            candidatos_colaborador=candidatos, fonte_vinculos=fontes, fonte_cliente_direto=fontes,
            fonte_unidade_posto=fontes, fonte_candidatos_relacao=None, clientes_broadcast=(),
            identificar_pagina=None, personalizar_contexto_do_grupo=None,
            registrar_dados_correlacao=False, fonte_inventario_pacote=None, politica_requisitos=None,
        )
        registrar_correlacoes_do_corredor(
            indice, documento_id=documento_id, registrado_em=AGORA,
            resultados_corredor=executar_documento_readonly(contexto_corredor, InventarioPrestacaoEmMemoria()),
        )

    contexto = ContextoComposicaoPrestacao(
        competencia_base='2026-07', fonte_clientes=fontes, fonte_requisitos=fontes,
        repositorio_execucoes=_RepositorioExecucoesPrestacaoMemoria(),
        requisitos_base=(
            RequisitoDocumentalPrestacao(TIPO_HOLERITE),
            RequisitoDocumentalPrestacao('Extrato da Folha de Pagamento'),
        ),
        competencias_por_cliente={cliente: ReferenciaCanonica('COMPETENCIA', '2026-07')},
        fonte_colaboradores_esperados=fontes, tipos_obrigatorios_por_colaborador=(TIPO_HOLERITE,),
        fonte_candidatos_por_necessidade=fonte_candidatos,
        repositorio_documentos=repositorio_documentos, armazenamento_arquivos=armazenamento,
        candidatos_colaborador=candidatos, fonte_vinculos=fontes, fonte_unidade_posto=fontes,
        fonte_cliente_direto=fontes,
    )
    return contexto, marca, (col_a, col_b)


def test_real_ciclo_pelo_indice_postgres_pronto_ordens_por_colaborador_e_intencao_separada():
    from magnata_os.classificacao.adapters.postgres_correlacao_documento_prestacao import (
        construir_fonte_candidatos_por_necessidade_postgres,
    )
    from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import diagnosticar_prestacao_upstream
    from magnata_os.documental.modulo01.adapters.postgres_repositorio import RepositorioDocumentosPostgres

    conexao = _conectar()
    contexto, marca, (col_a, col_b) = montar_cenario_ciclo(
        RepositorioDocumentosPostgres(conexao), _indice(conexao),
        construir_fonte_candidatos_por_necessidade_postgres(conexao),
    )
    diagnostico = diagnosticar_prestacao_upstream(contexto)

    (cliente,) = diagnostico.clientes
    assert cliente.estado_pacote == 'PRONTO'
    grupos = {g[0].necessidade.colaborador.entidade_id: [r.documento_id for r in g]
              for _c, _k, g in diagnostico.grupos_por_colaborador()}
    assert grupos == {col_a.entidade_id: [f'doc-a-{marca}'], col_b.entidade_id: [f'doc-b-{marca}']}
    (intencao,) = diagnostico.intencoes_cliente()
    assert intencao.documento_ids == (f'doc-ext-{marca}',)
    conexao.close()


def test_real_ciclo_pelo_indice_postgres_sem_holerite_de_b_fica_fora_de_pronto():
    from magnata_os.classificacao.adapters.postgres_correlacao_documento_prestacao import (
        construir_fonte_candidatos_por_necessidade_postgres,
    )
    from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import diagnosticar_prestacao_upstream
    from magnata_os.documental.modulo01.adapters.postgres_repositorio import RepositorioDocumentosPostgres

    conexao = _conectar()
    contexto, _marca, _cols = montar_cenario_ciclo(
        RepositorioDocumentosPostgres(conexao), _indice(conexao),
        construir_fonte_candidatos_por_necessidade_postgres(conexao), com_holerite_b=False,
    )
    diagnostico = diagnosticar_prestacao_upstream(contexto)
    (cliente,) = diagnostico.clientes
    assert cliente.estado_pacote != 'PRONTO'
    assert diagnostico.trios_prontos == () and diagnostico.intencoes_cliente() == ()
    conexao.close()


def test_real_rollback_remove_so_a_0007_e_reaplicacao_restaura():
    conexao = _conectar()
    _executar_arquivo(conexao, os.path.join(_MIG_ORQ, '0007_correlacao_documento_prestacao_rollback.sql'))
    assert not _existe(conexao, _TABELA)
    assert _existe(conexao, 'documentos')                       # dependência intacta
    with conexao.cursor() as cursor:                             # função da 0001 preservada
        cursor.execute("SELECT to_regprocedure('magnata_orquestrador.bloquear_mutacao_auditoria()')")
        assert cursor.fetchone()[0] is not None
    conexao.commit()
    _executar_arquivo(conexao, os.path.join(_MIG_ORQ, '0007_correlacao_documento_prestacao.sql'))
    assert _existe(conexao, _TABELA)
    conexao.close()


def test_real_mesma_relacao_de_duas_origens_tem_historias_independentes():
    from magnata_os.classificacao.correlacao_documento_prestacao import ORIGEM_RESOLUCAO_TEMPORAL_PONTO
    conexao = _conectar()
    documento = _salvar_documento(conexao)
    item = _item(documento.documento_id, f'cli-{_sufixo()}', tipo='Folha de Ponto', colaborador=f'col-{_sufixo()}')
    indice = _indice(conexao)

    assert _registrar(indice, documento.documento_id, [item], origem=ORIGEM_CORREDOR_PRESTACAO).novas == 1
    assert _registrar(indice, documento.documento_id, [item], origem=ORIGEM_RESOLUCAO_TEMPORAL_PONTO).novas == 1
    _registrar(indice, documento.documento_id, [], origem=ORIGEM_CORREDOR_PRESTACAO)        # só o corredor supera
    assert indice.listar(item.cliente, item.competencia) == (item,)                        # ponto ainda sustenta
    assert _registrar(indice, documento.documento_id, [item], origem=ORIGEM_CORREDOR_PRESTACAO).reativadas == 1
    assert sorted((o.origem, o.sequencia, o.estado.value) for o in indice.historico_do_documento(documento.documento_id)) == [
        (ORIGEM_CORREDOR_PRESTACAO, 1, 'VIGENTE'), (ORIGEM_CORREDOR_PRESTACAO, 2, 'SUPERADA'),
        (ORIGEM_CORREDOR_PRESTACAO, 3, 'VIGENTE'), (ORIGEM_RESOLUCAO_TEMPORAL_PONTO, 1, 'VIGENTE'),
    ]


def test_real_reprocessar_sob_outro_ciclo_nunca_supera_relacao_de_outra_competencia():
    conexao = _conectar()
    documento = _salvar_documento(conexao)
    item = _item(documento.documento_id, f'cli-{_sufixo()}', competencia='2026-07')
    indice = _indice(conexao)
    _registrar(indice, documento.documento_id, [item])
    resultado = indice.registrar_relacoes_do_documento(
        documento_id=documento.documento_id, origem=ORIGEM_CORREDOR_PRESTACAO, itens=(),
        evidencia_sha256=None, registrado_em=AGORA, competencias_superaveis=frozenset({'2026-08'}),
    )
    assert resultado.gravadas == 0
    assert indice.listar(item.cliente, item.competencia) == (item,)
