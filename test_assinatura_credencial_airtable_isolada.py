import app as modulo


def _set_keys(global_key, assinatura_key):
    modulo.AIRTABLE_API_KEY = global_key
    modulo.AIRTABLE_ASSINATURA_API_KEY = assinatura_key


def test_assinatura_prefere_credencial_dedicada():
    _set_keys("global-test", "assinatura-test")
    with modulo.app.test_request_context("/assinatura/gerar", method="POST"):
        assert modulo._airtable_api_key_atual() == "assinatura-test"


def test_pagina_publica_assinatura_usa_credencial_dedicada():
    _set_keys("global-test", "assinatura-test")
    with modulo.app.test_request_context("/assinatura/token-exemplo"):
        assert modulo._airtable_api_key_atual() == "assinatura-test"


def test_fluxo_nao_assinatura_preserva_global():
    _set_keys("global-test", "assinatura-test")
    with modulo.app.test_request_context("/whatsapp/enviar-texto", method="POST"):
        assert modulo._airtable_api_key_atual() == "global-test"


def test_assinatura_sem_dedicada_faz_fallback_global():
    _set_keys("global-test", "")
    with modulo.app.test_request_context("/assinatura/gerar", method="POST"):
        assert modulo._airtable_api_key_atual() == "global-test"


def test_fora_de_request_preserva_global():
    _set_keys("global-test", "assinatura-test")
    assert modulo._airtable_api_key_atual() == "global-test"
