"""Compositor geral de resolução semântica documental — o componente que
faltava, segundo a auditoria da missão "AUDITORIA E RECONCILIAÇÃO DA
CAMADA DE RECONHECIMENTO DOCUMENTAL, FASE 2E": os contratos
(`DimensaoResolucao`, `EstadoResolucaoDimensao`, `NivelConfianca`,
`EvidenciaSanitizada`, `ResolucaoDimensao`, `ResultadoResolucaoSemantico`,
`MetadadosExecucaoResolucao`, `EntradaResolucaoDocumento`,
`PerfilAplicabilidadeResolucao` — todos em `contratos.py`) já eram
suficientes; faltava só QUEM os compõe.

O QUE ESTE MÓDULO É: um COMPOSITOR puro, sem I/O, sem conhecimento de
nenhum tipo documental específico. Recebe resoluções dimensionais JÁ
PRODUZIDAS por especialistas (classificador de tipo, identificação de
colaborador, vínculo de cliente, validação de competência — cada um
continua vivendo no seu próprio módulo, sem alteração de responsabilidade)
e monta UM `ResultadoResolucaoSemantico` consolidado, reaproveitando
inteiramente as invariantes estruturais que `ResultadoResolucaoSemantico.
__post_init__`/`ResolucaoDimensao.validar_contra` já impõem (conjunto de
dimensões == perfil, cardinalidade, coerência de NAO_APLICAVEL) — este
módulo nunca duplica essa validação, só decide o resultado CONSOLIDADO.

O QUE ESTE MÓDULO NUNCA FAZ (por desenho, não por esquecimento):
  - nunca classifica PDF (isso é `classificador_documental.py`);
  - nunca extrai texto (isso é `extracao_texto.py`);
  - nunca lê Airtable/Gmail/Postgres (nenhum I/O aqui, nenhum adapter);
  - nunca resolve CPF/CNPJ diretamente (isso é `resolver_funcionario`/
    `resolver_cliente`, importacao_lote/dominio.py);
  - nunca calcula competência esperada (isso é
    `competencia_esperada_prestacao.py`);
  - nunca escreve/avança esteira (isso é `ServicoAvancoEsteira`);
  - nunca conhece "Holerite" nem qualquer outro tipo documental por
    nome -- recebe `ResolucaoDimensao` já prontas, agnóstico ao
    conteúdo delas.

`resolucao_competencia_de_validacao` (abaixo) É a única tradução extra
que este módulo hospeda -- porque `ResultadoCompetencia` (importacao_
lote/contratos.py) não tem, ele mesmo, um dono natural dentro do pacote
`classificacao/` (mesma direção de dependência já usada por
`inventario_prestacao_resultados.py`: `classificacao/` pode importar
`importacao_lote/contratos.py`, nunca o contrário). Não é conhecimento
de Holerite -- é tradução de COMPETÊNCIA, genérica a qualquer tipo
documental que precise dela.
"""
from __future__ import annotations

from typing import Optional, Tuple

from ..documental.importacao_lote.contratos import ResultadoCompetencia
from .contratos import (
    ConfiancaResolucao,
    DimensaoResolucao,
    EntradaResolucaoDocumento,
    EstadoResolucaoDimensao,
    EstadoResultadoSemantico,
    NivelConfianca,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    ResolucaoDimensao,
    ResultadoResolucaoSemantico,
)

# Estados de ResolucaoDimensao que nunca exigem revisão humana e nunca
# impedem "pronto_para_routing_logico" -- uma dimensão RESOLVIDA (valor
# confirmado) ou NAO_APLICAVEL (o perfil explicitamente não pediu esta
# dimensão) são as duas únicas formas "limpas" de uma dimensão.
_ESTADOS_LIMPOS = frozenset({
    EstadoResolucaoDimensao.RESOLVIDA,
    EstadoResolucaoDimensao.NAO_APLICAVEL,
})


