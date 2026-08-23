"""
Observabilidade minima do motor -- sem instalar stack pesada (Prometheus,
OpenTelemetry etc.). Log estruturado em JSON por linha (stdout -- CI e
sessao ja capturam isso) + contadores em memoria para o processo atual.

Nunca loga payload sensivel inteiro -- so os campos passados
explicitamente pelo motor (event_id, tipo, nivel, tentativa...), nunca
o Evento inteiro nem excecoes cruas.
"""
from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from typing import Any, Dict

_logger = logging.getLogger('magnata_os.orquestrador')
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter('%(message)s'))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


class Observador:
    """Uma instancia por execucao do motor -- nunca compartilhada entre
    processos (cada CI run/sessao tem a sua)."""

    def __init__(self) -> None:
        self.contadores: Counter = Counter()

    def __call__(self, nome: str, campos: Dict[str, Any]) -> None:
        self.contadores[nome] += 1
        registro = {
            'evento_observabilidade': nome,
            **{
                k: (v if isinstance(v, (str, int, float, bool)) or v is None else str(v))
                for k, v in campos.items()
            },
        }
        _logger.info(json.dumps(registro, ensure_ascii=False))

    def resumo(self) -> Dict[str, int]:
        return dict(self.contadores)
