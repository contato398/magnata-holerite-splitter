"""Testes da política pura de competência ESPERADA da Prestação de Contas
(magnata_os/classificacao/competencia_esperada_prestacao.py).

Nenhum teste aqui usa relógio, e-mail, Airtable ou qualquer I/O -- só o
módulo puro em si.
"""
import pytest

from magnata_os.classificacao.competencia_esperada_prestacao import (
    ContextoCicloPrestacao,
    DeslocamentoCompetenciaCliente,
    PoliticaCompetenciaPrestacao,
)
from magnata_os.classificacao.contratos import ReferenciaCanonica


CLIENTE_A = ReferenciaCanonica("CLIENTE", "cliente-a")
CLIENTE_B = ReferenciaCanonica("CLIENTE", "cliente-b")


# ============================================================================
# ContextoCicloPrestacao
# ============================================================================

def test_contexto_ciclo_aceita_ano_mes_valido():
    contexto = ContextoCicloPrestacao(competencia_base=(2026, 7))
    assert contexto.competencia_base == (2026, 7)


@pytest.mark.parametrize("mes", [0, 13, -1])
def test_contexto_ciclo_rejeita_mes_fora_do_intervalo(mes):
    with pytest.raises(ValueError):
        ContextoCicloPrestacao(competencia_base=(2026, mes))


# ============================================================================
# DeslocamentoCompetenciaCliente
# ============================================================================

def test_deslocamento_exige_cliente_tipo_cliente():
    colaborador = ReferenciaCanonica("COLABORADOR", "colab-1")
    with pytest.raises(ValueError):
        DeslocamentoCompetenciaCliente(cliente=colaborador, competencia=(2026, 6))


def test_deslocamento_rejeita_mes_invalido():
    with pytest.raises(ValueError):
        DeslocamentoCompetenciaCliente(cliente=CLIENTE_A, competencia=(2026, 0))


def test_deslocamento_rejeita_tipo_documental_vazio():
    with pytest.raises(ValueError):
        DeslocamentoCompetenciaCliente(cliente=CLIENTE_A, competencia=(2026, 6), tipo_documental='   ')


def test_deslocamento_geral_aceita_tipo_documental_none():
    deslocamento = DeslocamentoCompetenciaCliente(cliente=CLIENTE_A, competencia=(2026, 6))
    assert deslocamento.tipo_documental is None


# ============================================================================
# PoliticaCompetenciaPrestacao -- construção
# ============================================================================

def test_politica_rejeita_version_vazia():
    with pytest.raises(ValueError):
        PoliticaCompetenciaPrestacao(version='   ')


def test_politica_aceita_sem_deslocamentos():
    politica = PoliticaCompetenciaPrestacao(version='1')
    assert politica.deslocamentos == ()


def test_politica_rejeita_deslocamento_especifico_duplicado():
    with pytest.raises(ValueError):
        PoliticaCompetenciaPrestacao(
            version='1',
            deslocamentos=(
                DeslocamentoCompetenciaCliente(CLIENTE_A, (2026, 6), 'holerite'),
                DeslocamentoCompetenciaCliente(CLIENTE_A, (2026, 5), 'holerite'),
            ),
        )


def test_politica_rejeita_deslocamento_geral_duplicado():
    with pytest.raises(ValueError):
        PoliticaCompetenciaPrestacao(
            version='1',
            deslocamentos=(
                DeslocamentoCompetenciaCliente(CLIENTE_A, (2026, 6)),
                DeslocamentoCompetenciaCliente(CLIENTE_A, (2026, 5)),
            ),
        )


def test_politica_aceita_especifico_e_geral_do_mesmo_cliente_como_chaves_distintas():
    # (cliente, "holerite") e (cliente, None) sao chaves DIFERENTES --
    # nunca colidem entre si, so consigo mesmo.
    politica = PoliticaCompetenciaPrestacao(
        version='1',
        deslocamentos=(
            DeslocamentoCompetenciaCliente(CLIENTE_A, (2026, 6), 'holerite'),
            DeslocamentoCompetenciaCliente(CLIENTE_A, (2026, 5)),
        ),
    )
    assert len(politica.deslocamentos) == 2


