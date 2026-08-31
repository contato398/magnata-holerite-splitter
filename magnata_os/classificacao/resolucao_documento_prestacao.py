"""Orquestrador GENÉRICO de resolução documental da Prestação de Contas
(missão "CORREDOR AUTÔNOMO PÓS-CLASSIFICAÇÃO V1", Fases 2/4/5/6/8/9/10/
12/13/14/20).

Fecha o corredor: texto já extraído -> tipo resolvido (`ponte_conteudo_
motor_semantico`, já existente) -> perfil de aplicabilidade (`perfil_
aplicabilidade_documental`, novo desta missão, consultado SÓ DEPOIS do
tipo resolvido — Fase 2, "nunca o inverso") -> dimensões restantes
resolvidas (competência via `resolucao_semantica.resolucao_competencia_
de_validacao`; colaborador via `identificacao_documental.resolver_
colaborador_de_texto`; cliente via `vinculos_prestacao.resolver_
clientes_validado`, todos já existentes) -> `ResultadoResolucaoSemantico`
consolidado (`resolucao_semantica.compor_resolucao_semantica`, já
existente, NUNCA duplicado) -> item(ns) de inventário
(`adaptador_inventario_prestacao`, já existente, NUNCA duplicado).

Fase 20 ("não criar GrandeOrquestrador2"): este módulo só COMPÕE peças
já existentes na ordem certa — nenhuma delas é reimplementada aqui.

Fase 16 (nunca inventar dado): qualquer dimensão que dependa de uma
fonte não informada (competência esperada ausente, fonte de vínculos
não injetada, colaborador não resolvido para derivar cliente) vira
`NAO_AVALIADA` — nunca um valor resolvido por suposição. Uma dimensão
`NAO_AVALIADA` sempre impede `pronto_para_routing_logico` (comportamento
já existente de `compor_resolucao_semantica`, nunca alterado aqui) —
autoavanço completo só ocorre quando toda evidência necessária já foi
efetivamente fornecida."""
from __future__ import annotations

import dataclasses
import enum
from typing import Optional, Sequence, Tuple

from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario
from magnata_os.documental.importacao_lote.dominio import extrair_competencia_de_texto, validar_competencia

from .adaptador_inventario_prestacao import (
    itens_para_clientes_broadcast,
    itens_para_multiplos_clientes_do_vinculo,
    resultado_semantico_para_item_inventario,
)
from .evidencia_estrutural_documental import analisar_estrutura_documento
from .resolucao_master_documental import EstadoGranularidadeDocumento, detectar_granularidade_documento
from .separacao_documental import IdentificadorDePagina, separar_por_carry_forward, texto_do_grupo
from .contratos import (
    AplicabilidadeDimensao,
    DimensaoResolucao,
    EntradaResolucaoDocumento,
    EstadoResolucaoDimensao,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    ResolucaoDimensao,
    ResultadoResolucaoSemantico,
)
from .identificacao_documental import (
    DocumentoComMultiplasIdentidades,
    multiplas_identidades_para_resolucao_dimensao,
    resolver_colaborador_de_texto,
)
from .inventario_prestacao_memoria import InventarioPrestacaoEmMemoria
from .perfil_aplicabilidade_documental import perfil_para_tipo
from .ponte_conteudo_motor_semantico import resolver_tipo_documental_de_texto
from .prestacao_readiness import ItemInventarioPrestacao
from .reconciliacao_origem_conteudo import (
    ResultadoReconciliacaoOrigem,
    reconciliar_origem_com_tipo_resolvido,
    tipo_resolvido_da_dimensao,
)
from .resolucao_semantica import compor_resolucao_semantica, resolucao_competencia_de_validacao
from .vinculo_unidade_prestacao import (
    FonteUnidadePostoPrestacao,
    FonteVinculoPrestacao,
    resolver_unidade_posto_validado,
    resolver_vinculo_validado,
)
from .vinculos_prestacao import FonteVinculosPrestacao, resolver_clientes_validado


