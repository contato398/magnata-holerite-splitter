"""Persistência REAL, arquivo local (nunca produção -- mesma disciplina
de `magnata_os.orquestrador.repositorio_execucoes.RepositorioExecucoesSQLite`:
"o caminho é sempre local ao processo que roda o motor: CI efêmero ou
sessão"). Usado para validar de verdade o schema/temporalidade desta
missão sem depender de um Postgres real provisionado (não disponível
nesta sessão -- confirmado por erro de driver ausente no baseline da
suíte).

DDL própria, hand-traduzida da migration Postgres canônica
(migrations/0001_criar_vinculo_trabalhista_e_alocacao.sql) -- mesmo
padrão já estabelecido por `repositorio_execucoes.py` (`_DDL`/`_DDL_AUDIT`
para SQLite, mantidas em sincronia manual com a migration Postgres real,
nunca a mesma fonte). Diferença REAL e documentada, nunca escondida:
SQLite não suporta `EXCLUDE USING gist`/`daterange` -- a invariante de
não-sobreposição é imposta EM PYTHON aqui (`temporal.intervalos_se_sobrepoem`),
nunca pelo banco. A fonte de verdade da constraint continua sendo a
migration Postgres; este adapter é só para teste local."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional, Tuple

from magnata_os.classificacao.contratos import ReferenciaCanonica, ResolucaoDimensao

from ..resolucao import resolver_unidade_posto_via_alocacao
from ..temporal import (
    RegistroAlocacao,
    RegistroVinculo,
    SobreposicaoAlocacaoError,
    SobreposicaoVinculoError,
    intervalos_se_sobrepoem,
)

_DDL_VINCULO = '''CREATE TABLE IF NOT EXISTS vinculo_trabalhista (
    id TEXT PRIMARY KEY,
    colaborador_id TEXT NOT NULL,
    data_admissao TEXT NOT NULL,
    data_desligamento TEXT
)'''

_DDL_ALOCACAO = '''CREATE TABLE IF NOT EXISTS alocacao (
    id TEXT PRIMARY KEY,
    vinculo_trabalhista_id TEXT NOT NULL REFERENCES vinculo_trabalhista (id),
    posto_id TEXT NOT NULL,
    vigente_de TEXT NOT NULL,
    vigente_ate TEXT
)'''


def _para_data(texto: Optional[str]) -> Optional[date]:
    return date.fromisoformat(texto) if texto else None


def _para_texto(valor: Optional[date]) -> Optional[str]:
    return valor.isoformat() if valor is not None else None


class RepositorioAlocacaoSQLite:
    """Implementa `FonteUnidadePostoPrestacao` (Protocol já existente,
    `vinculo_unidade_prestacao.py`) sobre SQLite local -- só para teste
    real desta missão, nunca chamado em produção (ver docstring do
    módulo)."""

    def __init__(self, caminho_db: Path) -> None:
        self._caminho = caminho_db
        caminho_db.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(caminho_db))
        self._conn.execute(_DDL_VINCULO)
        self._conn.execute(_DDL_ALOCACAO)
        self._conn.commit()

    def fechar(self) -> None:
        self._conn.close()

    # ── Escrita (mecanismo de captura -- nunca chamado com dado real
    # inventado nesta missão; usado só pelos testes desta missão e como
    # ponto de integração futura, ver Fase 7 do ADR) ─────────────────────

    def registrar_vinculo(
        self, vinculo_id: str, colaborador_id: str,
        data_admissao: date, data_desligamento: Optional[date] = None,
    ) -> None:
        if data_desligamento is not None and data_desligamento < data_admissao:
            raise ValueError('data_desligamento nao pode ser anterior a data_admissao')
        for row in self._conn.execute(
            'SELECT data_admissao, data_desligamento FROM vinculo_trabalhista WHERE colaborador_id = ?',
            (colaborador_id,),
        ):
            existente_inicio, existente_fim = _para_data(row[0]), _para_data(row[1])
            if intervalos_se_sobrepoem(data_admissao, data_desligamento, existente_inicio, existente_fim):
                raise SobreposicaoVinculoError(
                    f'vinculo sobreposto para colaborador_id={colaborador_id}')
        self._conn.execute(
            'INSERT INTO vinculo_trabalhista (id, colaborador_id, data_admissao, data_desligamento) '
            'VALUES (?, ?, ?, ?)',
            (vinculo_id, colaborador_id, _para_texto(data_admissao), _para_texto(data_desligamento)),
        )
        self._conn.commit()

    def registrar_alocacao(
        self, alocacao_id: str, vinculo_trabalhista_id: str, posto_id: str,
        vigente_de: date, vigente_ate: Optional[date] = None,
    ) -> None:
        if vigente_ate is not None and vigente_ate < vigente_de:
            raise ValueError('vigente_ate nao pode ser anterior a vigente_de')
        for row in self._conn.execute(
            'SELECT vigente_de, vigente_ate FROM alocacao '
            'WHERE vinculo_trabalhista_id = ? AND posto_id = ?',
            (vinculo_trabalhista_id, posto_id),
        ):
            existente_inicio, existente_fim = _para_data(row[0]), _para_data(row[1])
            if intervalos_se_sobrepoem(vigente_de, vigente_ate, existente_inicio, existente_fim):
                raise SobreposicaoAlocacaoError(
                    f'alocacao sobreposta para vinculo={vinculo_trabalhista_id} posto={posto_id}')
        self._conn.execute(
            'INSERT INTO alocacao (id, vinculo_trabalhista_id, posto_id, vigente_de, vigente_ate) '
            'VALUES (?, ?, ?, ?, ?)',
            (alocacao_id, vinculo_trabalhista_id, posto_id, _para_texto(vigente_de), _para_texto(vigente_ate)),
        )
        self._conn.commit()

    # ── Leitura temporal (consultas cruas -- testáveis isoladamente) ────

    def vinculos_vigentes_em(self, colaborador_id: str, data_inicio: date, data_fim: date) -> Tuple[str, ...]:
        ids = []
        for row in self._conn.execute(
            'SELECT id, data_admissao, data_desligamento FROM vinculo_trabalhista WHERE colaborador_id = ?',
            (colaborador_id,),
        ):
            inicio, fim = _para_data(row[1]), _para_data(row[2])
            if intervalos_se_sobrepoem(inicio, fim, data_inicio, data_fim):
                ids.append(row[0])
        return tuple(sorted(ids))

    def postos_vigentes_em(self, vinculo_trabalhista_id: str, data_inicio: date, data_fim: date) -> Tuple[str, ...]:
        ids = []
        for row in self._conn.execute(
            'SELECT posto_id, vigente_de, vigente_ate FROM alocacao WHERE vinculo_trabalhista_id = ?',
            (vinculo_trabalhista_id,),
        ):
            inicio, fim = _para_data(row[1]), _para_data(row[2])
            if intervalos_se_sobrepoem(inicio, fim, data_inicio, data_fim):
                ids.append(row[0])
        return tuple(sorted(ids))

    # ── Consulta/fechamento (missão "CAPTURA AUTOMÁTICA DE VÍNCULO E
    # ALOCAÇÃO V1") -- extensão mínima, mesmo schema, sem migration ────

    def vinculo_mais_recente_de(self, colaborador_id: str):
        row = self._conn.execute(
            'SELECT id, colaborador_id, data_admissao, data_desligamento '
            'FROM vinculo_trabalhista WHERE colaborador_id = ? '
            'ORDER BY data_admissao DESC LIMIT 1',
            (colaborador_id,),
        ).fetchone()
        if row is None:
            return None
        return RegistroVinculo(
            id=row[0], colaborador_id=row[1],
            data_admissao=_para_data(row[2]), data_desligamento=_para_data(row[3]),
        )

    def encerrar_vinculo(self, colaborador_id: str, data_desligamento) -> None:
        self._conn.execute(
            'UPDATE vinculo_trabalhista SET data_desligamento = ? '
            'WHERE colaborador_id = ? AND data_desligamento IS NULL',
            (_para_texto(data_desligamento), colaborador_id),
        )
        self._conn.commit()

    def alocacao_mais_recente_de(self, vinculo_trabalhista_id: str, posto_id: str):
        row = self._conn.execute(
            'SELECT id, vinculo_trabalhista_id, posto_id, vigente_de, vigente_ate '
            'FROM alocacao WHERE vinculo_trabalhista_id = ? AND posto_id = ? '
            'ORDER BY vigente_de DESC LIMIT 1',
            (vinculo_trabalhista_id, posto_id),
        ).fetchone()
        if row is None:
            return None
        return RegistroAlocacao(
            id=row[0], vinculo_trabalhista_id=row[1], posto_id=row[2],
            vigente_de=_para_data(row[3]), vigente_ate=_para_data(row[4]),
        )

    def encerrar_alocacao(self, vinculo_trabalhista_id: str, posto_id: str, vigente_ate) -> None:
        self._conn.execute(
            'UPDATE alocacao SET vigente_ate = ? '
            'WHERE vinculo_trabalhista_id = ? AND posto_id = ? AND vigente_ate IS NULL',
            (_para_texto(vigente_ate), vinculo_trabalhista_id, posto_id),
        )
        self._conn.commit()

    # ── Contrato FonteUnidadePostoPrestacao (já existente, nunca
    # duplicado) ──────────────────────────────────────────────────────

    def resolver_unidade_posto(
        self, colaborador: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> ResolucaoDimensao:
        return resolver_unidade_posto_via_alocacao(
            colaborador, competencia, self.vinculos_vigentes_em, self.postos_vigentes_em,
        )
