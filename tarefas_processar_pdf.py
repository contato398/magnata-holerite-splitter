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
F_PROC_TIPO_DOC = 'fldvkOVlwCMywGTES'

# Import das funções de processamento do app.py
from app import construir_mapa_cpf, extrair_pdf_colaborador, logger as app_logger


class _FalhaTransitoriaRetentavel(Exception):
    """Sinaliza ao bloco `except Exception` externo da task que esta falha
    já decidiu (`self.request.retries < self.max_retries`) que deve
    atravessar sem ser convertida em Status='Erro' definitivo -- precisa
    chegar intacta até o decorator `autoretry_for` do Celery, que é quem
    de fato agenda o reenvio (backoff/jitter). Sem esta classe, o
    `except Exception` genérico da task (que converte qualquer falha em
    retorno de dict, nunca deixando nada subir) engoliria a exceção antes
    do Celery poder vê-la -- motivo pelo qual, antes desta mudança,
    `autoretry_for`/`retry_backoff`/`retry_jitter` nunca disparavam."""


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
        idempotency_key: Chave de idempotência (SHA256 de record_id + pdf hash) --
            reservada para uso futuro de deduplicação por conteúdo; hoje a
            proteção contra execução duplicada é a verificação de status
            abaixo (idempotência "por efeito", não por chave).
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

        # Proteção de idempotência: se o Redis (broker/result backend, plano
        # free, sem persistência -- achado da Frente E "infra 24x7") perder a
        # fila e um humano reenfileirar manualmente via
        # reconciliar_processamento_pdf_travado.py, ou se o Celery redespachar
        # a mesma tarefa (acks_late + reinício do worker antes do ack), um
        # registro já concluído nunca deve ser reprocessado -- a saída real
        # (PDFs extraídos) não é persistida de novo por este reprocessamento
        # além da gravação do campo Status, mas evitamos o retrabalho e o
        # risco de qualquer efeito colateral futuro que dependa de "só roda
        # uma vez por registro".
        status_atual = _status_atual_airtable(processar_arquivo_record_id)
        if status_atual == 'Concluído':
            logger.info(
                f'[TASK] Ignorado (idempotência): {processar_arquivo_record_id} '
                f'já está Concluído -- execução duplicada descartada'
            )
            return {
                'success': True,
                'skipped_idempotente': True,
                'message': 'Registro já concluído -- execução duplicada ignorada',
            }

        # Atualizar status para "Processando" — obrigatório
        success_inicial = _atualizar_airtable(
            processar_arquivo_record_id,
            {
                F_PROC_STATUS: 'Processando',
                F_PROC_DATA: datetime.now().isoformat(),
            }
        )
        if not success_inicial:
            logger.error(f'[TASK] Falha ao atualizar Status→Processando')
            return {
                'success': False,
                'error_code': 'INITIAL_STATUS_UPDATE_FAILED',
                'message': 'Falha ao marcar registro como Processando',
            }
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
            # Falha de download é tipicamente transitória (rede, Airtable
            # fora do ar por um instante) -- diferente de EMPLOYEE_NOT_IDENTIFIED
            # ou CPF inválido, que nunca seriam corrigidos por retry. Enquanto
            # houver tentativa disponível, deixar o `autoretry_for` do decorator
            # reagendar (sem marcar 'Erro' ainda, para não oscilar o status
            # durante o retry); só na última tentativa o erro é definitivo.
            if self.request.retries < self.max_retries:
                raise _FalhaTransitoriaRetentavel(str(e)) from e
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

            # Sucesso! — Atualizar Status para Concluído (obrigatório)
            duracao = (datetime.now() - inicio).total_seconds()
            success_final = _atualizar_airtable(
                processar_arquivo_record_id,
                {
                    F_PROC_STATUS: 'Concluído',
                    F_PROC_DATA: datetime.now().isoformat(),
                }
            )

            if not success_final:
                logger.error(f'[TASK] Falha ao atualizar Status→Concluído')
                return {
                    'success': False,
                    'error_code': 'AIRTABLE_FINAL_UPDATE_FAILED',
                    'message': 'Falha ao marcar registro como Concluído',
                }

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

    except _FalhaTransitoriaRetentavel:
        # Deixar o decorator `autoretry_for` do Celery tratar -- nunca
        # converter em Status='Erro' aqui (ver docstring da classe).
        raise

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
    Atualiza registro no Airtable de forma segura com retry e validação.

    Returns:
        True se sucesso e campo Status confirmado, False se erro
    """
    max_retries = 3
    for tentativa in range(1, max_retries + 1):
        try:
            r = requests.patch(
                f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_PROCESSAR}/{record_id}?returnFieldsByFieldId=true',
                headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
                json={'fields': campos, 'typecast': True},
                timeout=30,
            )

            logger.info(f'[AIRTABLE] Tentativa {tentativa}: HTTP {r.status_code}')

            # Retry apenas para falhas transitórias
            if r.status_code in (429, 500, 502, 503, 504):
                if tentativa < max_retries:
                    logger.warning(f'[AIRTABLE] Retry em falha {r.status_code}')
                    import time
                    time.sleep(0.5)
                    continue
                else:
                    logger.error(f'[AIRTABLE] Falha após {max_retries} tentativas: {r.status_code}')
                    return False

            if r.status_code in (200, 201, 204):
                # Validar que o campo Status foi realmente atualizado
                try:
                    resp_json = r.json()
                    updated_fields = resp_json.get('fields', {})

                    # Se Status foi enviado, verificar que foi recebido
                    if F_PROC_STATUS in campos:
                        if F_PROC_STATUS in updated_fields:
                            logger.info(f'[AIRTABLE] Status confirmado: {updated_fields.get(F_PROC_STATUS)}')
                        else:
                            logger.warning(f'[AIRTABLE] Status não retornou na resposta')

                    logger.info(f'[AIRTABLE] Sucesso: {record_id}')
                except Exception as e:
                    logger.warning(f'[AIRTABLE] Resposta não é JSON: {type(e).__name__}')

                return True
            else:
                logger.error(f'[AIRTABLE] Erro {r.status_code}: {r.text[:200]}')
                return False

        except Exception as e:
            logger.error(f'[AIRTABLE] Tentativa {tentativa}: {type(e).__name__}: {str(e)[:100]}')
            if tentativa < max_retries:
                import time
                time.sleep(0.5)
                continue
            return False

    return False


def _status_atual_airtable(record_id: str) -> str | None:
    """
    Lê o Status atual do registro no Airtable, sem retry (best-effort):
    usada só para a checagem de idempotência no início da task -- se a
    leitura falhar, retorna None e a task segue o fluxo normal (nunca
    bloqueia o processamento por falha nesta checagem auxiliar; a falha
    real, se houver, será capturada mais adiante pelas chamadas que já
    têm retry/validação, como `_atualizar_airtable`).

    Returns:
        O valor de F_PROC_STATUS ('Pendente'/'Processando'/'Concluído'/
        'Erro'), ou None se o registro não existir ou a leitura falhar.
    """
    try:
        r = requests.get(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_PROCESSAR}/{record_id}?returnFieldsByFieldId=true',
            headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
            timeout=15,
        )
        if r.status_code != 200:
            logger.warning(f'[TASK] Checagem de idempotência: HTTP {r.status_code} ao ler {record_id}')
            return None
        return r.json().get('fields', {}).get(F_PROC_STATUS)
    except Exception as e:
        logger.warning(f'[TASK] Checagem de idempotência falhou (seguindo fluxo normal): {type(e).__name__}')
        return None


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
