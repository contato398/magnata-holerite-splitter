"""Extensao minima do classificador de falha: ENVIO_EXTERNO_INCERTO.

Cobre a regra pétrea do wiring WhatsApp + Assinatura V1: qualquer falha em
que não seja possível provar que o provedor externo NÃO processou a
mensagem deve classificar como ENVIO_EXTERNO_INCERTO, nunca TRANSIENT, e
nunca ser confundida com HUMAN_GATE genérico nem com PERMANENT.
"""
from magnata_os.orquestrador.classificador_falha import (
    ClasseFalha,
    FalhaEnvioIncerto,
    FalhaGateHumano,
    FalhaTransitoria,
    classificar,
)


def test_falha_envio_incerto_classifica_como_envio_externo_incerto():
    assert classificar(FalhaEnvioIncerto('read timeout pos-envio')) == (
        ClasseFalha.ENVIO_EXTERNO_INCERTO
    )


def test_falha_envio_incerto_e_subclasse_de_falha_gate_humano():
    # Garantia estrutural: quem já trata FalhaGateHumano genericamente
    # (except FalhaGateHumano) também captura FalhaEnvioIncerto.
    assert issubclass(FalhaEnvioIncerto, FalhaGateHumano)


def test_falha_gate_humano_pura_continua_human_gate_nao_envio_incerto():
    # A subclasse não pode "vazar" a classificação para a superclasse:
    # uma FalhaGateHumano genérica (não FalhaEnvioIncerto) continua
    # HUMAN_GATE comum, nunca ENVIO_EXTERNO_INCERTO.
    assert classificar(FalhaGateHumano('politica generica')) == ClasseFalha.HUMAN_GATE


def test_ordem_do_mapa_verifica_subclasse_antes_da_superclasse():
    # Trava de regressão: se alguém reordenar o dict e colocar
    # FalhaGateHumano antes de FalhaEnvioIncerto, este teste falha.
    from magnata_os.orquestrador.classificador_falha import _MAPA
    tipos = list(_MAPA.keys())
    assert tipos.index(FalhaEnvioIncerto) < tipos.index(FalhaGateHumano)


def test_envio_incerto_nunca_e_transient():
    assert classificar(FalhaEnvioIncerto('reset pos-conexao')) != ClasseFalha.TRANSIENT


def test_falha_transitoria_continua_transient_sem_regressao():
    assert classificar(FalhaTransitoria('connect timeout')) == ClasseFalha.TRANSIENT


def test_excecao_desconhecida_continua_permanent_fail_safe():
    assert classificar(RuntimeError('bug inesperado')) == ClasseFalha.PERMANENT
