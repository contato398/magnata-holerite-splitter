"""Adapter PostgreSQL para `ResolucaoDocumentalTemporalPonto` (missão
"IDENTIDADE TEMPORAL DOCUMENTAL DA FOLHA/CARTÃO DE PONTO V1").

Escrito contra a interface padronizada DB-API 2.0 (PEP 249), mesmo
padrão de `postgres_repositorio.py` -- nunca importa psycopg2/psycopg
diretamente; qualquer conexão compatível serve (real ou duplo de
teste). A tabela esperada é criada pela migration
`migrations/0010_criar_tabela_resolucao_documental_temporal.sql` --
NÃO aplicada por este módulo, e não aplicada em nenhum banco real por
esta missão.

GATE DE ATOMICIDADE: `salvar_com_evento` lê o estado atual (`SELECT ...
FOR UPDATE`, trava a linha se já existir), classifica a transição
(`classificar_transicao_resolucao`, mesma função pura do repositório em
memória — nunca duplicada) e insere/atualiza a resolução MAIS o evento
de auditoria (`eventos_documentais`, já existente) na MESMA transação —
uma única conexão, um único `commit()`. Se qualquer escrita falhar,
`rollback()` desfaz TUDO -- nunca um estado em que a resolução exista
sem o evento correspondente, e nunca uma atualização parcial. Isto é
intencionalmente MAIS restrito que `RepositorioHistoricoPostgres.
registrar` (que faz seu próprio commit isolado) -- este adapter nunca
chama aquele método diretamente, monta os INSERTs/UPDATE manualmente na
mesma transação.

GATE DE REPROCESSAMENTO: mesma semântica do repositório em memória —
EQUIVALENTE nunca escreve nada (libera o lock com `rollback()`, nunca
`commit()` de uma transação vazia); CONFLITO nunca decide sozinho qual
valor prevalece (rebaixa a competência persistida para `CONFLITO`,
preserva os 2 valores em disputa no evento de auditoria)."""
from __future__ import annotations

import json
from typing import List, Optional

from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.classificacao.resolucao_temporal_ponto import (
    ResolucaoDocumentalTemporalPonto,
    TransicaoResolucaoTemporal,
    classificar_transicao_resolucao,
    resolucao_a_persistir_para_transicao,
)
from magnata_os.documental.modulo01.repositorio_resolucao_temporal import FabricanteEvento

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
        fabricar_evento: FabricanteEvento,
    ) -> TransicaoResolucaoTemporal:
        """`resolucao_id` é derivado deterministicamente do
        `documento_id` (`restemp:<documento_id>`) -- coerente com a
        constraint UNIQUE(documento_id) da migration (1 resolução
        canônica por documento; reprocessar o mesmo documento produz o
        MESMO `resolucao_id`, nunca uma segunda linha por acidente de
        geração aleatória).

        Fluxo, tudo na MESMA transação: `SELECT ... FOR UPDATE` (trava a
        linha existente, se houver) -> classifica a transição -> por
        transição:
          - EQUIVALENTE: `rollback()` (libera o lock, nenhuma escrita,
            nenhum evento -- nunca um commit de transação vazia);
          - NOVA: `INSERT` da resolução;
          - ATUALIZACAO/CONFLITO: `UPDATE` da linha já existente (nunca
            um segundo `INSERT` -- UNIQUE(documento_id) preservado);
        seguido, para os 3 últimos casos, do `INSERT` do evento de
        auditoria e um único `commit()`. Qualquer falha em qualquer
        etapa -> `rollback()` completo, nunca uma escrita parcial."""
        resolucao_id = f'restemp:{resolucao.documento_id}'
        evidencias: dict = {}  # proveniência sanitizada -- vazio nesta fase (nenhuma coletada ainda)
        try:
            with self._conexao.cursor() as cur:
                colunas_select = ', '.join(_COLUNAS_RESOLUCAO)
                cur.execute(
                    f'SELECT {colunas_select} FROM resolucao_documental_temporal '
                    f'WHERE documento_id = %s FOR UPDATE',
                    (resolucao.documento_id,),
                )
                linha_anterior = cur.fetchone()
                anterior = _linha_para_resolucao(linha_anterior) if linha_anterior else None
                transicao = classificar_transicao_resolucao(anterior, resolucao)

                if transicao == TransicaoResolucaoTemporal.EQUIVALENTE:
                    self._conexao.rollback()  # libera o lock -- nenhuma escrita, nenhum evento
                    return transicao

                a_persistir = resolucao_a_persistir_para_transicao(transicao, resolucao)
                valores_resolucao = (
                    a_persistir.colaborador_id, a_persistir.periodo_inicio, a_persistir.periodo_fim,
                    _competencia_para_texto(a_persistir), a_persistir.resolucao_competencia.estado.value,
                    json.dumps(evidencias),
                )
                if transicao == TransicaoResolucaoTemporal.NOVA:
                    cur.execute(
                        f"""
                        INSERT INTO resolucao_documental_temporal ({', '.join(_COLUNAS_RESOLUCAO)})
                        VALUES ({', '.join(['%s'] * len(_COLUNAS_RESOLUCAO))})
                        """,
                        (resolucao_id, a_persistir.documento_id, a_persistir.tipo_documental, *valores_resolucao),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE resolucao_documental_temporal
                        SET tipo_documental = %s, colaborador_id = %s, periodo_inicio = %s,
                            periodo_fim = %s, competencia = %s, estado_resolucao = %s, evidencias = %s
                        WHERE documento_id = %s
                        """,
                        (a_persistir.tipo_documental, *valores_resolucao, resolucao.documento_id),
                    )

                evento = fabricar_evento(transicao, anterior, resolucao)
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
            return transicao
        except Exception:
            # Rollback COMPLETO: desfaz também o INSERT/UPDATE da
            # resolução -- nunca um commit parcial (gate de atomicidade).
            self._conexao.rollback()
            raise

    def listar_todos(self) -> List[ResolucaoDocumentalTemporalPonto]:
        colunas = ', '.join(_COLUNAS_RESOLUCAO)
        with self._conexao.cursor() as cur:
            cur.execute(f'SELECT {colunas} FROM resolucao_documental_temporal ORDER BY criado_em ASC')
            linhas = cur.fetchall()
        return [_linha_para_resolucao(l) for l in linhas]
