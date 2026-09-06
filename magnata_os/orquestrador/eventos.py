"""
Envelope de evento e maquina de estados do nucleo do Orquestrador.

Contexto: MATRIZ_AUTONOMIA.md e ARQUITETURA_EVENTOS.md (Central Command,
Etapa 12) desenharam o padrao FONTE -> ADAPTER -> EVENTO -> SERVICO ->
ESTADO -> ORQUESTRADOR sem implementar o motor. Este modulo e a
implementacao real do "EVENTO" e do "ESTADO" desse padrao -- pequena,
testavel, substituivel.

Regra que vale para todo o pacote orquestrador, nao so este arquivo
(TAXONOMIA_MEMORIA.md paragrafo 2): nada aqui pode produzir efeito sobre
HUMAN_DECISION. Este modulo so define o envelope e a maquina de estados;
quem decide o que e permitido escrever e politica_autonomia.py e motor.py.
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping, Tuple


class TipoEvento(str, Enum):
    """Vocabulario FECHADO de proposito -- um TipoEvento novo exige
    decisao explicita (nunca inferido de string livre em tempo de
    execucao). Todo TipoEvento tem que ter uma entrada em
    politica_autonomia.py -- o padrao para o que nao tiver e
    HUMAN_REQUIRED, nunca omissao silenciosa."""

    GIT_MAIN_AVANCOU = 'GIT_MAIN_AVANCOU'
    PR_MESCLADO = 'PR_MESCLADO'
    SUITE_DIVERGIU = 'SUITE_DIVERGIU'
    ESTRUTURA_CODIGO_DIVERGIU = 'ESTRUTURA_CODIGO_DIVERGIU'
    # Evento operacional GENERICO: uma origem do Magnata OS propos uma
    # comunicacao. Nao significa WhatsApp, nao autoriza envio e nunca
    # carrega texto/destinatarios no envelope. Em V1 permanece sob gate
    # humano obrigatorio (politica_autonomia.py).
    COMUNICACAO_SOLICITADA = 'COMUNICACAO_SOLICITADA'


class EstadoExecucao(str, Enum):
    RECEIVED = 'RECEIVED'
    VALIDATED = 'VALIDATED'
    CLASSIFIED = 'CLASSIFIED'
    WAITING_GATE = 'WAITING_GATE'
    EXECUTING = 'EXECUTING'
    SUCCEEDED = 'SUCCEEDED'
    FAILED_RETRYABLE = 'FAILED_RETRYABLE'
    FAILED_FINAL = 'FAILED_FINAL'
    IGNORED = 'IGNORED'
    SUPERSEDED = 'SUPERSEDED'


# Transicoes permitidas -- fail-safe: qualquer transicao nao listada aqui
# e invalida por definicao ("nao sei" nunca vira "deve ser essa").
#
# X -> RECEIVED em varias linhas abaixo e sempre replay MANUAL (motor.py
# MotorOrquestrador.replay(), nunca automatico dentro de processar()).
# FAILED_FINAL -> RECEIVED e o caso original (Point 3, Missao de
# Fechamento). RECEIVED/VALIDATED/CLASSIFIED/EXECUTING/WAITING_GATE ->
# RECEIVED foram adicionados na reconciliacao de concorrencia: apos o
# fix que impede um segundo processar() de retomar um evento "em
# andamento" (fecha a corrida de dupla execucao de Acao externa), um
# evento cujo worker original morreu no meio do fluxo (crash entre a
# reivindicacao e o estado terminal) fica preso nesses estados para
# sempre por design -- NUNCA retomado automaticamente (isso reabriria
# a mesma corrida). A unica saida e um operador humano confirmar, fora
# de banda, que o worker original realmente morreu (nao esta so lento)
# e chamar replay() explicitamente -- mesmo gate humano ja usado para
# FAILED_FINAL, agora tambem cobrindo este caso.
TRANSICOES_VALIDAS: Mapping[EstadoExecucao, Tuple[EstadoExecucao, ...]] = {
    EstadoExecucao.RECEIVED: (
        EstadoExecucao.VALIDATED, EstadoExecucao.IGNORED, EstadoExecucao.RECEIVED,
    ),
    EstadoExecucao.VALIDATED: (EstadoExecucao.CLASSIFIED, EstadoExecucao.RECEIVED),
    EstadoExecucao.CLASSIFIED: (
        EstadoExecucao.WAITING_GATE, EstadoExecucao.EXECUTING, EstadoExecucao.SUPERSEDED,
        EstadoExecucao.RECEIVED,
    ),
    EstadoExecucao.WAITING_GATE: (
        EstadoExecucao.RECEIVED,
    ),  # terminal para o motor -- so replay manual avanca
    EstadoExecucao.EXECUTING: (
        EstadoExecucao.SUCCEEDED, EstadoExecucao.FAILED_RETRYABLE, EstadoExecucao.FAILED_FINAL,
        EstadoExecucao.RECEIVED,
    ),
    EstadoExecucao.FAILED_RETRYABLE: (
        EstadoExecucao.EXECUTING,
        EstadoExecucao.FAILED_FINAL,
        EstadoExecucao.WAITING_GATE,
    ),
    EstadoExecucao.SUCCEEDED: (),
    EstadoExecucao.FAILED_FINAL: (EstadoExecucao.RECEIVED,),  # replay manual
    EstadoExecucao.IGNORED: (),
    EstadoExecucao.SUPERSEDED: (),
}


class TransicaoInvalida(Exception):
    """Levantada quando o motor tenta uma transicao fora de
    TRANSICOES_VALIDAS. Nunca silenciada -- CLAUDE.md paragrafo 4:
    falha nunca e silenciosa."""


def validar_transicao(de: EstadoExecucao, para: EstadoExecucao) -> None:
    permitidas = TRANSICOES_VALIDAS.get(de, ())
    if para not in permitidas:
        raise TransicaoInvalida(
            f'transicao invalida: {de.value} -> {para.value} '
            f'(permitidas de {de.value}: {[p.value for p in permitidas]})'
        )


class Sensibilidade(str, Enum):
    """Quanto do payload pode ser logado/persistido em texto. Nunca
    colocar PII no envelope -- ver Evento.payload_referencia abaixo."""

    PUBLICO = 'PUBLICO'    # seguro em log/audit inteiro (ex.: sha de commit)
    INTERNO = 'INTERNO'    # seguro dentro do repositorio, nao em log externo
    SENSIVEL = 'SENSIVEL'  # so referencia, nunca conteudo


@dataclasses.dataclass(frozen=True)
class Evento:
    """Envelope canonico. Imutavel -- um evento nunca e alterado depois
    de criado; o que muda com o tempo e o RegistroExecucao associado.

    payload_referencia: NUNCA o payload inteiro quando sensibilidade !=
    PUBLICO -- so um identificador que permite localizar o dado na fonte
    original (sha de commit, numero de PR, caminho de arquivo). Mesma
    disciplina de MEMORIA_SENSIVEL.md aplicada ao envelope de evento --
    por isso o tamanho e limitado abaixo, nao so documentado.
    """

    event_id: str
    event_type: TipoEvento
    source: str
    occurred_at: datetime
    received_at: datetime
    correlation_id: str
    entity_type: str
    entity_id: str
    payload_referencia: str
    sensibilidade: Sensibilidade = Sensibilidade.INTERNO
    proveniencia: str = ''
    retry_count: int = 0

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError('event_id obrigatorio -- e a chave de idempotencia')
        if self.event_type is None:
            raise ValueError(
                'event_type obrigatorio -- motor.py despacha por evento.event_type.value'
            )
        if self.sensibilidade != Sensibilidade.PUBLICO and len(self.payload_referencia) > 500:
            raise ValueError(
                'payload_referencia parece grande demais para ser so uma '
                'referencia -- nunca colar payload sensivel/inteiro aqui'
            )


def novo_event_id(event_type: TipoEvento, entity_id: str, occurred_at: datetime) -> str:
    """event_id DETERMINISTICO -- mesmo (tipo, entidade, instante) produz
    sempre o mesmo id. E a base da deduplicacao (repositorio_execucoes.py
    busca por este id). Um id aleatorio nunca deduplicaria nada."""
    base = f'{event_type.value}:{entity_id}:{occurred_at.isoformat()}'
    return str(uuid.uuid5(uuid.NAMESPACE_URL, base))


def agora() -> datetime:
    return datetime.now(timezone.utc)
