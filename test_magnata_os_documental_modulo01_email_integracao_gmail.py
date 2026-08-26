"""E2E local: fonte Gmail readonly -> AdapterCapturaEmail -> documental."""
import base64

from magnata_os.documental.modulo01.adapters.email_captura import (
    AdapterCapturaEmail,
)
from magnata_os.documental.modulo01.adapters.email_gmail_readonly import (
    ClienteGmailReadOnly,
)
from magnata_os.documental.modulo01.repositorio import (
    RepositorioDocumentosEmMemoria,
    RepositorioHistoricoEmMemoria,
)
from magnata_os.documental.modulo01.repositorio_esteira import (
    RepositorioEstadosEsteiraEmMemoria,
    RepositorioLotesEmMemoria,
)
from magnata_os.documental.modulo01.servico_avanco_esteira import (
    ServicoAvancoEsteira,
)
from magnata_os.documental.modulo01.servico_entrada import (
    ServicoEntradaDocumental,
)
from magnata_os.documental.modulo01.servico_lote import ServicoCriacaoLote


class _Executavel:
    def __init__(self, resultado):
        self.resultado = resultado

    def execute(self):
        return self.resultado


class RecursoGmailE2E:
    """Duplo readonly minimo; qualquer escrita causaria AttributeError."""

    def __init__(self, mensagens):
        self.mensagens = {mensagem['id']: mensagem for mensagem in mensagens}

    def users(self):
        return self

    def labels(self):
        return _Labels()

    def messages(self):
        return _Messages(self)


class _Labels:
    def list(self, userId):  # noqa: N803
        return _Executavel({
            'labels': [{'id': 'L_SHADOW', 'name': 'Shadow-Entrada'}]
        })


class _Messages:
    def __init__(self, recurso):
        self.recurso = recurso

    def list(self, userId, labelIds, pageToken=None):  # noqa: N803
        assert pageToken is None
        return _Executavel({
            'messages': [{'id': item} for item in self.recurso.mensagens]
        })

    def get(self, userId, id, format):  # noqa: A002,N803
        return _Executavel(self.recurso.mensagens[id])

    def attachments(self):
        return _Attachments()


class _Attachments:
    def get(self, **_parametros):
        raise AssertionError('E2E usa apenas PDF inline')


def _b64(conteudo):
    return base64.urlsafe_b64encode(conteudo).decode('ascii').rstrip('=')


def _mensagem(message_id, remetente, anexos):
    return {
        'id': message_id,
        'internalDate': '1787670000000',
        'payload': {
            'headers': [
                {'name': 'From', 'value': remetente},
                {'name': 'Subject', 'value': 'Competencia 08/2026'},
            ],
            'mimeType': 'multipart/mixed',
            'parts': anexos,
        },
    }


def _pdf(nome, conteudo):
    return {
        'filename': nome,
        'mimeType': 'application/pdf',
        'body': {'data': _b64(conteudo)},
    }


def _montar_e2e(mensagens):
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_historico = RepositorioHistoricoEmMemoria()
    repo_lotes = RepositorioLotesEmMemoria()
    repo_estados = RepositorioEstadosEsteiraEmMemoria()
    servico_entrada = ServicoEntradaDocumental(repo_docs, repo_historico)
    servico_avanco = ServicoAvancoEsteira(repo_estados, repo_historico)
    servico_lote = ServicoCriacaoLote(
        repo_lotes, servico_entrada, servico_avanco
    )
    fonte = ClienteGmailReadOnly(
        label='Shadow-Entrada',
        credenciais=object(),
        construir_recurso=lambda _credenciais: RecursoGmailE2E(mensagens),
    )
    return (
        AdapterCapturaEmail(fonte, servico_lote),
        repo_docs,
        repo_historico,
        repo_lotes,
    )


def test_e2e_ingere_somente_allowlist_e_pdf_preservando_proveniencia():
    permitida = _mensagem(
        'gmail-id-001',
        'DP <dpessoal.contabilidade1@hotmail.com>',
        [
            _pdf('holerite.pdf', b'PDF-HOLERITE'),
            {
                'filename': 'observacoes.txt',
                'mimeType': 'text/plain',
                'body': {'data': _b64(b'ignorar')},
            },
        ],
    )
    bloqueada = _mensagem(
        'gmail-id-002',
        'terceiro@example.net',
        [_pdf('nao-ingerir.pdf', b'PDF-TERCEIRO')],
    )
    adapter, repo_docs, repo_historico, repo_lotes = _montar_e2e(
        [permitida, bloqueada]
    )

    resumo = adapter.capturar_novas_mensagens()

    assert resumo.mensagens_processadas == 1
    assert len(resumo.resumos_lote) == 1
    assert resumo.resumos_lote[0].quantidade_arquivos == 1
    documentos = repo_docs.listar_todos()
    assert len(documentos) == 1
    assert documentos[0].nome_original == 'holerite.pdf'
    lote = repo_lotes.listar_todos()[0]
    assert lote.metadados == {
        'message_id': 'gmail-id-001',
        'remetente': 'dpessoal.contabilidade1@hotmail.com',
        'assunto': 'Competencia 08/2026',
        'recebido_em_origem': '2026-08-25T15:00:00+00:00',
    }
    eventos = repo_historico.listar_todos()
    assert any(
        evento.detalhes.get('metadados') == {
            'origem_message_id': 'gmail-id-001',
            'origem_remetente': 'dpessoal.contabilidade1@hotmail.com',
        }
        for evento in eventos
    )


def test_e2e_reprocessamento_preserva_idempotencia_existente_por_hash():
    mensagem = _mensagem(
        'gmail-id-repetido',
        'dpfiscal.contabilidade2@hotmail.com',
        [_pdf('fiscal.pdf', b'CONTEUDO-ESTAVEL')],
    )
    adapter, repo_docs, _repo_historico, _repo_lotes = _montar_e2e(
        [mensagem]
    )

    primeiro = adapter.capturar_novas_mensagens()
    segundo = adapter.capturar_novas_mensagens()

    assert primeiro.resumos_lote[0].quantidade_sucesso == 1
    assert segundo.resumos_lote[0].quantidade_duplicados == 1
    assert len(repo_docs.listar_todos()) == 1
