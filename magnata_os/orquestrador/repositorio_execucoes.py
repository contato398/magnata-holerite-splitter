"""
Persistencia do ciclo de vida de execucao de eventos -- idempotencia,
audit log, retry.

Preferencia explicita da missao que criou isto: nao provisionar
infraestrutura nova. SQLite local, arquivo unico, zero dependencia nova
(stdlib). Interface (Protocol) pensada para trocar por Postgres depois
sem mudar motor.py -- so o repositorio muda, mesmo padrao ja usado em
magnata_os/documental/modulo01/ (repositorio.py com implementacao em
memoria e Postgres atras da mesma interface).
"""
from __future__ import annotations

import dataclasses
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Protocol

from .eventos import EstadoExecucao


@dataclasses.dataclass
class RegistroExecucao:
    """Registro de auditoria de UM evento processado. Cada transicao de
    estado e persistida via RepositorioExecucoes.salvar -- nunca
    sobrescrita em silencio (quem quiser o historico completo consulta
    o audit log append-only, nao este registro, que so guarda o estado
    mais recente por event_id).

    Adicionalmente rastreia replays manuais (Point 3 da Missão):
    - evento_json: Evento serializado (para replay)
    - manualmente_reiniciado_por: Quem pediu o replay (provenance)
    - manualmente_reiniciado_em: Quando foi solicitado
    - motivo_reinicio_manual: Por que foi reiniciado
    """

    event_id: str
    event_type: str
    estado: EstadoExecucao
    nivel_autonomia: int
    acao: str
    resultado: Optional[str]
    evidencia: Optional[str]
    attempt: int
    next_retry_at: Optional[datetime]
    last_error_classe: Optional[str]
    last_error_at: Optional[datetime]
    criado_em: datetime
    atualizado_em: datetime
    evento_json: Optional[str] = None  # Evento serializado para replay
    manualmente_reiniciado_por: Optional[str] = None  # Quem pediu replay
    manualmente_reiniciado_em: Optional[datetime] = None  # Quando
    motivo_reinicio_manual: Optional[str] = None  # Por que


class RepositorioExecucoes(Protocol):
    def buscar_por_event_id(self, event_id: str) -> Optional[RegistroExecucao]: ...
    def salvar(self, registro: RegistroExecucao) -> None: ...
    def listar_todos(self) -> List[RegistroExecucao]: ...


class RepositorioExecucoesEmMemoria:
    """Para teste -- sem disco, sem SQLite. Mesmo padrao de
    RepositorioDocumentosEmMemoria (modulo01/repositorio.py)."""

    def __init__(self) -> None:
        self._dados: dict = {}

    def buscar_por_event_id(self, event_id: str) -> Optional[RegistroExecucao]:
        return self._dados.get(event_id)

    def salvar(self, registro: RegistroExecucao) -> None:
        self._dados[registro.event_id] = registro

    def listar_todos(self) -> List[RegistroExecucao]:
        return list(self._dados.values())


_DDL = '''CREATE TABLE IF NOT EXISTS execucoes (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    estado TEXT NOT NULL,
    nivel_autonomia INTEGER NOT NULL,
    acao TEXT NOT NULL,
    resultado TEXT,
    evidencia TEXT,
    attempt INTEGER NOT NULL,
    next_retry_at TEXT,
    last_error_classe TEXT,
    last_error_at TEXT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    evento_json TEXT,
    manualmente_reiniciado_por TEXT,
    manualmente_reiniciado_em TEXT,
    motivo_reinicio_manual TEXT
)'''


class RepositorioExecucoesSQLite:
    """Persistencia real, arquivo local (nunca producao -- o caminho e
    sempre local ao processo que roda o motor: CI efemero ou sessao)."""

    def __init__(self, caminho_db: Path) -> None:
        self._caminho = caminho_db
        caminho_db.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(caminho_db))
        self._conn.execute(_DDL)
        self._conn.commit()

    def buscar_por_event_id(self, event_id: str) -> Optional[RegistroExecucao]:
        cur = self._conn.execute('SELECT * FROM execucoes WHERE event_id = ?', (event_id,))
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        d = dict(zip(cols, row))
        return RegistroExecucao(
            event_id=d['event_id'], event_type=d['event_type'],
            estado=EstadoExecucao(d['estado']), nivel_autonomia=d['nivel_autonomia'],
            acao=d['acao'], resultado=d['resultado'], evidencia=d['evidencia'],
            attempt=d['attempt'],
            next_retry_at=datetime.fromisoformat(d['next_retry_at']) if d['next_retry_at'] else None,
            last_error_classe=d['last_error_classe'],
            last_error_at=datetime.fromisoformat(d['last_error_at']) if d['last_error_at'] else None,
            criado_em=datetime.fromisoformat(d['criado_em']),
            atualizado_em=datetime.fromisoformat(d['atualizado_em']),
            evento_json=d.get('evento_json'),
            manualmente_reiniciado_por=d.get('manualmente_reiniciado_por'),
            manualmente_reiniciado_em=datetime.fromisoformat(d['manualmente_reiniciado_em']) if d.get('manualmente_reiniciado_em') else None,
            motivo_reinicio_manual=d.get('motivo_reinicio_manual'),
        )

    def salvar(self, registro: RegistroExecucao) -> None:
        self._conn.execute(
            '''INSERT INTO execucoes (event_id, event_type, estado, nivel_autonomia, acao,
                resultado, evidencia, attempt, next_retry_at, last_error_classe,
                last_error_at, criado_em, atualizado_em, evento_json,
                manualmente_reiniciado_por, manualmente_reiniciado_em, motivo_reinicio_manual)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(event_id) DO UPDATE SET
                 estado=excluded.estado, resultado=excluded.resultado,
                 evidencia=excluded.evidencia, attempt=excluded.attempt,
                 next_retry_at=excluded.next_retry_at,
                 last_error_classe=excluded.last_error_classe,
                 last_error_at=excluded.last_error_at,
                 atualizado_em=excluded.atualizado_em,
                 evento_json=excluded.evento_json,
                 manualmente_reiniciado_por=excluded.manualmente_reiniciado_por,
                 manualmente_reiniciado_em=excluded.manualmente_reiniciado_em,
                 motivo_reinicio_manual=excluded.motivo_reinicio_manual''',
            (
                registro.event_id, registro.event_type, registro.estado.value,
                registro.nivel_autonomia, registro.acao, registro.resultado,
                registro.evidencia, registro.attempt,
                registro.next_retry_at.isoformat() if registro.next_retry_at else None,
                registro.last_error_classe,
                registro.last_error_at.isoformat() if registro.last_error_at else None,
                registro.criado_em.isoformat(), registro.atualizado_em.isoformat(),
                registro.evento_json,
                registro.manualmente_reiniciado_por,
                registro.manualmente_reiniciado_em.isoformat() if registro.manualmente_reiniciado_em else None,
                registro.motivo_reinicio_manual,
            ),
        )
        self._conn.commit()

    def listar_todos(self) -> List[RegistroExecucao]:
        cur = self._conn.execute('SELECT event_id FROM execucoes')
        return [self.buscar_por_event_id(r[0]) for r in cur.fetchall()]

    def fechar(self) -> None:
        self._conn.close()
