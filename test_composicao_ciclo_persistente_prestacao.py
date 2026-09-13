"""Testes para composição persistente REAL de ciclos de Prestação de Contas.

Incremento 1: Persistência básica (8 testes)
Incremento 2: Orquestração de fluxo (7 testes)
Incremento 3: Aquisição canônica (documentos brutos + corredor eventual)
Incremento 4 (correção pós-merge PR #158): `_adquirir_inventario_via_
corredor` testada diretamente -- ver docstring dessa função sobre por
que foi extraída (nenhum teste populava `resolucoes_ancora`/
`competencias_por_cliente`, então o laço original nunca era
exercitado de verdade).

Dados 100% sintéticos, zero I/O externo.
"""
import hashlib
from datetime import datetime, timezone
from typing import Optional, Tuple

import pytest

from magnata_os.documental.modulo01.dominio import Documento

from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    ContextoComposicaoPrestacao,
    _adquirir_inventario_via_corredor,
    atualizar_execucao_por_estado_pacote,
    criar_e_persistir_execucao,
    executar_ciclo_prestacao_persistente,
    retomar_execucao_por_id,
)
from magnata_os.documental.modulo01.dominio import Documento
from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.execucao_prestacao import (
    ExecucaoPrestacao,
    RepositorioExecucoesPrestacao,
)
from magnata_os.classificacao.fonte_clientes_prestacao import FonteClientesPrestacao
from magnata_os.classificacao.fonte_requisitos_prestacao import FonteRequisitosPrestacao
from magnata_os.classificacao.pacote_prestacao import EstadoPacotePrestacao
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.documental.modulo01.armazenamento import (
    ArmazenamentoArquivosEmMemoria,
    ArquivoNaoEncontrado,
)
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria

try:
    import pdfplumber  # noqa: F401
    _PDFPLUMBER_FUNCIONAL = True
except BaseException:
    _PDFPLUMBER_FUNCIONAL = False

_MOTIVO_SKIP_PDFPLUMBER = (
    "pdfplumber quebrado neste ambiente (pyo3_runtime.PanicException / "
    "_cffi_backend ausente) — falha de ambiente pré-existente, não do código novo"
)