# ============================================================================
# PoliticaCompetenciaPrestacao.competencia_esperada_para -- precedencia
# ============================================================================

def test_sem_contexto_e_sem_deslocamento_devolve_none():
    politica = PoliticaCompetenciaPrestacao(version='1')
    assert politica.competencia_esperada_para(None, CLIENTE_A, 'holerite') is None


def test_com_contexto_e_sem_deslocamento_devolve_base():
    politica = PoliticaCompetenciaPrestacao(version='1')
    contexto = ContextoCicloPrestacao(competencia_base=(2026, 7))
    assert politica.competencia_esperada_para(contexto, CLIENTE_A, 'holerite') == (2026, 7)


def test_deslocamento_geral_sobrepoe_a_base():
    politica = PoliticaCompetenciaPrestacao(
        version='1',
        deslocamentos=(DeslocamentoCompetenciaCliente(CLIENTE_A, (2026, 5)),),
    )
    contexto = ContextoCicloPrestacao(competencia_base=(2026, 7))
    assert politica.competencia_esperada_para(contexto, CLIENTE_A, 'holerite') == (2026, 5)


def test_deslocamento_especifico_tem_precedencia_sobre_o_geral():
    politica = PoliticaCompetenciaPrestacao(
        version='1',
        deslocamentos=(
            DeslocamentoCompetenciaCliente(CLIENTE_A, (2026, 5)),
            DeslocamentoCompetenciaCliente(CLIENTE_A, (2026, 4), 'holerite'),
        ),
    )
    contexto = ContextoCicloPrestacao(competencia_base=(2026, 7))
    assert politica.competencia_esperada_para(contexto, CLIENTE_A, 'holerite') == (2026, 4)
    # outro tipo documental do mesmo cliente continua usando o geral
    assert politica.competencia_esperada_para(contexto, CLIENTE_A, 'extrato_cliente') == (2026, 5)


def test_deslocamento_de_um_cliente_nunca_afeta_outro():
    politica = PoliticaCompetenciaPrestacao(
        version='1',
        deslocamentos=(DeslocamentoCompetenciaCliente(CLIENTE_A, (2026, 5)),),
    )
    contexto = ContextoCicloPrestacao(competencia_base=(2026, 7))
    assert politica.competencia_esperada_para(contexto, CLIENTE_B, 'holerite') == (2026, 7)


def test_competencia_esperada_para_exige_cliente_tipo_cliente():
    politica = PoliticaCompetenciaPrestacao(version='1')
    colaborador = ReferenciaCanonica("COLABORADOR", "colab-1")
    with pytest.raises(ValueError):
        politica.competencia_esperada_para(None, colaborador, 'holerite')


# ============================================================================
# Fail-safe estrutural -- nunca le o relogio
# ============================================================================

def test_modulo_nunca_importa_relogio():
    """Prova estatica (AST): o modulo nunca importa datetime/date/time --
    a competencia base e SEMPRE um parametro explicito de quem chama,
    nunca descoberta pelo relogio dentro deste modulo (mesmo principio
    ja provado para composicao.py nao acessar rede)."""
    import ast
    import inspect

    import magnata_os.classificacao.competencia_esperada_prestacao as modulo

    codigo_fonte = inspect.getsource(modulo)
    arvore = ast.parse(codigo_fonte)
    modulos_importados = {
        alias.name.split('.')[0]
        for no in ast.walk(arvore)
        if isinstance(no, ast.Import)
        for alias in no.names
    } | {
        no.module.split('.')[0]
        for no in ast.walk(arvore)
        if isinstance(no, ast.ImportFrom) and no.module
    }
    proibidos = {'datetime', 'time', 'calendar'}
    assert not (modulos_importados & proibidos)
