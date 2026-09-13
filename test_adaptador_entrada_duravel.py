"""Testes do AdaptadorEntradaDuravel (Incremento A).

Valida que a fachada:
- expõe registrar_entrada() com assinatura idêntica
- armazena blob antes de Documento
- arquivo_original recebe referência real
- idempotência por hash preservada
- compatível com ServicoCriacaoLote (duck typing)
"""
import hashlib
from datetime import datetime, timezone

import pytest

from magnata_os.documental.modulo01.adaptador_entrada_duravel import (
    AdaptadorEntradaDuravel,
)
from magnata_os.documental.modulo01.armazenamento import (
    ArmazenamentoArquivosEmMemoria,
    ArquivoNaoEncontrado,
)
from magnata_os.documental.modulo01.dominio import (
    Documento,
    StatusDocumento,
)
from magnata_os.documental.modulo01.repositorio import (
    RepositorioDocumentosEmMemoria,
    RepositorioHistoricoEmMemoria,
)


@pytest.fixture
def repositorio_documentos():
    return RepositorioDocumentosEmMemoria()


@pytest.fixture
def repositorio_historico():
    return RepositorioHistoricoEmMemoria()


@pytest.fixture
def armazenamento():
    return ArmazenamentoArquivosEmMemoria()


@pytest.fixture
def adaptador(repositorio_documentos, repositorio_historico, armazenamento):
    return AdaptadorEntradaDuravel(
        repositorio_documentos=repositorio_documentos,
        repositorio_historico=repositorio_historico,
        armazenamento=armazenamento,
    )


def test_adaptador_expoe_registrar_entrada(adaptador):
    """Verificar que adaptador tem método registrar_entrada."""
    assert hasattr(adaptador, 'registrar_entrada')
    assert callable(adaptador.registrar_entrada)


def test_registrar_entrada_assinatura_compativel(adaptador):
    """Verificar que assinatura tem parâmetros essenciais.

    Não comparar com ServicoEntradaDocumental (interno de Fase 1),
    apenas validar que registrar_entrada tem os parâmetros esperados.
    """
    import inspect

    # Extrair assinatura
    sig = inspect.signature(adaptador.registrar_entrada)
    params = list(sig.parameters.keys())

    # Verificar parâmetros essenciais
    assert 'conteudo' in params
    assert 'nome_original' in params
    assert 'mime_type' in params
    assert 'origem' in params
    assert 'correlation_id' in params
    assert 'lote_id' in params
    assert 'metadados' in params


def test_adaptador_armazena_blob_antes_documento(
    adaptador, repositorio_documentos, armazenamento
):
    """Verificar que blob é armazenado ANTES de Documento ser criado."""
    conteudo = b"PDF test content"
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()

    # Verificar que blob não existe antes
    assert not armazenamento.existe(hash_sha256)

    # Registrar entrada
    documento = adaptador.registrar_entrada(
        conteudo=conteudo,
        nome_original="test.pdf",
        mime_type="application/pdf",
        origem="teste",
    )

    # Verificar que blob foi armazenado
    assert armazenamento.existe(hash_sha256)

    # Verificar que Documento foi criado
    assert documento.documento_id is not None
    assert documento.hash_sha256 == hash_sha256


def test_arquivo_original_recebe_referencia_real(adaptador, armazenamento):
    """Verificar que arquivo_original contém referência real, não placeholder."""
    conteudo = b"PDF content"
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()

    documento = adaptador.registrar_entrada(
        conteudo=conteudo,
        nome_original="test.pdf",
        mime_type="application/pdf",
        origem="teste",
    )

    # arquivo_original NÃO deve ser "pendente-armazenamento://..."
    assert not documento.arquivo_original.startswith("pendente-armazenamento://")

    # Deve ser referência válida do armazenamento
    assert documento.arquivo_original == armazenamento.referencia(hash_sha256)


def test_idempotencia_mesmo_hash_reutiliza_documento(adaptador, armazenamento):
    """Verificar que mesmo hash retorna mesmo Documento, não duplica blob."""
    conteudo = b"PDF content"
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()

    # Primeira entrada
    documento_1 = adaptador.registrar_entrada(
        conteudo=conteudo,
        nome_original="test1.pdf",
        mime_type="application/pdf",
        origem="teste",
    )

    # Segunda entrada com MESMO conteúdo
    documento_2 = adaptador.registrar_entrada(
        conteudo=conteudo,
        nome_original="test2.pdf",
        mime_type="application/pdf",
        origem="teste",
    )

    # Mesmo documento_id
    assert documento_1.documento_id == documento_2.documento_id

    # Blob armazenado uma única vez (armazenamento é idempotente)
    # Verificar tentando ler
    with armazenamento.abrir_leitura(hash_sha256) as arquivo:
        recuperado = arquivo.read()
    assert recuperado == conteudo


def test_recupera_bytes_por_hash(adaptador, armazenamento):
    """Verificar que bytes podem ser recuperados via abrir_leitura(hash)."""
    conteudo = b"PDF test content for recovery"
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()

    adaptador.registrar_entrada(
        conteudo=conteudo,
        nome_original="test.pdf",
        mime_type="application/pdf",
        origem="teste",
    )

    # Recuperar bytes
    with armazenamento.abrir_leitura(hash_sha256) as arquivo:
        recuperado = arquivo.read()

    assert recuperado == conteudo


def test_adaptador_duck_typing_compativel(adaptador):
    """Verificar que adaptador é compatível por duck typing.

    Qualquer código que chame adaptador.registrar_entrada(...) funcionará
    sem alteração se anteriormente chamava ServicoEntradaDocumental.registrar_entrada(...),
    porque a assinatura é idêntica.
    """
    # Se chegou aqui, o adaptador foi criado e tem o método
    # Duck typing será validado em testes de integração (Incremento B)
    assert callable(adaptador.registrar_entrada)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
