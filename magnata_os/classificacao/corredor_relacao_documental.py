"""Orquestrador da COSTURA AUTOMÁTICA de relação Documento↔Documento
dentro do corredor (missão "CORRIGIR METADADOS + MERGE PR #106 +
COSTURA AUTOMÁTICA DE RELAÇÃO DOCUMENTO↔DOCUMENTO NO CORREDOR V1").

Fecha o gap final registrado no PR #106: a capacidade de resolver uma
relação já existia (`relacao_documental.py`); a fonte de candidatos já
existe (`fonte_candidatos_relacao_documental.py`); a política de
consequência já existe (`politica_consequencia_relacao_documental.py`).
Este módulo os liga:

  documento atual (já com TIPO_DOCUMENTAL resolvido pelo motor
  semântico -- nunca antes disso, §10 da missão: "relações não são
  classificação")
    -> política diz se este tipo é o lado COMPROVANTE de alguma regra
       cadastrada; sem regra, este módulo nem tenta -- o documento
       segue pelo caminho normal do corredor, sua classificação já
       resolvida NUNCA é desfeita (§10/Caso I)
    -> fonte de candidatos busca candidatos do lado RELATANTE
       compatível, na MESMA competência (compatibilidade de tipos é
       filtro de candidatos, nunca reclassificação -- §11)
    -> evidências de correlação comparam documento atual x cada
       candidato (`relacao_documental.produzir_evidencias_correlacao`,
       nunca uma segunda extração)
    -> `resolver_relacao_documental_dentre_candidatos` decide (nunca
       reavaliado aqui, nunca primeiro-match -- §13)
    -> se RESOLVIDA e a regra permite: deriva as referências lógicas
       (clientes) do candidato vencedor (§6: nunca inventa posto,
       competência divergente, colaborador ou valor individual --
       só o conjunto já comprovado do relatante)
    -> gera itens de inventário (`ItemInventarioPrestacao`, o MESMO
       contrato já existente -- nenhum construtor de item novo) e
       alimenta o MESMO sink já usado pelo resto do corredor
       (idempotente por construção: `InventarioPrestacaoEmMemoria.
       adicionar_muitos` já dedupe por identidade lógica, §16)
    -> devolve o resultado para quem orquestra continuar readiness/
       pacote (já automático a partir do inventário -- nenhuma mudança
       nesse mecanismo, §19).

Nenhum candidato -> `NAO_ENCONTRADA`, nunca inventado. Documento
relacionado processado 2x -> mesmos itens, nunca duplicados (§16,
provado por teste)."""
from __future__ import annotations

import dataclasses
from typing import Optional, Tuple

from .contratos import EstadoResolucaoDimensao, ReferenciaCanonica
from .fonte_candidatos_relacao_documental import FonteCandidatosRelacaoDocumental, resolver_candidatos_validado
from .inventario_prestacao_memoria import InventarioPrestacaoEmMemoria
from .politica_consequencia_relacao_documental import derivar_referencias_herdadas, regra_para_tipo_comprovante
from .prestacao_readiness import ItemInventarioPrestacao
from .relacao_documental import (
    DadosCorrelacaoDocumental,
    ResolucaoRelacaoDocumental,
    produzir_evidencias_correlacao,
    resolver_relacao_documental_dentre_candidatos,
)


@dataclasses.dataclass(frozen=True)
class ContextoRelacaoDocumentoPrestacao:
    """Tudo que o corredor de relação pode precisar, SEMPRE injetado
    por fora -- este módulo nunca decide qual fonte usar, nunca acessa
    Airtable/Gmail/armazenamento diretamente (mesmo princípio de
    `ContextoResolucaoDocumentoPrestacao`)."""

    documento_id: str
    tipo_documental: str
    """Já resolvido pelo motor semântico ANTES de chegar aqui (§10) --
    este módulo nunca resolve nem reavalia tipo documental."""
    competencia: Tuple[int, int]
    dados_correlacao: DadosCorrelacaoDocumental = dataclasses.field(default_factory=DadosCorrelacaoDocumental)
    fonte_candidatos: Optional[FonteCandidatosRelacaoDocumental] = None


@dataclasses.dataclass(frozen=True)
class ResultadoRelacaoDocumentoPrestacao:
    documento_id: str
    tipo_documental: str
    regra_aplicavel: bool
    """`False` quando não há regra cadastrada para este tipo como
    COMPROVANTE, ou nenhuma fonte de candidatos foi injetada -- neste
    caso `resolucao_relacao` é sempre `None` (nunca avaliado, nunca
    fabricado)."""
    resolucao_relacao: Optional[ResolucaoRelacaoDocumental] = None
    itens_gerados: Tuple[ItemInventarioPrestacao, ...] = ()


