"""Testes de
`magnata_os/documental/modulo01/adapters/blueprint_painel_estatico.py`
-- o blueprint que serve os arquivos estaticos do painel (`frontend/`)
sob o prefixo `/painel`.

`flask.Flask.test_client()` sobre um app de TESTE isolado, construido
so aqui -- NUNCA o `app` real de `app.py`, nunca registrado nele (mesma
tecnica de test_magnata_os_documental_modulo01_blueprint_esteira.py).
Nenhuma rede/banco real envolvido -- so leitura de arquivo estatico
real de `frontend/` (ja existente no repositorio, sem dado pessoal).
"""
from __future__ import annotations

import json

import flask
import pytest

from magnata_os.documental.modulo01.adapters.blueprint_painel_estatico import (
    DIRETORIO_FRONTEND,
    painel_estatico_bp,
)


@pytest.fixture()
def cliente():
    app = flask.Flask(__name__)
    app.register_blueprint(painel_estatico_bp)
    return app.test_client()


def test_diretorio_frontend_resolve_para_pasta_real_do_repositorio():
    assert DIRETORIO_FRONTEND.is_dir()
    assert (DIRETORIO_FRONTEND / 'index.html').is_file()


def test_raiz_do_prefixo_serve_index_html(cliente):
    resposta = cliente.get('/painel/')
    assert resposta.status_code == 200
    assert b'<html' in resposta.data.lower()
    assert 'text/html' in resposta.content_type


def test_arquivo_estatico_existente_e_servido_com_content_type_correto(cliente):
    # frontend/src/nav.js existe de verdade no repositorio (modulo de
    # navegacao do painel, ja mesclado em main).
    resposta = cliente.get('/painel/src/nav.js')
    assert resposta.status_code == 200
    assert 'javascript' in resposta.content_type


def test_arquivo_css_existente_e_servido_com_content_type_correto(cliente):
    resposta = cliente.get('/painel/styles/tokens.css')
    assert resposta.status_code == 200
    assert 'text/css' in resposta.content_type


def test_caminho_inexistente_retorna_404_real(cliente):
    resposta = cliente.get('/painel/src/arquivo-que-nao-existe-de-verdade.js')
    assert resposta.status_code == 404


def test_nunca_serve_arquivo_fora_do_diretorio_frontend_via_traversal(cliente):
    # Tenta escapar de frontend/ para ler app.py (legado protegido) via
    # ../ -- send_from_directory tem que rejeitar (404), nunca servir.
    resposta = cliente.get('/painel/../app.py')
    assert resposta.status_code == 404
    assert b'Flask' not in resposta.data  # nunca o conteudo real de app.py

    resposta_codificada = cliente.get('/painel/%2e%2e/app.py')
    assert resposta_codificada.status_code == 404


def test_nunca_serve_arquivo_fora_do_diretorio_frontend_via_path_absoluto(cliente):
    # send_from_directory tambem precisa rejeitar um caminho que, apos
    # normalizado, aponte para fora de DIRETORIO_FRONTEND mesmo sem
    # ".." literal no texto da URL.
    resposta = cliente.get('/painel/..%2f..%2f..%2f..%2fapp.py')
    assert resposta.status_code == 404


def test_manifest_e_servido_com_content_type_de_manifesto_pwa(cliente):
    # frontend/manifest.webmanifest -- App Shell (instalabilidade),
    # servido pelo mesmo blueprint estatico, sem rota nova nem mudanca
    # em app.py (ver docs/decisoes/app-shell-manifest-pwa-v1.md).
    resposta = cliente.get('/painel/manifest.webmanifest')
    assert resposta.status_code == 200
    assert 'manifest+json' in resposta.content_type


def test_manifest_e_json_valido_e_referencia_so_icones_ja_existentes(cliente):
    resposta = cliente.get('/painel/manifest.webmanifest')
    manifesto = json.loads(resposta.data)

    assert manifesto['start_url'] == '/painel/'
    assert manifesto['scope'] == '/painel/'
    assert len(manifesto['icons']) >= 1
    for icone in manifesto['icons']:
        # Cada icone referenciado precisa existir de verdade em
        # frontend/ -- nunca um caminho inventado que renderizaria
        # icone quebrado na instalacao do app.
        assert (DIRETORIO_FRONTEND / icone['src']).is_file()


def test_index_html_referencia_o_manifest_e_define_theme_color(cliente):
    resposta = cliente.get('/painel/')
    html = resposta.data.decode('utf-8')
    assert 'rel="manifest" href="manifest.webmanifest"' in html
    assert 'name="theme-color"' in html
