"""Testes do intérprete de ordem em linguagem natural
(`interpretar_ordem_operador_v1.py`) -- núcleo puro, sem nenhuma
dependência de Postgres/Airtable/corredor real nem de API de LLM
externa. Dados 100% sintéticos.

Mesmo padrão de `test_selecao_envio_operador_v1.py` (`_linha` como
helper de fixture, formato idêntico de linhas de diagnóstico)."""
import pytest

from magnata_os.orquestrador.interpretar_ordem_operador_v1 import (
    DuvidaInterpretacaoOrdem,
    InterpretacaoOrdemOperadorError,
    ResultadoInterpretacaoOrdem,
    interpretar_ordem_contra_linhas_diagnostico,
)
from magnata_os.orquestrador.selecao_envio_operador_v1 import ItemSelecaoEnvioOperador, SelecaoEnvioOperador


def _linha(cliente_id, competencia_id, tipo_documental, colaborador_id, situacao='PRONTO'):
    return {
        'cliente_id': cliente_id, 'competencia_id': competencia_id,
        'tipo_documental': tipo_documental, 'colaborador_id': colaborador_id,
        'situacao': situacao,
    }


DIRETORIO_2_PESSOAS = {'colab-1': 'Fulano da Silva', 'colab-2': 'Beltrano Souza'}


# ---------------------------------------------------------------------
# Contrato -- ResultadoInterpretacaoOrdem é uma união clara
# ---------------------------------------------------------------------

def test_resultado_rejeita_selecao_e_duvidas_juntas():
    with pytest.raises(InterpretacaoOrdemOperadorError):
        ResultadoInterpretacaoOrdem(
            selecao=SelecaoEnvioOperador(itens=()),
            duvidas=(DuvidaInterpretacaoOrdem(codigo='X', descricao='y', trecho_ordem=''),),
        )


def test_resultado_rejeita_vazio_dos_dois_lados():
    with pytest.raises(InterpretacaoOrdemOperadorError):
        ResultadoInterpretacaoOrdem(selecao=None, duvidas=())


def test_ordem_vazia_levanta_erro_estrutural():
    with pytest.raises(InterpretacaoOrdemOperadorError):
        interpretar_ordem_contra_linhas_diagnostico('   ', ())


# ---------------------------------------------------------------------
# Caminho feliz -- 1 destinatário, inequívoco
# ---------------------------------------------------------------------

def test_ordem_simples_com_assinatura():
    linhas = (_linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),)
    resultado = interpretar_ordem_contra_linhas_diagnostico(
        'manda pro Fulano da Silva o holerite de setembro, com assinatura digital e comprovante',
        linhas, diretorio_nomes=DIRETORIO_2_PESSOAS,
    )
    assert resultado.pronta
    assert resultado.selecao == SelecaoEnvioOperador(itens=(
        ItemSelecaoEnvioOperador(
            cliente_id='cliente-1', competencia_id='2026-09', colaborador_id='colab-1',
            tipos_documentais=('HOLERITE',), exigir_assinatura_digital_e_comprovante=True,
        ),
    ))


def test_ordem_simples_sem_assinatura_e_sem_mencao_default_false():
    linhas = (_linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),)
    resultado = interpretar_ordem_contra_linhas_diagnostico(
        'manda pro Fulano da Silva o holerite de setembro sem assinatura',
        linhas, diretorio_nomes=DIRETORIO_2_PESSOAS,
    )
    assert resultado.pronta
    assert resultado.selecao.itens[0].exigir_assinatura_digital_e_comprovante is False

    resultado_sem_mencao = interpretar_ordem_contra_linhas_diagnostico(
        'manda pro Fulano da Silva o holerite de setembro',
        linhas, diretorio_nomes=DIRETORIO_2_PESSOAS,
    )
    assert resultado_sem_mencao.pronta
    assert resultado_sem_mencao.selecao.itens[0].exigir_assinatura_digital_e_comprovante is False


def test_competencia_por_extenso_com_barra_ano_e_iso_produzem_o_mesmo_resultado():
    linhas = (_linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),)
    variantes = (
        'manda pro Fulano da Silva o holerite de setembro de 2026',
        'manda pro Fulano da Silva o holerite de 09/2026',
        'manda pro Fulano da Silva o holerite de 2026-09',
    )
    resultados = [
        interpretar_ordem_contra_linhas_diagnostico(ordem, linhas, diretorio_nomes=DIRETORIO_2_PESSOAS)
        for ordem in variantes
    ]
    assert all(r.pronta for r in resultados)
    assert len({r.selecao for r in resultados}) == 1


def test_competencia_implicita_quando_diagnostico_so_tem_1():
    """Mês não citado na ordem, mas o diagnóstico só cobre 1 competência
    para o cliente -- inferida sem ambiguidade, sem dúvida."""
    linhas = (_linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),)
    resultado = interpretar_ordem_contra_linhas_diagnostico(
        'manda pro Fulano da Silva o holerite', linhas, diretorio_nomes=DIRETORIO_2_PESSOAS,
    )
    assert resultado.pronta
    assert resultado.selecao.itens[0].competencia_id == '2026-09'


# ---------------------------------------------------------------------
# Múltiplos destinatários
# ---------------------------------------------------------------------

def test_multiplos_destinatarios_com_conector_repetido():
    linhas = (
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-2'),
    )
    resultado = interpretar_ordem_contra_linhas_diagnostico(
        'manda pro Fulano da Silva e pro Beltrano Souza o holerite de setembro, com assinatura digital e comprovante',
        linhas, diretorio_nomes=DIRETORIO_2_PESSOAS,
    )
    assert resultado.pronta
    colaboradores = {item.colaborador_id for item in resultado.selecao.itens}
    assert colaboradores == {'colab-1', 'colab-2'}
    assert all(item.exigir_assinatura_digital_e_comprovante for item in resultado.selecao.itens)


