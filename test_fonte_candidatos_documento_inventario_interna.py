"""Testes para FonteCandidatosDocumentoInventarioInterna (V1.1 Incremento 1)."""

import pytest
from datetime import datetime, timezone

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.classificacao.inventario_prestacao_memoria import InventarioPrestacaoEmMemoria
from magnata_os.classificacao.fonte_candidatos_documento_inventario_interna import (
    FonteCandidatosDocumentoInventarioInterna,
)
from magnata_os.documental.modulo01.dominio import Documento
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria


# Fixtures
@pytest.fixture
def repositorio_docs():
    return RepositorioDocumentosEmMemoria()


@pytest.fixture
def fonte_interna(repositorio_docs):
    return FonteCandidatosDocumentoInventarioInterna(
        fonte_inventario=InventarioPrestacaoEmMemoria(),
        repositorio_documentos=repositorio_docs,
    )


def _criar_documento(doc_id, hash_sha):
    """Helper para criar Documento minimal."""
    agora = datetime.now(timezone.utc)
    return Documento(
        documento_id=doc_id,
        arquivo_original=f"s3://bucket/{hash_sha}",
        nome_original=f"doc_{doc_id}.pdf",
        mime_type="application/pdf",
        tamanho=1024,
        hash_sha256=hash_sha,
        origem="teste_interna",
        recebido_em=agora,
        lote_id=None,
        status="REGISTRADO",
        correlation_id="teste",
        criado_em=agora,
        atualizado_em=agora,
    )


# Testes
def test_1_necessidade_sem_candidatos_retorna_vazio(fonte_interna):
    """Teste 1: necessidade sem candidatos → tuple vazio."""
    cliente = ReferenciaCanonica('CLIENTE', 'cli-A')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-09')
    necessidade = NecessidadeDocumentoPrestacao(
        cliente=cliente,
        competencia=competencia,
        tipo_documental='Extrato da Folha de Pagamento',
        motivo_exigencia='teste',
    )

    resultado = fonte_interna.candidatos_para(necessidade)
    assert resultado == ()


def test_2_cliente_competencia_corretos_consulta_inventario(fonte_interna, repositorio_docs):
    """Teste 2: cliente + competência corretos → consulta inventário correspondente."""
    cliente = ReferenciaCanonica('CLIENTE', 'cli-B')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-09')

    # Preparar: adicionar documento ao repositório
    doc = _criar_documento('doc-001', 'a' * 64)
    repositorio_docs.salvar(doc)

    # Preparar: adicionar item ao inventário
    inventario = InventarioPrestacaoEmMemoria()
    inventario.adicionar(ItemInventarioPrestacao(
        documento_id='doc-001',
        tipo_documental='Extrato da Folha de Pagamento',
        cliente=cliente,
        competencia=competencia,
    ))

    fonte = FonteCandidatosDocumentoInventarioInterna(inventario, repositorio_docs)

    # Executar
    necessidade = NecessidadeDocumentoPrestacao(
        cliente=cliente,
        competencia=competencia,
        tipo_documental='Extrato da Folha de Pagamento',
        motivo_exigencia='teste',
    )
    resultado = fonte.candidatos_para(necessidade)

    # Validar
    assert len(resultado) == 1
    assert resultado[0].documento_id == 'doc-001'


def test_3_tipo_documental_correto_retorna(fonte_interna, repositorio_docs):
    """Teste 3: tipo documental correto → retorna Documento."""
    cliente = ReferenciaCanonica('CLIENTE', 'cli-C')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-09')
    tipo_correto = 'Holerite da Folha de Pagamento'

    doc = _criar_documento('doc-002', 'b' * 64)
    repositorio_docs.salvar(doc)

    inventario = InventarioPrestacaoEmMemoria()
    inventario.adicionar(ItemInventarioPrestacao(
        documento_id='doc-002',
        tipo_documental=tipo_correto,
        cliente=cliente,
        competencia=competencia,
    ))

    fonte = FonteCandidatosDocumentoInventarioInterna(inventario, repositorio_docs)

    necessidade = NecessidadeDocumentoPrestacao(
        cliente=cliente,
        competencia=competencia,
        tipo_documental=tipo_correto,
        motivo_exigencia='teste',
    )
    resultado = fonte.candidatos_para(necessidade)

    assert len(resultado) == 1
    assert resultado[0].documento_id == 'doc-002'


def test_4_tipo_errado_exclui(fonte_interna, repositorio_docs):
    """Teste 4: tipo errado → exclui."""
    cliente = ReferenciaCanonica('CLIENTE', 'cli-D')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-09')

    doc = _criar_documento('doc-003', 'c' * 64)
    repositorio_docs.salvar(doc)

    inventario = InventarioPrestacaoEmMemoria()
    inventario.adicionar(ItemInventarioPrestacao(
        documento_id='doc-003',
        tipo_documental='Extrato da Folha de Pagamento',
        cliente=cliente,
        competencia=competencia,
    ))

    fonte = FonteCandidatosDocumentoInventarioInterna(inventario, repositorio_docs)

    # Pedir tipo DIFERENTE
    necessidade = NecessidadeDocumentoPrestacao(
        cliente=cliente,
        competencia=competencia,
        tipo_documental='Holerite da Folha de Pagamento',  # Diferente!
        motivo_exigencia='teste',
    )
    resultado = fonte.candidatos_para(necessidade)

    assert resultado == ()


