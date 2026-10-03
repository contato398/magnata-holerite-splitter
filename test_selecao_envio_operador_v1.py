"""Testes da camada de seleção/curadoria do operador
(`selecao_envio_operador_v1.py`) -- contrato puro + validação contra o
diagnóstico, sem nenhuma dependência de Postgres/Airtable/corredor real.
Dados 100% sintéticos.
"""
import pytest

from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    DiagnosticoCliente,
    DiagnosticoNecessidade,
    DiagnosticoPrestacao,
    EstadoPacotePrestacao,
    SituacaoNecessidade,
)
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.orquestrador.selecao_envio_operador_v1 import (
    ItemSelecaoEnvioOperador,
    ItemSelecaoInvalido,
    SelecaoApontaParaNecessidadeInexistente,
    SelecaoApontaParaNecessidadeNaoPronta,
    SelecaoEnvioOperador,
    validar_selecao_contra_diagnostico,
    validar_selecao_contra_linhas_diagnostico,
)


def _linha(cliente_id, competencia_id, tipo_documental, colaborador_id, situacao='PRONTO'):
    return {
        'cliente_id': cliente_id, 'competencia_id': competencia_id,
        'tipo_documental': tipo_documental, 'colaborador_id': colaborador_id,
        'situacao': situacao,
    }


def _item(*, cliente_id='cliente-1', competencia_id='2026-09', colaborador_id='colab-1',
          tipos=('HOLERITE',), exigir=False):
    return ItemSelecaoEnvioOperador(
        cliente_id=cliente_id, competencia_id=competencia_id, colaborador_id=colaborador_id,
        tipos_documentais=tuple(tipos), exigir_assinatura_digital_e_comprovante=exigir,
    )


# ---------------------------------------------------------------------
# Contrato -- validação estrutural (__post_init__)
# ---------------------------------------------------------------------

def test_item_selecao_rejeita_tipos_documentais_vazio():
    with pytest.raises(ItemSelecaoInvalido):
        ItemSelecaoEnvioOperador(
            cliente_id='c', competencia_id='2026-09', colaborador_id='colab',
            tipos_documentais=(), exigir_assinatura_digital_e_comprovante=False,
        )


def test_item_selecao_rejeita_tipo_duplicado():
    with pytest.raises(ItemSelecaoInvalido):
        _item(tipos=('HOLERITE', 'HOLERITE'))


def test_item_selecao_rejeita_exigir_nao_booleano():
    with pytest.raises(ItemSelecaoInvalido):
        ItemSelecaoEnvioOperador(
            cliente_id='c', competencia_id='2026-09', colaborador_id='colab',
            tipos_documentais=('HOLERITE',), exigir_assinatura_digital_e_comprovante=1,
        )


def test_selecao_rejeita_colaborador_repetido_em_2_itens_do_mesmo_cliente_competencia():
    with pytest.raises(ItemSelecaoInvalido):
        SelecaoEnvioOperador(itens=(
            _item(colaborador_id='colab-1', tipos=('HOLERITE',)),
            _item(colaborador_id='colab-1', tipos=('FOLHA_PONTO',)),
        ))


# ---------------------------------------------------------------------
# Validação contra o diagnóstico (núcleo puro, linhas)
# ---------------------------------------------------------------------

def test_1_documento_para_1_destinatario_valida_ok():
    linhas = (_linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),)
    selecao = SelecaoEnvioOperador(itens=(_item(tipos=('HOLERITE',)),))
    validados = validar_selecao_contra_linhas_diagnostico(linhas, selecao)
    assert len(validados) == 1
    assert validados[0].tipos_documentais == ('HOLERITE',)


def test_n_documentos_para_1_destinatario_valida_ok():
    linhas = (
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),
        _linha('cliente-1', '2026-09', 'FOLHA_PONTO', 'colab-1'),
    )
    selecao = SelecaoEnvioOperador(itens=(_item(tipos=('HOLERITE', 'FOLHA_PONTO')),))
    validados = validar_selecao_contra_linhas_diagnostico(linhas, selecao)
    assert len(validados) == 1
    assert set(validados[0].tipos_documentais) == {'HOLERITE', 'FOLHA_PONTO'}


