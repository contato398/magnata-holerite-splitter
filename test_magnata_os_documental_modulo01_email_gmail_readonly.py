"""
Testes do cliente Gmail real, so-leitura (Modulo 01 -- Fase 1 do modo
sombra, ver docs/decisoes/plano-modo-sombra-captura-email.md).

Nenhum teste deste arquivo acessa rede, Gmail real ou credencial real --
tudo roda contra `RecursoGmailFalso`, um duplo que reproduz a interface
encadeada da API Gmail (`.users().messages().list(...).execute()`) mas
SO implementa os 4 metodos de leitura que `ClienteGmailReadOnly`
realmente chama. Qualquer tentativa de chamar um metodo de escrita
(`modify`, `trash`, `delete`, `send`, `batchModify`, ou qualquer metodo
de escrita em `labels()`) levanta `AttributeError` no proprio duplo --
e o que `test_cliente_nunca_chama_metodo_de_escrita_do_gmail` prova.

`carregar_credenciais_gmail_readonly` e `construir_recurso_gmail` (as
duas unicas funcoes que tocariam o Gmail de verdade) nunca sao chamadas
com um caminho/credencial real em nenhum teste aqui.
"""
import base64

import pytest

from magnata_os.documental.modulo01.adapters.email_gmail_readonly import (
    ESCOPOS_READONLY,
    ClienteGmailReadOnly,
    CredencialGmailAusente,
    LabelGmailNaoEncontrada,
    carregar_credenciais_gmail_readonly,
)


class RecursoGmailFalso:
    """Duplo de teste do recurso `googleapiclient` da API Gmail v1. So
    implementa os metodos de LEITURA que o cliente real chama --
    `users().labels().list`, `users().messages().list`,
    `users().messages().get`, `users().messages().attachments().get`.
    Qualquer outro metodo (escrita) nao existe neste duplo -- chamar
    `.modify()`, `.trash()`, `.send()` etc. levanta AttributeError,
    nunca silenciosamente "funciona"."""

    def __init__(self, labels=None, mensagens_por_id=None, lista_ids=None, anexos_por_attachment_id=None):
        self._labels = labels or []
        self._mensagens_por_id = mensagens_por_id or {}
        self._lista_ids = lista_ids if lista_ids is not None else list(self._mensagens_por_id.keys())
        self._anexos_por_attachment_id = anexos_por_attachment_id or {}
        self.chamadas = []

    def users(self):
        return self

    def labels(self):
        return _RecursoLabels(self)

    def messages(self):
        return _RecursoMessages(self)


class _Executavel:
    def __init__(self, resultado, chamadas, nome):
        self._resultado = resultado
        chamadas.append(nome)

    def execute(self):
        return self._resultado


class _RecursoLabels:
    def __init__(self, pai):
        self._pai = pai

    def list(self, userId):  # noqa: N803 -- nome espelha a API real
        return _Executavel(
            {'labels': self._pai._labels}, self._pai.chamadas, 'labels.list'
        )


class _RecursoMessages:
    def __init__(self, pai):
        self._pai = pai

    def list(self, userId, labelIds):  # noqa: N803
        return _Executavel(
            {'messages': [{'id': mid} for mid in self._pai._lista_ids]},
            self._pai.chamadas,
            'messages.list',
        )

    def get(self, userId, id, format):  # noqa: A002,N803
        return _Executavel(self._pai._mensagens_por_id[id], self._pai.chamadas, 'messages.get')

    def attachments(self):
        return _RecursoAttachments(self._pai)


class _RecursoAttachments:
    def __init__(self, pai):
        self._pai = pai

    def get(self, userId, messageId, id):  # noqa: A002,N803
        return _Executavel(
            self._pai._anexos_por_attachment_id[id], self._pai.chamadas, 'attachments.get'
        )


def _b64(dado: bytes) -> str:
    return base64.urlsafe_b64encode(dado).decode('ascii')


def _construir_recurso_falso(recurso):
    return lambda credenciais: recurso


def test_escopo_e_travado_em_readonly():
    assert ESCOPOS_READONLY == ('https://www.googleapis.com/auth/gmail.readonly',)


def test_credencial_ausente_levanta_sem_tocar_google():
    with pytest.raises(CredencialGmailAusente):
        carregar_credenciais_gmail_readonly()


def test_label_nao_encontrada_levanta_erro_claro():
    recurso = RecursoGmailFalso(labels=[{'id': 'L1', 'name': 'Outra-Label'}])
    cliente = ClienteGmailReadOnly(
        label='Processado-Modulo01',
        credenciais='credencial-falsa-nunca-usada',
        construir_recurso=_construir_recurso_falso(recurso),
    )
    with pytest.raises(LabelGmailNaoEncontrada):
        cliente.buscar_novas_mensagens()