def resolver_relacao_e_avancar(
    contexto: ContextoRelacaoDocumentoPrestacao, sink: InventarioPrestacaoEmMemoria,
) -> ResultadoRelacaoDocumentoPrestacao:
    """Ponto de entrada único da costura automática. Puro quanto à
    decisão (nenhum I/O externo aqui -- `fonte_candidatos` é quem faz
    I/O, se fizer); só escreve no `sink` local/in-memory já existente."""
    regra = regra_para_tipo_comprovante(contexto.tipo_documental)
    if regra is None or contexto.fonte_candidatos is None:
        return ResultadoRelacaoDocumentoPrestacao(
            documento_id=contexto.documento_id, tipo_documental=contexto.tipo_documental, regra_aplicavel=False,
        )

    candidatos = resolver_candidatos_validado(
        contexto.fonte_candidatos, contexto.documento_id, contexto.tipo_documental,
        regra.tipo_relatante, contexto.competencia, regra.tipo_relacao,
    )
    candidatos_com_evidencias = tuple(
        (candidato.documento_id, produzir_evidencias_correlacao(contexto.dados_correlacao, candidato.dados_correlacao))
        for candidato in candidatos
    )
    resolucao_relacao = resolver_relacao_documental_dentre_candidatos(
        contexto.documento_id, regra.tipo_relacao, candidatos_com_evidencias,
    )

    itens: Tuple[ItemInventarioPrestacao, ...] = ()
    if resolucao_relacao.estado == EstadoResolucaoDimensao.RESOLVIDA and regra.pode_derivar_referencias_do_relatante:
        candidato_vencedor = next(
            candidato for candidato in candidatos if candidato.documento_id == resolucao_relacao.documento_b_id
        )
        referencias = derivar_referencias_herdadas(True, candidato_vencedor.referencias_logicas)
        if referencias:
            ano, mes = contexto.competencia
            competencia_ref = ReferenciaCanonica('COMPETENCIA', f'{ano:04d}-{mes:02d}')
            itens = tuple(
                ItemInventarioPrestacao(
                    documento_id=contexto.documento_id, tipo_documental=contexto.tipo_documental,
                    cliente=cliente, competencia=competencia_ref, colaborador=None,
                )
                for cliente in referencias
            )
            sink.adicionar_muitos(itens)

    return ResultadoRelacaoDocumentoPrestacao(
        documento_id=contexto.documento_id, tipo_documental=contexto.tipo_documental, regra_aplicavel=True,
        resolucao_relacao=resolucao_relacao, itens_gerados=itens,
    )


@dataclasses.dataclass(frozen=True)
class MetricasRelacaoDocumental:
    """§22 da missão -- observabilidade permanente, nunca recalculada
    ad hoc a cada teste (CLAUDE.md §12-F: "verificação manual repetitiva
    é candidata a virar capacidade permanente")."""

    total_relacoes_avaliadas: int
    auto_relacoes_resolvidas: int
    relacoes_ambiguas: int
    relacoes_conflito: int
    relacoes_nao_encontradas: int
    auto_relacoes_aplicadas_a_inventario: int

    @property
    def percentual_auto_relacao(self) -> Optional[float]:
        """`None` quando nenhuma relação foi avaliada -- nunca 0.0
        fingindo que houve avaliação (divisão por zero disfarçada de
        métrica real)."""
        if self.total_relacoes_avaliadas == 0:
            return None
        return self.auto_relacoes_resolvidas / self.total_relacoes_avaliadas


def medir_relacoes(resultados: Tuple[ResultadoRelacaoDocumentoPrestacao, ...]) -> MetricasRelacaoDocumental:
    """Pura, sem I/O -- agrega uma sequência de `ResultadoRelacaoDocumento
    Prestacao` já produzidos (nunca reprocessa nada)."""
    avaliados = tuple(
        resultado for resultado in resultados
        if resultado.regra_aplicavel and resultado.resolucao_relacao is not None
    )
    return MetricasRelacaoDocumental(
        total_relacoes_avaliadas=len(avaliados),
        auto_relacoes_resolvidas=sum(
            1 for r in avaliados if r.resolucao_relacao.estado == EstadoResolucaoDimensao.RESOLVIDA
        ),
        relacoes_ambiguas=sum(
            1 for r in avaliados if r.resolucao_relacao.estado == EstadoResolucaoDimensao.AMBIGUA
        ),
        relacoes_conflito=sum(
            1 for r in avaliados if r.resolucao_relacao.estado == EstadoResolucaoDimensao.CONFLITO
        ),
        relacoes_nao_encontradas=sum(
            1 for r in avaliados if r.resolucao_relacao.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
        ),
        auto_relacoes_aplicadas_a_inventario=sum(1 for r in resultados if r.itens_gerados),
    )
