import app as modulo


def _set_keys(valor_global, valor_assinatura):
    setattr(modulo, 'AIRTABLE_' + 'API_KEY', valor_global)
    setattr(modulo, 'AIRTABLE_ASSINATURA_' + 'API_KEY', valor_assinatura)


def test_assinatura_prefere_credencial_dedicada():
    _set_keys('test', 'test')
    with modulo.app.test_request_context('/assinatura/gerar', method='POST'):
        assert modulo._airtable_api_key_atual() == 'test'


def test_pagina_publica_assinatura_usa_credencial_dedicada():
    _set_keys('test', 'test')
    with modulo.app.test_request_context('/assinatura/token-exemplo'):
        assert modulo._airtable_api_key_atual() == 'test'


def test_fluxo_nao_assinatura_preserva_global():
    _set_keys('test', 'sample')
    with modulo.app.test_request_context('/whatsapp/enviar-texto', method='POST'):
        assert modulo._airtable_api_key_atual() == 'test'


def test_assinatura_sem_dedicada_faz_fallback_global():
    _set_keys('test', '')
    with modulo.app.test_request_context('/assinatura/gerar', method='POST'):
        assert modulo._airtable_api_key_atual() == 'test'


def test_fora_de_request_preserva_global():
    _set_keys('test', 'sample')
    assert modulo._airtable_api_key_atual() == 'test'
