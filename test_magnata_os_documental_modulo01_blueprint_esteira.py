"""Testes de
`magnata_os/documental/modulo01/adapters/blueprint_esteira.py` -- o
adapter HTTP que expoe a API de esteira (Modulo 01, Fase 4) para o
painel operacional (Fase 5).

`flask.Flask.test_client()` sobre um app de TESTE isolado, construido
so aqui -- NUNCA o `app` real de `app.py`, nunca registrado nele (mesma
tecnica de test_magnata_os_autenticacao_sessao_e_blueprint_v1.py).
Nenhum teste aqui acessa Postgres, S3, Airtable ou rede real -- o
contexto da API e sempre um ContextoApi com repositorios EM MEMORIA,
injetado via `configurar_fabrica_contexto`.

Dado sintetico apenas -- nenhum CPF, nome de funcionario real ou
holerite real (ver /CLAUDE.md §6, LGPD)."""
from __future__ import annotations

from datetime import datetime, timezone

import flask
import pytest

from magnata_os.autenticacao.adapters.blueprint_login import auth_bp
from magnata_os.autenticacao.adapters.sessao import configurar_sessao_segura
from magnata_os.documental.modulo01.adapters.blueprint_esteira import (
    BancoNaoConfigurado,
    configurar_fabrica_contexto,
    esteira_bp,
    obter_contexto_api,
)
from magnata_os.documental.modulo01.api.handlers import ContextoApi
from magnata_os.documental.modulo01.dominio import Documento, StatusDocumento
from magnata_os.documental.modulo01.dominio_esteira import (
    EstadoEsteiraDocumento,
    EtapaEsteira,
    LoteDocumental,
    SituacaoEsteira,
)
from magnata_os.documental.modulo01.repositorio import RepositorioDocumentosEmMemoria, RepositorioHistoricoEmMemoria
from magnata_os.documental.modulo01.repositorio_esteira import (
    RepositorioEstadosEsteiraEmMemoria,
    RepositorioLotesEmMemoria,
)

_CLIENT_ID = 'client-id-sintetico.apps.googleusercontent.com'
_EMAIL_GESTOR = 'gestor@exemplo.com'
_EMAIL_OPERACIONAL = 'operador@exemplo.com'
_EMAIL_FORA_DA_ALLOWLIST = 'estranho@exemplo.com'

_AGORA = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


def _documento_sintetico(doc_id: str, lote_id=None) -> Documento:
    return Documento(
        documento_id=doc_id,
        arquivo_original=f's3://bucket-teste/{doc_id}.pdf',
        nome_original=f'{doc_id}.pdf',
        mime_type='application/pdf',
        tamanho=1234,
        hash_sha256=f'hash-{doc_id}',
        origem='UPLOAD_MANUAL',
        recebido_em=_AGORA,
        lote_id=lote_id,
        status=StatusDocumento.RECEBIDO,
        correlation_id=f'corr-{doc_id}',
        criado_em=_AGORA,
        atualizado_em=_AGORA,
    )


def _estado_sintetico(doc_id: str, situacao: SituacaoEsteira, lote_id=None) -> EstadoEsteiraDocumento:
    return EstadoEsteiraDocumento(
        documento_id=doc_id,
        lote_id=lote_id,
        etapa_atual=EtapaEsteira.CLASSIFICACAO,
        situacao=situacao,
        motivo_bloqueio=None,
        proxima_acao=None,
        entrou_na_etapa_em=_AGORA,
        atualizado_em=_AGORA,
        correlation_id=f'corr-{doc_id}',
    )


def _contexto_com_um_documento() -> ContextoApi:
    repo_docs = RepositorioDocumentosEmMemoria()
    repo_hist = RepositorioHistoricoEmMemoria()
    repo_lotes = RepositorioLotesEmMemoria()
    repo_estados = RepositorioEstadosEsteiraEmMemoria()

    repo_docs.salvar(_documento_sintetico('doc-1'))
    repo_estados.salvar(_estado_sintetico('doc-1', SituacaoEsteira.EM_PROCESSAMENTO))

    return ContextoApi(
        repositorio_documentos=repo_docs,
        repositorio_historico=repo_hist,
        repositorio_lotes=repo_lotes,
        repositorio_estados=repo_estados,
        relogio=lambda: _AGORA,
    )


def _app_teste(monkeypatch, verificador_fake, fabrica_contexto=None):
    app = flask.Flask('magnata_teste_esteira')
    configurar_sessao_segura(app, secret_key='fake', secure=False)
    app.register_blueprint(auth_bp)
    app.register_blueprint(esteira_bp)

    monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_ID', _CLIENT_ID)
    monkeypatch.setenv(
        'MAGNATA_ADMIN_ALLOWLIST', f'{_EMAIL_GESTOR}:GESTOR,{_EMAIL_OPERACIONAL}:OPERACIONAL')

    import magnata_os.autenticacao.provedor_google_oidc as provedor
    monkeypatch.setattr(provedor, 'verificar_id_token_google', verificador_fake)
    import magnata_os.autenticacao.adapters.blueprint_login as blueprint_mod
    monkeypatch.setattr(blueprint_mod, 'verificar_id_token_google', verificador_fake)

    if fabrica_contexto is not False:
        configurar_fabrica_contexto(fabrica_contexto or _contexto_com_um_documento)
    yield app
    configurar_fabrica_contexto(None)


