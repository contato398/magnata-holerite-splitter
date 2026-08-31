"""Dimensões VINCULO e UNIDADE_POSTO como resoluções REAIS (missão
"EVIDÊNCIA RELACIONAL DOCUMENTO↔DOCUMENTO + VÍNCULO/UNIDADE_POSTO REAIS",
Fase 2/3/4; corrigido pelo "ADENDO PRÉ-MERGE AO PR #106 — CORREÇÃO DA
SEMÂNTICA DE VÍNCULO HISTÓRICO").

CORREÇÃO (adendo pré-merge, achado real): a primeira versão deste
módulo resolvia VINCULO por ESPELHAMENTO da resolução já feita para
CLIENTE — fabricando `ReferenciaCanonica('VINCULO',
f'{colaborador}:{cliente}')` a partir de 2 IDs já resolvidos. Isso NÃO
é evidência real de vínculo: é uma identidade derivada artificialmente
só para satisfazer o compositor semântico, e a resolução herdada
carimbava `RESOLVIDA` mesmo quando a única fonte era vínculo CORRENTE
sendo usado para uma competência HISTÓRICA — o motivo sanitizado
(`MOTIVO_VINCULO_ATUAL_COMO_PROXY`) não mudava o SIGNIFICADO do estado
`RESOLVIDA`, o que violava a regra "vínculo corrente não prova vínculo
histórico".

CORRIGIDO: VINCULO agora segue o MESMO padrão de UNIDADE_POSTO —
resolvido exclusivamente por uma fonte REAL via `Protocol`
(`FonteVinculoPrestacao.resolver_vinculo`), nunca fabricado aqui. A
responsabilidade de decidir se uma competência histórica está
realmente comprovada (e não só "vínculo corrente sendo usado como
proxy") é da FONTE, exatamente como já era o desenho de
`FonteUnidadePostoPrestacao` desde a primeira versão deste módulo —
nunca uma segunda regra paralela aqui. Nenhuma fonte real de produção
para VINCULO existe ainda (só o Protocol e fontes fake de teste) — por
isso `perfil_aplicabilidade_documental.py` mantém VINCULO
`NAO_APLICAVEL` em todo perfil (§4 do adendo: "não quebrar o corredor
atual" — nunca inventar uma resolução falsa só para não bloquear o
compositor). A capacidade fica pronta e testada isoladamente para
quando uma fonte real existir.

CLIENTE continua resolvido pelo mecanismo já existente
(`vinculos_prestacao.FonteVinculosPrestacao`, via
`resolver_clientes_validado`) — este módulo nunca duplica isso.
CLIENTE responde "para qual cliente este documento se aplica?";
VINCULO responde "qual relação real colaborador/posto/cliente
sustenta essa aplicação?" — perguntas distintas, nunca fundidas
(cláusula geral `/CLAUDE.md` §4: dimensões nunca fundidas).

Fluxo real (§2 da missão original): COLABORADOR → VÍNCULO →
UNIDADE/POSTO → CLIENTE. `vinculos_prestacao.FonteVinculosPrestacao`
já resolve CLIENTE a partir de COLABORADOR **ou** de UNIDADE_POSTO
(`_ORIGENS_SUPORTADAS` já incluía `UNIDADE_POSTO` desde antes da
missão original — a porta já antecipava este fluxo).

UNIDADE_POSTO: produtor real via `FonteUnidadePostoPrestacao`
(cardinalidade múltipla genuína quando o colaborador tem mais de um
posto na mesma competência — nunca escolhido arbitrariamente, §3 da
missão original). A responsabilidade de temporalidade (§5 do adendo:
"se a fonte só conhece posto corrente e a competência é histórica, não
declarar UNIDADE_POSTO histórica como RESOLVIDA sem evidência de
vigência") já era, desde a primeira versão, inteiramente da FONTE —
este módulo só delega e valida invariantes estruturais, nunca decide
nem sobrescreve o que a fonte devolveu."""
from __future__ import annotations

from typing import Optional, Protocol, Tuple

from .contratos import DimensaoResolucao, ReferenciaCanonica, ResolucaoDimensao

MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA = 'vinculo_historico_sem_evidencia_de_vigencia'
"""Vocabulário sanitizado disponível para qualquer fonte REAL de
`FonteVinculoPrestacao`/`FonteUnidadePostoPrestacao` anexar em
`ResolucaoDimensao.motivos` quando ela só conhece o vínculo/posto
CORRENTE e não consegue provar vigência para a competência histórica
pedida (ela mesma decide o estado — tipicamente `NAO_ENCONTRADA` — este
módulo nunca decide por ela). Não é usado, produzido ou interpretado
por nenhuma função deste módulo -- só oferecido para consistência de
vocabulário entre fontes futuras, evitando cada uma inventar seu
próprio código de motivo para a mesma situação."""


class FonteUnidadePostoPrestacao(Protocol):
    """Fonte substituível para a dimensão UNIDADE_POSTO — nunca
    Airtable diretamente (Protocol duck-typed). A fonte é inteiramente
    responsável pela correção temporal da resposta (ver docstring do
    módulo) -- este módulo nunca reavalia isso."""

    def resolver_unidade_posto(
        self, colaborador: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> ResolucaoDimensao: ...


def resolver_unidade_posto_validado(
    fonte: FonteUnidadePostoPrestacao,
    colaborador: ReferenciaCanonica,
    competencia: ReferenciaCanonica,
) -> ResolucaoDimensao:
    """Executa a porta e valida só as invariantes estruturais — mesmo
    padrão de `vinculos_prestacao.resolver_clientes_validado`, nunca
    duplicado."""
    if colaborador.tipo_entidade != 'COLABORADOR':
        raise ValueError('colaborador deve ser referencia canonica de COLABORADOR')
    if competencia.tipo_entidade != 'COMPETENCIA':
        raise ValueError('competencia deve ser referencia canonica de COMPETENCIA')

    resultado = fonte.resolver_unidade_posto(colaborador, competencia)
    if resultado.dimensao != DimensaoResolucao.UNIDADE_POSTO:
        raise ValueError('resolucao de unidade/posto deve pertencer a dimensao UNIDADE_POSTO')
    referencias = resultado.valores_confirmados + resultado.candidatos
    if any(referencia.tipo_entidade != 'UNIDADE_POSTO' for referencia in referencias):
        raise ValueError('resolucao de unidade/posto aceita somente referencias UNIDADE_POSTO')
    return resultado


class FonteVinculoPrestacao(Protocol):
    """Fonte substituível para a dimensão VINCULO EM SI — nunca
    fabricada a partir de COLABORADOR+CLIENTE (correção do adendo
    pré-merge). Mesmo padrão de `FonteUnidadePostoPrestacao`: a fonte é
    inteiramente responsável por decidir se tem evidência real de
    vínculo para a competência pedida (corrente ou historicamente
    comprovada) -- este módulo nunca reavalia, nunca fabrica identidade,
    nunca promove vínculo corrente a verdade histórica."""

    def resolver_vinculo(
        self, colaborador: ReferenciaCanonica, competencia: ReferenciaCanonica,
    ) -> ResolucaoDimensao: ...


def resolver_vinculo_validado(
    fonte: FonteVinculoPrestacao,
    colaborador: ReferenciaCanonica,
    competencia: ReferenciaCanonica,
) -> ResolucaoDimensao:
    """Executa a porta e valida só as invariantes estruturais — mesmo
    padrão de `resolver_unidade_posto_validado`. Nunca fabrica
    `ReferenciaCanonica('VINCULO', ...)` aqui: a identidade do vínculo
    (qualquer que seja seu formato -- decisão de quem implementa a
    fonte real) vem inteiramente de `fonte.resolver_vinculo`."""
    if colaborador.tipo_entidade != 'COLABORADOR':
        raise ValueError('colaborador deve ser referencia canonica de COLABORADOR')
    if competencia.tipo_entidade != 'COMPETENCIA':
        raise ValueError('competencia deve ser referencia canonica de COMPETENCIA')

    resultado = fonte.resolver_vinculo(colaborador, competencia)
    if resultado.dimensao != DimensaoResolucao.VINCULO:
        raise ValueError('resolucao de vinculo deve pertencer a dimensao VINCULO')
    referencias = resultado.valores_confirmados + resultado.candidatos
    if any(referencia.tipo_entidade != 'VINCULO' for referencia in referencias):
        raise ValueError('resolucao de vinculo aceita somente referencias VINCULO')
    return resultado
