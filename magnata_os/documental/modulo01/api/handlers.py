"""
Handlers/controladores da API de esteira (Modulo 01, Fase 4).

Cada funcao publica aqui corresponde a um endpoint conceitual (ver
MAGNATA_OS_DOCUMENTAL_MODULO01_FASE4.md) -- framework-agnostico de
proposito: recebe tipos Python simples (ContextoApi, Sujeito, filtros
de filtros.py), nunca um `Request` do Flask ou de qualquer outro
framework, e devolve sempre um contrato de contratos.py, nunca uma
entidade de dominio ou um DTO interno. Um adapter web futuro (fora do
escopo desta fase) e quem traduz HTTP <-> estes tipos.

Toda funcao publica:
  1. Comeca chamando `exigir_perfil()` com o conjunto de perfis que ELA
     PROPRIA declara precisar (constantes PERMISSAO_* abaixo) -- nunca
     implicito, nunca "confia" que quem chamou ja verificou.
  2. E decorada com `@proteger_erros`: qualquer excecao que nao seja
     ApiError e convertida em ErroInternoNaoExposto ANTES de sair do
     handler -- o contrato publico de toda funcao aqui e "so levanta
     ApiError (erros.py), nunca uma excecao de infraestrutura crua".
"""
from __future__ import annotations

import dataclasses
import functools
import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional, Tuple

from ..dominio import Documento, EventoHistorico
from ..dominio_esteira import EstadoEsteiraDocumento, EtapaEsteira, LoteDocumental, SituacaoEsteira, TipoProximaAcao
from ..dtos_esteira import ItemEsteiraDocumento, montar_item_esteira
from ..repositorio import RepositorioDocumentos, RepositorioHistorico
from ..repositorio_esteira import RepositorioEstadosEsteira, RepositorioLotes
from .autorizacao import Perfil, Sujeito, exigir_perfil
from .contratos import (
    BloqueioResponse,
    DocumentoEsteiraResponse,
    HistoricoItemResponse,
    HistoricoResumidoResponse,
    LoteResponse,
    MotivoBloqueioResponse,
    PaginacaoResponse,
    ProximaAcaoResponse,
    ResumoEsteiraResponse,
    UltimoEventoResponse,
)
from .erros import (
    ApiError,
    DocumentoNaoEncontrado,
    ErroInternoNaoExposto,
    FiltroInvalido,
    LoteNaoEncontrado,
    MENSAGEM_ERRO_INTERNO_PADRAO,
)
from .filtros import (
    CAMPOS_ORDENACAO_BLOQUEIOS,
    CAMPOS_ORDENACAO_DOCUMENTOS,
    CAMPOS_ORDENACAO_LOTES,
    FiltroDocumentos,
    FiltroLotes,
    Ordenacao,
    Paginacao,
    validar_filtro_documentos,
    validar_filtro_lotes,
    validar_ordenacao,
    validar_paginacao,
)

# ============================================================================
# permissoes -- cada handler declara explicitamente qual conjunto exige
# ============================================================================

# Visao geral de leitura (resumo, listas, documento/lote individual,
# documentos parados): todo perfil monitora o estado da esteira.
PERMISSAO_LEITURA_GERAL = frozenset({Perfil.OPERACIONAL, Perfil.GESTOR, Perfil.AUDITOR})

# Filas operacionais de ACAO (bloqueios, acoes humanas): quem de fato
# resolve essas pendencias no dia a dia -- auditor consulta o estado via
# documentos/historico, nao via a fila operacional de trabalho.
PERMISSAO_FILA_OPERACIONAL = frozenset({Perfil.OPERACIONAL, Perfil.GESTOR})

# Historico completo de um documento: trilha de auditoria detalhada --
# operacional tem a proxima acao ja resolvida nas outras consultas e nao
# precisa do historico bruto para o trabalho do dia a dia.
PERMISSAO_AUDITORIA = frozenset({Perfil.GESTOR, Perfil.AUDITOR})

