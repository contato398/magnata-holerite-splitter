"""Token/link reservado para o motor legado de assinatura.

Todos os dados são sintéticos e toda fronteira externa é substituída por fake.
"""
import base64
import hashlib
from unittest.mock import Mock, patch

import app


TOKEN = base64.urlsafe_b64encode(bytes(range(32))).rstrip(b'=').decode('ascii')
OUTRO_TOKEN = base64.urlsafe_b64encode(bytes(range(32, 64))).rstrip(b'=').decode('ascii')
TOKEN_PREVISIVEL = base64.urlsafe_b64encode(bytes(32)).rstrip(b'=').decode('ascii')
ACAO_ID = 'a' * 64
OUTRA_ACAO_ID = 'b' * 64
FUNC_ID = 'recFUNCIONARIOSINTETICO'
ARQUIVO_ID = 'recARQUIVOSINTETICO'
PDF = b'%PDF-1.4\nconteudo sintetico assinatura reservada'


def _resp(records=None, fields=None, ok=True):
    resposta = Mock()
    resposta.ok = ok
    resposta.status_code = 200 if ok else 503
    if fields is not None:
        resposta.json.return_value = {'fields': fields}
    else:
        resposta.json.return_value = {'records': records or []}
    return resposta


def _arquivo():
    return _resp(fields={
        app.F_ARQ_ATTACH: [{
            'url': 'https://example.invalid/documento.pdf',
            'filename': 'documento-sintetico.pdf',
        }],
        'fldxbZwVNa01pchqF': [FUNC_ID],
    })


def _existente(token=TOKEN, acao_id=ACAO_ID, status='PREPARADO'):
    return {
        'id': 'recASSINATURASINTETICA',
        'fields': {
            app.F_ASS_HASH: token,
            app.F_ASS_REQUEST_ID: acao_id,
            app.F_ASS_STATUS: status,
        },
    }


def _chamar_core(*, token=TOKEN, acao_id=ACAO_ID, gets=None, disparar=False):
    respostas = gets or [_arquivo(), _resp(), _resp()]
    with patch('app._validar_configuracao_assinatura_v36', return_value=(True, 'ok')), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('PESSOA SINTETICA', '5511000000000')), \
         patch('app._carregar_documento_url', return_value=PDF), \
         patch('app._at_throttle'), \
         patch('app.requests.get', side_effect=respostas), \
         patch('app._criar_registro', return_value='recASSINATURANOVA') as criar, \
         patch('app._anexar_attachment'), \
         patch('app._evolution_enviar_texto') as enviar_texto, \
         patch('app._evolution_enviar_documento') as enviar_documento:
        resultado = app._gerar_assinatura_core(
            funcionario_id=FUNC_ID,
            tipo_documento='COMUNICADO',
            arquivo_record_id=ARQUIVO_ID,
            token_reservado=token,
            acao_execucao_id=acao_id,
            disparar_whatsapp=disparar,
        )
    return resultado, criar, enviar_texto, enviar_documento


def test_validador_aceita_reserva_criptografica_canonica():
    assert app._validar_reserva_assinatura(TOKEN, ACAO_ID) is None


def test_validador_preserva_chamada_legada_sem_parametros():
    assert app._validar_reserva_assinatura() is None


def test_validador_exige_token_e_correlacao_juntos():
    assert 'juntos' in app._validar_reserva_assinatura(TOKEN, None)
    assert 'juntos' in app._validar_reserva_assinatura(None, ACAO_ID)


def test_validador_rejeita_token_vazio_curto_malformado_ou_previsivel():
    invalidos = ['', 'curto', '!' * 43, TOKEN + 'A', TOKEN_PREVISIVEL]
    assert all(app._validar_reserva_assinatura(valor, ACAO_ID) for valor in invalidos)


def test_validador_rejeita_correlacao_que_nao_seja_sha256_opaco():
    assert 'acao_execucao_id inválido' in app._validar_reserva_assinatura(TOKEN, 'acao-humana-1')


def test_reserva_cria_obrigacao_com_mesmo_token_e_correlacao_sem_whatsapp():
    (resultado, status), criar, enviar_texto, enviar_documento = _chamar_core()
    assert status == 200
    assert resultado['hash_token'] == TOKEN
    assert resultado['link'].endswith('/assinatura/' + TOKEN)
    campos = criar.call_args.args[1]
    assert campos[app.F_ASS_HASH] == TOKEN
    assert campos[app.F_ASS_REQUEST_ID] == ACAO_ID
    enviar_texto.assert_not_called()
    enviar_documento.assert_not_called()


def test_retry_mesma_identidade_token_e_correlacao_retorna_mesma_obrigacao():
    (resultado, status), criar, enviar_texto, enviar_documento = _chamar_core(
        gets=[_arquivo(), _resp(records=[_existente()])],
    )
    assert status == 200
    assert resultado['assinatura_id'] == 'recASSINATURASINTETICA'
    assert resultado['link'].endswith('/assinatura/' + TOKEN)
    assert resultado['motivo'] == 'retornando_obrigacao_reservada_existente'
    criar.assert_not_called()
    enviar_texto.assert_not_called()
    enviar_documento.assert_not_called()


def test_mesma_obrigacao_com_token_diferente_falha_explicitamente():
    (resultado, status), criar, _, _ = _chamar_core(
        token=OUTRO_TOKEN,
        gets=[_arquivo(), _resp(records=[_existente()])],
    )
    assert status == 409
    assert resultado['erro'] == 'conflito_token_mesma_obrigacao'
    criar.assert_not_called()


def test_mesma_obrigacao_com_correlacao_diferente_falha_explicitamente():
    (resultado, status), criar, _, _ = _chamar_core(
        acao_id=OUTRA_ACAO_ID,
        gets=[_arquivo(), _resp(records=[_existente()])],
    )
    assert status == 409
    assert resultado['erro'] == 'conflito_correlacao_mesma_obrigacao'
    criar.assert_not_called()


def test_token_ja_usado_por_outra_obrigacao_falha_explicitamente():
    (resultado, status), criar, _, _ = _chamar_core(
        gets=[_arquivo(), _resp(), _resp(records=[_existente(acao_id=OUTRA_ACAO_ID)])],
    )
    assert status == 409
    assert resultado['erro'] == 'token_reservado_ja_utilizado'
    criar.assert_not_called()


def test_documento_divergente_nao_pode_reutilizar_token_existente():
    # A identidade calculada com o PDF atual não existe, mas o token já está
    # ligado a outra identidade documental: falha fechada antes da criação.
    (resultado, status), criar, _, _ = _chamar_core(
        gets=[_arquivo(), _resp(), _resp(records=[_existente()])],
    )
    assert status == 409
    assert resultado['erro'] == 'token_reservado_ja_utilizado'
    criar.assert_not_called()


def test_assinatura_ja_existente_retorna_mesma_obrigacao_sem_recriar():
    (resultado, status), criar, _, _ = _chamar_core(
        gets=[_arquivo(), _resp(records=[_existente(status='Assinado')])],
    )
    assert status == 200
    assert resultado['assinatura_id'] == 'recASSINATURASINTETICA'
    criar.assert_not_called()


def test_reserva_falha_fechada_se_consulta_de_unicidade_falhar():
    (resultado, status), criar, _, _ = _chamar_core(
        gets=[_arquivo(), _resp(), _resp(ok=False)],
    )
    assert status == 503
    assert resultado['erro'] == 'falha_verificacao_token_reservado'
    criar.assert_not_called()


def test_reserva_falha_fechada_se_consulta_da_identidade_falhar():
    (resultado, status), criar, _, _ = _chamar_core(
        gets=[_arquivo(), RuntimeError('falha sintética')],
    )
    assert status == 503
    assert resultado['erro'] == 'falha_verificacao_obrigacao_reservada'
    criar.assert_not_called()


def test_reserva_falha_fechada_se_identidade_retornar_http_nao_ok():
    (resultado, status), criar, _, _ = _chamar_core(
        gets=[_arquivo(), _resp(ok=False)],
    )
    assert status == 503
    assert resultado['erro'] == 'falha_verificacao_obrigacao_reservada'
    criar.assert_not_called()


def test_reserva_nunca_admite_disparo_whatsapp():
    (resultado, status), criar, enviar_texto, enviar_documento = _chamar_core(disparar=True, gets=[])
    assert status == 400
    assert resultado['erro'] == 'token_reservado exige disparar_whatsapp=false'
    criar.assert_not_called()
    enviar_texto.assert_not_called()
    enviar_documento.assert_not_called()


