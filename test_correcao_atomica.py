"""
TESTE INTEGRAL DA CORREÇÃO ATÔMICA
- Upload PDF → extração de URL → enfileiramento → error handling
"""

import json
from io import BytesIO
from unittest.mock import patch, Mock, call
import pytest


def test_separar_pdf_url_obtained_after_upload():
    """
    Teste A+B+C: Upload → Airtable retorna anexo → URL extraída com sucesso
    """
    from app import app

    client = app.test_client()
    pdf_bytes = b'%PDF-1.4\n' + b'x' * 200
    record_id = 'recTEST123456789'

    # Mock do upload (sucesso)
    # Mock do GET com retry (retorna anexo na primeira tentativa)
    # Mock do apply_async

    with patch('app._fazer_upload_pdf_airtable', return_value=True) as mock_upload, \
         patch('app.requests.get') as mock_get, \
         patch('app._enfileirar_processamento', return_value=(True, 'task-123')) as mock_enfileira:

        # Mock GET para validar record (primeira chamada)
        # Mock GET para obter URL (segunda chamada com returnFieldsByFieldId=true)
        mock_get.side_effect = [
            Mock(status_code=200, json=lambda: {'fields': {}}),  # Validar record
            Mock(status_code=200, json=lambda: {  # Obter URL com retry
                'fields': {
                    'fldQtevv6jAwKVdEN': [
                        {'url': 'https://example.com/attachment.pdf'}
                    ]
                }
            }),
        ]

        response = client.post(
            '/separar',
            data={
                'processar_arquivo_record_id': record_id,
                'pdf': (BytesIO(pdf_bytes), 'test.pdf'),
            },
            content_type='multipart/form-data',
        )

    # Validações obrigatórias
    assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.get_json()}"
    data = response.get_json()
    assert data['success'] is True
    assert data['task_id'] == 'task-123'

    # Validar que apply_async foi chamado com URL válida
    assert mock_enfileira.call_count == 1, f"Expected 1 call to apply_async, got {mock_enfileira.call_count}"
    call_args = mock_enfileira.call_args
    assert call_args[0][2] == 'https://example.com/attachment.pdf', "pdf_url deve ser a URL do anexo"

    print("✅ Test A+B+C PASSOU: PDF upload → URL extraída → apply_async com URL válida")


def test_separar_pdf_url_missing_no_enqueue():
    """
    Teste D+E+F: Se URL não aparecer, não enfileira e usa campo válido
    """
    from app import app

    client = app.test_client()
    pdf_bytes = b'%PDF-1.4\n' + b'x' * 200
    record_id = 'recTEST123456789'

    with patch('app._fazer_upload_pdf_airtable', return_value=True) as mock_upload, \
         patch('app.requests.get') as mock_get, \
         patch('app._enfileirar_processamento') as mock_enfileira:

        # Mock GET: sempre retorna sem anexos (5 tentativas)
        mock_get.side_effect = [
            Mock(status_code=200, json=lambda: {'fields': {}}),  # Validar record
            Mock(status_code=200, json=lambda: {'fields': {}}),  # Tentativa 1
            Mock(status_code=200, json=lambda: {'fields': {}}),  # Tentativa 2
            Mock(status_code=200, json=lambda: {'fields': {}}),  # Tentativa 3
            Mock(status_code=200, json=lambda: {'fields': {}}),  # Tentativa 4
            Mock(status_code=200, json=lambda: {'fields': {}}),  # Tentativa 5
        ]

        response = client.post(
            '/separar',
            data={
                'processar_arquivo_record_id': record_id,
                'pdf': (BytesIO(pdf_bytes), 'test.pdf'),
            },
            content_type='multipart/form-data',
        )

    # Validações obrigatórias
    assert response.status_code == 200, f"Expected 200 when URL missing, got {response.status_code}"
    data = response.get_json()
    assert data['success'] is False
    assert data['error_code'] == 'PDF_ATTACHMENT_URL_NOT_AVAILABLE'

    # NÃO deve chamar apply_async se URL não existe
    mock_enfileira.assert_not_called()

    print("✅ Test D+E+F PASSOU: URL ausente → sem enfileiramento → error code correto")


def test_field_ids_valid_and_consistent():
    """
    Teste G+H: Todos os Field IDs existem no metadata e não há inválidos
    """
    from app import (
        F_PROC_STATUS, F_PROC_DATA, F_PROC_TIPO_DOC, F_PROC_ARQUIVOS
    )
    from tarefas_processar_pdf import (
        F_PROC_STATUS as TASK_F_PROC_STATUS,
        F_PROC_DATA as TASK_F_PROC_DATA,
        F_PROC_TIPO_DOC as TASK_F_PROC_TIPO_DOC,
    )

    # Metadata real do Airtable
    valid_fields = {
        'fldvN9T5MiuKZGDi0': 'Status',
        'flddNzmqp1Im1D02m': 'Data Processo',
        'fldvkOVlwCMywGTES': 'Tipo de Documento',
        'fldQtevv6jAwKVdEN': 'Arquivos',
    }

    # Validar app.py
    assert F_PROC_STATUS in valid_fields, f"app.py F_PROC_STATUS inválido: {F_PROC_STATUS}"
    assert F_PROC_DATA in valid_fields, f"app.py F_PROC_DATA inválido: {F_PROC_DATA}"
    assert F_PROC_TIPO_DOC in valid_fields, f"app.py F_PROC_TIPO_DOC inválido: {F_PROC_TIPO_DOC}"
    assert F_PROC_ARQUIVOS in valid_fields, f"app.py F_PROC_ARQUIVOS inválido: {F_PROC_ARQUIVOS}"

    # Validar tarefas_processar_pdf.py (deve ser idêntico)
    assert TASK_F_PROC_STATUS == F_PROC_STATUS, "tarefas_processar_pdf.py F_PROC_STATUS diverge"
    assert TASK_F_PROC_DATA == F_PROC_DATA, "tarefas_processar_pdf.py F_PROC_DATA diverge"
    assert TASK_F_PROC_TIPO_DOC == F_PROC_TIPO_DOC, "tarefas_processar_pdf.py F_PROC_TIPO_DOC diverge (era fldvkOVlwCMywGTEs)"

    # Verificar que fldvkOVlwCMywGTEs (typo antigo) não existe mais em nenhum lugar
    import re
    with open('app.py', 'r', encoding='utf-8') as f:
        app_content = f.read()
    with open('tarefas_processar_pdf.py', 'r', encoding='utf-8') as f:
        task_content = f.read()

    assert 'fldvkOVlwCMywGTEs' not in app_content, "Typo antigo encontrado em app.py"
    assert 'fldvkOVlwCMywGTEs' not in task_content, "Typo antigo encontrado em tarefas_processar_pdf.py"

    print("✅ Test G+H PASSOU: Todos Field IDs válidos e consistentes")


def test_task_registration():
    """
    Teste I: processar_pdf_task está registrada no Celery
    """
    from celery_app import celery_app

    registered = sorted(k for k in celery_app.tasks.keys() if 'processar_pdf' in k)
    assert 'tarefas_processar_pdf.processar_pdf_task' in registered, \
        f"processar_pdf_task não registrada. Registradas: {registered}"

    print("✅ Test I PASSOU: processar_pdf_task registrada")


def test_no_queue_parameter_in_apply_async():
    """
    Teste J: apply_async não usa queue='default'
    """
    import inspect
    from app import _enfileirar_processamento

    source = inspect.getsource(_enfileirar_processamento)
    assert "queue='default'" not in source, "apply_async ainda contém queue='default'"
    assert 'queue=' not in source or 'queue=' not in source.split('apply_async')[1].split(')')[0], \
        "apply_async usa queue parameter"

    print("✅ Test J PASSOU: Sem queue='default' em apply_async")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
