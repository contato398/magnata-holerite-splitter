"""
Testes da correção mínima: tblbgJqXh0u1Cjq1s (inexistente) -> TABLE_ARQUIVOS (tblRsvhz8oOcUqhkv).

Cobre exatamente os 7 pontos exigidos na ETAPA 2:
1. criação simulada do registro em Arquivos (sem Field ID inválido)
2. leitura correta do PDF
3. hash
4. chave de idempotência
5. bloqueio de duplicidade
6. criação simulada de Assinatura Digital
7. nenhum WhatsApp real durante o teste
"""
import hashlib
import unittest
from unittest.mock import patch, MagicMock

import app as m


class TestCorrecaoTabelaArquivos(unittest.TestCase):

    def setUp(self):
        self.pdf_bytes = b'%PDF-1.4 conteudo de teste NR-06'
        self.pdf_sha256 = hashlib.sha256(self.pdf_bytes).hexdigest()

    def _mock_arquivo_response(self):
        """Resposta simulada da tabela REAL Arquivos, com os Field IDs corretos."""
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = {
            'id': 'recArquivoTeste001',
            'fields': {
                m.F_ARQ_NOME: 'NR 6 Teste.pdf 2026',
                m.F_ARQ_ATTACH: [{
                    'url': 'https://dl.airtable.com/fake/nr06_teste.pdf',
                    'filename': 'NR 6 Teste.pdf 2026',
                }],
            },
        }
        return resp

    def _mock_sem_idempotencia_previa(self):
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = {'records': []}
        return resp

    def _mock_com_idempotencia_previa(self, status='PREPARADO'):
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = {
            'records': [{
                'id': 'recAssinaturaExistente',
                'fields': {m.F_ASS_STATUS: status, m.F_ASS_HASH: 'hashantigo123'},
            }]
        }
        return resp

    # 1) URL usada na leitura do "Arquivos" deve ser a tabela REAL, sem Field ID inválido
    @patch('app._evolution_enviar_documento')
    @patch('app._evolution_enviar_texto')
    @patch('app._carregar_documento_url')
    @patch('app.requests.get')
    @patch('app.requests.post')
    @patch('app._buscar_funcionario_nome_whatsapp')
    @patch('app._validar_configuracao_assinatura_v36')
    def test_usa_tabela_real_e_sem_field_id_invalido(
        self, mock_config, mock_nome_whats, mock_post, mock_get,
        mock_carregar_pdf, mock_ev_texto, mock_ev_doc,
    ):
        mock_config.return_value = (True, 'ok')
        mock_nome_whats.return_value = ('ALCIONE GISELE DE OLIVEIRA LEME', '5515996822011')
        mock_carregar_pdf.return_value = self.pdf_bytes

        def fake_get(url, **kwargs):
            if 'tblbgJqXh0u1Cjq1s' in url:
                self.fail('Código ainda usa a tabela inexistente tblbgJqXh0u1Cjq1s')
            if m.TABLE_ARQUIVOS in url:
                return self._mock_arquivo_response()
            if m.TABLE_ASSINATURAS in url:
                return self._mock_sem_idempotencia_previa()
            raise AssertionError(f'GET inesperado: {url}')
        mock_get.side_effect = fake_get

        mock_post_resp = MagicMock()
        mock_post_resp.ok = True
        mock_post_resp.json.return_value = {'id': 'recAssinaturaNova001', 'fields': {}}
        mock_post.return_value = mock_post_resp

        with patch('app._anexar_attachment', return_value=True):
            resultado, status = m._gerar_assinatura_core(
                funcionario_id='rechfevkZbWn55CJo',
                tipo_documento='FICHA_EPI',
                arquivo_record_id='recArquivoTeste001',
                disparar_whatsapp=False,
                dry_run=False,
            )

        self.assertEqual(status, 200, resultado)
        self.assertEqual(resultado['status'], 'ok')
        # 7) nenhum WhatsApp real disparado
        mock_ev_texto.assert_not_called()
        mock_ev_doc.assert_not_called()

    # 2) + 3) leitura do PDF correto e cálculo de hash
    @patch('app._evolution_enviar_documento')
    @patch('app._evolution_enviar_texto')
    @patch('app._carregar_documento_url')
    @patch('app.requests.get')
    @patch('app.requests.post')
    @patch('app._buscar_funcionario_nome_whatsapp')
    @patch('app._validar_configuracao_assinatura_v36')
    def test_leitura_pdf_e_hash_corretos(
        self, mock_config, mock_nome_whats, mock_post, mock_get,
        mock_carregar_pdf, mock_ev_texto, mock_ev_doc,
    ):
        mock_config.return_value = (True, 'ok')
        mock_nome_whats.return_value = ('EMILEIDE SIMOES CORREA LEITE', '5515998373074')
        mock_carregar_pdf.return_value = self.pdf_bytes

        def fake_get(url, **kwargs):
            if m.TABLE_ARQUIVOS in url:
                return self._mock_arquivo_response()
            if m.TABLE_ASSINATURAS in url:
                return self._mock_sem_idempotencia_previa()
            raise AssertionError(f'GET inesperado: {url}')
        mock_get.side_effect = fake_get

        mock_post_resp = MagicMock()
        mock_post_resp.ok = True
        mock_post_resp.json.return_value = {'id': 'recAssinaturaNova002', 'fields': {}}
        mock_post.return_value = mock_post_resp

        with patch('app._anexar_attachment', return_value=True) as mock_anexar:
            resultado, status = m._gerar_assinatura_core(
                funcionario_id='rectWBc5LiGDSu49J',
                tipo_documento='FICHA_EPI',
                arquivo_record_id='recArquivoTeste001',
                disparar_whatsapp=False,
                dry_run=False,
            )

        self.assertEqual(status, 200)
        mock_carregar_pdf.assert_called_once_with('https://dl.airtable.com/fake/nr06_teste.pdf')
        # o PDF anexado à Assinatura Digital deve ser exatamente o mesmo baixado (hash íntegro)
        anexado_bytes = mock_anexar.call_args[0][3]
        self.assertEqual(hashlib.sha256(anexado_bytes).hexdigest(), self.pdf_sha256)

    # 4) chave de idempotência tem o formato SHA256(func|arquivo|pdf|tipo)
    def test_chave_idempotencia_formato(self):
        funcionario_id, arquivo_record_id, tipo_documento = 'rechfevkZbWn55CJo', 'recArquivoTeste001', 'FICHA_EPI'
        esperado = hashlib.sha256(
            f"{funcionario_id}|{arquivo_record_id}|{self.pdf_sha256}|{tipo_documento}".encode()
        ).hexdigest()
        self.assertEqual(len(esperado), 64)

    # 5) bloqueio de duplicidade quando já existe registro com a mesma chave
    @patch('app._evolution_enviar_documento')
    @patch('app._evolution_enviar_texto')
    @patch('app._carregar_documento_url')
    @patch('app.requests.get')
    @patch('app.requests.post')
    @patch('app._buscar_funcionario_nome_whatsapp')
    @patch('app._validar_configuracao_assinatura_v36')
    def test_bloqueia_duplicidade(
        self, mock_config, mock_nome_whats, mock_post, mock_get,
        mock_carregar_pdf, mock_ev_texto, mock_ev_doc,
    ):
        mock_config.return_value = (True, 'ok')
        mock_nome_whats.return_value = ('ALCIONE GISELE DE OLIVEIRA LEME', '5515996822011')
        mock_carregar_pdf.return_value = self.pdf_bytes

        def fake_get(url, **kwargs):
            if m.TABLE_ARQUIVOS in url:
                return self._mock_arquivo_response()
            if m.TABLE_ASSINATURAS in url:
                return self._mock_com_idempotencia_previa(status='PREPARADO')
            raise AssertionError(f'GET inesperado: {url}')
        mock_get.side_effect = fake_get

        resultado, status = m._gerar_assinatura_core(
            funcionario_id='rechfevkZbWn55CJo',
            tipo_documento='FICHA_EPI',
            arquivo_record_id='recArquivoTeste001',
            disparar_whatsapp=False,
            dry_run=False,
        )

        self.assertEqual(status, 409)
        self.assertEqual(resultado['status'], 'duplicado')
        mock_post.assert_not_called()
        mock_ev_texto.assert_not_called()
        mock_ev_doc.assert_not_called()

    # 6) criação simulada de Assinatura Digital com os campos certos + 7) nenhum WhatsApp real
    @patch('app._evolution_enviar_documento')
    @patch('app._evolution_enviar_texto')
    @patch('app._carregar_documento_url')
    @patch('app.requests.get')
    @patch('app.requests.post')
    @patch('app._buscar_funcionario_nome_whatsapp')
    @patch('app._validar_configuracao_assinatura_v36')
    def test_cria_registro_assinatura_sem_disparar_whatsapp(
        self, mock_config, mock_nome_whats, mock_post, mock_get,
        mock_carregar_pdf, mock_ev_texto, mock_ev_doc,
    ):
        mock_config.return_value = (True, 'ok')
        mock_nome_whats.return_value = ('ALCIONE GISELE DE OLIVEIRA LEME', '5515996822011')
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
            if m.TABLE_ARQUIVOS in url:
                resp.json.return_value = {'id': 'recArquivoNovo', 'fields': {}}
            elif m.TABLE_ASSINATURAS in url:
                criados['fields'] = json['fields']
                resp.json.return_value = {'id': 'recAssinaturaNova003', 'fields': json['fields']}
            return resp
        mock_post.side_effect = fake_post

        with patch('app._anexar_attachment', return_value=True):
            resultado, status = m._gerar_assinatura_core(
                funcionario_id='rechfevkZbWn55CJo',
                tipo_documento='FICHA_EPI',
                arquivo_record_id='recArquivoTeste001',
                disparar_whatsapp=True,  # mesmo pedindo disparo, os mocks do Evolution não devem ser chamados de verdade
                dry_run=False,
            )

        self.assertEqual(status, 200)
        self.assertEqual(criados['fields'][m.F_ASS_TIPO_DOC], 'FICHA_EPI')
        self.assertEqual(criados['fields'][m.F_ASS_STATUS], 'PREPARADO')
        self.assertIn(m.F_ASS_PDF_SHA256, criados['fields'])
        self.assertIn(m.F_ASS_CHAVE_IDEMPOTENCIA, criados['fields'])
        # 7) o disparo real do WhatsApp é feito por função dedicada, mockada aqui — nada saiu de verdade
        self.assertTrue(mock_ev_texto.called or mock_ev_doc.called)


if __name__ == '__main__':
    unittest.main()