def test_multiplos_destinatarios_separados_por_virgula_e_e():
    linhas = (
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-2'),
    )
    resultado = interpretar_ordem_contra_linhas_diagnostico(
        'envia o holerite de setembro para Fulano da Silva, Beltrano Souza',
        linhas, diretorio_nomes=DIRETORIO_2_PESSOAS,
    )
    assert resultado.pronta
    colaboradores = {item.colaborador_id for item in resultado.selecao.itens}
    assert colaboradores == {'colab-1', 'colab-2'}


# ---------------------------------------------------------------------
# Dúvidas -- nunca uma escolha arbitrária
# ---------------------------------------------------------------------

def test_nome_ambiguo_vira_duvida_nunca_escolha_arbitraria():
    linhas = (
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-2'),
    )
    diretorio = {'colab-1': 'Fulano da Silva', 'colab-2': 'Fulano de Souza'}
    resultado = interpretar_ordem_contra_linhas_diagnostico(
        'manda pro Fulano o holerite de setembro', linhas, diretorio_nomes=diretorio,
    )
    assert not resultado.pronta
    codigos = {d.codigo for d in resultado.duvidas}
    assert 'DESTINATARIO_AMBIGUO' in codigos


def test_destinatario_nao_encontrado_vira_duvida():
    linhas = (_linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),)
    resultado = interpretar_ordem_contra_linhas_diagnostico(
        'manda pro Ciclano o holerite de setembro', linhas, diretorio_nomes=DIRETORIO_2_PESSOAS,
    )
    assert not resultado.pronta
    assert resultado.duvidas[0].codigo == 'DESTINATARIO_NAO_ENCONTRADO'


def test_documento_nao_encontrado_vira_duvida():
    linhas = (_linha('cliente-1', '2026-09', 'FGTS', 'colab-1'),)
    resultado = interpretar_ordem_contra_linhas_diagnostico(
        'manda pro Fulano da Silva o holerite de setembro', linhas, diretorio_nomes=DIRETORIO_2_PESSOAS,
    )
    assert not resultado.pronta
    assert resultado.duvidas[0].codigo == 'DOCUMENTO_NAO_ENCONTRADO'


def test_documento_nao_pronto_vira_duvida():
    linhas = (_linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1', situacao='PENDENTE'),)
    resultado = interpretar_ordem_contra_linhas_diagnostico(
        'manda pro Fulano da Silva o holerite de setembro', linhas, diretorio_nomes=DIRETORIO_2_PESSOAS,
    )
    assert not resultado.pronta
    assert resultado.duvidas[0].codigo == 'DOCUMENTO_NAO_PRONTO'


def test_competencia_ausente_e_nao_inferivel_vira_duvida():
    linhas = (
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),
        _linha('cliente-1', '2026-08', 'HOLERITE', 'colab-1'),
    )
    resultado = interpretar_ordem_contra_linhas_diagnostico(
        'manda pro Fulano da Silva o holerite', linhas, diretorio_nomes=DIRETORIO_2_PESSOAS,
    )
    assert not resultado.pronta
    assert resultado.duvidas[0].codigo == 'COMPETENCIA_AUSENTE_E_NAO_INFERIVEL'


def test_tipo_documental_nao_reconhecido_vira_duvida():
    linhas = (_linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),)
    resultado = interpretar_ordem_contra_linhas_diagnostico(
        'manda pro Fulano da Silva alguma coisa de setembro', linhas, diretorio_nomes=DIRETORIO_2_PESSOAS,
    )
    assert not resultado.pronta
    codigos = {d.codigo for d in resultado.duvidas}
    assert 'TIPO_DOCUMENTAL_NAO_IDENTIFICADO' in codigos


def test_sem_diretorio_nomes_usa_colaborador_id_como_nome():
    """Limitação declarada: sem diretório de nomes, colaborador_id
    (opaco em produção) é o próprio texto de correspondência."""
    linhas = (_linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),)
    resultado = interpretar_ordem_contra_linhas_diagnostico(
        'manda pro colab-1 o holerite de setembro', linhas,
    )
    assert resultado.pronta
    assert resultado.selecao.itens[0].colaborador_id == 'colab-1'


# ---------------------------------------------------------------------
# Idempotência
# ---------------------------------------------------------------------

def test_idempotente_mesma_ordem_mesmo_diagnostico_mesmo_resultado():
    linhas = (
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-2'),
    )
    ordem = 'manda pro Fulano da Silva e pro Beltrano Souza o holerite de setembro, com assinatura digital e comprovante'
    r1 = interpretar_ordem_contra_linhas_diagnostico(ordem, linhas, diretorio_nomes=DIRETORIO_2_PESSOAS)
    r2 = interpretar_ordem_contra_linhas_diagnostico(ordem, linhas, diretorio_nomes=DIRETORIO_2_PESSOAS)
    assert r1 == r2


def test_idempotente_tambem_para_resultado_com_duvida():
    linhas = (
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-2'),
    )
    diretorio = {'colab-1': 'Fulano da Silva', 'colab-2': 'Fulano de Souza'}
    ordem = 'manda pro Fulano o holerite de setembro'
    r1 = interpretar_ordem_contra_linhas_diagnostico(ordem, linhas, diretorio_nomes=diretorio)
    r2 = interpretar_ordem_contra_linhas_diagnostico(ordem, linhas, diretorio_nomes=diretorio)
    assert r1 == r2