@pytest.fixture
def app_com_dado(monkeypatch):
    yield from _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR))


def _fake_verificar(email, sub='sub-sintetico-1'):
    def _v(token, client_id=None, **kwargs):
        if token != 'test':
            from magnata_os.autenticacao.provedor_google_oidc import TokenGoogleInvalido
            raise TokenGoogleInvalido('token invalido (fake)')
        from magnata_os.autenticacao.provedor_google_oidc import IdentidadeGoogleVerificada
        return IdentidadeGoogleVerificada(email=email, sub=sub)
    return _v


def _logar(cliente, email='gestor@exemplo.com'):
    resp = cliente.post('/auth/login', json={'id_token': 'test'})
    assert resp.status_code == 200
    return resp.get_json()


# ============================================================================
# sem sessao -- nunca degrada para 200
# ============================================================================

def test_resumo_sem_sessao_401(app_com_dado):
    cliente = app_com_dado.test_client()
    resp = cliente.get('/magnata-os/documental/esteira/resumo')
    assert resp.status_code == 401


def test_documentos_sem_sessao_401(app_com_dado):
    cliente = app_com_dado.test_client()
    resp = cliente.get('/magnata-os/documental/documentos')
    assert resp.status_code == 401


def test_bloqueios_sem_sessao_401(app_com_dado):
    cliente = app_com_dado.test_client()
    resp = cliente.get('/magnata-os/documental/bloqueios')
    assert resp.status_code == 401


# ============================================================================
# com sessao -- dado real do ContextoApi injetado, nunca mock
# ============================================================================

def test_resumo_com_sessao_devolve_dado_real(app_com_dado):
    cliente = app_com_dado.test_client()
    _logar(cliente)
    resp = cliente.get('/magnata-os/documental/esteira/resumo')
    assert resp.status_code == 200
    corpo = resp.get_json()
    assert corpo['total_documentos'] == 1
    assert corpo['total_por_situacao'].get('EM_PROCESSAMENTO') == 1


def test_documentos_com_sessao_lista_documento_sintetico(app_com_dado):
    cliente = app_com_dado.test_client()
    _logar(cliente)
    resp = cliente.get('/magnata-os/documental/documentos')
    assert resp.status_code == 200
    corpo = resp.get_json()
    assert corpo['total_itens'] == 1
    item = corpo['itens'][0]
    assert item['documento_id'] == 'doc-1'
    # LGPD -- nenhum campo de CPF/nome de funcionario no contrato exposto.
    assert 'cpf' not in item
    assert 'nome_funcionario' not in item


def test_documento_inexistente_404(app_com_dado):
    cliente = app_com_dado.test_client()
    _logar(cliente)
    resp = cliente.get('/magnata-os/documental/documentos/nao-existe')
    assert resp.status_code == 404
    assert resp.get_json()['codigo'] == 'DOCUMENTO_NAO_ENCONTRADO'


def test_filtro_situacao_invalido_400(app_com_dado):
    cliente = app_com_dado.test_client()
    _logar(cliente)
    resp = cliente.get('/magnata-os/documental/documentos?situacao=NAO_EXISTE')
    assert resp.status_code == 400
    assert resp.get_json()['codigo'] == 'FILTRO_INVALIDO'


def test_paginacao_invalida_400(app_com_dado):
    cliente = app_com_dado.test_client()
    _logar(cliente)
    resp = cliente.get('/magnata-os/documental/documentos?tamanho_pagina=0')
    assert resp.status_code == 400
    assert resp.get_json()['codigo'] == 'PAGINACAO_INVALIDA'


# ============================================================================
# perfil operacional -- historico exige PERMISSAO_AUDITORIA
# ============================================================================

def test_historico_documento_perfil_operacional_403(monkeypatch):
    for app in _app_teste(monkeypatch, _fake_verificar(_EMAIL_OPERACIONAL)):
        cliente = app.test_client()
        _logar(cliente, _EMAIL_OPERACIONAL)
        resp = cliente.get('/magnata-os/documental/documentos/doc-1/historico')
        assert resp.status_code == 403
        assert resp.get_json()['codigo'] == 'PERMISSAO_NEGADA'


def test_email_fora_da_allowlist_nao_consegue_logar(monkeypatch):
    for app in _app_teste(monkeypatch, _fake_verificar(_EMAIL_FORA_DA_ALLOWLIST)):
        cliente = app.test_client()
        resp = cliente.post('/auth/login', json={'id_token': 'test'})
        assert resp.status_code == 403
        resp2 = cliente.get('/magnata-os/documental/esteira/resumo')
        assert resp2.status_code == 401


# ============================================================================
# sem DATABASE_URL configurada -- nunca finge dado real (503, nao mock)
# ============================================================================

def test_sem_database_url_devolve_503_nunca_dado_mockado(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    for app in _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR), fabrica_contexto=False):
        cliente = app.test_client()
        _logar(cliente)
        resp = cliente.get('/magnata-os/documental/esteira/resumo')
        assert resp.status_code == 503
        assert resp.get_json()['codigo'] == 'BANCO_NAO_CONFIGURADO'
