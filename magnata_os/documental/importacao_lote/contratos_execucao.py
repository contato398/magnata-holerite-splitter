"""Contratos (tipos puros) da camada de ESCRITA da importação em lote —
Fase 4, separada da classificação do dry-run (`contratos.py`).

Mesma regra de pureza: só `dataclasses`, `Enum` e tipos nativos.
"""

from __future__ import annotations

import types
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping, Optional

from .contratos import TipoDocumental


class SituacaoItemExecucao(str, Enum):
    """Situação de UM item dentro de UMA execução (lote). Nunca confundida
    com `ClassificacaoCorrespondencia` (contratos.py) — aquela é resultado
    de MATCHING; esta é resultado de ESCRITA/orquestração."""

    PENDENTE = 'PENDENTE'
    EM_PROCESSAMENTO = 'EM_PROCESSAMENTO'
    SUCESSO = 'SUCESSO'
    FAILED_RETRYABLE = 'FAILED_RETRYABLE'
    FAILED_COMPENSATED = 'FAILED_COMPENSATED'
    FAILED_ORPHANED = 'FAILED_ORPHANED'
    BLOQUEADO_CONFLITO_VERSAO = 'BLOQUEADO_CONFLITO_VERSAO'
    IGNORADO_NAO_EXACT = 'IGNORADO_NAO_EXACT'


# Situações terminais — um item nesta situação nunca é reprocessado do
# zero por uma nova tentativa (escritor.py consulta isto antes de agir).
SITUACOES_TERMINAIS = frozenset({
    SituacaoItemExecucao.SUCESSO,
    SituacaoItemExecucao.FAILED_COMPENSATED,
    SituacaoItemExecucao.FAILED_ORPHANED,
    SituacaoItemExecucao.BLOQUEADO_CONFLITO_VERSAO,
    SituacaoItemExecucao.IGNORADO_NAO_EXACT,
})


@dataclass(frozen=True)
class ItemExecucao:
    """Estado persistido de UM item de manifesto dentro de UMA execução
    (lote). `documento_id` é nullable e nunca é a chave do item — ver
    migration 0009 e seu comentário de cardinalidade."""

    item_importacao_id: str
    lote_id: str
    manifesto_item_id: str
    tipo_documental: TipoDocumental
    documento_id: Optional[str]
    identidade_ingestao: str
    situacao: SituacaoItemExecucao
    tentativas: int
    external_record_id: Optional[str]
    external_criado_por_esta_execucao: bool
    attachment_confirmado: bool
    ultimo_erro_sanitizado: Optional[str]
    criado_em: datetime
    atualizado_em: datetime


@dataclass(frozen=True)
class EventoItemExecucao:
    """Um fato ocorrido com UM item de execução — trilha append-only
    completa desde a criação (`PENDENTE`), inclusive ANTES de
    `documento_id` existir (correção de auditoria desta rodada:
    `eventos_documentais` exige `documento_id` NOT NULL e por isso não
    consegue representar essa fase — ver
    `magnata_os/documental/modulo01/migrations/0009_itens_importacao_lote.sql`,
    tabela `eventos_itens_importacao_lote`).

    Nunca editado nem apagado (mesmo princípio de `EventoHistorico`,
    modulo01/dominio.py). `detalhes` é sempre congelado para um Mapping
    imutável, mesma disciplina de `EventoHistorico.detalhes`."""

    item_importacao_id: str
    lote_id: str
    documento_id: Optional[str]
    situacao: SituacaoItemExecucao
    tentativas: int
    erro_sanitizado: Optional[str]
    timestamp: datetime
    detalhes: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.detalhes, types.MappingProxyType):
            object.__setattr__(self, 'detalhes', types.MappingProxyType(dict(self.detalhes or {})))


@dataclass(frozen=True)
class VersionamentoLogico:
    """Companheira 1:1 de `Documento` (modulo01/dominio.py) — identidade
    lógica (documento_logico_id) e posição na cadeia de versões.
    `substitui_documento_id`, quando presente, sempre aponta para outro
    VersionamentoLogico (nunca para um Documento fora do modelo)."""

    documento_id: str
    documento_logico_id: str
    versao_documento: int
    substitui_documento_id: Optional[str]
    criado_em: datetime


@dataclass(frozen=True)
class ResultadoEscrita:
    """Resultado de UMA tentativa de escrita de UM item — retornado por
    `escritor.escrever_item`. `processado=False` é a resposta explícita
    para itens que nunca deveriam ter sido chamados (classificação
    diferente de EXACT/pronto_para_gravacao) — nunca uma exceção nesse
    caso, é um resultado esperado do fluxo."""

    item_importacao_id: Optional[str]
    manifesto_item_id: str
    situacao: SituacaoItemExecucao
    documento_id: Optional[str]
    external_record_id: Optional[str]
    processado: bool
    motivo: Optional[str] = None
