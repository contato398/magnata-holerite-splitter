"""
TESTE DO HOTFIX FINAL — Garantir Concluído ou Erro no Airtable
"""

import pytest
from unittest.mock import patch, Mock, call


def test_task_updates_to_processando_initially():
    """
    Teste 1: Task atualiza Status→Processando no início
    """
    from tarefas_processar_pdf import processar_pdf_task

    with patch('tarefas_processar_pdf._atualizar_airtable') as mock_update, \
         patch('tarefas_processar_pdf.requests.get') as mock_get:

        # Mock: Processando OK, depois PDF download falha (força parada antes do processamento)
        mock_update.side_effect = [True, False]  # Processando OK, depois fecha
        mock_get.return_value = Mock(status_code=200, content=b'%PDF\nfake')

        result = processar_pdf_task(
            'recTEST123',
            idempotency_key='key123',
            pdf_url='https://example.com/pdf'
        )

        # Verificar que primeiro call foi com Status=Processando
        first_call = mock_update.call_args_list[0]
        fields_dict = first_call[0][1]
        assert 'fldvN9T5MiuKZGDi0' in fields_dict, "Status field não foi enviado"
        assert fields_dict['fldvN9T5MiuKZGDi0'] == 'Processando'

        print("✅ Teste 1 PASSOU: Status→Processando no início")


def test_task_success_requires_final_update():
    """
    Teste 2: success=True somente se atualização final de Concluído for confirmada
    """
    from tarefas_processar_pdf import processar_pdf_task

    # Caso A: Atualização final falha → success=False
    with patch('tarefas_processar_pdf._atualizar_airtable') as mock_update, \
         patch('tarefas_processar_pdf.construir_mapa_cpf') as mock_build, \
         patch('tarefas_processar_pdf.extrair_pdf_colaborador') as mock_extract, \
         patch('tarefas_processar_pdf.requests.get') as mock_get:

        mock_update.side_effect = [True, False]  # Processando OK, Concluído FALHA
        mock_get.return_value = Mock(status_code=200, content=b'%PDF\nfake')
        mock_build.return_value = ({'111': {'nome': 'Test', 'paginas': [1]}}, 1)
        mock_extract.return_value = b'pdf'

        result = processar_pdf_task('recTEST123', 'key123', 'https://example.com/pdf')

        assert result['success'] is False, "success deve ser False quando PATCH final falha"
        assert result['error_code'] == 'AIRTABLE_FINAL_UPDATE_FAILED'

    # Caso B: Atualização final OK → success=True
    with patch('tarefas_processar_pdf._atualizar_airtable') as mock_update, \
         patch('tarefas_processar_pdf.construir_mapa_cpf') as mock_build, \
         patch('tarefas_processar_pdf.extrair_pdf_colaborador') as mock_extract, \
         patch('tarefas_processar_pdf.requests.get') as mock_get:

        mock_update.side_effect = [True, True]  # Ambos OK
        mock_get.return_value = Mock(status_code=200, content=b'%PDF\nfake')
        mock_build.return_value = ({'111': {'nome': 'Test', 'paginas': [1]}}, 1)
        mock_extract.return_value = b'pdf'

        result = processar_pdf_task('recTEST123', 'key123', 'https://example.com/pdf')

        assert result['success'] is True, "success deve ser True quando PATCH final OK"
        assert result['total_funcionarios'] == 1

    print("✅ Teste 2 PASSOU: success=True somente se PATCH final confirmado")


