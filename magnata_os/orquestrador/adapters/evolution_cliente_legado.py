"""Cliente Evolution API legado — extraído mecanicamente de `app.py`
(missão "IMPLEMENTAÇÃO LOCAL CONTROLADA — EXTRAÇÃO EVOLUTION + CANÁRIO
NOMINAL V1").

Extração MECÂNICA, não uma reescrita: `EVOLUTION_API_URL`,
`EVOLUTION_INSTANCE`, `EVOLUTION_API_KEY` e as 3 funções
`_evolution_enviar_texto`/`_evolution_enviar_video`/
`_evolution_enviar_documento` têm aqui exatamente o mesmo corpo, mesmos
payloads, mesma autenticação, mesmos endpoints e mesmo tratamento de
resposta/erro que tinham em `app.py` — nenhuma linha de lógica mudou.
`app.py` agora importa esses mesmos nomes deste módulo (ver comentário
em `app.py` no ponto da extração).

Por que este módulo existe: as 3 funções não dependem de Flask, sessão
(`configurar_sessao_segura`), Airtable nem de nenhum outro estado de
`app.py` -- só de `requests`/`base64`/`os` e das 3 constantes acima.
Extraí-las permite compor `TransporteEvolutionLegado`
(`transporte_evolution_legado.py`) num processo que nunca precisa
importar `app.py` inteiro (e, com isso, nunca precisa de
`MAGNATA_SESSION_SECRET_KEY`, que não tem nenhuma relação com
Evolution/WhatsApp) -- gap identificado e fechado pela missão
"FECHAMENTO FINAL DO BLOCKER DE COMPOSIÇÃO EVOLUTION".

Nenhuma dependência de Flask/Airtable/sessão neste módulo -- mesma
disciplina de `magnata_os/CLAUDE.md` ("todo serviço externo entra por
adapter... nunca importa o driver por nome dentro do domínio")."""
from __future__ import annotations

import base64
import os

import requests

# Evolution API (gateway WhatsApp) — v2.28. URL e instância não são
# segredo (default embutido, preservado idêntico ao de app.py); a API
# KEY é secreta e DEVE vir por variável de ambiente.
EVOLUTION_API_URL = os.environ.get('EVOLUTION_API_URL', 'http://143.95.214.239:8080').rstrip('/')
EVOLUTION_INSTANCE = os.environ.get('EVOLUTION_INSTANCE', 'magnata')
EVOLUTION_API_KEY = os.environ.get('EVOLUTION_API_KEY', '')


def _evolution_enviar_texto(numero: str, texto: str):
    """Envia 1 mensagem de texto puro via Evolution API v2 (sendText) — usado
    para o link de Assinatura Nativa (sem custo extra, mesma instância já
    configurada para o envio de holerites)."""
    endpoint = f'{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}'
    payload = {'number': numero, 'text': texto}
    r = requests.post(
        endpoint,
        headers={'apikey': EVOLUTION_API_KEY, 'Content-Type': 'application/json'},
        json=payload,
        timeout=90,
    )
    if not (200 <= r.status_code < 300):
        raise RuntimeError(f'Evolution HTTP {r.status_code}: {r.text[:300]}')
    return r.json()


def _evolution_enviar_video(numero: str, video_base64: str, nome_arquivo: str, legenda: str = ''):
    """Envia um MP4 já validado como base64 pela Evolution API, com legenda opcional."""
    endpoint = f'{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE}'
    payload = {
        'number': numero,
        'mediatype': 'video',
        'mimetype': 'video/mp4',
        'media': video_base64,
        'fileName': nome_arquivo,
    }
    if legenda:
        payload['caption'] = legenda
    resposta = requests.post(
        endpoint,
        headers={'apikey': EVOLUTION_API_KEY, 'Content-Type': 'application/json'},
        json=payload,
        timeout=90,
    )
    if not (200 <= resposta.status_code < 300):
        raise RuntimeError(f'Evolution HTTP {resposta.status_code}')
    return resposta.json()


def _evolution_enviar_documento(numero: str, media_url: str, filename: str, caption=None,
                                 media_bytes: bytes = None):
    """
    Envia 1 documento (PDF) via Evolution API v2 (sendMedia).

    Por padrão manda 'media' como URL (Evolution busca o arquivo). Se
    media_bytes for informado, manda em base64 embutido no payload —
    mais confiável: elimina a etapa em que a própria Evolution API busca
    a URL (CloudFront/S3 do Airtable) por conta própria, etapa em que já
    foi observado em produção (08/07/2026) entrega de PDF corrompido/
    incompleto para uma minoria dos destinatários ("Erro de formato de
    arquivo" no WhatsApp), mesmo com o arquivo de origem íntegro
    (confirmado por download e validação direta do mesmo PDF).
    """
    endpoint = f'{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE}'
    payload = {
        'number': numero,
        'mediatype': 'document',
        'mimetype': 'application/pdf',
        'media': base64.b64encode(media_bytes).decode('utf-8') if media_bytes else media_url,
        'fileName': filename,
    }
    if caption:
        payload['caption'] = caption
    r = requests.post(
        endpoint,
        headers={'apikey': EVOLUTION_API_KEY, 'Content-Type': 'application/json'},
        json=payload,
        timeout=90,
    )
    if not (200 <= r.status_code < 300):
        raise RuntimeError(f'Evolution HTTP {r.status_code}: {r.text[:300]}')
    return r.json()
