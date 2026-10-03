"""
Reconciliação manual de registros presos em Status='Processando' na
tabela Processar Arquivos (fila de separação de PDF por Celery).

Por que este script existe: o broker/result backend do Celery é um
Redis de produção no plano `free` do Render, sem persistência
(achado da Frente E "infra e operação 24x7", 2026-10-03 --
ver /mnt/project-files/magnata-os/infra-operacao-24x7.md). Se esse
Redis reiniciar com uma tarefa em andamento, a fila em memória é
perdida -- nem `task_acks_late`, nem o `autoretry_for` do Celery
alcançam esse caso, porque os dois dependem do próprio broker
sobreviver para redespachar. A única forma de saber que algo ficou
travado é olhar a fonte de verdade real (Airtable, campo Status),
não o Celery.

Regra pétrea (mesmo princípio de
`magnata_os/orquestrador/reconciliacao_execucao_orfa.py`:
"worker morto ≠ mensagem não enviada"): esta reconciliação NUNCA roda
por scheduler, cron ou timeout automático -- só por invocação manual
explícita de um humano. Por padrão só LISTA (nenhuma escrita); reenviar
para a fila exige a flag `--reenfileirar` explicitamente. Diferente do
domínio do orquestrador (que lida com envio externo real e por isso
proíbe reenvio automático até nesse script manual), aqui o efeito de
rodar a task de novo é interno e sobrescreve os mesmos campos Airtable
(Status/Data) -- por isso o reenfileiramento manual é seguro, mas segue
exigindo decisão humana explícita por design, não por timeout.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY', '')
BASE_ID = 'appaCpIVj7Q97VhFy'
TABLE_PROCESSAR = 'tblXaLXvGJMyFOayc'
F_PROC_STATUS = 'fldvN9T5MiuKZGDi0'
F_PROC_DATA = 'flddNzmqp1Im1D02m'

MINUTOS_LIMITE_DEFAULT = 30  # bem acima de task_time_limit=900s (15min)


def listar_travados(minutos_limite: int = MINUTOS_LIMITE_DEFAULT) -> list[dict]:
    """
    Lista registros de Processar Arquivos com Status='Processando' há
    mais de `minutos_limite` minutos. Não usa filterByFormula (o nome de
    exibição real dos campos F_PROC_STATUS/F_PROC_DATA não está
    confirmado neste repositório) -- pagina via returnFieldsByFieldId e
    filtra em Python pelos IDs de campo já conhecidos, igual ao padrão
    de `tarefas_processar_pdf.py`.
    """
    limite = datetime.now(timezone.utc) - timedelta(minutes=minutos_limite)
    travados: list[dict] = []
    offset = None
    paginas = 0

    while paginas < 20:  # trava de segurança -- tabela não deveria ter milhares de registros presos
        params = {'returnFieldsByFieldId': 'true', 'pageSize': 100}
        if offset:
            params['offset'] = offset

        r = requests.get(
            f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_PROCESSAR}',
            headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()

        for rec in data.get('records', []):
            fields = rec.get('fields', {})
            if fields.get(F_PROC_STATUS) != 'Processando':
                continue
            data_str = fields.get(F_PROC_DATA)
            if not data_str:
                continue
            try:
                data_proc = datetime.fromisoformat(data_str)
                if data_proc.tzinfo is None:
                    data_proc = data_proc.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if data_proc < limite:
                travados.append({
                    'record_id': rec['id'],
                    'processando_desde': data_str,
                    'fields': fields,
                })

        offset = data.get('offset')
        paginas += 1
        if not offset:
            break

    return travados


def reenfileirar(record_id: str, pdf_url: str | None) -> str:
    """Reenfileira a mesma task Celery para `record_id`. Idempotente no
    destino: `processar_pdf_task` agora verifica o Status atual no início
    e ignora se já estiver 'Concluído' (ver tarefas_processar_pdf.py)."""
    from tarefas_processar_pdf import gerar_idempotency_key, processar_pdf_task

    pdf_hash = ''  # reenfileiramento manual não tem o PDF em mãos para hashear de novo
    idempotency_key = gerar_idempotency_key(record_id, pdf_hash)
    task = processar_pdf_task.apply_async(args=(record_id, idempotency_key, pdf_url))
    return task.id


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minutos-limite', type=int, default=MINUTOS_LIMITE_DEFAULT)
    parser.add_argument('--reenfileirar', action='store_true',
                         help='Sem esta flag, só lista (dry-run). Com ela, reenfileira cada travado encontrado.')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if not AIRTABLE_API_KEY:
        print('ERRO: AIRTABLE_API_KEY não configurada no ambiente.', file=sys.stderr)
        return 1

    travados = listar_travados(args.minutos_limite)

    if not travados:
        print(f'Nenhum registro travado em Processando há mais de {args.minutos_limite} minutos.')
        return 0

    print(f'{len(travados)} registro(s) travado(s) em Processando há mais de {args.minutos_limite} minutos:')
    for item in travados:
        print(f"  - {item['record_id']} (desde {item['processando_desde']})")

    if not args.reenfileirar:
        print('\nDry-run (padrão) -- nenhuma tarefa reenfileirada. Use --reenfileirar para reenviar.')
        return 0

    print('\nReenfileirando...')
    for item in travados:
        pdf_url = (item['fields'].get('fldQtevv6jAwKVdEN') or [{}])[0].get('url') if item['fields'].get('fldQtevv6jAwKVdEN') else None
        task_id = reenfileirar(item['record_id'], pdf_url)
        print(f"  - {item['record_id']} -> task_id={task_id}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
