"""
Tarefas Celery para processamento assíncrono de PDFs.
Versão: 1.0 (2026-07-20)
"""

import os
import logging
import hashlib
import requests
from datetime import datetime
from celery_app import celery_app

logger = logging.getLogger(__name__)

AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY', '')
BASE_ID = 'appaCpIVj7Q97VhFy'
TABLE_PROCESSAR = 'tblXaLXvGJMyFOayc'
F_PROC_STATUS = 'fldvN9T5MiuKZGDi0'
F_PROC_DATA = 'flddNzmqp1Im1D02m'
F_PROC_TIPO_DOC = 'fldvkOVlwCMywGTEs'

# Import das funções de processamento do app.py
from app import construir_mapa_cpf, extrair_pdf_colaborador, logger as app_logger


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={'max_retries': 3},
)
def processar_pdf_task(
    self,
    processar_arquivo_record_id: str,
    idempotency_key: str | None = None,
    pdf_url: str | None = None,
) -> dict:
    """
    Processa PDF de forma assíncrona.

    Args:
        processar_arquivo_record_id: ID do registro no Airtable (começa com 'rec')
        idempotency_key: Chave de idempotência (SHA256 de record_id + pdf hash)
        pdf_url: URL do anexo no Airtable (para download)

    Returns:
        dict com resultado do processamento
    """

    logger.info(f'[TASK] Iniciando: {processar_arquivo_record_id} | task_id={self.request.id}')
    inicio = datetime.now()

    try:
        # Validar Record ID
        if not processar_arquivo_record_id or not processar_arquivo_record_id.startswith('rec'):
            logger.error(f'[TASK] Record ID inválido: {processar_arquivo_record_id}')
            return {
                'success': False,
                'error_code': 'INVALID_RECORD_ID',
                'message': 'ID do registro inválido',
            }

        # Atualizar status para "Processando"
        _atualizar_airtable(
            processar_arquivo_record_id,
            {
                F_PROC_STATUS: 'Processando',
            }
        )
        logger.info(f'[TASK] Status → Processando | {processar_arquivo_record_id}')

        # Baixar PDF do Airtable
        if not pdf_url:
            logger.error(f'[TASK] PDF URL não fornecida')
            _atualizar_airtable(
                processar_arquivo_record_id,
                {
                    F_PROC_STATUS: 'Erro',
                    F_PROC_TIPO_DOC: 'PDF_URL_MISSING',
                    F_PROC_DATA: datetime.now().isoformat(),
                }
            )
            return {
                'success': False,
                'error_code': 'PDF_URL_MISSING',
                'message': 'URL do PDF não disponível',
            }

        # Baixar arquivo
        logger.info(f'[TASK] Baixando PDF: {pdf_url[:50]}...')
        try:
            resp = requests.get(pdf_url, timeout=60)
            resp.raise_for_status()
            pdf_bytes = resp.content
        except Exception as e:
            logger.error(f'[TASK] Erro download PDF: {type(e).__name__}: {str(e)[:200]}')
            _atualizar_airtable(
                processar_arquivo_record_id,
                {
                    F_PROC_STATUS: 'Erro',
                    F_PROC_TIPO_DOC: 'PDF_DOWNLOAD_FAILED',
                    F_PROC_DATA: datetime.now().isoformat(),
                }
            )
            return {
                'success': False,
                'error_code': 'PDF_DOWNLOAD_FAILED',
                'message': f'Erro ao baixar PDF: {type(e).__name__}',
            }

        # Processar PDF (usar funções existentes)
        logger.info(f'[TASK] Processando PDF ({len(pdf_bytes)} bytes)')

        # Salvar temporariamente para processar
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            mapa, total_paginas = construir_mapa_cpf(tmp_path)

            if not mapa:
                logger.warning(f'[TASK] Nenhum CPF encontrado no PDF')
                _atualizar_airtable(
                    processar_arquivo_record_id,
                    {
                        F_PROC_STATUS: 'Erro',
                        F_PROC_TIPO_DOC: 'EMPLOYEE_NOT_IDENTIFIED',
                        F_PROC_DATA: datetime.now().isoformat(),
                    }
                )
                return {
                    'success': False,
                    'error_code': 'EMPLOYEE_NOT_IDENTIFIED',
                    'message': 'Nenhum funcionário/CPF encontrado no PDF',
                }

            # Extrair PDFs individuais
            funcionarios = []
            for cpf, dados in mapa.items():
                pdf_ind = extrair_pdf_colaborador(tmp_path, dados['paginas'])
                funcionarios.append({
                    'cpf': cpf,
                    'nome': dados['nome'],
                    'tamanho_bytes': len(pdf_ind),
                })

            logger.info(f'[TASK] PDF processado: {len(funcionarios)} funcionários')

            # Sucesso!
            duracao = (datetime.now() - inicio).total_seconds()
            _atualizar_airtable(
                processar_arquivo_record_id,
                {
                    F_PROC_STATUS: 'Concluído',
                    F_PROC_DATA: datetime.now().isoformat(),
                }
            )

            logger.info(f'[TASK] Concluído em {duracao:.1f}s | {processar_arquivo_record_id}')

            return {
                'success': True,
                'total_funcionarios': len(funcionarios),
                'duracao_segundos': duracao,
            }

        finally:
            # Limpar arquivo temporário
            import os as os_module
            try:
                os_module.unlink(tmp_path)
            except Exception as e:
                logger.warning(f'[TASK] Erro ao limpar temp: {e}')

    except Exception as exc:
        logger.exception(f'[TASK] Erro inesperado: {type(exc).__name__}')
        _atualizar_airtable(
            processar_arquivo_record_id,
            {
                F_PROC_STATUS: 'Erro',
                F_PROC_TIPO_DOC: 'PROCESSING_ERROR',
                F_PROC_DATA: datetime.now().isoformat(),
            }
        )
        return {
            'success': False,
            'error_code': 'PROCESSING_ERROR',
            'message': f'{type(exc).__name__}: erro ao processar',
        }


def _atualizar_airtable(record_id: str, campos: dict) -> bool:
    """
    Atualiza registro no Airtable de forma segura.

    Returns:
        True se sucesso, False se erro
    """
    try:
        r = requests.patch(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_PROCESSAR}/{record_id}',
            headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
            json={'fields': campos, 'typecast': True},
            timeout=30,
        )

        if r.status_code in (200, 201, 204):
            logger.info(f'[AIRTABLE] Atualizado: {record_id}')
            return True
        else:
            logger.error(f'[AIRTABLE] Erro {r.status_code}: {r.text[:200]}')
            return False

    except Exception as e:
        logger.error(f'[AIRTABLE] Erro ao atualizar: {type(e).__name__}: {str(e)[:200]}')
        return False


def gerar_idempotency_key(record_id: str, pdf_hash: str) -> str:
    """
    Gera chave de idempotência SHA256 baseada em record_id + pdf_hash.

    Args:
        record_id: ID do registro Airtable
        pdf_hash: SHA256 do arquivo PDF

    Returns:
        str: Chave SHA256
    """
    chave = f'{record_id}:{pdf_hash}'
    return hashlib.sha256(chave.encode()).hexdigest()
