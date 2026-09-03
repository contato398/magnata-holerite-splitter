"""Resolução temporal de um documento de Folha/Cartão de Ponto (missão
"IDENTIDADE TEMPORAL DOCUMENTAL DA FOLHA/CARTÃO DE PONTO V1"):

    período REAL extraído do PDF -> competência
    colaborador -> cliente(s) via alocação histórica (interseção de período)

Reaproveita, sem duplicar: `ReferenciaCanonica`, `ResolucaoDimensao`,
`EstadoResolucaoDimensao`, `DimensaoResolucao` (`contratos.py`);
`extrair_periodo_cartao_ponto` (`extracao_periodo_documental_ponto.py`);
`TIPO_FOLHA_DE_PONTO` (`produtores_evidencia_ponto.py`).

NÃO reaproveita `validar_competencia`/`resolucao_competencia_de_
validacao` (`importacao_lote/dominio.py`/`resolucao_semantica.py`):
aquele par resolve "compare a competência extraída com uma
COMPETÊNCIA ESPERADA fornecida de fora" (marcador mês/ano no texto,
ambíguo por natureza, comparado contra expectativa). O período do
Cartão de Ponto é EXPLÍCITO e autocontido (`Período: dd/mm/aaaa até
dd/mm/aaaa`) — a competência é uma derivação determinística do próprio
período (fechamento do período), sem precisar de nenhuma expectativa
externa para ser confiável. Reaproveitar aquele par forçaria uma
comparação que este caso não precisa — por isso este módulo produz
`ResolucaoDimensao` diretamente, no MESMO vocabulário, sem inventar
estado novo.

Cliente/posto NUNCA é persistido como fato — sempre resolvido em tempo
de consulta, por INTERSEÇÃO entre `[periodo_inicio, periodo_fim]` do
documento e cada alocação histórica `[vigente_de, vigente_ate]`
(mesma disciplina de `magnata_os/documental/alocacao`, nunca o cadastro
atual). Transferência de posto DENTRO do período produz múltiplos
valores confirmados legítimos — nunca reduzido a 1 (mesmo mecanismo já
usado para "vínculo múltiplo genuíno" de Holerite, `adaptador_
inventario_prestacao.py::itens_para_multiplos_clientes_do_vinculo`)."""
from __future__ import annotations

import dataclasses
import datetime
import enum
from typing import Optional, Protocol, Tuple

from .contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from .extracao_periodo_documental_ponto import extrair_periodo_cartao_ponto
from .produtores_evidencia_ponto import TIPO_FOLHA_DE_PONTO


@dataclasses.dataclass(frozen=True)
class AlocacaoHistorica:
    """Representação neutra de 1 alocação — mesma forma conceitual das
    tabelas `vinculo_trabalhista`/`alocacao` já existentes
    (`magnata_os/documental/alocacao`), injetada por quem chama (ver
    `FonteAlocacaoHistorica` abaixo). Este módulo nunca conhece
    Postgres/Airtable."""

    colaborador_id: str
    cliente_id: str
    vigente_de: datetime.date
    vigente_ate: Optional[datetime.date]

    def __post_init__(self) -> None:
        if not self.colaborador_id.strip():
            raise ValueError('colaborador_id deve ser texto nao vazio')
        if not self.cliente_id.strip():
            raise ValueError('cliente_id deve ser texto nao vazio')
        if self.vigente_ate is not None and self.vigente_ate < self.vigente_de:
            raise ValueError('vigente_ate nao pode ser anterior a vigente_de')

    def intersecta(self, periodo_inicio: datetime.date, periodo_fim: datetime.date) -> bool:
        return self.vigente_de <= periodo_fim and (
            self.vigente_ate is None or self.vigente_ate >= periodo_inicio
        )


