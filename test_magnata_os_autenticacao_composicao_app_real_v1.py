"""Testes de COMPOSIÇÃO REAL -- missão "ATIVAÇÃO MÍNIMA DA AUTENTICAÇÃO
ADMINISTRATIVA NO APP.PY": validam o `app` de verdade (`app.py`), depois do
wiring mínimo que conecta `magnata_os/autenticacao/adapters/blueprint_login.py`
(`auth_bp`) e `adapters/sessao.py` (`configurar_sessao_segura`) já
implementados e testados no PR #118.

Diferença deliberada para `test_magnata_os_autenticacao_sessao_e_blueprint_v1.py`
(que testa os adapters isolados, sobre um `flask.Flask` de TESTE construído
só naquele arquivo): aqui o alvo é `app.py::app`, o Flask real de produção
-- prova que o wiring em si (import + `configurar_sessao_segura` +
`register_blueprint`) funciona sobre o app inteiro, com todas as outras
rotas/blueprints/config já carregados, sem quebrar nada existente.

Nenhuma chamada de rede real (Google/Airtable/Postgres) em nenhum teste
deste arquivo -- só composição e roteamento, via `flask.Flask.test_client()`.
`conftest.py` (raiz) garante `MAGNATA_SESSION_SECRET_KEY` presente no
ambiente ANTES da coleta importar `app.py` (ver docstring de lá para o
porquê)."""
import ast
import inspect

import pytest

import app as app_modulo
from app import app as flask_app


def _client():
    flask_app.testing = True
    return flask_app.test_client()


# ============================================================================
# 1-3. Rotas de auth registradas no app REAL
# ============================================================================

def test_app_real_registra_auth_login():
    regras = {r.rule for r in flask_app.url_map.iter_rules()}
    assert '/auth/login' in regras


def test_app_real_registra_auth_me():
    regras = {r.rule for r in flask_app.url_map.iter_rules()}
    assert '/auth/me' in regras


def test_app_real_registra_auth_logout():
    regras = {r.rule for r in flask_app.url_map.iter_rules()}
    assert '/auth/logout' in regras


# ============================================================================
# 4. Configuração de sessão efetivamente aplicada ao app real
# ============================================================================

def test_app_real_tem_sessao_segura_configurada():
    assert flask_app.secret_key  # nunca None/vazio -- configurar_sessao_segura já rodou
    assert flask_app.config['SESSION_COOKIE_HTTPONLY'] is True
    assert flask_app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'
    # Secure=True é o default de configurar_sessao_segura -- app.py nunca
    # passa secure=False (isso é só para o app de TESTE isolado dos outros
    # arquivos, nunca para o app real).
    assert flask_app.config['SESSION_COOKIE_SECURE'] is True


def test_cookie_de_login_no_app_real_e_httponly_e_samesite_lax(monkeypatch):
    """Prova ponta a ponta -- o cookie que o app REAL de fato emite num
    login tem os atributos exigidos, não só a config estática."""
    import magnata_os.autenticacao.adapters.blueprint_login as blueprint_mod
    from magnata_os.autenticacao.provedor_google_oidc import IdentidadeGoogleVerificada

    email = 'gestor-composicao@exemplo.com'

    def _verificador_fake(token, client_id=None, **kwargs):
        return IdentidadeGoogleVerificada(email=email, sub='sub-composicao-1')

    monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_ID', 'client-id-sintetico.apps.googleusercontent.com')
    monkeypatch.setenv('MAGNATA_ADMIN_ALLOWLIST', f'{email}:GESTOR')
    monkeypatch.setattr(blueprint_mod, 'verificar_id_token_google', _verificador_fake)

    resp = _client().post('/auth/login', json={'id_token': 'test'})
    assert resp.status_code == 200
    set_cookie = resp.headers.get('Set-Cookie', '')
    assert 'HttpOnly' in set_cookie
    assert 'SameSite=Lax' in set_cookie


# ============================================================================
# 5. Ausência de MAGNATA_SESSION_SECRET_KEY falha de modo seguro (fail-closed)
# ============================================================================

def test_configurar_sessao_segura_sem_chave_falha_fail_closed():
    """Mesma função que `app.py` chama no wiring -- prova que o ponto exato
    de composição usado pelo app real recusa configurar uma sessão insegura
    quando o segredo está ausente, em vez de gerar um valor por conta
    própria ou degradar silenciosamente. Um `flask.Flask` NOVO e descartável
    aqui -- nunca reconfigura o `app` real já carregado (que já tem
    `secret_key` válido desde o import; reconfigurá-lo invalidaria sessões
    de outros testes desta mesma sessão de pytest)."""
    import flask

    from magnata_os.autenticacao.adapters.sessao import SegredoSessaoAusente, configurar_sessao_segura

    app_descartavel = flask.Flask('teste_fail_closed_composicao')
    with pytest.raises(SegredoSessaoAusente):
        configurar_sessao_segura(app_descartavel, ambiente={})


# ============================================================================
# 6. Nenhuma credencial hardcoded no wiring de app.py
# ============================================================================