class EstadoCorredorDocumentoPrestacao(str, enum.Enum):
    """Estado FINAL observável do corredor para métrica/observabilidade
    (Fase 20/23) -- nunca uma segunda fonte de verdade sobre RESOLVIDA/
    PARCIAL/etc. (essa continua sendo só `ResultadoResolucaoSemantico.
    estado_consolidado`, quando o corredor chega até lá)."""

    TEXTO_NAO_EXTRAIVEL = 'TEXTO_NAO_EXTRAIVEL'
    TIPO_DESCONHECIDO = 'TIPO_DESCONHECIDO'
    TIPO_AMBIGUO = 'TIPO_AMBIGUO'
    TIPO_CONFLITO = 'TIPO_CONFLITO'
    ORIGEM_CONTEUDO_DIVERGENTE = 'ORIGEM_CONTEUDO_DIVERGENTE'
    PERFIL_NAO_CADASTRADO = 'PERFIL_NAO_CADASTRADO'
    RESOLVIDO_E_AVANCOU = 'RESOLVIDO_E_AVANCOU'
    REVISAO_NECESSARIA = 'REVISAO_NECESSARIA'


@dataclasses.dataclass(frozen=True)
class ContextoResolucaoDocumentoPrestacao:
    """Tudo que o corredor pode precisar, SEMPRE injetado por fora —
    este módulo nunca decide qual fonte usar, nunca acessa Airtable/
    Gmail/armazenamento diretamente (Fase 27: core sem dependência de
    Airtable, confirmado por teste arquitetural)."""

    documento_id: str
    hash_sha256: str
    tipo_origem: Optional[str] = None
    competencia_esperada: Optional[Tuple[int, int]] = None
    candidatos_colaborador: Sequence[CandidatoFuncionario] = ()
    fonte_vinculos: Optional[FonteVinculosPrestacao] = None
    cliente_direto: Optional[ReferenciaCanonica] = None
    """Para famílias de granularidade cliente (ex.: Extrato) cujo
    cliente já é conhecido pela ORIGEM do documento (ex.: um registro
    Airtable já vinculado a 1 cliente) -- nunca inferido aqui, sempre
    informado por quem orquestra a partir de um contexto real."""
    fonte_unidade_posto: Optional[FonteUnidadePostoPrestacao] = None
    """Fonte substituível para a dimensão UNIDADE_POSTO (missão
    "EVIDÊNCIA RELACIONAL DOCUMENTO↔DOCUMENTO + VÍNCULO/UNIDADE_POSTO
    REAIS") -- só consultada quando o perfil do tipo resolvido marca
    UNIDADE_POSTO como aplicável (hoje: só Holerite)."""
    fonte_vinculo_real: Optional[FonteVinculoPrestacao] = None
    """Fonte substituível para a dimensão VINCULO EM SI (corrigido pelo
    adendo pré-merge ao PR #106 -- nunca mais fabricada por espelhamento
    de CLIENTE). Só consultada quando o perfil do tipo resolvido marca
    VINCULO como aplicável -- hoje NENHUM perfil marca (revertido para
    NAO_APLICAVEL até existir uma fonte real de produção; ver
    `perfil_aplicabilidade_documental.py`), então este campo hoje não
    tem efeito em nenhum corredor real -- mantido pronto para quando um
    perfil futuro precisar dele, com prova de necessidade."""
    contexto_fontes_fingerprint: str = 'sem-fontes-externas'


@dataclasses.dataclass(frozen=True)
class ResultadoProcessamentoDocumentoPrestacao:
    documento_id: str
    estado: EstadoCorredorDocumentoPrestacao
    tipo_documental: Optional[str] = None
    perfil: Optional[PerfilAplicabilidadeResolucao] = None
    resolucao_semantica: Optional[ResultadoResolucaoSemantico] = None
    motivo: Optional[str] = None


def _resolver_competencia(
    texto: str, regra_aplicavel: bool, competencia_esperada: Optional[Tuple[int, int]],
) -> ResolucaoDimensao:
    if not regra_aplicavel:
        return ResolucaoDimensao(dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.NAO_APLICAVEL)
    if competencia_esperada is None:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.NAO_AVALIADA,
            metodo='resolucao_documento_prestacao', motivos=('competencia_esperada_nao_informada',),
        )
    ano_esperado, mes_esperado = competencia_esperada
    extraida = extrair_competencia_de_texto(texto)
    resultado_competencia = validar_competencia(extraida, ano_esperado, mes_esperado)
    return resolucao_competencia_de_validacao(resultado_competencia, competencia_esperada)


def _resolver_colaborador(
    texto: str, regra_aplicavel: bool, candidatos: Sequence[CandidatoFuncionario],
) -> ResolucaoDimensao:
    if not regra_aplicavel:
        return ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL)
    resultado = resolver_colaborador_de_texto(texto, candidatos)
    if isinstance(resultado, DocumentoComMultiplasIdentidades):
        return multiplas_identidades_para_resolucao_dimensao(resultado)
    return resultado


