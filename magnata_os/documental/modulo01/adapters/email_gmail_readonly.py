"""
Cliente Gmail real (Modulo 01 -- Fase 1 do modo sombra de captura de
e-mail, ver docs/decisoes/plano-modo-sombra-captura-email.md).

INERTE POR DESENHO -- nesta fase, nenhum teste deste modulo carrega
credencial real, faz chamada de rede ou acessa uma caixa de e-mail de
verdade. As UNICAS duas funcoes que falariam com o Gmail de verdade
(`carregar_credenciais_gmail_readonly` com um token real, e
`construir_recurso_gmail`) nunca sao chamadas por nenhum teste, nem por
nenhum outro modulo do repositorio hoje -- so seriam exercitadas se
alguem, numa Fase 2 futura, instanciasse `ClienteGmailReadOnly` com uma
credencial de verdade E sem injetar `construir_recurso` de teste. Ligar
isto a um Gmail real e Fase 2 do plano citado acima -- GATE HUMANO,
autorizacao de fase completa (CLAUDE.md paragrafo 6a-f). Nenhuma resposta
ambigua autoriza essa fase.

Escopo OAuth travado em codigo para *readonly* -- nao existe parametro
que amplie para gmail.modify ou superior (ver ESCOPOS_READONLY). Este
cliente so chama endpoints de LEITURA da API Gmail:
`users().labels().list`, `users().messages().list`,
`users().messages().get`, `users().messages().attachments().get`. Nenhum
metodo de escrita (`modify`, `trash`, `delete`, `send`, `batchModify`,
`labels().create/update/delete`) e sequer referenciado neste arquivo --
test_magnata_os_documental_modulo01_email_gmail_readonly.py prova isso
usando um recurso-duplo que so implementa os 4 metodos de leitura acima
(qualquer outro metodo levanta AttributeError no proprio duplo).

Implementa o `FonteMensagensEmail` (Protocol) ja definido em
email_captura.py -- mesmo padrao de qualquer adapter novo deste pacote
(ver magnata_os/CLAUDE.md, "todo servico externo entra por adapter").

Import de `googleapiclient`/`google.oauth2` e sempre local (dentro da
funcao que precisa), nunca no topo do arquivo -- mesmo padrao ja usado
em adapters/conexao.py para psycopg: importar este modulo nunca exige as
bibliotecas do Google instaladas; so construir um recurso real exige.
"""
from __future__ import annotations

import base64
import dataclasses
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional, Sequence

from .email_captura import AnexoEmailRecebido, MensagemEmailRecebida

# Travado em codigo -- nunca ampliado por parametro ou configuracao de
# ambiente. Ver docs/decisoes/plano-modo-sombra-captura-email.md Fase 0.
ESCOPOS_READONLY = ('https://www.googleapis.com/auth/gmail.readonly',)


class CredencialGmailAusente(Exception):
    """Nao ha credencial de Gmail configurada. Falha alto e claro -- nunca
    retorna um cliente sem autenticacao real (CLAUDE.md paragrafo 4,
    "falha nunca e silenciosa")."""


class LabelGmailNaoEncontrada(Exception):
    """A label configurada nao existe na caixa consultada."""


def carregar_credenciais_gmail_readonly(caminho_token: Optional[str] = None) -> Any:
    """
    Carrega uma credencial OAuth REAL de escopo *readonly*, a partir de um
    arquivo de token ja emitido (`google.oauth2.credentials.Credentials`
    via `from_authorized_user_file`). Nao existe fluxo de autorizacao
    interativa aqui (nenhum `InstalledAppFlow`) -- emitir o token e
    responsabilidade de fora deste modulo, na Fase 2, sob autorizacao de
    fase.

    Levanta `CredencialGmailAusente` se `caminho_token` nao for informado
    -- nunca tenta um caminho default silencioso (ex.: variavel de
    ambiente implicita). Nenhum teste deste modulo chama esta funcao com
    um caminho real.
    """
    if not caminho_token:
        raise CredencialGmailAusente(
            'Nenhum caminho de token informado -- Fase 1 do modo sombra '
            'nao acessa Gmail real. Ver '
            'docs/decisoes/plano-modo-sombra-captura-email.md Fase 2.'
        )
    from google.oauth2.credentials import Credentials  # import local -- ver docstring do modulo

    return Credentials.from_authorized_user_file(caminho_token, list(ESCOPOS_READONLY))