LIMITE_PARADO_PADRAO_SEGUNDOS = 24 * 60 * 60.0  # 24h


def _relogio_padrao() -> datetime:
    return datetime.now(timezone.utc)


@dataclasses.dataclass(frozen=True)
class ContextoApi:
    """Agrupa os repositorios que os handlers precisam -- nunca
    instanciado com adapters reais (Postgres/S3) nesta fase."""

    repositorio_documentos: RepositorioDocumentos
    repositorio_historico: RepositorioHistorico
    repositorio_lotes: RepositorioLotes
    repositorio_estados: RepositorioEstadosEsteira
    relogio: Callable[[], datetime] = _relogio_padrao


def proteger_erros(func):
    """Garante que todo handler so levanta ApiError. Qualquer outra
    excecao (bug, repositorio indisponivel, KeyError inesperado, etc.)
    e convertida em ErroInternoNaoExposto, com a MESMA mensagem generica
    sempre -- a excecao original fica encadeada via `from exc` (visivel
    em stacktrace/logs de processo), nunca na mensagem exposta."""

    @functools.wraps(func)
    def _wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ApiError:
            raise
        except Exception as exc:
            raise ErroInternoNaoExposto(MENSAGEM_ERRO_INTERNO_PADRAO) from exc

    return _wrapper


# ============================================================================
# helpers -- ordenacao segura, paginacao, mapeamento para contratos
# ============================================================================

def _iso(momento: Optional[datetime]) -> Optional[str]:
    return momento.isoformat() if momento is not None else None


def _ordenar_seguro(itens: list, extrator: Callable[[Any], Any], direcao: str) -> list:
    """Nunca recebe um nome de campo arbitrario -- `extrator` sempre vem
    de um dicionario fixo (allowlist) resolvido ANTES desta funcao ser
    chamada (ver validar_ordenacao). Itens cujo extrator devolve None
    (ex.: documento legado, sem `atualizado_em` de esteira) sempre vao
    para o fim da lista, em qualquer direcao -- nunca quebram o sort
    comparando None com datetime/float."""
    com_valor = [item for item in itens if extrator(item) is not None]
    sem_valor = [item for item in itens if extrator(item) is None]
    com_valor.sort(key=extrator, reverse=(direcao == 'desc'))
    return com_valor + sem_valor


def _paginar(itens: list, paginacao: Paginacao) -> Tuple[list, int, int]:
    total_itens = len(itens)
    total_paginas = math.ceil(total_itens / paginacao.tamanho_pagina) if total_itens > 0 else 0
    inicio = (paginacao.pagina - 1) * paginacao.tamanho_pagina
    fim = inicio + paginacao.tamanho_pagina
    return itens[inicio:fim], total_itens, total_paginas


def _buscar_ultimo_evento(ctx: ContextoApi, documento_id: str) -> Optional[EventoHistorico]:
    eventos = ctx.repositorio_historico.listar_por_documento(documento_id)
    return max(eventos, key=lambda e: e.timestamp) if eventos else None


def _motivo_bloqueio_para_response(motivo) -> Optional[MotivoBloqueioResponse]:
    if motivo is None:
        return None
    return MotivoBloqueioResponse(
        codigo=motivo.codigo,
        descricao=motivo.descricao,
        detalhe_tecnico=motivo.detalhe_tecnico,
        resolvivel_automaticamente=motivo.resolvivel_automaticamente,
    )


def _proxima_acao_para_response(proxima_acao) -> Optional[ProximaAcaoResponse]:
    if proxima_acao is None:
        return None
    return ProximaAcaoResponse(
        acao=proxima_acao.acao,
        tipo=proxima_acao.tipo.value,
        prazo=_iso(proxima_acao.prazo),
        responsavel=proxima_acao.responsavel,
    )


