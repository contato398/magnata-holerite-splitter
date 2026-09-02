"""Testes de `sujeito_autorizado_da_sessao()`/`exigir_sessao_com_perfil`/
`/auth/me` -- REVISÃO OBRIGATÓRIA PR #118, blocker de segurança: uma
sessão já aberta precisa refletir a autorização ATUAL do Magnata OS
(revogação/mudança de perfil na allowlist), nunca confiar cegamente no
perfil gravado no cookie no momento do login.

Mesma disciplina de `test_magnata_os_autenticacao_sessao_e_blueprint_v1.py`
-- app Flask de TESTE isolado, nunca `app.py`; nenhuma chamada de rede
real ao Google; e-mails 100% sintéticos. `_app_teste`/`_fake_verificar`
duplicados deliberadamente aqui (mesmo padrão já usado em outros pares
de arquivo de teste deste repositório) para manter este arquivo
autocontido e focado só no cenário de revalidação."""
import flask
import pytest

from magnata_os.autenticacao.adapters.blueprint_login import auth_bp, exigir_csrf, exigir_sessao_com_perfil
from magnata_os.autenticacao.adapters.sessao import configurar_sessao_segura
from magnata_os.autenticacao.identidade import Perfil

_CLIENT_ID = 'client-id-sintetico.apps.googleusercontent.com'
_EMAIL_GESTOR = 'gestor-revalidacao@exemplo.com'


def _app_teste(monkeypatch, allowlist_inicial):
    app = flask.Flask('magnata_teste_revalidacao')
    configurar_sessao_segura(app, secret_key='fake', secure=False)
    app.register_blueprint(auth_bp)

    monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_ID', _CLIENT_ID)
    monkeypatch.setenv('MAGNATA_ADMIN_ALLOWLIST', allowlist_inicial)

    def _verificador(token, client_id=None, **kwargs):
        from magnata_os.autenticacao.provedor_google_oidc import IdentidadeGoogleVerificada, TokenGoogleInvalido
        if token != 'test':
            raise TokenGoogleInvalido('token invalido (fake)')
        return IdentidadeGoogleVerificada(email=_EMAIL_GESTOR, sub='sub-revalidacao-1')

    import magnata_os.autenticacao.adapters.blueprint_login as blueprint_mod
    monkeypatch.setattr(blueprint_mod, 'verificar_id_token_google', _verificador)

    @app.route('/protegida-gestor', methods=['POST'])
    @exigir_sessao_com_perfil(frozenset({Perfil.GESTOR}))
    @exigir_csrf
    def _protegida_gestor(sujeito):
        return flask.jsonify({'ok': True, 'perfil_efetivo': sujeito.perfil.value})

    @app.route('/protegida-operacional', methods=['POST'])
    @exigir_sessao_com_perfil(frozenset({Perfil.OPERACIONAL}))
    @exigir_csrf
    def _protegida_operacional(sujeito):
        return flask.jsonify({'ok': True, 'perfil_efetivo': sujeito.perfil.value})

    return app


def _login(cliente):
    resp = cliente.post('/auth/login', json={'id_token': 'test'})
    assert resp.status_code == 200
    return resp.get_json()['csrf_token']


# ============================================================================
# 1/2/3 -- login GESTOR, allowlist muda GESTOR->OPERACIONAL na MESMA sessao
# ============================================================================