def test_task_error_updates_status():
    """
    Teste 3: Exceção atualiza Status→Erro
    """
    from tarefas_processar_pdf import processar_pdf_task

    with patch('tarefas_processar_pdf._atualizar_airtable') as mock_update, \
         patch('tarefas_processar_pdf.construir_mapa_cpf') as mock_build, \
         patch('tarefas_processar_pdf.requests.get') as mock_get:

        mock_update.side_effect = [True, True]  # Processando OK, depois Erro OK
        mock_get.return_value = Mock(status_code=200, content=b'%PDF\nfake')
        mock_build.side_effect = Exception("PDF parse failed")

        result = processar_pdf_task('recTEST123', 'key123', 'https://example.com/pdf')

        assert result['success'] is False
        assert result['error_code'] == 'PROCESSING_ERROR'

        # Verificar que foi tentada atualização com Status=Erro
        error_calls = [c for c in mock_update.call_args_list if 'Erro' in str(c)]
        assert len(error_calls) > 0, "Status→Erro não foi chamado na exceção"

    print("✅ Teste 3 PASSOU: Exceção atualiza Status→Erro")


def test_field_ids_valid():
    """
    Teste 4: Nenhum Field ID inexistente
    """
    from tarefas_processar_pdf import (
        F_PROC_STATUS, F_PROC_DATA, F_PROC_TIPO_DOC, TABLE_PROCESSAR
    )

    valid_ids = {
        'fldvN9T5MiuKZGDi0': 'Status',
        'flddNzmqp1Im1D02m': 'Data Processo',
        'fldvkOVlwCMywGTES': 'Tipo de Documento',
        'tblXaLXvGJMyFOayc': 'TABLE_PROCESSAR',
    }

    assert F_PROC_STATUS in valid_ids.keys(), f"Status ID inválido: {F_PROC_STATUS}"
    assert F_PROC_DATA in valid_ids.keys(), f"Data ID inválido: {F_PROC_DATA}"
    assert F_PROC_TIPO_DOC in valid_ids.keys(), f"TipoDoc ID inválido: {F_PROC_TIPO_DOC}"
    assert TABLE_PROCESSAR in valid_ids.keys(), f"Table ID inválido: {TABLE_PROCESSAR}"

    print("✅ Teste 4 PASSOU: Todos Field IDs válidos")


def test_no_duplicate_tasks():
    """
    Teste 5: Nenhuma tarefa duplicada por idempotência
    """
    from tarefas_processar_pdf import gerar_idempotency_key

    # Mesmos inputs → mesma chave
    key1 = gerar_idempotency_key('recTEST', 'hash123')
    key2 = gerar_idempotency_key('recTEST', 'hash123')
    assert key1 == key2, "Chave não é determinística"

    # Inputs diferentes → chaves diferentes
    key3 = gerar_idempotency_key('recOTHER', 'hash123')
    assert key1 != key3, "Chaves devem divergir com record_id diferente"

    print("✅ Teste 5 PASSOU: Idempotência previne duplicação")


def test_retry_logic():
    """
    Teste 6: Retry apenas para 429/5xx, máximo 3 tentativas
    """
    from tarefas_processar_pdf import _atualizar_airtable

    with patch('tarefas_processar_pdf.requests.patch') as mock_patch:
        # Simular 429, 429, 200
        mock_patch.side_effect = [
            Mock(status_code=429, text='Rate limit'),
            Mock(status_code=429, text='Rate limit'),
            Mock(status_code=200, json=lambda: {'fields': {'fldvN9T5MiuKZGDi0': 'Concluído'}}),
        ]

        result = _atualizar_airtable('recTEST', {'fldvN9T5MiuKZGDi0': 'Concluído'})

        assert result is True, "Deve suceder após retries"
        assert mock_patch.call_count == 3, f"Esperava 3 chamadas, got {mock_patch.call_count}"

    # Teste: 4xx não faz retry
    with patch('tarefas_processar_pdf.requests.patch') as mock_patch:
        mock_patch.return_value = Mock(status_code=400, text='Bad request')

        result = _atualizar_airtable('recTEST', {'fldvN9T5MiuKZGDi0': 'Concluído'})

        assert result is False, "Deve falhar em 400"
        assert mock_patch.call_count == 1, "Não deve retry em 400"

    print("✅ Teste 6 PASSOU: Retry logic correto")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
