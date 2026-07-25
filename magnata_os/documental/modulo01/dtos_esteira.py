"""
DTOs de saida da esteira operacional (Modulo 01, Fase 3).

Camada de apresentacao/consulta, deliberadamente separada das entidades
de dominio (dominio_esteira.py): quem consome estes DTOs (relatorios,
futura API, futura interface web) nunca depende diretamente da forma
interna de LoteDocumental/EstadoEsteiraDocumento -- se o dominio evoluir
internamente, o contrato externo so muda quando as funcoes de conversao
aqui mudarem, de proposito.

Nenhuma funcao aqui faz I/O -- so transforma dados ja carregados.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Mapping, Optional, Tuple

from .dominio import Documento
from .dominio_esteira import (
    EstadoEsteiraDocumento,
    EtapaEsteira,
    MotivoBloqueio,
    ProximaAcao,
    SituacaoEsteira,
    TipoProximaAcao,
)


@dataclasses.dataclass(frozen=True)
class MotivoBloqueioDTO:
    codigo: str
    descricao: str
    detalhe_tecnico: Optional[str]
    resolvivel_automaticamente: bool


@dataclasses.dataclass(frozen=True)
class ProximaAcaoDTO:
    acao: str
    tipo: TipoProximaAcao
    prazo: Optional[datetime]
    responsavel: Optional[str]


@dataclasses.dataclass(frozen=True)
class ItemEsteiraDocumento:
    """Resposta completa a "onde este documento esta, como esta, por
    que parou, qual a proxima acao, ha quanto tempo" -- o principio
    obrigatorio desta fase (ver MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3.md).

    `rastreado_pela_esteira=False` e a resposta explicita para
    documentos legados (sem EstadoEsteiraDocumento, tipicamente criados
    antes da Fase 3) -- os campos de esteira ficam None em vez de
    inventar um estado que nunca existiu de verdade."""

    documento_id: str
    lote_id: Optional[str]
    rastreado_pela_esteira: bool
    etapa_atual: Optional[EtapaEsteira]
    situacao: Optional[SituacaoEsteira]
    motivo_bloqueio: Optional[MotivoBloqueioDTO]
    proxima_acao: Optional[ProximaAcaoDTO]
    entrou_na_etapa_em: Optional[datetime]
    tempo_na_etapa_segundos: Optional[float]
    atualizado_em: Optional[datetime]


@dataclasses.dataclass(frozen=True)
class ItemResumoLote:
    """Resultado do processamento de UM arquivo dentro de um lote."""

    nome_original: str
    documento_id: Optional[str]
    sucesso: bool
    duplicado: bool
    erro: Optional[str]


@dataclasses.dataclass(frozen=True)
class ResumoLote:
    lote_id: str
    origem: str
    correlation_id: str
    quantidade_arquivos: int
    quantidade_sucesso: int
    quantidade_duplicados: int
    quantidade_erro: int
    situacao: SituacaoEsteira
    criado_em: datetime
    itens: Tuple[ItemResumoLote, ...]


@dataclasses.dataclass(frozen=True)
class ResumoEsteira:
    """Visao agregada da esteira inteira -- para paineis/relatorios."""

    total_documentos_rastreados: int
    por_etapa: Mapping[EtapaEsteira, int]
    por_situacao: Mapping[SituacaoEsteira, int]
    total_bloqueados: int
    total_com_acao_humana_pendente: int


def motivo_bloqueio_para_dto(motivo: Optional[MotivoBloqueio]) -> Optional[MotivoBloqueioDTO]:
    if motivo is None:
        return None
    return MotivoBloqueioDTO(
        codigo=motivo.codigo,
        descricao=motivo.descricao,
        detalhe_tecnico=motivo.detalhe_tecnico,
        resolvivel_automaticamente=motivo.resolvivel_automaticamente,
    )


def proxima_acao_para_dto(proxima_acao: Optional[ProximaAcao]) -> Optional[ProximaAcaoDTO]:
    if proxima_acao is None:
        return None
    return ProximaAcaoDTO(
        acao=proxima_acao.acao,
        tipo=proxima_acao.tipo,
        prazo=proxima_acao.prazo,
        responsavel=proxima_acao.responsavel,
    )


def montar_item_esteira(
    documento: Documento,
    estado: Optional[EstadoEsteiraDocumento],
    agora: datetime,
) -> ItemEsteiraDocumento:
    """
    Constroi a resposta completa de rastreamento para um documento.
    `estado is None` e o caso de compatibilidade com documento legado
    (ver dominio_esteira.py, docstring de EstadoEsteiraDocumento) --
    nunca levanta excecao, sempre responde algo, com
    rastreado_pela_esteira=False deixando isso explicito para quem
    consome o DTO.
    """
    if estado is None:
        return ItemEsteiraDocumento(
            documento_id=documento.documento_id,
            lote_id=documento.lote_id,
            rastreado_pela_esteira=False,
            etapa_atual=None,
            situacao=None,
            motivo_bloqueio=None,
            proxima_acao=None,
            entrou_na_etapa_em=None,
            tempo_na_etapa_segundos=None,
            atualizado_em=None,
        )

    tempo_na_etapa_segundos = (agora - estado.entrou_na_etapa_em).total_seconds()
    return ItemEsteiraDocumento(
        documento_id=estado.documento_id,
        lote_id=estado.lote_id,
        rastreado_pela_esteira=True,
        etapa_atual=estado.etapa_atual,
        situacao=estado.situacao,
        motivo_bloqueio=motivo_bloqueio_para_dto(estado.motivo_bloqueio),
        proxima_acao=proxima_acao_para_dto(estado.proxima_acao),
        entrou_na_etapa_em=estado.entrou_na_etapa_em,
        tempo_na_etapa_segundos=tempo_na_etapa_segundos,
        atualizado_em=estado.atualizado_em,
    )
