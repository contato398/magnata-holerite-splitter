"""
Adapter de armazenamento compativel com S3 (Modulo 01, Fase 2).

Escrito contra a interface minima que qualquer cliente S3-like ja expoe
(`put_object`, `get_object`, `head_object`, `delete_object` -- os
mesmos nomes de metodo do cliente S3 da `boto3`). Nunca importa `boto3`
diretamente. Quem instanciar este adapter em producao passa um
`boto3.client('s3', ...)` real (ou qualquer cliente compativel, ex.:
MinIO); testes passam um duplo de teste com a mesma interface. Ver
MAGNATA_OS_DOCUMENTAL_MODULO01_FASE2.md.
"""
from __future__ import annotations

from typing import BinaryIO

from ..armazenamento import ConteudoDivergente


def _e_nao_encontrado(exc: Exception) -> bool:
    """
    Deteccao duck-typed de 'objeto nao encontrado', sem importar
    botocore. O ClientError real da boto3 expoe `.response['Error']['Code']`
    -- confere isso de forma defensiva, sem exigir o tipo exato.
    """
    resposta = getattr(exc, 'response', None)
    if not isinstance(resposta, dict):
        return False
    codigo = resposta.get('Error', {}).get('Code', '')
    return codigo in ('404', 'NoSuchKey', 'NotFound')


class ArmazenamentoArquivosS3:
    """Adapter compativel com S3. A chave do objeto e
    `<prefixo><hash_sha256>` -- a propria chave e o hash, entao dois
    conteudos diferentes nunca colidem na mesma chave (a menos de
    colisao de SHA-256). Idempotente: um segundo armazenar() para o
    mesmo hash nunca reenvia, so confirma (por tamanho) que e o mesmo
    conteudo."""

    def __init__(self, cliente_s3, bucket: str, prefixo: str = 'documentos/') -> None:
        self._cliente = cliente_s3
        self._bucket = bucket
        self._prefixo = prefixo

    def _chave(self, hash_sha256: str) -> str:
        return f'{self._prefixo}{hash_sha256}'

    def referencia(self, hash_sha256: str) -> str:
        return f's3://{self._bucket}/{self._chave(hash_sha256)}'

    def existe(self, hash_sha256: str) -> bool:
        try:
            self._cliente.head_object(Bucket=self._bucket, Key=self._chave(hash_sha256))
            return True
        except Exception as exc:
            if _e_nao_encontrado(exc):
                return False
            raise

    def armazenar(
        self, hash_sha256: str, conteudo: bytes, mime_type: str,
        nome_original: str, tamanho: int,
    ) -> str:
        chave = self._chave(hash_sha256)
        try:
            metadados_atuais = self._cliente.head_object(Bucket=self._bucket, Key=chave)
        except Exception as exc:
            if not _e_nao_encontrado(exc):
                raise
            metadados_atuais = None

        if metadados_atuais is not None:
            tamanho_atual = metadados_atuais.get('ContentLength')
            if tamanho_atual is not None and tamanho_atual != tamanho:
                raise ConteudoDivergente(
                    f'Ja existe objeto em s3://{self._bucket}/{chave} com tamanho '
                    f'{tamanho_atual}, diferente do conteudo agora enviado ({tamanho}).'
                )
            return self.referencia(hash_sha256)

        self._cliente.put_object(
            Bucket=self._bucket,
            Key=chave,
            Body=conteudo,
            ContentType=mime_type,
            Metadata={
                'hash-sha256': hash_sha256,
                'nome-original': nome_original,
                'tamanho-original': str(tamanho),
            },
        )
        return self.referencia(hash_sha256)

    def abrir_leitura(self, hash_sha256: str) -> BinaryIO:
        resposta = self._cliente.get_object(Bucket=self._bucket, Key=self._chave(hash_sha256))
        return resposta['Body']

    def remover(self, hash_sha256: str) -> None:
        """SOMENTE para compensacao tecnica deliberada -- nunca chamado
        automaticamente pelo fluxo de entrada."""
        self._cliente.delete_object(Bucket=self._bucket, Key=self._chave(hash_sha256))
