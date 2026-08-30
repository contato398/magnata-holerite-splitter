"""Testes de `normalizacao_requisitos_prestacao.py` (Fase 7 da missão
"POLÍTICA OPERACIONAL REAL DE CLIENTES/REQUISITOS")."""
from magnata_os.classificacao.normalizacao_requisitos_prestacao import (
    EstadoNormalizacaoRequisito,
    RegistroRequisitoExterno,
    normalizar_requisito,
    normalizar_requisitos,
)


def test_tipo_canonico_conhecido_e_valido():
    resultado = normalizar_requisito(RegistroRequisitoExterno('Holerite'))
    assert resultado.estado == EstadoNormalizacaoRequisito.VALIDO
    assert resultado.requisito.tipo_documental == 'Holerite'
    assert resultado.requisito.quantidade_minima == 1


def test_tipo_desconhecido_nunca_vira_requisito_silenciosamente():
    resultado = normalizar_requisito(RegistroRequisitoExterno('Coisa Que Nao Existe'))
    assert resultado.estado == EstadoNormalizacaoRequisito.TIPO_DESCONHECIDO
    assert resultado.requisito is None
    assert 'desconhecido' in resultado.motivo


def test_quantidade_invalida_nunca_vira_requisito_silenciosamente():
    resultado = normalizar_requisito(RegistroRequisitoExterno('Holerite', quantidade_minima=0))
    assert resultado.estado == EstadoNormalizacaoRequisito.QUANTIDADE_INVALIDA
    assert resultado.requisito is None


def test_normalizar_requisitos_separa_validos_de_rejeitados_sem_descartar():
    registros = (
        RegistroRequisitoExterno('Holerite'),
        RegistroRequisitoExterno('Tipo Inventado'),
        RegistroRequisitoExterno('FGTS', quantidade_minima=2),
    )
    validos, todos = normalizar_requisitos(registros)
    assert len(validos) == 2
    assert {r.tipo_documental for r in validos} == {'Holerite', 'FGTS'}
    assert len(todos) == 3  # nunca descarta o rejeitado do relatório
    rejeitados = [r for r in todos if r.estado != EstadoNormalizacaoRequisito.VALIDO]
    assert len(rejeitados) == 1


def test_resultado_invalido_nunca_carrega_requisito():
    import pytest
    from magnata_os.classificacao.normalizacao_requisitos_prestacao import ResultadoNormalizacaoRequisito
    from magnata_os.classificacao.prestacao_readiness import RequisitoDocumentalPrestacao
    with pytest.raises(ValueError):
        ResultadoNormalizacaoRequisito(
            estado=EstadoNormalizacaoRequisito.TIPO_DESCONHECIDO,
            requisito=RequisitoDocumentalPrestacao('Holerite'),
        )