class FonteAlocacaoHistorica(Protocol):
    """Porta substituível para consulta de alocação histórica — hoje
    implementada em memória (testes) ou por uma futura leitura de
    `alocacao` (Postgres, `magnata_os/documental/alocacao`); nunca
    Airtable como fonte de verdade desta dimensão."""

    def listar_para_colaborador(self, colaborador_id: str) -> Tuple[AlocacaoHistorica, ...]: ...


@dataclasses.dataclass(frozen=True)
class ResolucaoDocumentalTemporalPonto:
    """Resultado PURO da resolução temporal de 1 documento de Folha de
    Ponto — equivalente em memória à linha que
    `resolucao_documental_temporal` (proposta em
    `docs/decisoes/identidade-temporal-ponto-auditoria-v1.md`)
    persistiria. `resolucao_competencia`/`resolucao_cliente` são sempre
    `ResolucaoDimensao` já existentes — nenhum estado novo."""

    documento_id: str
    tipo_documental: str
    colaborador_id: Optional[str]
    periodo_inicio: Optional[datetime.date]
    periodo_fim: Optional[datetime.date]
    resolucao_competencia: ResolucaoDimensao

    def __post_init__(self) -> None:
        if not self.documento_id.strip():
            raise ValueError('documento_id deve ser texto nao vazio')
        if not self.tipo_documental.strip():
            raise ValueError('tipo_documental deve ser texto nao vazio')
        if self.resolucao_competencia.dimensao != DimensaoResolucao.COMPETENCIA:
            raise ValueError('resolucao_competencia deve ser da dimensao COMPETENCIA')


def resolver_periodo_e_competencia(texto_extraido: str) -> Tuple[
    Optional[datetime.date], Optional[datetime.date], ResolucaoDimensao,
]:
    """Extrai o período do texto e resolve a dimensão COMPETENCIA —
    competência = mês/ano do FECHAMENTO do período (mesma convenção já
    confirmada: ciclo que fecha dia 28, competência junho/2026 = período
    29/05/2026 a 28/06/2026 — regra do PERÍODO REAL do documento, nunca
    de um dia de corte configurado por cliente). Ausência/ambiguidade ->
    `NAO_ENCONTRADA` — nunca inventa."""
    periodo = extrair_periodo_cartao_ponto(texto_extraido)
    if periodo is None:
        return None, None, ResolucaoDimensao(
            dimensao=DimensaoResolucao.COMPETENCIA,
            estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
            metodo='extrair_periodo_cartao_ponto',
            motivos=('periodo_nao_declarado_ou_invalido',),
        )
    periodo_inicio, periodo_fim = periodo
    competencia = ReferenciaCanonica(
        'COMPETENCIA', f'{periodo_fim.year:04d}-{periodo_fim.month:02d}',
    )
    resolucao = ResolucaoDimensao(
        dimensao=DimensaoResolucao.COMPETENCIA,
        estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(competencia,),
        metodo='extrair_periodo_cartao_ponto',
    )
    return periodo_inicio, periodo_fim, resolucao


def resolver_clientes_por_periodo(
    fonte: FonteAlocacaoHistorica,
    colaborador_id: str,
    periodo_inicio: datetime.date,
    periodo_fim: datetime.date,
) -> ResolucaoDimensao:
    """Resolve cliente(s) por INTERSEÇÃO entre o período do documento e
    cada alocação histórica do colaborador. Zero interseções ->
    `NAO_ENCONTRADA` (nunca inventa vínculo); uma -> `RESOLVIDA` com 1
    valor; duas ou mais (transferência de posto DENTRO do período) ->
    `RESOLVIDA` com TODOS os valores confirmados, em ordem
    determinística (ordenados por `entidade_id`) — nunca reduzido
    silenciosamente a um só."""
    clientes = []
    for alocacao in fonte.listar_para_colaborador(colaborador_id):
        if alocacao.colaborador_id != colaborador_id:
            continue
        if not alocacao.intersecta(periodo_inicio, periodo_fim):
            continue
        cliente = ReferenciaCanonica('CLIENTE', alocacao.cliente_id)
        if cliente not in clientes:
            clientes.append(cliente)

    if not clientes:
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE,
            estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
            metodo='resolver_clientes_por_periodo',
            motivos=('nenhuma_alocacao_intersecta_o_periodo',),
        )
    clientes_ordenados = tuple(sorted(clientes, key=lambda c: c.entidade_id))
    return ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE,
        estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=clientes_ordenados,
        metodo='resolver_clientes_por_periodo',
    )


