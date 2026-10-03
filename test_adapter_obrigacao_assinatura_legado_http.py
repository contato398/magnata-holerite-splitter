"""AdapterObrigacaoAssinaturaLegadoHttp: ponte HTTP para o motor legado.

Garante: `criar_ou_recuperar` chama /assinatura/gerar com
disparar_whatsapp=false; `consultar_por_correlacao` NUNCA chama
/assinatura/gerar, só GET /assinatura/consulta -- read-only de verdade.
"""
from unittest.mock import Mock, patch

import pytest

from magnata_os.orquestrador.adapters.obrigacao_assinatura_legado_http import (
    AdapterObrigacaoAssinaturaLegadoHttp,
    ObrigacaoAssinaturaLegadoError,
    QuantidadeArquivosNaoSuportadaPeloLegado,
)
from magnata_os.orquestrador.obrigacao_assinatura import ObrigacaoAssinatura

ADAPTER = AdapterObrigacaoAssinaturaLegadoHttp(
    base_url='https://exemplo.invalid', api_key='dummy',
)


def _resp(status=200, corpo=None):
    resposta = Mock()
    resposta.status_code = status
    resposta.json.return_value = corpo or {}
    return resposta


def test_criar_ou_recuperar_chama_gerar_com_disparar_whatsapp_false():
    with patch('magnata_os.orquestrador.adapters.obrigacao_assinatura_legado_http.requests.post',
               return_value=_resp(corpo={'assinatura_id': 'rec1', 'link': 'https://x/assinatura/tok'})) as post:
        resultado = ADAPTER.criar_ou_recuperar(
            token_reservado='tok', acao_execucao_id='a' * 64,
            funcionario_id='rec1', tipo_documento='COMUNICADO', arquivo_record_ids=('recArq',),
        )
    url, kwargs = post.call_args.args, post.call_args.kwargs
    assert url[0].endswith('/assinatura/gerar')
    assert kwargs['json']['disparar_whatsapp'] is False
    assert kwargs['json']['token_reservado'] == 'tok'
    assert kwargs['json']['acao_execucao_id'] == 'a' * 64
    assert kwargs['json']['arquivo_record_id'] == 'recArq'
    assert isinstance(resultado, ObrigacaoAssinatura)
    assert resultado.assinatura_id == 'rec1'


def test_criar_ou_recuperar_devolve_o_proprio_token_reservado_sem_inferir_do_link():
    """O chamador escolheu `token_reservado`; `criar_ou_recuperar` garante
    (ou falha) que é esse o token persistido -- o adapter nunca precisa
    reler o corpo da resposta para saber o token de volta."""
    with patch('magnata_os.orquestrador.adapters.obrigacao_assinatura_legado_http.requests.post',
               return_value=_resp(corpo={'assinatura_id': 'rec1', 'link': 'https://x/assinatura/tok-diferente'})):
        resultado = ADAPTER.criar_ou_recuperar(
            token_reservado='tok-original', acao_execucao_id='a' * 64,
            funcionario_id='rec1', tipo_documento='COMUNICADO', arquivo_record_ids=('recArq',),
        )
    assert resultado.token == 'tok-original'


def test_criar_ou_recuperar_com_2_arquivos_usa_payload_do_pacote_holerite_ponto():
    with patch('magnata_os.orquestrador.adapters.obrigacao_assinatura_legado_http.requests.post',
               return_value=_resp(corpo={'assinatura_id': 'rec1', 'link': 'https://x/assinatura/tok'})) as post:
        ADAPTER.criar_ou_recuperar(
            token_reservado='tok', acao_execucao_id='a' * 64,
            funcionario_id='rec1', tipo_documento='HOLERITE_FOLHA_PONTO',
            arquivo_record_ids=('recHolerite', 'recPonto'),
        )
    kwargs = post.call_args.kwargs
    assert kwargs['json']['arquivo_holerite_record_id'] == 'recHolerite'
    assert kwargs['json']['arquivo_folha_ponto_record_id'] == 'recPonto'
    assert 'arquivo_record_id' not in kwargs['json']


def test_criar_ou_recuperar_com_2_arquivos_fora_do_pacote_holerite_ponto_falha():
    with pytest.raises(QuantidadeArquivosNaoSuportadaPeloLegado):
        ADAPTER.criar_ou_recuperar(
            token_reservado='tok', acao_execucao_id='a' * 64,
            funcionario_id='rec1', tipo_documento='EPI',
            arquivo_record_ids=('rec1', 'rec2'),
        )


