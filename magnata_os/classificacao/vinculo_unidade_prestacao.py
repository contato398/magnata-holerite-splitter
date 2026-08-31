"""Dimensões VINCULO e UNIDADE_POSTO como resoluções REAIS (missão
"EVIDÊNCIA RELACIONAL DOCUMENTO↔DOCUMENTO + VÍNCULO/UNIDADE_POSTO REAIS",
Fase 2/3/4).

Fluxo real (§2 da missão): COLABORADOR → VÍNCULO → UNIDADE/POSTO →
CLIENTE. `vinculos_prestacao.FonteVinculosPrestacao` já resolve CLIENTE
a partir de COLABORADOR **ou** de UNIDADE_POSTO (`_ORIGENS_SUPORTADAS`
já incluía `UNIDADE_POSTO` desde antes desta missão — a porta já
antecipava este fluxo, nunca reimplementado aqui). O que faltava:

1. um produtor REAL para a dimensão UNIDADE_POSTO (posto/local do
   colaborador, com cardinalidade múltipla genuína quando o colaborador
   tem mais de um posto na mesma competência — nunca escolhido
   arbitrariamente, §3 da missão);
2. expor VÍNCULO como sua PRÓPRIA dimensão (não só um mecanismo
   implícito por trás de CLIENTE) — este módulo faz isso por
   ESPELHAMENTO da resolução de CLIENTE já feita via vínculo, nunca
   reavaliando nada (`resolucao_vinculo_a_partir_de_cliente`).

TEMPORALIDADE (§4 da missão): o cadastro hoje só expõe vínculo
CORRENTE — confirmado por auditoria live anterior (nenhum campo de
vigência/período no schema Airtable de Funcionário/Local, sessão
anterior desta mesma missão macro). NUNCA promovido a "verdade
histórica": quando a competência avaliada não é a competência corrente
(injetada de fora, nunca lida do relógio aqui), a resolução carrega o
motivo sanitizado `MOTIVO_VINCULO_ATUAL_COMO_PROXY` — reaproveitando
`ResolucaoDimensao.motivos` (campo já existente) em vez de criar um
enum/estado novo (cláusula da missão: "não criar enum se contrato
existente já representa a incerteza")."""
from __future__ import annotations

from typing import Optional, Protocol, Tuple

from .contratos import DimensaoResolucao, EstadoResolucaoDimensao, ReferenciaCanonica, ResolucaoDimensao

MOTIVO_VINCULO_ATUAL_COMO_PROXY = 'vinculo_atual_usado_como_proxy_para_competencia_historica'


class FonteUnidadePostoPrestacao(Protocol):
    """Fonte substituível para a dimensão UNIDADE_POSTO — nunca
    Airtable diretamente (Protocol duck-typed, mesmo padrão de
    `FonteVinculosPrestacao`)."""

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


def _referencia_vinculo(colaborador: ReferenciaCanonica, cliente: ReferenciaCanonica) -> ReferenciaCanonica:
    """Identidade do vínculo -- combinação determinística de 2 IDs JÁ
    resolvidos (colaborador + cliente), nunca um dado inventado. Mesmo
    princípio de `dominio_versionamento.calcular_documento_logico_id`:
    identidade derivada de IDs existentes, nunca PII, nunca um novo
    identificador externo fabricado."""
    return ReferenciaCanonica('VINCULO', f'{colaborador.entidade_id}:{cliente.entidade_id}')


def resolucao_vinculo_a_partir_de_cliente(
    colaborador: ReferenciaCanonica,
    resolucao_cliente: ResolucaoDimensao,
    competencia_e_corrente: bool,
) -> ResolucaoDimensao:
    """Espelha o estado já decidido para a dimensão CLIENTE (resolvida
    via vínculo por `vinculos_prestacao.resolver_clientes_validado`,
    NUNCA reavaliado aqui) como a dimensão VINCULO em si. Mesmo estado,
    mesmos candidatos/valores (traduzidos para identidade VINCULO),
    mesma confiança -- só adiciona o motivo de temporalidade quando a
    competência avaliada não é a corrente (§4 da missão).

    `competencia_e_corrente`: decidido por quem chama (nunca lido do
    relógio aqui, cláusula pétrea de competência "entra uma vez, na
    borda") -- comparação entre a competência sendo avaliada e a
    competência atual do ciclo."""
    if resolucao_cliente.dimensao != DimensaoResolucao.CLIENTE:
        raise ValueError('resolucao_cliente deve ser da dimensao CLIENTE')

    motivos = resolucao_cliente.motivos
    if resolucao_cliente.estado == EstadoResolucaoDimensao.RESOLVIDA and not competencia_e_corrente:
        motivos = motivos + (MOTIVO_VINCULO_ATUAL_COMO_PROXY,)

    if resolucao_cliente.estado != EstadoResolucaoDimensao.RESOLVIDA:
        # Espelha o MESMO estado grave (NAO_ENCONTRADA/AMBIGUA/CONFLITO/
        # etc.) -- nunca decide diferente do que a resolução de cliente
        # já decidiu; candidatos traduzidos para identidade VINCULO só
        # quando existem (alguns estados nunca carregam candidato).
        candidatos = tuple(
            _referencia_vinculo(colaborador, cliente) for cliente in resolucao_cliente.candidatos
        )
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.VINCULO, estado=resolucao_cliente.estado,
            candidatos=candidatos, metodo='espelho_de_cliente_via_vinculo', motivos=motivos,
        )

    valores = tuple(
        _referencia_vinculo(colaborador, cliente) for cliente in resolucao_cliente.valores_confirmados
    )
    return ResolucaoDimensao(
        dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=valores, metodo='espelho_de_cliente_via_vinculo',
        confianca=resolucao_cliente.confianca, motivos=motivos,
    )
