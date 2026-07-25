"""
Modelo de dominio da esteira operacional do Modulo 01 (Documental), Fase 3.

Principio central desta fase: o estado TECNICO do Documento
(StatusDocumento, ver dominio.py -- RECEBIDO/REGISTRADO/.../ERRO) e a
etapa OPERACIONAL da esteira (onde o documento esta no fluxo de
producao: entrada, classificacao, separacao, etc.) sao dimensoes
DIFERENTES e nunca se misturam:

  - StatusDocumento responde "o registro deste Documento e valido?"
    (dado tecnico, dominio de dominio.py, imutavel por fase).
  - EtapaEsteira + SituacaoEsteira respondem "em que ponto do processo
    operacional este documento esta, e como esta indo?" -- podem
    evoluir independentemente do StatusDocumento (um Documento REGISTRADO
    pode estar em qualquer etapa da esteira, de ENTRADA a AUDITORIA).

Tudo aqui e puro: sem I/O, sem lock (lock e preocupacao de
repositorio_esteira.py), sem Airtable/Postgres/S3. Persistencia vive em
repositorio_esteira.py; orquestracao vive em servico_lote.py e
servico_avanco_esteira.py.
"""
from __future__ import annotations

import dataclasses
import secrets
import types
import uuid
from datetime import datetime
from enum import Enum
from typing import Mapping, Optional


class EtapaEsteira(str, Enum):
    """Etapas operacionais oficiais da esteira documental, nesta ordem
    linear. Nenhuma etapa nova entra aqui sem decisao explicita -- ver
    MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3.md."""

    ENTRADA = 'ENTRADA'
    REGISTRO = 'REGISTRO'
    CLASSIFICACAO = 'CLASSIFICACAO'
    SEPARACAO = 'SEPARACAO'
    IDENTIFICACAO = 'IDENTIFICACAO'
    VALIDACAO = 'VALIDACAO'
    MONTAGEM_PACOTE = 'MONTAGEM_PACOTE'
    DISTRIBUICAO = 'DISTRIBUICAO'
    CONFIRMACAO = 'CONFIRMACAO'
    AUDITORIA = 'AUDITORIA'


class SituacaoEsteira(str, Enum):
    """Como vai o trabalho na etapa atual -- eixo ortogonal a
    EtapaEsteira. Compartilhado entre LoteDocumental.situacao e
    EstadoEsteiraDocumento.situacao (mesmo vocabulario, dois usos)."""

    AGUARDANDO = 'AGUARDANDO'
    EM_PROCESSAMENTO = 'EM_PROCESSAMENTO'
    EM_REVISAO = 'EM_REVISAO'
    PRONTO = 'PRONTO'
    CONCLUIDO = 'CONCLUIDO'
    ERRO = 'ERRO'
    BLOQUEADO = 'BLOQUEADO'


class TipoProximaAcao(str, Enum):
    AUTOMATICA = 'AUTOMATICA'
    HUMANA = 'HUMANA'


@dataclasses.dataclass(frozen=True)
class MotivoBloqueio:
    """Motivo estruturado de um bloqueio ativo -- nunca um texto livre
    solto. `resolvivel_automaticamente` indica se algum processo futuro
    pode desbloquear sozinho (ex.: reconciliacao de arquivo orfao) ou se
    exige acao humana (ex.: CPF ilegivel no documento)."""

    codigo: str
    descricao: str
    detalhe_tecnico: Optional[str]
    resolvivel_automaticamente: bool


@dataclasses.dataclass(frozen=True)
class ProximaAcao:
    """Acao esperada para o documento sair do estado atual. `prazo` e
    `responsavel` sao opcionais -- nem toda acao tem SLA ou dono
    definido nesta fase."""

    acao: str
    tipo: TipoProximaAcao
    prazo: Optional[datetime]
    responsavel: Optional[str]


@dataclasses.dataclass(frozen=True)
class LoteDocumental:
    """Agrupa N arquivos recebidos numa mesma operacao de entrada,
    compartilhando origem e correlation_id. Um lote nao e um Documento
    nem substitui nenhum -- e a unidade de acompanhamento operacional de
    "uma entrada em lote" (ex.: um e-mail com 5 anexos, um upload em
    lote pela interface). `metadados` e sempre congelado para um Mapping
    imutavel, mesma disciplina de EventoHistorico.detalhes (dominio.py)."""

    lote_id: str
    origem: str
    recebido_em: datetime
    quantidade_arquivos: int
    situacao: SituacaoEsteira
    correlation_id: str
    criado_em: datetime
    atualizado_em: datetime
    metadados: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.metadados, types.MappingProxyType):
            object.__setattr__(self, 'metadados', types.MappingProxyType(dict(self.metadados or {})))


