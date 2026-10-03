"""Testes de `magnata_os/classificacao/politica_reenvio_pacote_holerite_ponto_v1.py`.

Cada caso replica, por entrada/saída, um dos ramos de
`_reenviar_pacote_holerite_ponto` em `app.py` -- sem tocar `app.py`,
sem Flask, sem Airtable, sem rede."""
from magnata_os.classificacao.politica_reenvio_pacote_holerite_ponto_v1 import (
    AcaoReenvioPacote,
    avaliar_concorrencia_reenvio,
    avaliar_integridade_documento,
    avaliar_pre_condicoes_reenvio,
)


def _pre_condicoes_base():
    return dict(
        elegivel=True,
        whatsapp_presente=True,
        reenvios_ate_agora=0,
        max_reenvios=5,
        quantidade_anexos_originais=2,
        quantidade_hashes_gravados=2,
    )


def test_pre_condicoes_vinculo_nao_ativo_bloqueia_antes_de_tudo():
    kwargs = _pre_condicoes_base()
    kwargs['elegivel'] = False
    # Mesmo com todos os outros critérios ruins também, o vínculo vence
    # primeiro -- replica a ordem exata de app.py.
    kwargs['whatsapp_presente'] = False
    kwargs['reenvios_ate_agora'] = 99

    resultado = avaliar_pre_condicoes_reenvio(**kwargs)

    assert resultado.bloqueado is True
    assert resultado.acao == AcaoReenvioPacote.CANCELADO_VINCULO_NAO_ATIVO


def test_pre_condicoes_whatsapp_ausente_bloqueia():
    kwargs = _pre_condicoes_base()
    kwargs['whatsapp_presente'] = False

    resultado = avaliar_pre_condicoes_reenvio(**kwargs)

    assert resultado.bloqueado is True
    assert resultado.acao == AcaoReenvioPacote.WHATSAPP_AUSENTE


def test_pre_condicoes_limite_de_reenvios_excedido_bloqueia():
    kwargs = _pre_condicoes_base()
    kwargs['reenvios_ate_agora'] = 5
    kwargs['max_reenvios'] = 5

    resultado = avaliar_pre_condicoes_reenvio(**kwargs)

    assert resultado.bloqueado is True
    assert resultado.acao == AcaoReenvioPacote.LIMITE_REENVIOS_EXCEDIDO


def test_pre_condicoes_abaixo_do_limite_nao_bloqueia_por_isso():
    kwargs = _pre_condicoes_base()
    kwargs['reenvios_ate_agora'] = 4
    kwargs['max_reenvios'] = 5

    resultado = avaliar_pre_condicoes_reenvio(**kwargs)

    assert resultado.bloqueado is False
    assert resultado.acao == AcaoReenvioPacote.LIBERADO_PARA_ENVIO


def test_pre_condicoes_estrutura_inesperada_anexos_bloqueia():
    kwargs = _pre_condicoes_base()
    kwargs['quantidade_anexos_originais'] = 1

    resultado = avaliar_pre_condicoes_reenvio(**kwargs)

    assert resultado.bloqueado is True
    assert resultado.acao == AcaoReenvioPacote.ESTRUTURA_INESPERADA


def test_pre_condicoes_estrutura_inesperada_hashes_bloqueia():
    kwargs = _pre_condicoes_base()
    kwargs['quantidade_hashes_gravados'] = 3

    resultado = avaliar_pre_condicoes_reenvio(**kwargs)

    assert resultado.bloqueado is True
    assert resultado.acao == AcaoReenvioPacote.ESTRUTURA_INESPERADA


def test_pre_condicoes_liberado_quando_tudo_ok():
    resultado = avaliar_pre_condicoes_reenvio(**_pre_condicoes_base())

    assert resultado.bloqueado is False
    assert resultado.acao == AcaoReenvioPacote.LIBERADO_PARA_ENVIO


def test_limite_e_estrutura_inesperada_sao_acoes_distintas():
    # Em app.py os dois compartilham item['acao'] == 'bloqueado_para_
    # revisao' e só se distinguem por item['erro']; o Enum aqui usa o
    # valor de 'erro' exatamente para que os dois nomes nunca colidam
    # no mesmo membro (aliasing).
    assert AcaoReenvioPacote.LIMITE_REENVIOS_EXCEDIDO != AcaoReenvioPacote.ESTRUTURA_INESPERADA


def test_integridade_documento_hashes_iguais_eh_valido():
    assert avaliar_integridade_documento(
        frozenset({'aaa', 'bbb'}), frozenset({'aaa', 'bbb'}),
    ) is True


def test_integridade_documento_hash_trocado_eh_invalido():
    assert avaliar_integridade_documento(
        frozenset({'aaa', 'ccc'}), frozenset({'aaa', 'bbb'}),
    ) is False


def test_integridade_documento_quantidade_diferente_eh_invalido():
    assert avaliar_integridade_documento(
        frozenset({'aaa'}), frozenset({'aaa', 'bbb'}),
    ) is False


def test_concorrencia_status_ainda_reenviar_libera():
    assert avaliar_concorrencia_reenvio('Reenviar') is True


def test_concorrencia_status_mudou_bloqueia():
    assert avaliar_concorrencia_reenvio('Pendente') is False


def test_concorrencia_status_ausente_bloqueia():
    assert avaliar_concorrencia_reenvio(None) is False
