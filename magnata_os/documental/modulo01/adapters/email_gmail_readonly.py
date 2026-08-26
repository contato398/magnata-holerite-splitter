"""Fonte Gmail readonly e inerte para a Captura de E-mail Shadow V1.

Este modulo apenas define a integracao. Nenhuma credencial e carregada e
nenhuma conexao e aberta ao importa-lo. Os testes injetam um recurso local;
construir o recurso real permanece um gate separado de operacao externa.

Politica de seguranca:
- o unico escopo OAuth e ``gmail.readonly``;
- a allowlist de remetentes e fixa em codigo;
- somente endpoints Gmail de leitura sao usados;
- partes com ``application/pdf`` OU nome ``.pdf`` entram;
- mensagens fora da allowlist e anexos nao-PDF sao ignorados de forma
  deterministica.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import PurePath
from typing import Any, Callable, List, Optional, Sequence

from .email_captura import AnexoEmailRecebido, MensagemEmailRecebida

ESCOPOS_READONLY = ('https://www.googleapis.com/auth/gmail.readonly',)
REMETENTES_PERMITIDOS = frozenset({
    'dpessoal.contabilidade1@hotmail.com',
    'dpfiscal.contabilidade2@hotmail.com',
})
MIME_TYPE_PDF = 'application/pdf'


class CredencialGmailAusente(Exception):
    """Nenhum caminho de credencial foi informado explicitamente."""


class LabelGmailNaoEncontrada(Exception):
    """A label readonly configurada nao existe na caixa consultada."""


class DataInternaGmailInvalida(ValueError):
    """``internalDate`` esta ausente ou nao representa Unix epoch em ms."""


class MensagemGmailInvalida(ValueError):
    """O recurso retornado pelo Gmail nao possui ID canonico valido."""


def carregar_credenciais_gmail_readonly(caminho_token: Optional[str] = None) -> Any:
    """Carrega um token ja emitido, sempre restringindo-o ao escopo readonly.

    Nao ha caminho default, variavel de ambiente implicita nem fluxo OAuth
    interativo. Esta funcao nao e chamada pela Captura Shadow V1 nem por seus
    testes.
    """
    if not caminho_token:
        raise CredencialGmailAusente(
            'Nenhum caminho de token informado; a Captura Shadow V1 e inerte.'
        )
    from google.oauth2.credentials import Credentials

    return Credentials.from_authorized_user_file(
        caminho_token, list(ESCOPOS_READONLY)
    )


def construir_recurso_gmail(credenciais: Any) -> Any:
    """Constroi o recurso Gmail real; nenhum teste chama esta funcao."""
    from googleapiclient.discovery import build

    return build(
        'gmail',
        'v1',
        credentials=credenciais,
        cache_discovery=False,
        static_discovery=True,
    )


def _cabecalho(headers: Sequence[dict], nome: str) -> str:
    for header in headers:
        if str(header.get('name', '')).casefold() == nome.casefold():
            return str(header.get('value', ''))
    return ''


def _normalizar_remetente(valor_from: str) -> str:
    """Extrai e normaliza o addr-spec do header RFC 5322 ``From``."""
    _nome, endereco = parseaddr(valor_from or '')
    normalizado = endereco.strip().casefold()
    if normalizado.count('@') != 1:
        return ''
    local, dominio = normalizado.split('@', 1)
    if not local or not dominio:
        return ''
    return normalizado


def _data_recebimento(detalhe: dict) -> datetime:
    valor = detalhe.get('internalDate')
    if valor is None or isinstance(valor, bool):
        raise DataInternaGmailInvalida('internalDate ausente ou invalido.')
    try:
        milissegundos = int(valor)
        if milissegundos < 0 or str(valor).strip() != str(milissegundos):
            raise ValueError
        return datetime.fromtimestamp(
            milissegundos / 1000, tz=timezone.utc
        )
    except (ValueError, TypeError, OverflowError, OSError) as exc:
        raise DataInternaGmailInvalida(
            f'internalDate invalido: {valor!r}.'
        ) from exc


def _decodificar_base64url(dado: str) -> bytes:
    if not dado:
        return b''
    preenchido = dado + '=' * (-len(dado) % 4)
    return base64.b64decode(
        preenchido.encode('ascii'), altchars=b'-_', validate=True
    )


def _parte_e_pdf(parte: dict) -> bool:
    nome = str(parte.get('filename') or '').strip()
    mime_type = str(parte.get('mimeType') or '').strip().casefold()
    nome_indica_pdf = bool(
        nome and PurePath(nome).suffix.casefold() == '.pdf'
    )
    mime_indica_pdf = mime_type == MIME_TYPE_PDF
    return nome_indica_pdf or mime_indica_pdf


def _extrair_pdfs(
    recurso: Any,
    message_id: str,
    parte: dict,
) -> List[AnexoEmailRecebido]:
    """Percorre a arvore MIME em profundidade e devolve apenas PDFs."""
    anexos: List[AnexoEmailRecebido] = []

    if _parte_e_pdf(parte):
        corpo = parte.get('body') or {}
        attachment_id = corpo.get('attachmentId')
        if attachment_id:
            resposta = (
                recurso.users()
                .messages()
                .attachments()
                .get(
                    userId='me',
                    messageId=message_id,
                    id=attachment_id,
                )
                .execute()
            )
            dado_b64 = str(resposta.get('data') or '')
        else:
            dado_b64 = str(corpo.get('data') or '')

        anexos.append(
            AnexoEmailRecebido(
                nome_original=str(parte.get('filename') or ''),
                mime_type=str(parte.get('mimeType') or ''),
                conteudo=_decodificar_base64url(dado_b64),
            )
        )

    for subparte in parte.get('parts') or []:
        anexos.extend(_extrair_pdfs(recurso, message_id, subparte))
    return anexos


class ClienteGmailReadOnly:
    """Implementacao de ``FonteMensagensEmail`` contra Gmail API v1.

    O recurso e injetavel para que a Captura Shadow V1 rode localmente sem
    credencial nem rede. O filtro por allowlist acontece depois de parsear o
    header ``From`` da mensagem completa.
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
        for label in resposta.get('labels') or []:
            if label.get('name') == self._label:
                return str(label['id'])
        raise LabelGmailNaoEncontrada(
            f'Label {self._label!r} nao encontrada na caixa consultada.'
        )

    def _listar_ids_mensagens(self, label_id: str) -> List[str]:
        ids: List[str] = []
        page_token: Optional[str] = None
        while True:
            parametros = {'userId': 'me', 'labelIds': [label_id]}
            if page_token is not None:
                parametros['pageToken'] = page_token
            resposta = (
                self._recurso.users().messages().list(**parametros).execute()
            )
            for item in resposta.get('messages') or []:
                message_id = item.get('id')
                if not message_id:
                    raise MensagemGmailInvalida(
                        'Item da listagem Gmail sem resource ID.'
                    )
                ids.append(str(message_id))
            page_token = resposta.get('nextPageToken')
            if not page_token:
                return ids

    def buscar_novas_mensagens(self) -> Sequence[MensagemEmailRecebida]:
        label_id = self._resolver_id_label()
        mensagens: List[MensagemEmailRecebida] = []

        for id_listado in self._listar_ids_mensagens(label_id):
            detalhe = (
                self._recurso.users()
                .messages()
                .get(userId='me', id=id_listado, format='full')
                .execute()
            )
            message_id = detalhe.get('id')
            if not message_id:
                raise MensagemGmailInvalida(
                    f'Mensagem listada como {id_listado!r} sem resource ID.'
                )
            message_id = str(message_id)
            if message_id != id_listado:
                raise MensagemGmailInvalida(
                    'Resource ID da mensagem diverge do ID da listagem.'
                )

            payload = detalhe.get('payload') or {}
            headers = payload.get('headers') or []
            remetente = _normalizar_remetente(_cabecalho(headers, 'From'))
            if remetente not in REMETENTES_PERMITIDOS:
                continue

            mensagens.append(
                MensagemEmailRecebida(
                    message_id=message_id,
                    remetente=remetente,
                    assunto=_cabecalho(headers, 'Subject'),
                    recebido_em=_data_recebimento(detalhe),
                    anexos=_extrair_pdfs(
                        self._recurso, message_id, payload
                    ),
                )
            )
        return mensagens
