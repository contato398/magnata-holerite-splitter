"""Adaptador GERAL: `ResultadoResolucaoSemantico` → `ItemInventarioPrestacao`
(missão "CORREDOR OPERACIONAL DA PRESTAÇÃO DE CONTAS", Fase 3).

Hoje existem 2 caminhos para chegar a `ItemInventarioPrestacao`, cada
um específico demais para generalizar:
  - `inventario_prestacao_resultados.py::_converter_resultado` — `if/elif`
    por `TipoDocumental` (só Holerite/Extrato), opera sobre `ResultadoItem`
    (Família B, `importacao_lote/contratos.py` — vocabulário histórico,
    corredor Airtable-shadow ainda em uso, PRESERVADO, nunca removido
    aqui).
  - `documental/modulo01/ponte_prestacao_holerite.py::confirmar_holerite_
    para_inventario` — só Holerite, opera sobre `HoleriteConfirmadoDTO`
    (DTO específico da esteira do Módulo 01, PRESERVADO, nunca removido
    aqui — cláusula pétrea #14: "preservar a ponte Holerite existente
    se sua remoção for arriscada; migrar progressivamente").

Este módulo é o terceiro caminho — GENÉRICO — que qualquer família cujo
motor geral (`resolver_tipo_documental` + `compor_resolucao_semantica`,
PRs #93/#94/#95/#96) já produziu um `ResultadoResolucaoSemantico`
completo pode atravessar, sem `if tipo ==` algum e sem nenhum DTO novo
por família. NUNCA reavalia nada — só LÊ um resultado já composto.

Nunca decide sozinho em caso de ambiguidade/conflito/erro técnico:
qualquer dimensão obrigatória fora de `RESOLVIDA` (com exatamente 1
valor confirmado) devolve `None` — exceção humana, nunca decisão
automática (cláusula pétrea #9). Nunca inventa cliente/vínculo: o
vínculo COLABORADOR→CLIENTE já deve ter sido resolvido ANTES de compor
`resolucao` (por `resolver_clientes_validado`, `vinculos_prestacao.py`)
— este módulo só LÊ a dimensão CLIENTE já resolvida, nunca a calcula.
"""
from __future__ import annotations

from typing import Optional, Tuple

from .contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResultadoResolucaoSemantico,
)
from .prestacao_readiness import ItemInventarioPrestacao


def _valor_unico_resolvido(
    resolucao: ResultadoResolucaoSemantico,
    dimensao: DimensaoResolucao,
) -> Optional[ReferenciaCanonica]:
    resolucao_dimensao = next(
        (item for item in resolucao.resolucoes if item.dimensao == dimensao), None,
    )
    if resolucao_dimensao is None:
        return None
    if resolucao_dimensao.estado != EstadoResolucaoDimensao.RESOLVIDA:
        return None
    if len(resolucao_dimensao.valores_confirmados) != 1:
        return None
    return resolucao_dimensao.valores_confirmados[0]


def resultado_semantico_para_item_inventario(
    documento_id: str,
    resolucao: ResultadoResolucaoSemantico,
    cliente_broadcast: Optional[ReferenciaCanonica] = None,
) -> Optional[ItemInventarioPrestacao]:
    """Converte QUALQUER `ResultadoResolucaoSemantico` já composto (não
    reavalia nada) num `ItemInventarioPrestacao`. Devolve `None` (nunca
    levanta exceção de fonte externa, mesmo princípio já usado pelos 2
    caminhos existentes) quando:
      - TIPO_DOCUMENTAL não está RESOLVIDA com exatamente 1 valor;
      - COMPETENCIA não está RESOLVIDA com exatamente 1 valor;
      - CLIENTE não está RESOLVIDA com exatamente 1 valor E também não
        está NAO_APLICAVEL (documento global — só neste caso o
        `cliente_broadcast` injetado é usado; sem ele, `None`).

    `cliente_broadcast`: quando o PERFIL já decidiu que CLIENTE é
    NAO_APLICAVEL para este documento (documento global/broadcast —
    decisão tomada em `PerfilAplicabilidadeResolucao`, nunca inferida
    aqui), o CHAMADOR informa para qual cliente este item lógico está
    sendo gerado — nunca descoberto/inventado por este módulo (ver
    `itens_para_clientes_broadcast` para múltiplos clientes de uma vez,
    sempre preservando o MESMO `documento_id` — identidade documental
    única, nunca duplicada fisicamente).

    Quando a dimensão COLABORADOR está RESOLVIDA (Holerite, Folha de
    Ponto etc.), o item carrega essa identidade SANITIZADA (`Referencia
    Canonica('COLABORADOR', id)`, nunca CPF/nome) — usado pela
    obrigatoriedade por cardinalidade do Holerite (Adendo de Regra de
    Negócio, `holerite_obrigatorio_prestacao.py`)."""
    tipo = _valor_unico_resolvido(resolucao, DimensaoResolucao.TIPO_DOCUMENTAL)
    if tipo is None:
        return None
    competencia = _valor_unico_resolvido(resolucao, DimensaoResolucao.COMPETENCIA)
    if competencia is None:
        return None

    resolucao_cliente = next(
        (item for item in resolucao.resolucoes if item.dimensao == DimensaoResolucao.CLIENTE), None,
    )
    if resolucao_cliente is None:
        return None
    if resolucao_cliente.estado == EstadoResolucaoDimensao.NAO_APLICAVEL:
        if cliente_broadcast is None:
            return None
        cliente = cliente_broadcast
    else:
        cliente = _valor_unico_resolvido(resolucao, DimensaoResolucao.CLIENTE)
        if cliente is None:
            return None

    colaborador = _valor_unico_resolvido(resolucao, DimensaoResolucao.COLABORADOR)

    return ItemInventarioPrestacao(
        documento_id=documento_id,
        tipo_documental=tipo.entidade_id,
        cliente=cliente,
        competencia=competencia,
        colaborador=colaborador,
    )


