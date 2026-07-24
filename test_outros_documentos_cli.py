"""
Testes do comando manual interno (scripts/outros_documentos_cli.py).

Nenhum destes testes acessa o Airtable real -- requests.get/patch,
_at_throttle, input e logger sao todos mockados. O comando em si nunca e
executado contra producao a partir daqui.
"""
from unittest.mock import patch, Mock

import pytest

from scripts import outros_documentos_cli as cli


def _resultado_dry_run(envio_id, qtd_a_adicionar=1, conflitos=None, filenames=None):
    return {
        'envios': [{
            'envio_id': envio_id,
            'envio_nome': 'Envio Teste',
            'cliente': ['Cliente Teste'],
            'status_atual': 'Pendente',
            'qtd_recibos_novos': qtd_a_adicionar,
            'qtd_a_adicionar': qtd_a_adicionar,
            'filenames_a_adicionar': filenames or (['novo.pdf'] if qtd_a_adicionar else []),
            'qtd_ja_existentes_no_envio': 2,
            'duplicados_evitados': [],
            'conflitos': conflitos or [],
        }],
        'rejeitados': [],
    }


# --------------------------------------------------------------- dry-run ---

def test_dry_run_nunca_chama_aplicar():
    with patch('scripts.outros_documentos_cli._dry_run_outros_documentos_para_envios',
               return_value=_resultado_dry_run('recEnvioA')) as mock_dry, \
         patch('scripts.outros_documentos_cli._aplicar_outros_documentos_no_envio') as mock_aplicar:
        cli.cmd_dry_run('Junho 2026', 'corr123')

    mock_dry.assert_called_once_with('Junho 2026')
    mock_aplicar.assert_not_called()


# ---------------------------------------------------------------- aplicar --

def test_aplicar_sem_confirmar_nao_chama_aplicar():
    with patch('scripts.outros_documentos_cli.confirmar_campo_arquivos', return_value=True), \
         patch('scripts.outros_documentos_cli._dry_run_outros_documentos_para_envios',
               return_value=_resultado_dry_run('recEnvioA')), \
         patch('scripts.outros_documentos_cli._aplicar_outros_documentos_no_envio') as mock_aplicar:
        resultado = cli.cmd_aplicar('Junho 2026', 'recEnvioA', 'corr123',
                                     confirmar_input=lambda _: 'nao')

    assert resultado == 'cancelado'
    mock_aplicar.assert_not_called()


def test_aplicar_entrada_diferente_de_confirmar_cancela():
    entradas_invalidas = ['confirmar', 'CONFIRMAR ', 'sim', '', 'CONFIRMA', 'yes']
    with patch('scripts.outros_documentos_cli.confirmar_campo_arquivos', return_value=True), \
         patch('scripts.outros_documentos_cli._dry_run_outros_documentos_para_envios',
               return_value=_resultado_dry_run('recEnvioA')), \
         patch('scripts.outros_documentos_cli._aplicar_outros_documentos_no_envio') as mock_aplicar:
        for entrada in entradas_invalidas:
            resultado = cli.cmd_aplicar('Junho 2026', 'recEnvioA', 'corr123',
                                         confirmar_input=lambda _, e=entrada: e)
            assert resultado == 'cancelado', f'entrada {entrada!r} deveria cancelar'

    mock_aplicar.assert_not_called()


def test_aplicar_com_conflito_nao_chama_aplicar():
    conflitos = [{'filename': 'x.pdf', 'motivo': 'mesmo_nome_tamanho_diferente'}]
    with patch('scripts.outros_documentos_cli.confirmar_campo_arquivos', return_value=True), \
         patch('scripts.outros_documentos_cli._dry_run_outros_documentos_para_envios',
               return_value=_resultado_dry_run('recEnvioA', conflitos=conflitos)), \
         patch('scripts.outros_documentos_cli._aplicar_outros_documentos_no_envio') as mock_aplicar:
        resultado = cli.cmd_aplicar('Junho 2026', 'recEnvioA', 'corr123',
                                     confirmar_input=lambda _: 'CONFIRMAR')

    assert resultado == 'conflito_detectado'
    mock_aplicar.assert_not_called()


def test_aplicar_sem_novidade_nao_chama_aplicar_nem_patch():
    with patch('scripts.outros_documentos_cli.confirmar_campo_arquivos', return_value=True), \
         patch('scripts.outros_documentos_cli._dry_run_outros_documentos_para_envios',
               return_value=_resultado_dry_run('recEnvioA', qtd_a_adicionar=0)), \
         patch('scripts.outros_documentos_cli._aplicar_outros_documentos_no_envio') as mock_aplicar:
        resultado = cli.cmd_aplicar('Junho 2026', 'recEnvioA', 'corr123',
                                     confirmar_input=lambda _: 'CONFIRMAR')

    assert resultado == 'sem_novidade'
    mock_aplicar.assert_not_called()