def _resolver_cliente(
    regra_aplicavel: bool,
    resolucao_colaborador: ResolucaoDimensao,
    resolucao_competencia: ResolucaoDimensao,
    fonte_vinculos: Optional[FonteVinculosPrestacao],
    cliente_direto: Optional[ReferenciaCanonica],
) -> ResolucaoDimensao:
    if not regra_aplicavel:
        # Família broadcast (Fase 5/10) -- cliente(s) reais são
        # decididos DEPOIS, na composição do item de inventário
        # (`itens_para_clientes_broadcast`, injetado por quem chama),
        # nunca por este módulo.
        return ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_APLICAVEL)

    if cliente_direto is not None:
        # Granularidade cliente (ex.: Extrato) -- cliente já conhecido
        # pela origem, injetado por quem chama, nunca inferido aqui.
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(cliente_direto,), metodo='cliente_direto_da_origem',
        )

    # Granularidade colaborador -- cliente DERIVADO do vínculo
    # (Fase 5: "conteúdo->colaborador->vínculo->cliente(s)"). Exige
    # colaborador resolvido com exatamente 1 valor e competência
    # resolvida -- nunca inventa nenhum dos dois.
    if (
        resolucao_colaborador.estado != EstadoResolucaoDimensao.RESOLVIDA
        or len(resolucao_colaborador.valores_confirmados) != 1
    ):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_AVALIADA,
            metodo='resolucao_documento_prestacao', motivos=('colaborador_nao_resolvido_para_derivar_cliente',),
        )
    if (
        resolucao_competencia.estado != EstadoResolucaoDimensao.RESOLVIDA
        or len(resolucao_competencia.valores_confirmados) != 1
    ):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_AVALIADA,
            metodo='resolucao_documento_prestacao', motivos=('competencia_nao_resolvida_para_derivar_cliente',),
        )
    if fonte_vinculos is None:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_AVALIADA,
            metodo='resolucao_documento_prestacao', motivos=('fonte_vinculos_nao_informada',),
        )
    return resolver_clientes_validado(
        fonte_vinculos,
        resolucao_colaborador.valores_confirmados[0],
        resolucao_competencia.valores_confirmados[0],
    )


def _resolver_unidade_posto(
    regra_aplicavel: bool,
    resolucao_colaborador: ResolucaoDimensao,
    fonte_unidade_posto: Optional[FonteUnidadePostoPrestacao],
    competencia_confirmada: Optional[ReferenciaCanonica],
) -> ResolucaoDimensao:
    if not regra_aplicavel:
        return ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL)
    if (
        resolucao_colaborador.estado != EstadoResolucaoDimensao.RESOLVIDA
        or len(resolucao_colaborador.valores_confirmados) != 1
    ):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_AVALIADA,
            metodo='resolucao_documento_prestacao', motivos=('colaborador_nao_resolvido_para_derivar_unidade_posto',),
        )
    if competencia_confirmada is None:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_AVALIADA,
            metodo='resolucao_documento_prestacao', motivos=('competencia_nao_resolvida_para_derivar_unidade_posto',),
        )
    if fonte_unidade_posto is None:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_AVALIADA,
            metodo='resolucao_documento_prestacao', motivos=('fonte_unidade_posto_nao_informada',),
        )
    return resolver_unidade_posto_validado(
        fonte_unidade_posto, resolucao_colaborador.valores_confirmados[0], competencia_confirmada,
    )


def _resolver_vinculo(
    regra_aplicavel: bool,
    colaborador_resolvido: Optional[ReferenciaCanonica],
    fonte_vinculo_real: Optional[FonteVinculoPrestacao],
    competencia_confirmada: Optional[ReferenciaCanonica],
) -> ResolucaoDimensao:
    """Mesmo padrão de `_resolver_unidade_posto` -- corrigido pelo
    adendo pré-merge ao PR #106: nunca mais fabrica a identidade do
    vínculo por espelhamento de CLIENTE. Só resolve de verdade quando
    uma fonte REAL está disponível; caso contrário fica `NAO_AVALIADA`
    (nunca `RESOLVIDA` por decreto)."""
    if not regra_aplicavel:
        return ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL)
    if colaborador_resolvido is None:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_AVALIADA,
            metodo='resolucao_documento_prestacao', motivos=('colaborador_nao_resolvido_para_derivar_vinculo',),
        )
    if competencia_confirmada is None:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_AVALIADA,
            metodo='resolucao_documento_prestacao', motivos=('competencia_nao_resolvida_para_derivar_vinculo',),
        )
    if fonte_vinculo_real is None:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_AVALIADA,
            metodo='resolucao_documento_prestacao', motivos=('fonte_vinculo_real_nao_informada',),
        )
    return resolver_vinculo_validado(fonte_vinculo_real, colaborador_resolvido, competencia_confirmada)


