"""Allowlist administrativa -- autoridade de AUTORIZAÇÃO do Magnata OS
(missão "AUTENTICAÇÃO ADMINISTRATIVA COMPARTILHADA V1", FASE 5).

**Airtable nunca é authority de acesso.** A identidade (e-mail) é
verificada externamente pelo Google (`provedor_google_oidc.py`); QUEM
pode entrar e COM QUE perfil é decidido inteiramente aqui, por uma
fonte que pertence ao Magnata OS -- nunca por uma tabela do Airtable.

**Menor mecanismo seguro para V1: variável de ambiente**, no formato
`MAGNATA_ADMIN_ALLOWLIST=email1@x.com:GESTOR,email2@x.com:OPERACIONAL`
-- nenhuma tabela nova, nenhuma migration, revogação/rotação é só
trocar a variável de ambiente no Render e reiniciar o serviço (nenhum
deploy de código). Isso é deliberadamente MENOR do que uma tabela
`usuarios_administrativos` no Postgres -- que é a evolução natural
(protocolo compatível: `ResolvedorAllowlist` abaixo é injetável; um
adapter Postgres futuro implementa a MESMA interface sem mudar nenhum
chamador) -- mas criar essa tabela agora seria "schema novo antes do
gate", que esta missão explicitamente evita (ver ADR, FASE 5).

Nenhum e-mail/allowlist real da Magnata é usado em nenhum teste deste
módulo -- só endereços sintéticos."""
from __future__ import annotations

import os
from typing import Dict, Optional

from .identidade import Perfil


class AllowlistMalFormada(ValueError):
    """`MAGNATA_ADMIN_ALLOWLIST` presente mas com formato inválido --
    nunca ignorado silenciosamente (uma allowlist mal-lida poderia
    conceder ou negar acesso errado sem ninguém perceber)."""


def _parsear_allowlist(texto: str) -> Dict[str, Perfil]:
    mapa: Dict[str, Perfil] = {}
    for par in (p.strip() for p in texto.split(',') if p.strip()):
        if ':' not in par:
            raise AllowlistMalFormada(f'entrada sem ":perfil": {par!r}')
        email, _, perfil_texto = par.partition(':')
        email = email.strip().lower()
        perfil_texto = perfil_texto.strip().upper()
        if not email:
            raise AllowlistMalFormada(f'entrada sem e-mail: {par!r}')
        try:
            perfil = Perfil(perfil_texto)
        except ValueError:
            raise AllowlistMalFormada(f'perfil desconhecido {perfil_texto!r} para {email!r}') from None
        if email in mapa:
            raise AllowlistMalFormada(f'e-mail duplicado na allowlist: {email!r}')
        mapa[email] = perfil
    return mapa


class ResolvedorAllowlistAmbiente:
    """Lê `MAGNATA_ADMIN_ALLOWLIST` do ambiente uma vez na construção
    (nunca por-requisição -- evita reler/reparsear a cada checagem;
    trocar a variável exige reiniciar o processo, comportamento já
    aceito para `DATABASE_URL`/`AIRTABLE_API_KEY` em todo o
    repositório). `ambiente`: injetável para teste."""

    def __init__(self, ambiente: Optional[dict] = None) -> None:
        fonte = ambiente if ambiente is not None else os.environ
        self._mapa = _parsear_allowlist(fonte.get('MAGNATA_ADMIN_ALLOWLIST', ''))

    def perfil_para_email(self, email: str) -> Optional[Perfil]:
        """`None` = e-mail não está na allowlist -- nunca um perfil
        default/mais permissivo por omissão."""
        return self._mapa.get((email or '').strip().lower())