def test_aplicar_confirmado_chama_aplicar_exatamente_uma_vez():
    with patch('scripts.outros_documentos_cli.confirmar_campo_arquivos', return_value=True), \
         patch('scripts.outros_documentos_cli._ler_attachments_atuais', return_value=['attA', 'attB']), \
         patch('scripts.outros_documentos_cli._dry_run_outros_documentos_para_envios',
               return_value=_resultado_dry_run('recEnvioA')), \
         patch('scripts.outros_documentos_cli._aplicar_outros_documentos_no_envio',
               return_value={'envio_id': 'recEnvioA', 'status': 'aplicado',
                              'adicionados': ['novo.pdf'], 'total_apos': 3}) as mock_aplicar:
        resultado = cli.cmd_aplicar('Junho 2026', 'recEnvioA', 'corr123',
                                     confirmar_input=lambda _: 'CONFIRMAR')

    assert resultado == 'aplicado'
    mock_aplicar.assert_called_once_with('recEnvioA', 'Junho 2026')


def test_aplicar_nao_permite_multiplos_envio_ids_em_uma_chamada():
    """cmd_aplicar so aceita um envio_id por assinatura -- nao ha parametro
    de lista/lote. Confere isso na propria assinatura da funcao."""
    import inspect
    parametros = inspect.signature(cli.cmd_aplicar).parameters
    assert 'envio_id' in parametros
    assert 'envio_ids' not in parametros
    assert parametros['envio_id'].kind != inspect.Parameter.VAR_POSITIONAL


# ------------------------------------------------------- campo Arquivos ----

def test_campo_nao_confirmado_bloqueia_aplicacao_sem_ler_nem_escrever():
    with patch('scripts.outros_documentos_cli.confirmar_campo_arquivos', return_value=False), \
         patch('scripts.outros_documentos_cli._dry_run_outros_documentos_para_envios') as mock_dry, \
         patch('scripts.outros_documentos_cli._aplicar_outros_documentos_no_envio') as mock_aplicar:
        resultado = cli.cmd_aplicar('Junho 2026', 'recEnvioA', 'corr123')

    assert resultado == 'CAMPO_ARQUIVOS_NAO_CONFIRMADO'
    mock_dry.assert_not_called()
    mock_aplicar.assert_not_called()


def test_confirmar_campo_arquivos_confere_field_id_via_meta_api():
    resposta = Mock(ok=True, status_code=200, json=lambda: {
        'tables': [{
            'id': cli.TABLE_ENVIOS,
            'fields': [{'id': cli.F_ENVIO_ARQUIVOS, 'name': 'Arquivos'}],
        }],
    })
    with patch('scripts.outros_documentos_cli.requests.get', return_value=resposta) as mock_get, \
         patch('scripts.outros_documentos_cli.requests.patch') as mock_patch:
        assert cli.confirmar_campo_arquivos() is True

    mock_patch.assert_not_called()  # confirmacao e leitura pura, nunca escreve
    assert mock_get.call_args.args[0].startswith('https://api.airtable.com/v0/meta/')


def test_confirmar_campo_arquivos_retorna_false_se_field_id_diferente():
    resposta = Mock(ok=True, status_code=200, json=lambda: {
        'tables': [{
            'id': cli.TABLE_ENVIOS,
            'fields': [{'id': 'fldOUTROCAMPO', 'name': 'Arquivos'}],
        }],
    })
    with patch('scripts.outros_documentos_cli.requests.get', return_value=resposta):
        assert cli.confirmar_campo_arquivos() is False


def test_confirmar_campo_arquivos_retorna_false_se_campo_nao_existir():
    resposta = Mock(ok=True, status_code=200, json=lambda: {
        'tables': [{'id': cli.TABLE_ENVIOS, 'fields': [{'id': 'fldX', 'name': 'Outro Campo'}]}],
    })
    with patch('scripts.outros_documentos_cli.requests.get', return_value=resposta):
        assert cli.confirmar_campo_arquivos() is False


def test_confirmar_campo_arquivos_retorna_false_se_meta_api_falhar():
    with patch('scripts.outros_documentos_cli.requests.get', side_effect=Exception('timeout')):
        assert cli.confirmar_campo_arquivos() is False


