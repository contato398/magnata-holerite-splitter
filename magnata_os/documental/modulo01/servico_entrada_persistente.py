"""
Operacao de entrada da Fase 2 -- orquestra armazenamento fisico +
persistencia de Documento/Historico (Fase 1, inalterada).

Nao substitui ServicoEntradaDocumental (servico_entrada.py) -- compoe
com ele. A logica de idempotencia, atomicidade sob concorrencia e
compensacao de Documento/Historico continua sendo a da Fase 1, sem
nenhuma alteracao. Este modulo so acrescenta o passo de armazenamento
fisico ANTES dela, na ordem definida em
MAGNATA_OS_DOCUMENTAL_MODULO01_FASE2.md ("Sequencia transacional
escolhida").
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Callable, Optional

from .armazenamento import ArmazenamentoArquivos
from .dominio import Documento, gerar_documento_id
from .repositorio import RepositorioDocumentos, RepositorioHistorico
from .servico_entrada import ArquivoAusente, ServicoEntradaDocumental, _relogio_padrao


class FalhaArmazenamento(Exception):
    """Falha ao armazenar o arquivo fisico. Levantada ANTES de qualquer
    interacao com o repositorio de Documento -- nenhum Documento e
    criado quando isso acontece, entao nao ha o que compensar."""


def registrar_entrada_com_armazenamento(
    repositorio_documentos: RepositorioDocumentos,
    repositorio_historico: RepositorioHistorico,
    armazenamento: ArmazenamentoArquivos,
    conteudo: bytes,
    nome_original: str,
    mime_type: str,
    origem: str,
    gerador_documento_id: Callable[[], str] = gerar_documento_id,
    relogio: Callable[[], datetime] = _relogio_padrao,
    correlation_id: Optional[str] = None,
    lote_id: Optional[str] = None,
    metadados: Optional[dict] = None,
) -> Documento:
    """
    Registra a entrada de um documento com armazenamento fisico
    durevel. Ordem (ver MAGNATA_OS_DOCUMENTAL_MODULO01_FASE2.md):

      1. calcula o hash SHA-256 do conteudo;
      2. armazena o arquivo (idempotente por hash) -- SEMPRE antes do
         Documento, para que nunca exista um Documento sem arquivo
         correspondente;
      3. delega ao ServicoEntradaDocumental (Fase 1) para persistir
         Documento + Historico, usando a referencia ja resolvida no
         passo 2 -- sem repetir nenhuma chamada de armazenamento.

    Se o armazenamento falhar, levanta FalhaArmazenamento antes de tocar
    em qualquer repositorio de Documento. Se o registro do
    Documento/Historico falhar depois do armazenamento ter sucesso, o
    arquivo permanece armazenado (nunca e removido automaticamente) --
    idempotencia por hash garante que uma nova tentativa com o mesmo
    conteudo reaproveita o arquivo ja la, sem reenviar.
    """
    if not conteudo:
        raise ArquivoAusente(
            'Arquivo ausente ou vazio -- nao e possivel registrar entrada sem conteudo.'
        )

    hash_sha256 = hashlib.sha256(conteudo).hexdigest()

    try:
        referencia = armazenamento.armazenar(
            hash_sha256, conteudo, mime_type, nome_original, len(conteudo),
        )
    except Exception as exc:
        raise FalhaArmazenamento(
            f'Falha ao armazenar arquivo antes de registrar o Documento '
            f'(hash_sha256={hash_sha256}): {exc}'
        ) from exc

    servico = ServicoEntradaDocumental(
        repositorio_documentos,
        repositorio_historico,
        gerador_documento_id=gerador_documento_id,
        gerador_referencia_arquivo=lambda _hash: referencia,
        relogio=relogio,
    )
    return servico.registrar_entrada(
        conteudo, nome_original, mime_type, origem,
        correlation_id=correlation_id, lote_id=lote_id, metadados=metadados,
    )
