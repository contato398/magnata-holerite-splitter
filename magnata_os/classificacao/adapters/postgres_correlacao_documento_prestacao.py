"""Adapter PostgreSQL do índice J3 (`magnata_orquestrador.correlacao_
documento_prestacao`, migration orquestrador 0007).

DB-API duck-typed (conexão injetada; nunca importa driver, nunca lê
secret, nunca aplica migration). A decisão do que gravar é SEMPRE
`planejar_observacoes` (domínio) -- este módulo só lê o estado corrente e
grava o plano, na mesma transação, sob `pg_advisory_xact_lock` por
(documento_id, origem): dois reprocessamentos concorrentes do mesmo
documento serializam, e o segundo vê o estado já gravado pelo primeiro
(nunca duplica versão). `UNIQUE (relacao_id, origem, sequencia)` é a
segunda barreira, no banco.

Leituras (`listar`, `historico_do_documento`) não fazem commit: a
conexão é de quem compõe (mesmo padrão de `buscar` dos demais
repositórios); quem mantém a conexão aberta encerra a transação.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, FrozenSet, Optional, Tuple

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.correlacao_documento_prestacao import (
    EstadoCorrelacao,
    ObservacaoCorrelacao,
    ResultadoRegistroCorrelacao,
    _itens_vigentes_deduplicados,
    planejar_observacoes,
)
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao

_TABELA = 'magnata_orquestrador.correlacao_documento_prestacao'
_CLASSE_LOCK = 6007  # espaço próprio de advisory lock (Gate 1 usa 6006)
_COLUNAS = (
    'relacao_id, sequencia, documento_id, cliente_id, competencia, tipo_documental, '
    'colaborador_id, estado, origem, evidencia_sha256, registrado_em'
)


def _linha_para_observacao(linha) -> ObservacaoCorrelacao:
    (relacao_id, sequencia, documento_id, cliente_id, competencia, tipo_documental,
     colaborador_id, estado, origem, evidencia_sha256, registrado_em) = linha
    return ObservacaoCorrelacao(
        relacao_id=relacao_id,
        sequencia=sequencia,
        item=ItemInventarioPrestacao(
            documento_id=documento_id,
            tipo_documental=tipo_documental,
            cliente=ReferenciaCanonica('CLIENTE', cliente_id),
            competencia=ReferenciaCanonica('COMPETENCIA', competencia),
            colaborador=ReferenciaCanonica('COLABORADOR', colaborador_id) if colaborador_id else None,
        ),
        estado=EstadoCorrelacao(estado),
        origem=origem,
        evidencia_sha256=evidencia_sha256,
        registrado_em=registrado_em,
    )


class RepositorioCorrelacaoDocumentoPrestacaoPostgres:
    """Implementa `RepositorioCorrelacaoDocumentoPrestacao` e, via
    `listar`, `FonteInventarioPrestacao`."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def registrar_relacoes_do_documento(
        self, *, documento_id: str, origem: str, itens: Tuple[ItemInventarioPrestacao, ...],
        evidencia_sha256: Optional[str], registrado_em: datetime,
        competencias_superaveis: Optional[FrozenSet[str]] = None,
    ) -> ResultadoRegistroCorrelacao:
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    'SELECT pg_advisory_xact_lock(%s, hashtext(%s))',
                    (_CLASSE_LOCK, f'{documento_id}|{origem}'),
                )
                cursor.execute(
                    f'''SELECT DISTINCT ON (relacao_id) {_COLUNAS}
                          FROM {_TABELA}
                         WHERE documento_id = %s AND origem = %s
                         ORDER BY relacao_id, sequencia DESC''',
                    (documento_id, origem),
                )
                estado_atual: Dict[str, tuple] = {}
                for linha in cursor.fetchall():
                    obs = _linha_para_observacao(linha)
                    estado_atual[obs.relacao_id] = (obs.estado, obs.sequencia, obs.item)

                observacoes, resultado = planejar_observacoes(
                    documento_id=documento_id, origem=origem, itens=itens,
                    estado_atual=estado_atual, evidencia_sha256=evidencia_sha256,
                    registrado_em=registrado_em, competencias_superaveis=competencias_superaveis,
                )
                for obs in observacoes:
                    item = obs.item
                    cursor.execute(
                        f'INSERT INTO {_TABELA} ({_COLUNAS}) '
                        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                        (
                            obs.relacao_id, obs.sequencia, item.documento_id,
                            item.cliente.entidade_id, item.competencia.entidade_id,
                            item.tipo_documental,
                            item.colaborador.entidade_id if item.colaborador is not None else None,
                            obs.estado.value, obs.origem, obs.evidencia_sha256, obs.registrado_em,
                        ),
                    )
            self._conexao.commit()
            return resultado
        except Exception:
            self._conexao.rollback()
            raise

    def listar(
        self, cliente: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> Tuple[ItemInventarioPrestacao, ...]:
        """Relações cujo estado CORRENTE (maior sequencia por relacao_id e
        origem) é VIGENTE para (cliente, competência). Somente leitura."""
        if cliente.tipo_entidade != 'CLIENTE' or competencia.tipo_entidade != 'COMPETENCIA':
            return ()
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'''SELECT {_COLUNAS} FROM (
                        SELECT DISTINCT ON (relacao_id, origem) {_COLUNAS}
                          FROM {_TABELA}
                         WHERE cliente_id = %s AND competencia = %s
                         ORDER BY relacao_id, origem, sequencia DESC
                    ) AS corrente
                    WHERE estado = %s''',
                (cliente.entidade_id, competencia.entidade_id, EstadoCorrelacao.VIGENTE.value),
            )
            linhas = cursor.fetchall()
        return _itens_vigentes_deduplicados(_linha_para_observacao(linha).item for linha in linhas)

    def historico_do_documento(self, documento_id: str) -> Tuple[ObservacaoCorrelacao, ...]:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'SELECT {_COLUNAS} FROM {_TABELA} WHERE documento_id = %s '
                'ORDER BY origem, relacao_id, sequencia',
                (documento_id,),
            )
            linhas = cursor.fetchall()
        return tuple(_linha_para_observacao(linha) for linha in linhas)


def construir_fonte_candidatos_por_necessidade_postgres(conexao):
    """Consumidor J3 -- `FonteCandidatosDocumentaisPorNecessidade` real:
    candidatos = relações VIGENTES do índice para (cliente, competência)
    filtradas por tipo (tradução canônica J1b) e colaborador (NULL para
    necessidade de nível cliente), materializadas como `Documento`
    INTERNO via `RepositorioDocumentosPostgres.buscar_por_id` -- nunca um
    record-id do Airtable (FK garante). Reutiliza a fonte interna já
    existente (`FonteCandidatosDocumentoInventarioInterna`); nenhum filtro
    novo, nenhuma segunda regra de candidatura."""
    from magnata_os.classificacao.fonte_candidatos_documento_inventario_interna import (
        FonteCandidatosDocumentoInventarioInterna,
    )
    from magnata_os.documental.modulo01.adapters.postgres_repositorio import RepositorioDocumentosPostgres

    return FonteCandidatosDocumentoInventarioInterna(
        fonte_inventario=RepositorioCorrelacaoDocumentoPrestacaoPostgres(conexao),
        repositorio_documentos=RepositorioDocumentosPostgres(conexao),
    )
