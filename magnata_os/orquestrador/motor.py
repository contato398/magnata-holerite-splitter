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
from datetime import timedelta
from typing import Callable, Dict, Optional, Tuple

from .classificador_falha import ClasseFalha, classificar
from .eventos import EstadoExecucao, Evento, agora, validar_transicao
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
    ) -> None:
        self._repo = repositorio
        self._acoes = acoes
        self._observador = observador

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

        agora_ = agora()
        registro = existente or RegistroExecucao(
            event_id=evento.event_id, event_type=evento.event_type.value,
            estado=EstadoExecucao.RECEIVED, nivel_autonomia=-1, acao='',
            resultado=None, evidencia=None, attempt=0,
            next_retry_at=None, last_error_classe=None, last_error_at=None,
            criado_em=agora_, atualizado_em=agora_,
        )
        self._emitir('evento_recebido', event_id=evento.event_id, tipo=evento.event_type.value)

        # 2) VALIDACAO -- so chegar aqui ja significa Evento bem formado
        # (Evento.__post_init__ ja validou o envelope na criacao).
        registro = self._transicionar(registro, EstadoExecucao.VALIDATED)

        # 3) CLASSIFICACAO + POLITICA DE AUTONOMIA
        nivel = nivel_para(evento.event_type)
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
        registro.estado = novo_estado
        registro.atualizado_em = agora()
        return registro
