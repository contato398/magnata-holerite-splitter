"""Testes locais do cliente Gmail readonly; nenhuma rede e acessada."""
import base64

import pytest

from magnata_os.documental.modulo01.adapters.email_gmail_readonly import (
    ESCOPOS_READONLY,
    REMETENTES_PERMITIDOS,
    ClienteGmailReadOnly,
    CredencialGmailAusente,
    DataInternaGmailInvalida,
    LabelGmailNaoEncontrada,
    MensagemGmailInvalida,
    carregar_credenciais_gmail_readonly,
)


class RecursoGmailFalso:
    """Duplo que expoe somente os quatro endpoints readonly usados."""

    def __init__(
        self,
        mensagens_por_id=None,
        paginas=None,
        anexos=None,
        labels=None,
    ):
        self.mensagens = mensagens_por_id or {}
        self.paginas = paginas or {None: {'messages': []}}
        self.anexos = anexos or {}
        self.labels_gmail = labels or [
            {'id': 'LABEL_1', 'name': 'Shadow-Entrada'}
        ]
        self.chamadas = []

    def users(self):
        return self

    def labels(self):
        return _Labels(self)

    def messages(self):
        return _Messages(self)


class _Executavel:
    def __init__(self, resultado):
        self.resultado = resultado

    def execute(self):
        return self.resultado


class _Labels:
    def __init__(self, pai):
        self.pai = pai

    def list(self, userId):  # noqa: N803
        self.pai.chamadas.append(('labels.list', {'userId': userId}))
        return _Executavel({'labels': self.pai.labels_gmail})


class _Messages:
    def __init__(self, pai):
        self.pai = pai

    def list(self, **parametros):
        self.pai.chamadas.append(('messages.list', parametros))
        return _Executavel(self.pai.paginas[parametros.get('pageToken')])

    def get(self, **parametros):
        self.pai.chamadas.append(('messages.get', parametros))
        return _Executavel(self.pai.mensagens[parametros['id']])

    def attachments(self):
        return _Attachments(self.pai)


class _Attachments:
    def __init__(self, pai):
        self.pai = pai

    def get(self, **parametros):
        self.pai.chamadas.append(('attachments.get', parametros))
        return _Executavel(self.pai.anexos[parametros['id']])


def _b64(conteudo: bytes) -> str:
    return base64.urlsafe_b64encode(conteudo).decode('ascii').rstrip('=')


def _mensagem(
    message_id='gmail-resource-1',
    remetente='dpessoal.contabilidade1@hotmail.com',
    internal_date='1735689600000',
    parts=None,
):
    return {
        'id': message_id,
        'internalDate': internal_date,
        'payload': {
            'headers': [
                {'name': 'From', 'value': remetente},
                {'name': 'Subject', 'value': 'Documentos mensais'},
            ],
            'mimeType': 'multipart/mixed',
            'parts': parts or [],
        },
    }


def _cliente(recurso):
    return ClienteGmailReadOnly(
        label='Shadow-Entrada',
        credenciais=object(),
        construir_recurso=lambda _credenciais: recurso,
    )


def _recurso_com_mensagens(*mensagens, **kwargs):
    ids = [mensagem['id'] for mensagem in mensagens]
    return RecursoGmailFalso(
        mensagens_por_id={mensagem['id']: mensagem for mensagem in mensagens},
        paginas={None: {'messages': [{'id': item} for item in ids]}},
        **kwargs,
    )


def test_escopo_oauth_e_exclusivamente_gmail_readonly():
    assert ESCOPOS_READONLY == (
        'https://www.googleapis.com/auth/gmail.readonly',
    )


def test_allowlist_e_exclusiva_e_fixa():
    assert REMETENTES_PERMITIDOS == frozenset({
        'dpessoal.contabilidade1@hotmail.com',
        'dpfiscal.contabilidade2@hotmail.com',
    })


def test_credencial_ausente_falha_sem_importar_cliente_google():
    with pytest.raises(CredencialGmailAusente):
        carregar_credenciais_gmail_readonly()


def test_label_ausente_falha_explicitamente():
    recurso = RecursoGmailFalso(labels=[{'id': 'X', 'name': 'Outra'}])
    with pytest.raises(LabelGmailNaoEncontrada):
        _cliente(recurso).buscar_novas_mensagens()


@pytest.mark.parametrize('valor', [None, '', 'agora', '-1', '1.5', True])
def test_internal_date_ausente_ou_invalido_falha_explicitamente(valor):
    mensagem = _mensagem(internal_date=valor)
    recurso = _recurso_com_mensagens(mensagem)
    with pytest.raises(DataInternaGmailInvalida):
        _cliente(recurso).buscar_novas_mensagens()


def test_from_e_parseado_normalizado_e_filtrado_por_allowlist():
    permitida = _mensagem(
        message_id='permitida',
        remetente='  Departamento Pessoal <DPESSOAL.CONTABILIDADE1@HOTMAIL.COM> ',
    )
    bloqueada = _mensagem(
        message_id='bloqueada', remetente='intruso@example.net'
    )
    mensagens = _cliente(
        _recurso_com_mensagens(permitida, bloqueada)
    ).buscar_novas_mensagens()

    assert [mensagem.message_id for mensagem in mensagens] == ['permitida']
    assert mensagens[0].remetente == 'dpessoal.contabilidade1@hotmail.com'


