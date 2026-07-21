"""
Testes da rota isolada /email-avulso/enviar (_enviar_email_avulso_core).

Cobre: dedup por nome normalizado, PDF que não abre, limite de tamanho,
idempotência (bloqueio de segundo envio do mesmo pacote), dry_run nunca
dispara e-mail real, envio real chama _smtp_enviar_email exatamente uma
vez, autenticação X-API-KEY da rota HTTP, origem inválida.
"""
import hashlib
import io
import unittest
from unittest.mock import patch, MagicMock

from pypdf import PdfWriter

import app as m


def _pdf_valido():
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


PDF_VALIDO = _pdf_valido()


class TestResolverAnexoAvulso(unittest.TestCase):
    @patch('app.requests.get')
    def test_origem_invalida_levanta_erro(self, mock_get):
        with self.assertRaises(ValueError):
            m._resolver_anexo_avulso('OutraTabela', 'rec1', 'att1')
        mock_get.assert_not_called()

    @patch('app.requests.get')
    def test_attachment_id_nao_encontrado(self, mock_get):
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = {'fields': {m.F_ENVIO_ARQUIVOS: [{'id': 'attX', 'filename': 'a.pdf', 'url': 'u'}]}}
        mock_get.return_value = resp
        with self.assertRaises(ValueError):
            m._resolver_anexo_avulso('Envio', 'rec1', 'attNaoExiste')