def test_busca_mensagem_com_anexo_via_attachment_id():
    conteudo = b'PDF-FALSO-CONTEUDO-DE-TESTE'
    recurso = RecursoGmailFalso(
        labels=[{'id': 'L1', 'name': 'Processado-Modulo01'}],
        mensagens_por_id={
            'msg-1': {
                'internalDate': '1735689600000',  # 2025-01-01T00:00:00Z
                'payload': {
                    'headers': [
                        {'name': 'From', 'value': 'cliente@exemplo.com'},
                        {'name': 'Subject', 'value': 'Holerite Janeiro'},
                    ],
                    'parts': [
                        {
                            'filename': 'holerite.pdf',
                            'mimeType': 'application/pdf',
                            'body': {'attachmentId': 'att-1'},
                        }
                    ],
                },
            }
        },
        anexos_por_attachment_id={'att-1': {'data': _b64(conteudo)}},
    )
    cliente = ClienteGmailReadOnly(
        label='Processado-Modulo01',
        credenciais='credencial-falsa-nunca-usada',
        construir_recurso=_construir_recurso_falso(recurso),
    )

    mensagens = cliente.buscar_novas_mensagens()

    assert len(mensagens) == 1
    msg = mensagens[0]
    assert msg.message_id == 'msg-1'
    assert msg.remetente == 'cliente@exemplo.com'
    assert msg.assunto == 'Holerite Janeiro'
    assert len(msg.anexos) == 1
    assert msg.anexos[0].nome_original == 'holerite.pdf'
    assert msg.anexos[0].mime_type == 'application/pdf'
    assert msg.anexos[0].conteudo == conteudo


def test_busca_mensagem_com_anexo_inline_sem_attachment_id():
    conteudo = b'conteudo-inline'
    recurso = RecursoGmailFalso(
        labels=[{'id': 'L1', 'name': 'Processado-Modulo01'}],
        mensagens_por_id={
            'msg-2': {
                'internalDate': '1735689600000',
                'payload': {
                    'headers': [],
                    'parts': [
                        {
                            'filename': 'nota.txt',
                            'mimeType': 'text/plain',
                            'body': {'data': _b64(conteudo)},
                        }
                    ],
                },
            }
        },
    )
    cliente = ClienteGmailReadOnly(
        label='Processado-Modulo01',
        credenciais='x',
        construir_recurso=_construir_recurso_falso(recurso),
    )

    mensagens = cliente.buscar_novas_mensagens()

    assert mensagens[0].anexos[0].conteudo == conteudo


def test_mensagem_sem_anexo_e_devolvida_com_lista_vazia_nunca_descartada():
    recurso = RecursoGmailFalso(
        labels=[{'id': 'L1', 'name': 'Processado-Modulo01'}],
        mensagens_por_id={
            'msg-3': {
                'internalDate': '1735689600000',
                'payload': {
                    'headers': [{'name': 'From', 'value': 'x@y.com'}],
                    'parts': [{'filename': '', 'mimeType': 'text/plain', 'body': {'data': ''}}],
                },
            }
        },
    )
    cliente = ClienteGmailReadOnly(
        label='Processado-Modulo01',
        credenciais='x',
        construir_recurso=_construir_recurso_falso(recurso),
    )

    mensagens = cliente.buscar_novas_mensagens()

    assert len(mensagens) == 1
    assert mensagens[0].anexos == []


def test_multiplas_mensagens_sao_todas_devolvidas():
    recurso = RecursoGmailFalso(
        labels=[{'id': 'L1', 'name': 'Processado-Modulo01'}],
        mensagens_por_id={
            'msg-a': {'internalDate': '1735689600000', 'payload': {'headers': [], 'parts': []}},
            'msg-b': {'internalDate': '1735689600000', 'payload': {'headers': [], 'parts': []}},
        },
        lista_ids=['msg-a', 'msg-b'],
    )
    cliente = ClienteGmailReadOnly(
        label='Processado-Modulo01',
        credenciais='x',
        construir_recurso=_construir_recurso_falso(recurso),
    )

    mensagens = cliente.buscar_novas_mensagens()

    assert {m.message_id for m in mensagens} == {'msg-a', 'msg-b'}


def test_cliente_nunca_chama_metodo_de_escrita_do_gmail():
    """O duplo so tem os 4 metodos de leitura -- se o cliente real
    chamasse qualquer metodo de escrita (modify/trash/delete/send/
    batchModify/labels create-update-delete), este teste levantaria
    AttributeError por causa do duplo, nao passaria silenciosamente."""
    recurso = RecursoGmailFalso(
        labels=[{'id': 'L1', 'name': 'Processado-Modulo01'}],
        mensagens_por_id={'msg-1': {'internalDate': '1735689600000', 'payload': {'headers': [], 'parts': []}}},
    )
    for metodo_proibido in ('modify', 'trash', 'delete', 'send', 'batchModify'):
        assert not hasattr(recurso.messages(), metodo_proibido)
    for metodo_proibido in ('create', 'update', 'delete', 'patch'):
        assert not hasattr(recurso.labels(), metodo_proibido)

    cliente = ClienteGmailReadOnly(
        label='Processado-Modulo01',
        credenciais='x',
        construir_recurso=_construir_recurso_falso(recurso),
    )
    cliente.buscar_novas_mensagens()

    assert recurso.chamadas == ['labels.list', 'messages.list', 'messages.get']


def test_recurso_e_construido_via_callable_injetado_nao_via_default_real():
    """Confirma que o cliente usa o `construir_recurso` injetado -- nunca
    o default real (`construir_recurso_gmail`, que importaria
    googleapiclient e chamaria a rede) quando um duplo e passado."""
    chamadas = []

    def construir_falso(credenciais):
        chamadas.append(credenciais)
        return RecursoGmailFalso(labels=[{'id': 'L1', 'name': 'X'}], mensagens_por_id={})

    cliente = ClienteGmailReadOnly(
        label='X', credenciais='minha-credencial-de-teste', construir_recurso=construir_falso
    )
    cliente.buscar_novas_mensagens()

    assert chamadas == ['minha-credencial-de-teste']
