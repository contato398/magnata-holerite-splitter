"""
Macro 6A — Auditoria e correção pontual de segurança de rotas (Task #4).

Achado comprovado (risco prioritário indicado pelo usuário e confirmado por
leitura de código, inclusive nas próprias docstrings anteriores): as rotas
`/processar-doc-cliente`, `/processar-guia` e `/processar-recibos`
escreviam em Airtable (Extrato Mensal/FGTS de CLIENTES, Guias e
Comprovantes, Recibos de FUNCIONÁRIOS) aceitando qualquer chamador que
soubesse a URL pública do serviço, sem nenhuma credencial própria — só
checavam se o SERVIDOR tinha AIRTABLE_API_KEY configurada, o que não
autentica quem está chamando.

Correção: reaproveita o MESMO mecanismo já usado por /email/webhook,
/processar-fila, /gerar-fila-envios-email e /disparar-fila-email — header
X-API-KEY comparado à variável de ambiente já existente EMAIL_WEBHOOK_KEY.
Nenhum segredo novo, nenhuma variável de ambiente nova.

100% dado sintético -- nenhum CPF/nome real em nenhum lugar deste arquivo.
"""
import io
from unittest.mock import patch

import pytest

import app
from app import app as flask_app


def _client():
    flask_app.testing = True
    return flask_app.test_client()


PDF_SINTETICO = b'%PDF-1.4\n' + b'conteudo-sintetico-de-teste' * 5


# ── /processar-doc-cliente ───────────────────────────────────────────────

def test_processar_doc_cliente_sem_x_api_key_e_rejeitado_com_401():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._processar_doc_cliente_master') as mock_processa:
        resp = _client().post(
            '/processar-doc-cliente',
            data={'tipo': 'extrato', 'folha_mensal': 'Maio 2026',
                  'pdf': (io.BytesIO(PDF_SINTETICO), 'mestre.pdf')},
            content_type='multipart/form-data',
        )
    assert resp.status_code == 401
    mock_processa.assert_not_called()


def test_processar_doc_cliente_com_x_api_key_errada_e_rejeitado_com_401():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._processar_doc_cliente_master') as mock_processa:
        resp = _client().post(
            '/processar-doc-cliente',
            data={'tipo': 'extrato', 'folha_mensal': 'Maio 2026',
                  'pdf': (io.BytesIO(PDF_SINTETICO), 'mestre.pdf')},
            headers={'X-API-KEY': 'chave-errada'},
            content_type='multipart/form-data',
        )
    assert resp.status_code == 401
    mock_processa.assert_not_called()


def test_processar_doc_cliente_com_x_api_key_correta_segue_fluxo_normal():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._processar_doc_cliente_master',
               return_value={'status': 'concluido', 'registros_criados': 0}) as mock_processa:
        resp = _client().post(
            '/processar-doc-cliente',
            data={'tipo': 'extrato', 'folha_mensal': 'Maio 2026',
                  'pdf': (io.BytesIO(PDF_SINTETICO), 'mestre.pdf')},
            headers={'X-API-KEY': 'test'},
            content_type='multipart/form-data',
        )
    assert resp.status_code == 200
    mock_processa.assert_called_once()


# ── /processar-guia ──────────────────────────────────────────────────────

def test_processar_guia_sem_x_api_key_e_rejeitado_com_401():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._criar_registro') as mock_criar:
        resp = _client().post(
            '/processar-guia',
            data={'tipo': 'DCTFWeb',
                  'arquivo': (io.BytesIO(PDF_SINTETICO), 'guia.pdf')},
            content_type='multipart/form-data',
        )
    assert resp.status_code == 401
    mock_criar.assert_not_called()


def test_processar_guia_com_x_api_key_correta_segue_fluxo_normal():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._criar_registro', return_value='recGUIANOVA'), \
         patch('app._anexar_attachment') as mock_anexar:
        resp = _client().post(
            '/processar-guia',
            data={'tipo': 'DCTFWeb',
                  'arquivo': (io.BytesIO(PDF_SINTETICO), 'guia.pdf')},
            headers={'X-API-KEY': 'test'},
            content_type='multipart/form-data',
        )
    assert resp.status_code == 200
    mock_anexar.assert_called_once()


# ── /processar-recibos ───────────────────────────────────────────────────

def test_processar_recibos_sem_x_api_key_e_rejeitado_com_401():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._processar_recibos_master') as mock_processa:
        resp = _client().post(
            '/processar-recibos',
            data={'tipo': 'Salário', 'folha_mensal': 'Maio 2026',
                  'pdf': (io.BytesIO(PDF_SINTETICO), 'recibos.pdf')},
            content_type='multipart/form-data',
        )
    assert resp.status_code == 401
    mock_processa.assert_not_called()


def test_processar_recibos_com_x_api_key_correta_segue_fluxo_normal():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._processar_recibos_master',
               return_value={'status': 'concluido', 'recibos_anexados': 0}) as mock_processa:
        resp = _client().post(
            '/processar-recibos',
            data={'tipo': 'Salário', 'folha_mensal': 'Maio 2026',
                  'pdf': (io.BytesIO(PDF_SINTETICO), 'recibos.pdf')},
            headers={'X-API-KEY': 'test'},
            content_type='multipart/form-data',
        )
    assert resp.status_code == 200
    mock_processa.assert_called_once()


# ── Regressão: rotas já protegidas continuam exigindo a chave certa ─────

def test_processar_fila_continua_exigindo_x_api_key():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'):
        resp = _client().post('/processar-fila', json={'tipo_documento': 'Holerite'})
    assert resp.status_code == 401


def test_email_webhook_continua_exigindo_x_api_key():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'):
        resp = _client().post('/email/webhook', json={'message_id': '<x@y>'})
    assert resp.status_code == 401


# ── "dry-run não grava" (Macro 6A — fechamento autônomo, §8) ────────────
# Achado de cobertura: os testes existentes de dry_run checavam só o
# retorno ('acao': 'criaria_envio'), nunca provavam com um spy que a
# função de escrita real nunca é chamada. A lógica em si já estava certa
# (if dry_run: ... else: _criar_envio_documento(...)) -- gap de prova, não
# de comportamento.

@patch('app._at_throttle', lambda: None)
@patch('app._carregar_envios_pendentes', lambda tipo: (set(), set()))
@patch('app._carregar_contexto_distribuicao', lambda: ({}, {}, {}))
@patch('app._at_listar_todos')
def test_gerar_fila_envios_email_dry_run_nunca_chama_criar_envio_documento(mock_listar):
    def fake(table, fields=None, filtro=None):
        if table == app.TABLE_CLIENTES:
            return [{'id': 'recCLI', 'fields': {
                'Nome': 'CLIENTE SINTETICO', 'Email': 'cliente@teste.invalido',
                'Status': {'name': 'Ativo'},
            }}]
        return []
    mock_listar.side_effect = fake

    with patch('app._criar_envio_documento') as mock_criar:
        resultado = app._gerar_fila_envios_email(
            folha_mensal='Maio 2026', guias_ids=['recG1'], dry_run=True)

    assert resultado['dry_run'] is True
    mock_criar.assert_not_called()


@patch('app._at_throttle', lambda: None)
@patch('app._carregar_envios_pendentes', lambda tipo: (set(), set()))
@patch('app._carregar_contexto_distribuicao', lambda: ({}, {}, {}))
@patch('app._at_listar_todos')
def test_gerar_fila_envios_email_real_chama_criar_envio_documento(mock_listar):
    """Contraprova: com dry_run=False, o mesmo cenário CHAMA a escrita real
    -- confirma que o teste acima não passaria por acidente (ex.: cliente
    filtrado antes de chegar no branch dry_run)."""
    def fake(table, fields=None, filtro=None):
        if table == app.TABLE_CLIENTES:
            return [{'id': 'recCLI', 'fields': {
                'Nome': 'CLIENTE SINTETICO', 'Email': 'cliente@teste.invalido',
                'Status': {'name': 'Ativo'},
            }}]
        return []
    mock_listar.side_effect = fake

    with patch('app._criar_envio_documento', return_value=('recENVIONOVO', True)) as mock_criar:
        resultado = app._gerar_fila_envios_email(
            folha_mensal='Maio 2026', guias_ids=['recG1'], dry_run=False)

    assert resultado['dry_run'] is False
    mock_criar.assert_called_once()