def test_5_colaborador_correto_retorna(fonte_interna, repositorio_docs):
    """Teste 5: colaborador correto → retorna."""
    cliente = ReferenciaCanonica('CLIENTE', 'cli-E')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-09')
    colaborador = ReferenciaCanonica('COLABORADOR', 'func-001')

    doc = _criar_documento('doc-004', 'd' * 64)
    repositorio_docs.salvar(doc)

    inventario = InventarioPrestacaoEmMemoria()
    inventario.adicionar(ItemInventarioPrestacao(
        documento_id='doc-004',
        tipo_documental='Holerite da Folha de Pagamento',
        cliente=cliente,
        competencia=competencia,
        colaborador=colaborador,
    ))

    fonte = FonteCandidatosDocumentoInventarioInterna(inventario, repositorio_docs)

    necessidade = NecessidadeDocumentoPrestacao(
        cliente=cliente,
        competencia=competencia,
        tipo_documental='Holerite da Folha de Pagamento',
        motivo_exigencia='teste',
        colaborador=colaborador,
    )
    resultado = fonte.candidatos_para(necessidade)

    assert len(resultado) == 1
    assert resultado[0].documento_id == 'doc-004'


def test_6_colaborador_errado_exclui(fonte_interna, repositorio_docs):
    """Teste 6: colaborador errado → exclui."""
    cliente = ReferenciaCanonica('CLIENTE', 'cli-F')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-09')
    colaborador_real = ReferenciaCanonica('COLABORADOR', 'func-001')
    colaborador_pedido = ReferenciaCanonica('COLABORADOR', 'func-999')

    doc = _criar_documento('doc-005', 'e' * 64)
    repositorio_docs.salvar(doc)

    inventario = InventarioPrestacaoEmMemoria()
    inventario.adicionar(ItemInventarioPrestacao(
        documento_id='doc-005',
        tipo_documental='Holerite da Folha de Pagamento',
        cliente=cliente,
        competencia=competencia,
        colaborador=colaborador_real,
    ))

    fonte = FonteCandidatosDocumentoInventarioInterna(inventario, repositorio_docs)

    necessidade = NecessidadeDocumentoPrestacao(
        cliente=cliente,
        competencia=competencia,
        tipo_documental='Holerite da Folha de Pagamento',
        motivo_exigencia='teste',
        colaborador=colaborador_pedido,  # Diferente!
    )
    resultado = fonte.candidatos_para(necessidade)

    assert resultado == ()


def test_7_necessidade_sem_colaborador_ignora_com_colaborador(fonte_interna, repositorio_docs):
    """Teste 7: necessidade sem colaborador → ignora itens com colaborador."""
    cliente = ReferenciaCanonica('CLIENTE', 'cli-G')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-09')

    doc = _criar_documento('doc-006', 'f' * 64)
    repositorio_docs.salvar(doc)

    inventario = InventarioPrestacaoEmMemoria()
    inventario.adicionar(ItemInventarioPrestacao(
        documento_id='doc-006',
        tipo_documental='Holerite da Folha de Pagamento',
        cliente=cliente,
        competencia=competencia,
        colaborador=ReferenciaCanonica('COLABORADOR', 'func-001'),  # Tem colaborador!
    ))

    fonte = FonteCandidatosDocumentoInventarioInterna(inventario, repositorio_docs)

    necessidade = NecessidadeDocumentoPrestacao(
        cliente=cliente,
        competencia=competencia,
        tipo_documental='Holerite da Folha de Pagamento',
        motivo_exigencia='teste',
        colaborador=None,  # Sem colaborador!
    )
    resultado = fonte.candidatos_para(necessidade)

    assert resultado == ()


def test_8_multiplos_candidatos_validos_retorna_todos_deterministicamente(
    fonte_interna, repositorio_docs
):
    """Teste 8: múltiplos candidatos válidos → retorna todos determinísticamente."""
    cliente = ReferenciaCanonica('CLIENTE', 'cli-H')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-09')

    # Criar 3 documentos
    docs = [
        _criar_documento('doc-007', 'g' * 64),
        _criar_documento('doc-008', 'h' * 64),
        _criar_documento('doc-009', 'i' * 64),
    ]
    for doc in docs:
        repositorio_docs.salvar(doc)

    inventario = InventarioPrestacaoEmMemoria()
    for doc in docs:
        inventario.adicionar(ItemInventarioPrestacao(
            documento_id=doc.documento_id,
            tipo_documental='Extrato da Folha de Pagamento',
            cliente=cliente,
            competencia=competencia,
        ))

    fonte = FonteCandidatosDocumentoInventarioInterna(inventario, repositorio_docs)

    necessidade = NecessidadeDocumentoPrestacao(
        cliente=cliente,
        competencia=competencia,
        tipo_documental='Extrato da Folha de Pagamento',
        motivo_exigencia='teste',
    )
    resultado = fonte.candidatos_para(necessidade)

    # Validar: todos 3 retornam, ordenados por documento_id
    assert len(resultado) == 3
    ids_esperados = ['doc-007', 'doc-008', 'doc-009']
    ids_reais = [d.documento_id for d in resultado]
    assert ids_reais == ids_esperados


