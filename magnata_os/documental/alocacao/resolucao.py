"""Lógica COMPARTILHADA de resolução de UNIDADE_POSTO via Alocação
persistida -- implementa o Protocol JÁ EXISTENTE
`magnata_os.classificacao.vinculo_unidade_prestacao.FonteUnidadePostoPrestacao`
(nunca duplicado, nunca um segundo contrato para a mesma pergunta).

Função pura, injetada com as 2 consultas temporais (vínculos vigentes,
postos vigentes) -- cada adapter concreto (Postgres, SQLite) só liga
esta lógica às próprias queries, nunca reimplementa a decisão de
RESOLVIDA/NAO_ENCONTRADA (mesma disciplina de `PoliticaCompetenciaPrestacao.
competencia_esperada_para`: 1 lugar decide, adapters só fornecem dado)."""
from __future__ import annotations

from datetime import date
from typing import Callable, Tuple

from magnata_os.classificacao.contratos import (
    ConfiancaResolucao,
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    EvidenciaSanitizada,
    NivelConfianca,
    ReferenciaCanonica,
    ResolucaoDimensao,
)

from .temporal import intervalo_do_mes

MOTIVO_ALOCACAO_NAO_REGISTRADA = 'alocacao_nao_registrada_para_competencia'
"""Distinto de `vinculo_unidade_prestacao.MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA`
(que sinaliza uma fonte que só conhece o CORRENTE e nunca pode provar
histórico -- ex.: `FonteUnidadePostoPrestacaoAirtableShadow`). Esta
fonte é desenhada para conhecer histórico; quando devolve
NAO_ENCONTRADA, o motivo é a ausência REAL de registro de Alocação
para o colaborador/competência pedidos -- nunca uma limitação
estrutural da fonte."""


def _competencia_para_intervalo(competencia: ReferenciaCanonica) -> Tuple[date, date]:
    ano_texto, mes_texto = competencia.entidade_id.split('-', maxsplit=1)
    return intervalo_do_mes(int(ano_texto), int(mes_texto))


def resolver_unidade_posto_via_alocacao(
    colaborador: ReferenciaCanonica,
    competencia: ReferenciaCanonica,
    vinculos_vigentes_em: Callable[[str, date, date], Tuple[str, ...]],
    postos_vigentes_em: Callable[[str, date, date], Tuple[str, ...]],
) -> ResolucaoDimensao:
    """`vinculos_vigentes_em(colaborador_id, data_inicio, data_fim)` ->
    ids de `vinculo_trabalhista` cuja janela [admissão, desligamento]
    tem interseção com [data_inicio, data_fim] (o mês da competência
    inteiro, nunca um único dia -- preserva transferência/troca de
    vínculo no meio do mês).

    `postos_vigentes_em(vinculo_trabalhista_id, data_inicio, data_fim)`
    -> ids de posto (`alocacao.posto_id`) cuja janela [vigente_de,
    vigente_ate] intersecta o mesmo período.

    Cardinalidade múltipla é sempre genuína aqui (nunca AMBIGUA só por
    existir mais de 1 posto na mesma competência) -- mesma disciplina já
    estabelecida por `FonteUnidadePostoPrestacaoAirtableShadow`: rateio
    entre postos diferentes, ou troca de posto no meio do mês, produzem
    legitimamente N valores confirmados, nunca uma escolha arbitrária de
    qual "vale mais". "Conflito" (2 alocações do mesmo vínculo NO MESMO
    posto sobrepostas) é impedido estruturalmente pela constraint
    `EXCLUDE`/verificação de aplicação de cada adapter -- nunca
    observável aqui, portanto nunca precisa de um estado à parte."""
    if colaborador.tipo_entidade != 'COLABORADOR':
        raise ValueError('colaborador deve ser referencia canonica de COLABORADOR')
    if competencia.tipo_entidade != 'COMPETENCIA':
        raise ValueError('competencia deve ser referencia canonica de COMPETENCIA')

    data_inicio, data_fim = _competencia_para_intervalo(competencia)

    postos: set = set()
    vinculos = vinculos_vigentes_em(colaborador.entidade_id, data_inicio, data_fim)
    for vinculo_id in vinculos:
        postos.update(postos_vigentes_em(vinculo_id, data_inicio, data_fim))

    if not postos:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
            metodo='alocacao_persistida', motivos=(MOTIVO_ALOCACAO_NAO_REGISTRADA,),
        )

    postos_ordenados = tuple(sorted(postos))
    valores = tuple(ReferenciaCanonica('UNIDADE_POSTO', posto_id) for posto_id in postos_ordenados)
    evidencias = tuple(
        EvidenciaSanitizada(
            tipo_evidencia='ALOCACAO_PERSISTIDA', fonte='alocacao_temporal',
            referencia_fonte=posto_id, metodo='vinculo_alocacao_vigente',
            forca=NivelConfianca.FORTE, entidade_candidata=ReferenciaCanonica('UNIDADE_POSTO', posto_id),
            motivo_sanitizado='alocacao_com_vigencia_comprovada',
        )
        for posto_id in postos_ordenados
    )
    return ResolucaoDimensao(
        dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=valores, evidencias=evidencias, metodo='alocacao_persistida',
        confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )
