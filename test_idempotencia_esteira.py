"""
Macro 6A — Auditoria de idempotência (Task #3).

Sem credenciais/conector Airtable ou PostgreSQL habilitados nesta sessão
(ver relatório final: "não verificável nesta sessão" != "não provisionado"),
a inspeção só-leitura de duplicatas reais fica registrada como pendência
externa. O que ESTE arquivo comprova, com fixtures 100% sintéticas e
adaptadores simulados (sem nenhuma escrita real): que as camadas de
idempotência já implementadas no código — Message-ID (Emails Savian),
Hash do Anexo original (Arquivos), e a verificação de anexo já existente
por nome+hash (_verificar_anexo_em_lista / _buscar_holerite_existente) —
de fato bloqueiam reprocessamento quando exercitadas. Antes desta bateria
de testes, nenhuma dessas funções tinha cobertura direta (achado de
COBERTURA, não de lógica -- o comportamento em si já está correto na
leitura de código; o gap era a ausência de prova automatizada).

100% dado sintético -- nenhum CPF/nome real em nenhum lugar deste arquivo.
"""
import base64
import hashlib
from unittest.mock import Mock, patch

import pytest

from app import (
    TIPO_ENVIO_EMAIL_CLIENTE,
    _buscar_holerite_existente,
    _disparar_fila_email,
    _verificar_anexo_em_lista,
    _verificar_anexo_holerite,
    app,
)


# ── _verificar_anexo_em_lista — identidade por nome + hash ──────────────

def test_arquivo_ausente_da_lista_e_novo():
    attachments = [{'filename': 'outro.pdf', 'url': 'https://x/outro.pdf'}]
    resultado = _verificar_anexo_em_lista(attachments, 'holerite.pdf', 'hashqualquer')
    assert resultado == 'novo'


def test_mesmo_nome_e_mesmo_conteudo_e_identico_nao_duplica():
    conteudo_existente = b'%PDF-conteudo-sintetico-identico'
    hash_existente = hashlib.sha256(conteudo_existente).hexdigest()
    attachments = [{'filename': 'holerite.pdf', 'url': 'https://x/holerite.pdf'}]

    with patch('app.requests.get', return_value=Mock(content=conteudo_existente)):
        resultado = _verificar_anexo_em_lista(attachments, 'holerite.pdf', hash_existente)

    assert resultado == 'identico'


def test_mesmo_nome_mas_conteudo_diferente_e_conflito_nao_substitui_sozinho():
    conteudo_existente = b'%PDF-conteudo-A'
    hash_novo_diferente = hashlib.sha256(b'%PDF-conteudo-B').hexdigest()
    attachments = [{'filename': 'holerite.pdf', 'url': 'https://x/holerite.pdf'}]

    with patch('app.requests.get', return_value=Mock(content=conteudo_existente)):
        resultado = _verificar_anexo_em_lista(attachments, 'holerite.pdf', hash_novo_diferente)

    assert resultado == 'conflito'


def test_falha_ao_baixar_anexo_existente_e_tratada_como_conflito_nunca_sobrescreve():
    """Falha de rede ao comparar não pode ser tratada como 'novo' — isso
    permitiria sobrescrever silenciosamente. Trava para o lado seguro."""
    attachments = [{'filename': 'holerite.pdf', 'url': 'https://x/holerite.pdf'}]

    with patch('app.requests.get', side_effect=Exception('timeout sintético')):
        resultado = _verificar_anexo_em_lista(attachments, 'holerite.pdf', 'hashqualquer')

    assert resultado == 'conflito'


def test_verificar_anexo_holerite_delega_para_campo_pdf_holerite():
    conteudo_existente = b'%PDF-holerite-sintetico'
    hash_existente = hashlib.sha256(conteudo_existente).hexdigest()
    from app import F_HOL_PDF
    holerite_fields = {F_HOL_PDF: [{'filename': 'holerite.pdf', 'url': 'https://x/holerite.pdf'}]}

    with patch('app.requests.get', return_value=Mock(content=conteudo_existente)):
        resultado = _verificar_anexo_holerite(holerite_fields, 'holerite.pdf', hash_existente)

    assert resultado == 'identico'


def test_verificar_anexo_holerite_sem_campo_pdf_e_novo():
    resultado = _verificar_anexo_holerite({}, 'holerite.pdf', 'hashqualquer')
    assert resultado == 'novo'


# ── _buscar_holerite_existente — identidade funcionário + competência ───

def _resposta(json_dict):
    r = Mock()
    r.raise_for_status = Mock()
    r.json.return_value = json_dict
    return r


def test_holerite_existente_para_mesmo_funcionario_e_encontrado():
    from app import F_HOL_FUNC
    resp = _resposta({'records': [
        {'id': 'recHOLEXISTENTE', 'fields': {F_HOL_FUNC: ['recFUNCALVO']}},
    ]})
    with patch('app.requests.get', return_value=resp), patch('app._at_throttle'):
        rec = _buscar_holerite_existente('recFUNCALVO', 'Maio 2026')
    assert rec is not None
    assert rec['id'] == 'recHOLEXISTENTE'


def test_holerite_de_outro_funcionario_na_mesma_folha_nao_e_confundido():
    """Mesma folha_mensal, mas vinculado a OUTRO funcionário -- não pode
    ser tratado como duplicata do funcionário-alvo."""
    from app import F_HOL_FUNC
    resp = _resposta({'records': [
        {'id': 'recHOLOUTRAPESSOA', 'fields': {F_HOL_FUNC: ['recOUTROFUNC']}},
    ]})
    with patch('app.requests.get', return_value=resp), patch('app._at_throttle'):
        rec = _buscar_holerite_existente('recFUNCALVO', 'Maio 2026')
    assert rec is None


def test_nenhum_holerite_na_folha_devolve_none():
    resp = _resposta({'records': []})
    with patch('app.requests.get', return_value=resp), patch('app._at_throttle'):
        rec = _buscar_holerite_existente('recFUNCALVO', 'Maio 2026')
    assert rec is None


# ── /email/webhook — Message-ID e Hash do Anexo (ingestão) ──────────────

def _client():
    app.testing = True
    return app.test_client()


def test_webhook_message_id_duplicado_nao_grava_nada():
    payload = {
        'message_id': '<msg-sintetico-123@mail.gmail.com>',
        'assunto': 'Assunto sintético', 'remetente': 'origem@teste.invalido',
        'corpo': 'corpo sintético', 'anexos': [],
    }
    with patch('app.EMAIL_WEBHOOK_KEY', 'chave-sintetica-teste'), patch('app.AIRTABLE_API_KEY', 'airtable-key-sintetica'), \
         patch('app._buscar_por_campo', return_value={'id': 'recEMAILJAEXISTE'}) as mock_busca, \
         patch('app._criar_registro') as mock_criar:
        resp = _client().post(
            '/email/webhook', json=payload,
            headers={'X-API-KEY': 'chave-sintetica-teste'},
        )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['email_savian']['acao'] == 'duplicado_message_id'
    assert body['email_savian']['gravado'] is False
    mock_criar.assert_not_called()
    mock_busca.assert_called_once()
    assert mock_busca.call_args.args[1] == 'MESSAGE ID'


def test_webhook_anexo_com_hash_ja_existente_nao_reprocessa_conteudo():
    conteudo = b'%PDF-anexo-sintetico'
    hash_esperado = hashlib.sha256(conteudo).hexdigest()
    payload = {
        'message_id': '<msg-sintetico-456@mail.gmail.com>',
        'assunto': 'Assunto sintético', 'remetente': 'origem@teste.invalido',
        'corpo': 'corpo sintético',
        'anexos': [{'nome_arquivo': 'doc.pdf', 'conteudo_base64': base64.b64encode(conteudo).decode()}],
    }

    def busca_por_campo(table, campo, valor):
        if campo == 'MESSAGE ID':
            return None  # e-mail em si não é duplicado
        if campo == 'Hash do Anexo':
            return {'id': 'recARQUIVOJAEXISTE'}  # mas o anexo já existe
        return None

    with patch('app.EMAIL_WEBHOOK_KEY', 'chave-sintetica-teste'), patch('app.AIRTABLE_API_KEY', 'airtable-key-sintetica'), \
         patch('app._buscar_por_campo', side_effect=busca_por_campo), \
         patch('app._criar_registro', return_value='recEMAILNOVO') as mock_criar, \
         patch('app.classificar_documento', return_value=('Outro', 0)):
        resp = _client().post(
            '/email/webhook', json=payload,
            headers={'X-API-KEY': 'chave-sintetica-teste'},
        )

    assert resp.status_code == 200
    body = resp.get_json()
    anexo = body['anexos_processados'][0]
    assert anexo['duplicado'] is True
    assert anexo['hash'] == hash_esperado
    assert anexo['arquivo_record_id'] == 'recARQUIVOJAEXISTE'
    # o e-mail (Emails Savian) foi criado normalmente -- só o ANEXO duplicado
    # foi bloqueado, e-mails legítimos com mistura de anexo novo/repetido
    # continuam sendo registrados.
    mock_criar.assert_called_once()


def test_webhook_dry_run_nunca_cria_registro_mesmo_sem_duplicidade():
    payload = {
        'message_id': '<msg-sintetico-789@mail.gmail.com>',
        'assunto': 'Assunto sintético', 'remetente': 'origem@teste.invalido',
        'corpo': 'corpo sintético', 'anexos': [], 'dry_run': True,
    }
    with patch('app.EMAIL_WEBHOOK_KEY', 'chave-sintetica-teste'), patch('app.AIRTABLE_API_KEY', 'airtable-key-sintetica'), \
         patch('app._buscar_por_campo', return_value=None), \
         patch('app._criar_registro') as mock_criar:
        resp = _client().post(
            '/email/webhook', json=payload,
            headers={'X-API-KEY': 'chave-sintetica-teste'},
        )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['email_savian']['acao'] == 'criaria_novo'
    assert body['email_savian']['gravado'] is False
    mock_criar.assert_not_called()


# ── Protocolo de envio (Macro 6A — fechamento autônomo, §7, camada 9) ───
# Achado: _disparar_fila_email não tinha nenhum teste provando que um
# envio JÁ marcado "Enviado" nunca é reenviado, nem que o envio real marca
# o Status corretamente. A lógica em si (filtro Status == 'Preparando')
# já estava correta na leitura de código -- gap de cobertura, não de lógica.

@patch('app._at_throttle', lambda: None)
@patch('app._at_listar_todos')
def test_disparar_fila_email_envia_uma_vez_e_marca_enviado(mock_listar):
    mock_listar.return_value = [{'id': 'recENV1', 'fields': {
        'Tipo': TIPO_ENVIO_EMAIL_CLIENTE, 'Status': 'Preparando', 'Canal': 'E-mail',
        'Email': 'cliente@teste.invalido', 'Cliente': [{'id': 'recCLI1', 'name': 'CLIENTE SINTETICO'}],
        'PDF HOLERITES': [{'url': 'http://x/h.pdf', 'filename': 'h.pdf'}],
    }}]
    with patch('app.EMAIL_SENDER', 'remetente@teste.invalido'), \
         patch('app.EMAIL_SENDER_PASSWORD', 'senha-sintetica-teste'), \
         patch('app._baixar_attachment_bytes', return_value=b'pdf-fake'), \
         patch('app._smtp_enviar_email') as mock_smtp, \
         patch('app._marcar_envio_status') as mock_marcar:
        resultado = _disparar_fila_email(dry_run=False)

    assert resultado['total_enviados'] == 1
    mock_smtp.assert_called_once()
    mock_marcar.assert_called_once_with('recENV1', 'Enviado')


@patch('app._at_throttle', lambda: None)
@patch('app._at_listar_todos')
def test_disparar_fila_email_nunca_reenvia_envio_ja_marcado_enviado(mock_listar):
    """Achado central desta camada: um Envio já 'Enviado' nunca é
    reprocessado -- mesmo estando na mesma listagem que um 'Preparando'
    legítimo, só este último é enviado."""
    mock_listar.return_value = [
        {'id': 'recENV_JA_ENVIADO', 'fields': {
            'Tipo': TIPO_ENVIO_EMAIL_CLIENTE, 'Status': 'Enviado', 'Canal': 'E-mail',
            'Email': 'outro@teste.invalido', 'Cliente': [{'id': 'recCLI2', 'name': 'OUTRO CLIENTE'}],
            'PDF HOLERITES': [{'url': 'http://x/h2.pdf', 'filename': 'h2.pdf'}],
        }},
        {'id': 'recENV_PREPARANDO', 'fields': {
            'Tipo': TIPO_ENVIO_EMAIL_CLIENTE, 'Status': 'Preparando', 'Canal': 'E-mail',
            'Email': 'cliente@teste.invalido', 'Cliente': [{'id': 'recCLI1', 'name': 'CLIENTE SINTETICO'}],
            'PDF HOLERITES': [{'url': 'http://x/h.pdf', 'filename': 'h.pdf'}],
        }},
    ]
    with patch('app.EMAIL_SENDER', 'remetente@teste.invalido'), \
         patch('app.EMAIL_SENDER_PASSWORD', 'senha-sintetica-teste'), \
         patch('app._baixar_attachment_bytes', return_value=b'pdf-fake'), \
         patch('app._smtp_enviar_email') as mock_smtp, \
         patch('app._marcar_envio_status') as mock_marcar:
        resultado = _disparar_fila_email(dry_run=False)

    assert resultado['total_enviados'] == 1
    mock_smtp.assert_called_once()
    # o envio já concluído nunca aparece em nenhuma chamada de marcação/envio
    ids_marcados = [c.args[0] for c in mock_marcar.call_args_list]
    assert 'recENV_JA_ENVIADO' not in ids_marcados
    assert ids_marcados == ['recENV_PREPARANDO']