def test_rebaixamento_de_perfil_na_allowlist_e_refletido_na_mesma_sessao(monkeypatch):
    app = _app_teste(monkeypatch, f'{_EMAIL_GESTOR}:GESTOR')
    cliente = app.test_client()
    csrf = _login(cliente)  # 1. login como GESTOR

    resp_antes = cliente.post('/protegida-gestor', headers={'X-CSRF-Token': csrf})
    assert resp_antes.status_code == 200
    assert resp_antes.get_json()['perfil_efetivo'] == 'GESTOR'

    # 2. allowlist muda GESTOR -> OPERACIONAL (simula nova config + restart:
    # sujeito_autorizado_da_sessao le o ambiente do zero a cada chamada,
    # entao mudar a env var ja e suficiente, sem reiniciar processo de verdade)
    monkeypatch.setenv('MAGNATA_ADMIN_ALLOWLIST', f'{_EMAIL_GESTOR}:OPERACIONAL')

    # 3. rota GESTOR passa a negar -- MESMO cookie de sessao, nenhum novo login
    resp_gestor_depois = cliente.post('/protegida-gestor', headers={'X-CSRF-Token': csrf})
    assert resp_gestor_depois.status_code == 403

    # 4. rota OPERACIONAL passa a refletir o novo perfil, mesma sessao
    resp_operacional_depois = cliente.post('/protegida-operacional', headers={'X-CSRF-Token': csrf})
    assert resp_operacional_depois.status_code == 200
    assert resp_operacional_depois.get_json()['perfil_efetivo'] == 'OPERACIONAL'


# ============================================================================
# 5/6 -- usuario removido da allowlist -- acesso negado sem esperar expiracao
# ============================================================================

def test_usuario_removido_da_allowlist_perde_acesso_na_mesma_sessao(monkeypatch):
    app = _app_teste(monkeypatch, f'{_EMAIL_GESTOR}:GESTOR')
    cliente = app.test_client()
    csrf = _login(cliente)

    resp_antes = cliente.post('/protegida-gestor', headers={'X-CSRF-Token': csrf})
    assert resp_antes.status_code == 200

    # usuario removido inteiramente da allowlist (nao so rebaixado)
    monkeypatch.setenv('MAGNATA_ADMIN_ALLOWLIST', 'outra-pessoa@exemplo.com:GESTOR')

    resp_depois = cliente.post('/protegida-gestor', headers={'X-CSRF-Token': csrf})
    assert resp_depois.status_code == 401  # nunca 200 -- cookie antigo nao preserva privilegio

    # /me tambem reflete a revogacao -- nunca mostra identidade obsoleta
    resp_me = cliente.get('/auth/me')
    assert resp_me.get_json()['autenticado'] is False


def test_cookie_antigo_nunca_preserva_privilegio_apos_allowlist_vazia(monkeypatch):
    """'restart/nova configuração simulada': allowlist esvaziada por
    completo (como se o serviço tivesse subido com uma config nova, sem
    ninguém autorizado ainda) -- cookie antigo, assinado com a MESMA
    MAGNATA_SESSION_SECRET_KEY, nao vale mais nada."""
    app = _app_teste(monkeypatch, f'{_EMAIL_GESTOR}:GESTOR')
    cliente = app.test_client()
    csrf = _login(cliente)
    assert cliente.post('/protegida-gestor', headers={'X-CSRF-Token': csrf}).status_code == 200

    monkeypatch.setenv('MAGNATA_ADMIN_ALLOWLIST', '')  # allowlist vazia -- ninguem autorizado

    resp = cliente.post('/protegida-gestor', headers={'X-CSRF-Token': csrf})
    assert resp.status_code == 401


# ============================================================================
# 9 -- allowlist malformada falha fechado (nunca 500 vazando stacktrace,
# nunca allow-all)
# ============================================================================

def test_allowlist_malformada_apos_login_falha_fechado(monkeypatch):
    app = _app_teste(monkeypatch, f'{_EMAIL_GESTOR}:GESTOR')
    cliente = app.test_client()
    csrf = _login(cliente)
    assert cliente.post('/protegida-gestor', headers={'X-CSRF-Token': csrf}).status_code == 200

    # config quebrada depois do login -- nunca deveria crashar nem liberar acesso
    monkeypatch.setenv('MAGNATA_ADMIN_ALLOWLIST', 'entrada-sem-dois-pontos')

    resp = cliente.post('/protegida-gestor', headers={'X-CSRF-Token': csrf})
    assert resp.status_code == 401  # fail-closed -- nunca 200, nunca 500 nao tratado


