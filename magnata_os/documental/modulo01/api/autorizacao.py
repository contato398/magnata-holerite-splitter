"""
Camada de autorização da API de esteira (Modulo 01, Fase 4).

**Consolidado** na missão "AUTENTICAÇÃO ADMINISTRATIVA COMPARTILHADA
V1" -- este arquivo era antes uma cópia completa e independente de
`Perfil`/`Sujeito`/`exigir_perfil`; agora é um shim fino sobre
`magnata_os/autenticacao/identidade.py` (fonte única). Nenhum import
existente quebra: `Perfil`, `Sujeito` e `exigir_perfil` continuam
exportados daqui com o MESMO comportamento observável de antes --
`Sujeito(Perfil.GESTOR)` continua funcionando, `exigir_perfil` continua
levantando `PermissaoNegada` DESTE módulo (`.erros.PermissaoNegada`,
que é um `ApiError` com `codigo`/`status_http`, consumido por
`erros.tratar_erro_para_resposta` -- nunca trocado pela base genérica
do pacote compartilhado, que não é um `ApiError`).

Continua SEM AUTENTICAÇÃO REAL: `Sujeito` é um portador de perfil,
nunca o resultado de validar uma sessão/token/senha por si só -- quem
de fato autentica agora é `magnata_os/autenticacao/sessao.py`
(gate fechado nesta mesma missão para o Magnata OS inteiro).
"""
from __future__ import annotations

from typing import FrozenSet

from magnata_os.autenticacao.identidade import Perfil, Sujeito
from magnata_os.autenticacao.identidade import exigir_perfil as _exigir_perfil_base

from .erros import PermissaoNegada

__all__ = ['Perfil', 'Sujeito', 'PermissaoNegada', 'exigir_perfil']


def exigir_perfil(sujeito: Sujeito, perfis_permitidos: FrozenSet[Perfil]) -> None:
    """Mesma assinatura/comportamento de sempre -- delega à checagem
    compartilhada, injetando `.erros.PermissaoNegada` (nunca a base
    genérica) para preservar `codigo`/`status_http` no erro levantado."""
    _exigir_perfil_base(sujeito, perfis_permitidos, classe_erro=PermissaoNegada)