def _evento_para_response(evento: Optional[EventoHistorico]) -> Optional[UltimoEventoResponse]:
    if evento is None:
        return None
    return UltimoEventoResponse(evento=evento.evento, timestamp=_iso(evento.timestamp), correlation_id=evento.correlation_id)


def _historico_item_para_response(evento: EventoHistorico) -> HistoricoItemResponse:
    return HistoricoItemResponse(
        evento=evento.evento,
        status_anterior=evento.status_anterior.value if evento.status_anterior else None,
        status_novo=evento.status_novo.value if evento.status_novo else None,
        timestamp=_iso(evento.timestamp),
        correlation_id=evento.correlation_id,
        detalhes=dict(evento.detalhes),
    )


def _documento_para_response(
    documento: Documento, item: ItemEsteiraDocumento, ultimo_evento: Optional[EventoHistorico],
) -> DocumentoEsteiraResponse:
    return DocumentoEsteiraResponse(
        documento_id=documento.documento_id,
        nome_original=documento.nome_original,
        lote_id=documento.lote_id,
        origem=documento.origem,
        etapa_atual=item.etapa_atual.value if item.etapa_atual else None,
        situacao=item.situacao.value if item.situacao else None,
        motivo_bloqueio=_motivo_bloqueio_para_response(item.motivo_bloqueio),
        proxima_acao=_proxima_acao_para_response(item.proxima_acao),
        tempo_na_etapa_segundos=item.tempo_na_etapa_segundos,
        ultimo_evento=_evento_para_response(ultimo_evento),
        recebido_em=_iso(documento.recebido_em),
        atualizado_em=_iso(item.atualizado_em),
        rastreado_pela_esteira=item.rastreado_pela_esteira,
    )


def _lote_para_response(lote: LoteDocumental) -> LoteResponse:
    return LoteResponse(
        lote_id=lote.lote_id,
        origem=lote.origem,
        recebido_em=_iso(lote.recebido_em),
        quantidade_arquivos=lote.quantidade_arquivos,
        situacao=lote.situacao.value,
        correlation_id=lote.correlation_id,
        criado_em=_iso(lote.criado_em),
        atualizado_em=_iso(lote.atualizado_em),
        metadados=dict(lote.metadados),
    )


def _bloqueio_para_response(
    documento: Documento, estado: EstadoEsteiraDocumento, tempo_bloqueado_segundos: float,
) -> BloqueioResponse:
    return BloqueioResponse(
        documento_id=documento.documento_id,
        nome_original=documento.nome_original,
        lote_id=documento.lote_id,
        etapa_atual=estado.etapa_atual.value,
        motivo_bloqueio=_motivo_bloqueio_para_response(estado.motivo_bloqueio),
        proxima_acao=_proxima_acao_para_response(estado.proxima_acao),
        tempo_bloqueado_segundos=tempo_bloqueado_segundos,
    )


def _construir_linhas_documentos(
    ctx: ContextoApi, agora: datetime,
) -> List[Tuple[Documento, ItemEsteiraDocumento]]:
    """Uma linha por Documento (Fase 1), sempre -- inclusive documentos
    legados sem EstadoEsteiraDocumento (montar_item_esteira, Fase 3,
    responde rastreado_pela_esteira=False para eles, nunca os
    exclui)."""
    linhas = []
    for documento in ctx.repositorio_documentos.listar_todos():
        estado = ctx.repositorio_estados.buscar_por_documento_id(documento.documento_id)
        item = montar_item_esteira(documento, estado, agora)
        linhas.append((documento, item))
    return linhas


