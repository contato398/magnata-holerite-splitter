"""
Health check e metricas de saude do motor Orquestrador.

Fornece:
- Estado de saude (verde/amarelo/vermelho)
- Metricas de eventos processados
- Taxa de erro, retry, gate
- Rastreamento de performance

Ha dois modos complementares:
- MonitorSaudemotor: contadores em memoria do processo atual;
- MonitorSaudemotorPersistente: reconstrui a saude a partir do repositorio
  persistente de execucoes, portanto sobrevive a reinicios do processo.

O modo persistente NAO cria uma segunda fonte de verdade: ele deriva o
snapshot dos estados ja gravados pelo RepositorioExecucoes.
"""
from __future__ import annotations

import dataclasses
from collections import Counter
from typing import Dict

from .eventos import EstadoExecucao
from .repositorio_execucoes import RepositorioExecucoes


@dataclasses.dataclass(frozen=True)
class EstadoSaudemotor:
    """Snapshot de saude do motor em um ponto no tempo."""

    eventos_processados_total: int
    eventos_sucesso: int
    eventos_falha_retentavel: int
    eventos_falha_final: int
    eventos_gate_humano: int
    eventos_ignorados: int

    taxa_sucesso: float
    taxa_erro_permanente: float
    taxa_gate_humano: float

    saude: str  # 'VERDE' | 'AMARELO' | 'VERMELHO'

    def resumo_json(self) -> Dict:
        return {
            'eventos_processados_total': self.eventos_processados_total,
            'eventos_sucesso': self.eventos_sucesso,
            'eventos_falha_retentavel': self.eventos_falha_retentavel,
            'eventos_falha_final': self.eventos_falha_final,
            'eventos_gate_humano': self.eventos_gate_humano,
            'eventos_ignorados': self.eventos_ignorados,
            'taxa_sucesso': self.taxa_sucesso,
            'taxa_erro_permanente': self.taxa_erro_permanente,
            'taxa_gate_humano': self.taxa_gate_humano,
            'saude': self.saude,
        }


class MonitorSaudemotor:
    """Monitor em memoria do processo atual."""

    def __init__(self) -> None:
        self._contadores: Counter = Counter()

    def registrar_evento_estado(self, estado: EstadoExecucao) -> None:
        self._contadores['total'] += 1

        if estado == EstadoExecucao.SUCCEEDED:
            self._contadores['sucesso'] += 1
        elif estado == EstadoExecucao.FAILED_RETRYABLE:
            self._contadores['falha_retentavel'] += 1
        elif estado == EstadoExecucao.FAILED_FINAL:
            self._contadores['falha_final'] += 1
        elif estado == EstadoExecucao.WAITING_GATE:
            self._contadores['gate_humano'] += 1
        elif estado == EstadoExecucao.IGNORED:
            self._contadores['ignorado'] += 1

    def obter_saude(self) -> EstadoSaudemotor:
        total = self._contadores.get('total', 0)

        if total == 0:
            return EstadoSaudemotor(
                eventos_processados_total=0,
                eventos_sucesso=0,
                eventos_falha_retentavel=0,
                eventos_falha_final=0,
                eventos_gate_humano=0,
                eventos_ignorados=0,
                taxa_sucesso=0.0,
                taxa_erro_permanente=0.0,
                taxa_gate_humano=0.0,
                saude='VERDE',
            )

        sucesso = self._contadores.get('sucesso', 0)
        falha_retentavel = self._contadores.get('falha_retentavel', 0)
        falha_final = self._contadores.get('falha_final', 0)
        gate = self._contadores.get('gate_humano', 0)
        ignorado = self._contadores.get('ignorado', 0)

        taxa_sucesso = sucesso / total
        taxa_erro_permanente = falha_final / total
        taxa_gate = gate / total

        if taxa_erro_permanente > 0.3:
            saude = 'VERMELHO'
        elif taxa_sucesso < 0.6:
            saude = 'AMARELO'
        else:
            saude = 'VERDE'

        return EstadoSaudemotor(
            eventos_processados_total=total,
            eventos_sucesso=sucesso,
            eventos_falha_retentavel=falha_retentavel,
            eventos_falha_final=falha_final,
            eventos_gate_humano=gate,
            eventos_ignorados=ignorado,
            taxa_sucesso=taxa_sucesso,
            taxa_erro_permanente=taxa_erro_permanente,
            taxa_gate_humano=taxa_gate,
            saude=saude,
        )

    def resetar(self) -> None:
        self._contadores.clear()


class MonitorSaudemotorPersistente:
    """Health derivado do estado persistido de execucoes.

    Em vez de manter contadores paralelos, cada leitura reconstroi o
    snapshot a partir de ``RepositorioExecucoes.listar_todos()``. Assim:

    - reiniciar o processo nao zera a saude;
    - SQLite hoje e Postgres no futuro podem usar a mesma interface;
    - um evento que passou por retry e terminou em sucesso conta uma vez,
      pelo seu estado atual, evitando inflar metricas por transicoes;
    - o repositorio de execucoes continua sendo a fonte de verdade.
    """

    def __init__(self, repositorio: RepositorioExecucoes) -> None:
        self._repositorio = repositorio

    def obter_saude(self) -> EstadoSaudemotor:
        monitor = MonitorSaudemotor()
        for registro in self._repositorio.listar_todos():
            if registro is not None:
                monitor.registrar_evento_estado(registro.estado)
        return monitor.obter_saude()
