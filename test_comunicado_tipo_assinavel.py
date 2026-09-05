"""
Teste de regressão da extensão mínima: COMUNICADO passa a ser um tipo
documental assinável, reaproveitando 100% o fluxo genérico já existente
de /assinatura/gerar (_gerar_assinatura_core) — sem rota nova, sem motor
novo, sem alteração de Airtable nem de Evolution/WhatsApp.

Cobre exatamente os 3 pontos exigidos:
1. COMUNICADO está na whitelist (TIPOS_DOCUMENTO_VALIDOS);
2. COMUNICADO tem nome de exibição (NOMES_DOCUMENTOS);
3. _gerar_assinatura_core aceita COMUNICADO pelo mesmo fluxo genérico
   usado hoje por tipos como FICHA_EPI (nenhum tratamento especial).
"""
import hashlib
import unittest
from unittest.mock import patch, MagicMock

import app as m


class TestComunicadoTipoAssinavel(unittest.TestCase):

    def setUp(self):
        self.pdf_bytes = b'%PDF-1.4 conteudo de teste COMUNICADO'
        self.pdf_sha256 = hashlib.sha256(self.pdf_bytes).hexdigest()

    # 1) whitelist
    def test_comunicado_esta_na_whitelist(self):
        self.assertIn('COMUNICADO', m.TIPOS_DOCUMENTO_VALIDOS)

    # 2) nome de exibição
    def test_comunicado_tem_nome_de_exibicao(self):
        self.assertEqual(m.NOMES_DOCUMENTOS.get('COMUNICADO'), 'Comunicado')

    def _mock_arquivo_response(self):
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = {
            'id': 'recArquivoComunicado001',
            'fields': {
                m.F_ARQ_NOME: 'Comunicado Teste.pdf',
                m.F_ARQ_ATTACH: [{
                    'url': 'https://dl.airtable.com/fake/comunicado_teste.pdf',
                    'filename': 'Comunicado Teste.pdf',
                }],
            },
        }
        return resp

    def _mock_sem_idempotencia_previa(self):
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = {'records': []}
        return resp

    # 3) _gerar_assinatura_core aceita COMUNICADO pelo mesmo fluxo genérico
    @patch('app._evolution_enviar_documento')
    @patch('app._evolution_enviar_texto')
    @patch('app._carregar_documento_url')
    @patch('app.requests.get')
    @patch('app.requests.post')
    @patch('app._buscar_funcionario_nome_whatsapp')
    @patch('app._validar_configuracao_assinatura_v36')
    def test_gerar_assinatura_core_aceita_comunicado(
        self, mock_config, mock_nome_whats, mock_post, mock_get,
        mock_carregar_pdf, mock_ev_texto, mock_ev_doc,
    ):
        mock_config.return_value = (True, 'ok')
        mock_nome_whats.return_value = ('FUNCIONARIO TESTE COMUNICADO', '5515999998888')
        mock_carregar_pdf.return_value = self.pdf_bytes

        def fake_get(url, **kwargs):
            if m.TABLE_ARQUIVOS in url:
                return self._mock_arquivo_response()
            if m.TABLE_ASSINATURAS in url:
                return self._mock_sem_idempotencia_previa()
            raise AssertionError(f'GET inesperado: {url}')
        mock_get.side_effect = fake_get

        criados = {}

        def fake_post(url, headers=None, json=None, **kwargs):
            resp = MagicMock()
            resp.ok = True
            if m.TABLE_ASSINATURAS in url:
                criados['fields'] = json['fields']
                resp.json.return_value = {'id': 'recAssinaturaComunicado001', 'fields': json['fields']}
            else:
                resp.json.return_value = {'id': 'recArquivoNovo', 'fields': {}}
            return resp
        mock_post.side_effect = fake_post

        with patch('app._anexar_attachment', return_value=True):
            resultado, status = m._gerar_assinatura_core(
                funcionario_id='rechfevkZbWn55CJo',
                tipo_documento='COMUNICADO',
                arquivo_record_id='recArquivoComunicado001',
                disparar_whatsapp=False,
                dry_run=False,
            )

        # aceito pela whitelist e processado pelo fluxo genérico (mesmo
        # comportamento hoje observado para FICHA_EPI/RESCISAO/etc.)
        self.assertEqual(status, 200, resultado)
        self.assertEqual(resultado['status'], 'ok')
        self.assertEqual(resultado['tipo_documento'], 'COMUNICADO')
        self.assertEqual(criados['fields'][m.F_ASS_TIPO_DOC], 'COMUNICADO')
        self.assertEqual(criados['fields'][m.F_ASS_NOME], 'Comunicado')
        self.assertEqual(criados['fields'][m.F_ASS_STATUS], 'PREPARADO')
        self.assertIn(m.F_ASS_PDF_SHA256, criados['fields'])
        self.assertIn(m.F_ASS_CHAVE_IDEMPOTENCIA, criados['fields'])
        # nenhum WhatsApp real disparado (disparar_whatsapp=False)
        mock_ev_texto.assert_not_called()
        mock_ev_doc.assert_not_called()

    # tipo ainda fora da whitelist continua rejeitado (nenhuma regressão
    # na validação da whitelist causada por esta extensão)
    @patch('app._validar_configuracao_assinatura_v36')
    def test_tipo_desconhecido_continua_rejeitado(self, mock_config):
        mock_config.return_value = (True, 'ok')
        resultado, status = m._gerar_assinatura_core(
            funcionario_id='rechfevkZbWn55CJo',
            tipo_documento='TIPO_INEXISTENTE_XYZ',
            arquivo_record_id='recQualquer',
            disparar_whatsapp=False,
            dry_run=False,
        )
        self.assertEqual(status, 400)
        self.assertEqual(resultado['status'], 'erro')


if __name__ == '__main__':
    unittest.main()
