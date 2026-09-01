"""Camada de autorização abstrata da Confirmação de Alocação (missão
"ENTRADA OPERACIONAL + POSTGRES PRÓPRIO V1", FASE 6).

**SEM AUTENTICAÇÃO REAL NESTA FASE** -- `Sujeito` é um portador de
perfil declarado pelo chamador, nunca o resultado de validar uma
sessão, token ou senha. Isso é uma repetição deliberada do MESMO gate
já registrado em `magnata_os/documental/modulo01/api/autorizacao.py`
("Nao implementar ainda" em `MAGNATA_OS_DOCUMENTAL_MODULO01_FASE4.md"):
este projeto não tem, hoje, nenhum mecanismo de autenticação
administrativa (auditado nesta missão -- `app.py` não tem
`login_required`, `SECRET_KEY` de sessão, Basic Auth nem qualquer
verificação de identidade de entrada; só chama Airtable/Resend como
cliente, nunca autentica quem chama `app.py`). Inventar senha
hardcoded, token em URL ou segredo no código para preencher essa lacuna
é proibido por CLAUDE.md §6 -- a lacuna fica registrada como GATE
aberto (ver ADR desta missão), nunca contornada.

**Cópia local, deliberada, do mesmo desenho de `modulo01/api/
autorizacao.py`** -- não importada de lá: mesma disciplina já
estabelecida em todo o pacote `alocacao/importacao_lote` de duplicar
uma peça pequena para preservar desacoplamento entre módulos
(CLAUDE.md raiz §3, "um módulo não importa o interno de outro") em vez
de criar uma dependência cruzada para 20 linhas de lógica. Quando uma
fase futura implementar autenticação real, o único ponto de integração
é onde `Sujeito` é construído (fora deste módulo, no adapter web ainda
não implementado) -- toda a lógica de "quem pode confirmar o quê" já
vive aqui e não muda.

Cada handler (`api/handlers.py`) chama `exigir_perfil()` como a
PRIMEIRA coisa que faz -- nunca None, nunca implícito."""
from __future__ import annotations

import dataclasses
from enum import Enum
from typing import FrozenSet


class Perfil(str, Enum):
    """Perfis operacionais abstratos desta fase. Nenhum perfil novo
    entra aqui sem decisão explícita. Só `GESTOR` é usado nesta missão
    (confirmação de alocação altera histórico canônico -- nunca uma
    operação de leitura, que dispensaria essa restrição)."""

    OPERACIONAL = 'OPERACIONAL'
    GESTOR = 'GESTOR'
    AUDITOR = 'AUDITOR'


@dataclasses.dataclass(frozen=True)
class Sujeito:
    """Quem está fazendo a chamada -- só o perfil, sem identidade real
    nesta fase (nenhum nome de usuário, e-mail ou token). Não tem
    NENHUM campo que sirva de trilha de auditoria de "quem confirmou"
    -- essa é uma lacuna real e distinta, registrada na FASE 7 do ADR
    desta missão (exigiria schema novo, gate próprio, não resolvido
    aqui)."""

    perfil: Perfil


class PermissaoNegada(Exception):
    """Perfil do sujeito não está entre os permitidos para a operação."""


def exigir_perfil(sujeito: Sujeito, perfis_permitidos: FrozenSet[Perfil]) -> None:
    """Levanta `PermissaoNegada` se `sujeito.perfil` não estiver em
    `perfis_permitidos`. Nunca aplica exceção à regra em silêncio --
    todo handler que chama isto declara explicitamente seu próprio
    conjunto de perfis permitidos."""
    if sujeito.perfil not in perfis_permitidos:
        perfis_str = ', '.join(sorted(p.value for p in perfis_permitidos))
        raise PermissaoNegada(
            f'Perfil {sujeito.perfil.value} nao tem permissao para esta operacao '
            f'(permitido: {perfis_str}).'
        )