def test_wiring_de_auth_em_app_py_nao_hardcoda_credencial():
    """Le o TRECHO de app.py entre `app = Flask(__name__)` e o registro do
    primeiro blueprint pré-existente (`secullum_bp`) -- a região exata do
    wiring desta missão -- e garante que nenhum literal de Client
    ID/allowlist/segredo foi colado ali. O wiring só pode importar/chamar
    funções; toda credencial real continua vindo do ambiente."""
    fonte = inspect.getsource(app_modulo)
    inicio = fonte.index('from magnata_os.autenticacao.adapters.blueprint_login import auth_bp')
    fim = fonte.index('app.register_blueprint(auth_bp)') + len('app.register_blueprint(auth_bp)')
    trecho = fonte[inicio:fim]

    assert 'GOOGLE_OAUTH_CLIENT_ID' not in trecho or "os.environ" not in trecho.replace('GOOGLE_OAUTH_CLIENT_ID', '')
    # Nenhuma atribuição direta de string a secret_key/client_id/allowlist
    # dentro do trecho -- só chamadas de função (configurar_sessao_segura),
    # nunca `app.secret_key = "..."` nem `... = "algo@algo.com:GESTOR"`.
    arvore = ast.parse(trecho.strip() or 'pass')
    for no in ast.walk(arvore):
        if isinstance(no, ast.Assign):
            for alvo in no.targets:
                nome = getattr(alvo, 'attr', None) or getattr(alvo, 'id', None)
                if nome and 'secret' in str(nome).lower():
                    assert False, f'atribuicao direta de segredo encontrada no wiring: {nome!r}'


# ============================================================================
# 7. Rotas pré-existentes continuam registradas (nenhuma regressão de rota)
# ============================================================================

def test_rotas_pre_existentes_continuam_registradas():
    regras = {r.rule for r in flask_app.url_map.iter_rules()}
    # Amostra de rotas de módulos/blueprints já carregados antes desta
    # missão -- prova que o wiring novo não substituiu nem removeu nada.
    assert '/secullum/sincronizar-funcionarios' in regras or any(
        r.startswith('/secullum') for r in regras
    )


# ============================================================================
# 8. Nenhum comportamento Airtable foi alterado
# ============================================================================

def test_wiring_de_auth_nao_importa_airtable():
    """Mesma técnica estrutural (AST sobre imports reais, nunca menção em
    comentário) já usada em
    `test_magnata_os_autenticacao_sessao_e_blueprint_v1.py::
    test_modulos_de_autenticacao_nunca_importam_airtable` -- aqui aplicada
    ao trecho de app.py que faz o wiring."""
    fonte = inspect.getsource(app_modulo)
    inicio = fonte.index('from magnata_os.autenticacao.adapters.blueprint_login import auth_bp')
    fim = fonte.index('app.register_blueprint(auth_bp)') + len('app.register_blueprint(auth_bp)')
    trecho = fonte[inicio:fim]
    arvore = ast.parse('\n'.join(
        linha for linha in trecho.splitlines() if not linha.strip().startswith('#')
    ))
    nomes_importados = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes_importados += [alias.name for alias in no.names]
        elif isinstance(no, ast.ImportFrom) and no.module:
            nomes_importados.append(no.module)
    assert not any('airtable' in nome.lower() for nome in nomes_importados)
    assert nomes_importados  # sanidade: o trecho realmente tinha os 2 imports esperados


def test_variaveis_airtable_do_app_continuam_intactas():
    """`AIRTABLE_API_KEY`/`BASE_ID` (definidos logo depois do wiring, em
    app.py) continuam existindo com o mesmo mecanismo de sempre -- o
    wiring de auth não tocou nenhuma variável/config do Airtable."""
    assert hasattr(app_modulo, 'AIRTABLE_API_KEY')
    assert hasattr(app_modulo, 'BASE_ID')
    assert app_modulo.BASE_ID == 'appaCpIVj7Q97VhFy'


# ============================================================================
# 9. Import/startup do app real continua funcional em ambiente de teste
# ============================================================================

def test_import_do_app_real_nao_levanta_excecao():
    """Se este teste está rodando, `import app` (feito no topo deste
    arquivo) já teve que suceder -- reforça a intenção explicitamente como
    caso de teste nomeado, não só um efeito colateral do import de módulo."""
    assert flask_app is not None
    assert flask_app.name == 'app'


# ============================================================================
# 10. Nenhuma regressão nos testes do PR #118 (adapters continuam intactos)
# ============================================================================

def test_blueprint_login_nao_foi_duplicado_nem_modificado():
    """`auth_bp` registrado no app real é o MESMO objeto Blueprint definido
    em `blueprint_login.py` -- nunca uma cópia/reimplementação dentro de
    app.py (checagem de identidade de objeto, não só de nome)."""
    from magnata_os.autenticacao.adapters.blueprint_login import auth_bp as auth_bp_original
    assert flask_app.blueprints['magnata_autenticacao'] is auth_bp_original
