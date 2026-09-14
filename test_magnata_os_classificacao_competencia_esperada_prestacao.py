"""Testes da política pura de competência ESPERADA da Prestação de Contas
(magnata_os/classificacao/competencia_esperada_prestacao.py).

Nenhum teste aqui usa relógio, e-mail, Airtable ou qualquer I/O -- só o
módulo puro em si.
"""
import pytest

from magnata_os.classificacao.competencia_esperada_prestacao import (
    DESLOCAMENTO_SKY_TATUI,
    POLITICA_COMPETENCIA_PRESTACAO_V1,
    REFERENCIA_CLIENTE_SKY_TATUI,
    ContextoCicloPrestacao,
    DeslocamentoCompetenciaCliente,
    PoliticaCompetenciaPorTipoNaoSuportadaError,
    PoliticaCompetenciaPrestacao,
    verificar_politica_sem_override_por_tipo,
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


def test_deslocamento_exige_exatamente_um_entre_competencia_e_offset():
    with pytest.raises(ValueError):
        DeslocamentoCompetenciaCliente(cliente=CLIENTE_A)  # nenhum dos dois
    with pytest.raises(ValueError):
        DeslocamentoCompetenciaCliente(cliente=CLIENTE_A, competencia=(2026, 6), offset_meses=-1)  # os dois


def test_deslocamento_relativo_rejeita_offset_zero():
    with pytest.raises(ValueError):
        DeslocamentoCompetenciaCliente(cliente=CLIENTE_A, offset_meses=0)


def test_deslocamento_relativo_aceita_offset_valido():
    deslocamento = DeslocamentoCompetenciaCliente(cliente=CLIENTE_A, offset_meses=-1)
    assert deslocamento.competencia is None
    assert deslocamento.offset_meses == -1


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
# Deslocamento RELATIVO -- exceção real do SKY Tatuí (missão "ATIVAR
# REGRA DE COMPETÊNCIA DO SKY TATUÍ"). Referência canônica confirmada
# por leitura somente-GET no Airtable (recrqv5NvbC37WfSl) -- ver
# docs/decisoes/competencia-esperada-prestacao-v1.md.
# ============================================================================

def test_caso1_sky_com_base_julho_resulta_junho():
    resultado = POLITICA_COMPETENCIA_PRESTACAO_V1.competencia_esperada_para(
        ContextoCicloPrestacao(competencia_base=(2026, 7)),
        REFERENCIA_CLIENTE_SKY_TATUI, 'holerite',
    )
    assert resultado == (2026, 6)


def test_caso2_sky_com_base_janeiro_vira_o_ano_para_dezembro_anterior():
    resultado = POLITICA_COMPETENCIA_PRESTACAO_V1.competencia_esperada_para(
        ContextoCicloPrestacao(competencia_base=(2027, 1)),
        REFERENCIA_CLIENTE_SKY_TATUI, 'holerite',
    )
    assert resultado == (2026, 12)


def test_caso3_cliente_comum_continua_usando_a_base():
    resultado = POLITICA_COMPETENCIA_PRESTACAO_V1.competencia_esperada_para(
        ContextoCicloPrestacao(competencia_base=(2026, 7)),
        CLIENTE_A, 'holerite',
    )
    assert resultado == (2026, 7)


def test_caso6_sky_sem_contexto_e_fail_safe_nunca_inventa():
    resultado = POLITICA_COMPETENCIA_PRESTACAO_V1.competencia_esperada_para(
        None, REFERENCIA_CLIENTE_SKY_TATUI, 'holerite',
    )
    assert resultado is None


def test_caso7_precedencia_especifica_por_tipo_continua_funcionando_com_relativo():
    politica = PoliticaCompetenciaPrestacao(
        version='1',
        deslocamentos=(
            DESLOCAMENTO_SKY_TATUI,  # geral: offset -1
            DeslocamentoCompetenciaCliente(
                REFERENCIA_CLIENTE_SKY_TATUI, tipo_documental='extrato_cliente', offset_meses=-2),
        ),
    )
    contexto = ContextoCicloPrestacao(competencia_base=(2026, 7))
    # tipo especifico (extrato_cliente) usa o offset proprio (-2)
    assert politica.competencia_esperada_para(contexto, REFERENCIA_CLIENTE_SKY_TATUI, 'extrato_cliente') == (2026, 5)
    # outro tipo continua usando o geral do SKY (-1)
    assert politica.competencia_esperada_para(contexto, REFERENCIA_CLIENTE_SKY_TATUI, 'holerite') == (2026, 6)


def test_caso8_conflito_de_deslocamentos_continua_fail_fast():
    with pytest.raises(ValueError):
        PoliticaCompetenciaPrestacao(
            version='1',
            deslocamentos=(
                DeslocamentoCompetenciaCliente(REFERENCIA_CLIENTE_SKY_TATUI, offset_meses=-1),
                DeslocamentoCompetenciaCliente(REFERENCIA_CLIENTE_SKY_TATUI, offset_meses=-2),
            ),
        )


def test_sky_absoluto_e_relativo_no_mesmo_cliente_ainda_conflita_na_chave():
    """Mesmo misturando forma absoluta e relativa, a CHAVE de conflito
    continua sendo (cliente, tipo_documental) -- nunca decide por forma."""
    with pytest.raises(ValueError):
        PoliticaCompetenciaPrestacao(
            version='1',
            deslocamentos=(
                DeslocamentoCompetenciaCliente(REFERENCIA_CLIENTE_SKY_TATUI, competencia=(2026, 6)),
                DeslocamentoCompetenciaCliente(REFERENCIA_CLIENTE_SKY_TATUI, offset_meses=-1),
            ),
        )


def test_offset_meses_aplica_corretamente_em_varias_viradas():
    from magnata_os.classificacao.competencia_esperada_prestacao import _aplicar_offset_meses
    assert _aplicar_offset_meses((2026, 7), -1) == (2026, 6)
    assert _aplicar_offset_meses((2027, 1), -1) == (2026, 12)
    assert _aplicar_offset_meses((2026, 1), -1) == (2025, 12)
    assert _aplicar_offset_meses((2026, 6), 1) == (2026, 7)
    assert _aplicar_offset_meses((2026, 12), 1) == (2027, 1)


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


# ============================================================================
# verificar_politica_sem_override_por_tipo (Incremento 3, evolução do
# contrato do ciclo de Prestação V1 -- fail-closed de competência por tipo)
# ============================================================================


def test_politica_geral_sem_override_por_tipo_e_aceita():
    """POLITICA_COMPETENCIA_PRESTACAO_V1 (a política real de produção,
    só com o deslocamento geral do SKY Tatuí) nunca deve falhar aqui --
    é exatamente o caso que a V1 do ciclo suporta hoje."""
    verificar_politica_sem_override_por_tipo(POLITICA_COMPETENCIA_PRESTACAO_V1)


def test_politica_vazia_e_aceita():
    verificar_politica_sem_override_por_tipo(PoliticaCompetenciaPrestacao(version='1'))


def test_politica_com_um_override_por_tipo_falha_fechado():
    politica = PoliticaCompetenciaPrestacao(
        version='1',
        deslocamentos=(
            DeslocamentoCompetenciaCliente(CLIENTE_A, tipo_documental='Holerite', offset_meses=-1),
        ),
    )
    with pytest.raises(PoliticaCompetenciaPorTipoNaoSuportadaError):
        verificar_politica_sem_override_por_tipo(politica)


def test_politica_com_multiplos_overrides_por_tipo_falha_fechado():
    politica = PoliticaCompetenciaPrestacao(
        version='1',
        deslocamentos=(
            DeslocamentoCompetenciaCliente(CLIENTE_A, tipo_documental='Holerite', offset_meses=-1),
            DeslocamentoCompetenciaCliente(CLIENTE_B, tipo_documental='Extrato', offset_meses=-2),
        ),
    )
    with pytest.raises(PoliticaCompetenciaPorTipoNaoSuportadaError):
        verificar_politica_sem_override_por_tipo(politica)


def test_politica_com_geral_e_especifico_misturados_ainda_falha_fechado():
    """O mesmo caso real testado em `test_deslocamento_geral_e_especifico_
    coexistem_mesmo_cliente` (SKY geral + extrato_cliente específico) --
    aqui provando que a guarda rejeita mesmo quando existe TAMBÉM um
    deslocamento geral válido no meio."""
    politica = PoliticaCompetenciaPrestacao(
        version='1',
        deslocamentos=(
            DESLOCAMENTO_SKY_TATUI,  # geral: offset -1
            DeslocamentoCompetenciaCliente(
                REFERENCIA_CLIENTE_SKY_TATUI, tipo_documental='extrato_cliente', offset_meses=-2),
        ),
    )
    with pytest.raises(PoliticaCompetenciaPorTipoNaoSuportadaError):
        verificar_politica_sem_override_por_tipo(politica)


def test_mensagem_de_erro_nunca_sugere_sentinela_ou_escolha_arbitraria():
    """A mensagem de erro deve nomear o cliente/tipo em conflito -- nunca
    sugerir contornar com um valor arbitrário (nenhuma menção a
    'sentinela'/'default'/'primeiro tipo')."""
    politica = PoliticaCompetenciaPrestacao(
        version='1',
        deslocamentos=(
            DeslocamentoCompetenciaCliente(CLIENTE_A, tipo_documental='Holerite', offset_meses=-1),
        ),
    )
    with pytest.raises(PoliticaCompetenciaPorTipoNaoSuportadaError) as excinfo:
        verificar_politica_sem_override_por_tipo(politica)
    mensagem = str(excinfo.value).lower()
    assert 'cliente-a' in mensagem
    assert 'holerite' in mensagem
    for termo_proibido in ('sentinela', 'default', 'primeiro tipo', 'arbitrari'):
        assert termo_proibido not in mensagem