# ============================================================================
# 10 -- indisponibilidade da fonte de autorizacao nunca vira allow-all
# ============================================================================

def test_fonte_de_autorizacao_indisponivel_nunca_vira_allow_all(monkeypatch):
    from magnata_os.autenticacao.adapters import sessao as sessao_mod

    app = _app_teste(monkeypatch, f'{_EMAIL_GESTOR}:GESTOR')
    cliente = app.test_client()
    csrf = _login(cliente)
    assert cliente.post('/protegida-gestor', headers={'X-CSRF-Token': csrf}).status_code == 200

    class _ResolvedorIndisponivel:
        def perfil_para_email(self, email):
            raise ConnectionError('fonte de autorizacao indisponivel (simulado)')

    monkeypatch.setattr(sessao_mod, 'ResolvedorAllowlistAmbiente', _ResolvedorIndisponivel)

    resp = cliente.post('/protegida-gestor', headers={'X-CSRF-Token': csrf})
    assert resp.status_code == 401  # nunca 200 so porque a fonte de autorizacao falhou


def test_usuario_revogado_ainda_consegue_encerrar_a_propria_sessao(monkeypatch):
    """Design explícito: `logout()` usa o cache não-revalidado de
    propósito -- encerrar a própria sessão nunca deveria depender de
    ainda estar na allowlist. Um usuário revogado consegue limpar seu
    próprio cookie mesmo sem acesso a nenhuma rota protegida."""
    app = _app_teste(monkeypatch, f'{_EMAIL_GESTOR}:GESTOR')
    cliente = app.test_client()
    csrf = _login(cliente)

    monkeypatch.setenv('MAGNATA_ADMIN_ALLOWLIST', 'outra-pessoa@exemplo.com:GESTOR')  # revogado

    assert cliente.post('/protegida-gestor', headers={'X-CSRF-Token': csrf}).status_code == 401
    resp_logout = cliente.post('/auth/logout', headers={'X-CSRF-Token': csrf})
    assert resp_logout.status_code == 204  # logout funciona mesmo revogado


# ============================================================================
# 11 -- zero regressao em login/logout/CSRF (smoke -- suíte completa de
# regressão já em test_magnata_os_autenticacao_sessao_e_blueprint_v1.py)
# ============================================================================

def test_login_logout_csrf_continuam_funcionando_sem_mudanca_de_allowlist(monkeypatch):
    app = _app_teste(monkeypatch, f'{_EMAIL_GESTOR}:GESTOR')
    cliente = app.test_client()
    csrf = _login(cliente)
    assert cliente.post('/protegida-gestor', headers={'X-CSRF-Token': csrf}).status_code == 200
    assert cliente.post('/protegida-gestor').status_code == 403  # sem CSRF
    resp_logout = cliente.post('/auth/logout', headers={'X-CSRF-Token': csrf})
    assert resp_logout.status_code == 204
    assert cliente.get('/auth/me').get_json()['autenticado'] is False


# ============================================================================
# 12 -- perfil autodeclarado continua impossivel (rota protegida nunca le
# corpo/query da requisicao para decidir perfil)
# ============================================================================

def test_rota_protegida_ignora_qualquer_perfil_no_corpo_da_requisicao(monkeypatch):
    app = _app_teste(monkeypatch, f'{_EMAIL_GESTOR}:OPERACIONAL')
    cliente = app.test_client()
    csrf = _login(cliente)
    # tenta se autodeclarar GESTOR no corpo -- rota nunca le isso
    resp = cliente.post(
        '/protegida-gestor', headers={'X-CSRF-Token': csrf}, json={'perfil': 'GESTOR', 'sujeito_id': 'forjado'})
    assert resp.status_code == 403  # continua OPERACIONAL de verdade, negado para rota GESTOR
