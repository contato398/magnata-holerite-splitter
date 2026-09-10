"""Adaptador PostgreSQL para persistência de execuções de Prestação.

Padrão: DB-API 2.0 puro (sem psycopg2 por nome, só como protocol duck-typed).
Reutiliza padrão já usado em repositorio_execucoes_postgres.py (Orquestrador).
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from magnata_os.classificacao.execucao_prestacao import (
    ExecucaoPrestacao,
    RepositorioExecucoesPrestacao,
)


class RepositorioExecucoesPrestacaoPostgres:
    """Persistência via PostgreSQL em tabela magnata_orquestrador.execucoes_prestacao."""

    def __init__(self, conexao) -> None:
        """conexao: DB-API 2.0 compatible (psycopg ou psycopg2)."""
        self._conexao = conexao

    def criar(self, execucao: ExecucaoPrestacao) -> None:
        """Insere execução nova."""
        sql = """
        INSERT INTO magnata_orquestrador.execucoes_prestacao
        (execucao_prestacao_id, competencia_base, estado, origem,
         criado_em, atualizado_em, concluido_em)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cur = self._conexao.cursor()
        cur.execute(
            sql,
            (
                execucao.execucao_prestacao_id,
                execucao.competencia_base,
                execucao.estado,
                execucao.origem,
                execucao.criado_em,
                execucao.atualizado_em,
                execucao.concluido_em,
            ),
        )
        self._conexao.commit()

    def buscar_por_id(
        self, execucao_prestacao_id: str,
    ) -> Optional[ExecucaoPrestacao]:
        """Consulta execução por ID."""
        sql = """
        SELECT execucao_prestacao_id, competencia_base, estado, origem,
               criado_em, atualizado_em, concluido_em
        FROM magnata_orquestrador.execucoes_prestacao
        WHERE execucao_prestacao_id = %s
        """
        cur = self._conexao.cursor()
        cur.execute(sql, (execucao_prestacao_id,))
        row = cur.fetchone()
        if not row:
            return None
        return ExecucaoPrestacao(
            execucao_prestacao_id=row[0],
            competencia_base=row[1],
            estado=row[2],
            origem=row[3],
            criado_em=row[4],
            atualizado_em=row[5],
            concluido_em=row[6],
        )

    def atualizar_estado(
        self,
        execucao_prestacao_id: str,
        novo_estado: str,
        concluido_em: Optional[datetime] = None,
    ) -> None:
        """Atualiza estado e concluido_em."""
        sql = """
        UPDATE magnata_orquestrador.execucoes_prestacao
        SET estado = %s, concluido_em = %s, atualizado_em = NOW()
        WHERE execucao_prestacao_id = %s
        """
        cur = self._conexao.cursor()
        cur.execute(sql, (novo_estado, concluido_em, execucao_prestacao_id))
        self._conexao.commit()

    def listar_por_competencia(
        self, competencia_base: str,
    ) -> List[ExecucaoPrestacao]:
        """Lista execuções de uma competência."""
        sql = """
        SELECT execucao_prestacao_id, competencia_base, estado, origem,
               criado_em, atualizado_em, concluido_em
        FROM magnata_orquestrador.execucoes_prestacao
        WHERE competencia_base = %s
        ORDER BY criado_em DESC
        """
        cur = self._conexao.cursor()
        cur.execute(sql, (competencia_base,))
        rows = cur.fetchall()
        return [
            ExecucaoPrestacao(
                execucao_prestacao_id=row[0],
                competencia_base=row[1],
                estado=row[2],
                origem=row[3],
                criado_em=row[4],
                atualizado_em=row[5],
                concluido_em=row[6],
            )
            for row in rows
        ]

    def listar_todas(self) -> List[ExecucaoPrestacao]:
        """Lista todas as execuções."""
        sql = """
        SELECT execucao_prestacao_id, competencia_base, estado, origem,
               criado_em, atualizado_em, concluido_em
        FROM magnata_orquestrador.execucoes_prestacao
        ORDER BY criado_em DESC
        """
        cur = self._conexao.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        return [
            ExecucaoPrestacao(
                execucao_prestacao_id=row[0],
                competencia_base=row[1],
                estado=row[2],
                origem=row[3],
                criado_em=row[4],
                atualizado_em=row[5],
                concluido_em=row[6],
            )
            for row in rows
        ]
