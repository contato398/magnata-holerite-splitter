"""Adaptador de entrada documental com armazenamento durável (Fase 2).

Fachada compatível com ServicoEntradaDocumental que delega para
registrar_entrada_com_armazenamento(), permitindo composição com
ServicoCriacaoLote via duck typing (sem alteração de código público).

Responsabilidade ÚNICA:
expor registrar_entrada(...) com mesma assinatura, delegando tudo para
legado existente. NÃO implementa hash, deduplicação, Documento,
histórico, armazenamento ou esteira — apenas composição de partes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from .armazenamento import ArmazenamentoArquivos
from .dominio import Documento
from .repositorio import RepositorioDocumentos, RepositorioHistorico
from .servico_entrada_persistente import registrar_entrada_com_armazenamento


class AdaptadorEntradaDuravel:
    """Fachada para registrar_entrada_com_armazenamento.

    Fornece registrar_entrada() com assinatura idêntica a
    ServicoEntradaDocumental, permitindo uso via duck typing em
    ServicoCriacaoLote sem alteração de código.

    Garantias:
    - blob armazenado ANTES de Documento (atomicidade por função)
    - arquivo_original contém referência real (não placeholder)
    - idempotência por hash_sha256 preservada
    - histórico e deduplicação delegados ao legado
    """

    def __init__(
        self,
        repositorio_documentos: RepositorioDocumentos,
        repositorio_historico: RepositorioHistorico,
        armazenamento: ArmazenamentoArquivos,
        relogio: Optional[Callable[[], datetime]] = None,
    ) -> None:
        """Inicializa com todas as dependências necessárias.

        Args:
            repositorio_documentos: Persistência de Documento
            repositorio_historico: Persistência de EventoHistorico
            armazenamento: Backend de blob (S3, memória, etc.)
            relogio: Callable para obter datetime.now() (opcional, para testes determinísticos)
        """
        self._repositorio_documentos = repositorio_documentos
        self._repositorio_historico = repositorio_historico
        self._armazenamento = armazenamento
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
        """Registra entrada com armazenamento durável.

        Assinatura idêntica a ServicoEntradaDocumental.registrar_entrada()
        para permitir substituição via duck typing.

        Delegação:
        1. registrar_entrada_com_armazenamento() armazena blob
        2. Mesmo retorna Documento com arquivo_original = referência real
        3. Histórico e deduplicação tratados pelo legado

        Args:
            conteudo: bytes do arquivo
            nome_original: nome do arquivo
            mime_type: tipo MIME
            origem: identificação da fonte
            correlation_id: opcional, para correlação de logs
            lote_id: opcional, para agrupar documentos
            metadados: opcional, metadados da entrada

        Returns:
            Documento persistido com arquivo_original preenchido

        Raises:
            FalhaArmazenamento: se blob não puder ser armazenado
            FalhaPersistencia: se Documento não puder ser persistido
        """
        kwargs_relogio = {'relogio': self._relogio} if self._relogio is not None else {}
        return registrar_entrada_com_armazenamento(
            repositorio_documentos=self._repositorio_documentos,
            repositorio_historico=self._repositorio_historico,
            armazenamento=self._armazenamento,
            conteudo=conteudo,
            nome_original=nome_original,
            mime_type=mime_type,
            origem=origem,
            correlation_id=correlation_id,
            lote_id=lote_id,
            metadados=metadados,
            **kwargs_relogio,
        )
