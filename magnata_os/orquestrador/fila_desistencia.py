"""
Fila de desistencia (Dead-Letter Queue) do Orquestrador.

Eventos que falharam permanentemente (apos retentativas esgotadas,
ou erros nao-retentaveis) vao para a fila de desistencia:

- Append-only (nunca apaga, nunca edita)
- Acompanhada de motivo, tentativas, e ultimo erro
- Isolada do fluxo principal (nao bloqueia processamento)
- Consultavel para auditoria, retry manual, investigacao

Sem persistencia pesada -- usa repositorio_execucoes como fonte.
Quem quer recuperar um evento da DLQ replica em memoria e retenta.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import List, Optional

from .eventos import EstadoExecucao
from .repositorio_execucoes import RegistroExecucao


@dataclasses.dataclass(frozen=True)
class ItemFilaDesistencia:
    """Um evento que falhou permanentemente e saiu do fluxo."""

    event_id: str
    event_type: str
    tentativas_consumidas: int
    ultimo_erro_classe: Optional[str]
    ultimo_erro_at: Optional[datetime]
    resultado_final: str
    registrado_em: datetime


class FilaDesistenciaEmMemoria:
    """Fila em memoria -- sem disco, para teste.

    Mesmo padrao de RepositorioExecucoesEmMemoria."""

    def __init__(self) -> None:
        self._items: List[ItemFilaDesistencia] = []

    def registrar(self, item: ItemFilaDesistencia) -> None:
        """Append um item a fila (nunca sobrescreve)."""
        self._items.append(item)

    def listar_todos(self) -> List[ItemFilaDesistencia]:
        """Retorna todos os itens da DLQ em ordem de chegada."""
        return list(self._items)

    def listar_por_event_type(self, event_type: str) -> List[ItemFilaDesistencia]:
        """Filtra por tipo de evento."""
        return [item for item in self._items if item.event_type == event_type]


def extrair_para_fila_desistencia(
    registro: RegistroExecucao,
) -> Optional[ItemFilaDesistencia]:
    """Extrai um evento de FAILED_FINAL para a fila de desistencia.

    Retorna None se estado nao e FAILED_FINAL (nao e desistencia)."""
    if registro.estado != EstadoExecucao.FAILED_FINAL:
        return None

    return ItemFilaDesistencia(
        event_id=registro.event_id,
        event_type=registro.event_type,
        tentativas_consumidas=registro.attempt,
        ultimo_erro_classe=registro.last_error_classe,
        ultimo_erro_at=registro.last_error_at,
        resultado_final=registro.resultado or 'desconhecido',
        registrado_em=datetime.now(timezone.utc),
    )
