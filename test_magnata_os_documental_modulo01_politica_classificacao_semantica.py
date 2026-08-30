"""Testes de `politica_classificacao_semantica.py` (missão "INTEGRAÇÃO
REAL DO CONTEÚDO DOCUMENTAL AO MOTOR SEMÂNTICO", Fases 2/3/5/6/7/8/13).

Todos os casos usam o MESMO contrato `DecisaoTransicaoClassificacao` já
consumido por `ServicoAvancoEsteira.aplicar_resultado_classificacao`
(prova de que nenhuma esteira/mecânica nova foi criada)."""
from magnata_os.classificacao.contratos import DimensaoResolucao, EstadoResolucaoDimensao, ResolucaoDimensao
from magnata_os.documental.modulo01 import politica_classificacao_semantica as politica
from magnata_os.documental.modulo01.dominio_esteira import SituacaoEsteira
from magnata_os.documental.modulo01.politica_classificacao_semantica import (
    CODIGO_BLOQUEIO_AMBIGUA_SEMANTICA,
    CODIGO_BLOQUEIO_COMPETENCIA_AMBIGUA,
    CODIGO_BLOQUEIO_COMPETENCIA_DIVERGENTE,
    CODIGO_BLOQUEIO_CONFLITO_TIPO,
    CODIGO_BLOQUEIO_ORIGEM_CONTEUDO_DIVERGENTES,
    CODIGO_BLOQUEIO_TEXTO_NAO_EXTRAIVEL,
    decidir_transicao_classificacao_semantica,
)


def test_texto_none_vira_bloqueio_tecnico_distinto_de_desconhecido():
    """Fase 3: PDF sem texto extraível NUNCA é confundido com
    "desconhecido" (NAO_ENCONTRADA) -- é um bloqueio técnico à parte,
    com código próprio."""
    decisao = decidir_transicao_classificacao_semantica(texto=None)
    assert decisao.deve_avancar is True
    assert decisao.situacao_classificacao == SituacaoEsteira.BLOQUEADO
    assert decisao.deve_bloquear is True
    assert decisao.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_TEXTO_NAO_EXTRAIVEL
    assert decisao.motivo_bloqueio.resolvivel_automaticamente is False


def test_resolvida_sem_origem_avanca_automaticamente_sem_bloqueio():
    """Fase 7: RESOLVIDA sem nenhuma origem para reconciliar -- avança
    sozinha, CONCLUIDO, sem bloqueio (auto-avanço)."""
    decisao = decidir_transicao_classificacao_semantica(
        texto='Resumo da Folha de Pagamento -- Julho/2026',
    )
    assert decisao.deve_avancar is True
    assert decisao.situacao_classificacao == SituacaoEsteira.CONCLUIDO
    assert decisao.deve_bloquear is False
    assert decisao.motivo_bloqueio is None


def test_resolvida_com_origem_concordante_avanca_automaticamente():
    """Fase 5: origem × conteúdo em REFORCO -- avança sozinha, mesmo
    caminho de auto-avanço."""
    decisao = decidir_transicao_classificacao_semantica(
        texto='Resumo da Folha de Pagamento -- Julho/2026',
        tipo_origem='Extrato da Folha de Pagamento',
    )
    assert decisao.deve_avancar is True
    assert decisao.situacao_classificacao == SituacaoEsteira.CONCLUIDO
    assert decisao.deve_bloquear is False


def test_resolvida_com_origem_divergente_vira_conflito_nunca_avanca_silenciosamente():
    """Fase 5/6 REGRA CRÍTICA: estar numa tabela/origem declarada nunca
    prova o tipo sozinho -- conteúdo resolve para outro tipo -> CONFLITO,
    bloqueado, nunca a origem vencendo silenciosamente."""
    decisao = decidir_transicao_classificacao_semantica(
        texto='Comprovante de recolhimento do FGTS',
        tipo_origem='Holerite',
    )
    assert decisao.deve_avancar is True
    assert decisao.situacao_classificacao == SituacaoEsteira.BLOQUEADO
    assert decisao.deve_bloquear is True
    assert decisao.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_ORIGEM_CONTEUDO_DIVERGENTES
    assert 'Holerite' in decisao.motivo_bloqueio.descricao
    assert 'FGTS' in decisao.motivo_bloqueio.descricao


def test_conflito_do_proprio_motor_vira_bloqueio(monkeypatch):
    """CONFLITO (2+ sinais FORTES incompatíveis) do resolvedor geral --
    nenhum produtor real hoje agregado pela ponte emite 2 candidatos
    FORTE simultâneos para textos distintos (o classificador legado só
    emite 1 hipótese vencedora por chamada -- achado real desta missão,
    registrado no relatório final, não escondido); o branch da política
    para esse estado existe para quando um produtor futuro o alcançar,
    e é testado aqui isolando a resposta do resolvedor via monkeypatch
    -- nunca inventando um texto artificial que não reflete o
    comportamento real hoje."""
    resolucao_conflito = ResolucaoDimensao(
        dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.CONFLITO,
        metodo='teste', motivos=('sinais_fortes_incompativeis',),
    )
    monkeypatch.setattr(politica, 'resolver_tipo_documental_de_texto', lambda texto: resolucao_conflito)
    decisao = decidir_transicao_classificacao_semantica(texto='qualquer texto')
    assert decisao.situacao_classificacao == SituacaoEsteira.BLOQUEADO
    assert decisao.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_CONFLITO_TIPO


