"""Persistência real, duravel e independente de provedor -- mesmo
padrão de `magnata_os.orquestrador.repositorio_execucoes_postgres.
RepositorioExecucoesPostgres`: adapter duck-typed contra DB-API 2.0
(`conexao.cursor()`, `%s` como placeholder), nunca importa `psycopg2`
por nome (domínio/adapter aqui não sabem qual driver concreto foi
injetado -- ver `magnata_os/CLAUDE.md`, "todo serviço externo entra por
adapter").

NUNCA aplicado contra Postgres real nesta missão (nenhum Postgres
provisionado nesta sessão) -- validado só contra
`adapters/sqlite_alocacao.py` (mesma lógica, mesmo contrato,
`resolucao.py` compartilhada). A migration canônica
(`migrations/0001_criar_vinculo_trabalhista_e_alocacao.sql`) é a fonte
de verdade do schema; este adapter só executa contra ela quando um
Postgres real for provisionado (gate humano separado)."""
from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

from magnata_os.classificacao.contratos import ReferenciaCanonica, ResolucaoDimensao

from ..resolucao import resolver_unidade_posto_via_alocacao

_TABELA_VINCULO = 'vinculo_trabalhista'
_TABELA_ALOCACAO = 'alocacao'


class RepositorioAlocacaoPostgres:
    """Implementa `FonteUnidadePostoPrestacao` (Protocol já existente,
    `vinculo_unidade_prestacao.py`) sobre Postgres real. A invariante de
    não-sobreposição é imposta PELO BANCO (constraint `EXCLUDE` da
    migration 0001) -- este adapter nunca reimplementa a checagem em
    Python (ao contrário do adapter SQLite, que precisa por não ter
    `EXCLUDE USING gist`)."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    # ── Escrita (mecanismo de captura -- ver Fase 7 do ADR desta
    # missão; nunca chamado com dado real inventado aqui) ────────────────

    def registrar_vinculo(
        self, vinculo_id: str, colaborador_id: str,
        data_admissao: date, data_desligamento: Optional[date] = None,
    ) -> None:
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {_TABELA_VINCULO} '
                    '(id, colaborador_id, data_admissao, data_desligamento) '
                    'VALUES (%s, %s, %s, %s)',
                    (vinculo_id, colaborador_id, data_admissao, data_desligamento),
                )
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise

    def registrar_alocacao(
        self, alocacao_id: str, vinculo_trabalhista_id: str, posto_id: str,
        vigente_de: date, vigente_ate: Optional[date] = None,
    ) -> None:
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {_TABELA_ALOCACAO} '
                    '(id, vinculo_trabalhista_id, posto_id, vigente_de, vigente_ate) '
                    'VALUES (%s, %s, %s, %s, %s)',
                    (alocacao_id, vinculo_trabalhista_id, posto_id, vigente_de, vigente_ate),
                )
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise

    # ── Leitura temporal (mesmo par de consultas do adapter SQLite --
    # overlap expresso em SQL puro, equivalente ao `daterange(...) &&`
    # da migration, sem depender de sintaxe específica de versão) ───────

    def vinculos_vigentes_em(self, colaborador_id: str, data_inicio: date, data_fim: date) -> Tuple[str, ...]:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'SELECT id FROM {_TABELA_VINCULO} '
                'WHERE colaborador_id = %s '
                'AND data_admissao <= %s '
                'AND (data_desligamento IS NULL OR data_desligamento >= %s) '
                'ORDER BY id',
                (colaborador_id, data_fim, data_inicio),
            )
            linhas = cursor.fetchall()
        return tuple(linha[0] for linha in linhas)

    def postos_vigentes_em(self, vinculo_trabalhista_id: str, data_inicio: date, data_fim: date) -> Tuple[str, ...]:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'SELECT posto_id FROM {_TABELA_ALOCACAO} '
                'WHERE vinculo_trabalhista_id = %s '
                'AND vigente_de <= %s '
                'AND (vigente_ate IS NULL OR vigente_ate >= %s) '
                'ORDER BY posto_id',
                (vinculo_trabalhista_id, data_fim, data_inicio),
            )
            linhas = cursor.fetchall()
        return tuple(linha[0] for linha in linhas)

    # ── Contrato FonteUnidadePostoPrestacao (já existente, nunca
    # duplicado) ──────────────────────────────────────────────────────

    def resolver_unidade_posto(
        self, colaborador: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> ResolucaoDimensao:
        return resolver_unidade_posto_via_alocacao(
            colaborador, competencia, self.vinculos_vigentes_em, self.postos_vigentes_em,
        )