def test_paginacao_percorre_todos_os_next_page_tokens():
    primeira = _mensagem(message_id='pagina-1')
    segunda = _mensagem(
        message_id='pagina-2',
        remetente='dpfiscal.contabilidade2@hotmail.com',
    )
    recurso = RecursoGmailFalso(
        mensagens_por_id={'pagina-1': primeira, 'pagina-2': segunda},
        paginas={
            None: {
                'messages': [{'id': 'pagina-1'}],
                'nextPageToken': 'placeholder',
            },
            'placeholder': {'messages': [{'id': 'pagina-2'}]},
        },
    )

    mensagens = _cliente(recurso).buscar_novas_mensagens()

    assert [mensagem.message_id for mensagem in mensagens] == [
        'pagina-1', 'pagina-2'
    ]
    listas = [c for c in recurso.chamadas if c[0] == 'messages.list']
    assert listas == [
        ('messages.list', {'userId': 'me', 'labelIds': ['LABEL_1']}),
        ('messages.list', {
            'userId': 'me',
            'labelIds': ['LABEL_1'],
            'pageToken': 'placeholder',
        }),
    ]


def test_mime_recursivo_extrai_pdf_attachment_id_e_pdf_inline():
    partes = [{
        'filename': '',
        'mimeType': 'multipart/mixed',
        'body': {},
        'parts': [
            {
                'filename': 'folha.PDF',
                'mimeType': 'application/pdf',
                'body': {'attachmentId': 'ATT_1'},
            },
            {
                'filename': '',
                'mimeType': 'multipart/alternative',
                'body': {},
                'parts': [{
                    'filename': 'ponto.pdf',
                    'mimeType': 'APPLICATION/PDF',
                    'body': {'data': _b64(b'PDF-inline')},
                }],
            },
        ],
    }]
    mensagem = _mensagem(parts=partes)
    recurso = _recurso_com_mensagens(
        mensagem, anexos={'ATT_1': {'data': _b64(b'PDF-attachment')}}
    )

    anexos = _cliente(recurso).buscar_novas_mensagens()[0].anexos

    assert [(a.nome_original, a.mime_type, a.conteudo) for a in anexos] == [
        ('folha.PDF', 'application/pdf', b'PDF-attachment'),
        ('ponto.pdf', 'APPLICATION/PDF', b'PDF-inline'),
    ]
    chamada = [c for c in recurso.chamadas if c[0] == 'attachments.get']
    assert chamada == [('attachments.get', {
        'userId': 'me',
        'messageId': 'gmail-resource-1',
        'id': 'ATT_1',
    })]


def test_politica_pdf_aceita_mime_ou_extensao_e_preserva_origem():
    partes = [
        {
            'filename': 'arquivo.pdf',
            'mimeType': 'application/pdf',
            'body': {'data': _b64(b'A')},
        },
        {
            'filename': 'arquivo.pdf',
            'mimeType': 'application/octet-stream',
            'body': {'data': _b64(b'B')},
        },
        {
            'filename': 'arquivo',
            'mimeType': 'application/pdf',
            'body': {'data': _b64(b'C')},
        },
        {
            'filename': 'arquivo.txt',
            'mimeType': 'application/pdf',
            'body': {'data': _b64(b'D')},
        },
        {
            'filename': 'arquivo.PDF',
            'mimeType': 'application/pdf',
            'body': {'data': _b64(b'E')},
        },
        {
            'filename': ' arquivo.PDF ',
            'mimeType': ' Application/PDF ',
            'body': {'data': _b64(b'G')},
        },
        {
            'filename': 'arquivo.txt',
            'mimeType': 'text/plain',
            'body': {'data': _b64(b'F')},
        },
    ]
    mensagem = _mensagem(parts=partes)

    resultado = _cliente(
        _recurso_com_mensagens(mensagem)
    ).buscar_novas_mensagens()

    assert [
        (anexo.nome_original, anexo.mime_type, anexo.conteudo)
        for anexo in resultado[0].anexos
    ] == [
        ('arquivo.pdf', 'application/pdf', b'A'),
        ('arquivo.pdf', 'application/octet-stream', b'B'),
        ('arquivo', 'application/pdf', b'C'),
        ('arquivo.txt', 'application/pdf', b'D'),
        ('arquivo.PDF', 'application/pdf', b'E'),
        (' arquivo.PDF ', ' Application/PDF ', b'G'),
    ]


def test_gmail_message_resource_id_e_o_id_canonico():
    mensagem = _mensagem(message_id='RESOURCE_ID_CANONICO')
    resultado = _cliente(
        _recurso_com_mensagens(mensagem)
    ).buscar_novas_mensagens()
    assert resultado[0].message_id == 'RESOURCE_ID_CANONICO'


def test_id_do_detalhe_divergente_da_listagem_falha():
    mensagem = _mensagem(message_id='detalhe')
    recurso = RecursoGmailFalso(
        mensagens_por_id={'listado': mensagem},
        paginas={None: {'messages': [{'id': 'listado'}]}},
    )
    with pytest.raises(MensagemGmailInvalida):
        _cliente(recurso).buscar_novas_mensagens()


def test_duplo_nao_expoe_nenhuma_operacao_de_escrita():
    recurso = _recurso_com_mensagens(_mensagem())
    for nome in ('modify', 'trash', 'delete', 'send', 'batchModify'):
        assert not hasattr(recurso.messages(), nome)
    for nome in ('create', 'update', 'delete', 'patch'):
        assert not hasattr(recurso.labels(), nome)

    _cliente(recurso).buscar_novas_mensagens()

    assert [nome for nome, _args in recurso.chamadas] == [
        'labels.list', 'messages.list', 'messages.get'
    ]