class TestEnviarEmailAvulsoCore(unittest.TestCase):
    def _mock_resolver(self, mapa):
        def fake(origem, record_id, attachment_id):
            return mapa[attachment_id]
        return fake

    @patch('app._smtp_enviar_email')
    @patch('app._carregar_documento_url')
    @patch('app._resolver_anexo_avulso')
    def test_dry_run_nunca_dispara_email(self, mock_resolver, mock_baixar, mock_smtp):
        mock_resolver.side_effect = self._mock_resolver({
            'att1': {'filename': 'Doc1.pdf', 'url': 'https://x/1'},
        })
        mock_baixar.return_value = PDF_VALIDO

        resultado, status = m._enviar_email_avulso_core(
            'destino@exemplo.com', 'Assunto', 'Corpo',
            [{'origem': 'Envio', 'record_id': 'rec1', 'attachment_id': 'att1'}],
            dry_run=True,
        )
        self.assertEqual(status, 200)
        self.assertEqual(resultado['acao'], 'enviaria')
        mock_smtp.assert_not_called()

    @patch('app._smtp_enviar_email')
    @patch('app._carregar_documento_url')
    @patch('app._resolver_anexo_avulso')
    def test_envio_real_chama_smtp_uma_vez(self, mock_resolver, mock_baixar, mock_smtp):
        mock_resolver.side_effect = self._mock_resolver({
            'att1': {'filename': 'Doc1.pdf', 'url': 'https://x/1'},
            'att2': {'filename': 'Doc2.pdf', 'url': 'https://x/2'},
        })
        mock_baixar.return_value = PDF_VALIDO

        resultado, status = m._enviar_email_avulso_core(
            'destino@exemplo.com', 'Assunto', 'Corpo',
            [{'origem': 'Envio', 'record_id': 'rec1', 'attachment_id': 'att1'},
             {'origem': 'Funcionario', 'record_id': 'rec2', 'attachment_id': 'att2'}],
            dry_run=False,
        )
        self.assertEqual(status, 200)
        self.assertEqual(resultado['acao'], 'enviado')
        mock_smtp.assert_called_once()
        args = mock_smtp.call_args[0]
        self.assertEqual(args[0], 'destino@exemplo.com')
        self.assertEqual(args[1], 'Assunto')
        self.assertEqual(len(args[3]), 2)

    @patch('app._smtp_enviar_email')
    @patch('app._carregar_documento_url')
    @patch('app._resolver_anexo_avulso')
    def test_bloqueia_arquivo_duplicado_na_selecao(self, mock_resolver, mock_baixar, mock_smtp):
        mock_resolver.side_effect = self._mock_resolver({
            'att1': {'filename': 'Mesmo Nome.pdf', 'url': 'https://x/1'},
            'att2': {'filename': '  mesmo nome.pdf  '.strip(), 'url': 'https://x/2'},
        })
        resultado, status = m._enviar_email_avulso_core(
            'destino@exemplo.com', 'Assunto', 'Corpo',
            [{'origem': 'Envio', 'record_id': 'rec1', 'attachment_id': 'att1'},
             {'origem': 'Envio', 'record_id': 'rec1', 'attachment_id': 'att2'}],
            dry_run=True,
        )
        self.assertEqual(status, 409)
        self.assertEqual(resultado['erro'], 'arquivo_duplicado_na_selecao')
        mock_smtp.assert_not_called()

    @patch('app._smtp_enviar_email')
    @patch('app._carregar_documento_url')
    @patch('app._resolver_anexo_avulso')
    def test_bloqueia_pdf_que_nao_abre(self, mock_resolver, mock_baixar, mock_smtp):
        mock_resolver.side_effect = self._mock_resolver({
            'att1': {'filename': 'Corrompido.pdf', 'url': 'https://x/1'},
        })
        mock_baixar.return_value = b'isso nao e um pdf valido'
        resultado, status = m._enviar_email_avulso_core(
            'destino@exemplo.com', 'Assunto', 'Corpo',
            [{'origem': 'Envio', 'record_id': 'rec1', 'attachment_id': 'att1'}],
            dry_run=True,
        )
        self.assertEqual(status, 422)
        self.assertEqual(resultado['erro'].split(':')[0], 'pdf_nao_abre')
        mock_smtp.assert_not_called()

    @patch('app._smtp_enviar_email')
    @patch('app._carregar_documento_url')
    @patch('app._resolver_anexo_avulso')
    def test_bloqueia_tamanho_acima_do_limite(self, mock_resolver, mock_baixar, mock_smtp):
        mock_resolver.side_effect = self._mock_resolver({
            'att1': {'filename': 'Grande.pdf', 'url': 'https://x/1'},
        })
        # simula um PDF valido porem gigante (acima do limite de 20MB)
        grande = PDF_VALIDO + b'0' * (21 * 1024 * 1024)
        mock_baixar.return_value = grande
        resultado, status = m._enviar_email_avulso_core(
            'destino@exemplo.com', 'Assunto', 'Corpo',
            [{'origem': 'Envio', 'record_id': 'rec1', 'attachment_id': 'att1'}],
            dry_run=True,
        )
        self.assertEqual(status, 413)
        self.assertEqual(resultado['erro'], 'tamanho_total_excede_limite')
        mock_smtp.assert_not_called()

    @patch('app._smtp_enviar_email')
    @patch('app._carregar_documento_url')
    @patch('app._resolver_anexo_avulso')
    def test_idempotencia_bloqueia_segundo_envio_do_mesmo_pacote(self, mock_resolver, mock_baixar, mock_smtp):
        mock_resolver.side_effect = self._mock_resolver({
            'att1': {'filename': 'Doc1.pdf', 'url': 'https://x/1'},
        })
        mock_baixar.return_value = PDF_VALIDO

        r1, s1 = m._enviar_email_avulso_core(
            'destino@exemplo.com', 'Assunto', 'Corpo',
            [{'origem': 'Envio', 'record_id': 'rec1', 'attachment_id': 'att1'}],
            dry_run=False,
        )
        self.assertEqual(s1, 200)
        self.assertEqual(r1['acao'], 'enviado')

        r2, s2 = m._enviar_email_avulso_core(
            'destino@exemplo.com', 'Assunto', 'Corpo',
            [{'origem': 'Envio', 'record_id': 'rec1', 'attachment_id': 'att1'}],
            dry_run=False,
        )
        self.assertEqual(s2, 409)
        self.assertEqual(r2['status'], 'duplicado')
        mock_smtp.assert_called_once()  # so a primeira chamada disparou de verdade

    def test_destinatario_invalido(self):
        resultado, status = m._enviar_email_avulso_core(
            'nao-e-email', 'Assunto', 'Corpo',
            [{'origem': 'Envio', 'record_id': 'rec1', 'attachment_id': 'att1'}],
            dry_run=True,
        )
        self.assertEqual(status, 400)
        self.assertEqual(resultado['erro'], 'destinatario_invalido')

    def test_lista_arquivos_vazia(self):
        resultado, status = m._enviar_email_avulso_core(
            'destino@exemplo.com', 'Assunto', 'Corpo', [], dry_run=True,
        )
        self.assertEqual(status, 400)
        self.assertEqual(resultado['erro'], 'lista_arquivos_vazia')


class TestRotaHTTPEmailAvulso(unittest.TestCase):
    def setUp(self):
        self.client = m.app.test_client()
        self.patcher = patch('app.EMAIL_WEBHOOK_KEY', 'chave-teste-avulso')
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_sem_api_key_retorna_401(self):
        resp = self.client.post('/email-avulso/enviar', json={
            'destinatario': 'a@b.com', 'assunto': 'x', 'corpo': 'y',
            'arquivos': [{'origem': 'Envio', 'record_id': 'r', 'attachment_id': 'a'}],
        })
        self.assertEqual(resp.status_code, 401)

    @patch('app._enviar_email_avulso_core')
    def test_com_api_key_chama_core_com_dry_run_default_true(self, mock_core):
        mock_core.return_value = ({'status': 'ok', 'dry_run': True}, 200)
        resp = self.client.post('/email-avulso/enviar',
                                 json={'destinatario': 'a@b.com', 'assunto': 'x', 'corpo': 'y',
                                       'arquivos': [{'origem': 'Envio', 'record_id': 'r', 'attachment_id': 'a'}]},
                                 headers={'X-API-KEY': 'chave-teste-avulso'})
        self.assertEqual(resp.status_code, 200)
        _, kwargs = mock_core.call_args
        self.assertTrue(kwargs['dry_run'])


if __name__ == '__main__':
    unittest.main()