def _aplicar_filtro_documentos(
    linhas: List[Tuple[Documento, ItemEsteiraDocumento]], filtro: FiltroDocumentos,
) -> List[Tuple[Documento, ItemEsteiraDocumento]]:
    resultado = []
    for documento, item in linhas:
        if filtro.etapa is not None and item.etapa_atual != filtro.etapa:
            continue
        if filtro.situacao is not None and item.situacao != filtro.situacao:
            continue
        if filtro.lote_id is not None and documento.lote_id != filtro.lote_id:
            continue
        if filtro.origem is not None and documento.origem != filtro.origem:
            continue
        if filtro.bloqueado is not None:
            esta_bloqueado = item.situacao == SituacaoEsteira.BLOQUEADO
            if esta_bloqueado != filtro.bloqueado:
                continue
        if filtro.acao_humana is not None:
            tem_acao_humana = item.proxima_acao is not None and item.proxima_acao.tipo == TipoProximaAcao.HUMANA
            if tem_acao_humana != filtro.acao_humana:
                continue
        if filtro.recebido_de is not None and documento.recebido_em < filtro.recebido_de:
            continue
        if filtro.recebido_ate is not None and documento.recebido_em > filtro.recebido_ate:
            continue
        if filtro.tempo_minimo_parado_segundos is not None:
            tempo = item.tempo_na_etapa_segundos
            if tempo is None or tempo < filtro.tempo_minimo_parado_segundos:
                continue
        resultado.append((documento, item))
    return resultado


def _aplicar_filtro_lotes(lotes: List[LoteDocumental], filtro: FiltroLotes) -> List[LoteDocumental]:
    resultado = []
    for lote in lotes:
        if filtro.origem is not None and lote.origem != filtro.origem:
            continue
        if filtro.situacao is not None and lote.situacao != filtro.situacao:
            continue
        if filtro.recebido_de is not None and lote.recebido_em < filtro.recebido_de:
            continue
        if filtro.recebido_ate is not None and lote.recebido_em > filtro.recebido_ate:
            continue
        resultado.append(lote)
    return resultado


_EXTRATORES_ORDENACAO_DOCUMENTOS: dict = {
    'atualizado_em': lambda par: par[1].atualizado_em,
    'entrou_na_etapa_em': lambda par: par[1].entrou_na_etapa_em,
    'recebido_em': lambda par: par[0].recebido_em,
    'documento_id': lambda par: par[0].documento_id,
    'tempo_na_etapa_segundos': lambda par: par[1].tempo_na_etapa_segundos,
}

_EXTRATORES_ORDENACAO_LOTES: dict = {
    'criado_em': lambda lote: lote.criado_em,
    'recebido_em': lambda lote: lote.recebido_em,
    'quantidade_arquivos': lambda lote: lote.quantidade_arquivos,
    'lote_id': lambda lote: lote.lote_id,
}

_EXTRATORES_ORDENACAO_BLOQUEIOS: dict = {
    'tempo_bloqueado_segundos': lambda linha: linha[2],
    'documento_id': lambda linha: linha[0].documento_id,
}


# ============================================================================
# handlers -- um por endpoint conceitual
# ============================================================================

