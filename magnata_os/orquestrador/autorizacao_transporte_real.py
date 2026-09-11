"""Gate fail-closed de três barreiras independentes para o transporte
WhatsApp real (Evolution).

Esta é a ÚNICA função autorizada a decidir se um ciclo de produção pode
compor `ExecutorEvolutionLegado` em vez de `ExecutorAcaoDryRun`. Nenhum
outro ponto do código deve reimplementar esta lógica.

Reaproveita `deve_rodar_em_dry_run()` (`configuracao.py`) sem alterar sua
semântica histórica -- aqui ela funciona só como VETO (bloqueia quando
True), nunca como habilitadora. O fato de `deve_rodar_em_dry_run()` ser
fail-OPEN para ausência de variável (ausência = não vetar) é inofensivo
neste uso: as outras duas barreiras já partem fechadas por padrão, então
um veto ausente nunca abre nada sozinho.

REAL = autorizar_transporte_real is True
       AND ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO == "1" (exato)
       AND NOT deve_rodar_em_dry_run()

Barreira 1 (estrutural): `autorizar_transporte_real` é parâmetro de
código, default literal `False` -- nunca lido de variável de ambiente.
Só uma mudança de código, revisada em PR, pode virar `True`.

Barreira 2 (operacional positiva): `ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO`
exige o valor exato `"1"` -- ausência, vazio, "0", "true", "yes", "01",
" 1" ou qualquer outro valor são tratados como NÃO autorizado. Mais
estrito de propósito que o parser de `ORQUESTRADOR_DRY_RUN`: esta
variável só pode HABILITAR, então quanto mais estreito o valor aceito,
menor o risco de uma configuração ambígua ligar o transporte real por
engano.

Barreira 3 (veto): `ORQUESTRADOR_DRY_RUN` ativo bloqueia sempre,
independente das outras duas.
"""
from __future__ import annotations

import os

from .configuracao import deve_rodar_em_dry_run

NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL = 'ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO'
_VALOR_AUTORIZADO_EXATO = '1'


def _autorizacao_operacional_explicita() -> bool:
    """Fail-closed: só o valor exato '1' habilita. Nunca aceita variantes
    (case, espaço, zero-padding) -- qualquer ambiguidade de parsing aqui
    seria um risco de habilitação acidental, não de bloqueio acidental."""
    valor = os.environ.get(NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL)
    return valor == _VALOR_AUTORIZADO_EXATO


def transporte_real_habilitado(*, autorizar_transporte_real: bool) -> bool:
    """Única função que decide se o transporte real pode ser composto.

    `autorizar_transporte_real` é sempre um argumento explícito do
    chamador (nunca lido de ambiente aqui) -- é a barreira estrutural.
    """
    if autorizar_transporte_real is not True:
        return False
    if not _autorizacao_operacional_explicita():
        return False
    if deve_rodar_em_dry_run():
        return False
    return True
