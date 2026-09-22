"""
Adapters PostgreSQL para LoteDocumental e EstadoEsteiraDocumento
(Modulo 01, Fase 3 -- persistencia duravel da esteira operacional).

Mesmo padrao de magnata_os/documental/modulo01/adapters/
postgres_repositorio.py (Fase 2): escritos contra a interface
padronizada da DB-API 2.0 (PEP 249) -- `.cursor()`, `.execute()`,
`.fetchone()`, `.fetchall()`, `.commit()`, `.rollback()` -- nunca
importam psycopg2/psycopg diretamente. Qualquer objeto de conexao
compativel serve.

As tabelas esperadas (lotes_documentais, estados_esteira_documental) ja
sao criadas pelas migrations 0005/0006 -- nenhuma delas e aplicada por
este modulo, e nenhum schema novo e introduzido aqui.
"""
from __future__ import annotations

import json
from typing import Callable, List, Optional, Tuple

from ..dominio_esteira import (
    EstadoEsteiraDocumento,
    EtapaEsteira,
    LoteDocumental,
    MotivoBloqueio,
    ProximaAcao,
    SituacaoEsteira,
    TipoProximaAcao,
)

_COLUNAS_LOTES = (
    'lote_id', 'origem', 'recebido_em', 'quantidade_arquivos', 'situacao',
    'correlation_id', 'criado_em', 'atualizado_em', 'metadados',
)

_COLUNAS_ESTADOS = (
    'documento_id', 'lote_id', 'etapa_atual', 'situacao',
    'motivo_bloqueio_codigo', 'motivo_bloqueio_descricao',
    'motivo_bloqueio_detalhe_tecnico', 'motivo_bloqueio_resolvivel_automaticamente',
    'proxima_acao_acao', 'proxima_acao_tipo', 'proxima_acao_prazo', 'proxima_acao_responsavel',
    'entrou_na_etapa_em', 'atualizado_em', 'correlation_id',
)


def _e_violacao_de_integridade(exc: Exception) -> bool:
    """
    Deteccao duck-typed de violacao de constraint (ex.: PRIMARY KEY, FK),
    sem importar nenhum driver especifico -- mesma logica de
    postgres_repositorio.py::_e_violacao_de_integridade (duplicada aqui
    deliberadamente: sao 2 linhas puras, acoplar os 2 arquivos de adapter
    por isso custaria mais do que a duplicacao).
    """
    return any(base.__name__ == 'IntegrityError' for base in type(exc).__mro__)


def _lote_para_linha(lote: LoteDocumental) -> tuple:
    return (
        lote.lote_id, lote.origem, lote.recebido_em, lote.quantidade_arquivos,
        lote.situacao.value, lote.correlation_id, lote.criado_em, lote.atualizado_em,
        json.dumps(dict(lote.metadados)),
    )


def _linha_para_lote(linha: tuple) -> LoteDocumental:
    (
        lote_id, origem, recebido_em, quantidade_arquivos, situacao,
        correlation_id, criado_em, atualizado_em, metadados,
    ) = linha
    metadados_dict = json.loads(metadados) if isinstance(metadados, str) else (metadados or {})
    return LoteDocumental(
        lote_id=lote_id,
        origem=origem,
        recebido_em=recebido_em,
        quantidade_arquivos=quantidade_arquivos,
        situacao=SituacaoEsteira(situacao),
        correlation_id=correlation_id,
        criado_em=criado_em,
        atualizado_em=atualizado_em,
        metadados=metadados_dict,
    )


def _estado_para_linha(estado: EstadoEsteiraDocumento) -> tuple:
    motivo = estado.motivo_bloqueio
    proxima = estado.proxima_acao
    return (
        estado.documento_id,
        estado.lote_id,
        estado.etapa_atual.value,
        estado.situacao.value,
        motivo.codigo if motivo is not None else None,
        motivo.descricao if motivo is not None else None,
        motivo.detalhe_tecnico if motivo is not None else None,
        motivo.resolvivel_automaticamente if motivo is not None else None,
        proxima.acao if proxima is not None else None,
        proxima.tipo.value if proxima is not None else None,
        proxima.prazo if proxima is not None else None,
        proxima.responsavel if proxima is not None else None,
        estado.entrou_na_etapa_em,
        estado.atualizado_em,
        estado.correlation_id,
    )


def _linha_para_estado(linha: tuple) -> EstadoEsteiraDocumento:
    (
        documento_id, lote_id, etapa_atual, situacao,
        motivo_codigo, motivo_descricao, motivo_detalhe_tecnico, motivo_resolvivel,
        proxima_acao, proxima_tipo, proxima_prazo, proxima_responsavel,
        entrou_na_etapa_em, atualizado_em, correlation_id,
    ) = linha

    motivo_bloqueio = None
    if motivo_codigo is not None:
        motivo_bloqueio = MotivoBloqueio(
            codigo=motivo_codigo,
            descricao=motivo_descricao,
            detalhe_tecnico=motivo_detalhe_tecnico,
            resolvivel_automaticamente=motivo_resolvivel,
        )

    proxima_acao_obj = None
    if proxima_acao is not None:
        proxima_acao_obj = ProximaAcao(
            acao=proxima_acao,
            tipo=TipoProximaAcao(proxima_tipo),
            prazo=proxima_prazo,
            responsavel=proxima_responsavel,
        )

    return EstadoEsteiraDocumento(
        documento_id=documento_id,
        lote_id=lote_id,
        etapa_atual=EtapaEsteira(etapa_atual),
        situacao=SituacaoEsteira(situacao),
        motivo_bloqueio=motivo_bloqueio,
        proxima_acao=proxima_acao_obj,
        entrou_na_etapa_em=entrou_na_etapa_em,
        atualizado_em=atualizado_em,
        correlation_id=correlation_id,
    )


class RepositorioLotesPostgres:
    """Adapter PostgreSQL para RepositorioLotes (ver repositorio_esteira.py,
    Fase 3). `salvar` e upsert explicito por PRIMARY KEY (lote_id) -- um
    LoteDocumental e estado atual, nunca historico, mesmo espirito de
    RepositorioDocumentosPostgres.salvar."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def buscar_por_id(self, lote_id: str) -> Optional[LoteDocumental]:
        colunas = ', '.join(_COLUNAS_LOTES)
        with self._conexao.cursor() as cur:
            cur.execute(f'SELECT {colunas} FROM lotes_documentais WHERE lote_id = %s', (lote_id,))
            linha = cur.fetchone()
        return _linha_para_lote(linha) if linha else None

    def salvar(self, lote: LoteDocumental) -> None:
        colunas = ', '.join(_COLUNAS_LOTES)
        marcadores = ', '.join(['%s'] * len(_COLUNAS_LOTES))
        atualizacoes = ', '.join(f'{c} = EXCLUDED.{c}' for c in _COLUNAS_LOTES if c != 'lote_id')
        try:
            with self._conexao.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO lotes_documentais ({colunas}) VALUES ({marcadores})
                    ON CONFLICT (lote_id) DO UPDATE SET {atualizacoes}
                    """,
                    _lote_para_linha(lote),
                )
            self._conexao.commit()
        except Exception:
            # Sem rollback aqui, a conexao ficaria em estado de transacao
            # abortada ate um ROLLBACK explicito -- mesma disciplina de
            # postgres_repositorio.py::RepositorioDocumentosPostgres.salvar.
            self._conexao.rollback()
            raise

    def listar_recentes(self, limite: int = 50) -> List[LoteDocumental]:
        """Mais recente primeiro, por `criado_em`. Sob empate exato de
        `criado_em`, a ordem de desempate pode divergir de
        RepositorioLotesEmMemoria (que desempata por ordem de insercao
        em memoria) -- risco documentado, aceito nesta fase, nunca
        resolvido por schema novo aqui (ver ADR/Ultraplan desta
        missao)."""
        colunas = ', '.join(_COLUNAS_LOTES)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM lotes_documentais ORDER BY criado_em DESC LIMIT %s',
                (limite,),
            )
            linhas = cur.fetchall()
        return [_linha_para_lote(l) for l in linhas]

    def listar_todos(self) -> List[LoteDocumental]:
        colunas = ', '.join(_COLUNAS_LOTES)
        with self._conexao.cursor() as cur:
            cur.execute(f'SELECT {colunas} FROM lotes_documentais ORDER BY criado_em ASC')
            linhas = cur.fetchall()
        return [_linha_para_lote(l) for l in linhas]


