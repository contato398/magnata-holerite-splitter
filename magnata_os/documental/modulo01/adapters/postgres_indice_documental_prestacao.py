"""Adapter PostgreSQL do índice documental da Prestação (J3).

Implementa, sobre a tabela `indice_documental_prestacao` (migration
`migrations/0011_criar_tabela_indice_documental_prestacao.sql` -- NÃO
aplicada por este módulo), o mesmo contrato do
`InventarioPrestacaoEmMemoria`:

- leitura: `listar(cliente, competencia)` -> `ItemInventarioPrestacao`
  (Protocol `FonteInventarioPrestacao`), consumida pela localização via
  `FonteCandidatosDocumentoInventarioInterna`;
- escrita: `adicionar_muitos(itens)` -> quantos foram NOVOS, consumida
  pelo produtor `_alimentar_indice_documental` da composição da
  Prestação.

DB-API 2.0 (PEP 249), mesmo padrão de `postgres_repositorio.py`: nunca
importa psycopg/psycopg2; qualquer conexão compatível serve. Append-only
e idempotente: `INSERT ... ON CONFLICT DO NOTHING` na identidade lógica
canônica (documento, cliente, colaborador); nunca UPDATE, nunca DELETE.
Uma chamada = uma transação: ou todos os itens entram, ou nenhum
(`rollback()` e a exceção é propagada -- nunca sucesso parcial
silencioso).
"""
from __future__ import annotations

from typing import Iterable, Tuple

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao

_SEM_COLABORADOR = ''


class RepositorioIndiceDocumentalPrestacaoPostgres:
    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def adicionar_muitos(self, itens: Iterable[ItemInventarioPrestacao]) -> int:
        itens = tuple(itens)
        if not itens:
            return 0
        novos = 0
        try:
            with self._conexao.cursor() as cursor:
                for item in itens:
                    cursor.execute(
                        'INSERT INTO indice_documental_prestacao '
                        '(documento_id, cliente_id, colaborador_id, competencia, tipo_documental) '
                        'VALUES (%s, %s, %s, %s, %s) '
                        'ON CONFLICT ON CONSTRAINT uq_indice_documental_prestacao_identidade DO NOTHING '
                        'RETURNING documento_id',
                        (
                            item.documento_id,
                            item.cliente.entidade_id,
                            item.colaborador.entidade_id if item.colaborador else _SEM_COLABORADOR,
                            item.competencia.entidade_id,
                            item.tipo_documental,
                        ),
                    )
                    if cursor.fetchone() is not None:
                        novos += 1
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        return novos

    def adicionar(self, item: ItemInventarioPrestacao) -> bool:
        return self.adicionar_muitos((item,)) == 1

    def listar(
        self, cliente: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> Tuple[ItemInventarioPrestacao, ...]:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                'SELECT documento_id, cliente_id, colaborador_id, competencia, tipo_documental '
                'FROM indice_documental_prestacao '
                'WHERE cliente_id = %s AND competencia = %s '
                'ORDER BY documento_id, colaborador_id',
                (cliente.entidade_id, competencia.entidade_id),
            )
            linhas = cursor.fetchall()
        return tuple(
            ItemInventarioPrestacao(
                documento_id=documento_id,
                tipo_documental=tipo_documental,
                cliente=ReferenciaCanonica('CLIENTE', cliente_id),
                competencia=ReferenciaCanonica('COMPETENCIA', competencia_texto),
                colaborador=(
                    ReferenciaCanonica('COLABORADOR', colaborador_id)
                    if colaborador_id != _SEM_COLABORADOR else None
                ),
            )
            for documento_id, cliente_id, colaborador_id, competencia_texto, tipo_documental in linhas
        )
