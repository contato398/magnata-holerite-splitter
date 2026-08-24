"""
Health check e metricas de saude do motor Orquestrador.

Fornece:
- Estado de saude (verde/amarelo/vermelho)
- Metricas de eventos processados
- Taxa de erro, retry, gate
- Rastreamento de performance

Sem estatefulidade persistida -- metricas em memoria do processo atual.
Para persistir, integra com Observador e observabilidade.py.
"""
from __future__ import annotations

import dataclasses
from collections import Counter
from typing import Dict, Optional

from .eventos import EstadoExecucao


@dataclasses.dataclass(frozen=True)
class EstadoSaudemotor:
    """Snapshot de saude do motor em um ponto no tempo."""

    eventos_processados_total: int
    eventos_sucesso: int
    eventos_falha_retentavel: int
    eventos_falha_final: int
    eventos_gate_humano: int
    eventos_ignorados: int

    # Taxas (0-1)
    taxa_sucesso: float  # sucesso / processados
    taxa_erro_permanente: float  # falha_final / processados
    taxa_gate_humano: float  # gate / processados

    # Estado de saude (enum-like)
    saude: str  # 'VERDE' | 'AMARELO' | 'VERMELHO'

    def resumo_json(self) -> Dict:
        """Serializa para JSON/dict."""
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
    """Monitor de saude do motor -- atualizado por Observador."""

    def __init__(self) -> None:
        self._contadores: Counter = Counter()

    def registrar_evento_estado(self, estado: EstadoExecucao) -> None:
        """Registra transicao de estado de um evento."""
        # Incrementa contador geral
        self._contadores['total'] += 1

        # Incrementa por estado
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
        """Calcula snapshot de saude atual."""
        total = self._contadores.get('total', 0)

        if total == 0:
            # Nenhum evento processado ainda
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
                saude='VERDE',  # Sem dados ainda e saude "OK"
            )

        sucesso = self._contadores.get('sucesso', 0)
        falha_retentavel = self._contadores.get('falha_retentavel', 0)
        falha_final = self._contadores.get('falha_final', 0)
        gate = self._contadores.get('gate_humano', 0)
        ignorado = self._contadores.get('ignorado', 0)

        taxa_sucesso = sucesso / total if total > 0 else 0.0
        taxa_erro_permanente = falha_final / total if total > 0 else 0.0
        taxa_gate = gate / total if total > 0 else 0.0

        # Heuristica simples de saude
        if taxa_erro_permanente > 0.3:
            saude = 'VERMELHO'  # >30% falhas permanentes
        elif taxa_sucesso < 0.6:
            saude = 'AMARELO'  # <60% sucesso
        else:
            saude = 'VERDE'  # Tudo OK

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
        """Reseta contadores (para teste ou novo ciclo)."""
        self._contadores.clear()
