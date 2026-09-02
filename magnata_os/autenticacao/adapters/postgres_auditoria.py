"""Persistência real da trilha `auditoria_operacoes` contra Postgres --
mesmo padrão duck-typed (DB-API 2.0) de `documental/alocacao/adapters/
postgres_alocacao.py`. NUNCA aplicado contra Postgres real nesta
missão fora do job `postgres-real` de CI -- nenhum Postgres provisionado
nesta sessão."""
from __future__ import annotations

from typing import Optional, Tuple

from .sqlite_auditoria import RegistroOperacaoAuditada

_TABELA = 'auditoria_operacoes'


class RepositorioAuditoriaPostgres:
    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def inserir_operacao(
        self, *, operacao_id: str, sujeito_id: Optional[str], email: str, perfil: str,
        operacao: str, referencia_agregado: Optional[str], resultado: str, erro_codigo: Optional[str],
    ) -> None:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'INSERT INTO {_TABELA} '
                '(id, sujeito_id, email, perfil, operacao, referencia_agregado, resultado, erro_codigo) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                (operacao_id, sujeito_id, email, perfil, operacao, referencia_agregado, resultado, erro_codigo),
            )
        self._conexao.commit()

    def listar_por_referencia(self, referencia_agregado: str) -> Tuple[RegistroOperacaoAuditada, ...]:
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT id, sujeito_id, email, perfil, operacao, referencia_agregado, '
                f'resultado, erro_codigo, criado_em FROM {_TABELA} '
                'WHERE referencia_agregado = %s ORDER BY criado_em ASC',
                (referencia_agregado,),
            )
            linhas = cur.fetchall()
        campos = (
            'id', 'sujeito_id', 'email', 'perfil', 'operacao',
            'referencia_agregado', 'resultado', 'erro_codigo', 'criado_em',
        )
        return tuple(RegistroOperacaoAuditada(**dict(zip(campos, linha))) for linha in linhas)