def compor_resolucao_semantica(
    entrada: EntradaResolucaoDocumento,
    perfil: PerfilAplicabilidadeResolucao,
    resolucoes: Tuple[ResolucaoDimensao, ...],
) -> ResultadoResolucaoSemantico:
    """Compõe um `ResultadoResolucaoSemantico` a partir de resoluções
    dimensionais já prontas. Determinístico e sem efeito colateral --
    mesmas `resolucoes`/`perfil`/`entrada` (logicamente iguais) sempre
    produzem o mesmo resultado, inclusive o mesmo `semantic_result_id`
    (hash canônico já calculado pelo próprio contrato).

    NUNCA reavalia se uma dimensão está certa -- confia inteiramente no
    que o especialista de cada dimensão já decidiu. A única decisão
    tomada aqui é a CONSOLIDAÇÃO: qual o estado geral, se precisa de
    revisão humana, se está pronto para roteamento lógico.

    Fail-loud herdado do próprio contrato: se `resolucoes` não cobrir
    exatamente as dimensões do `perfil`, ou violar cardinalidade, ou
    tiver uma dimensão NAO_APLICAVEL fora de uma regra NAO_APLICAVEL
    (ou vice-versa), a construção de `ResultadoResolucaoSemantico`
    abaixo levanta `ValueError` -- este módulo não amortece nem
    reinterpreta esse erro (erro de composição é erro de quem chama,
    nunca um estado de negócio).

    Regra de consolidação (precedência, do mais grave ao mais leve):
      1. qualquer dimensão ERRO_TECNICO -> ERRO_TECNICO consolidado
         (nunca convertido em ausência/NAO_ENCONTRADA);
      2. qualquer dimensão INVALIDA (e nenhuma ERRO_TECNICO) ->
         INVALIDA consolidado;
      3. todas as dimensões "limpas" (RESOLVIDA ou NAO_APLICAVEL) ->
         RESOLVIDA consolidado, pronto para routing lógico;
      4. ao menos uma dimensão RESOLVIDA, mas nem todas limpas ->
         PARCIAL;
      5. nenhuma dimensão RESOLVIDA (só AMBIGUA/CONFLITO/
         NAO_ENCONTRADA/NAO_AVALIADA) -> INCONCLUSIVA.

    `necessita_revisao_humana` é sempre o inverso de "estado_consolidado
    == RESOLVIDA" -- nenhum meio-termo silencioso; `pronto_para_
    routing_logico` idem."""
    tem_erro_tecnico = any(
        resolucao.estado == EstadoResolucaoDimensao.ERRO_TECNICO for resolucao in resolucoes
    )
    tem_invalida = any(
        resolucao.estado == EstadoResolucaoDimensao.INVALIDA for resolucao in resolucoes
    )
    todas_limpas = all(resolucao.estado in _ESTADOS_LIMPOS for resolucao in resolucoes)
    alguma_resolvida = any(
        resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA for resolucao in resolucoes
    )

    if tem_erro_tecnico:
        estado_consolidado = EstadoResultadoSemantico.ERRO_TECNICO
    elif tem_invalida:
        estado_consolidado = EstadoResultadoSemantico.INVALIDA
    elif todas_limpas:
        estado_consolidado = EstadoResultadoSemantico.RESOLVIDA
    elif alguma_resolvida:
        estado_consolidado = EstadoResultadoSemantico.PARCIAL
    else:
        estado_consolidado = EstadoResultadoSemantico.INCONCLUSIVA

    necessita_revisao_humana = estado_consolidado != EstadoResultadoSemantico.RESOLVIDA
    pronto_para_routing_logico = estado_consolidado == EstadoResultadoSemantico.RESOLVIDA

    motivos_consolidados = tuple(sorted({
        motivo for resolucao in resolucoes for motivo in resolucao.motivos
    }))

    return ResultadoResolucaoSemantico(
        documento_id=entrada.documento_id,
        resolver_id=entrada.resolver_id,
        resolver_version=entrada.resolver_version,
        politica_id=entrada.politica_id,
        politica_version=entrada.politica_version,
        perfil=perfil,
        resolucoes=resolucoes,
        estado_consolidado=estado_consolidado,
        necessita_revisao_humana=necessita_revisao_humana,
        motivos_consolidados=motivos_consolidados,
        pronto_para_routing_logico=pronto_para_routing_logico,
    )


def resolucao_competencia_de_validacao(
    resultado_competencia: ResultadoCompetencia,
    ano_mes_esperado: Optional[Tuple[int, int]],
) -> ResolucaoDimensao:
    """Traduz o resultado de `validar_competencia` (importacao_lote/
    dominio.py, já pura e reaproveitada sem alteração) para
    `ResolucaoDimensao` da dimensão COMPETENCIA. Genérico a qualquer
    tipo documental que precise validar competência -- nunca assume
    Holerite nem qualquer outro tipo.

    `ano_mes_esperado` só é usado quando `resultado_competencia ==
    CONFIRMADA` (o único caso em que observada e esperada coincidem) --
    nunca copiado de "observada" isoladamente, e nunca usado para
    inventar um valor quando o resultado não é CONFIRMADA."""
    if resultado_competencia == ResultadoCompetencia.CONFIRMADA:
        if ano_mes_esperado is None:
            raise ValueError("resultado CONFIRMADA exige ano_mes_esperado")
        ano, mes = ano_mes_esperado
        referencia = ReferenciaCanonica("COMPETENCIA", f"{ano:04d}-{mes:02d}")
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.COMPETENCIA,
            estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(referencia,),
            metodo="validar_competencia",
            confianca=ConfiancaResolucao(NivelConfianca.FORTE),
        )
    if resultado_competencia == ResultadoCompetencia.DIVERGENTE:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.COMPETENCIA,
            estado=EstadoResolucaoDimensao.CONFLITO,
            metodo="validar_competencia",
            motivos=("competencia_divergente",),
        )
    if resultado_competencia == ResultadoCompetencia.AMBIGUA:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.COMPETENCIA,
            estado=EstadoResolucaoDimensao.AMBIGUA,
            metodo="validar_competencia",
            motivos=("competencia_ambigua_no_documento",),
        )
    if resultado_competencia == ResultadoCompetencia.NAO_EXTRAIVEL:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.COMPETENCIA,
            estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
            metodo="validar_competencia",
            motivos=("competencia_nao_extraivel",),
        )

    # ResultadoCompetencia é um enum fechado com só as 4 branches acima
    # -- fail-safe explícito, nunca traduz por omissão.
    raise ValueError(
        f"ResultadoCompetencia sem tradução para ResolucaoDimensao: {resultado_competencia!r}")
