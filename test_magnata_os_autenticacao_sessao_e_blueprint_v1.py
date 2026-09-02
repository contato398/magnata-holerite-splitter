"""Testes de `magnata_os/autenticacao/adapters/sessao.py` +
`adapters/blueprint_login.py` -- via `flask.Flask.test_client()` sobre
um app de TESTE isolado, construído só neste arquivo (NUNCA o `app`
real de `app.py`, nunca registrado nele). `GOOGLE_OAUTH_CLIENT_ID`/
`MAGNATA_ADMIN_ALLOWLIST` são sempre valores sintéticos injetados via
`monkeypatch`/`ambiente` -- nenhuma chamada de rede real ao Google em
nenhum teste."""
import flask
import pytest

from magnata_os.autenticacao.adapters.blueprint_login import auth_bp, exigir_csrf, exigir_sessao_com_perfil
from magnata_os.autenticacao.adapters.sessao import configurar_sessao_segura
from magnata_os.autenticacao.identidade import Perfil

_CLIENT_ID = 'client-id-sintetico.apps.googleusercontent.com'
_EMAIL_GESTOR = 'gestor@exemplo.com'
_EMAIL_OPERACIONAL = 'operador@exemplo.com'
_EMAIL_FORA_DA_ALLOWLIST = 'estranho@exemplo.com'


def _app_teste(monkeypatch, verificador_fake):
    """App Flask isolado, nunca `app.py`. `verificador_fake` substitui
    a chamada real ao Google (`google.oauth2.id_token.verify_oauth2_token`)
    -- injetado via monkeypatch no MÓDULO do provedor, mesma técnica já
    usada em outros pontos deste repositório para nunca depender de
    rede real."""
    app = flask.Flask('magnata_teste_autenticacao')
    configurar_sessao_segura(
        app, secret_key='fake', secure=False,  # secure=False só porque o test_client fala http, nunca https
    )
    app.register_blueprint(auth_bp)

    monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_ID', _CLIENT_ID)
    monkeypatch.setenv(
        'MAGNATA_ADMIN_ALLOWLIST', f'{_EMAIL_GESTOR}:GESTOR,{_EMAIL_OPERACIONAL}:OPERACIONAL')

    import magnata_os.autenticacao.provedor_google_oidc as provedor
    monkeypatch.setattr(provedor, 'verificar_id_token_google', verificador_fake)
    # blueprint_login.py importou a funcao original por nome -- patch la tambem
    import magnata_os.autenticacao.adapters.blueprint_login as blueprint_mod
    monkeypatch.setattr(blueprint_mod, 'verificar_id_token_google', verificador_fake)

    return app


def _fake_verificar(email, sub='sub-sintetico-1'):
    def _v(token, client_id=None, **kwargs):
        if token != 'token-valido':
            from magnata_os.autenticacao.provedor_google_oidc import TokenGoogleInvalido
            raise TokenGoogleInvalido('token invalido (fake)')
        from magnata_os.autenticacao.provedor_google_oidc import IdentidadeGoogleVerificada
        return IdentidadeGoogleVerificada(email=email, sub=sub)
    return _v


# ============================================================================
# /auth/login
# ============================================================================

def test_login_sem_id_token_falha_400(monkeypatch):
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR))
    cliente = app.test_client()
    resp = cliente.post('/auth/login', json={})
    assert resp.status_code == 400


def test_login_com_token_invalido_falha_401(monkeypatch):
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR))
    cliente = app.test_client()
    resp = cliente.post('/auth/login', json={'id_token': 'token-forjado'})
    assert resp.status_code == 401


def test_login_com_email_fora_da_allowlist_falha_403(monkeypatch):
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_FORA_DA_ALLOWLIST))
    cliente = app.test_client()
    resp = cliente.post('/auth/login', json={'id_token': 'token-valido'})
    assert resp.status_code == 403


def test_login_valido_com_perfil_gestor_seta_sessao(monkeypatch):
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR))
    cliente = app.test_client()
    resp = cliente.post('/auth/login', json={'id_token': 'token-valido'})
    assert resp.status_code == 200
    corpo = resp.get_json()
    assert corpo['email'] == _EMAIL_GESTOR
    assert corpo['perfil'] == 'GESTOR'
    assert corpo['csrf_token']


def test_login_ignora_perfil_autodeclarado_no_corpo(monkeypatch):
    """FASE 8 -- 'handlers nunca aceitam perfil autodeclarado pelo
    request': mesmo que o corpo tente injetar perfil=GESTOR para um
    e-mail que so tem OPERACIONAL na allowlist, o perfil real da sessao
    e sempre o da allowlist -- nunca o do corpo."""
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_OPERACIONAL))
    cliente = app.test_client()
    resp = cliente.post('/auth/login', json={'id_token': 'token-valido', 'perfil': 'GESTOR'})
    assert resp.status_code == 200
    assert resp.get_json()['perfil'] == 'OPERACIONAL'  # nunca GESTOR


def test_cookie_de_sessao_e_httponly_e_samesite(monkeypatch):
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR))
    cliente = app.test_client()
    resp = cliente.post('/auth/login', json={'id_token': 'token-valido'})
    set_cookie = resp.headers.get('Set-Cookie', '')
    assert 'HttpOnly' in set_cookie
    assert 'SameSite=Lax' in set_cookie


# ============================================================================
# /auth/me
# ============================================================================

def test_me_sem_sessao_devolve_nao_autenticado(monkeypatch):
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR))
    cliente = app.test_client()
    resp = cliente.get('/auth/me')
    assert resp.status_code == 200
    assert resp.get_json()['autenticado'] is False