@proteger_erros
def obter_resumo_esteira(
    ctx: ContextoApi, sujeito: Sujeito, limite_parado_segundos: float = LIMITE_PARADO_PADRAO_SEGUNDOS,
) -> ResumoEsteiraResponse:
    """GET /magnata-os/documental/esteira/resumo"""
    exigir_perfil(sujeito, PERMISSAO_LEITURA_GERAL)
    if limite_parado_segundos < 0:
        raise FiltroInvalido('limite_parado_segundos nao pode ser negativo.')

    agora = ctx.relogio()
    documentos = ctx.repositorio_documentos.listar_todos()
    estados = ctx.repositorio_estados.listar_todos()

    total_por_etapa = Counter(e.etapa_atual.value for e in estados)
    total_por_situacao = Counter(e.situacao.value for e in estados)
    total_bloqueados = total_por_situacao.get(SituacaoEsteira.BLOQUEADO.value, 0)
    total_com_acao_humana = sum(
        1 for e in estados if e.proxima_acao is not None and e.proxima_acao.tipo == TipoProximaAcao.HUMANA
    )
    total_em_erro = total_por_situacao.get(SituacaoEsteira.ERRO.value, 0)
    total_parados = sum(
        1 for e in estados if (agora - e.entrou_na_etapa_em).total_seconds() >= limite_parado_segundos
    )

    hoje = agora.date()
    lotes_recebidos_hoje = sum(1 for lote in ctx.repositorio_lotes.listar_todos() if lote.recebido_em.date() == hoje)

    tempos_na_etapa = [(agora - e.entrou_na_etapa_em).total_seconds() for e in estados]
    tempo_medio = (sum(tempos_na_etapa) / len(tempos_na_etapa)) if tempos_na_etapa else None

    documento_mais_antigo_pendente = None
    pendentes = [
        e for e in estados
        if not (e.etapa_atual == EtapaEsteira.AUDITORIA and e.situacao == SituacaoEsteira.CONCLUIDO)
    ]
    if pendentes:
        estado_mais_antigo = min(pendentes, key=lambda e: e.entrou_na_etapa_em)
        documento = ctx.repositorio_documentos.buscar_por_id(estado_mais_antigo.documento_id)
        if documento is not None:
            item = montar_item_esteira(documento, estado_mais_antigo, agora)
            ultimo_evento = _buscar_ultimo_evento(ctx, documento.documento_id)
            documento_mais_antigo_pendente = _documento_para_response(documento, item, ultimo_evento)

    return ResumoEsteiraResponse(
        total_documentos=len(documentos),
        total_por_etapa=dict(total_por_etapa),
        total_por_situacao=dict(total_por_situacao),
        total_bloqueados=total_bloqueados,
        total_com_acao_humana=total_com_acao_humana,
        total_em_erro=total_em_erro,
        total_parados_acima_do_limite=total_parados,
        limite_parado_segundos=limite_parado_segundos,
        lotes_recebidos_hoje=lotes_recebidos_hoje,
        tempo_medio_na_etapa_segundos=tempo_medio,
        documento_mais_antigo_pendente=documento_mais_antigo_pendente,
    )


@proteger_erros
def listar_lotes(
    ctx: ContextoApi,
    sujeito: Sujeito,
    filtro: FiltroLotes = FiltroLotes(),
    paginacao: Paginacao = Paginacao(),
    ordenacao: Ordenacao = Ordenacao(campo='criado_em', direcao='desc'),
) -> PaginacaoResponse:
    """GET /magnata-os/documental/lotes"""
    exigir_perfil(sujeito, PERMISSAO_LEITURA_GERAL)
    validar_filtro_lotes(filtro)
    validar_paginacao(paginacao)
    validar_ordenacao(ordenacao, CAMPOS_ORDENACAO_LOTES)

    lotes = _aplicar_filtro_lotes(ctx.repositorio_lotes.listar_todos(), filtro)
    lotes = _ordenar_seguro(lotes, _EXTRATORES_ORDENACAO_LOTES[ordenacao.campo], ordenacao.direcao)
    pagina_itens, total_itens, total_paginas = _paginar(lotes, paginacao)

    return PaginacaoResponse(
        pagina=paginacao.pagina,
        tamanho_pagina=paginacao.tamanho_pagina,
        total_itens=total_itens,
        total_paginas=total_paginas,
        itens=tuple(_lote_para_response(lote) for lote in pagina_itens),
    )


@proteger_erros
def obter_lote(ctx: ContextoApi, sujeito: Sujeito, lote_id: str) -> LoteResponse:
    """GET /magnata-os/documental/lotes/{lote_id}"""
    exigir_perfil(sujeito, PERMISSAO_LEITURA_GERAL)
    lote = ctx.repositorio_lotes.buscar_por_id(lote_id)
    if lote is None:
        raise LoteNaoEncontrado(f'Lote nao encontrado: {lote_id!r}.')
    return _lote_para_response(lote)


