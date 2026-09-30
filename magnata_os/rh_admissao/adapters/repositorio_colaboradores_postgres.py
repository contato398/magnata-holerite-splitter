"""Adapter PostgreSQL do Cadastro de Colaborador (`RepositorioColaboradores`).

Implementa, sobre a tabela `rh_admissao_colaboradores` (migration
`magnata_os/rh_admissao/migrations/0001_criar_tabela_colaboradores.sql`
-- NÃO aplicada por este módulo), o contrato `RepositorioColaboradores`
(`magnata_os/rh_admissao/repositorio_colaboradores.py`).

DB-API 2.0 (PEP 249), mesmo padrão de
`documental/modulo01/adapters/postgres_repositorio.py` e
`documental/alocacao/adapters/postgres_alocacao.py`: nunca importa
psycopg/psycopg2 por nome; qualquer conexão compatível serve.

Idempotência: `salvar` é um `INSERT ... ON CONFLICT (colaborador_id) DO
UPDATE` -- a mesma chave (`colaborador_id`) já usada por
`gatilho_admissao.RegistroGatilhoAdmissaoEmMemoria`. Este adapter NUNCA
decide se uma mudança de `local_trabalho` já definido é legítima --
essa regra pertence ao domínio
(`dominio_cadastro_colaborador.aplicar_determinacao_local_trabalho`);
o adapter só grava o que o chamador já validou. Uma chamada = uma
transação: sucesso grava tudo, qualquer exceção reverte (`rollback()`),
nunca sucesso parcial silencioso.
"""
from __future__ import annotations

from typing import Optional, Tuple

from magnata_os.rh_admissao.dominio_cadastro_colaborador import (
    Colaborador,
    SituacaoCadastroColaborador,
)

_TABELA = 'rh_admissao_colaboradores'

_COLUNAS = (
    'colaborador_id', 'cpf', 'nome', 'cargo', 'local_trabalho',
    'situacao_cadastro', 'criado_em', 'atualizado_em',
)


def _linha_para_colaborador(linha) -> Colaborador:
    (colaborador_id, cpf, nome, cargo, local_trabalho,
     situacao_cadastro, criado_em, atualizado_em) = linha
    return Colaborador(
        colaborador_id=colaborador_id,
        cpf=cpf,
        nome=nome,
        cargo=cargo,
        local_trabalho=local_trabalho,
        situacao_cadastro=SituacaoCadastroColaborador(situacao_cadastro),
        criado_em=criado_em,
        atualizado_em=atualizado_em,
    )


class RepositorioColaboradoresPostgres:
    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def salvar(self, colaborador: Colaborador) -> Colaborador:
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {_TABELA} ({", ".join(_COLUNAS)}) '
                    'VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, now()), COALESCE(%s, now())) '
                    'ON CONFLICT (colaborador_id) DO UPDATE SET '
                    'cpf = EXCLUDED.cpf, nome = EXCLUDED.nome, cargo = EXCLUDED.cargo, '
                    'local_trabalho = EXCLUDED.local_trabalho, '
                    'situacao_cadastro = EXCLUDED.situacao_cadastro, '
                    'atualizado_em = EXCLUDED.atualizado_em '
                    f'RETURNING {", ".join(_COLUNAS)}',
                    (
                        colaborador.colaborador_id, colaborador.cpf, colaborador.nome,
                        colaborador.cargo, colaborador.local_trabalho,
                        colaborador.situacao_cadastro.value,
                        colaborador.criado_em, colaborador.atualizado_em,
                    ),
                )
                linha = cursor.fetchone()
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise
        return _linha_para_colaborador(linha)

    def buscar_por_id(self, colaborador_id: str) -> Optional[Colaborador]:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'SELECT {", ".join(_COLUNAS)} FROM {_TABELA} WHERE colaborador_id = %s',
                (colaborador_id,),
            )
            linha = cursor.fetchone()
        return _linha_para_colaborador(linha) if linha is not None else None

    def listar(self) -> Tuple[Colaborador, ...]:
        with self._conexao.cursor() as cursor:
            cursor.execute(f'SELECT {", ".join(_COLUNAS)} FROM {_TABELA} ORDER BY colaborador_id')
            linhas = cursor.fetchall()
        return tuple(_linha_para_colaborador(linha) for linha in linhas)