def test_confirmar_campo_arquivos_retorna_false_se_resposta_nao_ok():
    resposta = Mock(ok=False, status_code=403, json=lambda: {})
    with patch('scripts.outros_documentos_cli.requests.get', return_value=resposta):
        assert cli.confirmar_campo_arquivos() is False


# --------------------------------------------------------- configuracao ----

def test_configuracao_ausente_falha_com_mensagem_segura():
    with patch('scripts.outros_documentos_cli.AIRTABLE_API_KEY', ''), \
         patch('scripts.outros_documentos_cli.BASE_ID', 'appXXXX'):
        with pytest.raises(cli.ConfiguracaoAusente) as exc_info:
            cli._validar_configuracao()

    assert 'AIRTABLE_API_KEY' in str(exc_info.value)
    assert 'appXXXX' not in str(exc_info.value)  # nenhum valor de config exposto, so o nome do que falta


def test_configuracao_completa_nao_levanta():
    with patch('scripts.outros_documentos_cli.AIRTABLE_API_KEY', 'chave-fake'), \
         patch('scripts.outros_documentos_cli.BASE_ID', 'appXXXX'):
        cli._validar_configuracao()  # nao deve levantar


# ------------------------------------------------------------ auditoria ----

def test_correlation_id_aparece_nos_logs():
    with patch('scripts.outros_documentos_cli.logger') as mock_logger, \
         patch('scripts.outros_documentos_cli._dry_run_outros_documentos_para_envios',
               return_value=_resultado_dry_run('recEnvioA')):
        cli.cmd_dry_run('Junho 2026', 'corr-especifico-123')

    achou = any(
        'corr-especifico-123' in ' '.join(str(a) for a in chamada.args)
        for chamada in mock_logger.info.call_args_list
    )
    assert achou, 'correlation_id nao apareceu em nenhum log'


def test_nenhum_segredo_aparece_nos_logs():
    with patch('scripts.outros_documentos_cli.AIRTABLE_API_KEY', 'CHAVE-SUPER-SECRETA-TESTE'), \
         patch('scripts.outros_documentos_cli.logger') as mock_logger, \
         patch('scripts.outros_documentos_cli.confirmar_campo_arquivos', return_value=True), \
         patch('scripts.outros_documentos_cli._ler_attachments_atuais', return_value=['attA']), \
         patch('scripts.outros_documentos_cli._dry_run_outros_documentos_para_envios',
               return_value=_resultado_dry_run('recEnvioA')), \
         patch('scripts.outros_documentos_cli._aplicar_outros_documentos_no_envio',
               return_value={'envio_id': 'recEnvioA', 'status': 'aplicado',
                              'adicionados': ['novo.pdf'], 'total_apos': 3}):
        cli.cmd_dry_run('Junho 2026', 'corr1')
        cli.cmd_aplicar('Junho 2026', 'recEnvioA', 'corr2', confirmar_input=lambda _: 'CONFIRMAR')

    todas_chamadas = mock_logger.info.call_args_list + mock_logger.error.call_args_list
    for chamada in todas_chamadas:
        texto = ' '.join(str(a) for a in chamada.args)
        assert 'CHAVE-SUPER-SECRETA-TESTE' not in texto


def test_pre_patch_registra_attachment_ids_antes_da_escrita():
    with patch('scripts.outros_documentos_cli.confirmar_campo_arquivos', return_value=True), \
         patch('scripts.outros_documentos_cli._ler_attachments_atuais',
               return_value=['attExistente1', 'attExistente2']) as mock_ler, \
         patch('scripts.outros_documentos_cli.logger') as mock_logger, \
         patch('scripts.outros_documentos_cli._dry_run_outros_documentos_para_envios',
               return_value=_resultado_dry_run('recEnvioA')), \
         patch('scripts.outros_documentos_cli._aplicar_outros_documentos_no_envio',
               return_value={'envio_id': 'recEnvioA', 'status': 'aplicado',
                              'adicionados': ['novo.pdf'], 'total_apos': 3}) as mock_aplicar:
        cli.cmd_aplicar('Junho 2026', 'recEnvioA', 'corr123', confirmar_input=lambda _: 'CONFIRMAR')

    mock_ler.assert_called_once_with('recEnvioA')
    achou_pre_patch = any(
        'pre_patch' in ' '.join(str(a) for a in chamada.args)
        and 'attExistente1' in ' '.join(str(a) for a in chamada.args)
        for chamada in mock_logger.info.call_args_list
    )
    assert achou_pre_patch, 'log pre_patch com os attachment IDs existentes nao encontrado'

    # a leitura pre-patch acontece ANTES da escrita
    assert mock_ler.call_count == 1
    mock_aplicar.assert_called_once()
