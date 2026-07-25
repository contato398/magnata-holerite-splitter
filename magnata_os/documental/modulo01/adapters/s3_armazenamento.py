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

import hashlib
from typing import BinaryIO
from urllib.parse import quote

from ..armazenamento import ConteudoDivergente, HashInconsistente


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
    mesmo hash nunca reenvia -- confirma que e o mesmo conteudo
    comparando o ETag (MD5 do objeto, para upload de parte unica, que e
    sempre o caso aqui) contra o MD5 recalculado do conteudo agora
    enviado, nao so o tamanho. `hash_sha256` informado e sempre
    conferido contra o SHA-256 real do conteudo desta chamada -- nunca
    aceito por confianca no chamador."""

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
        hash_real = hashlib.sha256(conteudo).hexdigest()
        if hash_real != (hash_sha256 or '').strip().lower():
            raise HashInconsistente(
                f'hash_sha256 informado ({hash_sha256!r}) nao corresponde ao SHA-256 '
                f'real do conteudo ({hash_real}).'
            )

        chave = self._chave(hash_sha256)
        try:
            metadados_atuais = self._cliente.head_object(Bucket=self._bucket, Key=chave)
        except Exception as exc:
            if not _e_nao_encontrado(exc):
                raise
            metadados_atuais = None

        if metadados_atuais is not None:
            etag_atual = (metadados_atuais.get('ETag') or '').strip('"')
            md5_conteudo = hashlib.md5(conteudo).hexdigest()
            tamanho_atual = metadados_atuais.get('ContentLength')

            diverge = False
            if etag_atual:
                # ETag de upload de parte unica (sempre o caso aqui, ver
                # put_object abaixo) e o MD5 hex do objeto -- comparacao
                # de conteudo real, nao so de tamanho.
                diverge = etag_atual != md5_conteudo
            elif tamanho_atual is not None:
                # Fallback defensivo se o cliente nao expuser ETag --
                # mais fraco (so tamanho), documentado como limitacao.
                diverge = tamanho_atual != tamanho

            if diverge:
                raise ConteudoDivergente(
                    f'Ja existe objeto em s3://{self._bucket}/{chave} que nao corresponde '
                    f'ao conteudo agora enviado -- objeto ja armazenado pode estar '
                    f'corrompido/adulterado (hash_sha256={hash_sha256}).'
                )
            return self.referencia(hash_sha256)

        self._cliente.put_object(
            Bucket=self._bucket,
            Key=chave,
            Body=conteudo,
            ContentType=mime_type,
            Metadata={
                'hash-sha256': hash_sha256,
                # Metadados S3 sao enviados como headers HTTP -- precisam
                # ser ASCII-safe. nome_original pode conter acentos e
                # caracteres especiais (comum neste projeto); percent-
                # encoded (RFC 3986) antes de ir para o Metadata. Quem
                # for exibir o nome de volta precisa aplicar
                # urllib.parse.unquote() no valor lido.
                'nome-original': quote(nome_original, safe=''),
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
