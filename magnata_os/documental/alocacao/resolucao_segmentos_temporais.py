"""Resolução temporal pura: materialização de segmentos com cobertura integral.

Missão "CORREÇÃO DEFINITIVA DO PR #129 — RESOLUÇÃO TEMPORAL POSTO↔CLIENTE V1".

Função pura (zero I/O, zero driver de banco, zero Airtable, zero Flask).

Responsabilidade: receber fatos temporais reais de um adapter e decompor
a vigência de uma alocação em segmentos contínuos com cliente resolvido
ou lacuna histórica explícita. Nenhum período é fabricado; nenhum cliente
é inventado.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

from .temporal import (
    SegmentoTemporalAlocacao,
    SobreposicaoClientePorPostoError,
    StatusSegmentoTemporal,
    TuplaAlocacaoComClientes,
)


def materializar_segmentos_alocacao_com_cliente(
    alocacao_id: str,
    posto_id: str,
    vigente_de: date,
    vigente_ate: Optional[date],
    janela_inicio: date,
    janela_fim: date,
    tuplas_do_adapter: Tuple[TuplaAlocacaoComClientes, ...],
) -> Tuple[SegmentoTemporalAlocacao, ...]:
    """Materializa segmentos temporais completos de uma alocação com cliente resolvido.

    Entrada:
        alocacao_id: identidade da alocação (validada contra tuplas).
        posto_id: identidade do posto (validada contra tuplas).
        vigente_de: período início da alocação.
        vigente_ate: período fim da alocação (None = aberto).
        janela_inicio: início da janela consultada (data solicitada).
        janela_fim: fim da janela consultada.
        tuplas_do_adapter: resultado bruto do adapter PostgreSQL
            (fatos reais de interseção alocação ∩ cliente_por_posto).

    Saída: Tuple[SegmentoTemporalAlocacao, ...]
        - Cobertura 100% do intervalo_efetivo (alocação ∩ janela).
        - Nenhum buraco; nenhuma sobreposição.
        - Ordenado por segmento_de ASC.
        - cliente_id=NULL para lacunas (status=HISTORICO_NAO_COMPROVADO).
        - cliente_id preenchido para fatos reais (status=COMPROVADO).

    Exceções:
        ValueError: se janela_fim < janela_inicio.
        SobreposicaoClientePorPostoError: se dois clientes diferentes
            sobrepostos no mesmo posto.
        ValueError: se tupla de outro alocacao_id ou posto_id.
    """

    # Validação 1: janela finita válida
    if janela_fim < janela_inicio:
        raise ValueError(
            f"janela_fim ({janela_fim}) deve ser >= janela_inicio ({janela_inicio})"
        )

    # Validação 2: isolar e validar tuplas (alocacao_id, posto_id)
    for tupla in tuplas_do_adapter:
        if tupla.alocacao_id != alocacao_id:
            raise ValueError(
                f"Tupla contaminada: alocacao_id={tupla.alocacao_id} "
                f"(esperado {alocacao_id})"
            )
        if tupla.posto_id != posto_id:
            raise ValueError(
                f"Tupla contaminada: posto_id={tupla.posto_id} "
                f"(esperado {posto_id})"
            )

    # Cálculo de intervalo_efetivo
    alocacao_fim_efetivo = vigente_ate if vigente_ate is not None else date.max
    intervalo_inicio = max(vigente_de, janela_inicio)
    intervalo_fim = min(alocacao_fim_efetivo, janela_fim)

    # Se não houver interseção: retornar vazio
    if intervalo_fim < intervalo_inicio:
        return tuple()

    # Validação 3: detectar sobreposição de clientes diferentes
    clientes_ativos = {}  # data -> cliente_id
    for tupla in tuplas_do_adapter:
        if tupla.cliente_id is None:
            # Não é fato de cliente; pular
            continue

        cliente_inicio = tupla.cliente_vigente_de
        cliente_fim = tupla.cliente_vigente_ate if tupla.cliente_vigente_ate is not None else date.max

        # Recortar ao intervalo efetivo
        recorte_inicio = max(cliente_inicio, intervalo_inicio)
        recorte_fim = min(cliente_fim, intervalo_fim)

        if recorte_fim < recorte_inicio:
            # Cliente fora do intervalo efetivo; pular
            continue

        # Verificar sobreposição com cliente diferente já registrado
        for data_ativa in range(recorte_inicio.toordinal(), recorte_fim.toordinal() + 1):
            data_ord = date.fromordinal(data_ativa)
            cliente_anterior = clientes_ativos.get(data_ord)
            if cliente_anterior is not None and cliente_anterior != tupla.cliente_id:
                raise SobreposicaoClientePorPostoError(
                    f"Sobreposição de clientes no mesmo posto ({posto_id}): "
                    f"{cliente_anterior} e {tupla.cliente_id} sobrepostos em {data_ord}"
                )
            clientes_ativos[data_ord] = tupla.cliente_id

    # Construir lista de períodos com cliente real (recortados ao intervalo efetivo)
    periodos_reais = []
    for tupla in tuplas_do_adapter:
        if tupla.cliente_id is None:
            continue

        cliente_inicio = tupla.cliente_vigente_de
        cliente_fim = tupla.cliente_vigente_ate if tupla.cliente_vigente_ate is not None else date.max

        recorte_inicio = max(cliente_inicio, intervalo_inicio)
        recorte_fim = min(cliente_fim, intervalo_fim)

        if recorte_fim >= recorte_inicio:
            periodos_reais.append(
                (recorte_inicio, recorte_fim, tupla.cliente_id)
            )

    # Ordenar períodos reais por data de início
    periodos_reais.sort(key=lambda x: x[0])

    # Materializar segmentos: fatos reais + lacunas
    segmentos = []
    cursor = intervalo_inicio

    for periodo_inicio, periodo_fim, cliente_id in periodos_reais:
        # Lacuna antes deste período
        if cursor < periodo_inicio:
            segmentos.append(
                SegmentoTemporalAlocacao(
                    alocacao_id=alocacao_id,
                    posto_id=posto_id,
                    segmento_de=cursor,
                    segmento_ate=date.fromordinal(periodo_inicio.toordinal() - 1),
                    cliente_id=None,
                    status=StatusSegmentoTemporal.HISTORICO_NAO_COMPROVADO,
                )
            )

        # Período com cliente real
        segmentos.append(
            SegmentoTemporalAlocacao(
                alocacao_id=alocacao_id,
                posto_id=posto_id,
                segmento_de=periodo_inicio,
                segmento_ate=periodo_fim,
                cliente_id=cliente_id,
                status=StatusSegmentoTemporal.COMPROVADO,
            )
        )

        cursor = date.fromordinal(periodo_fim.toordinal() + 1)

    # Lacuna final (se houver)
    if cursor <= intervalo_fim:
        segmentos.append(
            SegmentoTemporalAlocacao(
                alocacao_id=alocacao_id,
                posto_id=posto_id,
                segmento_de=cursor,
                segmento_ate=intervalo_fim,
                cliente_id=None,
                status=StatusSegmentoTemporal.HISTORICO_NAO_COMPROVADO,
            )
        )

    # Se nenhum período real, o intervalo todo é lacuna
    if not periodos_reais and intervalo_fim >= intervalo_inicio:
        segmentos = [
            SegmentoTemporalAlocacao(
                alocacao_id=alocacao_id,
                posto_id=posto_id,
                segmento_de=intervalo_inicio,
                segmento_ate=intervalo_fim,
                cliente_id=None,
                status=StatusSegmentoTemporal.HISTORICO_NAO_COMPROVADO,
            )
        ]

    return tuple(segmentos)