class RepositorioEstadosEsteiraPostgres:
    """Adapter PostgreSQL para RepositorioEstadosEsteira (ver
    repositorio_esteira.py, Fase 3). `criar_se_ausente` e atomico via
    PRIMARY KEY (documento_id) do banco -- mesmo padrao comprovado de
    RepositorioDocumentosPostgres.salvar_se_ausente_por_hash."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def buscar_por_documento_id(self, documento_id: str) -> Optional[EstadoEsteiraDocumento]:
        colunas = ', '.join(_COLUNAS_ESTADOS)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM estados_esteira_documental WHERE documento_id = %s',
                (documento_id,),
            )
            linha = cur.fetchone()
        return _linha_para_estado(linha) if linha else None

    def salvar(self, estado: EstadoEsteiraDocumento) -> None:
        colunas = ', '.join(_COLUNAS_ESTADOS)
        marcadores = ', '.join(['%s'] * len(_COLUNAS_ESTADOS))
        atualizacoes = ', '.join(
            f'{c} = EXCLUDED.{c}' for c in _COLUNAS_ESTADOS if c != 'documento_id'
        )
        try:
            with self._conexao.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO estados_esteira_documental ({colunas}) VALUES ({marcadores})
                    ON CONFLICT (documento_id) DO UPDATE SET {atualizacoes}
                    """,
                    _estado_para_linha(estado),
                )
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise

    def criar_se_ausente(
        self, documento_id: str, fabricar_estado: Callable[[], EstadoEsteiraDocumento],
    ) -> Tuple[EstadoEsteiraDocumento, bool]:
        """
        Atomica via PRIMARY KEY (documento_id) do banco: `fabricar_estado()`
        e sempre chamada (o custo de fabricar um estado a mais em caso de
        corrida e aceitavel e barato) -- a garantia de unicidade nao
        depende disso, depende da constraint do banco. Mesmo padrao
        comprovado de RepositorioDocumentosPostgres.salvar_se_ausente_por_hash.
        """
        estado = fabricar_estado()
        colunas = ', '.join(_COLUNAS_ESTADOS)
        marcadores = ', '.join(['%s'] * len(_COLUNAS_ESTADOS))
        try:
            with self._conexao.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO estados_esteira_documental ({colunas}) VALUES ({marcadores})
                    ON CONFLICT (documento_id) DO NOTHING
                    RETURNING documento_id
                    """,
                    _estado_para_linha(estado),
                )
                inserido = cur.fetchone() is not None
            self._conexao.commit()
        except Exception as exc:
            self._conexao.rollback()
            if not _e_violacao_de_integridade(exc):
                raise
            inserido = False

        if inserido:
            return estado, True

        existente = self.buscar_por_documento_id(documento_id)
        if existente is None:
            raise RuntimeError(
                f'documento_id={documento_id} nao encontrado apos INSERT nao efetivado -- '
                f'estado inesperado do banco.'
            )
        return existente, False

    def listar_todos(self) -> List[EstadoEsteiraDocumento]:
        colunas = ', '.join(_COLUNAS_ESTADOS)
        with self._conexao.cursor() as cur:
            cur.execute(f'SELECT {colunas} FROM estados_esteira_documental ORDER BY entrou_na_etapa_em ASC')
            linhas = cur.fetchall()
        return [_linha_para_estado(l) for l in linhas]

    def listar_por_lote(self, lote_id: str) -> List[EstadoEsteiraDocumento]:
        colunas = ', '.join(_COLUNAS_ESTADOS)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM estados_esteira_documental WHERE lote_id = %s',
                (lote_id,),
            )
            linhas = cur.fetchall()
        return [_linha_para_estado(l) for l in linhas]

    def listar_por_etapa(self, etapa: EtapaEsteira) -> List[EstadoEsteiraDocumento]:
        colunas = ', '.join(_COLUNAS_ESTADOS)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM estados_esteira_documental WHERE etapa_atual = %s',
                (etapa.value,),
            )
            linhas = cur.fetchall()
        return [_linha_para_estado(l) for l in linhas]

    def listar_por_situacao(self, situacao: SituacaoEsteira) -> List[EstadoEsteiraDocumento]:
        colunas = ', '.join(_COLUNAS_ESTADOS)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM estados_esteira_documental WHERE situacao = %s',
                (situacao.value,),
            )
            linhas = cur.fetchall()
        return [_linha_para_estado(l) for l in linhas]
