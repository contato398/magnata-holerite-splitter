"""
Porta de armazenamento de arquivos do Modulo 01 (Documental), Fase 2.

Define o contrato que qualquer adapter de armazenamento fisico precisa
cumprir (S3, disco, etc.) e uma implementacao em memoria para testes
rapidos. Nao importa nenhuma biblioteca de armazenamento especifica --
ver adapters/s3_armazenamento.py para o adapter real.
"""
from __future__ import annotations

import hashlib
import io
import threading
from typing import BinaryIO, Protocol


class ConteudoDivergente(Exception):
    """Ja existe um objeto armazenado para este hash que nao corresponde
    ao conteudo agora enviado -- nunca sobrescreve em silencio. Indica
    corrupcao/adulteracao do objeto ja armazenado (o que foi gravado nao
    bate mais com o proprio hash que o nomeia), ja que
    HashInconsistente cobre o caso de o CHAMADOR informar um hash que
    nao corresponde ao conteudo desta chamada."""


class HashInconsistente(Exception):
    """O hash_sha256 informado nao corresponde ao SHA-256 real do
    conteudo desta chamada -- nunca aceito, mesmo que o tamanho bata.
    Verificado localmente (recalculando o hash), sem confiar no valor
    que o chamador afirma."""


class ArquivoNaoEncontrado(Exception):
    """Nenhum objeto armazenado para o hash consultado."""


class ArmazenamentoArquivos(Protocol):
    """Contrato que qualquer adapter de armazenamento fisico precisa
    cumprir. `armazenar` e idempotente por hash: chamar de novo com o
    mesmo hash e o mesmo conteudo nunca reenvia nem duplica."""

    def armazenar(
        self, hash_sha256: str, conteudo: bytes, mime_type: str,
        nome_original: str, tamanho: int,
    ) -> str:
        """Armazena o conteudo (se ainda nao existir para esse hash) e
        retorna a referencia permanente."""
        ...

    def existe(self, hash_sha256: str) -> bool: ...

    def abrir_leitura(self, hash_sha256: str) -> BinaryIO:
        """Retorna um objeto tipo arquivo para leitura por streaming --
        nunca carrega o conteudo inteiro em memoria de proposito."""
        ...

    def remover(self, hash_sha256: str) -> None:
        """SOMENTE para compensacao tecnica deliberada -- nunca parte do
        fluxo normal de entrada (ver MAGNATA_OS_DOCUMENTAL_MODULO01_FASE2.md,
        secao 'Sequencia transacional')."""
        ...

    def referencia(self, hash_sha256: str) -> str:
        """Gera/retorna a referencia permanente para um hash, sem
        necessariamente ler ou confirmar o conteudo."""
        ...


class ArmazenamentoArquivosEmMemoria:
    """Implementacao em memoria, para testes e para esta fase de
    fundacao. Nao persiste entre execucoes, nao acessa nada externo.
    Protegida por threading.Lock, para uso seguro em testes de
    concorrencia."""

    def __init__(self, prefixo: str = 'memoria://') -> None:
        self._prefixo = prefixo
        self._objetos: dict = {}
        self._metadados: dict = {}
        self._lock = threading.Lock()

    def referencia(self, hash_sha256: str) -> str:
        return f'{self._prefixo}{hash_sha256}'

    def existe(self, hash_sha256: str) -> bool:
        with self._lock:
            return hash_sha256 in self._objetos

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

        with self._lock:
            existente = self._objetos.get(hash_sha256)
            if existente is not None:
                if len(existente) != tamanho or existente != conteudo:
                    raise ConteudoDivergente(
                        f'Ja existe objeto armazenado para hash={hash_sha256} que nao '
                        f'corresponde ao conteudo agora enviado (mesmo tamanho ou nao) -- '
                        f'objeto ja armazenado pode estar corrompido/adulterado.'
                    )
                return self.referencia(hash_sha256)

            self._objetos[hash_sha256] = bytes(conteudo)
            self._metadados[hash_sha256] = {
                'mime_type': mime_type, 'nome_original': nome_original, 'tamanho': tamanho,
            }
            return self.referencia(hash_sha256)

    def abrir_leitura(self, hash_sha256: str) -> BinaryIO:
        with self._lock:
            conteudo = self._objetos.get(hash_sha256)
        if conteudo is None:
            raise ArquivoNaoEncontrado(f'Nenhum objeto armazenado para hash={hash_sha256}')
        return io.BytesIO(conteudo)

    def remover(self, hash_sha256: str) -> None:
        with self._lock:
            self._objetos.pop(hash_sha256, None)
            self._metadados.pop(hash_sha256, None)
