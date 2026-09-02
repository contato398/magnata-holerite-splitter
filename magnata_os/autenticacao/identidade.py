"""Identidade/autorização canônicas do Magnata OS (missão "AUTENTICAÇÃO
ADMINISTRATIVA COMPARTILHADA V1", FASE 2/3). Fonte ÚNICA de `Perfil`/
`Sujeito`/`exigir_perfil` — antes desta missão, existiam 2 cópias
independentes (`documental/modulo01/api/autorizacao.py`,
`documental/alocacao/autorizacao.py`), cada uma com seu próprio "sem
autenticação real nesta fase". Ambas viraram shims finos deste módulo
(ver seus próprios arquivos) -- nenhum comportamento externo mudou,
nenhum import existente quebrou.

**autenticação = quem é. autorização = o que pode fazer.** Este módulo
só resolve autorização (`exigir_perfil`) e o tipo de dado que carrega
identidade (`Sujeito`) -- quem de fato POPULA um `Sujeito` com uma
identidade real e verificada é `provedor_google_oidc.py` +
`sessao.py` (a fronteira de autenticação real), nunca este módulo.
`Sujeito` continua podendo ser construído com só `perfil` (compatível
com todo código/teste já existente que fazia `Sujeito(Perfil.GESTOR)`)
-- os campos novos (`sujeito_id`/`email`/`autenticado_por`) são todos
opcionais, preenchidos de verdade só quando a autenticação real
constrói o objeto."""
from __future__ import annotations

import dataclasses
from enum import Enum
from typing import FrozenSet, Optional, Type


class Perfil(str, Enum):
    """Perfis operacionais canônicos. Nenhum perfil novo entra aqui sem
    decisão explícita -- os 3 já existentes (auditados nesta missão em
    ambas as cópias anteriores, idênticos) são preservados sem
    alteração."""

    OPERACIONAL = 'OPERACIONAL'
    GESTOR = 'GESTOR'
    AUDITOR = 'AUDITOR'


@dataclasses.dataclass(frozen=True)
class Sujeito:
    """Quem está fazendo a chamada. `perfil` continua o único campo
    OBRIGATÓRIO e continua na posição 0 -- todo código existente que
    construía `Sujeito(Perfil.X)` posicionalmente continua funcionando
    sem alteração.

    `sujeito_id`/`email`/`autenticado_por`: novos nesta missão,
    opcionais, `None` por padrão -- só preenchidos quando um adapter de
    autenticação real (`sessao.py`) constrói o objeto a partir de uma
    identidade verificada (nunca autodeclarados por quem chama um
    handler; ver `sessao.py::sujeito_da_sessao`). `autenticado_por` é
    um rótulo de proveniência (ex.: `'google_oidc'`) -- nunca um
    segredo, nunca um token."""

    perfil: Perfil
    sujeito_id: Optional[str] = None
    email: Optional[str] = None
    autenticado_por: Optional[str] = None


class PermissaoNegada(Exception):
    """Perfil do sujeito não está entre os permitidos para a operação.
    Classe BASE -- um módulo com sua própria hierarquia de erro (ex.:
    `documental/modulo01/api/erros.py::PermissaoNegada`, que também é
    um `ApiError` com `codigo`/`status_http`) injeta sua própria
    subclasse via `exigir_perfil(..., classe_erro=...)` em vez de
    duplicar a lógica de checagem -- ver `modulo01/api/autorizacao.py`
    para o exemplo real."""


def exigir_perfil(
    sujeito: Sujeito,
    perfis_permitidos: FrozenSet[Perfil],
    *,
    classe_erro: Type[Exception] = PermissaoNegada,
) -> None:
    """Levanta `classe_erro` (por padrão `PermissaoNegada` deste módulo)
    se `sujeito.perfil` não estiver em `perfis_permitidos`. Nunca aplica
    exceção à regra em silêncio -- todo handler que chama isto declara
    explicitamente seu próprio conjunto de perfis permitidos."""
    if sujeito.perfil not in perfis_permitidos:
        perfis_str = ', '.join(sorted(p.value for p in perfis_permitidos))
        raise classe_erro(
            f'Perfil {sujeito.perfil.value} nao tem permissao para esta operacao '
            f'(permitido: {perfis_str}).'
        )