def test_me_com_sessao_devolve_identidade(monkeypatch):
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR))
    cliente = app.test_client()
    cliente.post('/auth/login', json={'id_token': 'token-valido'})
    resp = cliente.get('/auth/me')
    corpo = resp.get_json()
    assert corpo['autenticado'] is True
    assert corpo['email'] == _EMAIL_GESTOR
    assert corpo['perfil'] == 'GESTOR'


# ============================================================================
# /auth/logout -- CSRF obrigatorio
# ============================================================================

def test_logout_sem_sessao_falha_401(monkeypatch):
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR))
    cliente = app.test_client()
    resp = cliente.post('/auth/logout')
    assert resp.status_code == 401


def test_logout_sem_csrf_falha_403(monkeypatch):
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR))
    cliente = app.test_client()
    cliente.post('/auth/login', json={'id_token': 'token-valido'})
    resp = cliente.post('/auth/logout')  # sem header X-CSRF-Token
    assert resp.status_code == 403


def test_logout_com_csrf_adulterado_falha_403(monkeypatch):
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR))
    cliente = app.test_client()
    cliente.post('/auth/login', json={'id_token': 'token-valido'})
    resp = cliente.post('/auth/logout', headers={'X-CSRF-Token': 'token-forjado-qualquer'})
    assert resp.status_code == 403


def test_logout_com_csrf_correto_encerra_sessao(monkeypatch):
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR))
    cliente = app.test_client()
    login = cliente.post('/auth/login', json={'id_token': 'token-valido'})
    csrf = login.get_json()['csrf_token']
    resp = cliente.post('/auth/logout', headers={'X-CSRF-Token': csrf})
    assert resp.status_code == 204

    # replay -- sessao (cookie) apos logout nao autentica mais
    apos = cliente.get('/auth/me')
    assert apos.get_json()['autenticado'] is False


# ============================================================================
# Decorators para rotas de dominio futuras -- nunca degrada para allow-all
# ============================================================================

def _rota_protegida_de_teste(app):
    @app.route('/protegida', methods=['POST'])
    @exigir_sessao_com_perfil(frozenset({Perfil.GESTOR}))
    @exigir_csrf
    def _protegida(sujeito):
        return flask.jsonify({'ok': True, 'quem': sujeito.email, 'sujeito_id': sujeito.sujeito_id})


def test_rota_protegida_sem_sessao_nunca_degrada_para_allow_all(monkeypatch):
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR))
    _rota_protegida_de_teste(app)
    cliente = app.test_client()
    resp = cliente.post('/protegida')
    assert resp.status_code == 401  # nunca 200 sem sessao


def test_rota_protegida_com_perfil_insuficiente_recusa(monkeypatch):
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_OPERACIONAL))
    _rota_protegida_de_teste(app)
    cliente = app.test_client()
    login = cliente.post('/auth/login', json={'id_token': 'token-valido'})
    csrf = login.get_json()['csrf_token']
    resp = cliente.post('/protegida', headers={'X-CSRF-Token': csrf})
    assert resp.status_code == 403


def test_rota_protegida_com_gestor_e_csrf_funciona_e_identidade_chega_ao_handler(monkeypatch):
    """FASE 8 -- 'identidade chega corretamente à futura trilha de
    auditoria': o `sujeito` passado ao handler de domínio é o MESMO
    construído a partir da sessão real, nunca um objeto reconstruído
    às cegas."""
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR, sub='sub-gestor-xyz'))
    _rota_protegida_de_teste(app)
    cliente = app.test_client()
    login = cliente.post('/auth/login', json={'id_token': 'token-valido'})
    csrf = login.get_json()['csrf_token']
    resp = cliente.post('/protegida', headers={'X-CSRF-Token': csrf})
    assert resp.status_code == 200
    corpo = resp.get_json()
    assert corpo['quem'] == _EMAIL_GESTOR
    assert corpo['sujeito_id'] == 'sub-gestor-xyz'  # sub do Google chegou intacto ate o handler


def test_rota_protegida_sem_csrf_mesmo_autenticado_recusa(monkeypatch):
    app = _app_teste(monkeypatch, _fake_verificar(_EMAIL_GESTOR))
    _rota_protegida_de_teste(app)
    cliente = app.test_client()
    cliente.post('/auth/login', json={'id_token': 'token-valido'})
    resp = cliente.post('/protegida')  # sem X-CSRF-Token
    assert resp.status_code == 403


# ============================================================================
# Independência do Airtable -- estrutural
# ============================================================================

def test_modulos_de_autenticacao_nunca_importam_airtable():
    """Checa IMPORTS reais (`import ...airtable...`), nunca menções em
    docstring/comentário -- `allowlist.py` documenta deliberadamente
    'Airtable nunca é authority de acesso', o que não é um import."""
    import ast
    import inspect

    import magnata_os.autenticacao.adapters.blueprint_login as blueprint_mod
    import magnata_os.autenticacao.adapters.sessao as sessao_mod
    import magnata_os.autenticacao.allowlist as allowlist_mod
    import magnata_os.autenticacao.identidade as identidade_mod
    import magnata_os.autenticacao.provedor_google_oidc as provedor_mod

    for modulo in (identidade_mod, allowlist_mod, provedor_mod, sessao_mod, blueprint_mod):
        arvore = ast.parse(inspect.getsource(modulo))
        nomes_importados = []
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                nomes_importados += [alias.name for alias in no.names]
            elif isinstance(no, ast.ImportFrom) and no.module:
                nomes_importados.append(no.module)
        assert not any('airtable' in nome.lower() for nome in nomes_importados)


def test_configuracao_de_sessao_exige_secret_key_explicito():
    from magnata_os.autenticacao.adapters.sessao import SegredoSessaoAusente, configurar_sessao_segura
    app = flask.Flask('teste_sem_segredo')
    with pytest.raises(SegredoSessaoAusente):
        configurar_sessao_segura(app, ambiente={})
