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
    mais recente por event_id)."""

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
    atualizado_em TEXT NOT NULL
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
        )

    def salvar(self, registro: RegistroExecucao) -> None:
        self._conn.execute(
            '''INSERT INTO execucoes (event_id, event_type, estado, nivel_autonomia, acao,
                resultado, evidencia, attempt, next_retry_at, last_error_classe,
                last_error_at, criado_em, atualizado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(event_id) DO UPDATE SET
                 estado=excluded.estado, resultado=excluded.resultado,
                 evidencia=excluded.evidencia, attempt=excluded.attempt,
                 next_retry_at=excluded.next_retry_at,
                 last_error_classe=excluded.last_error_classe,
                 last_error_at=excluded.last_error_at,
                 atualizado_em=excluded.atualizado_em''',
            (
                registro.event_id, registro.event_type, registro.estado.value,
                registro.nivel_autonomia, registro.acao, registro.resultado,
                registro.evidencia, registro.attempt,
                registro.next_retry_at.isoformat() if registro.next_retry_at else None,
                registro.last_error_classe,
                registro.last_error_at.isoformat() if registro.last_error_at else None,
                registro.criado_em.isoformat(), registro.atualizado_em.isoformat(),
            ),
        )
        self._conn.commit()

    def listar_todos(self) -> List[RegistroExecucao]:
        cur = self._conn.execute('SELECT event_id FROM execucoes')
        return [self.buscar_por_event_id(r[0]) for r in cur.fetchall()]

    def fechar(self) -> None:
        self._conn.close()
