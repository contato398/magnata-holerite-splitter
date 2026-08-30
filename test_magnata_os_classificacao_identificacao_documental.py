"""Testes de `identificacao_documental.py` (missão "CORREDOR AUTÔNOMO
PÓS-CLASSIFICAÇÃO V1", Fase 8: identificação genérica de colaborador,
extraída de `politica_identificacao_holerite.py` para reuso por
qualquer família com granularidade colaborador)."""
from magnata_os.classificacao.contratos import DimensaoResolucao, EstadoResolucaoDimensao
from magnata_os.classificacao.identificacao_documental import (
    DocumentoComMultiplasIdentidades,
    multiplas_identidades_para_resolucao_dimensao,
    resolver_colaborador_de_texto,
)
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario


def _candidato(func_id, cpf, nome):
    return CandidatoFuncionario(func_id=func_id, cpf=cpf, nome_normalizado=nome)


def test_cpf_unico_resolve_colaborador():
    candidatos = [_candidato('func-1', '11122233344', 'JOAO DA SILVA')]
    resultado = resolver_colaborador_de_texto('CPF: 111.222.333-44', candidatos)
    assert resultado.dimensao == DimensaoResolucao.COLABORADOR
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados[0].entidade_id == 'func-1'


def test_dois_cpfs_distintos_vira_multiplas_identidades():
    candidatos = [_candidato('func-1', '11122233344', 'JOAO DA SILVA')]
    resultado = resolver_colaborador_de_texto(
        'CPF: 111.222.333-44\nCPF: 555.666.777-88', candidatos,
    )
    assert isinstance(resultado, DocumentoComMultiplasIdentidades)
    assert resultado.quantidade_cpfs_distintos == 2


def test_nenhum_cpf_nenhum_nome_bate_vira_nao_encontrada():
    candidatos = [_candidato('func-1', '11122233344', 'JOAO DA SILVA')]
    resultado = resolver_colaborador_de_texto('documento generico sem identidade', candidatos)
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_multiplas_identidades_para_resolucao_dimensao_vira_conflito_nunca_ambigua():
    resultado = multiplas_identidades_para_resolucao_dimensao(
        DocumentoComMultiplasIdentidades(quantidade_cpfs_distintos=3),
    )
    assert resultado.dimensao == DimensaoResolucao.COLABORADOR
    assert resultado.estado == EstadoResolucaoDimensao.CONFLITO


def test_quantidade_menor_que_2_e_rejeitada():
    import pytest
    with pytest.raises(ValueError):
        DocumentoComMultiplasIdentidades(quantidade_cpfs_distintos=1)


def test_nunca_carrega_cpf_ou_nome_na_resolucao():
    candidatos = [_candidato('func-1', '11122233344', 'JOAO DA SILVA')]
    resultado = resolver_colaborador_de_texto('CPF: 111.222.333-44', candidatos)
    for evidencia in resultado.evidencias:
        assert '111' not in evidencia.referencia_fonte
        assert 'JOAO' not in (evidencia.referencia_fonte or '').upper()
