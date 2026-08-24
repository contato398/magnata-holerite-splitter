"""
Testes de integracao: ClienteGmailReadOnly + AdapterCapturaEmail.

Prova que o cliente Gmail (so leitura) e o adapter de captura trabalham
juntos -- nenhum teste deste arquivo acessa rede ou Gmail real.
"""
import base64
from datetime import datetime, timezone

import pytest

from magnata_os.documental.modulo01.adapters.email_captura import (
    AdapterCapturaEmail,
    MensagemEmailRecebida,
    AnexoEmailRecebido,
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
from magnata_os.documental.modulo01.servico_avanco_esteira import ServicoAvancoEsteira
from magnata_os.documental.modulo01.servico_entrada import ServicoEntradaDocumental
from magnata_os.documental.modulo01.servico_lote import ServicoCriacaoLote


class RecursoGmailFalsoParaIntegracao:
    """Duplo de recurso Gmail para testes de integracao -- emula
    exatamente o que o ClienteGmailReadOnly espera da API real."""

    def __init__(self, mensagens_gmail):
        self._mensagens = mensagens_gmail
        self.chamadas = []

    def users(self):
        return self

    def labels(self):
        return _LabelsIntegracao(self)

    def messages(self):
        return _MessagesIntegracao(self)


class _LabelsIntegracao:
    def __init__(self, pai):
        self._pai = pai

    def list(self, userId):
        return _ExecutavelIntegracao(
            {'labels': [{'id': 'L1', 'name': 'Processado-Modulo01'}]}, self._pai.chamadas
        )


class _MessagesIntegracao:
    def __init__(self, pai):
        self._pai = pai

    def list(self, userId, labelIds):
        msg_ids = [{'id': m.message_id} for m in self._pai._mensagens]
        return _ExecutavelIntegracao({'messages': msg_ids}, self._pai.chamadas)

    def get(self, userId, id, format):
        for m in self._pai._mensagens:
            if m.message_id == id:
                return _ExecutavelIntegracao(
                    self._converter_para_gmail_json(m), self._pai.chamadas
                )
        raise KeyError(f'Mensagem {id} nao encontrada')

    @staticmethod
    def _converter_para_gmail_json(msg):
        headers = [
            {'name': 'From', 'value': msg.remetente},
            {'name': 'Subject', 'value': msg.assunto},
        ]
        partes = []
        for anexo in msg.anexos:
            dado_b64 = base64.urlsafe_b64encode(anexo.conteudo).decode('ascii')
            partes.append(
                {
                    'filename': anexo.nome_original,
                    'mimeType': anexo.mime_type,
                    'body': {'data': dado_b64},
                }
            )
        return {
            'id': msg.message_id,
            'internalDate': str(int(msg.recebido_em.timestamp() * 1000)),
            'payload': {'headers': headers, 'parts': partes},
        }

    def attachments(self):
        return _AttachmentsIntegracao()


class _AttachmentsIntegracao:
    def get(self, userId, messageId, id):
        return _ExecutavelIntegracao({}, [])


class _ExecutavelIntegracao:
    def __init__(self, resultado, chamadas):
        self._resultado = resultado
        self._chamadas = chamadas

    def execute(self):
        return self._resultado


def test_cliente_gmail_com_adapter_captura_processa_email_real():
    """Prova end-to-end: cliente Gmail lê mensagens do duplo, adapter
    as registra como lotes no servico de criacao."""
    # Setup: repositorios em memoria
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    repo_lotes = RepositorioLotesEmMemoria()
    repo_estados = RepositorioEstadosEsteiraEmMemoria()

    servico_entrada = ServicoEntradaDocumental(repo_docs, repo_hist)
    servico_avanco = ServicoAvancoEsteira(repo_estados, repo_hist)
    servico_lote = ServicoCriacaoLote(repo_lotes, servico_entrada, servico_avanco)

    # Mensagens Gmail fake (com anexo real em bytes)
    mensagens_gmail = [
        MensagemEmailRecebida(
            message_id='msg-1',
            remetente='dp@empresa.com',
            assunto='Folha Julho 2026',
            recebido_em=datetime(2026, 7, 31, 10, 0, 0, tzinfo=timezone.utc),
            anexos=[
                AnexoEmailRecebido(
                    nome_original='folha-julho.pdf',
                    mime_type='application/pdf',
                    conteudo=b'PDF-BYTES-FALSOS',
                )
            ],
        ),
        MensagemEmailRecebida(
            message_id='msg-2',
            remetente='dp@empresa.com',
            assunto='Ponto Julho 2026',
            recebido_em=datetime(2026, 7, 31, 11, 0, 0, tzinfo=timezone.utc),
            anexos=[
                AnexoEmailRecebido(
                    nome_original='ponto-julho.xlsx',
                    mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    conteudo=b'XLSX-BYTES-FALSOS',
                )
            ],
        ),
    ]

    # Cliente Gmail aponta para duplo
    recurso_falso = RecursoGmailFalsoParaIntegracao(mensagens_gmail)
    cliente_gmail = ClienteGmailReadOnly(
        label='Processado-Modulo01',
        credenciais='credencial-falsa',
        construir_recurso=lambda _: recurso_falso,
    )

    # Adapter coloca o cliente no meio
    adapter = AdapterCapturaEmail(cliente_gmail, servico_lote)

    # Executa captura
    resumo = adapter.capturar_novas_mensagens()

    # Validacoes
    assert resumo.mensagens_processadas == 2
    assert resumo.mensagens_sem_anexo == ()
    assert len(resumo.resumos_lote) == 2

    # Lote 1: folha de pagamento
    lote1 = resumo.resumos_lote[0]
    assert lote1.origem == 'email'
    assert lote1.quantidade_erro == 0
    assert len(lote1.itens) == 1
    assert lote1.itens[0].nome_original == 'folha-julho.pdf'

    # Lote 2: ponto
    lote2 = resumo.resumos_lote[1]
    assert lote2.origem == 'email'
    assert lote2.quantidade_erro == 0
    assert len(lote2.itens) == 1
    assert lote2.itens[0].nome_original == 'ponto-julho.xlsx'

    # Confirma que os documentos foram registrados no repositorio
    docs = repo_docs.listar_todos()
    assert len(docs) == 2
    assert {d.nome_original for d in docs} == {'folha-julho.pdf', 'ponto-julho.xlsx'}


def test_cliente_gmail_com_adapter_lida_com_msg_sem_anexo():
    """Adapter ja prova que mensagens sem anexo sao devidamente
    contabilizadas; aqui validamos que o cliente Gmail tambem as
    devolve corretamente (so que o adapter depois as descarta)."""
    mensagens_gmail = [
        MensagemEmailRecebida(
            message_id='msg-sem-anexo',
            remetente='alguem@empresa.com',
            assunto='Precisa de info',
            recebido_em=datetime(2026, 8, 1, tzinfo=timezone.utc),
            anexos=[],
        )
    ]

    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    repo_lotes = RepositorioLotesEmMemoria()
    repo_estados = RepositorioEstadosEsteiraEmMemoria()

    servico_entrada = ServicoEntradaDocumental(repo_docs, repo_hist)
    servico_avanco = ServicoAvancoEsteira(repo_estados, repo_hist)
    servico_lote = ServicoCriacaoLote(repo_lotes, servico_entrada, servico_avanco)

    recurso_falso = RecursoGmailFalsoParaIntegracao(mensagens_gmail)
    cliente_gmail = ClienteGmailReadOnly(
        label='Processado-Modulo01',
        credenciais='x',
        construir_recurso=lambda _: recurso_falso,
    )

    adapter = AdapterCapturaEmail(cliente_gmail, servico_lote)
    resumo = adapter.capturar_novas_mensagens()

    assert resumo.mensagens_processadas == 1
    assert resumo.mensagens_sem_anexo == ('msg-sem-anexo',)
    assert len(resumo.resumos_lote) == 0


def test_multiplos_anexos_por_msg_sao_todos_registrados():
    """Uma unica mensagem com varios anexos vira um lote com varios
    itens."""
    mensagens_gmail = [
        MensagemEmailRecebida(
            message_id='msg-multi',
            remetente='rh@empresa.com',
            assunto='Documentos funcionario',
            recebido_em=datetime(2026, 8, 1, tzinfo=timezone.utc),
            anexos=[
                AnexoEmailRecebido(
                    nome_original=f'doc{i}.pdf', mime_type='application/pdf', conteudo=f'PDF{i}'.encode()
                )
                for i in range(1, 4)
            ],
        )
    ]

    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    repo_lotes = RepositorioLotesEmMemoria()
    repo_estados = RepositorioEstadosEsteiraEmMemoria()

    servico_entrada = ServicoEntradaDocumental(repo_docs, repo_hist)
    servico_avanco = ServicoAvancoEsteira(repo_estados, repo_hist)
    servico_lote = ServicoCriacaoLote(repo_lotes, servico_entrada, servico_avanco)

    recurso_falso = RecursoGmailFalsoParaIntegracao(mensagens_gmail)
    cliente_gmail = ClienteGmailReadOnly(
        label='Processado-Modulo01',
        credenciais='x',
        construir_recurso=lambda _: recurso_falso,
    )

    adapter = AdapterCapturaEmail(cliente_gmail, servico_lote)
    resumo = adapter.capturar_novas_mensagens()

    assert len(resumo.resumos_lote) == 1
    lote = resumo.resumos_lote[0]
    assert len(lote.itens) == 3
    assert lote.quantidade_erro == 0
    assert {item.nome_original for item in lote.itens} == {'doc1.pdf', 'doc2.pdf', 'doc3.pdf'}
