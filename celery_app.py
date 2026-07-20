"""
Celery configuration para processamento assíncrono de PDFs.
Versão: 1.0 (2026-07-20)
"""

import os
from celery import Celery

# Obter URL do Redis (Render Key Value ou local)
redis_url = os.environ.get('REDIS_URL', os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'))

# Criar aplicativo Celery
celery_app = Celery(
    'magnata_holerites',
    broker=redis_url,
    backend=redis_url,
    include=['tarefas_processar_pdf'],
)

# Configuração obrigatória
celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='America/Sao_Paulo',
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_soft_time_limit=600,  # 10 minutos
    task_time_limit=900,  # 15 minutos (hard limit)
)

# Importar tasks APÓS a instância Celery estar criada
try:
    from tarefas_processar_pdf import processar_pdf_task  # noqa: F401
except ImportError:
    pass
