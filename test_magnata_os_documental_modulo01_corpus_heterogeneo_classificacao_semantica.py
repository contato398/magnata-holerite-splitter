"""Corpus E2E heterogêneo (missão "INTEGRAÇÃO REAL DO CONTEÚDO
DOCUMENTAL AO MOTOR SEMÂNTICO", Fase 18/19/20) -- prova, ponta a ponta,
que `decidir_transicao_classificacao_semantica` (texto -> ponte
multi-evidência -> reconciliação origem×conteúdo -> competência
esperada×observada -> decisão de transição de esteira) resolve os 10
casos especificados sem inventar nenhuma classificação e sem avançar
silenciosamente sobre nenhum conflito.

Escopo desta missão (declarado, não escondido -- ver relatório final):
prova até a decisão de transição da etapa CLASSIFICACAO (mesmo contrato
`DecisaoTransicaoClassificacao` já consumido por `ServicoAvancoEsteira`).
Encadeamento automático através de SEPARACAO/IDENTIFICACAO/VALIDACAO/
inventário/readiness/pacote lógico (Fase 7/10, granularidade por
família) fica para uma próxima macro-missão -- essas etapas ainda não
têm política de avanço automático implementada na esteira real
(`servico_avanco_esteira._DESCRICAO_PROXIMA_ACAO`), então "auto-avança"
aqui significa "sai da CLASSIFICACAO sem bloqueio nem revisão", nunca
"o documento já chegou à distribuição"."""
import dataclasses
from typing import Optional, Tuple

import pytest

from magnata_os.documental.modulo01.dominio_esteira import SituacaoEsteira
from magnata_os.documental.modulo01.politica_classificacao_semantica import (
    CODIGO_BLOQUEIO_AMBIGUA_SEMANTICA,
    CODIGO_BLOQUEIO_COMPETENCIA_DIVERGENTE,
    CODIGO_BLOQUEIO_ORIGEM_CONTEUDO_DIVERGENTES,
    CODIGO_BLOQUEIO_TEXTO_NAO_EXTRAIVEL,
    decidir_transicao_classificacao_semantica,
)


@dataclasses.dataclass(frozen=True)
class CasoCorpus:
    numero: int
    descricao: str
    texto: Optional[str]
    tipo_origem: Optional[str] = None
    competencia_esperada: Optional[Tuple[int, int]] = None
    situacao_esperada: SituacaoEsteira = SituacaoEsteira.CONCLUIDO
    codigo_bloqueio_esperado: Optional[str] = None


CORPUS: Tuple[CasoCorpus, ...] = (
    CasoCorpus(
        1, 'Holerite sem a palavra "Holerite" -- reconhecido por "Recibo de Pagamento"/"Total de Vencimentos"',
        texto='Recibo de Pagamento -- Total de Vencimentos',
        situacao_esperada=SituacaoEsteira.CONCLUIDO,
    ),
    CasoCorpus(
        2, 'Folha de Ponto sem título -- reconhecida por estrutura (linhas de marcação repetidas)',
        texto=(
            '29/04/26 - Qua - C1 18:56 01:00 01:53 09:05\n'
            '30/04/26 - Qui - C1 18:50 01:00 01:50 09:00'
        ),
        situacao_esperada=SituacaoEsteira.CONCLUIDO,
    ),
    CasoCorpus(
        3, '"Resumo da Folha" -- rótulo alternativo de Extrato, evidência combinada',
        texto='Resumo da Folha de Pagamento -- Julho/2026',
        situacao_esperada=SituacaoEsteira.CONCLUIDO,
    ),
    CasoCorpus(
        4, 'Origem declarada "Holerite" mas conteúdo resolve FGTS -- CONFLITO, nunca avança silenciosamente',
        texto='Comprovante de recolhimento do FGTS', tipo_origem='Holerite',
        situacao_esperada=SituacaoEsteira.BLOQUEADO,
        codigo_bloqueio_esperado=CODIGO_BLOQUEIO_ORIGEM_CONTEUDO_DIVERGENTES,
    ),
    CasoCorpus(
        5, 'Guia DCTFWeb/DARF com origem neutra -- resolvida semanticamente',
        texto='Guia de Recolhimento DCTFWeb',
        situacao_esperada=SituacaoEsteira.CONCLUIDO,
    ),
    CasoCorpus(
        6, 'Comprovante bancário -- finalidade Salário reconhecida (descrição + estrutura bancária)',
        texto='Comprovante de transferência -- pagamento de salário',
        situacao_esperada=SituacaoEsteira.CONCLUIDO,
    ),
    CasoCorpus(
        7, 'Comprovante ambíguo (Guia genérica × finalidade FGTS empatadas) -- revisão humana',
        texto='Comprovante de recolhimento do FGTS -- Código de Receita: 0561',
        situacao_esperada=SituacaoEsteira.BLOQUEADO,
        codigo_bloqueio_esperado=CODIGO_BLOQUEIO_AMBIGUA_SEMANTICA,
    ),
    CasoCorpus(
        8, 'PDF sem texto extraível -- necessidade técnica, nunca uma classificação inventada',
        texto=None,
        situacao_esperada=SituacaoEsteira.BLOQUEADO,
        codigo_bloqueio_esperado=CODIGO_BLOQUEIO_TEXTO_NAO_EXTRAIVEL,
    ),
    CasoCorpus(
        9, 'Documento totalmente desconhecido -- DESCONHECIDO, soft-flag, nunca "Outro" silencioso',
        texto='texto totalmente generico sem nenhum sinal',
        situacao_esperada=SituacaoEsteira.EM_REVISAO,
    ),
    CasoCorpus(
        10, 'Documento resolvido mas competência observada diverge da esperada -- CONFLITO',
        texto='Comprovante de recolhimento do FGTS\nCompetência: 07/2026',
        competencia_esperada=(2026, 6),
        situacao_esperada=SituacaoEsteira.BLOQUEADO,
        codigo_bloqueio_esperado=CODIGO_BLOQUEIO_COMPETENCIA_DIVERGENTE,
    ),
)


