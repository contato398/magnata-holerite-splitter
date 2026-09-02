"""Camada de autorização da Confirmação de Alocação.

**Consolidado** na missão "AUTENTICAÇÃO ADMINISTRATIVA COMPARTILHADA
V1" -- este arquivo era antes uma cópia completa e independente de
`Perfil`/`Sujeito`/`exigir_perfil`/`PermissaoNegada` (criada na missão
anterior, "ENTRADA OPERACIONAL + POSTGRES PRÓPRIO V1", como duplicação
DELIBERADA de `documental/modulo01/api/autorizacao.py` para preservar
desacoplamento entre módulos). Agora é um shim fino sobre
`magnata_os/autenticacao/identidade.py` (fonte única, compartilhada
entre TODOS os módulos -- autenticação é infraestrutura, não domínio de
um módulo). Nenhum import existente quebra: `Perfil`, `Sujeito`,
`PermissaoNegada` e `exigir_perfil` continuam exportados daqui com o
MESMO comportamento observável de antes.

Continua SEM AUTENTICAÇÃO REAL nesta camada de autorização em si --
quem de fato autentica agora é `magnata_os/autenticacao/sessao.py`
(gate fechado nesta mesma missão para o Magnata OS inteiro, não mais
específico de alocação)."""
from __future__ import annotations

from magnata_os.autenticacao.identidade import Perfil, PermissaoNegada, Sujeito, exigir_perfil

__all__ = ['Perfil', 'Sujeito', 'PermissaoNegada', 'exigir_perfil']
