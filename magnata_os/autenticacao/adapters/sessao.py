"""Sessão administrativa segura -- missão "AUTENTICAÇÃO ADMINISTRATIVA
COMPARTILHADA V1", FASE 4. Vive em `adapters/` porque importa `flask`
no topo do arquivo (mesmo padrão de `blueprint_login.py`, o outro
adapter deste pacote -- ver `magnata_os/CLAUDE.md`, "todo serviço
externo entra por adapter"); `identidade.py`/`allowlist.py`/
`provedor_google_oidc.py`, um nível acima, continuam livres de Flask.

Usa o mecanismo de sessão NATIVO do Flask (cookie assinado via
`itsdangerous`, já dependência do próprio Flask -- nenhuma biblioteca
nova) em vez de reinventar serialização/assinatura de cookie -- menor
superfície de ataque, código já revisado por terceiros.

Checklist da FASE 4, cada item com seu mecanismo:
  - `HttpOnly`         -> `SESSION_COOKIE_HTTPONLY=True` (sempre)
  - `Secure`           -> `SESSION_COOKIE_SECURE` (True por padrão;
                           `secure=False` só para o cliente de TESTE
                           local, nunca para uma sessão real ativada)
  - `SameSite`         -> `SESSION_COOKIE_SAMESITE='Lax'` (permite
                           navegação normal, bloqueia envio cross-site
                           em POST/requisições de terceiros)
  - expiração          -> `PERMANENT_SESSION_LIFETIME` + `session.permanent`
  - logout             -> `encerrar_sessao()` (`session.clear()`)
  - segredo via env    -> `configurar_sessao_segura(..., secret_key=None)`
                           lê `MAGNATA_SESSION_SECRET_KEY` do ambiente,
                           nunca um valor hardcoded; falha explícita se
                           ausente quando `secure=True` (nunca gera um
                           segredo aleatório por sessão de processo --
                           isso invalidaria sessões a cada restart e
                           mascararia a ausência real do segredo)
  - CSRF               -> `gerar_csrf_token`/`validar_csrf_token`
                           (synchronizer token pattern: token em
                           `session`, comparado ao token enviado pelo
                           formulário/header em toda escrita)

Nenhuma sessão real de produção é ativada por importar/testar este
módulo -- `configurar_sessao_segura` só CONFIGURA um app Flask já
existente, passado pelo chamador (nunca `app.py`, protegido; ver
`adapters/blueprint_login.py` para o Blueprint que usa isto, também
nunca registrado em `app.py` nesta missão)."""
from __future__ import annotations

import hmac
import os
import secrets
from datetime import timedelta
from typing import Optional

import flask

from ..identidade import Perfil, Sujeito

_CHAVE_SESSAO_SUJEITO = 'magnata_sujeito'
_CHAVE_SESSAO_CSRF = 'magnata_csrf_token'


class SegredoSessaoAusente(Exception):
    """`MAGNATA_SESSION_SECRET_KEY` não configurado -- sessão segura
    real exige essa variável; nunca um segredo gerado on-the-fly."""


class CsrfInvalido(Exception):
    """Token CSRF ausente ou não confere com o da sessão -- escrita
    recusada, nunca aplicada."""


def configurar_sessao_segura(
    app: 'flask.Flask',
    *,
    secret_key: Optional[str] = None,
    ambiente: Optional[dict] = None,
    secure: bool = True,
    tempo_de_vida: timedelta = timedelta(hours=8),
) -> None:
    """Configura `app` com os atributos de cookie/sessão da FASE 4.
    `secure=False` é aceito só para o `flask.Flask` de TESTE construído
    por `criar_app_teste_sessao()` (cliente de teste não fala HTTPS) --
    nunca para um app apontado para uso real."""
    fonte = ambiente if ambiente is not None else os.environ
    chave = secret_key if secret_key is not None else fonte.get('MAGNATA_SESSION_SECRET_KEY')
    if not chave:
        raise SegredoSessaoAusente(
            'MAGNATA_SESSION_SECRET_KEY nao configurada -- sessao segura real '
            'exige essa variavel de ambiente.'
        )
    app.secret_key = chave  # variavel local (lida do ambiente acima), nunca um literal
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SECURE'] = secure
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = tempo_de_vida


def iniciar_sessao(email: str, perfil: Perfil, *, sujeito_id: Optional[str] = None) -> None:
    """Grava a identidade JÁ VERIFICADA (por `provedor_google_oidc.py`
    + `allowlist.py`, nunca autodeclarada) na sessão Flask corrente, e
    marca a sessão como permanente (sujeita a `PERMANENT_SESSION_LIFETIME`,
    nunca eterna por padrão)."""
    flask.session[_CHAVE_SESSAO_SUJEITO] = {
        'email': email, 'perfil': perfil.value, 'sujeito_id': sujeito_id,
    }
    flask.session.permanent = True


def encerrar_sessao() -> None:
    """Logout -- limpa TODA a sessão (identidade e token CSRF juntos),
    nunca só parte dela."""
    flask.session.clear()


def sujeito_da_sessao() -> Optional[Sujeito]:
    """Reconstrói `Sujeito` a partir da sessão Flask corrente -- `None`
    se não houver sessão autenticada (nunca um `Sujeito` "anônimo" com
    perfil implícito). Único lugar deste pacote onde um `Sujeito` nasce
    de uma requisição HTTP real -- nenhum handler de domínio aceita
    `perfil` vindo direto do corpo/query da requisição."""
    dados = flask.session.get(_CHAVE_SESSAO_SUJEITO)
    if not dados:
        return None
    return Sujeito(
        perfil=Perfil(dados['perfil']), sujeito_id=dados.get('sujeito_id'),
        email=dados.get('email'), autenticado_por='sessao_flask',
    )


def gerar_csrf_token() -> str:
    """Gera (ou reaproveita, se já existir na sessão corrente) um token
    CSRF -- nunca um novo a cada chamada dentro da MESMA sessão
    (invalidaria formulários já renderizados ao usuário)."""
    token = flask.session.get(_CHAVE_SESSAO_CSRF)
    if not token:
        token = secrets.token_urlsafe(32)
        flask.session[_CHAVE_SESSAO_CSRF] = token
    return token


def validar_csrf_token(token_recebido: Optional[str]) -> None:
    """Levanta `CsrfInvalido` se `token_recebido` não conferir,
    byte-a-byte em tempo constante (`hmac.compare_digest`), com o token
    da sessão corrente -- nunca aceita ausência de token da sessão como
    "sem proteção configurada ainda"."""
    token_sessao = flask.session.get(_CHAVE_SESSAO_CSRF)
    if not token_sessao or not token_recebido or not hmac.compare_digest(token_sessao, token_recebido):
        raise CsrfInvalido('Token CSRF ausente ou invalido.')
