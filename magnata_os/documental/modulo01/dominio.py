"""
Modelo de dominio do Modulo 01 (Documental) -- fundacao da esteira
documental central.

Tudo aqui e puro: sem I/O, sem Airtable, sem rede, sem lock (lock e
preocupacao de repositorio, nao de dominio). Persistencia vive em
repositorio.py; orquestracao vive em servico_entrada.py.
"""
from __future__ import annotations

import dataclasses
import re
import secrets
import types
import uuid
from datetime import datetime
from enum import Enum
from typing import Mapping, Optional


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
    reconciliacao sem apagar histórico).

    `detalhes` e sempre congelado para um Mapping imutavel
    (types.MappingProxyType) no __post_init__, mesmo que quem construiu
    o evento tenha passado um dict comum -- a imutabilidade nao depende
    de disciplina de quem chama."""

    documento_id: str
    evento: str
    status_anterior: Optional[StatusDocumento]
    status_novo: Optional[StatusDocumento]
    timestamp: datetime
    correlation_id: str
    detalhes: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.detalhes, types.MappingProxyType):
            object.__setattr__(self, 'detalhes', types.MappingProxyType(dict(self.detalhes or {})))


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


def gerar_referencia_arquivo_provisoria(hash_sha256: str) -> str:
    """
    Provedor de referencia de armazenamento PROVISORIO -- nao persiste
    nada de verdade, so devolve uma referencia opaca baseada no hash.
    Existe para que Documento.arquivo_original nunca fique vazio antes de
    um adapter de armazenamento fisico real existir (fase futura).
    Trocavel via ServicoEntradaDocumental(gerador_referencia_arquivo=...)
    -- nunca hardcoded dentro do servico.
    """
    return f'pendente-armazenamento://{hash_sha256}'


class TransicaoStatusInvalida(Exception):
    """Uma transicao de status fora da maquina de estados oficial foi
    tentada. Nunca aplicada em silencio."""


# Maquina de estados oficial desta fase. So as transicoes efetivamente
# usadas pelo Modulo 01 (RECEBIDO -> REGISTRADO) sao exercidas hoje; as
# demais existem para o vocabulario ja estar definido quando modulos
# futuros (classificacao, OCR, etc.) precisarem delas -- nenhuma delas e
# implementada nesta fase. Uma transicao para o MESMO status nunca e
# valida (nao esta listada em nenhum conjunto abaixo).
TRANSICOES_PERMITIDAS: Mapping[StatusDocumento, frozenset] = types.MappingProxyType({
    StatusDocumento.RECEBIDO: frozenset({
        StatusDocumento.REGISTRADO, StatusDocumento.DUPLICADO, StatusDocumento.ERRO,
    }),
    StatusDocumento.REGISTRADO: frozenset({
        StatusDocumento.AGUARDANDO_PROCESSAMENTO, StatusDocumento.ERRO,
    }),
    StatusDocumento.AGUARDANDO_PROCESSAMENTO: frozenset({
        StatusDocumento.EM_PROCESSAMENTO, StatusDocumento.ERRO,
    }),
    StatusDocumento.EM_PROCESSAMENTO: frozenset({
        StatusDocumento.EM_REVISAO, StatusDocumento.AGUARDANDO_PROCESSAMENTO, StatusDocumento.ERRO,
    }),
    StatusDocumento.EM_REVISAO: frozenset({
        StatusDocumento.EM_PROCESSAMENTO, StatusDocumento.ERRO,
    }),
    StatusDocumento.ERRO: frozenset({
        StatusDocumento.EM_PROCESSAMENTO, StatusDocumento.EM_REVISAO,
    }),
    StatusDocumento.DUPLICADO: frozenset(),  # terminal nesta fase
})


def transicionar_status(documento: Documento, novo_status: StatusDocumento, quando: datetime) -> Documento:
    """Retorna uma NOVA instancia de Documento com o status atualizado.
    Nunca muta `documento`. Rejeita (TransicaoStatusInvalida) qualquer
    transicao fora de TRANSICOES_PERMITIDAS, incluindo transicionar para
    o mesmo status. Quem chama e responsavel por registrar o
    EventoHistorico correspondente."""
    permitidas = TRANSICOES_PERMITIDAS.get(documento.status, frozenset())
    if novo_status not in permitidas:
        raise TransicaoStatusInvalida(
            f'Transicao invalida: {documento.status.value} -> {novo_status.value} '
            f'(documento_id={documento.documento_id})'
        )
    return dataclasses.replace(documento, status=novo_status, atualizado_em=quando)