def test_1_documento_para_n_destinatarios_valida_ok():
    linhas = (
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-2'),
    )
    selecao = SelecaoEnvioOperador(itens=(
        _item(colaborador_id='colab-1', tipos=('HOLERITE',)),
        _item(colaborador_id='colab-2', tipos=('HOLERITE',)),
    ))
    validados = validar_selecao_contra_linhas_diagnostico(linhas, selecao)
    assert {v.colaborador_id for v in validados} == {'colab-1', 'colab-2'}


def test_exigir_assinatura_true_e_false_lado_a_lado():
    linhas = (
        _linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),
        _linha('cliente-1', '2026-09', 'CONTRATO', 'colab-2'),
    )
    selecao = SelecaoEnvioOperador(itens=(
        _item(colaborador_id='colab-1', tipos=('HOLERITE',), exigir=False),
        _item(colaborador_id='colab-2', tipos=('CONTRATO',), exigir=True),
    ))
    validados = validar_selecao_contra_linhas_diagnostico(linhas, selecao)
    por_colaborador = {v.colaborador_id: v.exigir_assinatura_digital_e_comprovante for v in validados}
    assert por_colaborador == {'colab-1': False, 'colab-2': True}


def test_selecao_apontando_para_necessidade_nao_pronta_e_rejeitada():
    linhas = (_linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1', situacao='EM_REVISAO'),)
    selecao = SelecaoEnvioOperador(itens=(_item(tipos=('HOLERITE',)),))
    with pytest.raises(SelecaoApontaParaNecessidadeNaoPronta):
        validar_selecao_contra_linhas_diagnostico(linhas, selecao)


def test_selecao_apontando_para_colaborador_inexistente_e_rejeitada():
    linhas = (_linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),)
    selecao = SelecaoEnvioOperador(itens=(_item(colaborador_id='colab-fantasma', tipos=('HOLERITE',)),))
    with pytest.raises(SelecaoApontaParaNecessidadeInexistente):
        validar_selecao_contra_linhas_diagnostico(linhas, selecao)


def test_selecao_apontando_para_documento_inexistente_e_rejeitada():
    linhas = (_linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),)
    selecao = SelecaoEnvioOperador(itens=(_item(tipos=('FOLHA_PONTO',)),))
    with pytest.raises(SelecaoApontaParaNecessidadeInexistente):
        validar_selecao_contra_linhas_diagnostico(linhas, selecao)


def test_sem_selecao_nenhuma_devolve_vazio_nunca_erro():
    linhas = (_linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),)
    selecao = SelecaoEnvioOperador(itens=())
    assert validar_selecao_contra_linhas_diagnostico(linhas, selecao) == ()


def test_idempotencia_validar_2_vezes_produz_mesmo_resultado():
    linhas = (_linha('cliente-1', '2026-09', 'HOLERITE', 'colab-1'),)
    selecao = SelecaoEnvioOperador(itens=(_item(tipos=('HOLERITE',)),))
    primeiro = validar_selecao_contra_linhas_diagnostico(linhas, selecao)
    segundo = validar_selecao_contra_linhas_diagnostico(linhas, selecao)
    assert primeiro == segundo


# ---------------------------------------------------------------------
# Ponta a ponta com as dataclasses reais de DiagnosticoPrestacao
# ---------------------------------------------------------------------

def test_validar_contra_diagnostico_real_end_to_end():
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-1')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-09')
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-1')
    necessidade = NecessidadeDocumentoPrestacao(
        cliente=cliente, competencia=competencia, tipo_documental='HOLERITE',
        motivo_exigencia='teste', colaborador=colaborador,
    )
    diagnostico = DiagnosticoPrestacao(
        competencia_base='2026-09',
        clientes=(
            DiagnosticoCliente(
                cliente=cliente, competencia=competencia, estado_pacote=EstadoPacotePrestacao.PRONTO,
                necessidades=(
                    DiagnosticoNecessidade(
                        necessidade=necessidade, situacao=SituacaoNecessidade.PRONTO,
                        documentos_avaliados=('doc-1',), documentos_elegiveis=('doc-1',),
                    ),
                ),
            ),
        ),
    )
    selecao = SelecaoEnvioOperador(itens=(_item(tipos=('HOLERITE',)),))
    validados = validar_selecao_contra_diagnostico(diagnostico, selecao)
    assert len(validados) == 1
    assert validados[0].colaborador_id == 'colab-1'
