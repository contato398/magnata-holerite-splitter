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
    """Etapas operacionais oficiais da esteira documental, na ordem
    canonica abaixo (usada para medir "salto" de etapa -- ver
    INDICE_ETAPA/eh_salto_de_etapa -- nao para dizer que a transicao e
    sempre passo-a-passo: ver TRANSICOES_ETAPA_PERMITIDAS, que e uma
    politica explicita, nao uma sequencia linear obrigatoria). Nenhuma
    etapa nova entra aqui sem decisao explicita -- ver
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


class MotivoSaltoObrigatorio(Exception):
    """Tentativa de pular uma ou mais etapas intermediarias (ver
    eh_salto_de_etapa) sem informar `motivo_transicao`. Um salto sempre
    precisa de uma razao registrada -- nunca aplicado em silencio (ver
    servico_avanco_esteira.py, ServicoAvancoEsteira.avancar_etapa)."""


# Ordem CANONICA das etapas -- usada so para medir distancia/"salto"
# entre duas etapas (ver INDICE_ETAPA/eh_salto_de_etapa), NAO para
# definir quais transicoes sao permitidas (isso e
# TRANSICOES_ETAPA_PERMITIDAS, uma politica explicita abaixo, nao uma
# sequencia linear obrigatoria).
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

INDICE_ETAPA: Mapping[EtapaEsteira, int] = types.MappingProxyType({
    etapa: indice for indice, etapa in enumerate(_ORDEM_ETAPAS)
})


def eh_salto_de_etapa(etapa_origem: EtapaEsteira, etapa_destino: EtapaEsteira) -> bool:
    """True se a transicao pula uma ou mais etapas intermediarias da
    ordem canonica (ex.: CLASSIFICACAO -> VALIDACAO pula SEPARACAO e
    IDENTIFICACAO; CLASSIFICACAO -> AUDITORIA pula todas as
    intermediarias, usado para duplicidade/descarte controlado).
    CLASSIFICACAO -> SEPARACAO (a proxima etapa imediata da ordem
    canonica) NAO e um salto. Funcao pura -- nao valida se a transicao
    e permitida, so mede distancia; quem decide se motivo_transicao e
    obrigatorio e ServicoAvancoEsteira.avancar_etapa."""
    return (INDICE_ETAPA[etapa_destino] - INDICE_ETAPA[etapa_origem]) > 1


# Politica EXPLICITA de transicoes permitidas -- substitui a antiga
# sequencia linear universal (toda etapa so avancava para a proxima).
# Um documento que nao exige separacao, por exemplo, vai direto de
# CLASSIFICACAO para IDENTIFICACAO ou VALIDACAO, sem passar
# artificialmente por SEPARACAO. CLASSIFICACAO -> AUDITORIA existe para
# duplicidade detectada ou descarte controlado (documento que nao
# segue o fluxo normal de pacote/distribuicao). AUDITORIA e sempre
# terminal (frozenset() -- nenhuma transicao a partir dela). Nenhuma
# entrada aqui pode apontar para uma etapa de indice igual ou menor que
# a etapa de origem -- essa invariante e verificada logo abaixo, na
# carga do modulo, para que uma edicao futura que introduza retrocesso
# quebre a IMPORTACAO do modulo (falha alta e ruidosa), nunca em
# silencio.
TRANSICOES_ETAPA_PERMITIDAS: Mapping[EtapaEsteira, frozenset] = types.MappingProxyType({
    EtapaEsteira.ENTRADA: frozenset({EtapaEsteira.REGISTRO}),
    EtapaEsteira.REGISTRO: frozenset({EtapaEsteira.CLASSIFICACAO}),
    EtapaEsteira.CLASSIFICACAO: frozenset({
        EtapaEsteira.SEPARACAO,
        EtapaEsteira.IDENTIFICACAO,
        EtapaEsteira.VALIDACAO,
        EtapaEsteira.AUDITORIA,
    }),
    EtapaEsteira.SEPARACAO: frozenset({EtapaEsteira.IDENTIFICACAO}),
    EtapaEsteira.IDENTIFICACAO: frozenset({EtapaEsteira.VALIDACAO}),
    EtapaEsteira.VALIDACAO: frozenset({EtapaEsteira.MONTAGEM_PACOTE}),
    EtapaEsteira.MONTAGEM_PACOTE: frozenset({EtapaEsteira.DISTRIBUICAO}),
    EtapaEsteira.DISTRIBUICAO: frozenset({EtapaEsteira.CONFIRMACAO}),
    EtapaEsteira.CONFIRMACAO: frozenset({EtapaEsteira.AUDITORIA}),
    EtapaEsteira.AUDITORIA: frozenset(),  # terminal
})

assert all(
    INDICE_ETAPA[destino] > INDICE_ETAPA[origem]
    for origem, destinos in TRANSICOES_ETAPA_PERMITIDAS.items()
    for destino in destinos
), (
    'TRANSICOES_ETAPA_PERMITIDAS contem uma transicao retroativa ou para a '
    'propria etapa -- nunca permitido (ver "nao permitir retrocesso silencioso" '
    'em MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3.md).'
)


def validar_transicao_etapa(etapa_atual: EtapaEsteira, nova_etapa: EtapaEsteira) -> None:
    """Levanta TransicaoEtapaInvalida se `nova_etapa` nao estiver
    prevista na politica (TRANSICOES_ETAPA_PERMITIDAS) a partir de
    `etapa_atual`. Nao muta nada -- so valida. Nao decide se a
    transicao e um "salto" que exige motivo -- ver eh_salto_de_etapa."""
    permitidas = TRANSICOES_ETAPA_PERMITIDAS.get(etapa_atual, frozenset())
    if nova_etapa not in permitidas:
        raise TransicaoEtapaInvalida(
            f'Transicao de etapa invalida: {etapa_atual.value} -> {nova_etapa.value}'
        )
