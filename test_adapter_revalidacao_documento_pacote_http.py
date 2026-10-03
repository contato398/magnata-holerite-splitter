"""AdapterRevalidacaoDocumentoPacoteHttp: download HTTP + SHA-256 dos
anexos originais de um pacote, sem credencial de Airtable (a URL do
anexo já é a forma pronta de acesso)."""
import hashlib
from unittest.mock import Mock, patch

import pytest

from magnata_os.orquestrador.adapters.revalidacao_documento_pacote_http import (
    AdapterRevalidacaoDocumentoPacoteHttp,
    RevalidacaoDocumentoPacoteError,
)

ADAPTER = AdapterRevalidacaoDocumentoPacoteHttp()


def _resp(ok=True, status=200, content=b''):
    resposta = Mock()
    resposta.ok = ok
    resposta.status_code = status
    resposta.content = content
    return resposta


def test_hashes_atuais_calcula_sha256_de_cada_url():
    conteudo_a, conteudo_b = b'conteudo-a', b'conteudo-b'
    with patch(
        'magnata_os.orquestrador.adapters.revalidacao_documento_pacote_http.requests.get',
        side_effect=[_resp(content=conteudo_a), _resp(content=conteudo_b)],
    ):
        resultado = ADAPTER.hashes_atuais(('https://x/a', 'https://x/b'))

    assert resultado == frozenset({
        hashlib.sha256(conteudo_a).hexdigest(),
        hashlib.sha256(conteudo_b).hexdigest(),
    })


def test_hashes_atuais_http_nao_ok_levanta_erro_dedicado():
    with patch(
        'magnata_os.orquestrador.adapters.revalidacao_documento_pacote_http.requests.get',
        return_value=_resp(ok=False, status=404),
    ):
        with pytest.raises(RevalidacaoDocumentoPacoteError):
            ADAPTER.hashes_atuais(('https://x/a',))


def test_hashes_atuais_falha_de_rede_levanta_erro_dedicado():
    import requests

    with patch(
        'magnata_os.orquestrador.adapters.revalidacao_documento_pacote_http.requests.get',
        side_effect=requests.ConnectionError('boom'),
    ):
        with pytest.raises(RevalidacaoDocumentoPacoteError):
            ADAPTER.hashes_atuais(('https://x/a',))


def test_hashes_atuais_sem_urls_devolve_conjunto_vazio():
    assert ADAPTER.hashes_atuais(()) == frozenset()
