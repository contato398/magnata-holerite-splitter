"""
Contratos de resposta da API de esteira (Modulo 01, Fase 4).

Estes dataclasses sao o contrato ESTAVEL que a API expoe -- deliberadamente
separados dos DTOs internos (dtos_esteira.py, Fase 3) e das entidades de
dominio (dominio.py/dominio_esteira.py): quem consome a API nunca ve
Enum, datetime, MappingProxyType nem qualquer tipo interno dos
repositorios, so `str`/`int`/`float`/`bool`/`dict`/`tuple`/`None` --
prontos para virar JSON sem nenhuma logica de conversao adicional (ver
serializacao.py). Se o dominio interno mudar de forma, este contrato so
muda quando os mapeadores em handlers.py forem alterados de proposito.

Todo campo de data/hora e uma string ISO-8601 (UTC). Todo campo de
enum de dominio (etapa, situacao, tipo de proxima acao, perfil) e a
string do `.value` do Enum correspondente.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Optional, Tuple


@dataclasses.dataclass(frozen=True)
class MotivoBloqueioResponse:
    codigo: str
    descricao: str
    detalhe_tecnico: Optional[str]
    resolvivel_automaticamente: bool


@dataclasses.dataclass(frozen=True)
class ProximaAcaoResponse:
    acao: str
    tipo: str  # 'AUTOMATICA' | 'HUMANA'
    prazo: Optional[str]
    responsavel: Optional[str]


@dataclasses.dataclass(frozen=True)
class UltimoEventoResponse:
    evento: str
    timestamp: str
    correlation_id: str


@dataclasses.dataclass(frozen=True)
class DocumentoEsteiraResponse:
    """Resposta completa de um documento -- responde de uma vez ao
    principio obrigatorio da Fase 4: onde esta, como esta, por que
    parou, quem precisa agir, qual a proxima acao, ha quanto tempo."""

    documento_id: str
    nome_original: str
    lote_id: Optional[str]
    origem: str
    etapa_atual: Optional[str]
    situacao: Optional[str]
    motivo_bloqueio: Optional[MotivoBloqueioResponse]
    proxima_acao: Optional[ProximaAcaoResponse]
    tempo_na_etapa_segundos: Optional[float]
    ultimo_evento: Optional[UltimoEventoResponse]
    recebido_em: str
    atualizado_em: Optional[str]
    rastreado_pela_esteira: bool


@dataclasses.dataclass(frozen=True)
class LoteResponse:
    lote_id: str
    origem: str
    recebido_em: str
    quantidade_arquivos: int
    situacao: str
    correlation_id: str
    criado_em: str
    atualizado_em: str
    metadados: dict


@dataclasses.dataclass(frozen=True)
class HistoricoItemResponse:
    evento: str
    status_anterior: Optional[str]
    status_novo: Optional[str]
    timestamp: str
    correlation_id: str
    detalhes: dict


@dataclasses.dataclass(frozen=True)
class HistoricoResumidoResponse:
    documento_id: str
    total_eventos: int
    eventos: Tuple[HistoricoItemResponse, ...]


@dataclasses.dataclass(frozen=True)
class BloqueioResponse:
    documento_id: str
    nome_original: str
    lote_id: Optional[str]
    etapa_atual: str
    motivo_bloqueio: MotivoBloqueioResponse
    proxima_acao: Optional[ProximaAcaoResponse]
    tempo_bloqueado_segundos: float


@dataclasses.dataclass(frozen=True)
class ResumoEsteiraResponse:
    total_documentos: int
    total_por_etapa: dict
    total_por_situacao: dict
    total_bloqueados: int
    total_com_acao_humana: int
    total_em_erro: int
    total_parados_acima_do_limite: int
    limite_parado_segundos: float
    lotes_recebidos_hoje: int
    tempo_medio_na_etapa_segundos: Optional[float]
    documento_mais_antigo_pendente: Optional[DocumentoEsteiraResponse]


@dataclasses.dataclass(frozen=True)
class PaginacaoResponse:
    """Envelope generico de paginacao -- `itens` e sempre uma tupla de
    um unico tipo de contrato (LoteResponse, DocumentoEsteiraResponse
    ou BloqueioResponse, dependendo do endpoint)."""

    pagina: int
    tamanho_pagina: int
    total_itens: int
    total_paginas: int
    itens: Tuple[Any, ...]


@dataclasses.dataclass(frozen=True)
class ErroApiResponse:
    """Formato uniforme de erro -- `mensagem` e sempre segura para
    exibir ao usuario final (nunca uma stacktrace, nunca um detalhe de
    infraestrutura). Ver erros.py."""

    codigo: str
    mensagem: str
    detalhes: Optional[dict] = None
