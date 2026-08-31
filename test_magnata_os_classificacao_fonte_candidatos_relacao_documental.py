"""Testes de `fonte_candidatos_relacao_documental.py` (missão "CORRIGIR
METADADOS + MERGE PR #106 + COSTURA AUTOMÁTICA DE RELAÇÃO
DOCUMENTO↔DOCUMENTO NO CORREDOR V1")."""
import pytest

from magnata_os.classificacao.fonte_candidatos_relacao_documental import (
    CandidatoRelacaoDocumental,
    FonteCandidatosRelacaoDocumentalComposta,
    resolver_candidatos_validado,
)
from magnata_os.classificacao.relacao_documental import DadosCorrelacaoDocumental, TipoRelacaoDocumental

_COMPETENCIA = (2026, 6)


class _FonteFake:
    def __init__(self, candidatos=()):
        self._candidatos = candidatos

    def candidatos_para_relacao(self, documento_id_atual, tipo_atual, tipo_candidato, competencia, tipo_relacao):
        return self._candidatos


def test_candidato_exige_documento_id_nao_vazio():
    with pytest.raises(ValueError):
        CandidatoRelacaoDocumental(documento_id='', tipo_documental='Relatório de Benefícios')


def test_candidato_exige_tipo_documental_nao_vazio():
    with pytest.raises(ValueError):
        CandidatoRelacaoDocumental(documento_id='doc-1', tipo_documental='')


def test_resolver_candidatos_validado_devolve_candidatos_da_fonte():
    candidatos = (
        CandidatoRelacaoDocumental(documento_id='rel-1', tipo_documental='Relatório de Benefícios'),
    )
    fonte = _FonteFake(candidatos)
    resultado = resolver_candidatos_validado(
        fonte, 'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios',
        _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert resultado == candidatos


def test_resolver_candidatos_validado_rejeita_proprio_documento_como_candidato():
    candidatos = (CandidatoRelacaoDocumental(documento_id='comp-1', tipo_documental='Relatório de Benefícios'),)
    fonte = _FonteFake(candidatos)
    with pytest.raises(ValueError):
        resolver_candidatos_validado(
            fonte, 'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios',
            _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
        )


def test_resolver_candidatos_validado_rejeita_tipo_fora_do_pedido():
    candidatos = (CandidatoRelacaoDocumental(documento_id='hol-1', tipo_documental='Holerite'),)
    fonte = _FonteFake(candidatos)
    with pytest.raises(ValueError):
        resolver_candidatos_validado(
            fonte, 'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios',
            _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
        )


def test_resolver_candidatos_validado_rejeita_competencia_divergente():
    candidatos = (
        CandidatoRelacaoDocumental(
            documento_id='rel-1', tipo_documental='Relatório de Benefícios',
            dados_correlacao=DadosCorrelacaoDocumental(competencia=(2025, 1)),
        ),
    )
    fonte = _FonteFake(candidatos)
    with pytest.raises(ValueError):
        resolver_candidatos_validado(
            fonte, 'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios',
            _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
        )


def test_composta_uniao_deduplicada_por_documento_id():
    c1 = CandidatoRelacaoDocumental(documento_id='rel-1', tipo_documental='Relatório de Benefícios')
    c1_duplicado = CandidatoRelacaoDocumental(documento_id='rel-1', tipo_documental='Relatório de Benefícios')
    c2 = CandidatoRelacaoDocumental(documento_id='rel-2', tipo_documental='Relatório de Benefícios')
    composta = FonteCandidatosRelacaoDocumentalComposta((_FonteFake((c1,)), _FonteFake((c1_duplicado, c2))))
    resultado = composta.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios',
        _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert {c.documento_id for c in resultado} == {'rel-1', 'rel-2'}
    assert len(resultado) == 2


def test_composta_nenhuma_fonte_devolve_vazio():
    composta = FonteCandidatosRelacaoDocumentalComposta(())
    resultado = composta.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios',
        _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert resultado == ()