@proteger_erros
def listar_documentos(
    ctx: ContextoApi,
    sujeito: Sujeito,
    filtro: FiltroDocumentos = FiltroDocumentos(),
    paginacao: Paginacao = Paginacao(),
    ordenacao: Ordenacao = Ordenacao(campo='atualizado_em', direcao='desc'),
) -> PaginacaoResponse:
    """GET /magnata-os/documental/documentos"""
    exigir_perfil(sujeito, PERMISSAO_LEITURA_GERAL)
    validar_filtro_documentos(filtro)
    validar_paginacao(paginacao)
    validar_ordenacao(ordenacao, CAMPOS_ORDENACAO_DOCUMENTOS)

    agora = ctx.relogio()
    linhas = _aplicar_filtro_documentos(_construir_linhas_documentos(ctx, agora), filtro)
    linhas = _ordenar_seguro(linhas, _EXTRATORES_ORDENACAO_DOCUMENTOS[ordenacao.campo], ordenacao.direcao)
    pagina_linhas, total_itens, total_paginas = _paginar(linhas, paginacao)

    itens = tuple(
        _documento_para_response(documento, item, _buscar_ultimo_evento(ctx, documento.documento_id))
        for documento, item in pagina_linhas
    )
    return PaginacaoResponse(
        pagina=paginacao.pagina, tamanho_pagina=paginacao.tamanho_pagina,
        total_itens=total_itens, total_paginas=total_paginas, itens=itens,
    )


@proteger_erros
def obter_documento(ctx: ContextoApi, sujeito: Sujeito, documento_id: str) -> DocumentoEsteiraResponse:
    """GET /magnata-os/documental/documentos/{documento_id}"""
    exigir_perfil(sujeito, PERMISSAO_LEITURA_GERAL)
    documento = ctx.repositorio_documentos.buscar_por_id(documento_id)
    if documento is None:
        raise DocumentoNaoEncontrado(f'Documento nao encontrado: {documento_id!r}.')

    agora = ctx.relogio()
    estado = ctx.repositorio_estados.buscar_por_documento_id(documento_id)
    item = montar_item_esteira(documento, estado, agora)
    ultimo_evento = _buscar_ultimo_evento(ctx, documento_id)
    return _documento_para_response(documento, item, ultimo_evento)


@proteger_erros
def obter_historico_documento(ctx: ContextoApi, sujeito: Sujeito, documento_id: str) -> HistoricoResumidoResponse:
    """GET /magnata-os/documental/documentos/{documento_id}/historico"""
    exigir_perfil(sujeito, PERMISSAO_AUDITORIA)
    documento = ctx.repositorio_documentos.buscar_por_id(documento_id)
    if documento is None:
        raise DocumentoNaoEncontrado(f'Documento nao encontrado: {documento_id!r}.')

    eventos = sorted(ctx.repositorio_historico.listar_por_documento(documento_id), key=lambda e: e.timestamp)
    itens = tuple(_historico_item_para_response(evento) for evento in eventos)
    return HistoricoResumidoResponse(documento_id=documento_id, total_eventos=len(itens), eventos=itens)


@proteger_erros
def listar_bloqueios(
    ctx: ContextoApi,
    sujeito: Sujeito,
    paginacao: Paginacao = Paginacao(),
    ordenacao: Ordenacao = Ordenacao(campo='tempo_bloqueado_segundos', direcao='desc'),
) -> PaginacaoResponse:
    """GET /magnata-os/documental/bloqueios"""
    exigir_perfil(sujeito, PERMISSAO_FILA_OPERACIONAL)
    validar_paginacao(paginacao)
    validar_ordenacao(ordenacao, CAMPOS_ORDENACAO_BLOQUEIOS)

    agora = ctx.relogio()
    linhas = []
    for estado in ctx.repositorio_estados.listar_todos():
        if estado.situacao != SituacaoEsteira.BLOQUEADO:
            continue
        documento = ctx.repositorio_documentos.buscar_por_id(estado.documento_id)
        if documento is None:
            continue  # nunca deveria acontecer (FK garante isso num banco real); defensivo aqui
        tempo_bloqueado = (agora - estado.atualizado_em).total_seconds()
        linhas.append((documento, estado, tempo_bloqueado))

    linhas = _ordenar_seguro(linhas, _EXTRATORES_ORDENACAO_BLOQUEIOS[ordenacao.campo], ordenacao.direcao)
    pagina_linhas, total_itens, total_paginas = _paginar(linhas, paginacao)

    itens = tuple(_bloqueio_para_response(documento, estado, tempo) for documento, estado, tempo in pagina_linhas)
    return PaginacaoResponse(
        pagina=paginacao.pagina, tamanho_pagina=paginacao.tamanho_pagina,
        total_itens=total_itens, total_paginas=total_paginas, itens=itens,
    )


