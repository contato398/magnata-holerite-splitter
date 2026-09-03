"""Adapter PostgreSQL para `ResolucaoDocumentalTemporalPonto` (missão
"IDENTIDADE TEMPORAL DOCUMENTAL DA FOLHA/CARTÃO DE PONTO V1").

Escrito contra a interface padronizada DB-API 2.0 (PEP 249), mesmo
padrão de `postgres_repositorio.py` -- nunca importa psycopg2/psycopg
diretamente; qualquer conexão compatível serve (real ou duplo de
teste). A tabela esperada é criada pela migration
`migrations/0010_criar_tabela_resolucao_documental_temporal.sql` --
NÃO aplicada por este módulo, e não aplicada em nenhum banco real por
esta missão.

GATE DE ATOMICIDADE: `salvar_com_evento` insere a resolução E o evento
de auditoria (`eventos_documentais`, já existente) na MESMA transação —
uma única conexão, um único `commit()`. Se qualquer um dos dois INSERTs
falhar, `rollback()` desfaz AMBOS -- nunca um estado em que a resolução
exista sem o evento correspondente. Isto é intencionalmente MAIS
restrito que `RepositorioHistoricoPostgres.registrar` (que faz seu
próprio commit isolado) -- este adapter nunca chama aquele método
diretamente, monta os 2 INSERTs manualmente na mesma transação."""
from __future__ import annotations

import json
from typing import Callable, List, Optional

from ..dominio import EventoHistorico
from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.classificacao.resolucao_temporal_ponto import ResolucaoDocumentalTemporalPonto

_COLUNAS_RESOLUCAO = (
    'resolucao_id', 'documento_id', 'tipo_documental', 'colaborador_id',
    'periodo_inicio', 'periodo_fim', 'competencia', 'estado_resolucao', 'evidencias',
)

_COLUNAS_EVENTOS = (
    'documento_id', 'evento', 'status_anterior', 'status_novo',
    '"timestamp"', 'correlation_id', 'detalhes',
)


def _e_violacao_de_integridade(exc: Exception) -> bool:
    """Mesma detecção duck-typed já usada em `postgres_repositorio.py`
    -- nunca duplicar a lógica, só a assinatura mínima aqui evita
    import cruzado desnecessário entre adapters irmãos."""
    for classe in type(exc).__mro__:
        if classe.__name__ == 'IntegrityError':
            return True
    return False


def _competencia_para_texto(resolucao: ResolucaoDocumentalTemporalPonto) -> Optional[str]:
    if resolucao.resolucao_competencia.estado != EstadoResolucaoDimensao.RESOLVIDA:
        return None
    valores = resolucao.resolucao_competencia.valores_confirmados
    if len(valores) != 1:
        return None
    return valores[0].entidade_id


def _linha_para_resolucao(linha) -> ResolucaoDocumentalTemporalPonto:
    (
        _resolucao_id, documento_id, tipo_documental, colaborador_id,
        periodo_inicio, periodo_fim, competencia, estado_resolucao, _evidencias,
    ) = linha
    if competencia is not None and estado_resolucao == EstadoResolucaoDimensao.RESOLVIDA.value:
        resolucao_competencia = ResolucaoDimensao(
            dimensao=DimensaoResolucao.COMPETENCIA,
            estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(ReferenciaCanonica('COMPETENCIA', competencia),),
        )
    else:
        resolucao_competencia = ResolucaoDimensao(
            dimensao=DimensaoResolucao.COMPETENCIA,
            estado=EstadoResolucaoDimensao(estado_resolucao),
        )
    return ResolucaoDocumentalTemporalPonto(
        documento_id=documento_id, tipo_documental=tipo_documental,
        colaborador_id=colaborador_id, periodo_inicio=periodo_inicio, periodo_fim=periodo_fim,
        resolucao_competencia=resolucao_competencia,
    )


class RepositorioResolucaoTemporalPostgres:
    """Implementa `RepositorioResolucaoTemporal`
    (`repositorio_resolucao_temporal.py`) contra Postgres real."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def buscar_por_documento_id(self, documento_id: str) -> Optional[ResolucaoDocumentalTemporalPonto]:
        colunas = ', '.join(_COLUNAS_RESOLUCAO)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM resolucao_documental_temporal WHERE documento_id = %s',
                (documento_id,),
            )
            linha = cur.fetchone()
        return _linha_para_resolucao(linha) if linha else None

    def salvar_com_evento(
        self,
        resolucao: ResolucaoDocumentalTemporalPonto,
        fabricar_evento: Callable[[], EventoHistorico],
    ) -> None:
        """`resolucao_id` é derivado deterministicamente do
        `documento_id` (`restemp:<documento_id>`) -- coerente com a
        constraint UNIQUE(documento_id) da migration (1 resolução
        canônica por documento; reprocessar o mesmo documento produz o
        MESMO `resolucao_id`, nunca uma segunda linha por acidente de
        geração aleatória). Ambos os INSERTs (resolução + evento)
        acontecem na MESMA transação: um único `commit()` ao final,
        `rollback()` completo em qualquer falha -- nunca um commit
        parcial."""
        resolucao_id = f'restemp:{resolucao.documento_id}'
        evidencias: dict = {}  # proveniência sanitizada -- vazio nesta fase (nenhuma coletada ainda)
        try:
            with self._conexao.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO resolucao_documental_temporal ({', '.join(_COLUNAS_RESOLUCAO)})
                    VALUES ({', '.join(['%s'] * len(_COLUNAS_RESOLUCAO))})
                    """,
                    (
                        resolucao_id, resolucao.documento_id, resolucao.tipo_documental,
                        resolucao.colaborador_id, resolucao.periodo_inicio, resolucao.periodo_fim,
                        _competencia_para_texto(resolucao),
                        resolucao.resolucao_competencia.estado.value,
                        json.dumps(evidencias),
                    ),
                )
                evento = fabricar_evento()
                cur.execute(
                    f"""
                    INSERT INTO eventos_documentais ({', '.join(_COLUNAS_EVENTOS)})
                    VALUES ({', '.join(['%s'] * len(_COLUNAS_EVENTOS))})
                    """,
                    (
                        evento.documento_id, evento.evento,
                        evento.status_anterior.value if evento.status_anterior else None,
                        evento.status_novo.value if evento.status_novo else None,
                        evento.timestamp, evento.correlation_id, json.dumps(dict(evento.detalhes)),
                    ),
                )
            self._conexao.commit()
        except Exception:
            # Rollback COMPLETO: desfaz o INSERT da resolução também --
            # nunca um commit parcial (gate de atomicidade desta missão).
            self._conexao.rollback()
            raise

    def listar_todos(self) -> List[ResolucaoDocumentalTemporalPonto]:
        colunas = ', '.join(_COLUNAS_RESOLUCAO)
        with self._conexao.cursor() as cur:
            cur.execute(f'SELECT {colunas} FROM resolucao_documental_temporal ORDER BY criado_em ASC')
            linhas = cur.fetchall()
        return [_linha_para_resolucao(l) for l in linhas]