def resolver_documento_ponto(
    documento_id: str,
    texto_extraido: str,
    colaborador_id: str,
    fonte_alocacao: FonteAlocacaoHistorica,
) -> Tuple[ResolucaoDocumentalTemporalPonto, ResolucaoDimensao]:
    """Orquestração ponta-a-ponta, pura, sem I/O: período -> competência
    -> cliente(s). Devolve `(resolucao_documental, resolucao_cliente)`
    — `resolucao_cliente` nunca é persistida (ver docstring do módulo);
    é sempre recomputável a partir do que já foi persistido
    (`colaborador_id`, `periodo_inicio`, `periodo_fim`) mais a alocação
    histórica vigente no momento da consulta."""
    periodo_inicio, periodo_fim, resolucao_competencia = resolver_periodo_e_competencia(texto_extraido)
    resolucao_documental = ResolucaoDocumentalTemporalPonto(
        documento_id=documento_id, tipo_documental=TIPO_FOLHA_DE_PONTO,
        colaborador_id=colaborador_id, periodo_inicio=periodo_inicio, periodo_fim=periodo_fim,
        resolucao_competencia=resolucao_competencia,
    )
    if periodo_inicio is None or periodo_fim is None:
        resolucao_cliente = ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE,
            estado=EstadoResolucaoDimensao.NAO_AVALIADA,
            metodo='resolver_documento_ponto',
            motivos=('periodo_indisponivel_cliente_nao_avaliado',),
        )
    else:
        resolucao_cliente = resolver_clientes_por_periodo(
            fonte_alocacao, colaborador_id, periodo_inicio, periodo_fim,
        )
    return resolucao_documental, resolucao_cliente


# ============================================================================
# Semântica de REPROCESSAMENTO (revisão independente pós-PR #127)
# ============================================================================
#
# Pergunta que motivou esta seção: se o mesmo `documento_id` for
# reprocessado (nova extração de período/competência) e o resultado
# divergir do já persistido, o sistema pode sobrescrever silenciosamente
# a verdade anterior? Resposta: NUNCA. As 4 transições abaixo são as
# ÚNICAS possíveis, e são a MESMA classificação usada tanto pelo
# repositório em memória quanto pelo adapter Postgres — nenhuma duplica
# esta decisão.

class TransicaoResolucaoTemporal(str, enum.Enum):
    """Classificação determinística de um `salvar_com_evento` contra o
    estado já persistido (se houver) para o MESMO `documento_id`."""

    NOVA = 'NOVA'
    """Nenhuma resolução anterior para este documento -- INSERT normal."""

    EQUIVALENTE = 'EQUIVALENTE'
    """Resolução anterior existe e é IDÊNTICA à nova (mesmo colaborador,
    período, estado e valor de competência) -- idempotência real: NENHUMA
    escrita, NENHUM evento novo (reprocessar o mesmo resultado nunca
    produz ruído na auditoria)."""

    ATUALIZACAO = 'ATUALIZACAO'
    """Resolução anterior existe e DIFERE da nova, mas não são 2
    competências RESOLVIDAS conflitantes entre si (ex.: extração antes
    NAO_ENCONTRADA, agora RESOLVIDA -- uma correção legítima, nunca uma
    disputa). A nova resolução é aplicada; o valor ANTERIOR nunca é
    apagado sem registro -- fica preservado para sempre no evento de
    auditoria (`EventoHistorico`, append-only)."""

    CONFLITO = 'CONFLITO'
    """Resolução anterior e nova são AMBAS `RESOLVIDA`, mas com valores de
    competência DIFERENTES -- disputa real entre 2 extrações confiantes.
    O sistema NUNCA decide sozinho qual prevalece: a dimensão COMPETENCIA
    persistida é rebaixada para `EstadoResolucaoDimensao.CONFLITO`
    (vocabulário já existente, nunca um estado novo) e o período fica
    `None` (não confiável enquanto a disputa não for resolvida por um
    humano) -- mesma filosofia de `EstadoPrestacaoReadiness.REVISAR` a
    jusante. Os 2 valores em disputa ficam preservados no evento de
    auditoria, nunca perdidos."""


