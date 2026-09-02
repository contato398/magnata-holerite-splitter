"""Verificação de identidade via Google OIDC ("Sign in with Google")
-- missão "AUTENTICAÇÃO ADMINISTRATIVA COMPARTILHADA V1", FASE 1/7.

**Modelo escolhido (ver ADR desta missão para a comparação completa):**
o navegador obtém um ID token assinado do Google (via o botão "Sign in
with Google"/Google Identity Services, carregado só no front-end, sem
nenhuma biblioteca de servidor nova) e envia esse token ao backend. Este
módulo só VERIFICA a assinatura/validade desse token contra as chaves
públicas do Google e devolve o e-mail verificado -- nunca decide
sozinho quem tem acesso (isso é `allowlist.py`, autoridade do próprio
Magnata OS) nem constrói sessão (isso é `sessao.py`).

**Zero dependência nova instalada:** reaproveita `google.oauth2.id_token`
+ `google.auth.transport.requests`, parte do pacote `google-auth`
(`requirements.txt`, já instalado, já usado por
`documental/modulo01/adapters/email_gmail_readonly.py` para um
propósito totalmente diferente -- aqui nunca importamos
`Credentials.from_authorized_user_file` nem lidamos com token de
mailbox).

`GOOGLE_OAUTH_CLIENT_ID`: variável de ambiente nova, só o CLIENT ID
público do OAuth (não é segredo -- é enviado ao navegador de qualquer
forma para renderizar o botão de login; `SECRET_CONTEXT_KEYWORDS` do
Gate 5 não o reconhece como sensível, e não deveria). Registrar esse
Client ID no Google Cloud Console é uma AÇÃO EXTERNA REAL, fora da
capacidade desta sessão e fora do escopo desta missão -- gate
reportado no ADR, nunca meramente assumido/inventado."""
from __future__ import annotations

import dataclasses
from typing import Callable, Optional

_VerificadorIdToken = Callable[[str, object, Optional[str]], dict]


@dataclasses.dataclass(frozen=True)
class IdentidadeGoogleVerificada:
    """`sub` é o id de assunto ESTÁVEL do Google (nunca muda para a
    mesma conta, ao contrário do e-mail, que uma conta pode trocar) --
    alimenta `Sujeito.sujeito_id` (FASE 2 da missão: identidade
    canônica com `sujeito_id`/`email`/`perfil`/`autenticado_por`)."""

    email: str
    sub: str


class GoogleClientIdAusente(Exception):
    """`GOOGLE_OAUTH_CLIENT_ID` não configurado -- a verificação real
    exige essa variável (nunca um valor default implícito)."""


class TokenGoogleInvalido(Exception):
    """O ID token não passou na verificação do Google (assinatura,
    expiração, audience/client_id errado, emissor errado, etc.) --
    mensagem sempre sanitizada, nunca inclui o token bruto."""


class EmailNaoVerificadoPeloGoogle(Exception):
    """O token é válido, mas o Google não confirma o e-mail
    (`email_verified` ausente/False) -- nunca aceito como identidade."""


class ClaimsGoogleIncompletos(Exception):
    """O token é válido e o e-mail é verificado, mas faltam claims
    essenciais (`sub`) para montar uma identidade completa -- nunca
    aceito com um `sujeito_id` inventado/`None` silencioso."""


def verificar_id_token_google(
    token: str,
    client_id: Optional[str] = None,
    *,
    verificador: Optional[_VerificadorIdToken] = None,
    ambiente: Optional[dict] = None,
) -> IdentidadeGoogleVerificada:
    """Verifica `token` e devolve `IdentidadeGoogleVerificada` (e-mail +
    `sub` estável). Levanta `GoogleClientIdAusente`/`TokenGoogleInvalido`/
    `EmailNaoVerificadoPeloGoogle` -- nunca devolve `None`/string vazia
    silenciosamente.

    `verificador`: callable injetável, assinatura
    `(token, request_transport, audience) -> dict` (mesma assinatura de
    `google.oauth2.id_token.verify_oauth2_token`) -- testes SEMPRE
    injetam um verificador fake; nenhum teste deste módulo depende de
    rede real nem de uma chave pública do Google de verdade.
    `ambiente`: injetável para teste (default `os.environ`)."""
    import os

    fonte_ambiente = ambiente if ambiente is not None else os.environ
    client_id_resolvido = client_id if client_id is not None else fonte_ambiente.get('GOOGLE_OAUTH_CLIENT_ID')
    if not client_id_resolvido:
        raise GoogleClientIdAusente(
            'GOOGLE_OAUTH_CLIENT_ID nao configurado -- a verificacao real de '
            'identidade Google exige essa variavel de ambiente.'
        )

    if verificador is None:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
        verificador = google_id_token.verify_oauth2_token
        transporte = google_requests.Request()
    else:
        transporte = None  # fake nao usa transporte real

    try:
        claims = verificador(token, transporte, client_id_resolvido)
    except Exception as exc:
        raise TokenGoogleInvalido(f'Token Google invalido: {type(exc).__name__}') from exc

    if not isinstance(claims, dict) or not claims.get('email_verified'):
        raise EmailNaoVerificadoPeloGoogle('Google nao confirma o e-mail deste token.')

    email = claims.get('email')
    if not email or not isinstance(email, str):
        raise EmailNaoVerificadoPeloGoogle('Token valido mas sem e-mail utilizavel.')

    sub = claims.get('sub')
    if not sub or not isinstance(sub, str):
        raise ClaimsGoogleIncompletos('Token valido mas sem "sub" (id estavel) utilizavel.')

    return IdentidadeGoogleVerificada(email=email, sub=sub)
