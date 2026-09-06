"""Contrato canonico de decisao humana para gates do Orquestrador, V1 shadow.

Esta camada modela a autorizacao como FATO proprio e append-only, separado do
estado mutavel de execucao. O V1 e deliberadamente in-memory: define contrato,
identidade e invariantes sem migration, Postgres, transporte ou efeito externo.

Regras:
- decisao sempre vinculada ao event_id e preview_id exatos;
- apenas referencias opacas/sanitizadas do ator e da proveniencia;
- mesmo fato e idempotente;
- decisao conflitante para o mesmo event_id/preview_id e recusada;
- nenhuma transicao de EstadoExecucao e realizada aqui;
- nenhuma autorizacao implica envio por si so.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Protocol

from .eventos import EstadoExecucao, TipoEvento
from .repositorio_execucoes import RepositorioExecucoes


class DecisaoGate(str, Enum):
    AUTORIZADO = 'AUTORIZADO'
    RECUSADO = 'RECUSADO'


class AutorizacaoGateError(ValueError):
    """Decisao de gate invalida ou incompatível com o estado observado."""


class ConflitoDecisaoGateError(AutorizacaoGateError):
    """O mesmo gate ja possui decisao final diferente."""


@dataclasses.dataclass(frozen=True)
class RegistroAutorizacaoGate:
    autorizacao_id: str
    event_id: str
    preview_id: str
    decisao: DecisaoGate
    ator_referencia: str
    registrado_em: datetime
    proveniencia: str

    def __post_init__(self) -> None:
        for campo, valor in (
            ('autorizacao_id', self.autorizacao_id),
            ('event_id', self.event_id),
            ('preview_id', self.preview_id),
            ('ator_referencia', self.ator_referencia),
            ('proveniencia', self.proveniencia),
        ):
            if not isinstance(valor, str) or not valor.strip():
                raise AutorizacaoGateError(f'{campo} deve ser texto nao vazio')
            if len(valor) > 500:
                raise AutorizacaoGateError(f'{campo} excede limite de referencia sanitizada')
        if self.registrado_em.tzinfo is None:
            raise AutorizacaoGateError('registrado_em deve possuir timezone')


class RepositorioAutorizacoesGate(Protocol):
    def registrar_se_novo(self, registro: RegistroAutorizacaoGate) -> bool: ...
    def buscar(self, event_id: str, preview_id: str) -> Optional[RegistroAutorizacaoGate]: ...
    def listar_por_evento(self, event_id: str) -> List[RegistroAutorizacaoGate]: ...


class RepositorioAutorizacoesGateEmMemoria:
    """Implementacao V1 para prova do contrato, sem persistencia externa."""

    def __init__(self) -> None:
        self._dados: dict[tuple[str, str], RegistroAutorizacaoGate] = {}
        self._lock = threading.Lock()

    def registrar_se_novo(self, registro: RegistroAutorizacaoGate) -> bool:
        chave = (registro.event_id, registro.preview_id)
        with self._lock:
            existente = self._dados.get(chave)
            if existente is None:
                self._dados[chave] = registro
                return True
            if existente == registro:
                return False
            if existente.decisao != registro.decisao:
                raise ConflitoDecisaoGateError(
                    'gate ja possui decisao final diferente para esta previa'
                )
            # Mesma decisao com metadados diferentes nao sobrescreve o fato original.
            return False

    def buscar(self, event_id: str, preview_id: str) -> Optional[RegistroAutorizacaoGate]:
        return self._dados.get((event_id, preview_id))

    def listar_por_evento(self, event_id: str) -> List[RegistroAutorizacaoGate]:
        return [r for (eid, _), r in self._dados.items() if eid == event_id]


def _id_autorizacao(
    *, event_id: str, preview_id: str, decisao: DecisaoGate, ator_referencia: str,
) -> str:
    payload = json.dumps(
        {
            'event_id': event_id,
            'preview_id': preview_id,
            'decisao': decisao.value,
            'ator_referencia': ator_referencia,
        },
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def registrar_decisao_gate_shadow(
    *,
    repositorio_execucoes: RepositorioExecucoes,
    repositorio_autorizacoes: RepositorioAutorizacoesGate,
    event_id: str,
    preview_id: str,
    decisao: DecisaoGate,
    ator_referencia: str,
    proveniencia: str,
    instante: datetime | None = None,
) -> RegistroAutorizacaoGate:
    """Registra o fato humano sem liberar nem reprocessar o evento."""
    execucao = repositorio_execucoes.buscar_por_event_id(event_id)
    if execucao is None:
        raise AutorizacaoGateError('evento nao encontrado no repositorio de execucoes')
    if execucao.event_type != TipoEvento.COMUNICACAO_SOLICITADA.value:
        raise AutorizacaoGateError('evento nao corresponde a COMUNICACAO_SOLICITADA')
    if execucao.estado != EstadoExecucao.WAITING_GATE:
        raise AutorizacaoGateError(
            f'evento deve estar em WAITING_GATE; estado atual {execucao.estado.value}'
        )

    preview = str(preview_id or '').strip()
    ator = str(ator_referencia or '').strip()
    origem = str(proveniencia or '').strip()
    if not preview or not ator or not origem:
        raise AutorizacaoGateError('preview_id, ator_referencia e proveniencia sao obrigatorios')

    quando = instante or datetime.now(timezone.utc)
    registro = RegistroAutorizacaoGate(
        autorizacao_id=_id_autorizacao(
            event_id=event_id,
            preview_id=preview,
            decisao=decisao,
            ator_referencia=ator,
        ),
        event_id=event_id,
        preview_id=preview,
        decisao=decisao,
        ator_referencia=ator,
        registrado_em=quando,
        proveniencia=origem,
    )
    repositorio_autorizacoes.registrar_se_novo(registro)
    return repositorio_autorizacoes.buscar(event_id, preview) or registro