def processar_documento_prestacao(
    texto: Optional[str],
    contexto: ContextoResolucaoDocumentoPrestacao,
) -> ResultadoProcessamentoDocumentoPrestacao:
    """Ponto único de entrada do corredor pós-classificação. Pura, sem
    I/O direto (tudo que precisa de I/O já chega INJETADO em `contexto`
    — `fonte_vinculos`, candidatos, competência esperada)."""
    if texto is None:
        return ResultadoProcessamentoDocumentoPrestacao(
            documento_id=contexto.documento_id,
            estado=EstadoCorredorDocumentoPrestacao.TEXTO_NAO_EXTRAIVEL,
            motivo='texto_nao_extraivel',
        )

    resolucao_tipo = resolver_tipo_documental_de_texto(texto)

    if resolucao_tipo.estado == EstadoResolucaoDimensao.AMBIGUA:
        return ResultadoProcessamentoDocumentoPrestacao(
            documento_id=contexto.documento_id,
            estado=EstadoCorredorDocumentoPrestacao.TIPO_AMBIGUO,
            motivo='tipo_documental_ambiguo',
        )
    if resolucao_tipo.estado == EstadoResolucaoDimensao.CONFLITO:
        return ResultadoProcessamentoDocumentoPrestacao(
            documento_id=contexto.documento_id,
            estado=EstadoCorredorDocumentoPrestacao.TIPO_CONFLITO,
            motivo='tipo_documental_conflito',
        )
    if resolucao_tipo.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA:
        return ResultadoProcessamentoDocumentoPrestacao(
            documento_id=contexto.documento_id,
            estado=EstadoCorredorDocumentoPrestacao.TIPO_DESCONHECIDO,
            motivo='tipo_documental_desconhecido',
        )
    # RESOLVIDA -- resolver_tipo_documental_de_texto só produz estes 4
    # estados (ver resolucao_tipo_documental.py); fail-safe simétrico ao
    # já usado em politica_classificacao_semantica.py.
    if resolucao_tipo.estado != EstadoResolucaoDimensao.RESOLVIDA:
        raise ValueError(f'EstadoResolucaoDimensao inesperado para TIPO_DOCUMENTAL: {resolucao_tipo.estado!r}')

    tipo = tipo_resolvido_da_dimensao(resolucao_tipo)

    if contexto.tipo_origem is not None:
        reconciliacao = reconciliar_origem_com_tipo_resolvido(contexto.tipo_origem, tipo)
        if reconciliacao.resultado == ResultadoReconciliacaoOrigem.CONFLITO:
            return ResultadoProcessamentoDocumentoPrestacao(
                documento_id=contexto.documento_id,
                estado=EstadoCorredorDocumentoPrestacao.ORIGEM_CONTEUDO_DIVERGENTE,
                tipo_documental=tipo,
                motivo=(
                    f'origem={reconciliacao.tipo_origem!r} diverge do '
                    f'conteudo={reconciliacao.tipo_resolvido!r}'
                ),
            )

    perfil = perfil_para_tipo(tipo)
    if perfil is None:
        return ResultadoProcessamentoDocumentoPrestacao(
            documento_id=contexto.documento_id,
            estado=EstadoCorredorDocumentoPrestacao.PERFIL_NAO_CADASTRADO,
            tipo_documental=tipo,
            motivo='tipo_sem_perfil_de_aplicabilidade_cadastrado',
        )

    regra_competencia = perfil.regra_para(DimensaoResolucao.COMPETENCIA)
    regra_colaborador = perfil.regra_para(DimensaoResolucao.COLABORADOR)
    regra_cliente = perfil.regra_para(DimensaoResolucao.CLIENTE)
    regra_unidade_posto = perfil.regra_para(DimensaoResolucao.UNIDADE_POSTO)
    regra_vinculo = perfil.regra_para(DimensaoResolucao.VINCULO)

    resolucao_competencia = _resolver_competencia(
        texto, regra_competencia.aplicabilidade != AplicabilidadeDimensao.NAO_APLICAVEL,
        contexto.competencia_esperada,
    )
    resolucao_colaborador = _resolver_colaborador(
        texto, regra_colaborador.aplicabilidade != AplicabilidadeDimensao.NAO_APLICAVEL,
        contexto.candidatos_colaborador,
    )
    resolucao_cliente = _resolver_cliente(
        regra_cliente.aplicabilidade != AplicabilidadeDimensao.NAO_APLICAVEL,
        resolucao_colaborador, resolucao_competencia, contexto.fonte_vinculos, contexto.cliente_direto,
    )
    competencia_confirmada = (
        resolucao_competencia.valores_confirmados[0]
        if resolucao_competencia.estado == EstadoResolucaoDimensao.RESOLVIDA
        and len(resolucao_competencia.valores_confirmados) == 1
        else None
    )
    colaborador_confirmado = (
        resolucao_colaborador.valores_confirmados[0]
        if resolucao_colaborador.estado == EstadoResolucaoDimensao.RESOLVIDA
        and len(resolucao_colaborador.valores_confirmados) == 1
        else None
    )
    resolucao_unidade_posto = _resolver_unidade_posto(
        regra_unidade_posto.aplicabilidade != AplicabilidadeDimensao.NAO_APLICAVEL,
        resolucao_colaborador, contexto.fonte_unidade_posto, competencia_confirmada,
    )
    resolucao_vinculo = _resolver_vinculo(
        regra_vinculo.aplicabilidade != AplicabilidadeDimensao.NAO_APLICAVEL,
        colaborador_confirmado, contexto.fonte_vinculo_real, competencia_confirmada,
    )

    entrada = EntradaResolucaoDocumento(
        documento_id=contexto.documento_id,
        hash_sha256=contexto.hash_sha256,
        resolver_id='resolucao_documento_prestacao',
        resolver_version='1',
        politica_id=perfil.perfil_id,
        politica_version=perfil.version,
        contexto_fontes_fingerprint=contexto.contexto_fontes_fingerprint,
    )
    resultado = compor_resolucao_semantica(
        entrada=entrada, perfil=perfil,
        resolucoes=(
            resolucao_tipo, resolucao_competencia, resolucao_cliente,
            resolucao_unidade_posto, resolucao_colaborador, resolucao_vinculo,
        ),
    )

    estado_corredor = (
        EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU if resultado.pronto_para_routing_logico
        else EstadoCorredorDocumentoPrestacao.REVISAO_NECESSARIA
    )
    return ResultadoProcessamentoDocumentoPrestacao(
        documento_id=contexto.documento_id, estado=estado_corredor,
        tipo_documental=tipo, perfil=perfil, resolucao_semantica=resultado,
    )


