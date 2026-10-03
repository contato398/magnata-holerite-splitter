"""AdapterConsultaStatusAssinaturaPacoteLegadoHttp: ponte HTTP read-only
para `/assinatura/consulta?token_reservado=...` (motor legado).
"""
from unittest.mock import Mock, patch

import pytest

from magnata_os.orquestrador.adapters.consulta_status_assinatura_pacote_legado_http import (
    AdapterConsultaStatusAssinaturaPacoteLegadoHttp,
    ConsultaStatusAssinaturaPacoteLegadoError,
)

ADAPTER = AdapterConsultaStatusAssinaturaPacoteLegadoHttp(
    base_url='https://exemplo.invalid', api_key='dummy',
)


def _resp(status=200, corpo=None):
    resposta = Mock()
    resposta.status_code = status
    resposta.json.return_value = corpo or {}
    return resposta


def test_status_atual_consulta_por_token_reservado_na_query():
    with patch(
        'magnata_os.orquestrador.adapters.consulta_status_assinatura_pacote_legado_http.requests.get',
        return_value=_resp(corpo={'existe': True, 'status': 'Reenviar'}),
    ) as get:
        resultado = ADAPTER.status_atual('tok123')

    url, kwargs = get.call_args.args, get.call_args.kwargs
    assert url[0].endswith('/assinatura/consulta')
    assert kwargs['params'] == {'token_reservado': 'tok123'}
    assert kwargs['headers']['X-API-KEY'] == 'dummy'
    assert resultado == 'Reenviar'


def test_status_atual_obrigacao_inexistente_devolve_none():
    with patch(
        'magnata_os.orquestrador.adapters.consulta_status_assinatura_pacote_legado_http.requests.get',
        return_value=_resp(corpo={'existe': False}),
    ):
        assert ADAPTER.status_atual('tok123') is None


def test_status_atual_http_nao_2xx_levanta_erro_dedicado_nunca_none():
    with patch(
        'magnata_os.orquestrador.adapters.consulta_status_assinatura_pacote_legado_http.requests.get',
        return_value=_resp(status=500),
    ):
        with pytest.raises(ConsultaStatusAssinaturaPacoteLegadoError):
            ADAPTER.status_atual('tok123')


def test_status_atual_falha_de_rede_levanta_erro_dedicado_nunca_none():
    import requests

    with patch(
        'magnata_os.orquestrador.adapters.consulta_status_assinatura_pacote_legado_http.requests.get',
        side_effect=requests.ConnectionError('boom'),
    ):
        with pytest.raises(ConsultaStatusAssinaturaPacoteLegadoError):
            ADAPTER.status_atual('tok123')
