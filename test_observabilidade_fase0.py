"""
Testes da Fase 0 — Observabilidade do Módulo 01 (Ingestão).

Objetivo: comprovar que a instrumentação de observabilidade não altera em
nada o comportamento já existente de /separar — mesmo status HTTP, mesmo
corpo de resposta, nenhuma escrita real no Airtable, nenhum efeito
colateral novo. A observabilidade só deve acrescentar logs.

Convenção alinhada a test_separar_obrigatorios.py (unittest + test_client).
Todas as integrações externas (Airtable, upload, fila) são mockadas —
nenhuma escrita real ocorre.
"""

import json
import logging
import os
import unittest
from io import BytesIO
from unittest.mock import patch, MagicMock

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

from app import app, F_PROC_ARQUIVOS
from src.observability import (
    ENV_FLAG_OBSERVABILIDADE,
    is_observability_enabled,
    nome_arquivo_seguro,
    _classificar_resultado,
)


def criar_cliente_teste():
    app.config['TESTING'] = True
    return app.test_client()


def criar_pdf_valido_minimo():
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 750, "HOLERITE - MAIO 2026")
    c.drawString(100, 730, "CPF: 123.456.789-00")
    c.save()
    buf.seek(0)
    return buf.getvalue()


def _resposta_airtable_registro_ok():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        'fields': {F_PROC_ARQUIVOS: [{'url': 'https://dl.airtable.com/fake/holerite.pdf'}]}
    }
    return resp


class TestObservabilidadeNaoAlteraComportamento(unittest.TestCase):
    """
    Cada teste aqui verifica que status HTTP e corpo de resposta continuam
    exatamente os documentados em MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1.md
    §2, com a observabilidade ativa (padrão).
    """

    def setUp(self):
        self.client = criar_cliente_teste()
        os.environ.pop(ENV_FLAG_OBSERVABILIDADE, None)  # garante padrão (ativada)

    def test_upload_manual_valido_sucesso_real_202(self):
        """Upload manual válido (mesmo fluxo usado por Make.com) → 202, success=true."""
        with patch('app.requests.get', return_value=_resposta_airtable_registro_ok()), \
             patch('app._fazer_upload_pdf_airtable', return_value=True), \
             patch('app._enfileirar_processamento', return_value=(True, 'task-123')):
            resp = self.client.post(
                '/separar',
                data={
                    'pdf': (BytesIO(criar_pdf_valido_minimo()), 'holerite.pdf'),
                    'processar_arquivo_record_id': 'recABC123',
                },
                content_type='multipart/form-data',
            )
        corpo = resp.get_json()
        self.assertEqual(resp.status_code, 202)
        self.assertTrue(corpo['success'])
        self.assertEqual(corpo['task_id'], 'task-123')

    def test_separar_arquivo_ausente_http_200_success_false(self):
        resp = self.client.post(
            '/separar',
            data={'processar_arquivo_record_id': 'recABC123'},
            content_type='multipart/form-data',
        )
        corpo = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(corpo['success'])
        self.assertEqual(corpo['error_code'], 'ATTACHMENT_NOT_FOUND')

    def test_separar_filename_ausente_http_200_success_false(self):
        resp = self.client.post(
            '/separar',
            data={
                'pdf': (BytesIO(criar_pdf_valido_minimo()), ''),
                'processar_arquivo_record_id': 'recABC123',
            },
            content_type='multipart/form-data',
        )
        corpo = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(corpo['success'])
        self.assertEqual(corpo['error_code'], 'PDF_NO_FILENAME')

    def test_separar_extensao_invalida_http_200_success_false(self):
        resp = self.client.post(
            '/separar',
            data={
                'pdf': (BytesIO(criar_pdf_valido_minimo()), 'holerite.txt'),
                'processar_arquivo_record_id': 'recABC123',
            },
            content_type='multipart/form-data',
        )
        corpo = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(corpo['success'])
        self.assertEqual(corpo['error_code'], 'PDF_INVALID_EXTENSION')

    def test_separar_record_id_invalido_http_400(self):
        resp = self.client.post(
            '/separar',
            data={'pdf': (BytesIO(criar_pdf_valido_minimo()), 'holerite.pdf')},
            content_type='multipart/form-data',
        )
        self.assertEqual(resp.status_code, 400)

    def test_excecao_inesperada_nao_e_convertida_em_sucesso(self):
        """Exceção real dentro da view continua retornando 500 — observabilidade
        não engole nem mascara a exceção.

        A checagem de registro no Airtable (app.requests.get) tem try/except
        próprio que converte falha em 200/AIRTABLE_CHECK_FAILED — por isso essa
        chamada é mockada para suceder, e a exceção é forçada no upload
        (_fazer_upload_pdf_airtable), ponto que não tem try/except local e por
        isso propaga para o except Exception externo da view (→ 500)."""
        with patch('app.requests.get', return_value=_resposta_airtable_registro_ok()), \
             patch('app._fazer_upload_pdf_airtable', side_effect=RuntimeError('falha simulada')):
            resp = self.client.post(
                '/separar',
                data={
                    'pdf': (BytesIO(criar_pdf_valido_minimo()), 'holerite.pdf'),
                    'processar_arquivo_record_id': 'recABC123',
                },
                content_type='multipart/form-data',
            )
        # A view já tem try/except próprio que converte exceção em 500 —
        # a observabilidade não deve mudar isso.
        self.assertEqual(resp.status_code, 500)
        corpo = resp.get_json()
        self.assertIn('error', corpo)

    def test_observabilidade_desativada_mesmo_comportamento(self):
        """Com a flag desativada, a resposta deve ser idêntica à ativada."""
        os.environ[ENV_FLAG_OBSERVABILIDADE] = 'false'
        try:
            resp = self.client.post(
                '/separar',
                data={'processar_arquivo_record_id': 'recABC123'},
                content_type='multipart/form-data',
            )
        finally:
            os.environ.pop(ENV_FLAG_OBSERVABILIDADE, None)

        corpo = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(corpo['success'])
        self.assertEqual(corpo['error_code'], 'ATTACHMENT_NOT_FOUND')