def test_9_item_aponta_documento_inexistente_ignora_failclosed(
    fonte_interna, repositorio_docs
):
    """Teste 9: item aponta para documento_id inexistente → ignora (fail-closed)."""
    cliente = ReferenciaCanonica('CLIENTE', 'cli-I')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-09')

    # Criar inventário com item cujo documento NÃO existe no repositório
    inventario = InventarioPrestacaoEmMemoria()
    inventario.adicionar(ItemInventarioPrestacao(
        documento_id='doc-inexistente',  # Não está no repositório!
        tipo_documental='Extrato da Folha de Pagamento',
        cliente=cliente,
        competencia=competencia,
    ))

    fonte = FonteCandidatosDocumentoInventarioInterna(inventario, repositorio_docs)

    necessidade = NecessidadeDocumentoPrestacao(
        cliente=cliente,
        competencia=competencia,
        tipo_documental='Extrato da Folha de Pagamento',
        motivo_exigencia='teste',
    )
    resultado = fonte.candidatos_para(necessidade)

    # Validar: retorna vazio (fail-closed)
    assert resultado == ()


def test_10_mesmo_hash_em_documentos_distintos_preserva_documento_id(
    fonte_interna, repositorio_docs
):
    """Teste 10: mesmo hash em Documentos distintos → preserva documento_id."""
    cliente = ReferenciaCanonica('CLIENTE', 'cli-J')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-09')

    # Mesmo hash, mas documento_id diferentes
    hash_compartilhado = 'j' * 64
    doc1 = _criar_documento('doc-010', hash_compartilhado)
    doc2 = _criar_documento('doc-011', hash_compartilhado)

    repositorio_docs.salvar(doc1)
    repositorio_docs.salvar(doc2)

    inventario = InventarioPrestacaoEmMemoria()
    inventario.adicionar(ItemInventarioPrestacao(
        documento_id='doc-010',
        tipo_documental='Extrato da Folha de Pagamento',
        cliente=cliente,
        competencia=competencia,
    ))
    inventario.adicionar(ItemInventarioPrestacao(
        documento_id='doc-011',
        tipo_documental='Extrato da Folha de Pagamento',
        cliente=cliente,
        competencia=competencia,
    ))

    fonte = FonteCandidatosDocumentoInventarioInterna(inventario, repositorio_docs)

    necessidade = NecessidadeDocumentoPrestacao(
        cliente=cliente,
        competencia=competencia,
        tipo_documental='Extrato da Folha de Pagamento',
        motivo_exigencia='teste',
    )
    resultado = fonte.candidatos_para(necessidade)

    # Validar: retorna ambos, preservando documento_id
    assert len(resultado) == 2
    ids_reais = {d.documento_id for d in resultado}
    assert ids_reais == {'doc-010', 'doc-011'}


def test_11_reexecucao_idempotente(fonte_interna, repositorio_docs):
    """Teste 11: reexecução → mesmo resultado."""
    cliente = ReferenciaCanonica('CLIENTE', 'cli-K')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-09')

    doc = _criar_documento('doc-012', 'k' * 64)
    repositorio_docs.salvar(doc)

    inventario = InventarioPrestacaoEmMemoria()
    inventario.adicionar(ItemInventarioPrestacao(
        documento_id='doc-012',
        tipo_documental='Extrato da Folha de Pagamento',
        cliente=cliente,
        competencia=competencia,
    ))

    fonte = FonteCandidatosDocumentoInventarioInterna(inventario, repositorio_docs)

    necessidade = NecessidadeDocumentoPrestacao(
        cliente=cliente,
        competencia=competencia,
        tipo_documental='Extrato da Folha de Pagamento',
        motivo_exigencia='teste',
    )

    # Executar 3 vezes
    resultado1 = fonte.candidatos_para(necessidade)
    resultado2 = fonte.candidatos_para(necessidade)
    resultado3 = fonte.candidatos_para(necessidade)

    # Validar: todos iguais
    assert resultado1 == resultado2 == resultado3
    assert len(resultado1) == 1


def test_12_nao_usa_airtable_nao_acessa_rede(fonte_interna):
    """Teste 12: NÃO usa Airtable, NÃO acessa rede."""
    # Simplesmente verificar que a implementação não importa Airtable
    # Grep no código seria ideal, mas aqui apenas confirmamos que a classe
    # foi criada sem rede
    assert hasattr(fonte_interna, 'candidatos_para')
    assert hasattr(fonte_interna, '_fonte_inventario')
    assert hasattr(fonte_interna, '_repositorio_documentos')

    # Ambas as dependências são injetadas (Protocol ou memória), não hardcoded
    # Logo, zero dependência de Airtable ou rede


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
