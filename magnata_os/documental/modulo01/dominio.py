"""
Modelo de dominio do Modulo 01 (Documental) -- fundacao da esteira
documental central.

Tudo aqui e puro: sem I/O, sem Airtable, sem rede. Persistencia vive em
repositorio.py; orquestracao vive em servico_entrada.py.
"""
from __future__ import annotations

import dataclasses
import re
import secrets
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional


class StatusDocumento(str, Enum):
    """Estados oficiais do documento nesta fase. Nenhum estado novo entra
    aqui sem decisao explicita -- ver MAGNATA_OS_DOCUMENTAL_MODULO01.md."""

    RECEBIDO = 'RECEBIDO'
    REGISTRADO = 'REGISTRADO'
    DUPLICADO = 'DUPLICADO'
    AGUARDANDO_PROCESSAMENTO = 'AGUARDANDO_PROCESSAMENTO'
    EM_PROCESSAMENTO = 'EM_PROCESSAMENTO'
    EM_REVISAO = 'EM_REVISAO'
    ERRO = 'ERRO'


@dataclasses.dataclass(frozen=True)
class Documento:
    """Entidade central. Imutavel -- uma transicao de status produz uma
    nova instancia (ver transicionar_status), nunca muta a existente."""

    documento_id: str
    arquivo_original: str
    nome_original: str
    mime_type: str
    tamanho: int
    hash_sha256: str
    origem: str
    recebido_em: datetime
    lote_id: Optional[str]
    status: StatusDocumento
    correlation_id: str
    criado_em: datetime
    atualizado_em: datetime


@dataclasses.dataclass(frozen=True)
class EventoHistorico:
    """Um fato ocorrido com um Documento. Historico e append-only -- nunca
    editado nem apagado (ver MAGNATA_OS_ESTADOS.md, principio de
    reconciliacao sem apagar histórico)."""

    documento_id: str
    evento: str
    status_anterior: Optional[StatusDocumento]
    status_novo: Optional[StatusDocumento]
    timestamp: datetime
    correlation_id: str
    detalhes: dict


_PADRAO_SHA256 = re.compile(r'^[0-9a-f]{64}$')


def hash_valido(valor: str) -> bool:
    """True se valor for uma string SHA-256 valida (64 chars hex)."""
    return bool(_PADRAO_SHA256.match((valor or '').strip().lower()))


def gerar_documento_id() -> str:
    """
    ID canonico do documento. Encapsulado numa unica funcao -- trocar a
    estrategia de geracao (ex.: UUIDv7 no futuro) nao exige mudar nenhum
    chamador, so esta funcao.
    """
    return str(uuid.uuid4())


def gerar_correlation_id() -> str:
    """Correlation ID observacional para uma operacao de entrada."""
    return f'doc{secrets.token_hex(8)}'


def transicionar_status(documento: Documento, novo_status: StatusDocumento, quando: datetime) -> Documento:
    """Retorna uma NOVA instancia de Documento com o status atualizado.
    Nunca muta `documento`. Quem chama e responsavel por registrar o
    EventoHistorico correspondente."""
    return dataclasses.replace(documento, status=novo_status, atualizado_em=quando)