def resolucoes_equivalentes(
    anterior: ResolucaoDocumentalTemporalPonto, novo: ResolucaoDocumentalTemporalPonto,
) -> bool:
    """Compara os campos observáveis -- nunca `documento_id`/
    `tipo_documental` (esses são sempre iguais para o mesmo documento,
    por construção de quem chama)."""
    return (
        anterior.colaborador_id == novo.colaborador_id
        and anterior.periodo_inicio == novo.periodo_inicio
        and anterior.periodo_fim == novo.periodo_fim
        and anterior.resolucao_competencia.estado == novo.resolucao_competencia.estado
        and anterior.resolucao_competencia.valores_confirmados == novo.resolucao_competencia.valores_confirmados
    )


def classificar_transicao_resolucao(
    anterior: Optional[ResolucaoDocumentalTemporalPonto],
    novo: ResolucaoDocumentalTemporalPonto,
) -> TransicaoResolucaoTemporal:
    """Função PURA e determinística — única fonte desta decisão,
    reaproveitada por `repositorio_resolucao_temporal.py` (memória) e
    `adapters/postgres_resolucao_temporal.py` (Postgres), nunca
    duplicada entre os dois."""
    if anterior is None:
        return TransicaoResolucaoTemporal.NOVA
    if resolucoes_equivalentes(anterior, novo):
        return TransicaoResolucaoTemporal.EQUIVALENTE
    ambas_resolvidas_e_diferentes = (
        anterior.resolucao_competencia.estado == EstadoResolucaoDimensao.RESOLVIDA
        and novo.resolucao_competencia.estado == EstadoResolucaoDimensao.RESOLVIDA
        and anterior.resolucao_competencia.valores_confirmados != novo.resolucao_competencia.valores_confirmados
    )
    if ambas_resolvidas_e_diferentes:
        return TransicaoResolucaoTemporal.CONFLITO
    return TransicaoResolucaoTemporal.ATUALIZACAO


def resolucao_a_persistir_para_transicao(
    transicao: TransicaoResolucaoTemporal,
    novo: ResolucaoDocumentalTemporalPonto,
) -> ResolucaoDocumentalTemporalPonto:
    """Resolução efetivamente escrita para cada transição. `NOVA`/
    `ATUALIZACAO` aplicam `novo` sem alteração. `CONFLITO` NUNCA decide
    sozinho qual dos dois valores prevalece -- rebaixa a dimensão
    COMPETENCIA para `CONFLITO` e limpa o período (ambos preservados,
    sem alteração, no evento de auditoria correspondente, nunca
    perdidos). `EQUIVALENTE` nunca chega aqui (tratado como no-op antes)."""
    if transicao != TransicaoResolucaoTemporal.CONFLITO:
        return novo
    resolucao_conflito = ResolucaoDimensao(
        dimensao=DimensaoResolucao.COMPETENCIA,
        estado=EstadoResolucaoDimensao.CONFLITO,
        metodo='classificar_transicao_resolucao',
        motivos=('competencia_divergente_entre_reprocessamentos',),
    )
    return ResolucaoDocumentalTemporalPonto(
        documento_id=novo.documento_id, tipo_documental=novo.tipo_documental,
        colaborador_id=novo.colaborador_id, periodo_inicio=None, periodo_fim=None,
        resolucao_competencia=resolucao_conflito,
    )
