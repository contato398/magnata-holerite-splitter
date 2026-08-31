"""Testes de `vinculo_unidade_prestacao.py` (missão "EVIDÊNCIA
RELACIONAL DOCUMENTO↔DOCUMENTO + VÍNCULO/UNIDADE_POSTO REAIS")."""
import pytest

from magnata_os.classificacao.contratos import DimensaoResolucao, EstadoResolucaoDimensao, ReferenciaCanonica, ResolucaoDimensao
from magnata_os.classificacao.vinculo_unidade_prestacao import (
    MOTIVO_VINCULO_ATUAL_COMO_PROXY,
    resolucao_vinculo_a_partir_de_cliente,
    resolver_unidade_posto_validado,
)

_COLABORADOR = ReferenciaCanonica('COLABORADOR', 'func-1')
_CLIENTE = ReferenciaCanonica('CLIENTE', 'cli-sky')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')


class _FonteUnidadePostoFake:
    def __init__(self, resolucao):
        self._resolucao = resolucao

    def resolver_unidade_posto(self, colaborador, competencia):
        return self._resolucao


def test_resolver_unidade_posto_validado_aceita_resolucao_valida():
    resolucao = ResolucaoDimensao(
        dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(ReferenciaCanonica('UNIDADE_POSTO', 'local-A'),),
    )
    fonte = _FonteUnidadePostoFake(resolucao)
    resultado = resolver_unidade_posto_validado(fonte, _COLABORADOR, _COMPETENCIA)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_resolver_unidade_posto_validado_rejeita_dimensao_errada():
    resolucao_errada = ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_APLICAVEL)
    fonte = _FonteUnidadePostoFake(resolucao_errada)
    with pytest.raises(ValueError):
        resolver_unidade_posto_validado(fonte, _COLABORADOR, _COMPETENCIA)


def test_resolver_unidade_posto_validado_rejeita_origem_nao_colaborador():
    resolucao = ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA)
    fonte = _FonteUnidadePostoFake(resolucao)
    with pytest.raises(ValueError):
        resolver_unidade_posto_validado(fonte, _CLIENTE, _COMPETENCIA)


def test_multiplos_postos_cardinalidade_multipla_nunca_escolhe_arbitrariamente():
    resolucao = ResolucaoDimensao(
        dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(
            ReferenciaCanonica('UNIDADE_POSTO', 'local-A'), ReferenciaCanonica('UNIDADE_POSTO', 'local-B'),
        ),
    )
    fonte = _FonteUnidadePostoFake(resolucao)
    resultado = resolver_unidade_posto_validado(fonte, _COLABORADOR, _COMPETENCIA)
    assert len(resultado.valores_confirmados) == 2


def test_vinculo_espelha_cliente_resolvida_competencia_corrente_sem_ressalva():
    resolucao_cliente = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(_CLIENTE,),
    )
    resultado = resolucao_vinculo_a_partir_de_cliente(_COLABORADOR, resolucao_cliente, competencia_e_corrente=True)
    assert resultado.dimensao == DimensaoResolucao.VINCULO
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados[0] == ReferenciaCanonica('VINCULO', 'func-1:cli-sky')
    assert MOTIVO_VINCULO_ATUAL_COMO_PROXY not in resultado.motivos


def test_vinculo_espelha_cliente_competencia_historica_carrega_ressalva():
    """§4: vínculo corrente usado para competência histórica -- nunca
    vira verdade histórica silenciosa, motivo sanitizado registrado."""
    resolucao_cliente = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(_CLIENTE,),
    )
    resultado = resolucao_vinculo_a_partir_de_cliente(_COLABORADOR, resolucao_cliente, competencia_e_corrente=False)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert MOTIVO_VINCULO_ATUAL_COMO_PROXY in resultado.motivos


def test_vinculo_espelha_estado_nao_resolvido_nunca_decide_diferente():
    resolucao_cliente = ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA)
    resultado = resolucao_vinculo_a_partir_de_cliente(_COLABORADOR, resolucao_cliente, competencia_e_corrente=True)
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_vinculo_multiplos_clientes_gera_multiplos_vinculos():
    cliente_b = ReferenciaCanonica('CLIENTE', 'cli-acme')
    resolucao_cliente = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(_CLIENTE, cliente_b),
    )
    resultado = resolucao_vinculo_a_partir_de_cliente(_COLABORADOR, resolucao_cliente, competencia_e_corrente=True)
    assert len(resultado.valores_confirmados) == 2


def test_dimensao_errada_rejeitada():
    resolucao_errada = ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL)
    with pytest.raises(ValueError):
        resolucao_vinculo_a_partir_de_cliente(_COLABORADOR, resolucao_errada, competencia_e_corrente=True)
