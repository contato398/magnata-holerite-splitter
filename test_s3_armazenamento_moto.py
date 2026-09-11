"""Compatibilidade de `ArmazenamentoArquivosS3` contra um cliente boto3
REAL (via `moto`, in-memory, sem rede, sem credencial real, sem Docker --
o ambiente desta sessão não tem daemon Docker disponível).

`test_magnata_os_documental_modulo01_fase2.py` já cobre toda a lógica de
negócio do adapter (idempotência, divergência, hash, streaming, etc.)
contra um duplo de teste escrito à mão (`_ClienteS3Falso`). Este arquivo
NUNCA duplica essa cobertura -- ele prova só o que aquele duplo não pode
provar: que o adapter também funciona, com a MESMA interface, contra um
cliente `boto3.client('s3', ...)` de verdade (moto intercepta a chamada
HTTP e simula o serviço S3 real).

`boto3`/`moto` são usados só aqui, na camada de teste de composição --
nunca dentro de `magnata_os/documental/modulo01/adapters/s3_armazenamento.py`
(que continua duck-typed, sem import de boto3) nem em qualquer módulo de
domínio.
"""
import boto3
import pytest
from moto import mock_aws

from magnata_os.documental.modulo01.adapters.s3_armazenamento import (
    ArmazenamentoArquivosS3,
)
from magnata_os.documental.modulo01.armazenamento import (
    ConteudoDivergente,
    HashInconsistente,
)

_BUCKET = 'magnata-teste-moto'
_REGIAO = 'us-east-1'


@pytest.fixture
def cliente_s3_real():
    with mock_aws():
        cliente = boto3.client('s3', region_name=_REGIAO)
        cliente.create_bucket(Bucket=_BUCKET)
        yield cliente


@pytest.fixture
def armazenamento(cliente_s3_real):
    return ArmazenamentoArquivosS3(cliente_s3_real, bucket=_BUCKET, prefixo='documentos/')


def _sha256_de(conteudo: bytes) -> str:
    import hashlib
    return hashlib.sha256(conteudo).hexdigest()


def test_armazenar_e_ler_de_volta_com_cliente_boto3_real(armazenamento):
    conteudo = b'holerite de teste -- conteudo fake, sem PII real'
    hash_sha256 = _sha256_de(conteudo)

    referencia = armazenamento.armazenar(
        hash_sha256, conteudo, 'application/pdf', 'holerite.pdf', len(conteudo),
    )

    assert referencia == f's3://{_BUCKET}/documentos/{hash_sha256}'
    assert armazenamento.existe(hash_sha256) is True
    lido = armazenamento.abrir_leitura(hash_sha256).read()
    assert lido == conteudo


def test_idempotente_nao_reenvia_para_mesmo_hash_e_conteudo_com_boto3_real(armazenamento):
    conteudo = b'conteudo idempotente'
    hash_sha256 = _sha256_de(conteudo)

    primeira = armazenamento.armazenar(hash_sha256, conteudo, 'text/plain', 'a.txt', len(conteudo))
    segunda = armazenamento.armazenar(hash_sha256, conteudo, 'text/plain', 'a.txt', len(conteudo))

    assert primeira == segunda
    assert armazenamento.abrir_leitura(hash_sha256).read() == conteudo


def test_conteudo_divergente_para_o_mesmo_hash_e_erro_nunca_sobrescreve_com_boto3_real(armazenamento):
    """Colisão simulada: já existe objeto na chave (que é o próprio hash),
    mas com conteúdo diferente do que o SHA-256 informado (e recém-
    conferido) autorizaria -- só possível fabricando a divergência
    diretamente no S3, já que a checagem de hash real nunca deixaria dois
    conteúdos diferentes chegarem à mesma chave em uso normal."""
    conteudo_original = b'conteudo original'
    hash_sha256 = _sha256_de(conteudo_original)
    armazenamento.armazenar(hash_sha256, conteudo_original, 'text/plain', 'a.txt', len(conteudo_original))

    conteudo_forjado_na_mesma_chave = b'objeto corrompido/adulterado por fora do adapter'
    armazenamento._cliente.put_object(
        Bucket=_BUCKET,
        Key=f'documentos/{hash_sha256}',
        Body=conteudo_forjado_na_mesma_chave,
    )

    with pytest.raises(ConteudoDivergente):
        armazenamento.armazenar(
            hash_sha256, conteudo_original, 'text/plain', 'a.txt', len(conteudo_original),
        )

    # o objeto forjado nunca é sobrescrito pelo adapter -- ele só relata
    # a divergência, nunca decide sozinho qual versão é a correta
    assert armazenamento.abrir_leitura(hash_sha256).read() == conteudo_forjado_na_mesma_chave


def test_hash_informado_nao_bate_com_o_real_e_rejeitado_antes_de_qualquer_upload(armazenamento, cliente_s3_real):
    conteudo = b'conteudo qualquer'
    hash_errado = '0' * 64

    with pytest.raises(HashInconsistente):
        armazenamento.armazenar(hash_errado, conteudo, 'text/plain', 'a.txt', len(conteudo))

    # nada foi enviado ao S3 -- a rejeição acontece antes do put_object
    objetos = cliente_s3_real.list_objects_v2(Bucket=_BUCKET)
    assert objetos.get('KeyCount', 0) == 0


def test_objeto_ausente_com_boto3_real(armazenamento):
    assert armazenamento.existe('f' * 64) is False


def test_chave_e_prefixo_mais_hash_com_boto3_real(cliente_s3_real):
    armazenamento_outro_prefixo = ArmazenamentoArquivosS3(
        cliente_s3_real, bucket=_BUCKET, prefixo='outro-prefixo/',
    )
    conteudo = b'conteudo'
    hash_sha256 = _sha256_de(conteudo)
    armazenamento_outro_prefixo.armazenar(hash_sha256, conteudo, 'text/plain', 'a.txt', len(conteudo))

    objetos = cliente_s3_real.list_objects_v2(Bucket=_BUCKET)
    chaves = [obj['Key'] for obj in objetos.get('Contents', [])]
    assert chaves == [f'outro-prefixo/{hash_sha256}']


def test_remover_e_so_compensacao_manual_com_boto3_real(armazenamento):
    conteudo = b'conteudo removivel'
    hash_sha256 = _sha256_de(conteudo)
    armazenamento.armazenar(hash_sha256, conteudo, 'text/plain', 'a.txt', len(conteudo))
    assert armazenamento.existe(hash_sha256) is True

    armazenamento.remover(hash_sha256)

    assert armazenamento.existe(hash_sha256) is False