def itens_para_multiplos_clientes_do_vinculo(
    documento_id: str,
    resolucao: ResultadoResolucaoSemantico,
) -> Tuple[ItemInventarioPrestacao, ...]:
    """Adendo de Regra de Negócio (Holerite), ponto 5/12: quando a
    dimensão CLIENTE resolveu RESOLVIDA com 2+ valores confirmados —
    um colaborador genuinamente vinculado a mais de um cliente na
    competência, resolvido pelo MESMO `FonteVinculosPrestacao` já
    existente (nunca inferido aqui, nunca filename) — gera 1 item por
    cliente, MESMO `documento_id`/`colaborador` em todos (identidade
    documental única, nunca duplicada fisicamente). Diferente de
    `itens_para_clientes_broadcast`: aqui a lista de clientes vem da
    PRÓPRIA resolução (vínculo real, já apurado), nunca injetada de
    fora — nunca confundir vínculo múltiplo genuíno com broadcast
    (documento global sem cliente nenhum resolvido)."""
    resolucao_cliente = next(
        (item for item in resolucao.resolucoes if item.dimensao == DimensaoResolucao.CLIENTE), None,
    )
    if resolucao_cliente is None or resolucao_cliente.estado != EstadoResolucaoDimensao.RESOLVIDA:
        return ()
    itens = []
    for cliente in resolucao_cliente.valores_confirmados:
        tipo = _valor_unico_resolvido(resolucao, DimensaoResolucao.TIPO_DOCUMENTAL)
        competencia = _valor_unico_resolvido(resolucao, DimensaoResolucao.COMPETENCIA)
        if tipo is None or competencia is None:
            return ()
        colaborador = _valor_unico_resolvido(resolucao, DimensaoResolucao.COLABORADOR)
        itens.append(ItemInventarioPrestacao(
            documento_id=documento_id, tipo_documental=tipo.entidade_id,
            cliente=cliente, competencia=competencia, colaborador=colaborador,
        ))
    return tuple(itens)


def itens_para_clientes_broadcast(
    documento_id: str,
    resolucao: ResultadoResolucaoSemantico,
    clientes: Tuple[ReferenciaCanonica, ...],
) -> Tuple[ItemInventarioPrestacao, ...]:
    """Gera 1 item lógico por cliente da lista informada — MESMO
    `documento_id` em todos (identidade documental única preservada,
    nunca duplicada fisicamente, Fase 11 da missão). A lista de
    clientes é sempre INJETADA por quem chama (nunca descoberta aqui —
    este módulo nunca sabe quantos/quais clientes existem no ciclo;
    isso é responsabilidade de quem orquestra o corredor, cláusula
    pétrea #10: Airtable/cadastro é fonte, nunca o motor documental)."""
    itens = []
    for cliente in clientes:
        item = resultado_semantico_para_item_inventario(documento_id, resolucao, cliente_broadcast=cliente)
        if item is not None:
            itens.append(item)
    return tuple(itens)
