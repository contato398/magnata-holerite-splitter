"""Matriz conservadora de falhas do adapter Evolution.

Cobre, para cada caso real da missão, a classificação exigida: só falhas
comprovadamente anteriores a qualquer transmissão são elegíveis a retry
(FalhaTransitoria); qualquer incerteza vira FalhaEnvioIncerto.
"""
import json

import pytest
import requests
import requests.exceptions
import urllib3.exceptions

from magnata_os.orquestrador.classificador_falha import FalhaEnvioIncerto, FalhaTransitoria
from magnata_os.orquestrador.adapters.transporte_evolution_legado import (
    TransporteEvolutionLegado,
)


def _adapter(enviar_texto=None, enviar_video=None, enviar_documento=None):
    return TransporteEvolutionLegado(
        enviar_texto_legado=enviar_texto or (lambda *a, **k: {'status': 'ok'}),
        enviar_video_legado=enviar_video or (lambda *a, **k: {'status': 'ok'}),
        enviar_documento_legado=enviar_documento or (lambda *a, **k: {'status': 'ok'}),
    )


def _levanta(exc):
    def _fn(*a, **k):
        raise exc
    return _fn


# ---- casos seguros para retry (TRANSIENT_SEGURO) ----------------------

def test_connect_timeout_e_transiente_seguro():
    adapter = _adapter(enviar_texto=_levanta(requests.exceptions.ConnectTimeout('x')))
    with pytest.raises(FalhaTransitoria):
        adapter.enviar_texto(numero='5511999999999', texto='oi')


def test_conexao_recusada_antes_de_conectar_e_transiente_seguro():
    causa = urllib3.exceptions.NewConnectionError(None, 'Connection refused')
    adapter = _adapter(enviar_texto=_levanta(requests.exceptions.ConnectionError(causa)))
    with pytest.raises(FalhaTransitoria):
        adapter.enviar_texto(numero='5511999999999', texto='oi')


def test_dns_inacessivel_antes_de_conectar_e_transiente_seguro():
    causa = urllib3.exceptions.NewConnectionError(None, 'Name or service not known')
    adapter = _adapter(enviar_texto=_levanta(requests.exceptions.ConnectionError(causa)))
    with pytest.raises(FalhaTransitoria):
        adapter.enviar_texto(numero='5511999999999', texto='oi')


# ---- casos incertos (ENVIO_EXTERNO_INCERTO) ----------------------------

def test_read_timeout_e_envio_externo_incerto():
    adapter = _adapter(enviar_texto=_levanta(requests.exceptions.ReadTimeout('x')))
    with pytest.raises(FalhaEnvioIncerto):
        adapter.enviar_texto(numero='5511999999999', texto='oi')


def test_reset_pos_conexao_sem_prova_e_envio_externo_incerto():
    # ConnectionError cuja causa NÃO é NewConnectionError -- biblioteca não
    # prova se o reset ocorreu antes ou depois do corpo ser transmitido.
    adapter = _adapter(enviar_texto=_levanta(
        requests.exceptions.ConnectionError(ConnectionResetError('reset'))
    ))
    with pytest.raises(FalhaEnvioIncerto):
        adapter.enviar_texto(numero='5511999999999', texto='oi')


def test_http_5xx_e_envio_externo_incerto():
    adapter = _adapter(enviar_texto=_levanta(RuntimeError('Evolution HTTP 502: bad gateway')))
    with pytest.raises(FalhaEnvioIncerto):
        adapter.enviar_texto(numero='5511999999999', texto='oi')


def test_json_invalido_apos_2xx_e_envio_externo_incerto():
    resposta = requests.Response()
    resposta.status_code = 200
    resposta._content = b'nao e json'
    adapter = _adapter(enviar_texto=_levanta(
        requests.exceptions.JSONDecodeError('msg', 'nao e json', 0)
    ))
    with pytest.raises(FalhaEnvioIncerto):
        adapter.enviar_texto(numero='5511999999999', texto='oi')


def test_excecao_pos_body_nao_mapeada_e_envio_externo_incerto():
    adapter = _adapter(enviar_texto=_levanta(OSError('erro de socket inesperado pos-envio')))
    with pytest.raises(FalhaEnvioIncerto):
        adapter.enviar_texto(numero='5511999999999', texto='oi')


# ---- falha permanente (não retry, mas não por prova de não-envio) -----

def test_http_4xx_e_permanent_nao_transiente():
    adapter = _adapter(enviar_texto=_levanta(RuntimeError('Evolution HTTP 400: payload invalido')))
    with pytest.raises(ValueError):
        adapter.enviar_texto(numero='5511999999999', texto='oi')


# ---- sucesso (2xx com e sem ID) ----------------------------------------

def test_sucesso_com_id_externo_repassa_resultado():
    adapter = _adapter(enviar_texto=lambda *a, **k: {'key': {'id': 'ABC123'}})
    resultado = adapter.enviar_texto(numero='5511999999999', texto='oi')
    assert resultado['key']['id'] == 'ABC123'


def test_sucesso_sem_id_externo_nao_levanta_excecao():
    adapter = _adapter(enviar_texto=lambda *a, **k: {'status': 'ok'})
    resultado = adapter.enviar_texto(numero='5511999999999', texto='oi')
    assert resultado == {'status': 'ok'}


# ---- vídeo/documento: reuso do mesmo cliente legado, sem duplicar payload

def test_enviar_video_base64_encoda_conteudo_binario_antes_de_chamar_legado():
    capturado = {}

    def _fake_enviar_video(numero, video_base64, nome_arquivo, legenda=''):
        capturado['video_base64'] = video_base64
        capturado['legenda'] = legenda
        return {'key': {'id': 'V1'}}

    adapter = _adapter(enviar_video=_fake_enviar_video)
    resultado = adapter.enviar_video(
        numero='5511999999999', conteudo=b'dados-binarios',
        nome_arquivo='video.mp4', legenda='oi',
    )
    import base64
    assert capturado['video_base64'] == base64.b64encode(b'dados-binarios').decode('ascii')
    assert capturado['legenda'] == 'oi'
    assert resultado['key']['id'] == 'V1'


def test_enviar_documento_repassa_bytes_diretamente_sem_url():
    capturado = {}

    def _fake_enviar_documento(numero, media_url, filename, caption=None, media_bytes=None):
        capturado['media_url'] = media_url
        capturado['media_bytes'] = media_bytes
        capturado['caption'] = caption
        return {'key': {'id': 'D1'}}

    adapter = _adapter(enviar_documento=_fake_enviar_documento)
    adapter.enviar_documento(
        numero='5511999999999', conteudo=b'%PDF-1.4 fake', nome_arquivo='doc.pdf', legenda='',
    )
    assert capturado['media_url'] is None
    assert capturado['media_bytes'] == b'%PDF-1.4 fake'
    assert capturado['caption'] is None