def test_criar_ou_recuperar_com_3_arquivos_falha_sempre():
    with pytest.raises(QuantidadeArquivosNaoSuportadaPeloLegado):
        ADAPTER.criar_ou_recuperar(
            token_reservado='tok', acao_execucao_id='a' * 64,
            funcionario_id='rec1', tipo_documento='HOLERITE_FOLHA_PONTO',
            arquivo_record_ids=('rec1', 'rec2', 'rec3'),
        )


def test_criar_ou_recuperar_propaga_erro_de_rede_como_excecao_dedicada():
    import requests
    with patch('magnata_os.orquestrador.adapters.obrigacao_assinatura_legado_http.requests.post',
               side_effect=requests.exceptions.ConnectionError('boom')):
        with pytest.raises(ObrigacaoAssinaturaLegadoError):
            ADAPTER.criar_ou_recuperar(
                token_reservado='tok', acao_execucao_id='a' * 64,
                funcionario_id='rec1', tipo_documento='COMUNICADO', arquivo_record_ids=('recArq',),
            )


def test_criar_ou_recuperar_falha_em_status_nao_2xx():
    with patch('magnata_os.orquestrador.adapters.obrigacao_assinatura_legado_http.requests.post',
               return_value=_resp(status=409, corpo={'erro': 'conflito'})):
        with pytest.raises(ObrigacaoAssinaturaLegadoError):
            ADAPTER.criar_ou_recuperar(
                token_reservado='tok', acao_execucao_id='a' * 64,
                funcionario_id='rec1', tipo_documento='COMUNICADO', arquivo_record_ids=('recArq',),
            )


def test_consultar_por_correlacao_nunca_chama_gerar():
    with patch('magnata_os.orquestrador.adapters.obrigacao_assinatura_legado_http.requests.post') as post, \
         patch('magnata_os.orquestrador.adapters.obrigacao_assinatura_legado_http.requests.get',
               return_value=_resp(corpo={'existe': False})) as get:
        ADAPTER.consultar_por_correlacao(acao_execucao_id='a' * 64)
    post.assert_not_called()
    assert get.call_args.args[0].endswith('/assinatura/consulta')
    assert get.call_args.kwargs['params'] == {'acao_execucao_id': 'a' * 64}


def test_consultar_por_correlacao_inexistente_retorna_none():
    with patch('magnata_os.orquestrador.adapters.obrigacao_assinatura_legado_http.requests.get',
               return_value=_resp(corpo={'existe': False})):
        resultado = ADAPTER.consultar_por_correlacao(acao_execucao_id='a' * 64)
    assert resultado is None


def test_consultar_por_correlacao_existente_mapeia_campos():
    corpo = {
        'existe': True, 'status': 'Assinado', 'assinatura_id': 'rec1',
        'link': 'https://x/assinatura/tok', 'comprovante_existe': True,
        'evidencia_hash': 'attCOMPROVANTE',
    }
    with patch('magnata_os.orquestrador.adapters.obrigacao_assinatura_legado_http.requests.get',
               return_value=_resp(corpo=corpo)):
        resultado = ADAPTER.consultar_por_correlacao(acao_execucao_id='a' * 64)
    assert resultado == ObrigacaoAssinatura(
        assinatura_id='rec1', link='https://x/assinatura/tok', status='Assinado',
        tem_comprovante=True, evidencia_opaca='attCOMPROVANTE',
    )
    assert resultado.token is None  # motor legado ainda não expõe `hash_token` nesta rota


def test_consultar_por_correlacao_mapeia_hash_token_quando_o_legado_ja_expoe():
    """Compatibilidade futura: quando `pacote-autorizacao-app-py.md` #1
    for aplicado em `app.py`, `/assinatura/consulta` passa a devolver
    `hash_token` -- o adapter já sabe repassá-lo, sem exigir nova
    mudança neste arquivo."""
    corpo = {
        'existe': True, 'status': 'Pendente', 'assinatura_id': 'rec1',
        'link': 'https://x/assinatura/tok-real', 'comprovante_existe': False,
        'evidencia_hash': None, 'hash_token': 'tok-real',
    }
    with patch('magnata_os.orquestrador.adapters.obrigacao_assinatura_legado_http.requests.get',
               return_value=_resp(corpo=corpo)):
        resultado = ADAPTER.consultar_por_correlacao(acao_execucao_id='a' * 64)
    assert resultado.token == 'tok-real'
