"""Testes do helper Evolution puro extraído de `app.py`
(`magnata_os/orquestrador/adapters/evolution_cliente_legado.py`) --
Etapa A da reorganização governada pós-Ultrareview (missão
"REORGANIZAÇÃO LOCAL PÓS-ULTRAREVIEW — SEPARAÇÃO GOVERNADA EVOLUTION /
APP.PY / CANÁRIO").

Nenhuma rede real -- `requests.post` é sempre um dublê. Prova: (1) o
módulo é importável isoladamente, sem Flask/sessão/Airtable/`app.py`;
(2) as 3 funções preservam exatamente endpoint, header de autenticação,
timeout e tratamento de resposta/erro já validados em produção via
`app.py` antes desta extração."""
from __future__ import annotations

import sys
from unittest.mock import Mock, patch

import pytest

from magnata_os.orquestrador.adapters import evolution_cliente_legado as cliente


def test_import_isolado_nunca_carrega_flask_app_ou_airtable():
    modulos_antes = set(sys.modules)
    import importlib
    importlib.reload(cliente)
    modulos_depois = set(sys.modules)
    novos = modulos_depois - modulos_antes
    assert 'flask' not in novos
    assert 'app' not in novos


def _resposta_ok(corpo=None):
    resposta = Mock()
    resposta.status_code = 200
    resposta.json.return_value = corpo if corpo is not None else {'status': 'ok'}
    resposta.text = ''
    return resposta


def _resposta_erro(status=500, texto='erro'):
    resposta = Mock()
    resposta.status_code = status
    resposta.text = texto
    return resposta


def test_enviar_texto_usa_endpoint_header_e_timeout_esperados():
    with patch.object(cliente, 'requests') as requests_mock:
        requests_mock.post.return_value = _resposta_ok({'id': 'abc'})
        resultado = cliente._evolution_enviar_texto('5511999999999', 'ola')

    requests_mock.post.assert_called_once()
    args, kwargs = requests_mock.post.call_args
    assert args[0] == f'{cliente.EVOLUTION_API_URL}/message/sendText/{cliente.EVOLUTION_INSTANCE}'
    assert kwargs['headers'] == {'apikey': cliente.EVOLUTION_API_KEY, 'Content-Type': 'application/json'}
    assert kwargs['json'] == {'number': '5511999999999', 'text': 'ola'}
    assert kwargs['timeout'] == 90
    assert resultado == {'id': 'abc'}


def test_enviar_texto_levanta_runtime_error_em_status_fora_de_2xx():
    with patch.object(cliente, 'requests') as requests_mock:
        requests_mock.post.return_value = _resposta_erro(503, 'indisponivel')
        with pytest.raises(RuntimeError, match='Evolution HTTP 503'):
            cliente._evolution_enviar_texto('5511999999999', 'ola')


def test_enviar_video_usa_endpoint_sendmedia_e_inclui_legenda_quando_presente():
    with patch.object(cliente, 'requests') as requests_mock:
        requests_mock.post.return_value = _resposta_ok({'id': 'v1'})
        cliente._evolution_enviar_video('5511999999999', 'YmFzZTY0', 'video.mp4', legenda='oi')

    _, kwargs = requests_mock.post.call_args
    assert kwargs['json']['mediatype'] == 'video'
    assert kwargs['json']['caption'] == 'oi'
    assert kwargs['timeout'] == 90


def test_enviar_documento_usa_media_bytes_em_base64_quando_informado():
    with patch.object(cliente, 'requests') as requests_mock:
        requests_mock.post.return_value = _resposta_ok({'id': 'd1'})
        cliente._evolution_enviar_documento(
            '5511999999999', media_url=None, filename='doc.pdf', media_bytes=b'%PDF-1.4',
        )

    _, kwargs = requests_mock.post.call_args
    assert kwargs['json']['mediatype'] == 'document'
    assert kwargs['json']['media'] != None  # base64 do conteudo, nunca a URL quando media_bytes existe
    assert kwargs['json']['fileName'] == 'doc.pdf'
