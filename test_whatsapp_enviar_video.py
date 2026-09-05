"""Testes isolados da rota dedicada de envio de vídeo pela Evolution."""

import base64
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault('MAGNATA_SESSION_SECRET_KEY', 'test')

import app as modulo


def mp4_base64(conteudo=b'dados'):
    arquivo = (16).to_bytes(4, 'big') + b'ftyp' + b'isom' + b'\x00\x00\x00\x00' + conteudo
    return base64.b64encode(arquivo).decode('ascii')


class TestWhatsappEnviarVideo(unittest.TestCase):
    def setUp(self):
        self.client = modulo.app.test_client()
        self.headers = {'X-API-KEY': 'test'}
        self.payload = {
            'numero': '(15) 98104-0400',
            'video_base64': mp4_base64(),
            'nome_arquivo': 'benefícios vídeo.mp4',
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
        resposta = self.client.options('/whatsapp/enviar-video')
        self.assertEqual(resposta.status_code, 204)
        post.assert_not_called()

    @patch('app.requests.post')
    def test_chave_ausente(self, post):
        resposta = self.client.post('/whatsapp/enviar-video', json=self.payload)
        self.assertEqual(resposta.status_code, 401)
        post.assert_not_called()

    @patch('app.requests.post')
    def test_chave_invalida(self, post):
        resposta = self.client.post(
            '/whatsapp/enviar-video', json=self.payload, headers={'X-API-KEY': 'placeholder'}
        )
        self.assertEqual(resposta.status_code, 401)
        post.assert_not_called()

    def _rejeitado_sem_envio(self, payload):
        with patch('app.requests.post') as post:
            resposta = self.client.post('/whatsapp/enviar-video', json=payload, headers=self.headers)
            self.assertEqual(resposta.status_code, 400, resposta.get_json())
            post.assert_not_called()

    def test_numero_invalido(self):
        self._rejeitado_sem_envio({**self.payload, 'numero': '123'})

    def test_base64_ausente(self):
        payload = dict(self.payload)
        del payload['video_base64']
        self._rejeitado_sem_envio(payload)

    def test_base64_invalido(self):
        self._rejeitado_sem_envio({**self.payload, 'video_base64': '%%%nao-base64%%%'})

    def test_conteudo_nao_mp4(self):
        conteudo = base64.b64encode(b'conteudo qualquer').decode('ascii')
        self._rejeitado_sem_envio({**self.payload, 'video_base64': conteudo})

    def test_arquivo_acima_do_limite(self):
        with patch.object(modulo, 'WHATSAPP_VIDEO_MAX_BYTES', 15):
            self._rejeitado_sem_envio({**self.payload, 'video_base64': mp4_base64(b'x' * 16)})

    def test_rejeita_url_campo_extra_e_nome_perigoso(self):
        self._rejeitado_sem_envio({**self.payload, 'url': 'http://exemplo.test/video.mp4'})
        self._rejeitado_sem_envio({**self.payload, 'nome_arquivo': '../../video.mp4'})

    @patch('app.requests.post')
    def test_sucesso_simulado(self, post):
        resposta_evolution = MagicMock(status_code=201)
        resposta_evolution.json.return_value = {'key': {'id': 'mensagem-simulada'}}
        post.return_value = resposta_evolution

        resposta = self.client.post('/whatsapp/enviar-video', json=self.payload, headers=self.headers)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.get_json(), {'status': 'ok', 'id': 'mensagem-simulada'})
        chamada = post.call_args
        self.assertEqual(chamada.args[0], 'http://143.95.214.239:8080/message/sendMedia/magnata')
        self.assertEqual(chamada.kwargs['timeout'], 90)
        self.assertEqual(chamada.kwargs['json'], {
            'number': '5515981040400',
            'mediatype': 'video',
            'mimetype': 'video/mp4',
            'media': self.payload['video_base64'],
            'fileName': 'beneficios_video.mp4',
        })

    @patch('app.requests.post')
    def test_sucesso_com_legenda_envia_caption(self, post):
        resposta_evolution = MagicMock(status_code=201)
        resposta_evolution.json.return_value = {'key': {'id': 'mensagem-com-legenda'}}
        post.return_value = resposta_evolution

        payload = {**self.payload, 'legenda': 'Benefícios Magnata'}
        resposta = self.client.post('/whatsapp/enviar-video', json=payload, headers=self.headers)

        self.assertEqual(resposta.status_code, 200)
        chamada = post.call_args
        self.assertEqual(chamada.kwargs['json']['caption'], 'Benefícios Magnata')
        self.assertEqual(chamada.kwargs['json']['fileName'], 'beneficios_video.mp4')

    def test_legenda_nao_string_e_rejeitada_sem_envio(self):
        self._rejeitado_sem_envio({**self.payload, 'legenda': ['invalida']})

    @patch('app.requests.post')
    def test_falha_simulada_da_evolution_sem_expor_resposta(self, post):
        resposta_evolution = MagicMock(status_code=500)
        resposta_evolution.text = 'segredo retornado pelo fornecedor'
        post.return_value = resposta_evolution

        resposta = self.client.post('/whatsapp/enviar-video', json=self.payload, headers=self.headers)

        self.assertEqual(resposta.status_code, 502)
        self.assertEqual(resposta.get_json(), {'status': 'erro', 'erro': 'Falha ao enviar vídeo.'})
        self.assertNotIn('segredo', resposta.get_data(as_text=True))
        post.assert_called_once()


if __name__ == '__main__':
    unittest.main()
