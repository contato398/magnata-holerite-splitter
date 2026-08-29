"""Testes da política pura de transição REGISTRO -> CLASSIFICACAO
(magnata_os/documental/modulo01/politica_classificacao.py).

Cobre só a TRADUÇÃO de DecisaoRoteamentoDocumental para
DecisaoTransicaoClassificacao -- não reclassifica, não chama
decidir_roteamento, não toca em repositório algum (função pura).
"""
import pytest

from magnata_os.classificacao.classificador_documental import EstadoClassificacao
from magnata_os.classificacao.roteamento_documental import (
    AcaoRoteamento,
    DecisaoRoteamentoDocumental,
    EscopoDocumental,
    MotivoRoteamento,
)
from magnata_os.documental.modulo01.dominio_esteira import MotivoBloqueio, SituacaoEsteira
from magnata_os.documental.modulo01.politica_classificacao import (
    CODIGO_BLOQUEIO_AMBIGUA,
    CODIGO_BLOQUEIO_PDF_INVALIDO,
    MOTIVO_TRANSICAO_CLASSIFICACAO_RESOLVIDA,
    DecisaoTransicaoClassificacao,
    decidir_transicao_classificacao,
)


def _decisao_resolvida(tipo: str = 'Holerite') -> DecisaoRoteamentoDocumental:
    return DecisaoRoteamentoDocumental(
        tipo_documental=tipo,
        estado_classificacao=EstadoClassificacao.RESOLVIDA,
        escopo_documental=EscopoDocumental.COLABORADOR,
        acao_recomendada=AcaoRoteamento.REVISAR_HUMANO,
        motivo=MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL,
        processador_disponivel=False,
        necessita_revisao_humana=True,
        prioridade_revisao='BAIXA',
        evidencias_sanitizadas=('hit',),
        tipos_concorrentes=(),
    )


def _decisao_ambigua() -> DecisaoRoteamentoDocumental:
    return DecisaoRoteamentoDocumental(
        tipo_documental='Outro',
        estado_classificacao=EstadoClassificacao.AMBIGUA,
        escopo_documental=EscopoDocumental.DESCONHECIDO,
        acao_recomendada=AcaoRoteamento.REVISAR_HUMANO,
        motivo=MotivoRoteamento.CLASSIFICACAO_AMBIGUA,
        processador_disponivel=False,
        necessita_revisao_humana=True,
        prioridade_revisao='ALTA',
        evidencias_sanitizadas=('hit1', 'hit2'),
        tipos_concorrentes=('Folha de Ponto', 'EPI'),
    )


def _decisao_nao_reconhecida() -> DecisaoRoteamentoDocumental:
    return DecisaoRoteamentoDocumental(
        tipo_documental='Outro',
        estado_classificacao=EstadoClassificacao.NAO_RECONHECIDA,
        escopo_documental=EscopoDocumental.DESCONHECIDO,
        acao_recomendada=AcaoRoteamento.REVISAR_HUMANO,
        motivo=MotivoRoteamento.TIPO_NAO_RECONHECIDO,
        processador_disponivel=False,
        necessita_revisao_humana=True,
        prioridade_revisao='MEDIA',
        evidencias_sanitizadas=(),
        tipos_concorrentes=(),
    )


def _decisao_invalida() -> DecisaoRoteamentoDocumental:
    return DecisaoRoteamentoDocumental(
        tipo_documental='Outro',
        estado_classificacao=EstadoClassificacao.INVALIDA,
        escopo_documental=EscopoDocumental.DESCONHECIDO,
        acao_recomendada=AcaoRoteamento.REVISAR_HUMANO,
        motivo=MotivoRoteamento.PDF_INVALIDO,
        processador_disponivel=False,
        necessita_revisao_humana=True,
        prioridade_revisao='ALTA',
        evidencias_sanitizadas=(),
        tipos_concorrentes=(),
    )


class TestResolvida:
    def test_avanca_com_situacao_concluido_sem_bloqueio(self):
        decisao_transicao = decidir_transicao_classificacao(_decisao_resolvida())
        assert decisao_transicao.deve_avancar is True
        assert decisao_transicao.situacao_classificacao == SituacaoEsteira.CONCLUIDO
        assert decisao_transicao.deve_bloquear is False
        assert decisao_transicao.motivo_bloqueio is None
        assert decisao_transicao.motivo_transicao == MOTIVO_TRANSICAO_CLASSIFICACAO_RESOLVIDA

    def test_motivo_transicao_nunca_usa_motivo_do_roteamento_para_resolvida(self):
        """Achado da revisão arquitetural: PROCESSADOR_AINDA_NAO_DISPONIVEL
        descreve a etapa POSTERIOR (processamento), não a classificação
        em si -- nunca usado como motivo_transicao de REGISTRO->CLASSIFICACAO."""
        decisao_transicao = decidir_transicao_classificacao(_decisao_resolvida())
        assert decisao_transicao.motivo_transicao != MotivoRoteamento.PROCESSADOR_AINDA_NAO_DISPONIVEL.value

    def test_resolvida_nao_vira_em_revisao_por_falta_de_processador(self):
        """Requisito explícito da revisão arquitetural: falta de
        processador é limitação da PRÓXIMA fase, nunca rebaixa
        CLASSIFICACAO para EM_REVISAO."""
        decisao_transicao = decidir_transicao_classificacao(_decisao_resolvida())
        assert decisao_transicao.situacao_classificacao != SituacaoEsteira.EM_REVISAO
        assert decisao_transicao.situacao_classificacao == SituacaoEsteira.CONCLUIDO


