"""Testes isolados da rota direta de PDF pela Evolution."""

import base64
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault('MAGNATA_SESSION_SECRET_KEY', 'test')

import app as modulo


def pdf_base64(conteudo=b'conteudo'):
    return base64.b64encode(b'%PDF-1.7\n' + conteudo).decode('ascii')


class TestWhatsappEnviarDocumento(unittest.TestCase):
    def setUp(self):
        self.client = modulo.app.test_client()
        self.headers = {'X-API-KEY': 'test'}
        self.payload = {
            'numero': '(15) 98104-0400',
            'documento_base64': pdf_base64(),
            'nome_arquivo': 'Manual do Colaborador.pdf',
        }
        self.config = patch.multiple(
            modulo,
            EMAIL_WEBHOOK_KEY='test',
            EVOLUTION_API_KEY='test',
        )
        self.config.start()
        self.addCleanup(self.config.stop)

    @patch('app.requests.post')
    def test_options_nao_envia(self, post):
        resposta = self.client.options('/whatsapp/enviar-documento')
        self.assertEqual(resposta.status_code, 204)
        post.assert_not_called()

    @patch('app.requests.post')
    def test_chave_ausente(self, post):
        resposta = self.client.post('/whatsapp/enviar-documento', json=self.payload)
        self.assertEqual(resposta.status_code, 401)
        post.assert_not_called()

    @patch('app.requests.post')
    def test_chave_invalida(self, post):
        resposta = self.client.post(
            '/whatsapp/enviar-documento',
            json=self.payload,
            headers={'X-API-KEY': 'placeholder'},
        )
        self.assertEqual(resposta.status_code, 401)
        post.assert_not_called()

    def _rejeitado_sem_envio(self, payload):
        with patch('app.requests.post') as post:
            resposta = self.client.post(
                '/whatsapp/enviar-documento', json=payload, headers=self.headers
            )
            self.assertEqual(resposta.status_code, 400, resposta.get_json())
            post.assert_not_called()

    def test_numero_invalido(self):
        self._rejeitado_sem_envio({**self.payload, 'numero': '123'})

    def test_base64_ausente(self):
        payload = dict(self.payload)
        del payload['documento_base64']
        self._rejeitado_sem_envio(payload)

    def test_base64_invalido(self):
        self._rejeitado_sem_envio({**self.payload, 'documento_base64': '%%%invalido%%%'})

    def test_conteudo_nao_pdf(self):
        conteudo = base64.b64encode(b'arquivo qualquer').decode('ascii')
        self._rejeitado_sem_envio({**self.payload, 'documento_base64': conteudo})

    def test_arquivo_acima_do_limite(self):
        with patch.object(modulo, 'WHATSAPP_DOCUMENTO_MAX_BYTES', 15):
            self._rejeitado_sem_envio({**self.payload, 'documento_base64': pdf_base64(b'x' * 16)})

    def test_rejeita_campo_extra_e_nome_perigoso(self):
        self._rejeitado_sem_envio({**self.payload, 'url': 'https://exemplo.test/manual.pdf'})
        self._rejeitado_sem_envio({**self.payload, 'nome_arquivo': '../../manual.pdf'})
        self._rejeitado_sem_envio({**self.payload, 'nome_arquivo': 'manual.exe'})

    @patch('app._criar_registro')
    @patch('app._at_obter_registro')
    @patch('app.requests.post')
    def test_sucesso_simulado_sem_airtable_ou_assinatura(self, post, obter, criar):
        resposta_evolution = MagicMock(status_code=200)
        resposta_evolution.json.return_value = {'key': {'id': 'mensagem-simulada'}}
        post.return_value = resposta_evolution

        resposta = self.client.post(
            '/whatsapp/enviar-documento', json=self.payload, headers=self.headers
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.get_json(), {'status': 'ok', 'id': 'mensagem-simulada'})
        obter.assert_not_called()
        criar.assert_not_called()
        chamada = post.call_args
        self.assertEqual(
            chamada.args[0],
            'http://143.95.214.239:8080/message/sendMedia/magnata',
        )
        self.assertEqual(chamada.kwargs['timeout'], 90)
        self.assertEqual(chamada.kwargs['json'], {
            'number': '5515981040400',
            'mediatype': 'document',
            'mimetype': 'application/pdf',
            'media': self.payload['documento_base64'],
            'fileName': 'Manual_do_Colaborador.pdf',
        })

    @patch('app.requests.post')
    def test_falha_simulada_da_evolution_sem_expor_resposta(self, post):
        resposta_evolution = MagicMock(status_code=500)
        resposta_evolution.text = 'resposta sensível do fornecedor'
        post.return_value = resposta_evolution

        resposta = self.client.post(
            '/whatsapp/enviar-documento', json=self.payload, headers=self.headers
        )

        self.assertEqual(resposta.status_code, 502)
        self.assertEqual(
            resposta.get_json(),
            {'status': 'erro', 'erro': 'Falha ao enviar documento.'},
        )
        self.assertNotIn('sensível', resposta.get_data(as_text=True))
        post.assert_called_once()


if __name__ == '__main__':
    unittest.main()
