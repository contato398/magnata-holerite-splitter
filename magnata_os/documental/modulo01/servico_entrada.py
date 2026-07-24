"""
Servico de entrada unica do Modulo 01 (Documental).

Ponto de entrada obrigatorio para qualquer documento novo: recebe
arquivo + origem + metadados opcionais, calcula hash, verifica
duplicidade e registra o Documento (RECEBIDO -> REGISTRADO) antes de
qualquer classificacao, OCR ou fatiamento -- que sao fases futuras, fora
de escopo aqui (ver MAGNATA_OS_DOCUMENTAL_MODULO01.md).

Principios aplicados (Manifesto):
  - Erros explicitos: falha nunca retorna nem registra sucesso.
  - Idempotencia: mesmo hash nunca cria um segundo Documento, mesmo sob
    chamadas concorrentes (atomicidade delegada ao repositorio, ver
    repositorio.RepositorioDocumentosEmMemoria.salvar_se_ausente_por_hash).
  - Auditoria: toda transicao de estado gera um EventoHistorico.
  - Consistencia: a criacao do Documento e seus 2 primeiros eventos
    (DOCUMENTO_RECEBIDO, DOCUMENTO_REGISTRADO) formam uma unica unidade
    logica -- se qualquer parte falhar depois da criacao, o Documento
    criado e removido (rollback explicito) antes de propagar o erro.
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
    gerar_referencia_arquivo_provisoria,
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
    sucesso -- quem chama precisa saber que a operacao nao completou. A
    causa original e sempre preservada via `raise ... from exc`."""


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
        gerador_referencia_arquivo: Callable[[str], str] = gerar_referencia_arquivo_provisoria,
        relogio: Callable[[], datetime] = _relogio_padrao,
    ) -> None:
        self._documentos = repositorio_documentos
        self._historico = repositorio_historico
        self._gerar_documento_id = gerador_documento_id
        self._gerar_referencia_arquivo = gerador_referencia_arquivo
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
        Registra a entrada de um documento novo. Idempotente por hash,
        inclusive sob concorrencia: a criacao (ou descoberta de que ja
        existe) e atomica no repositorio -- nunca cria um segundo
        Documento para o mesmo hash SHA-256, mesmo com chamadas
        simultaneas para o mesmo conteudo.
        """
        if not conteudo:
            raise ArquivoAusente(
                'Arquivo ausente ou vazio -- nao e possivel registrar entrada sem conteudo.'
            )

        correlation_id = correlation_id or gerar_correlation_id()
        hash_sha256 = hashlib.sha256(conteudo).hexdigest()
        agora = self._relogio()

        def _fabricar_documento_recebido() -> Documento:
            return Documento(
                documento_id=self._gerar_documento_id(),
                arquivo_original=self._gerar_referencia_arquivo(hash_sha256),
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

        try:
            documento, criado_agora = self._documentos.salvar_se_ausente_por_hash(
                hash_sha256, _fabricar_documento_recebido,
            )
        except Exception as exc:
            raise FalhaPersistencia(
                f'Falha ao registrar documento (hash_sha256={hash_sha256}): {exc}'
            ) from exc

        if not criado_agora:
            try:
                self._historico.registrar(EventoHistorico(
                    documento_id=documento.documento_id,
                    evento='TENTATIVA_DUPLICADA',
                    status_anterior=documento.status,
                    status_novo=documento.status,
                    timestamp=agora,
                    correlation_id=correlation_id,
                    detalhes={
                        'hash_sha256': hash_sha256,
                        'nome_original_tentativa': nome_original,
                        'origem_tentativa': origem,
                        'metadados_tentativa': dict(metadados or {}),
                    },
                ))
            except Exception as exc:
                raise FalhaPersistencia(
                    f'Falha ao registrar tentativa duplicada (documento_id={documento.documento_id}): {exc}'
                ) from exc
            return documento

        # Criacao + eventos formam uma unica unidade logica a partir
        # daqui: qualquer falha desfaz a criacao (remove o Documento)
        # antes de propagar FalhaPersistencia. O EventoHistorico que ja
        # tiver sido gravado com sucesso ANTES da falha permanece --
        # historico e append-only, nunca apagado, mesmo em rollback (ver
        # MAGNATA_OS_ESTADOS.md).
        try:
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
                    'metadados': dict(metadados or {}),
                },
            ))

            documento_registrado = transicionar_status(documento, StatusDocumento.REGISTRADO, agora)
            self._documentos.salvar(documento_registrado)

            self._historico.registrar(EventoHistorico(
                documento_id=documento_registrado.documento_id,
                evento='DOCUMENTO_REGISTRADO',
                status_anterior=StatusDocumento.RECEBIDO,
                status_novo=StatusDocumento.REGISTRADO,
                timestamp=agora,
                correlation_id=correlation_id,
                detalhes={},
            ))
        except Exception as exc:
            self._documentos.remover(documento.documento_id)
            raise FalhaPersistencia(
                f'Falha ao registrar entrada, rollback aplicado '
                f'(documento_id={documento.documento_id}): {exc}'
            ) from exc

        return documento_registrado

    def consultar_por_hash(self, hash_sha256: str) -> Optional[Documento]:
        """Consulta um Documento pelo hash, sem registrar nada. Valida o
        formato do hash antes de consultar -- nunca aceita uma string
        que nao seja SHA-256 valido em silencio."""
        if not hash_valido(hash_sha256):
            raise HashInvalido(f'hash_sha256 invalido: {hash_sha256!r}')
        return self._documentos.buscar_por_hash(hash_sha256.strip().lower())