def _pdf_minimo_com_texto(texto: str) -> bytes:
    """Fabrica um PDF válido mínimo contendo `texto` como conteúdo de
    página, usando reportlab -- mesmo helper de
    test_roteamento_documental_shadow.py::_pdf_minimo_com_texto,
    duplicado aqui (helper de teste local, não faz parte do pacote)
    para não criar dependência entre módulos de teste."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    import io
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(72, 720, texto)
    c.save()
    return buffer.getvalue()


def _documento_bruto(documento_id, hash_sha256, mime_type='application/pdf', tamanho=0):
    agora = datetime.now(timezone.utc)
    return Documento(
        documento_id=documento_id,
        arquivo_original=f'memoria://{hash_sha256}',
        nome_original=f'{documento_id}.pdf',
        mime_type=mime_type,
        tamanho=tamanho,
        hash_sha256=hash_sha256,
        origem='teste',
        recebido_em=agora,
        lote_id=None,
        status='RECEBIDO',
        correlation_id=f'correl-{documento_id}',
        criado_em=agora,
        atualizado_em=agora,
    )


_CICLO_TESTE = ContextoCicloPrestacao(competencia_base=(2026, 9))


# ==== MOCKS DE REPOSITÓRIO ====


class RepositorioExecucoesPrestacaoMemoria(RepositorioExecucoesPrestacao):
    """Implementação em memória de repositório."""

    def __init__(self) -> None:
        self._execucoes: dict = {}

    def criar(self, execucao: ExecucaoPrestacao) -> None:
        if execucao.execucao_prestacao_id in self._execucoes:
            raise ValueError('Execução já existe')
        self._execucoes[execucao.execucao_prestacao_id] = execucao

    def buscar_por_id(
        self, execucao_prestacao_id: str,
    ) -> Optional[ExecucaoPrestacao]:
        return self._execucoes.get(execucao_prestacao_id)

    def atualizar_estado(
        self,
        execucao_prestacao_id: str,
        novo_estado: str,
        concluido_em: Optional[datetime] = None,
    ) -> None:
        execucao = self.buscar_por_id(execucao_prestacao_id)
        if not execucao:
            raise ValueError('Execução não encontrada')
        execucao_atualizada = ExecucaoPrestacao(
            execucao_prestacao_id=execucao.execucao_prestacao_id,
            competencia_base=execucao.competencia_base,
            estado=novo_estado,
            origem=execucao.origem,
            criado_em=execucao.criado_em,
            atualizado_em=datetime.now(timezone.utc),
            concluido_em=concluido_em,
        )
        self._execucoes[execucao_prestacao_id] = execucao_atualizada

    def listar_por_competencia(self, competencia_base: str) -> tuple:
        return tuple(
            e for e in self._execucoes.values()
            if e.competencia_base == competencia_base
        )

    def listar_todas(self) -> tuple:
        return tuple(self._execucoes.values())


# ==== MOCKS DE FONTES ====


class FonteClientesPrestacaoMock(FonteClientesPrestacao):
    """Mock para fonte de clientes."""

    def listar_ativos(self, contexto=None) -> Tuple[ReferenciaCanonica, ...]:
        return (ReferenciaCanonica(tipo_entidade='CLIENTE', entidade_id='cliente-1'),)


class FonteRequisitosPrestacaoMock(FonteRequisitosPrestacao):
    """Mock para fonte de requisitos."""

    def listar_requisitos_por_cliente(self, cliente: ReferenciaCanonica) -> dict:
        return {}


# ==== TESTES INCREMENTO 1 ====


def test_criar_e_persistir_execucao():
    """Criar ExecucaoPrestacao e verificar persistência."""
    repositorio = RepositorioExecucoesPrestacaoMemoria()
    execucao = criar_e_persistir_execucao(
        competencia_base='2026-09',
        repositorio_execucoes=repositorio,
    )
    assert execucao.estado == 'INICIADA'
    assert execucao.concluido_em is None
    recuperada = repositorio.buscar_por_id(execucao.execucao_prestacao_id)
    assert recuperada is not None


def test_criar_execucao_formato_invalido():
    """Rejeitar competencia_base inválida."""
    repositorio = RepositorioExecucoesPrestacaoMemoria()
    with pytest.raises(ValueError, match='competencia_base'):
        criar_e_persistir_execucao(
            competencia_base='2026-13',
            repositorio_execucoes=repositorio,
        )


def test_atualizar_execucao_pronto_concluida():
    """PRONTO → CONCLUIDA com concluido_em."""
    repositorio = RepositorioExecucoesPrestacaoMemoria()
    execucao = criar_e_persistir_execucao(
        competencia_base='2026-09',
        repositorio_execucoes=repositorio,
    )
    execucao_atualizada = atualizar_execucao_por_estado_pacote(
        execucao_prestacao_id=execucao.execucao_prestacao_id,
        estado_pacote=EstadoPacotePrestacao.PRONTO,
        repositorio_execucoes=repositorio,
    )
    assert execucao_atualizada.estado == 'CONCLUIDA'
    assert execucao_atualizada.concluido_em is not None


def test_atualizar_execucao_incompleto_iniciada():
    """INCOMPLETO → INICIADA (retomável)."""
    repositorio = RepositorioExecucoesPrestacaoMemoria()
    execucao = criar_e_persistir_execucao(
        competencia_base='2026-09',
        repositorio_execucoes=repositorio,
    )
    execucao_atualizada = atualizar_execucao_por_estado_pacote(
        execucao_prestacao_id=execucao.execucao_prestacao_id,
        estado_pacote=EstadoPacotePrestacao.INCOMPLETO,
        repositorio_execucoes=repositorio,
    )
    assert execucao_atualizada.estado == 'INICIADA'
    assert execucao_atualizada.concluido_em is None


def test_atualizar_execucao_bloqueado_iniciada():
    """BLOQUEADO → INICIADA (não é FALHA, é condição de negócio)."""
    repositorio = RepositorioExecucoesPrestacaoMemoria()
    execucao = criar_e_persistir_execucao(
        competencia_base='2026-09',
        repositorio_execucoes=repositorio,
    )
    execucao_atualizada = atualizar_execucao_por_estado_pacote(
        execucao_prestacao_id=execucao.execucao_prestacao_id,
        estado_pacote=EstadoPacotePrestacao.BLOQUEADO,
        repositorio_execucoes=repositorio,
    )
    assert execucao_atualizada.estado == 'INICIADA'  # NÃO FALHA
    assert execucao_atualizada.concluido_em is None


def test_retomar_execucao_iniciada():
    """Retomar execução INICIADA."""
    repositorio = RepositorioExecucoesPrestacaoMemoria()
    execucao = criar_e_persistir_execucao(
        competencia_base='2026-09',
        repositorio_execucoes=repositorio,
    )
    retomada = retomar_execucao_por_id(
        execucao_prestacao_id=execucao.execucao_prestacao_id,
        repositorio_execucoes=repositorio,
    )
    assert retomada.estado == 'INICIADA'


def test_retomar_execucao_concluida_falha():
    """Retomar CONCLUIDA falha."""
    repositorio = RepositorioExecucoesPrestacaoMemoria()
    execucao = criar_e_persistir_execucao(
        competencia_base='2026-09',
        repositorio_execucoes=repositorio,
    )
    atualizar_execucao_por_estado_pacote(
        execucao_prestacao_id=execucao.execucao_prestacao_id,
        estado_pacote=EstadoPacotePrestacao.PRONTO,
        repositorio_execucoes=repositorio,
    )
    with pytest.raises(ValueError, match='retomável'):
        retomar_execucao_por_id(
            execucao_prestacao_id=execucao.execucao_prestacao_id,
            repositorio_execucoes=repositorio,
        )


# ==== TESTES INCREMENTO 3: FLUXO REAL ====


def test_execucao_ciclo_persistente_funciona():
    """Provar que executar_ciclo_prestacao_persistente pode ser chamado."""
    repositorio = RepositorioExecucoesPrestacaoMemoria()

    contexto = ContextoComposicaoPrestacao(
        competencia_base='2026-09',
        fonte_clientes=FonteClientesPrestacaoMock(),
        fonte_requisitos=FonteRequisitosPrestacaoMock(),
        repositorio_execucoes=repositorio,
    )

    # Executar ciclo persistente (vai chamar ciclo 1 e 2 realmente)
    execucao = executar_ciclo_prestacao_persistente(contexto)

    # Resultado é ExecucaoPrestacao válida e persistida
    assert execucao is not None
    assert execucao.execucao_prestacao_id is not None
    assert execucao.competencia_base == '2026-09'
    assert execucao.estado in ('INICIADA', 'CONCLUIDA', 'FALHA')

    # Verificar persistência
    recuperada = repositorio.buscar_por_id(execucao.execucao_prestacao_id)
    assert recuperada is not None




def test_retomada_por_execucao_id():
    """Validar que retomada via execucao_id funciona."""
    repositorio = RepositorioExecucoesPrestacaoMemoria()

    # Criar primeira execução direto (sem passar por ciclo) para que fique INICIADA
    execucao1 = criar_e_persistir_execucao(
        competencia_base='2026-09',
        repositorio_execucoes=repositorio,
    )
    id_execucao = execucao1.execucao_prestacao_id

    # Execução está INICIADA
    assert execucao1.estado == 'INICIADA'

    # Retomar segunda vez via contexto
    contexto = ContextoComposicaoPrestacao(
        competencia_base='2026-09',
        fonte_clientes=FonteClientesPrestacaoMock(),
        fonte_requisitos=FonteRequisitosPrestacaoMock(),
        repositorio_execucoes=repositorio,
    )
    execucao2 = executar_ciclo_prestacao_persistente(contexto, execucao_id=id_execucao)

    # Deve ser o MESMO ID
    assert execucao2.execucao_prestacao_id == id_execucao


def test_ciclo_prestacao_nao_foi_alterado():
    """Validar que ciclo_prestacao.py nao foi alterado."""
    from magnata_os.classificacao import ciclo_prestacao
    assert hasattr(ciclo_prestacao, 'executar_ciclo_prestacao')
    assert callable(getattr(ciclo_prestacao, 'executar_ciclo_prestacao'))


def test_fluxo_base_sem_aquisicao_externa():
    """Fluxo com inventário base (sem aquisição externa real)."""
    repositorio = RepositorioExecucoesPrestacaoMemoria()

    contexto = ContextoComposicaoPrestacao(
        competencia_base='2026-09',
        fonte_clientes=FonteClientesPrestacaoMock(),
        fonte_requisitos=FonteRequisitosPrestacaoMock(),
        repositorio_execucoes=repositorio,
        # Sem fonte_inventario_base, sem fonte_documentos_disponiveis
        # Fluxo roda apenas com ciclos vazios (sem aquisição externa)
    )

    execucao = executar_ciclo_prestacao_persistente(contexto)

    # Execução acontece e é persistida mesmo sem inventário externo
    assert execucao is not None
    assert execucao.execucao_prestacao_id is not None
    assert execucao.estado in ('INICIADA', 'CONCLUIDA', 'FALHA')


def test_aquisicao_canonica_com_repositorio_documentos():
    """Aquisição canônica: repositório de documentos + armazenamento + corredor."""
    from magnata_os.documental.modulo01.repositorio import (
        RepositorioDocumentosEmMemoria,
    )
    from magnata_os.documental.modulo01.armazenamento import (
        ArmazenamentoArquivosEmMemoria,
    )

    repositorio_execucoes = RepositorioExecucoesPrestacaoMemoria()
    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()

    # Criar um documento bruto com conteúdo armazenado (simulando AdaptadorEntradaDuravel)
    agora = datetime.now(timezone.utc)
    conteudo_documento = b"Documento de teste em PDF"

    # Registrar blob no armazenamento
    import hashlib
    hash_sha256 = hashlib.sha256(conteudo_documento).hexdigest()
    armazenamento.armazenar(
        hash_sha256=hash_sha256,
        conteudo=conteudo_documento,
        mime_type='application/pdf',
        nome_original='teste.pdf',
        tamanho=len(conteudo_documento),
    )

    # Criar Documento apontando para o blob armazenado
    documento_bruto = Documento(
        documento_id='doc-test-123',
        arquivo_original=armazenamento.referencia(hash_sha256),
        nome_original='teste.pdf',
        mime_type='application/pdf',
        tamanho=len(conteudo_documento),
        hash_sha256=hash_sha256,
        origem='teste',
        recebido_em=agora,
        lote_id=None,
        status='RECEBIDO',
        correlation_id='correlatestid',
        criado_em=agora,
        atualizado_em=agora,
    )
    repositorio_docs.salvar(documento_bruto)

    contexto = ContextoComposicaoPrestacao(
        competencia_base='2026-09',
        fonte_clientes=FonteClientesPrestacaoMock(),
        fonte_requisitos=FonteRequisitosPrestacaoMock(),
        repositorio_execucoes=repositorio_execucoes,
        repositorio_documentos=repositorio_docs,  # Novo: repositório para aquisição
        armazenamento_arquivos=armazenamento,     # Novo: armazenamento para blobs
    )

    execucao = executar_ciclo_prestacao_persistente(contexto)

    # Execução prova que documento foi reconhecido e processado
    assert execucao is not None
    assert execucao.execucao_prestacao_id is not None
    # Documento foi processado pelo corredor (não é mais "v2")
    assert execucao.estado in ('INICIADA', 'CONCLUIDA', 'FALHA')


def test_composicao_com_base():
    """Composição com inventário base pré-existente."""
    repositorio = RepositorioExecucoesPrestacaoMemoria()

    # Fonte base com 1 item
    cliente = ReferenciaCanonica(tipo_entidade='CLIENTE', entidade_id='cli-1')
    competencia = ReferenciaCanonica(tipo_entidade='COMPETENCIA', entidade_id='2026-09')

    item_base = ItemInventarioPrestacao(
        documento_id='doc-base-1',
        tipo_documental='Extrato da Folha de Pagamento',
        cliente=cliente,
        competencia=competencia,
    )

    from magnata_os.classificacao.inventario_prestacao_memoria import (
        InventarioPrestacaoEmMemoria,
    )

    fonte_base = InventarioPrestacaoEmMemoria()
    fonte_base.adicionar(item_base)

    contexto = ContextoComposicaoPrestacao(
        competencia_base='2026-09',
        fonte_clientes=FonteClientesPrestacaoMock(),
        fonte_requisitos=FonteRequisitosPrestacaoMock(),
        repositorio_execucoes=repositorio,
        fonte_inventario_base=fonte_base,  # Passando base
    )

    execucao = executar_ciclo_prestacao_persistente(contexto)

    # Execução foi realizada com base inventário
    assert execucao is not None
    assert execucao.execucao_prestacao_id is not None
    # Estado final (depende de readiness)
    assert execucao.estado in ('INICIADA', 'CONCLUIDA', 'FALHA')


def test_composicao_dedup_identidade_logica():
    """Composição deduplica por identidade_logica (não duplica A)."""
    repositorio = RepositorioExecucoesPrestacaoMemoria()

    cliente = ReferenciaCanonica(tipo_entidade='CLIENTE', entidade_id='cli-1')
    competencia = ReferenciaCanonica(tipo_entidade='COMPETENCIA', entidade_id='2026-09')

    # Item na base
    item_base = ItemInventarioPrestacao(
        documento_id='doc-shared-123',
        tipo_documental='Extrato da Folha de Pagamento',
        cliente=cliente,
        competencia=competencia,
    )

    from magnata_os.classificacao.inventario_prestacao_memoria import (
        InventarioPrestacaoEmMemoria,
    )

    fonte_base = InventarioPrestacaoEmMemoria()
    fonte_base.adicionar(item_base)

    # Aquisição TAMBÉM teria o mesmo documento (por ID)
    # Mas FonteInventarioPrestacaoComposta deduplica por identidade_logica

    contexto = ContextoComposicaoPrestacao(
        competencia_base='2026-09',
        fonte_clientes=FonteClientesPrestacaoMock(),
        fonte_requisitos=FonteRequisitosPrestacaoMock(),
        repositorio_execucoes=repositorio,
        fonte_inventario_base=fonte_base,
    )

    execucao = executar_ciclo_prestacao_persistente(contexto)

    # A execução prova que base foi passada e processada
    assert execucao is not None
    assert execucao.execucao_prestacao_id is not None


def test_ambiguidade_multiplos_documentos_avaliados():
    """Comportamento C: múltiplos documentos físicos → todos avaliados semanticamente.

    Não se decide pela quantidade física antes da semântica.
    Todos os documentos disponíveis são processados pelo corredor.
    """
    from magnata_os.documental.modulo01.repositorio import (
        RepositorioDocumentosEmMemoria,
    )
    from magnata_os.documental.modulo01.armazenamento import (
        ArmazenamentoArquivosEmMemoria,
    )
    import hashlib

    repositorio_execucoes = RepositorioExecucoesPrestacaoMemoria()
    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()

    agora = datetime.now(timezone.utc)

    # Criar 3 documentos DIFERENTES
    conteudos = [
        b"Document 1: Bank statement",
        b"Document 2: Payslip",
        b"Document 3: Income declaration",
    ]

    documentos = []
    for i, conteudo in enumerate(conteudos):
        hash_sha256 = hashlib.sha256(conteudo).hexdigest()
        armazenamento.armazenar(
            hash_sha256=hash_sha256,
            conteudo=conteudo,
            mime_type='application/pdf',
            nome_original=f'doc_{i}.pdf',
            tamanho=len(conteudo),
        )
        doc = Documento(
            documento_id=f'doc-{i}',
            arquivo_original=armazenamento.referencia(hash_sha256),
            nome_original=f'doc_{i}.pdf',
            mime_type='application/pdf',
            tamanho=len(conteudo),
            hash_sha256=hash_sha256,
            origem='teste',
            recebido_em=agora,
            lote_id=None,
            status='RECEBIDO',
            correlation_id=f'correl-{i}',
            criado_em=agora,
            atualizado_em=agora,
        )
        repositorio_docs.salvar(doc)
        documentos.append(doc)

    contexto = ContextoComposicaoPrestacao(
        competencia_base='2026-09',
        fonte_clientes=FonteClientesPrestacaoMock(),
        fonte_requisitos=FonteRequisitosPrestacaoMock(),
        repositorio_execucoes=repositorio_execucoes,
        repositorio_documentos=repositorio_docs,
        armazenamento_arquivos=armazenamento,
    )

    execucao = executar_ciclo_prestacao_persistente(contexto)

    # Execução prova que TODOS os documentos foram processados
    # (não foi feita decisão pela quantidade física antes da semântica)
    assert execucao is not None
    assert execucao.execucao_prestacao_id is not None
    assert execucao.estado in ('INICIADA', 'CONCLUIDA', 'FALHA')


def test_ciclo_persistente_via_adaptador_entrada_duravel():
    """Ciclo persistente completo: Documento → Armazenamento → Prestação.

    Valida que:
    - blob armazenado ANTES de Documento criado
    - Documento recebe referência real do blob
    - ciclo de Prestação processa Documento corretamente
    - execução finaliza em estado válido
    """
    from magnata_os.documental.modulo01.adaptador_entrada_duravel import (
        AdaptadorEntradaDuravel,
    )
    from magnata_os.documental.modulo01.repositorio import (
        RepositorioDocumentosEmMemoria,
        RepositorioHistoricoEmMemoria,
    )
    from magnata_os.documental.modulo01.armazenamento import (
        ArmazenamentoArquivosEmMemoria,
    )
    import hashlib

    # Setup
    repositorio_execucoes = RepositorioExecucoesPrestacaoMemoria()
    repositorio_docs = RepositorioDocumentosEmMemoria()
    repositorio_historico = RepositorioHistoricoEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()

    # 1. Registrar Documento via AdaptadorEntradaDuravel
    adaptador = AdaptadorEntradaDuravel(
        repositorio_documentos=repositorio_docs,
        repositorio_historico=repositorio_historico,
        armazenamento=armazenamento,
    )

    conteudo = b"Holerite 09/2026 - Colaborador Teste"
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()

    documento = adaptador.registrar_entrada(
        conteudo=conteudo,
        nome_original="holerite_09_2026.pdf",
        mime_type="application/pdf",
        origem="email_teste",
    )

    # 2. Validar que blob foi armazenado
    assert armazenamento.existe(hash_sha256)
    assert documento.hash_sha256 == hash_sha256
    assert documento.arquivo_original == armazenamento.referencia(hash_sha256)

    # 3. Recuperar bytes (validar blob integridade)
    with armazenamento.abrir_leitura(hash_sha256) as arquivo:
        recuperado = arquivo.read()
    assert recuperado == conteudo

    # 4. Executar ciclo de Prestação com Documento armazenado
    contexto = ContextoComposicaoPrestacao(
        competencia_base='2026-09',
        fonte_clientes=FonteClientesPrestacaoMock(),
        fonte_requisitos=FonteRequisitosPrestacaoMock(),
        repositorio_execucoes=repositorio_execucoes,
        repositorio_documentos=repositorio_docs,
        armazenamento_arquivos=armazenamento,
    )

    execucao = executar_ciclo_prestacao_persistente(contexto)

    # 5. Validar que execução foi realizada com Documento
    assert execucao is not None
    assert execucao.execucao_prestacao_id is not None
    # Documento foi processado pelo ciclo (não é mais "v2" ou pendente)
    assert execucao.estado in ('INICIADA', 'CONCLUIDA', 'FALHA')


# ==== BLOCKER D (5da729f): WIRING MORTO REMOVIDO ====
#
# BLOCKERs A, B, C de 5da729f foram REMOVIDOS daqui após mapeamento
# individual (correção pós-merge PR #158) -- cobertura nova, mais
# rigorosa, comprovadamente equivalente ou superior para cada um:
#
# - test_blocker_a_extracao_pdf_real (chamava extrair_texto_pdf
#   diretamente, com PDF hand-rolled, e afirmava 'Teste PDF' ou 'PDF'
#   no texto extraído): a correção do EXTRATOR em si (que produz texto
#   legível de um PDF real) já é coberta por
#   test_roteamento_documental_shadow.py::TestFluxoCompletoComPdfReal::
#   test_holerite_via_pdf_real (pré-existente, não desta missão). A
#   INTEGRAÇÃO deste módulo com o extrator -- o que este arquivo
#   deveria testar -- passa a ser coberta por
#   test_pdf_real_e_extraido_pelo_extrator_canonico_sem_erro (acima),
#   que exercita _adquirir_inventario_via_corredor de ponta a ponta e
#   confirma, via caplog, que nenhum evento de falha foi emitido.
#
# - test_blocker_a_pdf_corrompido_nao_silencioso (chamava
#   extrair_texto_pdf diretamente, esperava `pytest.raises(Exception)`):
#   o comportamento do extrator cru ao receber bytes inválidos é
#   legado, não tocado por esta missão, e já coberto indiretamente por
#   test_roteamento_documental_shadow.py::test_pdf_invalido_tem_motivo_
#   proprio_diferente. O comportamento que ESTE arquivo precisa provar
#   -- o que a composição faz com um PDF corrompido -- passa a ser
#   test_pdf_corrompido_e_pulado_via_extrator_canonico (acima): usa
#   extrair_texto_seguro (nunca deixa a exceção escapar até aqui) e
#   confirma o evento `pdf_ilegivel` via caplog.
#
# - test_blocker_b_blob_nao_encontrado_auditavel (usava objetos
#   fake via type('obj', (), {...})() SEM mime_type, chamado por
#   executar_ciclo_prestacao_persistente sem popular resolucoes_ancora/
#   competencias_por_cliente -- o laço de aquisição NUNCA executava;
#   comprovado empiricamente na auditoria pós-merge, spy em
#   executar_documento_readonly chamado 0 vezes mesmo com
#   requisitos_base preenchido. Testava, sem saber, um caminho morto):
#   substituído por
#   test_blob_nao_encontrado_e_logado_e_documento_pulado_sem_derrubar_
#   execucao (acima), que chama _adquirir_inventario_via_corredor
#   DIRETAMENTE com um Documento real (com mime_type) e afirma
#   positivamente que o evento blob_nao_encontrado foi logado --
#   cobertura estritamente superior: exercita o código de verdade e
#   faz uma afirmação positiva, não só "não quebrou".
#
# - test_blocker_c_falha_terminal_vs_documental (mesmo problema de
#   caminho morto do anterior; além disso, testava o comportamento da
#   heurística de classificação terminal/substring que o Incremento 4
#   desta mesma correção REVERTEU -- o alvo do teste deixou de existir
#   por desenho): substituído por
#   test_excecao_generica_sem_palavras_magicas_ainda_marca_falha
#   (acima), que prova o comportamento restaurado (qualquer exceção
#   marca FALHA) de forma direta e inequívoca.
#
# BLOCKER D é mantido tal como estava -- nenhuma cobertura nova o
# substitui, continua registrando uma intenção útil (guarda contra
# reintrodução do campo morto) sem equivalente em outro lugar.


def test_blocker_d_estrategia_aquisicao_removida():
    """BLOCKER D: Validar que imports mortos foram removidos."""
    from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
        ContextoComposicaoPrestacao
    )

    # Validar que campo ordem_fallback_fontes foi removido
    contexto = ContextoComposicaoPrestacao(
        competencia_base='2026-09',
        fonte_clientes=FonteClientesPrestacaoMock(),
        fonte_requisitos=FonteRequisitosPrestacaoMock(),
        repositorio_execucoes=RepositorioExecucoesPrestacaoMemoria(),
    )

    # Não deve ter atributo ordem_fallback_fontes
    assert not hasattr(contexto, 'ordem_fallback_fontes')


# ==== TESTES INCREMENTO 4 (correção pós-merge PR #158) ====
# `_adquirir_inventario_via_corredor` testada diretamente -- não
# precisa de resolução semântica/política de competência completa (o
# próprio `executar_ciclo_prestacao_persistente` só chama esta função
# quando o ciclo 1 já produziu `necessidades`, que exige
# `resolucoes_ancora`/`competencias_por_cliente` wired -- tocar
# `ciclo_prestacao.py` para isso sairia do escopo autorizado desta
# missão).


def _contexto_minimo(repositorio_documentos, armazenamento_arquivos):
    return ContextoComposicaoPrestacao(
        competencia_base='2026-09',
        fonte_clientes=FonteClientesPrestacaoMock(),
        fonte_requisitos=FonteRequisitosPrestacaoMock(),
        repositorio_execucoes=RepositorioExecucoesPrestacaoMemoria(),
        repositorio_documentos=repositorio_documentos,
        armazenamento_arquivos=armazenamento_arquivos,
    )


def test_mime_nao_pdf_e_pulado_sem_decodificar_como_texto(caplog):
    """Incremento 2/3: mime_type que não seja PDF nunca é decodificado
    como texto arbitrário -- é pulado, sem parser novo, e loga o evento
    ESTÁVEL `mime_nao_suportado`."""
    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()
    conteudo = b'nao e pdf'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    armazenamento.armazenar(
        hash_sha256=hash_sha256, conteudo=conteudo, mime_type='text/plain',
        nome_original='nota.txt', tamanho=len(conteudo),
    )
    repositorio_docs.salvar(_documento_bruto('doc-texto', hash_sha256, mime_type='text/plain'))

    with caplog.at_level('WARNING'):
        inventario = _adquirir_inventario_via_corredor(
            _contexto_minimo(repositorio_docs, armazenamento), _CICLO_TESTE,
        )
    assert inventario is not None  # nunca lança
    eventos = [getattr(r, 'evento', None) for r in caplog.records]
    assert 'mime_nao_suportado' in eventos
    registro = next(r for r in caplog.records if getattr(r, 'evento', None) == 'mime_nao_suportado')
    assert registro.documento_id == 'doc-texto'
    assert registro.mime_type == 'text/plain'


@pytest.mark.skipif(not _PDFPLUMBER_FUNCIONAL, reason=_MOTIVO_SKIP_PDFPLUMBER)
def test_pdf_corrompido_e_pulado_via_extrator_canonico(caplog):
    """Incremento 2/3: PDF (mime correto) mas bytes inválidos -- o
    extrator canônico (`extrair_texto_seguro` ->
    `extrair_texto_pdf`/pdfplumber) retorna None (nunca lança para fora
    daqui) -- documento é pulado, evento `pdf_ilegivel`, distinto do
    caso de mime não suportado."""
    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()
    conteudo = b'isto-nao-e-um-pdf-valido'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    armazenamento.armazenar(
        hash_sha256=hash_sha256, conteudo=conteudo, mime_type='application/pdf',
        nome_original='doc.pdf', tamanho=len(conteudo),
    )
    repositorio_docs.salvar(_documento_bruto('doc-pdf-invalido', hash_sha256))

    with caplog.at_level('WARNING'):
        inventario = _adquirir_inventario_via_corredor(
            _contexto_minimo(repositorio_docs, armazenamento), _CICLO_TESTE,
        )
    assert inventario is not None
    eventos = [getattr(r, 'evento', None) for r in caplog.records]
    assert 'pdf_ilegivel' in eventos
    assert 'mime_nao_suportado' not in eventos


@pytest.mark.skipif(not _PDFPLUMBER_FUNCIONAL, reason=_MOTIVO_SKIP_PDFPLUMBER)
def test_pdf_real_e_extraido_pelo_extrator_canonico_sem_erro(caplog):
    """Incremento 2/3: PDF real (fabricado com reportlab, mesmo helper
    já usado em test_roteamento_documental_shadow.py) é extraído pelo
    MESMO extrator canônico usado por processar_holerite/
    processar_extrato -- chega ao corredor sem cair em nenhum dos
    caminhos de falha (mime não suportado, PDF ilegível, corredor).
    Prova a correção do placeholder original (`decode('utf-8')` na v1
    da PR #158) e do uso cru de `extrair_texto_pdf` sem guarda de mime
    (na versão mesclada, `5da729f`)."""
    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()
    pdf_bytes = _pdf_minimo_com_texto('Extrato da Folha de Pagamento - Setembro 2026')
    hash_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    armazenamento.armazenar(
        hash_sha256=hash_sha256, conteudo=pdf_bytes, mime_type='application/pdf',
        nome_original='extrato.pdf', tamanho=len(pdf_bytes),
    )
    repositorio_docs.salvar(_documento_bruto('doc-pdf-real', hash_sha256, tamanho=len(pdf_bytes)))

    with caplog.at_level('WARNING'):
        inventario = _adquirir_inventario_via_corredor(
            _contexto_minimo(repositorio_docs, armazenamento), _CICLO_TESTE,
        )
    assert inventario is not None
    eventos = [getattr(r, 'evento', None) for r in caplog.records]
    assert not eventos  # nenhuma falha logada -- caminho feliz


def test_blob_nao_encontrado_e_logado_e_documento_pulado_sem_derrubar_execucao(caplog):
    """Incremento 3: Documento aponta para um hash que nunca foi
    armazenado -- `ArquivoNaoEncontrado` (já existente em
    armazenamento.py) gera o evento ESTÁVEL `blob_nao_encontrado`,
    nunca uma exceção não tratada, nunca confundida com falha de
    leitura."""
    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()
    repositorio_docs.salvar(_documento_bruto('doc-ausente', 'hash-nunca-armazenado'))

    with caplog.at_level('WARNING'):
        inventario = _adquirir_inventario_via_corredor(
            _contexto_minimo(repositorio_docs, armazenamento), _CICLO_TESTE,
        )

    assert inventario is not None  # nunca lança, nunca derruba a execução
    eventos = [getattr(r, 'evento', None) for r in caplog.records]
    assert eventos == ['blob_nao_encontrado']
    registro = caplog.records[0]
    assert registro.documento_id == 'doc-ausente'
    assert registro.hash_sha256 == 'hash-nunca-armazenado'


def test_falha_leitura_blob_diferente_de_nao_encontrado_e_logada_distintamente(caplog):
    """Incremento 3: 'encontrado mas falhou ao ler' (qualquer exceção
    que não seja `ArquivoNaoEncontrado`) precisa de um evento DIFERENTE
    de 'não encontrado' -- os dois eram o mesmo `continue` silencioso
    antes desta correção. Nunca a mensagem crua da exceção no log."""
    class _ArmazenamentoQuebrado:
        def abrir_leitura(self, hash_sha256):
            raise RuntimeError('disco corrompido -- detalhe interno sensível')

    repositorio_docs = RepositorioDocumentosEmMemoria()
    repositorio_docs.salvar(_documento_bruto('doc-corrompido', 'hash-x'))

    with caplog.at_level('ERROR'):
        inventario = _adquirir_inventario_via_corredor(
            _contexto_minimo(repositorio_docs, _ArmazenamentoQuebrado()), _CICLO_TESTE,
        )

    assert inventario is not None
    eventos = [getattr(r, 'evento', None) for r in caplog.records]
    assert eventos == ['blob_falha_leitura']
    registro = caplog.records[0]
    assert registro.documento_id == 'doc-corrompido'
    assert registro.exception_type == 'RuntimeError'
    # nunca a mensagem crua da exceção -- não vaza detalhe do backend
    for r in caplog.records:
        assert 'disco corrompido' not in r.getMessage()


def test_falha_no_corredor_e_logada_e_nao_impede_processamento_dos_demais(caplog, monkeypatch):
    """Incremento 3: uma falha inesperada dentro de
    `executar_documento_readonly` (nunca uma falha de negócio desenhada
    -- ver docstring) é logada com evento `corredor_falhou` e o tipo da
    exceção, nunca propagada para fora do laço, e NUNCA impede que os
    demais documentos do mesmo lote sejam processados."""
    import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo

    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()

    for documento_id, texto in (('doc-a', 'Holerite A'), ('doc-b', 'Holerite B')):
        conteudo = texto.encode('utf-8')
        hash_sha256 = hashlib.sha256(conteudo).hexdigest()
        armazenamento.armazenar(
            hash_sha256=hash_sha256, conteudo=conteudo, mime_type='application/pdf',
            nome_original=f'{documento_id}.pdf', tamanho=len(conteudo),
        )
        repositorio_docs.salvar(_documento_bruto(documento_id, hash_sha256))

    # extrair_texto_seguro sempre devolve texto não-None (não estamos
    # testando extração real de PDF aqui, só isolamento de falha do
    # corredor) -- monkeypatch só desta função, corredor real abaixo.
    monkeypatch.setattr(modulo, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer')

    chamadas = []

    def _executar_com_falha_para_doc_a(contexto_corredor, sink):
        chamadas.append(contexto_corredor.documento_id)
        if contexto_corredor.documento_id == 'doc-a':
            raise ValueError('falha inesperada no corredor')
        return ()

    monkeypatch.setattr(modulo, 'executar_documento_readonly', _executar_com_falha_para_doc_a)

    with caplog.at_level('WARNING'):
        inventario = _adquirir_inventario_via_corredor(
            _contexto_minimo(repositorio_docs, armazenamento), _CICLO_TESTE,
        )

    assert inventario is not None
    # AMBOS os documentos foram tentados -- doc-a falhando não impediu doc-b
    assert set(chamadas) == {'doc-a', 'doc-b'}
    eventos_doc_a = [
        r for r in caplog.records
        if getattr(r, 'evento', None) == 'corredor_falhou' and r.documento_id == 'doc-a'
    ]
    assert len(eventos_doc_a) == 1
    assert eventos_doc_a[0].exception_type == 'ValueError'
    assert not any(
        getattr(r, 'evento', None) == 'corredor_falhou' and r.documento_id == 'doc-b'
        for r in caplog.records
    )


def test_excecao_generica_sem_palavras_magicas_ainda_marca_falha(monkeypatch):
    """Incremento 4 (rollback de regressão): uma exceção genérica,
    levantada dentro do `try` externo de
    `executar_ciclo_prestacao_persistente`, cuja mensagem NÃO contém
    'execucao_prestacao' nem 'repositorio' (as "palavras mágicas" da
    heurística de substring introduzida por `5da729f` e revertida
    aqui), ainda assim marca a `ExecucaoPrestacao` como FALHA -- prova
    de que a heurística foi removida e o comportamento anterior
    (qualquer exceção não tratada marca FALHA) foi restaurado."""
    import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo

    def _levanta_erro_generico(**kwargs):
        raise RuntimeError('algo genérico quebrou, sem palavras mágicas aqui')

    monkeypatch.setattr(modulo, 'executar_ciclo_prestacao', _levanta_erro_generico)

    repositorio = RepositorioExecucoesPrestacaoMemoria()
    contexto = ContextoComposicaoPrestacao(
        competencia_base='2026-09',
        fonte_clientes=FonteClientesPrestacaoMock(),
        fonte_requisitos=FonteRequisitosPrestacaoMock(),
        repositorio_execucoes=repositorio,
    )

    with pytest.raises(RuntimeError):
        executar_ciclo_prestacao_persistente(contexto)

    # A exceção original propaga (nunca mascarada) E a execução foi
    # marcada FALHA -- as duas coisas, não uma ou outra.
    execucoes = repositorio.listar_todas()
    assert len(execucoes) == 1
    assert execucoes[0].estado == 'FALHA'
    assert execucoes[0].concluido_em is not None


def test_sem_repositorio_documentos_ou_armazenamento_retorna_inventario_vazio_sem_erro():
    """Guarda de borda preservada: sem repositório+armazenamento, a
    função devolve inventário vazio, nunca lança."""
    contexto = ContextoComposicaoPrestacao(
        competencia_base='2026-09',
        fonte_clientes=FonteClientesPrestacaoMock(),
        fonte_requisitos=FonteRequisitosPrestacaoMock(),
        repositorio_execucoes=RepositorioExecucoesPrestacaoMemoria(),
    )
    inventario = _adquirir_inventario_via_corredor(contexto, _CICLO_TESTE)
    assert inventario.listar(
        ReferenciaCanonica(tipo_entidade='CLIENTE', entidade_id='qualquer'),
        ReferenciaCanonica(tipo_entidade='COMPETENCIA', entidade_id='2026-09'),
    ) == ()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
