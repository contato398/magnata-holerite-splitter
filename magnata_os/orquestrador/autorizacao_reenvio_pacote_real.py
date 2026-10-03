"""Gate fail-closed de três barreiras independentes para o cutover do
reenvio do pacote Holerite+Ponto para o caminho novo do Orquestrador
(`magnata_os/classificacao/politica_reenvio_pacote_holerite_ponto_v1.py`
+ adapters em `magnata_os/orquestrador/adapters/`).

Mesmo padrão de `autorizacao_transporte_real.transporte_real_habilitado`
-- esta é a ÚNICA função autorizada a decidir se `app.py` pode delegar
`_reenviar_pacote_holerite_ponto` ao caminho novo em vez do caminho
legado. Nenhum outro ponto do código deve reimplementar esta lógica.

REAL = autorizar_reenvio_via_orquestrador is True
       AND ORQUESTRADOR_REENVIO_PACOTE_HABILITADO == "1" (exato)
       AND NOT deve_rodar_em_dry_run()

Barreira 1 (estrutural): `autorizar_reenvio_via_orquestrador` é
parâmetro de código, default literal `False` -- nunca lido de variável
de ambiente. Só uma mudança de código, revisada em PR, pode virar
`True`.

Barreira 2 (operacional positiva): `ORQUESTRADOR_REENVIO_PACOTE_
HABILITADO` exige o valor exato `"1"` -- ausência, vazio, "0", "true",
"yes" ou qualquer outro valor são tratados como NÃO autorizado.

Barreira 3 (veto): `ORQUESTRADOR_DRY_RUN` ativo bloqueia sempre,
independente das outras duas -- reaproveita `deve_rodar_em_dry_run()`
(`configuracao.py`) sem alterar sua semântica histórica, só como veto.

Ausência de qualquer uma das três mantém o caminho legado inalterado
em `app.py` -- este gate nunca é, por si só, o cutover; só autoriza
`app.py` a chamá-lo, e isso ainda depende de uma mudança própria em
`app.py` (ver `/mnt/project-files/magnata-os/pacote-autorizacao-app-py.md`).
"""
from __future__ import annotations

import os

from .configuracao import deve_rodar_em_dry_run

NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL = 'ORQUESTRADOR_REENVIO_PACOTE_HABILITADO'
_VALOR_AUTORIZADO_EXATO = '1'


def _autorizacao_operacional_explicita() -> bool:
    """Fail-closed: só o valor exato '1' habilita. Nunca aceita
    variantes (case, espaço, zero-padding)."""
    valor = os.environ.get(NOME_VARIAVEL_AUTORIZACAO_OPERACIONAL)
    return valor == _VALOR_AUTORIZADO_EXATO


def reenvio_pacote_via_orquestrador_habilitado(*, autorizar_reenvio_via_orquestrador: bool) -> bool:
    """Única função que decide se `app.py` pode delegar o reenvio do
    pacote Holerite+Ponto ao caminho novo do Orquestrador.

    `autorizar_reenvio_via_orquestrador` é sempre um argumento explícito
    do chamador (nunca lido de ambiente aqui) -- é a barreira estrutural.
    """
    if autorizar_reenvio_via_orquestrador is not True:
        return False
    if not _autorizacao_operacional_explicita():
        return False
    if deve_rodar_em_dry_run():
        return False
    return True