def avancar_para_inventario(
    resultado: ResultadoProcessamentoDocumentoPrestacao,
    sink: InventarioPrestacaoEmMemoria,
    clientes_broadcast: Tuple[ReferenciaCanonica, ...] = (),
) -> Tuple[ItemInventarioPrestacao, ...]:
    """Fase 7/14 (auto-avanço completo): só age quando o documento já
    está RESOLVIDO_E_AVANCOU (`pronto_para_routing_logico=True`) —
    qualquer outro estado devolve `()` sem tocar o sink (nunca inventa
    inventário a partir de uma resolução incompleta/ambígua/conflitante).

    Decide qual adaptador genérico já existente usar (nunca um `if
    tipo ==`) olhando só o ESTADO da dimensão CLIENTE, já resolvida:
      - RESOLVIDA com 1 valor -> `resultado_semantico_para_item_inventario`;
      - RESOLVIDA com 2+ valores (vínculo múltiplo genuíno) ->
        `itens_para_multiplos_clientes_do_vinculo`;
      - NAO_APLICAVEL (família broadcast) -> `itens_para_clientes_
        broadcast`, usando a lista INJETADA por quem chama (nunca
        descoberta aqui).

    Idempotente: delega a `InventarioPrestacaoEmMemoria.adicionar_
    muitos`, que já deduplica por `documento_id` -- processar o MESMO
    documento duas vezes nunca duplica itens (Fase 21)."""
    if resultado.estado != EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU:
        return ()
    resolucao = resultado.resolucao_semantica
    resolucao_cliente = next(
        (item for item in resolucao.resolucoes if item.dimensao == DimensaoResolucao.CLIENTE), None,
    )

    if resolucao_cliente is not None and resolucao_cliente.estado == EstadoResolucaoDimensao.NAO_APLICAVEL:
        itens = itens_para_clientes_broadcast(resultado.documento_id, resolucao, clientes_broadcast)
    elif resolucao_cliente is not None and len(resolucao_cliente.valores_confirmados) >= 2:
        itens = itens_para_multiplos_clientes_do_vinculo(resultado.documento_id, resolucao)
    else:
        item = resultado_semantico_para_item_inventario(resultado.documento_id, resolucao)
        itens = (item,) if item is not None else ()

    sink.adicionar_muitos(itens)
    return itens