def test_chamada_legada_continua_gerando_token_interno():
    token_legado = 'dummy'
    with patch('app._validar_configuracao_assinatura_v36', return_value=(True, 'ok')), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('PESSOA SINTETICA', None)), \
         patch('app._carregar_documento_url', return_value=PDF), \
         patch('app._at_throttle'), \
         patch('app.requests.get', side_effect=[_arquivo(), _resp()]), \
         patch('app._gerar_hash_assinatura', return_value=token_legado) as gerar, \
         patch('app._criar_registro', return_value='recLEGADA'), \
         patch('app._anexar_attachment'), \
         patch('app._evolution_enviar_texto') as enviar_texto, \
         patch('app._evolution_enviar_documento') as enviar_documento:
        resultado, status = app._gerar_assinatura_core(
            funcionario_id=FUNC_ID,
            tipo_documento='COMUNICADO',
            arquivo_record_id=ARQUIVO_ID,
        )
    assert status == 200
    assert resultado['hash_token'] == token_legado
    gerar.assert_called_once_with()
    enviar_texto.assert_not_called()
    enviar_documento.assert_not_called()


def test_rota_repassa_reserva_ao_pacote_compartilhado_sem_efeito_externo():
    app.app.testing = True
    with patch.object(app, 'EMAIL_WEBHOOK_KEY', 'dummy'), \
         patch('app._airtable_api_key_atual', return_value='dummy'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, 'ok')), \
         patch('app._gerar_pacote_assinatura_holerite_ponto', return_value=({'status': 'ok'}, 200)) as pacote:
        resposta = app.app.test_client().post('/assinatura/gerar', headers={
            'X-API-KEY': 'dummy',
        }, json={
            'funcionario_id': FUNC_ID,
            'tipo_documento': app.TIPO_PACOTE_HOLERITE_PONTO,
            'arquivo_holerite_record_id': 'recHOLERITESINTETICO',
            'arquivo_folha_ponto_record_id': 'recPONTOSINTETICO',
            'token_reservado': TOKEN,
            'acao_execucao_id': ACAO_ID,
            'disparar_whatsapp': False,
        })
    assert resposta.status_code == 200
    assert pacote.call_args.kwargs['token_reservado'] == TOKEN
    assert pacote.call_args.kwargs['acao_execucao_id'] == ACAO_ID
    assert pacote.call_args.kwargs['disparar_whatsapp'] is False


def test_pacote_compartilhado_persiste_mesma_reserva_sem_whatsapp():
    with patch('app._validar_configuracao_assinatura_v36', return_value=(True, 'ok')), \
         patch('app._status_funcionario_elegivel', return_value=(True, None)), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('PESSOA SINTETICA', '5511000000000')), \
         patch('app._carregar_documento_url', side_effect=[PDF, PDF + b'-ponto']), \
         patch('app._extrair_texto_pdf_bytes', side_effect=['holerite', 'ponto']), \
         patch('app.extrair_competencia_holerite', return_value=('Setembro 2026', '2026-09-01')), \
         patch('app._extrair_competencia_folha_ponto', return_value=('Setembro 2026', '2026-09-01')), \
         patch('app._at_throttle'), \
         patch('app.requests.get', side_effect=[_arquivo(), _arquivo(), _resp(), _resp()]), \
         patch('app._criar_registro', return_value='recPACOTESINTETICO') as criar, \
         patch('app._anexar_attachment'), \
         patch('app._evolution_enviar_texto') as enviar:
        resultado, status = app._gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID,
            arquivo_holerite_id='recHOLERITESINTETICO',
            arquivo_ponto_id='recPONTOSINTETICO',
            token_reservado=TOKEN,
            acao_execucao_id=ACAO_ID,
            disparar_whatsapp=False,
        )
    assert status == 200
    assert resultado['hash_token'] == TOKEN
    campos = criar.call_args.args[1]
    assert campos[app.F_ASS_HASH] == TOKEN
    assert campos[app.F_ASS_REQUEST_ID] == ACAO_ID
    enviar.assert_not_called()


def test_idempotency_key_permanece_identidade_documental_sem_token():
    esperado = hashlib.sha256(
        f'{FUNC_ID}|{ARQUIVO_ID}|{hashlib.sha256(PDF).hexdigest()}|COMUNICADO'.encode()
    ).hexdigest()
    (resultado, status), _, _, _ = _chamar_core()
    assert status == 200
    assert resultado['idempotency_key'] == esperado