class TestAmbigua:
    def test_avanca_e_bloqueia(self):
        decisao_transicao = decidir_transicao_classificacao(_decisao_ambigua())
        assert decisao_transicao.deve_avancar is True
        assert decisao_transicao.situacao_classificacao == SituacaoEsteira.BLOQUEADO
        assert decisao_transicao.deve_bloquear is True
        assert decisao_transicao.motivo_bloqueio is not None
        assert decisao_transicao.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_AMBIGUA
        assert decisao_transicao.motivo_bloqueio.resolvivel_automaticamente is False


class TestNaoReconhecida:
    def test_avanca_com_em_revisao_sem_bloqueio(self):
        decisao_transicao = decidir_transicao_classificacao(_decisao_nao_reconhecida())
        assert decisao_transicao.deve_avancar is True
        assert decisao_transicao.situacao_classificacao == SituacaoEsteira.EM_REVISAO
        assert decisao_transicao.deve_bloquear is False
        assert decisao_transicao.motivo_bloqueio is None

    def test_nao_reconhecida_nunca_e_hard_block(self):
        """Requisito explícito: NAO_RECONHECIDA nesta fase é EM_REVISAO,
        não hard-block."""
        decisao_transicao = decidir_transicao_classificacao(_decisao_nao_reconhecida())
        assert decisao_transicao.situacao_classificacao != SituacaoEsteira.BLOQUEADO


class TestPdfInvalido:
    def test_avanca_e_bloqueia_sem_resolucao_automatica(self):
        decisao_transicao = decidir_transicao_classificacao(_decisao_invalida())
        assert decisao_transicao.deve_avancar is True
        assert decisao_transicao.situacao_classificacao == SituacaoEsteira.BLOQUEADO
        assert decisao_transicao.deve_bloquear is True
        assert decisao_transicao.motivo_bloqueio.codigo == CODIGO_BLOQUEIO_PDF_INVALIDO
        # Requisito explícito: nenhum mecanismo automático real de
        # re-extração existe hoje -- nunca marcar True por hipótese.
        assert decisao_transicao.motivo_bloqueio.resolvivel_automaticamente is False


# ── Nota: ERRO_TECNICO_SHADOW e "shadow não executado" não têm
# DecisaoRoteamentoDocumental para traduzir -- não são testados aqui
# (não existe uma 5ª branch nesta política para eles). O comportamento
# "não avança" para esses 2 casos é responsabilidade do CHAMADOR
# (servico_lote.py, que simplesmente não invoca esta política quando
# `decisao is None`) -- coberto em test_servico_lote_roteamento_shadow.py.


class TestValidacaoContrato:
    def test_deve_avancar_false_nao_aceita_campos_de_bloqueio(self):
        with pytest.raises(ValueError, match='deve_avancar=False não pode carregar'):
            DecisaoTransicaoClassificacao(
                deve_avancar=False,
                situacao_classificacao=SituacaoEsteira.CONCLUIDO,
                deve_bloquear=False,
                motivo_bloqueio=None,
                motivo_transicao=None,
            )

    def test_deve_avancar_true_exige_situacao(self):
        with pytest.raises(ValueError, match='deve_avancar=True exige situacao_classificacao'):
            DecisaoTransicaoClassificacao(
                deve_avancar=True,
                situacao_classificacao=None,
                deve_bloquear=False,
                motivo_bloqueio=None,
                motivo_transicao=None,
            )

    def test_deve_bloquear_exige_motivo(self):
        with pytest.raises(ValueError, match='deve_bloquear=True exige motivo_bloqueio'):
            DecisaoTransicaoClassificacao(
                deve_avancar=True,
                situacao_classificacao=SituacaoEsteira.BLOQUEADO,
                deve_bloquear=True,
                motivo_bloqueio=None,
                motivo_transicao=None,
            )

    def test_deve_bloquear_exige_situacao_bloqueado(self):
        with pytest.raises(ValueError, match='deve_bloquear=True exige situacao_classificacao=BLOQUEADO'):
            DecisaoTransicaoClassificacao(
                deve_avancar=True,
                situacao_classificacao=SituacaoEsteira.CONCLUIDO,
                deve_bloquear=True,
                motivo_bloqueio=MotivoBloqueio('X', 'desc', None, False),
                motivo_transicao=None,
            )
