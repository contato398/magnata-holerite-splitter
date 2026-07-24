"""
Servico de entrada unica do Modulo 01 (Documental).

Ponto de entrada obrigatorio para qualquer documento novo: recebe
arquivo + origem + metadados opcionais, calcula hash, verifica
duplicidade e registra o Documento (RECEBIDO -> REGISTRADO) antes de
qualquer classificacao, OCR ou fatiamento -- que sao fases futuras, fora
de escopo aqui (ver MAGNATA_OS_DOCUMENTAL_MODULO01.md).

Principios aplicados (Manifesto):
  - Erros explicitos: falha nunca retorna nem registra sucesso.
  - Idempotencia: mesmo hash nunca cria um segundo Documento.
  - Auditoria: toda transicao de estado gera um EventoHistorico.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Callable, Optional

from .dominio import (
    Documento,
    EventoHistorico,
    StatusDocumento,
    gerar_correlation_id,
    gerar_documento_id,
    hash_valido,
    transicionar_status,
)
from .repositorio import RepositorioDocumentos, RepositorioHistorico


class ArquivoAusente(Exception):
    """Nenhum conteudo de arquivo foi fornecido para registrar entrada."""


class HashInvalido(Exception):
    """Uma string de hash SHA-256 mal formada foi usada numa consulta."""


class FalhaPersistencia(Exception):
    """Falha ao gravar Documento ou EventoHistorico. Nunca mascarada como
    sucesso -- quem chama precisa saber que a operacao nao completou."""


def _relogio_padrao() -> datetime:
    return datetime.now(timezone.utc)


class ServicoEntradaDocumental:
    """Orquestra o registro de um documento novo. Nao faz OCR,
    classificacao, fatiamento nem vinculo -- so recebe e registra."""

    def __init__(
        self,
        repositorio_documentos: RepositorioDocumentos,
        repositorio_historico: RepositorioHistorico,
        gerador_documento_id: Callable[[], str] = gerar_documento_id,
        relogio: Callable[[], datetime] = _relogio_padrao,
    ) -> None:
        self._documentos = repositorio_documentos
        self._historico = repositorio_historico
        self._gerar_documento_id = gerador_documento_id
        self._relogio = relogio

    def registrar_entrada(
        self,
        conteudo: bytes,
        nome_original: str,
        mime_type: str,
        origem: str,
        correlation_id: Optional[str] = None,
        lote_id: Optional[str] = None,
        metadados: Optional[dict] = None,
    ) -> Documento:
        """
        Registra a entrada de um documento novo. Idempotente por hash:
        se o conteudo (mesmo hash SHA-256) ja foi registrado antes,
        retorna o Documento existente e registra a tentativa no
        historico -- nunca cria um segundo Documento para o mesmo hash.
        """
        if not conteudo:
            raise ArquivoAusente(
                'Arquivo ausente ou vazio -- nao e possivel registrar entrada sem conteudo.'
            )

        correlation_id = correlation_id or gerar_correlation_id()
        hash_sha256 = hashlib.sha256(conteudo).hexdigest()
        agora = self._relogio()

        existente = self._documentos.buscar_por_hash(hash_sha256)
        if existente is not None:
            self._historico.registrar(EventoHistorico(
                documento_id=existente.documento_id,
                evento='TENTATIVA_DUPLICADA',
                status_anterior=existente.status,
                status_novo=existente.status,
                timestamp=agora,
                correlation_id=correlation_id,
                detalhes={
                    'hash_sha256': hash_sha256,
                    'nome_original_tentativa': nome_original,
                    'origem_tentativa': origem,
                    'metadados_tentativa': metadados or {},
                },
            ))
            return existente

        documento = Documento(
            documento_id=self._gerar_documento_id(),
            arquivo_original=f'pendente-armazenamento://{hash_sha256}',
            nome_original=nome_original,
            mime_type=mime_type,
            tamanho=len(conteudo),
            hash_sha256=hash_sha256,
            origem=origem,
            recebido_em=agora,
            lote_id=lote_id,
            status=StatusDocumento.RECEBIDO,
            correlation_id=correlation_id,
            criado_em=agora,
            atualizado_em=agora,
        )

        self._salvar_ou_falhar(documento, contexto='registrar RECEBIDO')
        self._historico.registrar(EventoHistorico(
            documento_id=documento.documento_id,
            evento='DOCUMENTO_RECEBIDO',
            status_anterior=None,
            status_novo=StatusDocumento.RECEBIDO,
            timestamp=agora,
            correlation_id=correlation_id,
            detalhes={
                'nome_original': nome_original,
                'origem': origem,
                'tamanho': documento.tamanho,
                'metadados': metadados or {},
            },
        ))

        documento_registrado = transicionar_status(documento, StatusDocumento.REGISTRADO, agora)
        self._salvar_ou_falhar(documento_registrado, contexto='transicionar para REGISTRADO')
        self._historico.registrar(EventoHistorico(
            documento_id=documento_registrado.documento_id,
            evento='DOCUMENTO_REGISTRADO',
            status_anterior=StatusDocumento.RECEBIDO,
            status_novo=StatusDocumento.REGISTRADO,
            timestamp=agora,
            correlation_id=correlation_id,
            detalhes={},
        ))

        return documento_registrado

    def consultar_por_hash(self, hash_sha256: str) -> Optional[Documento]:
        """Consulta um Documento pelo hash, sem registrar nada. Valida o
        formato do hash antes de consultar -- nunca aceita uma string
        que nao seja SHA-256 valido em silencio."""
        if not hash_valido(hash_sha256):
            raise HashInvalido(f'hash_sha256 invalido: {hash_sha256!r}')
        return self._documentos.buscar_por_hash(hash_sha256.strip().lower())

    def _salvar_ou_falhar(self, documento: Documento, contexto: str) -> None:
        try:
            self._documentos.salvar(documento)
        except Exception as exc:
            raise FalhaPersistencia(f'Falha ao {contexto} (documento_id={documento.documento_id}): {exc}') from exc
