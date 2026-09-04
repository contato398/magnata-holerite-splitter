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

import contextlib
from datetime import date
from typing import Optional, Tuple

from magnata_os.classificacao.contratos import ReferenciaCanonica, ResolucaoDimensao

from ..resolucao import resolver_unidade_posto_via_alocacao
from ..temporal import RegistroAlocacao, RegistroVinculo

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
        # Missão "REVISÃO OBRIGATÓRIA PR #114 -- ATOMICIDADE DA
        # TRANSFERÊNCIA": ver docstring de `transacao()` abaixo.
        self._em_transacao = False

    @contextlib.contextmanager
    def transacao(self):
        """Contexto transacional REAL -- tudo-ou-nada. Reaproveita a
        MESMA conexão já existente (nenhum repositório/motor/schema
        novo); só suspende o commit/rollback POR-CHAMADA dos métodos de
        escrita enquanto o bloco `with` está ativo, e faz 1 único
        commit (sucesso) ou 1 único rollback (qualquer exceção) ao
        final. Uso pretendido: `captura.aplicar_transferencia`, que
        precisa que "fechar A" e "abrir B" sejam atômicos -- nunca A
        fechada sem B aberta."""
        if self._em_transacao:
            raise RuntimeError('transacao aninhada nao suportada')
        self._em_transacao = True
        try:
            yield self
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        finally:
            self._em_transacao = False

    @contextlib.contextmanager
    def _escrita(self):
        """Envolve 1 escrita individual: fora de uma `transacao()`,
        continua se autoconfirmando sozinha (comportamento já testado
        por todos os testes pré-existentes); dentro de uma
        `transacao()`, deixa o commit/rollback inteiramente a cargo do
        escopo externo -- nunca os dois níveis competindo pela mesma
        conexão."""
        try:
            yield
            if not self._em_transacao:
                self._conexao.commit()
        except Exception:
            if not self._em_transacao:
                self._conexao.rollback()
            raise

    # ── Escrita (mecanismo de captura -- ver Fase 7 do ADR desta
    # missão; nunca chamado com dado real inventado aqui) ────────────────

    def registrar_vinculo(
        self, vinculo_id: str, colaborador_id: str,
        data_admissao: date, data_desligamento: Optional[date] = None,
    ) -> None:
        with self._escrita():
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {_TABELA_VINCULO} '
                    '(id, colaborador_id, data_admissao, data_desligamento) '
                    'VALUES (%s, %s, %s, %s)',
                    (vinculo_id, colaborador_id, data_admissao, data_desligamento),
                )

    def registrar_alocacao(
        self, alocacao_id: str, vinculo_trabalhista_id: str, posto_id: str,
        vigente_de: date, vigente_ate: Optional[date] = None,
    ) -> None:
        with self._escrita():
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {_TABELA_ALOCACAO} '
                    '(id, vinculo_trabalhista_id, posto_id, vigente_de, vigente_ate) '
                    'VALUES (%s, %s, %s, %s, %s)',
                    (alocacao_id, vinculo_trabalhista_id, posto_id, vigente_de, vigente_ate),
                )

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

    # ── Consulta/fechamento (missão "CAPTURA AUTOMÁTICA DE VÍNCULO E
    # ALOCAÇÃO V1") -- extensão mínima, mesmo schema, sem migration ────

    def vinculo_mais_recente_de(self, colaborador_id: str):
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT id, colaborador_id, data_admissao, data_desligamento '
                f'FROM {_TABELA_VINCULO} WHERE colaborador_id = %s '
                'ORDER BY data_admissao DESC LIMIT 1',
                (colaborador_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return RegistroVinculo(id=row[0], colaborador_id=row[1], data_admissao=row[2], data_desligamento=row[3])

    def encerrar_vinculo(self, colaborador_id: str, data_desligamento) -> None:
        with self._escrita():
            with self._conexao.cursor() as cur:
                cur.execute(
                    f'UPDATE {_TABELA_VINCULO} SET data_desligamento = %s '
                    'WHERE colaborador_id = %s AND data_desligamento IS NULL',
                    (data_desligamento, colaborador_id),
                )

    def alocacao_mais_recente_de(self, vinculo_trabalhista_id: str, posto_id: str):
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT id, vinculo_trabalhista_id, posto_id, vigente_de, vigente_ate '
                f'FROM {_TABELA_ALOCACAO} WHERE vinculo_trabalhista_id = %s AND posto_id = %s '
                'ORDER BY vigente_de DESC LIMIT 1',
                (vinculo_trabalhista_id, posto_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return RegistroAlocacao(
            id=row[0], vinculo_trabalhista_id=row[1], posto_id=row[2],
            vigente_de=row[3], vigente_ate=row[4],
        )

    def encerrar_alocacao(self, vinculo_trabalhista_id: str, posto_id: str, vigente_ate) -> None:
        with self._escrita():
            with self._conexao.cursor() as cur:
                cur.execute(
                    f'UPDATE {_TABELA_ALOCACAO} SET vigente_ate = %s '
                    'WHERE vinculo_trabalhista_id = %s AND posto_id = %s AND vigente_ate IS NULL',
                    (vigente_ate, vinculo_trabalhista_id, posto_id),
                )

    # ── Leitura histórica com clientes (missão "FUNDAÇÃO TEMPORAL
    # POSTO ↔ CLIENTE V1") ──────────────────────────────────────────────

    def listar_alocacoes_com_clientes_para_colaborador(
        self, colaborador_id: str, data_inicio, data_fim,
    ) -> Tuple:
        """Retorna TODAS as alocações históricas com clientes associados
        (via interseção temporal com vigencia_cliente_por_posto).

        Garantias:
          1. Colaborador DEVE ter vínculo aberto durante [data_inicio, data_fim]
          2. Alocação (colaborador ao posto) intersecta [data_inicio, data_fim]
          3. Relação posto→cliente PODE existir em [data_inicio, data_fim]
          4. ALOCAÇÃO E VIGÊNCIA_CLIENTE_POR_POSTO DEVEM INTERSECTAR ENTRE SI
             (não basta intersectar a janela consultada separadamente)
          5. Ausência de relação histórica NÃO fabrica cliente (LEFT JOIN + NULL)
          6. Múltiplos clientes legítimos aparecem como rows separadas
          7. Lacunas temporais (períodos sem cliente comprovado) retornam NULL
          8. Ordenação: determinística (posto_id, cliente_id, data)
        """
        from ..temporal import TuplaAlocacaoComClientes

        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'''
                SELECT
                    v.id,
                    v.colaborador_id,
                    a.id,
                    a.posto_id,
                    vc.cliente_id,
                    a.vigente_de,
                    a.vigente_ate,
                    vc.vigente_de,
                    vc.vigente_ate
                FROM {_TABELA_VINCULO} v
                INNER JOIN {_TABELA_ALOCACAO} a
                    ON a.vinculo_trabalhista_id = v.id
                LEFT JOIN vigencia_cliente_por_posto vc
                    ON a.posto_id = vc.posto_id
                    AND vc.vigente_de <= %s
                    AND (vc.vigente_ate IS NULL OR vc.vigente_ate >= %s)
                    AND (vc.vigente_ate IS NULL OR a.vigente_de <= vc.vigente_ate)
                    AND (a.vigente_ate IS NULL OR vc.vigente_de <= a.vigente_ate)
                WHERE v.colaborador_id = %s
                AND v.data_admissao <= %s
                AND (v.data_desligamento IS NULL OR v.data_desligamento >= %s)
                AND a.vigente_de <= %s
                AND (a.vigente_ate IS NULL OR a.vigente_ate >= %s)
                ORDER BY a.posto_id, vc.cliente_id, a.vigente_de ASC
                ''',
                (data_fim, data_inicio,  # vc temporal filter (janela)
                 colaborador_id,          # v.colaborador_id
                 data_fim, data_inicio,   # v temporal filter
                 data_fim, data_inicio),  # a temporal filter
            )
            linhas = cursor.fetchall()

        return tuple(
            TuplaAlocacaoComClientes(
                vinculo_id=linha[0],
                colaborador_id=linha[1],
                alocacao_id=linha[2],
                posto_id=linha[3],
                cliente_id=linha[4],  # NULL se nenhuma relação intersecta com alocacao
                alocacao_vigente_de=linha[5],
                alocacao_vigente_ate=linha[6],
                cliente_vigente_de=linha[7],
                cliente_vigente_ate=linha[8],
            )
            for linha in linhas
        )

    # ── Contrato FonteUnidadePostoPrestacao (já existente, nunca
    # duplicado) ──────────────────────────────────────────────────────

    def resolver_unidade_posto(
        self, colaborador: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> ResolucaoDimensao:
        return resolver_unidade_posto_via_alocacao(
            colaborador, competencia, self.vinculos_vigentes_em, self.postos_vigentes_em,
        )