def construir_recurso_gmail(credenciais: Any) -> Any:
    """Constroi o recurso `googleapiclient` real da API Gmail v1 a partir
    de uma credencial ja carregada. `static_discovery=True` evita
    depender de rede so para buscar o documento de descoberta da API --
    mesmo assim, as chamadas feitas pelo recurso construido aqui (list/
    get) continuam sendo rede real. Nenhum teste deste modulo chama esta
    funcao -- todo teste injeta um recurso-duplo via `construir_recurso`
    do `ClienteGmailReadOnly`."""
    from googleapiclient.discovery import build  # import local -- ver docstring do modulo

    return build('gmail', 'v1', credentials=credenciais, cache_discovery=False, static_discovery=True)


def _cabecalho(headers: Sequence[dict], nome: str) -> str:
    for h in headers:
        if h.get('name', '').lower() == nome.lower():
            return h.get('value', '')
    return ''


def _data_recebimento(detalhe: dict) -> datetime:
    internal_date_ms = detalhe.get('internalDate')
    if internal_date_ms is None:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(int(internal_date_ms) / 1000, tz=timezone.utc)


def _extrair_anexos(recurso: Any, message_id: str, partes: Sequence[dict]) -> List[AnexoEmailRecebido]:
    """So le corpo de anexo via `attachments().get` (leitura) -- nunca um
    metodo de escrita. Parte sem `filename` nao e anexo (ex.: corpo de
    texto/html da mensagem) e e ignorada aqui, sem erro -- o corpo da
    mensagem em si nao e usado por este cliente."""
    anexos: List[AnexoEmailRecebido] = []
    for parte in partes:
        nome = parte.get('filename') or ''
        if not nome:
            continue

        corpo = parte.get('body', {}) or {}
        if corpo.get('attachmentId'):
            resposta = (
                recurso.users()
                .messages()
                .attachments()
                .get(userId='me', messageId=message_id, id=corpo['attachmentId'])
                .execute()
            )
            dado_b64 = resposta.get('data', '')
        else:
            dado_b64 = corpo.get('data', '')

        conteudo = (
            base64.urlsafe_b64decode(dado_b64 + '=' * (-len(dado_b64) % 4))
            if dado_b64
            else b''
        )
        anexos.append(
            AnexoEmailRecebido(
                nome_original=nome,
                mime_type=parte.get('mimeType', 'application/octet-stream'),
                conteudo=conteudo,
            )
        )
    return anexos


class ClienteGmailReadOnly:
    """
    Implementa `FonteMensagensEmail` (email_captura.py) contra a API
    Gmail real -- SO LEITURA. Filtra por uma label dedicada (Fase 0 do
    plano de modo sombra -- opcao recomendada), nunca aplica nem remove
    label, nunca chama `/email/webhook`, nunca escreve em nada.

    `construir_recurso` e injetavel -- por padrao aponta para
    `construir_recurso_gmail` (real), mas todo teste deste modulo injeta
    um duplo que nunca faz rede nem importa `googleapiclient`. Nenhum
    teste passa uma credencial real nem deixa o default ser exercitado.
    """

    def __init__(
        self,
        label: str,
        credenciais: Any,
        construir_recurso: Callable[[Any], Any] = construir_recurso_gmail,
    ) -> None:
        self._label = label
        self._recurso = construir_recurso(credenciais)

    def _resolver_id_label(self) -> str:
        resposta = self._recurso.users().labels().list(userId='me').execute()
        for label in resposta.get('labels', []):
            if label.get('name') == self._label:
                return label['id']
        raise LabelGmailNaoEncontrada(
            f'Label "{self._label}" nao encontrada na caixa consultada.'
        )

    def buscar_novas_mensagens(self) -> Sequence[MensagemEmailRecebida]:
        label_id = self._resolver_id_label()
        resposta = (
            self._recurso.users()
            .messages()
            .list(userId='me', labelIds=[label_id])
            .execute()
        )

        mensagens: List[MensagemEmailRecebida] = []
        for item in resposta.get('messages', []) or []:
            detalhe = (
                self._recurso.users()
                .messages()
                .get(userId='me', id=item['id'], format='full')
                .execute()
            )
            payload = detalhe.get('payload', {}) or {}
            headers = payload.get('headers', []) or []
            partes = payload.get('parts', []) or []

            mensagens.append(
                MensagemEmailRecebida(
                    message_id=item['id'],
                    remetente=_cabecalho(headers, 'From'),
                    assunto=_cabecalho(headers, 'Subject'),
                    recebido_em=_data_recebimento(detalhe),
                    anexos=_extrair_anexos(self._recurso, item['id'], partes),
                )
            )
        return mensagens
