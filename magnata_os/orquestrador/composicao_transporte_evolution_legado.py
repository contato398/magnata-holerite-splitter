"""Composição canônica de `TransporteEvolutionLegado` a partir do
cliente Evolution extraído (missão "IMPLEMENTAÇÃO LOCAL CONTROLADA —
EXTRAÇÃO EVOLUTION + CANÁRIO NOMINAL V1").

Único ponto do repositório autorizado a construir
`TransporteEvolutionLegado` com as callables reais -- nunca duplica o
cliente HTTP, nunca reimplementa autenticação/payload (usa
`magnata_os.orquestrador.adapters.evolution_cliente_legado`, extraído
mecanicamente de `app.py`, por referência).

Este módulo NUNCA decide sozinho se o transporte real deve ser usado
-- essa decisão continua sendo exclusivamente de
`ciclo_producao_v1.compor_porta_execucao`/`autorizacao_transporte_real.
transporte_real_habilitado` (as três barreiras). Quem quiser o
transporte real sempre passa o resultado de
`compor_transporte_evolution_real()` como `transporte_evolution` para
`compor_porta_execucao(autorizar_transporte_real=True,
transporte_evolution=...)` -- nunca instancia `ExecutorEvolutionLegado`
diretamente."""
from __future__ import annotations

from .adapters.evolution_cliente_legado import (
    _evolution_enviar_documento,
    _evolution_enviar_texto,
    _evolution_enviar_video,
)
from .adapters.transporte_evolution_legado import TransporteEvolutionLegado


def compor_transporte_evolution_real() -> TransporteEvolutionLegado:
    """Constrói `TransporteEvolutionLegado` com as 3 callables reais do
    cliente Evolution extraído -- puro (nenhuma chamada de rede
    acontece aqui, só composição). Não importa `app.py`, Flask, sessão
    ou Airtable."""
    return TransporteEvolutionLegado(
        enviar_texto_legado=_evolution_enviar_texto,
        enviar_video_legado=_evolution_enviar_video,
        enviar_documento_legado=_evolution_enviar_documento,
    )