class TestObservabilidadeCorrelacaoELogs(unittest.TestCase):

    def setUp(self):
        self.client = criar_cliente_teste()
        os.environ.pop(ENV_FLAG_OBSERVABILIDADE, None)

    def test_correlation_id_preexistente_e_preservado(self):
        with self.assertLogs('ingestion.observability', level='INFO') as captura:
            self.client.post(
                '/separar',
                data={'processar_arquivo_record_id': 'recABC123'},
                content_type='multipart/form-data',
                headers={'X-Request-ID': 'meu-id-de-correlacao-123'},
            )

        linhas_inicio = [l for l in captura.output if 'ingestion_observability' in l and '"evento": "inicio"' in l]
        self.assertTrue(linhas_inicio, 'nenhum log de início capturado')
        payload = json.loads(linhas_inicio[0].split('ingestion_observability ', 1)[1])
        self.assertEqual(payload['correlation_id'], 'meu-id-de-correlacao-123')
        self.assertTrue(payload['correlation_preexistente'])

    def test_correlation_id_gerado_quando_ausente_e_igual_em_inicio_e_fim(self):
        with self.assertLogs('ingestion.observability', level='INFO') as captura:
            self.client.post(
                '/separar',
                data={'processar_arquivo_record_id': 'recABC123'},
                content_type='multipart/form-data',
            )

        eventos = []
        for linha in captura.output:
            if 'ingestion_observability' not in linha:
                continue
            eventos.append(json.loads(linha.split('ingestion_observability ', 1)[1]))

        ids = {e['correlation_id'] for e in eventos}
        self.assertEqual(len(ids), 1, 'correlation_id deve ser o mesmo em início e fim')

    def test_classificacao_observacional_falha_funcional_http_200(self):
        with self.assertLogs('ingestion.observability', level='INFO') as captura:
            self.client.post(
                '/separar',
                data={'processar_arquivo_record_id': 'recABC123'},
                content_type='multipart/form-data',
            )

        linhas_fim = [l for l in captura.output if '"evento": "fim"' in l]
        payload = json.loads(linhas_fim[0].split('ingestion_observability ', 1)[1])
        self.assertEqual(payload['status_http'], 200)
        self.assertFalse(payload['success_corpo'])
        self.assertEqual(payload['classificacao_observacional'], 'falha_funcional_http_200')
        self.assertEqual(payload['codigo_erro'], 'ATTACHMENT_NOT_FOUND')

    def test_nenhum_dado_sensivel_vaza_no_log(self):
        conteudo_pdf = criar_pdf_valido_minimo()
        with self.assertLogs('ingestion.observability', level='INFO') as captura:
            self.client.post(
                '/separar',
                data={
                    'pdf': (BytesIO(conteudo_pdf), 'holerite.pdf'),
                    'processar_arquivo_record_id': 'recABC123',
                },
                content_type='multipart/form-data',
                headers={'Authorization': 'Bearer super-secreto-nao-pode-vazar'},
            )

        texto_completo = '\n'.join(captura.output)
        self.assertNotIn('super-secreto-nao-pode-vazar', texto_completo)
        self.assertNotIn('CPF: 123.456.789-00', texto_completo)
        # bytes do PDF nunca aparecem como texto no log
        self.assertNotIn('%PDF', texto_completo)


class TestUtilitariosObservabilidade(unittest.TestCase):
    """Testes unitários puros do módulo src/observability.py."""

    def test_flag_padrao_ativada(self):
        os.environ.pop(ENV_FLAG_OBSERVABILIDADE, None)
        self.assertTrue(is_observability_enabled())

    def test_flag_desativada_com_valores_reconhecidos(self):
        for valor in ('false', '0', 'off', 'no'):
            os.environ[ENV_FLAG_OBSERVABILIDADE] = valor
            self.assertFalse(is_observability_enabled(), f'valor {valor!r} deveria desativar')
        os.environ.pop(ENV_FLAG_OBSERVABILIDADE, None)

    def test_nome_arquivo_seguro_sanitiza(self):
        self.assertEqual(nome_arquivo_seguro('../../etc/passwd'), '.._.._etc_passwd')
        self.assertEqual(nome_arquivo_seguro(''), '(sem nome)')
        self.assertEqual(nome_arquivo_seguro('holerite maio.pdf'), 'holerite_maio.pdf')

    def test_classificar_resultado(self):
        self.assertEqual(_classificar_resultado(202, {'success': True}), 'sucesso_real')
        self.assertEqual(_classificar_resultado(200, {'success': False}), 'falha_funcional_http_200')
        self.assertEqual(_classificar_resultado(400, {'success': False}), 'falha_http')
        self.assertEqual(_classificar_resultado(200, None), 'resultado_incerto')


if __name__ == '__main__':
    unittest.main()
