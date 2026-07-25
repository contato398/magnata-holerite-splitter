"""
Consultas de leitura da esteira operacional (Modulo 01, Fase 3).

Nenhuma funcao aqui muta estado -- todas sao leituras puras sobre os
repositorios (Fase 3) e, quando preciso, sobre o RepositorioHistorico da
Fase 1. Esta e a camada que responde ao principio obrigatorio desta
fase: para qualquer documento, o sistema precisa conseguir responder
onde esta, como esta, por que parou, qual a proxima acao, e ha quanto
tempo esta nessa etapa (ver MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3.md).
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from .dominio import EventoHistorico
from .dominio_esteira import EstadoEsteiraDocumento, EtapaEsteira, LoteDocumental, SituacaoEsteira, TipoProximaAcao
from .dtos_esteira import ProximaAcaoDTO, ResumoEsteira, proxima_acao_para_dto
from .repositorio import RepositorioHistorico
from .repositorio_esteira import RepositorioEstadosEsteira, RepositorioLotes


def _relogio_padrao() -> datetime:
    return datetime.now(timezone.utc)


def lotes_recentes(repositorio_lotes: RepositorioLotes, limite: int = 50) -> List[LoteDocumental]:
    return repositorio_lotes.listar_recentes(limite)


def lote_por_id(repositorio_lotes: RepositorioLotes, lote_id: str) -> Optional[LoteDocumental]:
    return repositorio_lotes.buscar_por_id(lote_id)


def documentos_por_etapa(
    repositorio_estados: RepositorioEstadosEsteira, etapa: EtapaEsteira,
) -> List[EstadoEsteiraDocumento]:
    return repositorio_estados.listar_por_etapa(etapa)


def documentos_por_situacao(
    repositorio_estados: RepositorioEstadosEsteira, situacao: SituacaoEsteira,
) -> List[EstadoEsteiraDocumento]:
    return repositorio_estados.listar_por_situacao(situacao)


def documentos_bloqueados(repositorio_estados: RepositorioEstadosEsteira) -> List[EstadoEsteiraDocumento]:
    return repositorio_estados.listar_por_situacao(SituacaoEsteira.BLOQUEADO)


def documentos_parados_a_partir_de(
    repositorio_estados: RepositorioEstadosEsteira,
    limite_segundos: float,
    relogio=_relogio_padrao,
) -> List[EstadoEsteiraDocumento]:
    """
    Documentos cuja permanencia na etapa atual (agora -
    entrou_na_etapa_em) ja atingiu ou ultrapassou `limite_segundos`.
    Ordenado do mais parado para o menos parado -- o primeiro da lista e
    sempre o caso mais critico.
    """
    agora = relogio()
    parados = [
        e for e in repositorio_estados.listar_todos()
        if (agora - e.entrou_na_etapa_em).total_seconds() >= limite_segundos
    ]
    parados.sort(key=lambda e: e.entrou_na_etapa_em)
    return parados


def documentos_com_acao_humana_pendente(
    repositorio_estados: RepositorioEstadosEsteira,
) -> List[EstadoEsteiraDocumento]:
    return [
        e for e in repositorio_estados.listar_todos()
        if e.proxima_acao is not None and e.proxima_acao.tipo == TipoProximaAcao.HUMANA
    ]


def ultimo_evento_e_proxima_acao(
    repositorio_historico: RepositorioHistorico,
    repositorio_estados: RepositorioEstadosEsteira,
    documento_id: str,
) -> Tuple[Optional[EventoHistorico], Optional[ProximaAcaoDTO]]:
    """
    Responde de uma vez "o que aconteceu por ultimo com este documento"
    (ultimo EventoHistorico, Fase 1 -- inclui eventos tecnicos E
    ESTEIRA_*) e "o que fazer a seguir" (proxima_acao do estado atual da
    esteira, Fase 3). Qualquer um dos dois pode ser None -- documento
    sem historico (nunca deveria acontecer para um documento existente,
    mas a funcao nao assume isso) ou documento nao rastreado pela
    esteira (legado).
    """
    eventos = repositorio_historico.listar_por_documento(documento_id)
    ultimo_evento = max(eventos, key=lambda e: e.timestamp) if eventos else None

    estado = repositorio_estados.buscar_por_documento_id(documento_id)
    proxima_acao_dto = proxima_acao_para_dto(estado.proxima_acao) if estado is not None else None

    return ultimo_evento, proxima_acao_dto


def montar_resumo_esteira(repositorio_estados: RepositorioEstadosEsteira) -> ResumoEsteira:
    """Visao agregada de toda a esteira -- para paineis/relatorios."""
    estados = repositorio_estados.listar_todos()
    por_etapa = Counter(e.etapa_atual for e in estados)
    por_situacao = Counter(e.situacao for e in estados)
    total_bloqueados = por_situacao.get(SituacaoEsteira.BLOQUEADO, 0)
    total_acao_humana = sum(
        1 for e in estados if e.proxima_acao is not None and e.proxima_acao.tipo == TipoProximaAcao.HUMANA
    )
    return ResumoEsteira(
        total_documentos_rastreados=len(estados),
        por_etapa=dict(por_etapa),
        por_situacao=dict(por_situacao),
        total_bloqueados=total_bloqueados,
        total_com_acao_humana_pendente=total_acao_humana,
    )
