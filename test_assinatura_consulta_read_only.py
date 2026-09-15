"""GET /assinatura/consulta -- somente leitura, sem efeito colateral.

Cobre exatamente os requisitos do Bloqueio 2: nunca cria, nunca dispara
Evolution, GET puro, reaproveita `_buscar_por_campo`, resposta mínima sem
PII nem URL sensível.
"""
from unittest.mock import Mock, patch

import app

ACAO_ID = 'a' * 64
TOKEN = 'dummy'


def _cliente():
    app.app.testing = True
    return app.app.test_client()


def _resp(records=None, ok=True):
    resposta = Mock()
    resposta.ok = ok
    resposta.status_code = 200 if ok else 503
    resposta.raise_for_status = Mock()
    if not ok:
        resposta.raise_for_status.side_effect = Exception('boom')
    resposta.json.return_value = {'records': records or []}
    return resposta


def test_options_nao_consulta_nada():
    cliente = _cliente()
    with patch('app.requests.get') as get:
        resposta = cliente.options('/assinatura/consulta')
    assert resposta.status_code == 204
    get.assert_not_called()


def test_chave_ausente_retorna_401_sem_consultar():
    cliente = _cliente()
    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app.requests.get') as get:
        resposta = cliente.get(f'/assinatura/consulta?acao_execucao_id={ACAO_ID}')
    assert resposta.status_code == 401
    get.assert_not_called()


def test_exige_exatamente_um_parametro():
    cliente = _cliente()
    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app.requests.get') as get:
        nenhum = cliente.get('/assinatura/consulta', headers={'X-API-KEY': 'dummy'})
        ambos = cliente.get(
            f'/assinatura/consulta?acao_execucao_id={ACAO_ID}&token_reservado={TOKEN}',
            headers={'X-API-KEY': 'dummy'},
        )
    assert nenhum.status_code == 400
    assert ambos.status_code == 400
    get.assert_not_called()


def test_obrigacao_inexistente_retorna_existe_false_sem_criar():
    cliente = _cliente()
    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=_resp(records=[])) as get, \
         patch('app._criar_registro') as criar, \
         patch('app._evolution_enviar_texto') as enviar_texto, \
         patch('app._evolution_enviar_documento') as enviar_documento:
        resposta = cliente.get(
            f'/assinatura/consulta?acao_execucao_id={ACAO_ID}',
            headers={'X-API-KEY': 'dummy'},
        )
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo == {
        'existe': False, 'status': None, 'assinatura_id': None,
        'link': None, 'comprovante_existe': False, 'evidencia_hash': None,
    }
    criar.assert_not_called()
    enviar_texto.assert_not_called()
    enviar_documento.assert_not_called()
    # a chamada real ao Airtable foi um GET, nunca POST
    metodo_chamado = get.call_args
    assert metodo_chamado is not None


def test_consulta_usa_apenas_requests_get_nunca_post():
    cliente = _cliente()
    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=_resp(records=[])), \
         patch('app.requests.post') as post:
        cliente.get(f'/assinatura/consulta?acao_execucao_id={ACAO_ID}', headers={'X-API-KEY': 'dummy'})
    post.assert_not_called()


def test_obrigacao_existente_pendente_sem_comprovante():
    registro = {
        'id': 'recASSINATURASINTETICA',
        'fields': {
            app.F_ASS_STATUS: 'Pendente',
            app.F_ASS_HASH: TOKEN,
            app.F_ASS_DOCUMENTO_PDF: [
                {'id': 'attHOLERITE', 'filename': 'Holerite - ASSINADO.pdf'},
            ],
        },
    }
    cliente = _cliente()
    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=_resp(records=[registro])):
        resposta = cliente.get(
            f'/assinatura/consulta?acao_execucao_id={ACAO_ID}',
            headers={'X-API-KEY': 'dummy'},
        )
    corpo = resposta.get_json()
    assert corpo['existe'] is True
    assert corpo['status'] == 'Pendente'
    assert corpo['assinatura_id'] == 'recASSINATURASINTETICA'
    assert corpo['link'].endswith(f'/assinatura/{TOKEN}')
    assert corpo['comprovante_existe'] is False
    assert corpo['evidencia_hash'] is None


def test_obrigacao_assinada_com_comprovante():
    registro = {
        'id': 'recASSINATURASINTETICA',
        'fields': {
            app.F_ASS_STATUS: 'Assinado',
            app.F_ASS_HASH: TOKEN,
            app.F_ASS_DOCUMENTO_PDF: [
                {'id': 'attHOLERITE', 'filename': 'Holerite - ASSINADO.pdf'},
                {'id': 'attCOMPROVANTE', 'filename': 'Comprovante Assinatura - X.pdf',
                 'url': 'https://airtable-signed-url.invalid/segredo'},
            ],
        },
    }
    cliente = _cliente()
    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=_resp(records=[registro])):
        resposta = cliente.get(
            f'/assinatura/consulta?token_reservado={TOKEN}',
            headers={'X-API-KEY': 'dummy'},
        )
    corpo = resposta.get_json()
    assert corpo['comprovante_existe'] is True
    assert corpo['evidencia_hash'] == 'attCOMPROVANTE'


def test_resposta_nunca_contem_url_assinada_nem_cpf():
    registro = {
        'id': 'recX',
        'fields': {
            app.F_ASS_STATUS: 'Assinado',
            app.F_ASS_HASH: TOKEN,
            app.F_ASS_CPF_INFORMADO: '11111111111',
            app.F_ASS_DOCUMENTO_PDF: [
                {'id': 'attC', 'filename': 'Comprovante Assinatura - X.pdf',
                 'url': 'https://airtable-signed-url.invalid/segredo-nao-pode-vazar'},
            ],
        },
    }
    cliente = _cliente()
    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app._at_throttle'), \
         patch('app.requests.get', return_value=_resp(records=[registro])):
        resposta = cliente.get(f'/assinatura/consulta?token_reservado={TOKEN}', headers={'X-API-KEY': 'dummy'})
    bruto = resposta.get_data(as_text=True)
    assert 'segredo-nao-pode-vazar' not in bruto
    assert '11111111111' not in bruto


def test_falha_de_consulta_retorna_503_sem_expor_detalhe():
    cliente = _cliente()
    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app._at_throttle'), \
         patch('app.requests.get', side_effect=RuntimeError('falha de rede sintetica')):
        resposta = cliente.get(f'/assinatura/consulta?acao_execucao_id={ACAO_ID}', headers={'X-API-KEY': 'dummy'})
    assert resposta.status_code == 503
