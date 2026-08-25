"""
Fila de desistencia (Dead-Letter Queue) do Orquestrador.

Eventos que falharam permanentemente (apos retentativas esgotadas,
ou erros nao-retentaveis) vao para a fila de desistencia:

- Append-only (nunca apaga, nunca edita)
- Acompanhada de motivo, tentativas, e ultimo erro
- Isolada do fluxo principal (nao bloqueia processamento)
- Consultavel para auditoria, retry manual, investigacao

Ha duas representacoes complementares:

- ``FilaDesistenciaEmMemoria`` recebe notificacoes do processo atual;
- ``VisaoFilaDesistenciaPersistente`` reconstroi a fila ativa a partir do
  ``RepositorioExecucoes``, sem tabela, banco ou fonte de verdade paralela.

A visao persistente e deliberadamente somente leitura. Recuperacao continua
passando pelas politicas do Orquestrador; consultar a DLQ nunca dispara replay.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import List, Optional

from .eventos import EstadoExecucao
from .repositorio_execucoes import RegistroExecucao, RepositorioExecucoes


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


class VisaoFilaDesistenciaPersistente:
    """Visao somente leitura dos eventos atualmente em ``FAILED_FINAL``.

    O repositorio de execucoes continua sendo a unica fonte de verdade. Cada
    consulta deriva um snapshot novo, portanto sobrevive a restart e acompanha
    replay manual sem sincronizacao paralela: quando o estado deixa de ser
    ``FAILED_FINAL``, o item deixa a fila *ativa*. O historico append-only da
    transicao permanece em ``RepositorioExecucoes.listar_auditoria``.
    """

    def __init__(self, repositorio: RepositorioExecucoes) -> None:
        self._repositorio = repositorio

    def listar_todos(self) -> List[ItemFilaDesistencia]:
        """Retorna a DLQ ativa em ordem deterministica de entrada."""
        itens = (
            extrair_para_fila_desistencia(
                registro,
                registrado_em=registro.atualizado_em,
            )
            for registro in self._repositorio.listar_todos()
            if registro is not None
        )
        presentes = [item for item in itens if item is not None]
        return sorted(presentes, key=lambda item: (item.registrado_em, item.event_id))

    def listar_por_event_type(self, event_type: str) -> List[ItemFilaDesistencia]:
        """Filtra o snapshot persistente por tipo de evento."""
        return [item for item in self.listar_todos() if item.event_type == event_type]


def extrair_para_fila_desistencia(
    registro: RegistroExecucao,
    registrado_em: Optional[datetime] = None,
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
        registrado_em=registrado_em or datetime.now(timezone.utc),
    )
