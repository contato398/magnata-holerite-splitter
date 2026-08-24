"""
Nucleo minimo executavel do Orquestrador -- coordena portas/adapters
existentes, nunca reimplementa o que ja existe (sensor, Graphify,
ServicoCriacaoLote). Ver docs/magnata-os/central-command/ARQUITETURA_EVENTOS.md.

Fluxo: EVENTO -> NORMALIZACAO -> IDENTIFICACAO -> DEDUPLICACAO ->
CLASSIFICACAO -> POLITICA DE AUTONOMIA -> ACAO -> VALIDACAO -> REGISTRO
-> ATUALIZACAO DO ESTADO.

Regra dura, sem excecao (TAXONOMIA_MEMORIA.md paragrafo 2): nenhuma Acao
coordenada por este motor pode escrever em HUMAN_DECISION ou em arquivo
protegido. Isto e VERIFICADO em tempo de execucao contra o que a Acao
declara ter escrito (ResultadoAcao.caminhos_escritos) -- nao so
documentado. Se uma Acao escrever em caminho proibido, o motor marca a
execucao como falha final E levanta AcaoProibida -- nunca deixa passar
em silencio.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional, Tuple

from .classificador_falha import ClasseFalha, classificar
from .configuracao import (
    aplicar_kill_switch_bloqueio,
    modo_seco_executavel,
)
from .eventos import EstadoExecucao, Evento, Sensibilidade, TipoEvento, agora, validar_transicao
from .fila_desistencia import FilaDesistenciaEmMemoria, extrair_para_fila_desistencia
from .politica_autonomia import NivelAutonomia, nivel_para
from .repositorio_execucoes import RegistroExecucao, RepositorioExecucoes

MAX_TENTATIVAS = 3
BACKOFF_BASE_SEGUNDOS = 60

# Caminhos que NENHUMA Acao pode escrever -- TAXONOMIA_MEMORIA.md
# paragrafo 2 (HUMAN_DECISION) + CLAUDE.md paragrafo 7 (app.py/render.yaml
# protegidos). Checado contra o que a Acao DECLARA ter escrito.
CAMINHOS_PROIBIDOS: Tuple[str, ...] = (
    'DECISIONS.md', 'DIRECTIVES.md', 'app.py', 'render.yaml', 'Procfile',
)


class AcaoProibida(Exception):
    """Levantada quando uma Acao declara ter escrito num caminho de
    HUMAN_DECISION ou protegido. Nunca contornavel por configuracao."""


@dataclasses.dataclass(frozen=True)
class ResultadoAcao:
    sucesso: bool
    evidencia: str
    caminhos_escritos: Tuple[str, ...] = ()


Acao = Callable[[Evento], ResultadoAcao]


def _serializar_evento(evento: Evento) -> str:
    """Serializa Evento para JSON (para armazenamento em replay)."""
    sensibilidade_val = (
        evento.sensibilidade.value
        if hasattr(evento.sensibilidade, 'value')
        else evento.sensibilidade
    )
    return json.dumps({
        'event_id': evento.event_id,
        'event_type': evento.event_type.value,
        'source': evento.source,
        'occurred_at': evento.occurred_at.isoformat(),
        'received_at': evento.received_at.isoformat(),
        'correlation_id': evento.correlation_id,
        'entity_type': evento.entity_type,
        'entity_id': evento.entity_id,
        'payload_referencia': evento.payload_referencia,
        'sensibilidade': sensibilidade_val,
        'proveniencia': evento.proveniencia,
        'retry_count': evento.retry_count,
    })


def _desserializar_evento(evento_json: str) -> Evento:
    """Reconstrói Evento a partir de JSON (para replay)."""
    d = json.loads(evento_json)
    return Evento(
        event_id=d['event_id'],
        event_type=TipoEvento(d['event_type']),
        source=d['source'],
        occurred_at=datetime.fromisoformat(d['occurred_at']),
        received_at=datetime.fromisoformat(d['received_at']),
        correlation_id=d['correlation_id'],
        entity_type=d['entity_type'],
        entity_id=d['entity_id'],
        payload_referencia=d['payload_referencia'],
        sensibilidade=Sensibilidade(d['sensibilidade']),
        proveniencia=d['proveniencia'],
        retry_count=d['retry_count'],
    )


class MotorOrquestrador:
    """Pequeno de proposito -- coordena, nao contem logica de negocio.
    Cada Acao e uma funcao registrada por TipoEvento (evento.value); o
    motor nunca sabe o que a Acao faz por dentro, so o contrato
    (Evento -> ResultadoAcao)."""

    def __init__(
        self,
        repositorio: RepositorioExecucoes,
        acoes: Dict[str, Acao],
        observador: Optional[Callable[[str, dict], None]] = None,
        fila_desistencia: Optional[FilaDesistenciaEmMemoria] = None,
    ) -> None:
        self._repo = repositorio
        self._acoes = acoes
        self._observador = observador
        self._fila_desistencia = fila_desistencia or FilaDesistenciaEmMemoria()

    def _emitir(self, nome: str, **campos) -> None:
        if self._observador is not None:
            self._observador(nome, campos)

    def processar(self, evento: Evento) -> RegistroExecucao:
        # 1) IDENTIFICACAO + DEDUPLICACAO -- idempotencia por event_id.
        # Um evento ja concluido (em qualquer estado terminal) nunca e
        # reprocessado -- devolve o registro existente sem tocar em nada.
        existente = self._repo.buscar_por_event_id(evento.event_id)
        if existente is not None and existente.estado in (
            EstadoExecucao.SUCCEEDED, EstadoExecucao.IGNORED, EstadoExecucao.FAILED_FINAL,
            # SUPERSEDED tambem nao tem transicao de saida em
            # TRANSICOES_VALIDAS (achado da reconciliacao) -- faltava
            # aqui, entao caia no ramo "em andamento" por engano e
            # levantava TransicaoInvalida em vez de devolver o registro
            # terminal como os outros tres.
            EstadoExecucao.SUPERSEDED,
        ):
            self._emitir(
                'evento_duplicado_ignorado',
                event_id=evento.event_id, estado_anterior=existente.estado.value,
            )
            return existente

        # RETRY: um evento que ja falhou de forma retentavel NUNCA volta
        # para o inicio do fluxo (RECEIVED/VALIDATED/CLASSIFIED de novo)
        # -- isso reclassificaria e reexecutaria fora de ordem. Ele so
        # pode ir direto para EXECUTING de novo, preservando o
        # `attempt`/nivel ja calculados na primeira passagem.
        if existente is not None and existente.estado == EstadoExecucao.FAILED_RETRYABLE:
            acao = self._acoes.get(evento.event_type.value)
            if acao is None:
                # a acao sumiu do registro entre tentativas (nao deveria
                # acontecer em uso normal) -- nunca finge sucesso.
                existente = self._transicionar(existente, EstadoExecucao.WAITING_GATE)
                existente.resultado = 'acao ausente na retentativa -- gate por omissao'
                self._repo.salvar(existente)
                self._emitir('gate_por_acao_ausente', event_id=evento.event_id)
                return existente
            self._emitir('evento_recebido', event_id=evento.event_id, tipo=evento.event_type.value,
                          retentativa=True)
            return self._executar_e_registrar(existente, evento, acao)

        if existente is None:
            # REIVINDICACAO ATOMICA: fecha a janela de corrida em que dois
            # workers concorrentes chegam aqui ao mesmo tempo para o MESMO
            # event_id novo -- sem isso, ambos veriam existente=None e
            # ambos executariam a Acao (prova: threading.Barrier forcando
            # a corrida mostrou dupla execucao de efeito externo antes
            # deste fix). criar_se_novo() e atomico no nivel do
            # repositorio (PRIMARY KEY no SQLite, threading.Lock em
            # memoria) -- nunca dois chamadores ganham para o mesmo
            # event_id.
            agora_ = agora()
            candidato = RegistroExecucao(
                event_id=evento.event_id, event_type=evento.event_type.value,
                estado=EstadoExecucao.RECEIVED, nivel_autonomia=-1, acao='',
                resultado=None, evidencia=None, attempt=0,
                next_retry_at=None, last_error_classe=None, last_error_at=None,
                criado_em=agora_, atualizado_em=agora_,
                evento_json=_serializar_evento(evento),
            )
            ganhou = self._repo.criar_se_novo(candidato)
            if not ganhou:
                # Perdeu a corrida -- outro worker ja reivindicou este
                # event_id. NUNCA executar a Acao aqui: devolve o estado
                # que o vencedor ja tiver persistido (pode ainda nao ser
                # terminal -- quem chama de novo mais tarde ve o estado
                # final). Falha nunca e silenciosa, mas aqui nao ha falha
                # -- so quem chegou depois, entao apenas cede.
                perdedor_encontrou = self._repo.buscar_por_event_id(evento.event_id)
                self._emitir(
                    'evento_perdeu_corrida_de_criacao', event_id=evento.event_id,
                )
                return perdedor_encontrou if perdedor_encontrou is not None else candidato
            registro = candidato
        else:
            # Evento ja existe mas nao esta em estado terminal (checado
            # acima) nem em FAILED_RETRYABLE (retomada explicita acima) --
            # ou seja, esta em RECEIVED/VALIDATED/CLASSIFIED/EXECUTING/
            # WAITING_GATE/SUPERSEDED: "em andamento" ou aguardando gate,
            # nunca um convite para reprocessar do zero. NUNCA retomar/
            # reexecutar aqui: um segundo processar() para o mesmo
            # event_id enquanto o primeiro ainda esta em andamento e a
            # MESMA classe de corrida que criar_se_novo() fecha para
            # evento novo -- aqui fecha a versao "evento ja existe mas
            # ainda em andamento" (achado da reconciliacao: sem este
            # bloqueio, um segundo worker via o registro em RECEIVED/
            # VALIDATED/etc. e reexecutava a Acao do zero, mesmo com
            # criar_se_novo() ja fechando a janela do evento
            # completamente novo).
            self._emitir(
                'evento_em_andamento_ignorado', event_id=evento.event_id,
                estado_atual=existente.estado.value,
            )
            return existente
        self._emitir('evento_recebido', event_id=evento.event_id, tipo=evento.event_type.value)

        # 2) VALIDACAO -- so chegar aqui ja significa Evento bem formado
        # (Evento.__post_init__ ja validou o envelope na criacao).
        registro = self._transicionar(registro, EstadoExecucao.VALIDATED)

        # 3) CLASSIFICACAO + POLITICA DE AUTONOMIA
        nivel = nivel_para(evento.event_type)
        # KILL_SWITCH: se ativado, força HUMAN_REQUIRED para tudo
        nivel = NivelAutonomia(aplicar_kill_switch_bloqueio(int(nivel)))
        registro.nivel_autonomia = int(nivel)
        registro = self._transicionar(registro, EstadoExecucao.CLASSIFIED)
        self._emitir('evento_classificado', event_id=evento.event_id, nivel=nivel.name)

        if nivel != NivelAutonomia.EXECUTE_SAFE:
            registro = self._transicionar(registro, EstadoExecucao.WAITING_GATE)
            registro.resultado = f'gate humano -- nivel {nivel.name}'
            self._repo.salvar(registro)
            self._emitir('gate_humano', event_id=evento.event_id, nivel=nivel.name)
            return registro

        # 4) ACAO -- so chega aqui em EXECUTE_SAFE.
        acao = self._acoes.get(evento.event_type.value)
        if acao is None:
            # Fail-safe: politica diz EXECUTE_SAFE mas ninguem registrou
            # a Acao correspondente -- nunca inventar comportamento,
            # vira gate por omissao em vez de travar ou fingir sucesso.
            registro = self._transicionar(registro, EstadoExecucao.WAITING_GATE)
            registro.resultado = 'sem acao registrada para este tipo -- gate por omissao'
            self._repo.salvar(registro)
            self._emitir('gate_por_acao_ausente', event_id=evento.event_id)
            return registro

        registro.acao = evento.event_type.value
        return self._executar_e_registrar(registro, evento, acao)

    def _executar_e_registrar(
        self, registro: RegistroExecucao, evento: Evento, acao: Acao,
    ) -> RegistroExecucao:
        """Passos 4 (execucao) a 6 (registro), compartilhados entre a
        primeira tentativa e cada retentativa -- para que os dois
        caminhos apliquem exatamente a mesma validacao de resultado
        (nenhum caminho proibido) e a mesma contagem de tentativas."""
        registro = self._transicionar(registro, EstadoExecucao.EXECUTING)
        registro.attempt += 1
        self._emitir('acao_executando', event_id=evento.event_id, tentativa=registro.attempt)

        # DRY_RUN: simula execucao sem side effect
        if modo_seco_executavel(registro.acao):
            registro = self._transicionar(registro, EstadoExecucao.SUCCEEDED)
            registro.resultado = 'DRY_RUN: simulacao concluida sem side effect'
            registro.evidencia = 'Orquestrador rodou em modo seco (ORQUESTRADOR_DRY_RUN=1)'
            self._repo.salvar(registro)
            self._emitir(
                'acao_dry_run', event_id=evento.event_id, acao=registro.acao,
                tentativa=registro.attempt,
            )
            return registro

        try:
            resultado = acao(evento)
        except Exception as exc:  # noqa: BLE001 -- classificado abaixo, nunca escondido
            classe = classificar(exc)
            registro.last_error_classe = classe.value
            registro.last_error_at = agora()
            if classe == ClasseFalha.TRANSIENT and registro.attempt < MAX_TENTATIVAS:
                registro = self._transicionar(registro, EstadoExecucao.FAILED_RETRYABLE)
                registro.next_retry_at = agora() + timedelta(
                    seconds=BACKOFF_BASE_SEGUNDOS * (2 ** (registro.attempt - 1))
                )
                registro.resultado = f'falha transitoria, tentativa {registro.attempt}/{MAX_TENTATIVAS}'
                self._repo.salvar(registro)
                self._emitir(
                    'falha_transitoria', event_id=evento.event_id,
                    tentativa=registro.attempt, next_retry_at=registro.next_retry_at.isoformat(),
                )
                return registro
            registro = self._transicionar(registro, EstadoExecucao.FAILED_FINAL)
            registro.resultado = f'falha final ({classe.value})'
            self._repo.salvar(registro)
            self._emitir('falha_final', event_id=evento.event_id, classe=classe.value)
            # Registra na fila de desistencia
            item_dlq = extrair_para_fila_desistencia(registro)
            if item_dlq:
                self._fila_desistencia.registrar(item_dlq)
            return registro

        # 5) VALIDACAO DO RESULTADO -- nenhuma Acao pode ter escrito em
        # caminho proibido, mesmo que ela mesma nao tenha percebido.
        for caminho in resultado.caminhos_escritos:
            if any(proibido in caminho for proibido in CAMINHOS_PROIBIDOS):
                registro = self._transicionar(registro, EstadoExecucao.FAILED_FINAL)
                registro.resultado = f'ACAO BLOQUEADA -- escreveu em caminho proibido: {caminho}'
                self._repo.salvar(registro)
                self._emitir(
                    'acao_bloqueada_caminho_proibido',
                    event_id=evento.event_id, caminho=caminho,
                )
                # Registra na fila de desistencia
                item_dlq = extrair_para_fila_desistencia(registro)
                if item_dlq:
                    self._fila_desistencia.registrar(item_dlq)
                raise AcaoProibida(
                    f'Acao para {evento.event_type.value} escreveu em {caminho}, que e '
                    f'HUMAN_DECISION/protegido -- nunca permitido em nivel EXECUTE_SAFE'
                )

        # 6) REGISTRO + ATUALIZACAO DO ESTADO
        registro = self._transicionar(registro, EstadoExecucao.SUCCEEDED)
        registro.resultado = 'sucesso'
        registro.evidencia = resultado.evidencia
        self._repo.salvar(registro)
        self._emitir(
            'acao_sucesso', event_id=evento.event_id,
            caminhos=list(resultado.caminhos_escritos),
        )
        return registro

    def _transicionar(self, registro: RegistroExecucao, novo_estado: EstadoExecucao) -> RegistroExecucao:
        validar_transicao(registro.estado, novo_estado)
        estado_anterior = registro.estado
        registro.estado = novo_estado
        registro.atualizado_em = agora()
        # Registrar transição no log append-only
        try:
            self._repo.registrar_auditoria(
                event_id=registro.event_id,
                estado_anterior=estado_anterior.value,
                estado_novo=novo_estado.value,
                registrado_em=registro.atualizado_em,
            )
        except Exception as e:
            # Log de auditoria não deve bloquear o processamento
            self._emitir('erro_ao_registrar_auditoria', event_id=registro.event_id, erro=str(e))
        return registro

    # Estados que replay() aceita como ponto de partida. FAILED_FINAL e o
    # caso original (Point 3). Os demais foram abertos na reconciliação
    # de concorrência: depois que processar() passou a recusar retomar
    # um evento "em andamento" (fecha a corrida de dupla execução de
    # Ação externa -- ver comentário em TRANSICOES_VALIDAS), um crash do
    # worker original entre a reivindicação e o estado terminal deixa o
    # evento preso num desses estados para sempre, e replay() manual é a
    # única saída (gate humano -- nunca automático).
    _ESTADOS_REPLAYAVEIS = (
        EstadoExecucao.FAILED_FINAL,
        EstadoExecucao.RECEIVED,
        EstadoExecucao.VALIDATED,
        EstadoExecucao.CLASSIFIED,
        EstadoExecucao.EXECUTING,
        EstadoExecucao.WAITING_GATE,
    )

    def replay(self, event_id: str, solicitado_por: str, motivo: str) -> RegistroExecucao:
        """Replay manual e explícito de um evento parado -- falhou
        permanentemente (FAILED_FINAL) ou ficou preso "em andamento"
        porque o worker que o reivindicou morreu antes de um estado
        terminal (RECEIVED/VALIDATED/CLASSIFIED/EXECUTING/WAITING_GATE).

        Point 3 da Missão de Fechamento: Replay Controlado
        - Manual: usuário solicita explicitamente
        - Explícito: não automático, com provenance (quem, quando, por quê)
        - Rastreado: registro atualizado com metadados de replay

        Quem chama isto para um evento que NÃO está em FAILED_FINAL está
        confirmando, fora de banda, que o worker anterior realmente
        morreu -- nunca chamar isto só porque um evento está demorando;
        processar() de novo é seguro e não reexecuta a Ação enquanto o
        worker original ainda pode estar vivo (ver motor.py:processar).

        Args:
            event_id: Evento a ser repetido (ver _ESTADOS_REPLAYAVEIS)
            solicitado_por: Identificação de quem solicitou (user/system)
            motivo: Razão para o replay (observação human-readable --
                para um replay de estado "em andamento", deve registrar
                como foi confirmado que o worker morreu)

        Returns:
            RegistroExecucao atualizado após retry bem-sucedido (ou falha nova)
        """
        # Recuperar o registro original
        registro = self._repo.buscar_por_event_id(event_id)
        if registro is None:
            raise ValueError(f'Evento não encontrado: {event_id}')

        if registro.estado not in self._ESTADOS_REPLAYAVEIS:
            raise ValueError(
                f'Evento em {registro.estado.value} não é replayável; '
                f'estados aceitos: {[e.value for e in self._ESTADOS_REPLAYAVEIS]}'
            )

        if registro.evento_json is None:
            raise ValueError(f'Evento não foi persistido para replay: {event_id}')

        # Desserializar evento original
        evento = _desserializar_evento(registro.evento_json)

        # Marcar como manualmente reiniciado
        agora_ = agora()
        registro.manualmente_reiniciado_por = solicitado_por
        registro.manualmente_reiniciado_em = agora_
        registro.motivo_reinicio_manual = motivo

        # Resetar para RECEIVED (re-processar do zero)
        registro = self._transicionar(registro, EstadoExecucao.RECEIVED)
        registro.attempt = 0
        registro.next_retry_at = None
        registro.last_error_classe = None
        registro.last_error_at = None
        registro.resultado = None
        registro.evidencia = None

        self._emitir(
            'replay_iniciado', event_id=event_id,
            solicitado_por=solicitado_por, motivo=motivo,
        )

        # Re-validar, classificar e executar (mesmo fluxo de processar())
        registro = self._transicionar(registro, EstadoExecucao.VALIDATED)

        # Classificação + Política de Autonomia
        nivel = nivel_para(evento.event_type)
        nivel = NivelAutonomia(aplicar_kill_switch_bloqueio(int(nivel)))
        registro.nivel_autonomia = int(nivel)
        registro = self._transicionar(registro, EstadoExecucao.CLASSIFIED)
        self._emitir('evento_classificado_replay', event_id=event_id, nivel=nivel.name)

        if nivel != NivelAutonomia.EXECUTE_SAFE:
            registro = self._transicionar(registro, EstadoExecucao.WAITING_GATE)
            registro.resultado = f'replay: gate humano -- nivel {nivel.name}'
            self._repo.salvar(registro)
            self._emitir('gate_humano_replay', event_id=event_id, nivel=nivel.name)
            return registro

        # Executar a ação
        acao = self._acoes.get(evento.event_type.value)
        if acao is None:
            # Ação sumiu -- gate por omissão
            registro = self._transicionar(registro, EstadoExecucao.WAITING_GATE)
            registro.resultado = 'replay: acao ausente -- gate por omissao'
            self._repo.salvar(registro)
            self._emitir('gate_por_acao_ausente_replay', event_id=event_id)
            return registro

        # Reexecutar com _executar_e_registrar
        return self._executar_e_registrar(registro, evento, acao)