@pytest.mark.parametrize('caso', CORPUS, ids=lambda c: f'caso_{c.numero:02d}')
def test_corpus_heterogeneo_caso(caso: CasoCorpus):
    decisao = decidir_transicao_classificacao_semantica(
        texto=caso.texto, tipo_origem=caso.tipo_origem, competencia_esperada=caso.competencia_esperada,
    )
    assert decisao.situacao_classificacao == caso.situacao_esperada, caso.descricao
    if caso.codigo_bloqueio_esperado is not None:
        assert decisao.deve_bloquear is True
        assert decisao.motivo_bloqueio.codigo == caso.codigo_bloqueio_esperado, caso.descricao
    else:
        assert decisao.deve_bloquear is False, caso.descricao


# ============================================================================
# Fase 20 -- métricas do corpus (AUTO_RESOLVIDO ≠ AUTO_AVANCO_COMPLETO;
# aqui só medimos até a decisão de transição de CLASSIFICACAO, ver
# docstring do módulo sobre o escopo declarado desta missão).
# ============================================================================

@dataclasses.dataclass(frozen=True)
class MetricasCorpusClassificacaoSemantica:
    total: int
    auto_avancaram: int  # CONCLUIDO, sem bloqueio -- saiu da etapa sozinho
    revisao: int  # EM_REVISAO (DESCONHECIDO) -- soft-flag, segue visível
    bloqueados: int  # BLOQUEADO -- AMBIGUA/CONFLITO/origem×conteúdo/competência/técnico

    def __post_init__(self) -> None:
        if self.auto_avancaram + self.revisao + self.bloqueados != self.total:
            raise ValueError('soma das categorias deve ser igual ao total')

    @property
    def percentual_automacao(self) -> float:
        if self.total == 0:
            return 0.0
        return round(100.0 * self.auto_avancaram / self.total, 2)


def _medir_corpus(corpus: Tuple[CasoCorpus, ...]) -> MetricasCorpusClassificacaoSemantica:
    auto_avancaram = revisao = bloqueados = 0
    for caso in corpus:
        decisao = decidir_transicao_classificacao_semantica(
            texto=caso.texto, tipo_origem=caso.tipo_origem, competencia_esperada=caso.competencia_esperada,
        )
        if decisao.deve_bloquear:
            bloqueados += 1
        elif decisao.situacao_classificacao == SituacaoEsteira.EM_REVISAO:
            revisao += 1
        else:
            auto_avancaram += 1
    return MetricasCorpusClassificacaoSemantica(
        total=len(corpus), auto_avancaram=auto_avancaram, revisao=revisao, bloqueados=bloqueados,
    )


def test_metricas_do_corpus_distinguem_auto_avanco_de_revisao_e_bloqueio():
    metricas = _medir_corpus(CORPUS)
    assert metricas.total == 10
    # Casos 1,2,3,5,6 avançam sozinhos (5); caso 9 vira revisão soft (1);
    # casos 4,7,8,10 bloqueiam (4) -- números fixos do corpus acima,
    # nunca recalculados por aproximação.
    assert metricas.auto_avancaram == 5
    assert metricas.revisao == 1
    assert metricas.bloqueados == 4
    assert metricas.percentual_automacao == 50.0