def processar_documento_com_separacao_se_necessaria(
    paginas: Sequence[str],
    contexto_base: ContextoResolucaoDocumentoPrestacao,
    identificar_pagina: Optional[IdentificadorDePagina] = None,
    personalizar_contexto_do_grupo=None,
) -> Tuple[ResultadoProcessamentoDocumentoPrestacao, ...]:
    """Fase 7 (separação): "não assumir que 1 PDF = 1 documento lógico".
    Reaproveita 100% dos detectores/engine JÁ EXISTENTES (`evidencia_
    estrutural_documental.analisar_estrutura_documento`, `resolucao_
    master_documental.detectar_granularidade_documento`, `separacao_
    documental.separar_por_carry_forward`) — nunca uma segunda engine
    de separação.

    - UNITARIO ou INCONCLUSIVO -> processa o documento inteiro como 1
      só (`texto = '\\n'.join(paginas)`), devolve 1 resultado.
    - POTENCIALMENTE_MASTER -> exige `identificar_pagina` (estratégia
      plugável já existente, ex.: `estrategia_por_cpf_colaborador`);
      sem ela, este módulo NUNCA decide sozinho como separar — devolve
      o documento INTEIRO como 1 resultado (mesmo caminho de
      INCONCLUSIVO), deixando o motor semântico decidir sobre o texto
      combinado (Fase 26: nunca inventa uma estratégia de separação
      só porque o documento parece ser master).
    - Com `identificar_pagina`: separa em grupos (`GrupoSeparado`) e
      REENTRA cada filho no MESMO `processar_documento_prestacao`
      (Fase 7: "cada filho retorna ao MESMO motor semântico"), com
      identidade PRÓPRIA derivada (`documento_id:entidade_id`, nunca o
      mesmo id do pai — Fase 7: "identidade própria derivada/
      proveniente"). Páginas em `indices_sem_grupo` NUNCA viram um
      documento — ficam de fora, nunca inventadas como grupo.

    `personalizar_contexto_do_grupo(contexto_filho, grupo) ->
    ContextoResolucaoDocumentoPrestacao`: hook OPCIONAL, injetado por
    quem chama — este módulo é agnóstico ao SIGNIFICADO de
    `grupo.entidade_id` (pode ser um cliente, um colaborador, ou
    qualquer outra granularidade futura, conforme a estratégia de
    `identificar_pagina` usada), nunca decide isso sozinho. Ex.: para
    separação por CNPJ de cliente, o chamador usa este hook para
    preencher `cliente_direto=ReferenciaCanonica('CLIENTE',
    grupo.entidade_id)` no contexto do filho — sem o hook, o contexto
    do filho é idêntico ao do pai (só com `documento_id` renomeado)."""
    evidencia = analisar_estrutura_documento(paginas)
    decisao = detectar_granularidade_documento(evidencia)

    if decisao.estado != EstadoGranularidadeDocumento.POTENCIALMENTE_MASTER or identificar_pagina is None:
        texto_completo = '\n'.join(paginas) if paginas else None
        return (processar_documento_prestacao(texto_completo, contexto_base),)

    separacao = separar_por_carry_forward(paginas, identificar_pagina)
    resultados = []
    for grupo in separacao.grupos:
        texto_filho = texto_do_grupo(paginas, grupo)
        contexto_filho = dataclasses.replace(
            contexto_base, documento_id=f'{contexto_base.documento_id}:{grupo.entidade_id}',
        )
        if personalizar_contexto_do_grupo is not None:
            contexto_filho = personalizar_contexto_do_grupo(contexto_filho, grupo)
        resultados.append(processar_documento_prestacao(texto_filho, contexto_filho))
    return tuple(resultados)
