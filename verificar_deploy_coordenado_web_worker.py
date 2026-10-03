"""
Diagnóstico (somente leitura) de divergência de deploy entre o serviço
web e o worker Celery no Render.

Por que existe: o worker (`srv-d9f4gipkh4rs73d4h7ug`) importa funções
de `app.py` (`construir_mapa_cpf`, `extrair_pdf_colaborador`) -- ou
seja, o comportamento do processamento assíncrono de PDF depende da
versão de `app.py` que está de fato rodando em cada serviço. Hoje o
worker tem `autoDeploy: yes` (deploya a cada commit em `main`) e o web
tem `autoDeploy: no` (deploy manual, proteção deliberada do legado --
CLAUDE.md §7). Isso significa que o worker pode estar rodando um
`app.py` mais novo que o web sem ninguém notar, até o dia em que uma
mudança nessas funções compartilhadas criar comportamento inconsistente
entre os dois serviços.

Este script só DETECTA e relata a divergência (commit de cada serviço
e se `app.py` -- o único arquivo de fato compartilhado -- mudou entre
eles) -- não dispara deploy nem altera nenhuma configuração. Ação
sobre o Render (deploy, toggle de autoDeploy) é gate de produção
(CLAUDE.md §6/§12-I) e fica com quem já é dono do domínio de deploy
via API do Render nesta rodada.

Uso: python3 verificar_deploy_coordenado_web_worker.py
Requer RENDER_API_KEY no ambiente e `git` disponível (para comparar
commits -- roda a partir de um checkout do repositório).
"""
from __future__ import annotations

import os
import subprocess
import sys

import requests

RENDER_API_KEY = os.environ.get('RENDER_API_KEY', '')
SRV_WEB = 'srv-d8iqj3uk1jcs73ap1np0'
SRV_WORKER = 'srv-d9f4gipkh4rs73d4h7ug'
# Só app.py é de fato compartilhado entre os dois serviços -- o worker
# importa `construir_mapa_cpf`/`extrair_pdf_colaborador` dele
# (tarefas_processar_pdf.py). `tarefas_processar_pdf.py` e
# `celery_app.py` são exclusivos do worker (o web nunca os importa),
# então uma mudança neles não é risco de inconsistência entre os dois
# serviços -- é só o worker redesplayando sozinho, o que já é esperado
# dado o autoDeploy dele.
ARQUIVOS_COMPARTILHADOS_COM_WORKER = ('app.py',)


def _headers() -> dict:
    # Em ambientes com RENDER_API_KEY real no ambiente, envia o Bearer
    # explícito. Em sessões onde um proxy já injeta a credencial de forma
    # transparente nas chamadas HTTPS para api.render.com (RENDER_API_KEY
    # nunca aparece como variável de ambiente literal nesse caso), não
    # envia header nenhum -- um Authorization vazio/forjado poderia
    # conflitar com a injeção do proxy.
    return {'Authorization': f'Bearer {RENDER_API_KEY}'} if RENDER_API_KEY else {}


def _ultimo_deploy_live(service_id: str) -> dict | None:
    r = requests.get(
        f'https://api.render.com/v1/services/{service_id}/deploys',
        headers=_headers(),
        params={'limit': 20},
        timeout=30,
    )
    r.raise_for_status()
    for item in r.json():
        dep = item['deploy']
        if dep['status'] == 'live':
            return dep
    return None


def _commits_entre(sha_antigo: str, sha_novo: str) -> list[str]:
    """Lista arquivos tocados entre dois commits (requer checkout local com histórico)."""
    try:
        out = subprocess.run(
            ['git', 'log', '--name-only', '--pretty=format:', f'{sha_antigo}..{sha_novo}'],
            capture_output=True, text=True, check=True,
        )
        return [linha.strip() for linha in out.stdout.splitlines() if linha.strip()]
    except subprocess.CalledProcessError:
        return []


def main() -> int:
    try:
        web = _ultimo_deploy_live(SRV_WEB)
        worker = _ultimo_deploy_live(SRV_WORKER)
    except requests.RequestException as e:
        print(f'ERRO ao consultar a API do Render: {type(e).__name__}: {e}', file=sys.stderr)
        print(
            'Confirme RENDER_API_KEY no ambiente (ou que a sessão tem um proxy '
            'que injeta a credencial para api.render.com).',
            file=sys.stderr,
        )
        return 1

    if not web or not worker:
        print('Não foi possível obter o último deploy live de um dos dois serviços.')
        return 1

    sha_web = web['commit']['id']
    sha_worker = worker['commit']['id']

    print(f'Web    -- live desde {web["updatedAt"]}: {sha_web}')
    print(f'Worker -- live desde {worker["updatedAt"]}: {sha_worker}')

    if sha_web == sha_worker:
        print('OK: web e worker estão no mesmo commit.')
        return 0

    arquivos = set(_commits_entre(sha_web, sha_worker)) | set(_commits_entre(sha_worker, sha_web))
    compartilhados_tocados = [a for a in arquivos if a in ARQUIVOS_COMPARTILHADOS_COM_WORKER]

    print(f'\nDIVERGÊNCIA: web e worker estão em commits diferentes.')
    if compartilhados_tocados:
        print(
            f'RISCO REAL: app.py mudou entre os dois commits -- web e worker podem estar '
            f'executando funções compartilhadas (construir_mapa_cpf/extrair_pdf_colaborador) '
            f'em versões diferentes agora.'
        )
        return 2
    else:
        print(
            'app.py não mudou entre os dois commits -- a divergência existe (o worker está '
            'em commit mais novo, esperado dado seu autoDeploy), mas sem risco de '
            'inconsistência comportamental conhecido, já que o único arquivo de fato '
            'compartilhado com o web não foi alterado nesse intervalo.'
        )
        return 0


if __name__ == '__main__':
    sys.exit(main())