@dataclasses.dataclass(frozen=True)
class EstadoEsteiraDocumento:
    """Estado OPERACIONAL de um Documento na esteira -- entidade
    separada de Documento (dominio.py) de proposito (ver principio
    central no topo do arquivo). Uma linha por documento_id (estado
    atual, nao historico -- o historico de transicoes vai para
    RepositorioHistorico via eventos ESTEIRA_*, reaproveitando a
    infraestrutura de auditoria ja construida na Fase 1, em vez de
    duplicar uma tabela de eventos).

    `lote_id` e Optional -- documentos anteriores a Fase 3 (ou
    registrados fora do fluxo de lote) nunca tem lote_id, e isso e
    esperado, nao um erro (ver "Documentos legados" em
    MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3.md)."""

    documento_id: str
    lote_id: Optional[str]
    etapa_atual: EtapaEsteira
    situacao: SituacaoEsteira
    motivo_bloqueio: Optional[MotivoBloqueio]
    proxima_acao: Optional[ProximaAcao]
    entrou_na_etapa_em: datetime
    atualizado_em: datetime
    correlation_id: str


def gerar_lote_id() -> str:
    """ID canonico de lote. Encapsulado numa unica funcao, mesma logica
    de gerar_documento_id (dominio.py) -- trocar a estrategia de geracao
    nao exige mudar nenhum chamador."""
    return f'lote-{uuid.uuid4()}'


def gerar_correlation_id_lote() -> str:
    return f'lote{secrets.token_hex(8)}'


class TransicaoEtapaInvalida(Exception):
    """Uma transicao de etapa fora da maquina de estados oficial da
    esteira foi tentada. Nunca aplicada em silencio."""


class AvancoBloqueadoPorPendencia(Exception):
    """Tentativa de avancar a etapa de um documento com
    situacao == BLOQUEADO e motivo_bloqueio ativo. O bloqueio precisa
    ser resolvido explicitamente (ver servico_avanco_esteira.py) antes
    de qualquer avanco de etapa."""


# Maquina de estados oficial da esteira: ordem linear, cada etapa so
# avanca para a PROXIMA etapa da sequencia (nunca pula, nunca volta,
# nunca fica parada na mesma etapa). AUDITORIA e terminal. Retroceder
# ou "revisar" uma etapa e modelado via SituacaoEsteira (EM_REVISAO),
# nao via retrocesso de EtapaEsteira -- a etapa em si nunca anda para
# tras.
_ORDEM_ETAPAS = (
    EtapaEsteira.ENTRADA,
    EtapaEsteira.REGISTRO,
    EtapaEsteira.CLASSIFICACAO,
    EtapaEsteira.SEPARACAO,
    EtapaEsteira.IDENTIFICACAO,
    EtapaEsteira.VALIDACAO,
    EtapaEsteira.MONTAGEM_PACOTE,
    EtapaEsteira.DISTRIBUICAO,
    EtapaEsteira.CONFIRMACAO,
    EtapaEsteira.AUDITORIA,
)

TRANSICOES_ETAPA_PERMITIDAS: Mapping[EtapaEsteira, frozenset] = types.MappingProxyType({
    etapa: frozenset({_ORDEM_ETAPAS[indice + 1]}) if indice + 1 < len(_ORDEM_ETAPAS) else frozenset()
    for indice, etapa in enumerate(_ORDEM_ETAPAS)
})


def validar_transicao_etapa(etapa_atual: EtapaEsteira, nova_etapa: EtapaEsteira) -> None:
    """Levanta TransicaoEtapaInvalida se `nova_etapa` nao for a proxima
    etapa valida a partir de `etapa_atual`. Nao muta nada -- so valida."""
    permitidas = TRANSICOES_ETAPA_PERMITIDAS.get(etapa_atual, frozenset())
    if nova_etapa not in permitidas:
        raise TransicaoEtapaInvalida(
            f'Transicao de etapa invalida: {etapa_atual.value} -> {nova_etapa.value}'
        )
