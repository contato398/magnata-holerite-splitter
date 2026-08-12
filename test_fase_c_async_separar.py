"""
FASE C — Testes da API Assíncrona /separar (v4.0 — SEM /tmp)

12 cenários testados, todos em memória (sem disco):
1. missing PDF → erro 200
2. missing Record ID → erro 400
3. invalid Record ID (não começa com 'rec') → erro 400
4. invalid PDF (header inválido) → não enfileira
5. upload failure → não enfileira
6. successful upload → calls queue exactly 1x
7. duplicate task → idempotency protegida
8. Worker success → updates Status=Concluído
9. Worker failure → updates Status=Erro
10. no WhatsApp calls → zero integração
11. no direct calls to construir_mapa_cpf → via imports
12. no /tmp dependency → memory-only

Status: CORRIGIDO (sem /tmp)
Data: 2026-07-20
"""

import pytest
import json
import hashlib
import base64
from io import BytesIO
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime


@pytest.fixture
def mock_airtable_env():
    """Setup environment variables"""
    with patch.dict('os.environ', {
        'AIRTABLE_API_KEY': 'patTEST123',
        'REDIS_URL': 'redis://localhost:6379/0',
    }):
        yield


@pytest.fixture
def test_pdf_bytes():
    """Cria um PDF fake válido (em memória, > 100 bytes)"""
    # PDF fake com conteúdo suficiente para passar na validação (> 100 bytes)
    pdf_content = b'%PDF-1.4\n%fake content for testing\n' + b'x' * 200
    return pdf_content


@pytest.fixture
def valid_record_id():
    return 'recTEST123456789'


# ─────────────────────────────────────────────────────────────────────────────
# CENÁRIO 1: Missing PDF → erro 200
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_1_missing_pdf(mock_airtable_env):
    """
    POST /separar SEM arquivo PDF
    Esperado: status 200, error_code='ATTACHMENT_NOT_FOUND'
    Validação: Sem /tmp (request.files['pdf'] é vazio)
    """
    from app import app

    client = app.test_client()

    response = client.post(
        '/separar',
        data={
            'processar_arquivo_record_id': 'recTEST123',
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is False
    assert data['error_code'] == 'ATTACHMENT_NOT_FOUND'
    print("✅ Cenário 1 PASSOU: Missing PDF rejeitado (memória)")


# ─────────────────────────────────────────────────────────────────────────────
# CENÁRIO 2: Missing Record ID → erro 400
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_2_missing_record_id(mock_airtable_env, test_pdf_bytes):
    """
    POST /separar COM PDF mas SEM Record ID
    Esperado: status 400, error_code='INVALID_RECORD_ID'
    Validação: Erro retorna antes de tocar no arquivo (PDF em BytesIO)
    """
    from app import app

    client = app.test_client()

    response = client.post(
        '/separar',
        data={
            'pdf': (BytesIO(test_pdf_bytes), 'test.pdf'),
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data['success'] is False
    assert data['error_code'] == 'INVALID_RECORD_ID'
    print("✅ Cenário 2 PASSOU: Missing Record ID rejeitado (400)")


# ─────────────────────────────────────────────────────────────────────────────
# CENÁRIO 3: Invalid Record ID format → erro 400
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_3_invalid_record_id_format(mock_airtable_env, test_pdf_bytes):
    """
    POST /separar COM PDF e Record ID que NÃO começa com 'rec'
    Esperado: status 400, error_code='INVALID_RECORD_ID'
    """
    from app import app

    client = app.test_client()

    response = client.post(
        '/separar',
        data={
            'processar_arquivo_record_id': 'INVALID123',
            'pdf': (BytesIO(test_pdf_bytes), 'test.pdf'),
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data['success'] is False
    assert data['error_code'] == 'INVALID_RECORD_ID'
    print("✅ Cenário 3 PASSOU: Invalid Record ID format rejeitado (400)")


# ─────────────────────────────────────────────────────────────────────────────
# CENÁRIO 4: Invalid PDF header → erro, no upload call
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_4_invalid_pdf_header(mock_airtable_env):
    """
    POST /separar COM PDF inválido (header != %PDF)
    Esperado: status 200, error_code='PDF_INVALID', upload NÃO chamado
    Validação: Validação em memória, sem disco
    """
    from app import app

    client = app.test_client()

    fake_pdf = b'NOT_A_PDF_HEADER\n content here' + b'x' * 200

    with patch('app._fazer_upload_pdf_airtable') as mock_upload:
        response = client.post(
            '/separar',
            data={
                'processar_arquivo_record_id': 'recTEST123',
                'pdf': (BytesIO(fake_pdf), 'test.pdf'),
            },
            content_type='multipart/form-data',
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is False
    assert data['error_code'] == 'PDF_INVALID'

    # NÃO chamou upload
    mock_upload.assert_not_called()
    print("✅ Cenário 4 PASSOU: Invalid PDF header rejeitado, sem upload")


# ─────────────────────────────────────────────────────────────────────────────
# CENÁRIO 5: Upload failure → error, no queue
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_5_upload_failure_no_queue(mock_airtable_env, test_pdf_bytes, valid_record_id):
    """
    POST /separar: upload falha → Celery task NÃO é criado
    Esperado: error_code='PDF_UPLOAD_FAILED', _enfileirar NOT called
    """
    from app import app

    client = app.test_client()

    with patch('app._fazer_upload_pdf_airtable', return_value=False) as mock_upload, \
         patch('app._enfileirar_processamento') as mock_enfileira, \
         patch('requests.get') as mock_get:

        # Mock Airtable record exists
        mock_get.return_value = Mock(status_code=200, json=lambda: {'fields': {}})

        response = client.post(
            '/separar',
            data={
                'processar_arquivo_record_id': valid_record_id,
                'pdf': (BytesIO(test_pdf_bytes), 'test.pdf'),
            },
            content_type='multipart/form-data',
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is False
    assert data['error_code'] == 'PDF_UPLOAD_FAILED'

    # NÃO enfileirou
    mock_enfileira.assert_not_called()
    print("✅ Cenário 5 PASSOU: Upload failure → sem enfileiramento")


# ─────────────────────────────────────────────────────────────────────────────
# CENÁRIO 6: Success → HTTP 202, queue exactly 1x
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_6_success_queue_once(mock_airtable_env, test_pdf_bytes, valid_record_id):
    """
    POST /separar: sucesso completo → _enfileirar chamado EXATAMENTE 1x
    Esperado: HTTP 202, task_id retornado, mock_enfileira.call_count == 1
    """
    from app import app

    client = app.test_client()

    with patch('app._fazer_upload_pdf_airtable', return_value=True) as mock_upload, \
         patch('app._enfileirar_processamento', return_value=(True, 'task-123')) as mock_enfileira, \
         patch('requests.get') as mock_get:

        # Mock Airtable record exists
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                'fields': {
                    'fldQtevv6jAwKVdEN': [{'url': 'https://example.com/pdf'}]
                }
            }
        )

        response = client.post(
            '/separar',
            data={
                'processar_arquivo_record_id': valid_record_id,
                'pdf': (BytesIO(test_pdf_bytes), 'test.pdf'),
            },
            content_type='multipart/form-data',
        )

    assert response.status_code == 202
    data = response.get_json()
    assert data['success'] is True
    assert data['status'] == 'enfileirado'
    assert data['task_id'] == 'task-123'

    # EXATAMENTE uma vez
    assert mock_enfileira.call_count == 1
    print("✅ Cenário 6 PASSOU: Success → HTTP 202, queue 1x")


# ─────────────────────────────────────────────────────────────────────────────
# CENÁRIO 7: Idempotency key (SHA256)
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_7_idempotency_key_generated(test_pdf_bytes, valid_record_id):
    """
    /separar: idempotency_key = SHA256(record_id + pdf_hash)
    Esperado: mesmo PDF + record = mesma chave
    """
    from tarefas_processar_pdf import gerar_idempotency_key

    pdf_hash = hashlib.sha256(test_pdf_bytes).hexdigest()
    key1 = gerar_idempotency_key(valid_record_id, pdf_hash)
    key2 = gerar_idempotency_key(valid_record_id, pdf_hash)

    assert key1 == key2
    assert len(key1) == 64  # SHA256 hex

    other_hash = hashlib.sha256(b'OTHER_CONTENT').hexdigest()
    key3 = gerar_idempotency_key(valid_record_id, other_hash)

    assert key1 != key3
    print("✅ Cenário 7 PASSOU: Idempotency key (SHA256) OK")


# ─────────────────────────────────────────────────────────────────────────────
# CENÁRIO 8: Worker success → Status=Concluído
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_8_worker_success_updates_concluido(mock_airtable_env):
    """
    Worker: PDF processado com sucesso
    Esperado: Status='Concluído', F_PROC_DATA preenchido
    """
    from tarefas_processar_pdf import processar_pdf_task

    with patch('tarefas_processar_pdf.construir_mapa_cpf') as mock_build, \
         patch('tarefas_processar_pdf.extrair_pdf_colaborador') as mock_extract, \
         patch('tarefas_processar_pdf.requests.get') as mock_get, \
         patch('tarefas_processar_pdf._atualizar_airtable') as mock_update:

        mock_get.return_value = Mock(
            status_code=200,
            content=b'%PDF\nfake'
        )
        mock_build.return_value = (
            {'11111111111': {'nome': 'Test', 'paginas': [1]}},
            1
        )
        mock_extract.return_value = b'extracted_pdf'

        result = processar_pdf_task(
            'recTEST123',
            idempotency_key='key123',
            pdf_url='https://example.com/pdf'
        )

        calls = mock_update.call_args_list
        last_call_fields = calls[-1][0][1]
        assert last_call_fields.get('fldvN9T5MiuKZGDi0') == 'Concluído'

        print("✅ Cenário 8 PASSOU: Worker success → Status=Concluído")


# ─────────────────────────────────────────────────────────────────────────────
# CENÁRIO 9: Worker failure → Status=Erro
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_9_worker_failure_updates_erro(mock_airtable_env):
    """
    Worker: PDF processing falha
    Esperado: Status='Erro', F_PROC_TIPO_DOC preenchido
    """
    from tarefas_processar_pdf import processar_pdf_task

    with patch('tarefas_processar_pdf.construir_mapa_cpf') as mock_build, \
         patch('tarefas_processar_pdf._atualizar_airtable') as mock_update, \
         patch('tarefas_processar_pdf.requests.get') as mock_get:

        mock_get.return_value = Mock(
            status_code=200,
            content=b'%PDF\nfake'
        )
        mock_build.return_value = ({}, 1)  # Nenhum employee

        result = processar_pdf_task(
            'recTEST123',
            idempotency_key='key123',
            pdf_url='https://example.com/pdf'
        )

        calls = mock_update.call_args_list
        last_call_fields = calls[-1][0][1]
        assert last_call_fields.get('fldvN9T5MiuKZGDi0') == 'Erro'

        print("✅ Cenário 9 PASSOU: Worker failure → Status=Erro")


# ─────────────────────────────────────────────────────────────────────────────
# CENÁRIO 10: No WhatsApp
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_10_no_whatsapp_integration(mock_airtable_env):
    """
    Verifica: ZERO chamadas a WhatsApp na pipeline ASSÍNCRONA de /separar
    (rota `separar` + tarefa Celery `processar_pdf_task`) — este teste é
    especificamente sobre ESSA pipeline (fatiamento de PDF por CPF), que
    nunca deveria depender de canal de envio nenhum.

    Correção (Macro 6A — fechamento autônomo, achado de teste defeituoso +
    expectativa antiga): a versão anterior fazia `from app import app` e
    depois `inspect.getsource(app)` — `app` aqui é a INSTÂNCIA Flask (o
    import sombreia o nome do módulo), não o módulo; `inspect.getsource()`
    nunca aceita um objeto Flask, então o teste sempre falhava com
    TypeError antes mesmo de checar qualquer coisa (bug de mecanismo, não
    de comportamento). Além disso, a asserção original varria o app.py
    INTEIRO — e a aplicação hoje tem integração WhatsApp real e deliberada
    (Evolution API, canal de envio de Holerite, disparo de Assinatura
    Nativa do Kit de Admissão), já coberta positivamente por outros testes
    (test_fila_envios_v2_23.py, test_correcao_tabela_arquivos.py). Isso é
    uma regra antiga (época em que WhatsApp não existia na aplicação)
    substituída por decisão já aprovada — não uma regressão a reverter.

    O comportamento inseguro que o teste original queria evitar (chamar
    WhatsApp de dentro da pipeline de fatiamento de PDF, que não tem
    relação nenhuma com canal de envio) continua garantido abaixo, agora
    escopado corretamente às duas funções que de fato compõem essa
    pipeline, em vez do módulo inteiro.
    """
    from app import separar
    import inspect

    separar_source = inspect.getsource(separar)
    assert 'whatsapp' not in separar_source.lower()
    assert 'telegram' not in separar_source.lower()

    from tarefas_processar_pdf import processar_pdf_task
    task_source = inspect.getsource(processar_pdf_task)
    assert 'whatsapp' not in task_source.lower()
    assert 'telegram' not in task_source.lower()

    print("✅ Cenário 10 PASSOU: ZERO integração WhatsApp")


# ─────────────────────────────────────────────────────────────────────────────
# CENÁRIO 11: No direct function calls
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_11_no_direct_function_calls(mock_airtable_env):
    """
    Verifica: construir_mapa_cpf chamada via imports
    """
    from tarefas_processar_pdf import processar_pdf_task
    import inspect

    source = inspect.getsource(processar_pdf_task)
    assert 'construir_mapa_cpf(tmp_path)' in source

    from app import construir_mapa_cpf
    assert callable(construir_mapa_cpf)

    print("✅ Cenário 11 PASSOU: Funções via imports")


# ─────────────────────────────────────────────────────────────────────────────
# CENÁRIO 12: No /tmp dependency
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_12_no_tmp_dependency(mock_airtable_env, test_pdf_bytes, valid_record_id):
    """
    Verifica: /separar v4.0 não usa /tmp
    - Não chama extrair_pdf_do_request()
    - Lê pdf_bytes diretamente de request.files
    - Upload direto de pdf_bytes
    - Payload contém URL (não path local)
    """
    from app import app
    import inspect

    # Verificar que /separar NÃO usa extrair_pdf_do_request
    separar_source = inspect.getsource(app.view_functions['separar'])

    assert 'extrair_pdf_do_request' not in separar_source
    assert 'request.files' in separar_source
    assert 'pdf_bytes = pdf_file.read()' in separar_source or 'pdf_bytes' in separar_source
    assert 'request.files[\'pdf\']' in separar_source

    # Verificar que não há referência a tempfile
    assert 'tempfile' not in separar_source
    assert 'NamedTemporaryFile' not in separar_source
    assert 'os.unlink' not in separar_source

    print("✅ Cenário 12 PASSOU: /separar v4.0 sem /tmp")


# ─────────────────────────────────────────────────────────────────────────────

def run_all_tests():
    """Executa todos os 12 cenários"""
    print("\n" + "=" * 80)
    print("FASE C — TESTES DO /separar ASSÍNCRONO v4.0 (12 CENÁRIOS — SEM /tmp)")
    print("=" * 80 + "\n")

    pytest.main([__file__, '-vv', '--tb=short'])


if __name__ == '__main__':
    run_all_tests()