def test_ambigua_vira_bloqueio_para_decisao_humana():
    """Dois candidatos moderados empatados ('Guia' genérico × finalidade
    FGTS, ambos MODERADA pelo mesmo sinal fiscal) -- AMBIGUA, só humano
    decide qual tipo. Mesmo texto já comprovado ambíguo pela ponte (ver
    test_magnata_os_classificacao_ponte_conteudo_motor_semantico.py::
    test_reforco_fiscal_estrutural_alimenta_a_mesma_disputa_do_resolvedor)."""
    texto_ambiguo = 'Comprovante de recolhimento do FGTS -- Código de Receita: 0561'
    decisao = decidir_transicao_classificacao_semantica(texto=texto_ambiguo)
    assert decisao.situacao_classificacao == SituacaoEsteira.BLOQUEADO
    assert decisao.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_AMBIGUA_SEMANTICA


def test_nao_encontrada_vira_revisao_soft_flag_nunca_bloqueio():
    """Fase 13: DESCONHECIDO -- soft-flag (EM_REVISAO), nunca hard-block
    (deve_bloquear=False) -- documento continua existindo/visível."""
    decisao = decidir_transicao_classificacao_semantica(texto='texto totalmente generico sem nenhum sinal')
    assert decisao.deve_avancar is True
    assert decisao.situacao_classificacao == SituacaoEsteira.EM_REVISAO
    assert decisao.deve_bloquear is False
    assert decisao.motivo_bloqueio is None


# ============================================================================
# Fase 9 -- competência esperada × observada
# ============================================================================

def test_competencia_observada_coincide_com_esperada_avanca_automaticamente():
    decisao = decidir_transicao_classificacao_semantica(
        texto='Comprovante de recolhimento do FGTS\nCompetência: 07/2026',
        competencia_esperada=(2026, 7),
    )
    assert decisao.situacao_classificacao == SituacaoEsteira.CONCLUIDO
    assert decisao.deve_bloquear is False


def test_competencia_observada_diverge_da_esperada_vira_conflito_bloqueado():
    """Fase 9: competência observada no PDF NUNCA é aceita como verdade
    por si só -- diverge da esperada (`ContextoCicloPrestacao`) -> bloco,
    nunca avanço silencioso, mesmo com TIPO_DOCUMENTAL já RESOLVIDA."""
    decisao = decidir_transicao_classificacao_semantica(
        texto='Comprovante de recolhimento do FGTS\nCompetência: 07/2026',
        competencia_esperada=(2026, 6),
    )
    assert decisao.situacao_classificacao == SituacaoEsteira.BLOQUEADO
    assert decisao.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_COMPETENCIA_DIVERGENTE


def test_competencia_ambigua_no_documento_bloqueia():
    decisao = decidir_transicao_classificacao_semantica(
        texto='Comprovante de recolhimento do FGTS\nCompetência: 07/2026 e 08/2026',
        competencia_esperada=(2026, 7),
    )
    assert decisao.situacao_classificacao == SituacaoEsteira.BLOQUEADO
    assert decisao.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_COMPETENCIA_AMBIGUA


def test_competencia_nao_declarada_no_documento_nao_bloqueia_sozinha():
    """Documento resolvido, sem nenhuma linha marcada de competência --
    NAO_EXTRAIVEL não é tratado como divergência (decisão registrada no
    módulo, não um bloqueio inventado por ausência de evidência)."""
    decisao = decidir_transicao_classificacao_semantica(
        texto='Comprovante de recolhimento do FGTS',
        competencia_esperada=(2026, 7),
    )
    assert decisao.situacao_classificacao == SituacaoEsteira.CONCLUIDO
    assert decisao.deve_bloquear is False


def test_origem_nunca_reconciliada_quando_conteudo_nao_resolveu():
    """Fase 6: conteúdo inconclusivo nunca vira RESOLVIDO só pela
    origem -- mesmo com tipo_origem informado, resultado continua
    EM_REVISAO (a reconciliação nem chega a rodar sobre um tipo
    resolvido, porque não existe um)."""
    decisao = decidir_transicao_classificacao_semantica(
        texto='texto totalmente generico sem nenhum sinal', tipo_origem='Holerite',
    )
    assert decisao.situacao_classificacao == SituacaoEsteira.EM_REVISAO
    assert decisao.deve_bloquear is False
