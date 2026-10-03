"""Testes de `politica_situacao_distribuicao_colaborador_v1.py`.

Cobre as 4 situações possíveis e a extração correta de motivos, para os
dois casos reais que motivaram a extração: Holerite (2 requisitos
documentais: arquivo + folha mensal) e Folha de Ponto (1 requisito:
anexo) -- mesma árvore de decisão, sem duplicar código."""
from magnata_os.classificacao.politica_situacao_distribuicao_colaborador_v1 import (
    SITUACAO_PENDENTE,
    SITUACAO_PRONTO_AMBOS,
    SITUACAO_PRONTO_PACOTE_CLIENTE,
    SITUACAO_PRONTO_WHATSAPP_COLABORADOR,
    CriteriosDistribuicaoColaborador,
    classificar_situacao_distribuicao,
)


def _criterios_holerite(
    *,
    funcionario_identificado=True,
    whatsapp_disponivel=True,
    arquivo_ok=True,
    folha_ok=True,
    cliente_identificado=True,
    email_cliente_disponivel=True,
):
    return CriteriosDistribuicaoColaborador(
        funcionario_identificado=funcionario_identificado,
        whatsapp_disponivel=whatsapp_disponivel,
        requisitos_documentais={
            'arquivo_holerite_ausente': arquivo_ok,
            'folha_mensal_ausente': folha_ok,
        },
        cliente_identificado=cliente_identificado,
        email_cliente_disponivel=email_cliente_disponivel,
    )


def _criterios_folha_ponto(
    *,
    whatsapp_disponivel=True,
    pdf_anexo_ok=True,
    cliente_identificado=True,
    email_cliente_disponivel=True,
):
    return CriteriosDistribuicaoColaborador(
        funcionario_identificado=True,
        whatsapp_disponivel=whatsapp_disponivel,
        requisitos_documentais={'pdf_folha_ponto_ausente': pdf_anexo_ok},
        cliente_identificado=cliente_identificado,
        email_cliente_disponivel=email_cliente_disponivel,
    )


def test_holerite_pronto_ambos_quando_whatsapp_e_cliente_ok():
    resultado = classificar_situacao_distribuicao(_criterios_holerite())

    assert resultado.situacao == SITUACAO_PRONTO_AMBOS
    assert resultado.ok_whatsapp is True
    assert resultado.ok_cliente is True
    assert resultado.motivos == ()


def test_holerite_pronto_whatsapp_colaborador_sem_cliente():
    resultado = classificar_situacao_distribuicao(
        _criterios_holerite(cliente_identificado=False)
    )

    assert resultado.situacao == SITUACAO_PRONTO_WHATSAPP_COLABORADOR
    assert resultado.ok_whatsapp is True
    assert resultado.ok_cliente is False
    assert resultado.motivos == ('cliente_local_nao_identificado',)


def test_holerite_pronto_pacote_cliente_sem_whatsapp():
    resultado = classificar_situacao_distribuicao(
        _criterios_holerite(whatsapp_disponivel=False)
    )

    assert resultado.situacao == SITUACAO_PRONTO_PACOTE_CLIENTE
    assert resultado.ok_whatsapp is False
    assert resultado.ok_cliente is True
    assert resultado.motivos == ('whatsapp_ausente',)


def test_holerite_sem_funcionario_e_sem_whatsapp_mas_cliente_ok_cai_no_pacote_cliente():
    # Réplica exata do legado: `ok_cliente` nunca depende de
    # `func_ids`/`whatsapp` -- só de cliente/e-mail/documentos. Logo,
    # funcionário e WhatsApp ausentes não geram 'pendente' por si só
    # enquanto o caminho do cliente continuar elegível.
    resultado = classificar_situacao_distribuicao(
        _criterios_holerite(funcionario_identificado=False, whatsapp_disponivel=False)
    )

    assert resultado.situacao == SITUACAO_PRONTO_PACOTE_CLIENTE
    assert resultado.ok_whatsapp is False
    assert resultado.ok_cliente is True
    assert resultado.motivos == ('funcionario_nao_identificado', 'whatsapp_ausente')


def test_holerite_pendente_quando_nenhum_caminho_e_elegivel():
    resultado = classificar_situacao_distribuicao(
        _criterios_holerite(
            funcionario_identificado=False,
            whatsapp_disponivel=False,
            cliente_identificado=False,
        )
    )

    assert resultado.situacao == SITUACAO_PENDENTE
    assert resultado.ok_whatsapp is False
    assert resultado.ok_cliente is False
    assert resultado.motivos == (
        'funcionario_nao_identificado',
        'whatsapp_ausente',
        'cliente_local_nao_identificado',
    )


def test_holerite_arquivo_ausente_bloqueia_os_dois_caminhos():
    resultado = classificar_situacao_distribuicao(
        _criterios_holerite(arquivo_ok=False)
    )

    assert resultado.situacao == SITUACAO_PENDENTE
    assert resultado.ok_whatsapp is False
    assert resultado.ok_cliente is False
    assert resultado.motivos == ('arquivo_holerite_ausente',)


def test_holerite_folha_mensal_ausente_bloqueia_os_dois_caminhos():
    resultado = classificar_situacao_distribuicao(
        _criterios_holerite(folha_ok=False)
    )

    assert resultado.situacao == SITUACAO_PENDENTE
    assert resultado.ok_whatsapp is False
    assert resultado.ok_cliente is False
    assert resultado.motivos == ('folha_mensal_ausente',)


def test_holerite_cliente_identificado_sem_email_gera_motivo_especifico():
    resultado = classificar_situacao_distribuicao(
        _criterios_holerite(cliente_identificado=True, email_cliente_disponivel=False)
    )

    assert resultado.situacao == SITUACAO_PRONTO_WHATSAPP_COLABORADOR
    assert resultado.motivos == ('email_cliente_ausente',)


def test_holerite_cliente_nao_identificado_nunca_soma_motivo_de_email():
    # cliente_identificado=False já é o motivo -- nunca adiciona também
    # 'email_cliente_ausente' por cima (replica o `elif` do legado).
    resultado = classificar_situacao_distribuicao(
        _criterios_holerite(cliente_identificado=False, email_cliente_disponivel=False)
    )

    assert resultado.motivos == ('cliente_local_nao_identificado',)


def test_folha_ponto_pronto_ambos():
    resultado = classificar_situacao_distribuicao(_criterios_folha_ponto())

    assert resultado.situacao == SITUACAO_PRONTO_AMBOS
    assert resultado.motivos == ()


def test_folha_ponto_pendente_sem_anexo_bloqueia_os_dois_caminhos():
    resultado = classificar_situacao_distribuicao(
        _criterios_folha_ponto(pdf_anexo_ok=False)
    )

    assert resultado.situacao == SITUACAO_PENDENTE
    assert resultado.ok_whatsapp is False
    assert resultado.ok_cliente is False
    assert resultado.motivos == ('pdf_folha_ponto_ausente',)


def test_resultado_e_imutavel():
    resultado = classificar_situacao_distribuicao(_criterios_holerite())
    try:
        resultado.situacao = SITUACAO_PENDENTE
    except Exception:
        pass
    else:
        raise AssertionError('ResultadoClassificacaoDistribuicao deveria ser frozen')
