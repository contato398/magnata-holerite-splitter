"""Adapter PostgreSQL para `identidade_colaborador.py` (Identidade
Canônica de Colaborador V1).

Escrito contra a interface padronizada DB-API 2.0 (PEP 249), mesmo
padrão de `modulo01/adapters/postgres_repositorio.py` e
`modulo01/adapters/postgres_resolucao_temporal.py` -- nunca importa
psycopg2/psycopg diretamente; qualquer conexão compatível serve (real
ou duplo de teste). A tabela esperada é criada pela migration
`migrations/0003_criar_identidade_colaborador_observada.sql` -- NÃO
aplicada por este módulo, e não aplicada em nenhum banco real por esta
missão.

GATE DE IDEMPOTÊNCIA/CONFLITO: `criar_se_ausente` insere sob a chave
primária composta (`tipo_identificador`, `identificador_hash`); uma
violação de chave primária com `colaborador_id` DIFERENTE do que já
existe é traduzida para `ConflitoIdentidadeColaborador` -- nunca um
`UPDATE`/sobrescrita silenciosa. Reprocessar o MESMO par
(identificador, colaborador_id) -- reexecução idempotente do mesmo
bootstrap -- devolve a linha já existente sem erro."""
from __future__ import annotations

from typing import List, Optional, Tuple

from ..identidade_colaborador import (
    ConflitoIdentidadeColaborador,
    IdentidadeColaboradorObservada,
)

_COLUNAS = (
    'tipo_identificador', 'identificador_hash', 'colaborador_id',
    'origem', 'versao_chave', 'criado_em', 'atualizado_em',
)


def _e_violacao_de_integridade(exc: Exception) -> bool:
    """Mesma detecção duck-typed já usada em `postgres_repositorio.py`/
    `postgres_resolucao_temporal.py` -- nunca duplicar a lógica, só a
    assinatura mínima aqui evita import cruzado desnecessário entre
    adapters irmãos."""
    for classe in type(exc).__mro__:
        if classe.__name__ == 'IntegrityError':
            return True
    return False


def _linha_para_identidade(linha) -> IdentidadeColaboradorObservada:
    (
        tipo_identificador, identificador_hash, colaborador_id,
        origem, versao_chave, criado_em, atualizado_em,
    ) = linha
    return IdentidadeColaboradorObservada(
        tipo_identificador=tipo_identificador, identificador_hash=identificador_hash,
        colaborador_id=colaborador_id, origem=origem, versao_chave=versao_chave,
        criado_em=criado_em, atualizado_em=atualizado_em,
    )


class RepositorioIdentidadeColaboradorPostgres:
    """Implementa `RepositorioIdentidadeColaborador`
    (`identidade_colaborador.py`) contra Postgres real."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def buscar_por_identificador(
        self, tipo_identificador: str, identificador_hash: str,
    ) -> Optional[IdentidadeColaboradorObservada]:
        colunas = ', '.join(_COLUNAS)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM identidade_colaborador_observada '
                f'WHERE tipo_identificador = %s AND identificador_hash = %s',
                (tipo_identificador, identificador_hash),
            )
            linha = cur.fetchone()
        return _linha_para_identidade(linha) if linha else None

    def criar_se_ausente(
        self, identidade: IdentidadeColaboradorObservada,
    ) -> Tuple[IdentidadeColaboradorObservada, bool]:
        """Tenta inserir; se a chave primária já existir, relê a linha
        existente e decide: MESMO colaborador_id -> devolve existente
        (idempotente); colaborador_id DIFERENTE -> `ConflitoIdentidade
        Colaborador`, nunca um UPDATE."""
        existente = self.buscar_por_identificador(
            identidade.tipo_identificador, identidade.identificador_hash,
        )
        if existente is not None:
            if existente.colaborador_id != identidade.colaborador_id:
                raise ConflitoIdentidadeColaborador(
                    existente.colaborador_id, identidade.colaborador_id,
                )
            return existente, False

        try:
            with self._conexao.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO identidade_colaborador_observada ({', '.join(_COLUNAS)})
                    VALUES ({', '.join(['%s'] * len(_COLUNAS))})
                    """,
                    (
                        identidade.tipo_identificador, identidade.identificador_hash,
                        identidade.colaborador_id, identidade.origem, identidade.versao_chave,
                        identidade.criado_em, identidade.atualizado_em,
                    ),
                )
            self._conexao.commit()
            return identidade, True
        except Exception as exc:
            self._conexao.rollback()
            if _e_violacao_de_integridade(exc):
                # Corrida: outra transação inseriu a MESMA chave entre o
                # SELECT acima e este INSERT -- relê e aplica a mesma
                # decisão de conflito/idempotência, nunca assume sucesso.
                existente_apos_corrida = self.buscar_por_identificador(
                    identidade.tipo_identificador, identidade.identificador_hash,
                )
                if existente_apos_corrida is not None:
                    if existente_apos_corrida.colaborador_id != identidade.colaborador_id:
                        raise ConflitoIdentidadeColaborador(
                            existente_apos_corrida.colaborador_id, identidade.colaborador_id,
                        ) from exc
                    return existente_apos_corrida, False
            raise

    def listar_todos(self) -> List[IdentidadeColaboradorObservada]:
        colunas = ', '.join(_COLUNAS)
        with self._conexao.cursor() as cur:
            cur.execute(f'SELECT {colunas} FROM identidade_colaborador_observada ORDER BY criado_em ASC')
            linhas = cur.fetchall()
        return [_linha_para_identidade(l) for l in linhas]