@proteger_erros
def listar_acoes_humanas(
    ctx: ContextoApi,
    sujeito: Sujeito,
    paginacao: Paginacao = Paginacao(),
    ordenacao: Ordenacao = Ordenacao(campo='atualizado_em', direcao='desc'),
) -> PaginacaoResponse:
    """GET /magnata-os/documental/acoes-humanas"""
    exigir_perfil(sujeito, PERMISSAO_FILA_OPERACIONAL)
    validar_paginacao(paginacao)
    validar_ordenacao(ordenacao, CAMPOS_ORDENACAO_DOCUMENTOS)

    agora = ctx.relogio()
    linhas = [
        (documento, item) for documento, item in _construir_linhas_documentos(ctx, agora)
        if item.proxima_acao is not None and item.proxima_acao.tipo == TipoProximaAcao.HUMANA
    ]
    linhas = _ordenar_seguro(linhas, _EXTRATORES_ORDENACAO_DOCUMENTOS[ordenacao.campo], ordenacao.direcao)
    pagina_linhas, total_itens, total_paginas = _paginar(linhas, paginacao)

    itens = tuple(
        _documento_para_response(documento, item, _buscar_ultimo_evento(ctx, documento.documento_id))
        for documento, item in pagina_linhas
    )
    return PaginacaoResponse(
        pagina=paginacao.pagina, tamanho_pagina=paginacao.tamanho_pagina,
        total_itens=total_itens, total_paginas=total_paginas, itens=itens,
    )


@proteger_erros
def listar_documentos_parados(
    ctx: ContextoApi,
    sujeito: Sujeito,
    tempo_minimo_segundos: float,
    paginacao: Paginacao = Paginacao(),
    ordenacao: Ordenacao = Ordenacao(campo='entrou_na_etapa_em', direcao='asc'),
) -> PaginacaoResponse:
    """GET /magnata-os/documental/parados"""
    exigir_perfil(sujeito, PERMISSAO_LEITURA_GERAL)
    if tempo_minimo_segundos < 0:
        raise FiltroInvalido('tempo_minimo_segundos nao pode ser negativo.')
    validar_paginacao(paginacao)
    validar_ordenacao(ordenacao, CAMPOS_ORDENACAO_DOCUMENTOS)

    agora = ctx.relogio()
    linhas = [
        (documento, item) for documento, item in _construir_linhas_documentos(ctx, agora)
        if item.tempo_na_etapa_segundos is not None and item.tempo_na_etapa_segundos >= tempo_minimo_segundos
    ]
    linhas = _ordenar_seguro(linhas, _EXTRATORES_ORDENACAO_DOCUMENTOS[ordenacao.campo], ordenacao.direcao)
    pagina_linhas, total_itens, total_paginas = _paginar(linhas, paginacao)

    itens = tuple(
        _documento_para_response(documento, item, _buscar_ultimo_evento(ctx, documento.documento_id))
        for documento, item in pagina_linhas
    )
    return PaginacaoResponse(
        pagina=paginacao.pagina, tamanho_pagina=paginacao.tamanho_pagina,
        total_itens=total_itens, total_paginas=total_paginas, itens=itens,
    )
