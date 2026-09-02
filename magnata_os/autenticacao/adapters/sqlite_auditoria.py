"""Persistência REAL, arquivo local, da trilha `auditoria_operacoes`
(missão "AUTENTICAÇÃO ADMINISTRATIVA COMPARTILHADA V1", FASE 6) --
mesma disciplina de `documental/alocacao/adapters/sqlite_alocacao.py`:
DDL própria, hand-traduzida da migration Postgres canônica, nunca a
mesma fonte. SQLite não impõe append-only por trigger (sem `plpgsql`) --
a garantia de banco fica só no Postgres real; este adapter é para teste
local, nunca produção."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

_DDL = '''CREATE TABLE IF NOT EXISTS auditoria_operacoes (
    id TEXT PRIMARY KEY,
    sujeito_id TEXT,
    email TEXT NOT NULL,
    perfil TEXT NOT NULL,
    operacao TEXT NOT NULL,
    referencia_agregado TEXT,
    resultado TEXT NOT NULL,
    erro_codigo TEXT,
    criado_em TEXT NOT NULL
)'''


class RegistroOperacaoAuditada:
    __slots__ = (
        'id', 'sujeito_id', 'email', 'perfil', 'operacao',
        'referencia_agregado', 'resultado', 'erro_codigo', 'criado_em',
    )

    def __init__(self, **kwargs) -> None:
        for chave in self.__slots__:
            setattr(self, chave, kwargs[chave])


class RepositorioAuditoriaSQLite:
    def __init__(self, caminho_db: Path) -> None:
        self._caminho = caminho_db
        caminho_db.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(caminho_db))
        self._conn.execute(_DDL)
        self._conn.commit()

    def fechar(self) -> None:
        self._conn.close()

    def inserir_operacao(
        self, *, operacao_id: str, sujeito_id: Optional[str], email: str, perfil: str,
        operacao: str, referencia_agregado: Optional[str], resultado: str, erro_codigo: Optional[str],
    ) -> None:
        self._conn.execute(
            'INSERT INTO auditoria_operacoes '
            '(id, sujeito_id, email, perfil, operacao, referencia_agregado, resultado, erro_codigo, criado_em) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (
                operacao_id, sujeito_id, email, perfil, operacao, referencia_agregado,
                resultado, erro_codigo, datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def listar_por_referencia(self, referencia_agregado: str) -> Tuple[RegistroOperacaoAuditada, ...]:
        """Só para teste/consulta -- nenhum caminho de escrita usa
        isto."""
        linhas = self._conn.execute(
            'SELECT id, sujeito_id, email, perfil, operacao, referencia_agregado, '
            'resultado, erro_codigo, criado_em FROM auditoria_operacoes '
            'WHERE referencia_agregado = ? ORDER BY criado_em ASC',
            (referencia_agregado,),
        ).fetchall()
        campos = (
            'id', 'sujeito_id', 'email', 'perfil', 'operacao',
            'referencia_agregado', 'resultado', 'erro_codigo', 'criado_em',
        )
        return tuple(RegistroOperacaoAuditada(**dict(zip(campos, linha))) for linha in linhas)
