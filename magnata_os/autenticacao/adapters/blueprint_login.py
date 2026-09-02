"""Blueprint Flask de login/logout administrativo -- missão
"AUTENTICAÇÃO ADMINISTRATIVA COMPARTILHADA V1", FASE 7 (wiring:
`request -> autenticar identidade -> construir Sujeito -> handler de
domínio`).

**NÃO registrado em `app.py` nesta missão** -- mesma decisão, pelo
mesmo motivo, da missão anterior ("ENTRADA OPERACIONAL..."): registrar
uma rota real é uma alteração de `app.py` (protegido, CLAUDE.md §7) e
depende de `GOOGLE_OAUTH_CLIENT_ID`/`MAGNATA_ADMIN_ALLOWLIST`/
`MAGNATA_SESSION_SECRET_KEY` reais, nenhum dos quais existe ainda nesta
sessão -- gate reportado no ADR. Totalmente testável via
`flask.Flask.test_client()` sobre um `flask.Flask` de TESTE isolado
(construído só dentro de `test_magnata_os_autenticacao_*.py`, nunca
neste pacote) -- nunca o `app` real de `app.py`.

`login`/`me`/`logout` nunca aceitam `perfil` do corpo da requisição --
perfil vem SEMPRE de `allowlist.py` (autoridade do Magnata OS), nunca
autodeclarado pelo cliente (mesma disciplina já valia para os handlers
de alocação, agora reforçada na própria borda de autenticação)."""
from __future__ import annotations

import functools
from typing import Callable, FrozenSet, Optional

from flask import Blueprint, jsonify, request

from ..allowlist import ResolvedorAllowlistAmbiente
from ..identidade import Perfil, PermissaoNegada, Sujeito, exigir_perfil
from ..provedor_google_oidc import (
    ClaimsGoogleIncompletos,
    EmailNaoVerificadoPeloGoogle,
    GoogleClientIdAusente,
    TokenGoogleInvalido,
    verificar_id_token_google,
)
from .sessao import CsrfInvalido, encerrar_sessao, gerar_csrf_token, iniciar_sessao, sujeito_da_sessao, validar_csrf_token

auth_bp = Blueprint('magnata_autenticacao', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['POST'])
def login():
    """Corpo esperado: `{"id_token": "<ID token do Google>"}`. Nunca lê
    `perfil`/`email` diretamente do corpo -- `email` só é aceito depois
    de verificado pelo Google; `perfil` só depois de resolvido pela
    allowlist."""
    dados = request.get_json(silent=True) or {}
    id_token = dados.get('id_token')
    if not id_token:
        return jsonify({'erro': 'id_token_ausente'}), 400

    try:
        identidade = verificar_id_token_google(id_token)
    except GoogleClientIdAusente:
        return jsonify({'erro': 'provedor_indisponivel'}), 503
    except (TokenGoogleInvalido, EmailNaoVerificadoPeloGoogle, ClaimsGoogleIncompletos):
        return jsonify({'erro': 'identidade_invalida'}), 401

    perfil = ResolvedorAllowlistAmbiente().perfil_para_email(identidade.email)
    if perfil is None:
        return jsonify({'erro': 'nao_autorizado'}), 403

    iniciar_sessao(identidade.email, perfil, sujeito_id=identidade.sub)
    return jsonify({'email': identidade.email, 'perfil': perfil.value, 'csrf_token': gerar_csrf_token()}), 200


@auth_bp.route('/logout', methods=['POST'])
def logout():
    sujeito = sujeito_da_sessao()
    if sujeito is None:
        return jsonify({'erro': 'nao_autenticado'}), 401
    try:
        validar_csrf_token(request.headers.get('X-CSRF-Token'))
    except CsrfInvalido:
        return jsonify({'erro': 'csrf_invalido'}), 403
    encerrar_sessao()
    return '', 204


@auth_bp.route('/me', methods=['GET'])
def me():
    sujeito = sujeito_da_sessao()
    if sujeito is None:
        return jsonify({'autenticado': False}), 200
    return jsonify({
        'autenticado': True, 'email': sujeito.email, 'perfil': sujeito.perfil.value,
        'csrf_token': gerar_csrf_token(),
    }), 200


def exigir_sessao_com_perfil(perfis_permitidos: FrozenSet[Perfil]) -> Callable:
    """Decorator para rotas de domínio FUTURAS (ex.: a rota real de
    Confirmação de Alocação, quando o gate de `app.py` for fechado):
    constrói `Sujeito` a partir da SESSÃO (nunca do request), exige
    perfil, e só então chama a view -- `sujeito` é passado como
    primeiro argumento posicional para a view decorada."""
    def decorador(view: Callable) -> Callable:
        @functools.wraps(view)
        def rota(*args, **kwargs):
            sujeito: Optional[Sujeito] = sujeito_da_sessao()
            if sujeito is None:
                return jsonify({'erro': 'nao_autenticado'}), 401
            try:
                exigir_perfil(sujeito, perfis_permitidos)
            except PermissaoNegada:
                return jsonify({'erro': 'permissao_negada'}), 403
            return view(sujeito, *args, **kwargs)
        return rota
    return decorador


def exigir_csrf(view: Callable) -> Callable:
    """Decorator para rotas de ESCRITA futuras -- valida o header
    `X-CSRF-Token` antes de chamar a view; nunca aplicado a `GET`."""
    @functools.wraps(view)
    def rota(*args, **kwargs):
        try:
            validar_csrf_token(request.headers.get('X-CSRF-Token'))
        except CsrfInvalido:
            return jsonify({'erro': 'csrf_invalido'}), 403
        return view(*args, **kwargs)
    return rota
