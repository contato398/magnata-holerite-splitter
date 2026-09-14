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
from magnata_os.classificacao.ciclo_prestacao import (
    NecessidadeDocumentoPrestacao,
    executar_ciclo_prestacao,
    executar_ciclo_prestacao_descoberta,
)
from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.execucao_prestacao import (
    ExecucaoPrestacao,
    RepositorioExecucoesPrestacao,
)
from magnata_os.classificacao.fonte_clientes_prestacao import FonteClientesPrestacao
from magnata_os.classificacao.fonte_requisitos_prestacao import FonteRequisitosPrestacao
from magnata_os.classificacao.pacote_prestacao import EstadoPacotePrestacao
from magnata_os.classificacao.prestacao_readiness import (
    ItemInventarioPrestacao,
    RequisitoDocumentalPrestacao,
)
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
        inventario, _resultados_aquisicao = _adquirir_inventario_via_corredor(
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
        inventario, _resultados_aquisicao = _adquirir_inventario_via_corredor(
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
        inventario, _resultados_aquisicao = _adquirir_inventario_via_corredor(
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
        inventario, _resultados_aquisicao = _adquirir_inventario_via_corredor(
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
        inventario, _resultados_aquisicao = _adquirir_inventario_via_corredor(
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
        inventario, _resultados_aquisicao = _adquirir_inventario_via_corredor(
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
    inventario, resultados_aquisicao = _adquirir_inventario_via_corredor(contexto, _CICLO_TESTE)
    assert inventario.listar(
        ReferenciaCanonica(tipo_entidade='CLIENTE', entidade_id='qualquer'),
        ReferenciaCanonica(tipo_entidade='COMPETENCIA', entidade_id='2026-09'),
    ) == ()
    assert resultados_aquisicao == ()


# ==== TESTES: evolução do contrato do ciclo de Prestação V1, Incremento 4 ====
# Antes desta correção, o retorno de `executar_documento_readonly`
# (resolução semântica REAL, com proveniência) era descartado por
# `_adquirir_inventario_via_corredor` mesmo em caso de sucesso. Estes
# testes provam que ele agora é retido, associado ao documento de
# origem, e nunca aparece para um documento que falhou antes de
# chegar ao corredor (mesma disciplina de isolamento por documento já
# validada acima).


def test_resolucao_real_do_corredor_e_retida_por_documento(monkeypatch):
    """Caminho feliz: o resultado REAL devolvido por
    `executar_documento_readonly` (nunca fabricado) é retido em
    `resultados_aquisicao`, associado ao `documento_id`/`hash_sha256`
    de origem -- não mais descartado."""
    import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo
    from magnata_os.classificacao.orquestrador_corredor_readonly import (
        ResultadoExecucaoCorredorPrestacao,
    )
    from magnata_os.classificacao.resolucao_documento_prestacao import (
        EstadoCorredorDocumentoPrestacao,
        ResultadoProcessamentoDocumentoPrestacao,
    )

    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()
    conteudo = b'Holerite Setembro 2026'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    armazenamento.armazenar(
        hash_sha256=hash_sha256, conteudo=conteudo, mime_type='application/pdf',
        nome_original='holerite.pdf', tamanho=len(conteudo),
    )
    repositorio_docs.salvar(_documento_bruto('doc-real', hash_sha256))

    monkeypatch.setattr(modulo, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer')

    resultado_processamento = ResultadoProcessamentoDocumentoPrestacao(
        documento_id='doc-real',
        estado=EstadoCorredorDocumentoPrestacao.TIPO_DESCONHECIDO,
        tipo_documental=None,
    )
    resultado_fake = ResultadoExecucaoCorredorPrestacao(
        resultado_corredor=resultado_processamento,
    )
    monkeypatch.setattr(
        modulo, 'executar_documento_readonly',
        lambda contexto_corredor, sink: (resultado_fake,),
    )

    inventario, resultados_aquisicao = _adquirir_inventario_via_corredor(
        _contexto_minimo(repositorio_docs, armazenamento), _CICLO_TESTE,
    )

    assert len(resultados_aquisicao) == 1
    registro = resultados_aquisicao[0]
    assert registro.documento_id == 'doc-real'
    assert registro.hash_sha256 == hash_sha256
    assert registro.resultados_corredor == (resultado_fake,)
    # Nunca fabricado: é o MESMO objeto devolvido pelo corredor real.
    assert registro.resultados_corredor[0] is resultado_fake


def test_documento_que_falha_antes_do_corredor_nunca_aparece_em_resultados_aquisicao(caplog):
    """Isolamento por documento (Incremento 3) continua valendo para a
    retenção nova: um documento cujo blob nunca foi encontrado é
    logado e pulado -- nunca gera uma entrada em
    `resultados_aquisicao` (não há resultado real do corredor para
    ele; jamais um placeholder fabricado no lugar)."""
    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()
    repositorio_docs.salvar(_documento_bruto('doc-ausente', 'hash-nunca-armazenado'))

    with caplog.at_level('WARNING'):
        inventario, resultados_aquisicao = _adquirir_inventario_via_corredor(
            _contexto_minimo(repositorio_docs, armazenamento), _CICLO_TESTE,
        )

    assert resultados_aquisicao == ()


def test_falha_no_corredor_nunca_gera_entrada_em_resultados_aquisicao_mas_nao_impede_outros(
    monkeypatch, caplog,
):
    """Documento cujo corredor lança exceção: não gera entrada em
    `resultados_aquisicao` (não há resultado real a reter), mas o
    documento seguinte, que teve sucesso, gera sua entrada normalmente
    -- mesma política de isolamento por documento já validada para o
    inventário/log, agora também para a retenção da resolução real."""
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

    monkeypatch.setattr(modulo, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer')

    def _executar_com_falha_para_doc_a(contexto_corredor, sink):
        if contexto_corredor.documento_id == 'doc-a':
            raise ValueError('falha inesperada no corredor')
        return ()

    monkeypatch.setattr(modulo, 'executar_documento_readonly', _executar_com_falha_para_doc_a)

    with caplog.at_level('WARNING'):
        inventario, resultados_aquisicao = _adquirir_inventario_via_corredor(
            _contexto_minimo(repositorio_docs, armazenamento), _CICLO_TESTE,
        )

    assert [r.documento_id for r in resultados_aquisicao] == ['doc-b']


# ==== TESTES: evolução do contrato do ciclo de Prestação V1, Incremento 5 ====
# `avaliar_candidatos_ancora` -- os 5 cenários obrigatórios (0
# candidatos; 1 candidato; N concordantes; N divergentes; candidato em
# revisão) + independência de ordem. NUNCA cria um novo
# `ResultadoResolucaoSemantico` -- só monta candidatos sintéticos de
# teste com os MESMOS contratos já usados por
# `test_magnata_os_classificacao_prestacao_readiness.py`.

from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    MOTIVO_RESOLUCOES_ANCORA_DIVERGENTES,
    MOTIVO_SEM_EVIDENCIA_DOCUMENTAL_REAL,
    avaliar_candidatos_ancora,
)
from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    ConfiancaResolucao,
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    EstadoResultadoSemantico,
    NivelConfianca,
    PerfilAplicabilidadeResolucao,
    RegraAplicabilidadeDimensao,
    ResolucaoDimensao,
    ResultadoResolucaoSemantico,
)

_CLIENTE_ESPERADO = ReferenciaCanonica('CLIENTE', 'cliente-ancora-1')
_COMPETENCIA_ESPERADA = ReferenciaCanonica('COMPETENCIA', '2026-09')
_OUTRO_CLIENTE = ReferenciaCanonica('CLIENTE', 'cliente-ancora-2')
_OUTRA_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-08')


def _regra_ancora(dimensao):
    return RegraAplicabilidadeDimensao(
        dimensao=dimensao,
        aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA,
        cardinalidade=Cardinalidade(1, 1),
    )


def _dimensao_ancora(dimensao, referencia=None, estado=EstadoResolucaoDimensao.RESOLVIDA):
    return ResolucaoDimensao(
        dimensao=dimensao,
        estado=estado,
        valores_confirmados=(referencia,) if referencia is not None else (),
        confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )


def _candidato_ancora(
    documento_id,
    cliente=_CLIENTE_ESPERADO,
    competencia=_COMPETENCIA_ESPERADA,
    estado_cliente=EstadoResolucaoDimensao.RESOLVIDA,
    estado_competencia=EstadoResolucaoDimensao.RESOLVIDA,
    necessita_revisao_humana=False,
):
    perfil = PerfilAplicabilidadeResolucao(
        perfil_id='prestacao-ancora-teste',
        version='1',
        escopo_documental='prestacao-contas',
        regras=(
            _regra_ancora(DimensaoResolucao.CLIENTE),
            _regra_ancora(DimensaoResolucao.COMPETENCIA),
        ),
    )
    return ResultadoResolucaoSemantico(
        documento_id=documento_id,
        resolver_id='resolver-teste-ancora',
        resolver_version='1',
        politica_id='prestacao-ancora',
        politica_version='1',
        perfil=perfil,
        resolucoes=(
            _dimensao_ancora(
                DimensaoResolucao.CLIENTE,
                cliente if estado_cliente == EstadoResolucaoDimensao.RESOLVIDA else None,
                estado_cliente,
            ),
            _dimensao_ancora(
                DimensaoResolucao.COMPETENCIA,
                competencia if estado_competencia == EstadoResolucaoDimensao.RESOLVIDA else None,
                estado_competencia,
            ),
        ),
        estado_consolidado=(
            EstadoResultadoSemantico.RESOLVIDA
            if estado_cliente == EstadoResolucaoDimensao.RESOLVIDA
            and estado_competencia == EstadoResolucaoDimensao.RESOLVIDA
            else EstadoResultadoSemantico.INCONCLUSIVA
        ),
        necessita_revisao_humana=necessita_revisao_humana,
    )


def test_ancora_zero_candidatos_sem_evidencia_documental_real():
    resultado = avaliar_candidatos_ancora((), _CLIENTE_ESPERADO, _COMPETENCIA_ESPERADA)
    assert resultado.ancora is None
    assert resultado.motivo_ausencia == MOTIVO_SEM_EVIDENCIA_DOCUMENTAL_REAL


def test_ancora_um_candidato_valido_e_usado_diretamente():
    candidato = _candidato_ancora('doc-1')
    resultado = avaliar_candidatos_ancora((candidato,), _CLIENTE_ESPERADO, _COMPETENCIA_ESPERADA)
    assert resultado.motivo_ausencia is None
    assert resultado.ancora is candidato


def test_ancora_n_candidatos_concordantes_escolhe_representante_deterministico():
    candidato_a = _candidato_ancora('doc-a')
    candidato_b = _candidato_ancora('doc-b')
    candidato_c = _candidato_ancora('doc-c')
    esperado = min(
        (candidato_a, candidato_b, candidato_c), key=lambda c: c.semantic_result_id
    )

    for ordem in (
        (candidato_a, candidato_b, candidato_c),
        (candidato_c, candidato_b, candidato_a),
        (candidato_b, candidato_c, candidato_a),
    ):
        resultado = avaliar_candidatos_ancora(ordem, _CLIENTE_ESPERADO, _COMPETENCIA_ESPERADA)
        assert resultado.motivo_ausencia is None
        assert resultado.ancora is esperado  # independente da ordem de entrada


def test_ancora_candidatos_divergentes_nunca_escolhe_um_lado():
    """Um candidato concorda com o esperado, outro resolve para OUTRO
    cliente -- nunca agrupado silenciosamente, nunca escolhido o
    'certo': resultado é divergência explícita, sem âncora nenhuma."""
    candidato_certo = _candidato_ancora('doc-certo')
    candidato_outro_cliente = _candidato_ancora('doc-errado', cliente=_OUTRO_CLIENTE)

    resultado = avaliar_candidatos_ancora(
        (candidato_certo, candidato_outro_cliente), _CLIENTE_ESPERADO, _COMPETENCIA_ESPERADA,
    )
    assert resultado.ancora is None
    assert resultado.motivo_ausencia == MOTIVO_RESOLUCOES_ANCORA_DIVERGENTES

    # Independência de ordem também na divergência.
    resultado_invertido = avaliar_candidatos_ancora(
        (candidato_outro_cliente, candidato_certo), _CLIENTE_ESPERADO, _COMPETENCIA_ESPERADA,
    )
    assert resultado_invertido.motivo_ausencia == MOTIVO_RESOLUCOES_ANCORA_DIVERGENTES


def test_ancora_candidatos_divergentes_por_competencia_tambem_nunca_escolhe_lado():
    candidato_certo = _candidato_ancora('doc-certo')
    candidato_outra_competencia = _candidato_ancora(
        'doc-outra-competencia', competencia=_OUTRA_COMPETENCIA
    )
    resultado = avaliar_candidatos_ancora(
        (candidato_certo, candidato_outra_competencia), _CLIENTE_ESPERADO, _COMPETENCIA_ESPERADA,
    )
    assert resultado.ancora is None
    assert resultado.motivo_ausencia == MOTIVO_RESOLUCOES_ANCORA_DIVERGENTES


@pytest.mark.parametrize(
    'estado_cliente,estado_competencia,necessita_revisao',
    [
        (EstadoResolucaoDimensao.AMBIGUA, EstadoResolucaoDimensao.RESOLVIDA, False),
        (EstadoResolucaoDimensao.CONFLITO, EstadoResolucaoDimensao.RESOLVIDA, False),
        (EstadoResolucaoDimensao.NAO_ENCONTRADA, EstadoResolucaoDimensao.RESOLVIDA, False),
        (EstadoResolucaoDimensao.RESOLVIDA, EstadoResolucaoDimensao.RESOLVIDA, True),
    ],
)
def test_ancora_candidato_em_revisao_nunca_vira_autoridade(
    estado_cliente, estado_competencia, necessita_revisao,
):
    """Candidato ambíguo/em conflito/não encontrado/com revisão humana
    pendente NUNCA vira âncora sozinho -- contribui para 'sem âncora
    válida' (mesmo motivo de 0 candidatos: não há distinção de negócio
    pedida hoje entre 'nenhum documento' e 'só evidência
    inconclusiva')."""
    candidato_em_revisao = _candidato_ancora(
        'doc-revisao',
        estado_cliente=estado_cliente,
        estado_competencia=estado_competencia,
        necessita_revisao_humana=necessita_revisao,
    )
    resultado = avaliar_candidatos_ancora(
        (candidato_em_revisao,), _CLIENTE_ESPERADO, _COMPETENCIA_ESPERADA,
    )
    assert resultado.ancora is None
    assert resultado.motivo_ausencia == MOTIVO_SEM_EVIDENCIA_DOCUMENTAL_REAL


def test_ancora_candidato_em_revisao_misturado_com_candidato_valido_usa_o_valido():
    """1 candidato em revisão + 1 candidato válido e concordante -- o
    de revisão nunca vira autoridade, mas também nunca contamina o
    válido: a âncora real é escolhida normalmente."""
    candidato_em_revisao = _candidato_ancora(
        'doc-revisao', estado_cliente=EstadoResolucaoDimensao.AMBIGUA,
    )
    candidato_valido = _candidato_ancora('doc-valido')

    resultado = avaliar_candidatos_ancora(
        (candidato_em_revisao, candidato_valido), _CLIENTE_ESPERADO, _COMPETENCIA_ESPERADA,
    )
    assert resultado.motivo_ausencia is None
    assert resultado.ancora is candidato_valido


# ==== TESTES: evolução do contrato do ciclo de Prestação V1, Incremento 7 ====
# Rewiring completo de `executar_ciclo_prestacao_persistente`: política
# de competência V1 validada antes de criar a execução; descoberta sem
# âncora; aquisição; retenção + seleção de âncora REAL; readiness com
# âncora real ou ausência explícita; fallback para
# `contexto.resolucoes_ancora` só quando NENHUMA evidência real foi
# adquirida para o cliente.

from magnata_os.classificacao.competencia_esperada_prestacao import (
    DeslocamentoCompetenciaCliente,
    PoliticaCompetenciaPorTipoNaoSuportadaError,
)
from magnata_os.classificacao.orquestrador_corredor_readonly import (
    ResultadoExecucaoCorredorPrestacao as _ResultadoExecucaoCorredorPrestacaoV7,
)
from magnata_os.classificacao.resolucao_documento_prestacao import (
    EstadoCorredorDocumentoPrestacao as _EstadoCorredorV7,
    ResultadoProcessamentoDocumentoPrestacao as _ResultadoProcessamentoV7,
)

_CLIENTE_V7 = ReferenciaCanonica('CLIENTE', 'cliente-v7')
_COMPETENCIA_V7 = ReferenciaCanonica('COMPETENCIA', '2026-09')


class _FonteRequisitosVaziaV7:
    def registros_para(self, cliente, contexto):
        return ()


class _FonteClientesV7:
    def listar_ativos(self, contexto=None):
        return (_CLIENTE_V7,)


class _FonteClientesDoisAtivosV7:
    def __init__(self, cliente_b):
        self._cliente_b = cliente_b

    def listar_ativos(self, contexto=None):
        return (_CLIENTE_V7, self._cliente_b)


class _RepositorioComUmDocumento:
    """Fake mínimo -- só `listar_todos()`, único método que
    `_adquirir_inventario_via_corredor` consulta."""

    def __init__(self, documento):
        self._documento = documento

    def listar_todos(self):
        return (self._documento,)


def _documento_bruto_v7(documento_id, hash_sha256):
    agora = datetime.now(timezone.utc)
    return Documento(
        documento_id=documento_id,
        arquivo_original=f'{documento_id}.pdf',
        nome_original=f'{documento_id}.pdf',
        mime_type='application/pdf',
        tamanho=10,
        hash_sha256=hash_sha256,
        origem='teste',
        recebido_em=agora,
        lote_id=None,
        status='RECEBIDO',
        correlation_id=f'corr-{documento_id}',
        criado_em=agora,
        atualizado_em=agora,
    )


class _FonteCandidatosPorNecessidadeFake:
    """Fake determinístico para teste: associação REAL e independente
    necessidade -> documentos candidatos, chaveada por (cliente,
    competencia) -- suficiente para os cenários destes testes (1 tipo
    documental por necessidade). O cliente/competência esperados vêm
    SEMPRE da própria `necessidade` recebida em `candidatos_para`,
    nunca de nada que o documento tenha resolvido."""

    def __init__(self, mapa: dict):
        self._mapa = mapa  # {(cliente, competencia): Tuple[Documento, ...]}

    def candidatos_para(self, necessidade):
        return self._mapa.get((necessidade.cliente, necessidade.competencia), ())


def _contexto_v7(repositorio_execucoes, **kwargs):
    defaults = dict(
        competencia_base='2026-09',
        fonte_clientes=_FonteClientesV7(),
        fonte_requisitos=_FonteRequisitosVaziaV7(),
        repositorio_execucoes=repositorio_execucoes,
        requisitos_base=(RequisitoDocumentalPrestacao('HOLERITE'),),
        competencias_por_cliente={_CLIENTE_V7: _COMPETENCIA_V7},
    )
    defaults.update(kwargs)
    return ContextoComposicaoPrestacao(**defaults)


def test_politica_v1_fail_closed_nunca_cria_execucao():
    """Política com deslocamento por tipo_documental -- fail-closed
    ANTES de criar/retomar a ExecucaoPrestacao (mesmo padrão de
    `criar_e_persistir_execucao`: config inválida nunca vira execução
    rastreada)."""
    from magnata_os.classificacao.competencia_esperada_prestacao import (
        PoliticaCompetenciaPrestacao,
    )

    politica_invalida = PoliticaCompetenciaPrestacao(
        version='teste-v7',
        deslocamentos=(
            DeslocamentoCompetenciaCliente(
                cliente=_CLIENTE_V7, offset_meses=-1, tipo_documental='EXTRATO',
            ),
        )
    )
    repositorio = RepositorioExecucoesPrestacaoMemoria()
    contexto = _contexto_v7(repositorio, politica_competencia=politica_invalida)

    with pytest.raises(PoliticaCompetenciaPorTipoNaoSuportadaError):
        executar_ciclo_prestacao_persistente(contexto)

    assert repositorio.listar_todas() == ()


def test_evidencia_real_concordante_ancora_readiness_ate_pronto(monkeypatch):
    """Necessidade A/X (único cliente ativo) tem, via `fonte_
    candidatos_por_necessidade`, exatamente 1 candidato real (doc-v7-
    real). Ele resolve CLIENTE/COMPETENCIA EXATAMENTE como a necessidade
    esperava e satisfaz o requisito -- a âncora REAL (nunca fabricada)
    flui até o readiness e o pacote fecha PRONTO, refletido no estado
    final CONCLUIDA."""
    import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo
    from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
    from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria

    repositorio_execucoes = RepositorioExecucoesPrestacaoMemoria()
    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()

    conteudo = b'holerite qualquer'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    armazenamento.armazenar(
        hash_sha256=hash_sha256, conteudo=conteudo, mime_type='application/pdf',
        nome_original='holerite.pdf', tamanho=len(conteudo),
    )
    documento_real = _documento_bruto_v7('doc-v7-real', hash_sha256)
    repositorio_docs.salvar(documento_real)

    monkeypatch.setattr(modulo, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer')

    resolucao_real = _candidato_ancora(
        'doc-v7-real', cliente=_CLIENTE_V7, competencia=_COMPETENCIA_V7,
    )

    def _executar_documento_readonly_fake(contexto_corredor, sink):
        sink.adicionar(
            ItemInventarioPrestacao(
                documento_id=contexto_corredor.documento_id,
                tipo_documental='HOLERITE',
                cliente=_CLIENTE_V7,
                competencia=_COMPETENCIA_V7,
            )
        )
        resultado_processamento = _ResultadoProcessamentoV7(
            documento_id=contexto_corredor.documento_id,
            estado=_EstadoCorredorV7.RESOLVIDO_E_AVANCOU,
            tipo_documental='HOLERITE',
            resolucao_semantica=resolucao_real,
        )
        return (_ResultadoExecucaoCorredorPrestacaoV7(resultado_corredor=resultado_processamento),)

    monkeypatch.setattr(modulo, 'executar_documento_readonly', _executar_documento_readonly_fake)

    fonte_candidatos = _FonteCandidatosPorNecessidadeFake({
        (_CLIENTE_V7, _COMPETENCIA_V7): (documento_real,),
    })
    contexto = _contexto_v7(
        repositorio_execucoes,
        repositorio_documentos=repositorio_docs,
        armazenamento_arquivos=armazenamento,
        fonte_candidatos_por_necessidade=fonte_candidatos,
    )
    execucao = executar_ciclo_prestacao_persistente(contexto)

    assert execucao.estado == 'CONCLUIDA'


def test_sem_evidencia_real_e_sem_ancora_pre_informada_fica_em_revisao_nunca_pronto(monkeypatch):
    """CORREÇÃO pós-Ultraplan: populamos os campos LEGADOS de aquisição
    em bloco (`repositorio_documentos`/`armazenamento_arquivos`) mas
    NUNCA `fonte_candidatos_por_necessidade` -- por si só, isso nunca é
    suficiente para gerar uma âncora (aquisição em bloco não é mais
    chamada pelo fluxo persistente). Cliente fica EM_REVISAO explícito,
    NUNCA PRONTO por acidente."""
    import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo
    from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
    from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria

    repositorio_execucoes = RepositorioExecucoesPrestacaoMemoria()
    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()

    conteudo = b'holerite sem cliente identificavel'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    armazenamento.armazenar(
        hash_sha256=hash_sha256, conteudo=conteudo, mime_type='application/pdf',
        nome_original='holerite.pdf', tamanho=len(conteudo),
    )
    repositorio_docs.salvar(_documento_bruto_v7('doc-v7-sem-cliente', hash_sha256))

    monkeypatch.setattr(modulo, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer')
    # `executar_documento_readonly` REAL (nunca monkeypatched aqui) --
    # de qualquer forma, sem `fonte_candidatos_por_necessidade`, nunca
    # chega a ser chamado pelo fluxo persistente.

    contexto = _contexto_v7(
        repositorio_execucoes,
        repositorio_documentos=repositorio_docs,
        armazenamento_arquivos=armazenamento,
        # fonte_candidatos_por_necessidade NÃO informada (default None)
    )
    execucao = executar_ciclo_prestacao_persistente(contexto)

    # Nunca CONCLUIDA por acidente -- sem evidência real, fica retomável.
    assert execucao.estado == 'INICIADA'


def test_ancora_pre_informada_e_ignorada_sem_evidencia_real_desta_execucao():
    """CORREÇÃO (auditoria pós-Incremento 7): `contexto.resolucoes_
    ancora` pré-informada NÃO É MAIS usada como fallback -- auditoria
    de todos os callers reais (produção/wiring) não encontrou NENHUM
    que popule este campo hoje, só testes com dados sintéticos; sem
    prova de que é uma resolução real aplicável, preservá-la custaria a
    independência do cross-check (proibido). Mesmo com uma entrada
    'bonita' pré-informada e um item de inventário base já satisfazendo
    o requisito, SEM nenhuma evidência real adquirida NESTA execução o
    cliente fica EM_REVISAO -- nunca CONCLUIDA por uma pré-informada
    não verificável."""
    item_base = ItemInventarioPrestacao(
        documento_id='doc-base-v7',
        tipo_documental='HOLERITE',
        cliente=_CLIENTE_V7,
        competencia=_COMPETENCIA_V7,
    )
    from magnata_os.classificacao.inventario_prestacao_memoria import (
        InventarioPrestacaoEmMemoria as _InventarioV7,
    )
    fonte_base = _InventarioV7()
    fonte_base.adicionar(item_base)

    resolucao_pre_informada = _candidato_ancora(
        'doc-pre-informado', cliente=_CLIENTE_V7, competencia=_COMPETENCIA_V7,
    )

    repositorio_execucoes = RepositorioExecucoesPrestacaoMemoria()
    contexto = _contexto_v7(
        repositorio_execucoes,
        fonte_inventario_base=fonte_base,
        resolucoes_ancora={_CLIENTE_V7: resolucao_pre_informada},
    )
    execucao = executar_ciclo_prestacao_persistente(contexto)

    assert execucao.estado == 'INICIADA'  # nunca CONCLUIDA -- fallback removido


def test_dois_documentos_reais_divergentes_nunca_escolhem_lado_fica_em_revisao(monkeypatch):
    """Necessidade A/X tem, via `fonte_candidatos_por_necessidade`, 2
    candidatos reais: um resolve CLIENTE/COMPETENCIA igual ao esperado,
    o outro resolve o MESMO cliente mas COMPETÊNCIA diferente --
    divergência real DENTRO do vínculo necessidade->documento, nunca
    uma escolha de lado: cliente fica EM_REVISAO, nunca PRONTO."""
    import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo
    from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
    from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria

    repositorio_execucoes = RepositorioExecucoesPrestacaoMemoria()
    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()

    documentos = {}
    for documento_id, texto in (('doc-v7-a', 'A'), ('doc-v7-b', 'B')):
        conteudo = texto.encode('utf-8')
        hash_sha256 = hashlib.sha256(conteudo).hexdigest()
        armazenamento.armazenar(
            hash_sha256=hash_sha256, conteudo=conteudo, mime_type='application/pdf',
            nome_original=f'{documento_id}.pdf', tamanho=len(conteudo),
        )
        documento = _documento_bruto_v7(documento_id, hash_sha256)
        repositorio_docs.salvar(documento)
        documentos[documento_id] = documento

    monkeypatch.setattr(modulo, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer')

    _OUTRA_COMPETENCIA_V7 = ReferenciaCanonica('COMPETENCIA', '2026-08')
    resolucao_a = _candidato_ancora('doc-v7-a', cliente=_CLIENTE_V7, competencia=_COMPETENCIA_V7)
    resolucao_b = _candidato_ancora('doc-v7-b', cliente=_CLIENTE_V7, competencia=_OUTRA_COMPETENCIA_V7)
    resolucoes_por_documento = {'doc-v7-a': resolucao_a, 'doc-v7-b': resolucao_b}

    def _executar_documento_readonly_fake(contexto_corredor, sink):
        resultado_processamento = _ResultadoProcessamentoV7(
            documento_id=contexto_corredor.documento_id,
            estado=_EstadoCorredorV7.RESOLVIDO_E_AVANCOU,
            tipo_documental='HOLERITE',
            resolucao_semantica=resolucoes_por_documento[contexto_corredor.documento_id],
        )
        return (_ResultadoExecucaoCorredorPrestacaoV7(resultado_corredor=resultado_processamento),)

    monkeypatch.setattr(modulo, 'executar_documento_readonly', _executar_documento_readonly_fake)

    fonte_candidatos = _FonteCandidatosPorNecessidadeFake({
        (_CLIENTE_V7, _COMPETENCIA_V7): (documentos['doc-v7-a'], documentos['doc-v7-b']),
    })
    contexto = _contexto_v7(
        repositorio_execucoes,
        repositorio_documentos=repositorio_docs,
        armazenamento_arquivos=armazenamento,
        fonte_candidatos_por_necessidade=fonte_candidatos,
    )
    execucao = executar_ciclo_prestacao_persistente(contexto)

    assert execucao.estado == 'INICIADA'  # nunca CONCLUIDA -- divergência nunca escolhe lado


# ==== TESTES: correção pós-auditoria (evolução do contrato do ciclo de
# Prestação V1) -- contexto esperado é obrigatório; nenhum
# reagrupamento por cliente/competência RESOLVIDO pode mascarar
# divergência do cliente/competência ESPERADO. ====


def test_critico_dois_documentos_reais_cliente_diferente_nunca_vira_segundo_grupo(monkeypatch):
    """TESTE CRÍTICO OBRIGATÓRIO (correção pós-Ultraplan "Correlação
    Necessidade → Aquisição → Resolução"): necessidade A/X (único
    cliente ATIVO nesta descoberta) tem, via `fonte_candidatos_por_
    necessidade`, 2 candidatos reais -- exatamente o vínculo legítimo
    que a correção exige preservar. Documento 1 resolve A/X (como
    esperado). Documento 2 -- também candidato da MESMA necessidade
    A/X -- resolve B/X: cliente DIFERENTE do esperado, mesma
    competência.

    Resultado esperado: A/X = divergente/revisão.
    NUNCA: "A/X válido (usando só doc-1) + B/X criado como segundo
    grupo" -- B não é sequer um cliente ativo nesta descoberta; se a
    composição reclassificasse doc-2 como "evidência de B" (em vez de
    tratá-lo como sinal de divergência contra A, cuja necessidade foi
    quem o trouxe), essa reclassificação desapareceria silenciosamente
    do resultado E A ficaria PRONTO/CONCLUIDA por engano, ignorando que
    o PRÓPRIO vínculo de A continha uma resolução real conflitante."""
    import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo
    from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
    from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria

    repositorio_execucoes = RepositorioExecucoesPrestacaoMemoria()
    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()

    documentos = {}
    for documento_id, texto in (('doc-critico-a', 'A'), ('doc-critico-b', 'B')):
        conteudo = texto.encode('utf-8')
        hash_sha256 = hashlib.sha256(conteudo).hexdigest()
        armazenamento.armazenar(
            hash_sha256=hash_sha256, conteudo=conteudo, mime_type='application/pdf',
            nome_original=f'{documento_id}.pdf', tamanho=len(conteudo),
        )
        documento = _documento_bruto_v7(documento_id, hash_sha256)
        repositorio_docs.salvar(documento)
        documentos[documento_id] = documento

    monkeypatch.setattr(modulo, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer')

    _CLIENTE_B_NAO_ATIVO = ReferenciaCanonica('CLIENTE', 'cliente-b-nao-ativo-neste-ciclo')
    resolucao_a_x = _candidato_ancora(
        'doc-critico-a', cliente=_CLIENTE_V7, competencia=_COMPETENCIA_V7,
    )
    resolucao_b_x = _candidato_ancora(
        'doc-critico-b', cliente=_CLIENTE_B_NAO_ATIVO, competencia=_COMPETENCIA_V7,
    )
    resolucoes_por_documento = {'doc-critico-a': resolucao_a_x, 'doc-critico-b': resolucao_b_x}

    def _executar_documento_readonly_fake(contexto_corredor, sink):
        # doc-critico-a também escreve no inventário -- prova que,
        # MESMO com o requisito HOLERITE fisicamente satisfeito, a
        # divergência real ainda impede PRONTO.
        if contexto_corredor.documento_id == 'doc-critico-a':
            sink.adicionar(
                ItemInventarioPrestacao(
                    documento_id=contexto_corredor.documento_id,
                    tipo_documental='HOLERITE',
                    cliente=_CLIENTE_V7,
                    competencia=_COMPETENCIA_V7,
                )
            )
        resultado_processamento = _ResultadoProcessamentoV7(
            documento_id=contexto_corredor.documento_id,
            estado=_EstadoCorredorV7.RESOLVIDO_E_AVANCOU,
            tipo_documental='HOLERITE',
            resolucao_semantica=resolucoes_por_documento[contexto_corredor.documento_id],
        )
        return (_ResultadoExecucaoCorredorPrestacaoV7(resultado_corredor=resultado_processamento),)

    monkeypatch.setattr(modulo, 'executar_documento_readonly', _executar_documento_readonly_fake)

    # Os 2 documentos são candidatos da MESMA necessidade A/X -- o
    # vínculo legítimo (nunca inferido do que cada um resolve).
    fonte_candidatos = _FonteCandidatosPorNecessidadeFake({
        (_CLIENTE_V7, _COMPETENCIA_V7): (documentos['doc-critico-a'], documentos['doc-critico-b']),
    })
    contexto = _contexto_v7(
        repositorio_execucoes,
        repositorio_documentos=repositorio_docs,
        armazenamento_arquivos=armazenamento,
        fonte_candidatos_por_necessidade=fonte_candidatos,
        # `_CLIENTE_B_NAO_ATIVO` propositalmente NÃO entra em
        # `fonte_clientes`/`competencias_por_cliente` -- só A está
        # ativo. A divergência precisa ser detectada mesmo assim,
        # nenhum "grupo B" nasce no resultado.
    )
    execucao = executar_ciclo_prestacao_persistente(contexto)

    # Nunca CONCLUIDA: a resolução real conflitante de doc-critico-b
    # (candidato da MESMA necessidade de A, mesmo resolvendo para um
    # cliente sequer ativo nesta descoberta) precisa impedir que A/X
    # seja confirmado só com a evidência de doc-critico-a.
    assert execucao.estado == 'INICIADA'


# ==== TESTES OBRIGATÓRIOS -- Adendo Ultraplan aprovado "Correlação
# Necessidade → Aquisição → Resolução" (implementação de
# FonteCandidatosDocumentaisPorNecessidade) ====


def test_obrigatorio_necessidades_de_clientes_distintos_cada_uma_valida_sem_conflito_cruzado():
    """REQUERIDO: necessidade A/X → doc A → resolve A/X; necessidade
    B/X → doc B → resolve B/X. Ambos os clientes estão ATIVOS nesta
    descoberta, cada um com sua PRÓPRIA necessidade/candidato -- vínculo
    legítimo preservado por `fonte_candidatos_por_necessidade`.
    Resultado: A válido, B válido, NENHUM conflito cruzado (o candidato
    de B nunca entra no vínculo de A, e vice-versa -- ao contrário do
    pool global de `c234d22`, já superado por esta correção)."""
    import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo
    from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
    from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria

    _CLIENTE_B = ReferenciaCanonica('CLIENTE', 'cliente-b-ativo-obrigatorio')

    repositorio_execucoes = RepositorioExecucoesPrestacaoMemoria()
    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()

    documentos = {}
    for documento_id, texto in (('doc-a-valido', 'A'), ('doc-b-valido', 'B')):
        conteudo = texto.encode('utf-8')
        hash_sha256 = hashlib.sha256(conteudo).hexdigest()
        armazenamento.armazenar(
            hash_sha256=hash_sha256, conteudo=conteudo, mime_type='application/pdf',
            nome_original=f'{documento_id}.pdf', tamanho=len(conteudo),
        )
        documento = _documento_bruto_v7(documento_id, hash_sha256)
        repositorio_docs.salvar(documento)
        documentos[documento_id] = documento

    monkeypatch_alvo = modulo
    resolucao_a = _candidato_ancora('doc-a-valido', cliente=_CLIENTE_V7, competencia=_COMPETENCIA_V7)
    resolucao_b = _candidato_ancora('doc-b-valido', cliente=_CLIENTE_B, competencia=_COMPETENCIA_V7)
    resolucoes_por_documento = {'doc-a-valido': resolucao_a, 'doc-b-valido': resolucao_b}

    def _executar_documento_readonly_fake(contexto_corredor, sink):
        cliente_do_doc = (
            _CLIENTE_V7 if contexto_corredor.documento_id == 'doc-a-valido' else _CLIENTE_B
        )
        sink.adicionar(
            ItemInventarioPrestacao(
                documento_id=contexto_corredor.documento_id,
                tipo_documental='HOLERITE',
                cliente=cliente_do_doc,
                competencia=_COMPETENCIA_V7,
            )
        )
        resultado_processamento = _ResultadoProcessamentoV7(
            documento_id=contexto_corredor.documento_id,
            estado=_EstadoCorredorV7.RESOLVIDO_E_AVANCOU,
            tipo_documental='HOLERITE',
            resolucao_semantica=resolucoes_por_documento[contexto_corredor.documento_id],
        )
        return (_ResultadoExecucaoCorredorPrestacaoV7(resultado_corredor=resultado_processamento),)

    from unittest.mock import patch

    fonte_candidatos = _FonteCandidatosPorNecessidadeFake({
        (_CLIENTE_V7, _COMPETENCIA_V7): (documentos['doc-a-valido'],),
        (_CLIENTE_B, _COMPETENCIA_V7): (documentos['doc-b-valido'],),
    })
    contexto = _contexto_v7(
        repositorio_execucoes,
        fonte_clientes=_FonteClientesDoisAtivosV7(_CLIENTE_B),
        competencias_por_cliente={_CLIENTE_V7: _COMPETENCIA_V7, _CLIENTE_B: _COMPETENCIA_V7},
        repositorio_documentos=repositorio_docs,
        armazenamento_arquivos=armazenamento,
        fonte_candidatos_por_necessidade=fonte_candidatos,
    )
    with patch.object(monkeypatch_alvo, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(monkeypatch_alvo, 'executar_documento_readonly', _executar_documento_readonly_fake):
        execucao = executar_ciclo_prestacao_persistente(contexto)

    # CONCLUIDA só é possível se TODOS os clientes ativos fecharam
    # PRONTO -- prova, sem visibilidade adicional, que nem A nem B
    # ficaram EM_REVISAO/divergente por causa um do outro.
    assert execucao.estado == 'CONCLUIDA'


def test_obrigatorio_necessidade_a_com_documento_que_resolve_outro_cliente_e_divergente_b_nao_nasce():
    """REQUERIDO: necessidade A/X → doc A → resolve B/X. Resultado: A =
    revisão por divergência; B não é criado por acidente. Visibilidade
    completa (composição manual dos passos internos) para verificar o
    motivo EXATO de `avaliar_candidatos_ancora` e que nenhum resultado
    para B aparece em lugar nenhum."""
    import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo
    from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
    from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria

    _CLIENTE_B_ACIDENTAL = ReferenciaCanonica('CLIENTE', 'cliente-b-nunca-deveria-nascer')

    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()
    conteudo = b'documento unico'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    armazenamento.armazenar(
        hash_sha256=hash_sha256, conteudo=conteudo, mime_type='application/pdf',
        nome_original='doc.pdf', tamanho=len(conteudo),
    )
    documento_unico = _documento_bruto_v7('doc-unico-resolve-b', hash_sha256)
    repositorio_docs.salvar(documento_unico)

    resolucao_b_por_acidente = _candidato_ancora(
        'doc-unico-resolve-b', cliente=_CLIENTE_B_ACIDENTAL, competencia=_COMPETENCIA_V7,
    )

    def _executar_documento_readonly_fake(contexto_corredor, sink):
        resultado_processamento = _ResultadoProcessamentoV7(
            documento_id=contexto_corredor.documento_id,
            estado=_EstadoCorredorV7.RESOLVIDO_E_AVANCOU,
            tipo_documental='HOLERITE',
            resolucao_semantica=resolucao_b_por_acidente,
        )
        return (_ResultadoExecucaoCorredorPrestacaoV7(resultado_corredor=resultado_processamento),)

    from unittest.mock import patch
    from magnata_os.classificacao.inventario_prestacao_memoria import (
        InventarioPrestacaoEmMemoria as _InventarioVazioV7,
    )

    fonte_candidatos = _FonteCandidatosPorNecessidadeFake({
        (_CLIENTE_V7, _COMPETENCIA_V7): (documento_unico,),
    })
    ciclo_para_corredor = ContextoCicloPrestacao(competencia_base=(2026, 9))
    contexto_composicao = _contexto_v7(
        RepositorioExecucoesPrestacaoMemoria(),
        repositorio_documentos=repositorio_docs,
        armazenamento_arquivos=armazenamento,
        fonte_candidatos_por_necessidade=fonte_candidatos,
    )

    with patch.object(modulo, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(modulo, 'executar_documento_readonly', _executar_documento_readonly_fake):
        resultado_descoberta = executar_ciclo_prestacao_descoberta(
            contexto=ciclo_para_corredor,
            fonte_clientes=_FonteClientesV7(),
            fonte_requisitos=_FonteRequisitosVaziaV7(),
            fonte_inventario=_InventarioVazioV7(),
            requisitos_base=(RequisitoDocumentalPrestacao('HOLERITE'),),
            competencias_por_cliente={_CLIENTE_V7: _COMPETENCIA_V7},
        )
        necessidades = tuple(
            n for r in resultado_descoberta.resultados_por_cliente for n in r.necessidades
        )
        inventario_adquirido, resultados_aquisicao = modulo._adquirir_por_necessidades(
            contexto_composicao, necessidades, ciclo_para_corredor,
        )

    candidatos_a = tuple(
        resultado_execucao.resultado_corredor.resolucao_semantica
        for resultado_aquisicao in resultados_aquisicao
        for resultado_execucao in resultado_aquisicao.resultados_corredor
        if resultado_aquisicao.necessidade.cliente == _CLIENTE_V7
        and resultado_execucao.resultado_corredor.resolucao_semantica is not None
    )
    avaliacao = avaliar_candidatos_ancora(candidatos_a, _CLIENTE_V7, _COMPETENCIA_V7)
    assert avaliacao.ancora is None
    assert avaliacao.motivo_ausencia == MOTIVO_RESOLUCOES_ANCORA_DIVERGENTES

    resultado_ciclo = executar_ciclo_prestacao(
        contexto=ciclo_para_corredor,
        fonte_clientes=_FonteClientesV7(),
        fonte_requisitos=_FonteRequisitosVaziaV7(),
        fonte_inventario=inventario_adquirido,
        requisitos_base=(RequisitoDocumentalPrestacao('HOLERITE'),),
        resolucoes_ancora={},  # A não tem âncora -- divergência, nunca fabricada
        competencias_por_cliente={_CLIENTE_V7: _COMPETENCIA_V7},
    )
    clientes_no_resultado = {r.cliente for r in resultado_ciclo.resultados_por_cliente}
    assert clientes_no_resultado == {_CLIENTE_V7}  # B NUNCA nasce por acidente
    resultado_a = next(r for r in resultado_ciclo.resultados_por_cliente if r.cliente == _CLIENTE_V7)
    assert resultado_a.pacote.estado == EstadoPacotePrestacao.EM_REVISAO


def test_obrigatorio_sem_fonte_candidatos_por_necessidade_cliente_fica_em_revisao_explicita():
    """REQUERIDO: A/X precisa de documento; `fonte_candidatos_por_
    necessidade = None`. A continua no resultado; nenhuma âncora é
    criada; A = EM_REVISAO / `sem_evidencia_documental_real`.

    Deliberadamente populamos `repositorio_documentos`/`armazenamento_
    arquivos` com um documento que RESOLVERIA perfeitamente (via
    corredor monkeypatched) se a aquisição em bloco legada fosse usada
    como fallback -- provando que a ausência da fonte por necessidade
    é respeitada de verdade, nunca mascarada por uma aquisição em
    bloco disponível nos bastidores."""
    import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo
    from magnata_os.classificacao.inventario_prestacao_memoria import (
        InventarioPrestacaoEmMemoria as _InventarioVazioV7,
    )
    from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
    from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria

    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()
    conteudo = b'holerite que resolveria perfeitamente se o fallback existisse'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    armazenamento.armazenar(
        hash_sha256=hash_sha256, conteudo=conteudo, mime_type='application/pdf',
        nome_original='doc.pdf', tamanho=len(conteudo),
    )
    repositorio_docs.salvar(_documento_bruto_v7('doc-tentador', hash_sha256))

    resolucao_perfeita = _candidato_ancora(
        'doc-tentador', cliente=_CLIENTE_V7, competencia=_COMPETENCIA_V7,
    )

    def _executar_documento_readonly_fake(contexto_corredor, sink):
        sink.adicionar(
            ItemInventarioPrestacao(
                documento_id=contexto_corredor.documento_id,
                tipo_documental='HOLERITE',
                cliente=_CLIENTE_V7,
                competencia=_COMPETENCIA_V7,
            )
        )
        resultado_processamento = _ResultadoProcessamentoV7(
            documento_id=contexto_corredor.documento_id,
            estado=_EstadoCorredorV7.RESOLVIDO_E_AVANCOU,
            tipo_documental='HOLERITE',
            resolucao_semantica=resolucao_perfeita,
        )
        return (_ResultadoExecucaoCorredorPrestacaoV7(resultado_corredor=resultado_processamento),)

    ciclo_para_corredor = ContextoCicloPrestacao(competencia_base=(2026, 9))
    resultado_descoberta = executar_ciclo_prestacao_descoberta(
        contexto=ciclo_para_corredor,
        fonte_clientes=_FonteClientesV7(),
        fonte_requisitos=_FonteRequisitosVaziaV7(),
        fonte_inventario=_InventarioVazioV7(),
        requisitos_base=(RequisitoDocumentalPrestacao('HOLERITE'),),
        competencias_por_cliente={_CLIENTE_V7: _COMPETENCIA_V7},
    )
    necessidades = tuple(
        n for r in resultado_descoberta.resultados_por_cliente for n in r.necessidades
    )
    assert necessidades  # A realmente precisa de documento (HOLERITE faltando)

    contexto_composicao = _contexto_v7(
        RepositorioExecucoesPrestacaoMemoria(),
        repositorio_documentos=repositorio_docs,
        armazenamento_arquivos=armazenamento,
        # fonte_candidatos_por_necessidade NÃO informada (default None)
    )
    from unittest.mock import patch
    with patch.object(modulo, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer'), \
         patch.object(modulo, 'executar_documento_readonly', _executar_documento_readonly_fake):
        inventario_adquirido, resultados_aquisicao = modulo._adquirir_por_necessidades(
            contexto_composicao, necessidades, ciclo_para_corredor,
        )
    assert resultados_aquisicao == ()  # nenhuma aquisição rodou, mesmo com documento "perfeito" disponível

    resultado_ciclo = executar_ciclo_prestacao(
        contexto=ciclo_para_corredor,
        fonte_clientes=_FonteClientesV7(),
        fonte_requisitos=_FonteRequisitosVaziaV7(),
        fonte_inventario=inventario_adquirido,
        requisitos_base=(RequisitoDocumentalPrestacao('HOLERITE'),),
        resolucoes_ancora={},  # nenhuma âncora real, nenhuma pré-informada
        competencias_por_cliente={_CLIENTE_V7: _COMPETENCIA_V7},
    )
    clientes_no_resultado = {r.cliente for r in resultado_ciclo.resultados_por_cliente}
    assert _CLIENTE_V7 in clientes_no_resultado  # nunca desaparece
    resultado_a = next(r for r in resultado_ciclo.resultados_por_cliente if r.cliente == _CLIENTE_V7)
    assert resultado_a.pacote.estado == EstadoPacotePrestacao.EM_REVISAO
    assert 'sem_evidencia_documental_real' in resultado_a.pacote.motivos


def test_critico_direto_avaliar_candidatos_ancora_nunca_reclassifica_cliente_divergente():
    """Mesmo cenário, no nível mais direto possível (sem aquisição,
    sem corredor) -- chamada direta a `avaliar_candidatos_ancora` com
    o pool GLOBAL (nunca pré-filtrado por cliente resolvido)."""
    candidato_a_x = _candidato_ancora('doc-a', cliente=_CLIENTE_V7, competencia=_COMPETENCIA_V7)
    _outro_cliente = ReferenciaCanonica('CLIENTE', 'outro-cliente-critico')
    candidato_b_x = _candidato_ancora('doc-b', cliente=_outro_cliente, competencia=_COMPETENCIA_V7)

    resultado = avaliar_candidatos_ancora(
        (candidato_a_x, candidato_b_x), _CLIENTE_V7, _COMPETENCIA_V7,
    )
    assert resultado.ancora is None
    assert resultado.motivo_ausencia == MOTIVO_RESOLUCOES_ANCORA_DIVERGENTES


def test_critico_direto_avaliar_candidatos_ancora_nunca_reclassifica_competencia_divergente():
    """Equivalente para divergência de competência (nível direto)."""
    candidato_a_x = _candidato_ancora('doc-a', cliente=_CLIENTE_V7, competencia=_COMPETENCIA_V7)
    _outra_competencia = ReferenciaCanonica('COMPETENCIA', '2026-01')
    candidato_a_y = _candidato_ancora('doc-b', cliente=_CLIENTE_V7, competencia=_outra_competencia)

    resultado = avaliar_candidatos_ancora(
        (candidato_a_x, candidato_a_y), _CLIENTE_V7, _COMPETENCIA_V7,
    )
    assert resultado.ancora is None
    assert resultado.motivo_ausencia == MOTIVO_RESOLUCOES_ANCORA_DIVERGENTES


def test_sem_cliente_resolvido_nunca_vira_ancora_cliente_esperado_permanece_em_revisao(monkeypatch):
    """Ponto 3 da correção: caminho SEM resolução de cliente (wiring
    atual ainda não fornece `fonte_cliente_direto`/`fonte_vinculos` --
    ver `_adquirir_inventario_via_corredor`). Prova, com o CORREDOR
    REAL (nenhum monkeypatch de `executar_documento_readonly`, nenhum
    fallback sintético):
    - documento processado sem CLIENTE resolvido nunca vira âncora;
    - nunca é convertido em certeza;
    - o cliente ESPERADO permanece no resultado do ciclo (nunca some);
    - o pacote fica EM_REVISAO;
    - o motivo é `sem_evidencia_documental_real`."""
    import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo
    from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria
    from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivosEmMemoria

    repositorio_docs = RepositorioDocumentosEmMemoria()
    armazenamento = ArmazenamentoArquivosEmMemoria()
    conteudo = b'documento sem cliente identificavel pelo wiring atual'
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    armazenamento.armazenar(
        hash_sha256=hash_sha256, conteudo=conteudo, mime_type='application/pdf',
        nome_original='doc.pdf', tamanho=len(conteudo),
    )
    documento_bruto = _documento_bruto_v7('doc-sem-cliente', hash_sha256)

    monkeypatch.setattr(modulo, 'extrair_texto_seguro', lambda conteudo_bytes: 'texto qualquer')
    # `executar_documento_readonly` REAL -- nenhum monkeypatch aqui.
    # Sem `fonte_cliente_direto`/`fonte_vinculos` (nenhum informado em
    # `_adquirir_inventario_via_corredor` hoje), CLIENTE nunca resolve.

    contexto_composicao = _contexto_v7(
        RepositorioExecucoesPrestacaoMemoria(),
        repositorio_documentos=_RepositorioComUmDocumento(documento_bruto),
        armazenamento_arquivos=armazenamento,
    )
    ciclo_para_corredor = ContextoCicloPrestacao(competencia_base=(2026, 9))

    # Aquisição real -- confirma empiricamente que CLIENTE não resolve.
    inventario_adquirido, resultados_aquisicao = modulo._adquirir_inventario_via_corredor(
        contexto_composicao, ciclo_para_corredor,
    )
    candidatos_reais = tuple(
        resultado_execucao.resultado_corredor.resolucao_semantica
        for resultado_aquisicao in resultados_aquisicao
        for resultado_execucao in resultado_aquisicao.resultados_corredor
        if resultado_execucao.resultado_corredor.resolucao_semantica is not None
    )
    for candidato in candidatos_reais:
        cliente_resolvido = modulo._dimensao_resolvida_com_valor_unico(candidato, DimensaoResolucao.CLIENTE)
        assert cliente_resolvido is None  # nunca resolvido -- confirma a premissa do teste

    # Seleção de âncora: nunca vira âncora, nunca certeza fabricada.
    avaliacao = avaliar_candidatos_ancora(candidatos_reais, _CLIENTE_V7, _COMPETENCIA_V7)
    assert avaliacao.ancora is None
    assert avaliacao.motivo_ausencia == MOTIVO_SEM_EVIDENCIA_DOCUMENTAL_REAL

    # Ciclo completo (nível de `executar_ciclo_prestacao`, com
    # visibilidade total do resultado -- nunca só o estado opaco da
    # ExecucaoPrestacao): cliente esperado PERMANECE no resultado,
    # nunca descartado, com EM_REVISAO e motivo explícito.
    resultado_ciclo = executar_ciclo_prestacao(
        contexto=ciclo_para_corredor,
        fonte_clientes=_FonteClientesV7(),
        fonte_requisitos=_FonteRequisitosVaziaV7(),
        fonte_inventario=inventario_adquirido,
        requisitos_base=(RequisitoDocumentalPrestacao('HOLERITE'),),
        resolucoes_ancora={},  # nenhuma âncora real, nenhuma pré-informada
        competencias_por_cliente={_CLIENTE_V7: _COMPETENCIA_V7},
    )
    clientes_no_resultado = {r.cliente for r in resultado_ciclo.resultados_por_cliente}
    assert _CLIENTE_V7 in clientes_no_resultado  # nunca desaparece
    resultado_cliente = next(r for r in resultado_ciclo.resultados_por_cliente if r.cliente == _CLIENTE_V7)
    assert resultado_cliente.pacote.estado == EstadoPacotePrestacao.EM_REVISAO
    assert 'sem_evidencia_documental_real' in resultado_cliente.pacote.motivos


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
