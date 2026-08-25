"""Politica fail-safe de autorrecuperacao do Grande Orquestrador.

Autonomia de execucao e autonomia de recuperacao sao decisoes diferentes:
uma Acao pode ser segura na primeira chamada e ainda assim nao ser segura
para repetir depois de timeout/crash. Por isso esta matriz e separada de
``politica_autonomia.py`` e exige duas provas explicitas para retry automatico:

1. o tipo de evento foi autorizado para recuperacao automatica;
2. a Acao correspondente possui semantica idempotente conhecida.

Ausencia de entrada nunca significa permissao: o default e escalar ao humano.
"""
from __future__ import annotations

import dataclasses
from typing import Mapping

from .eventos import TipoEvento


@dataclasses.dataclass(frozen=True)
class PoliticaRecuperacao:
    retry_automatico: bool
    acao_idempotente: bool
    justificativa: str

    @property
    def permite_retry_seguro(self) -> bool:
        return self.retry_automatico and self.acao_idempotente


_NEGAR_POR_OMISSAO = PoliticaRecuperacao(
    retry_automatico=False,
    acao_idempotente=False,
    justificativa='tipo sem politica explicita de recuperacao',
)


# Somente a atualizacao de AUTO_FACT entra na V1. Ela recalcula o snapshot
# a partir das fontes e substitui o mesmo artefato derivado; nao envia
# mensagem, nao escreve em producao e nao altera HUMAN_DECISION.
_POLITICAS: Mapping[TipoEvento, PoliticaRecuperacao] = {
    TipoEvento.GIT_MAIN_AVANCOU: PoliticaRecuperacao(
        retry_automatico=True,
        acao_idempotente=True,
        justificativa=(
            'recalculo idempotente de AUTO_FACT derivado do Git; '
            'sem escrita em producao ou canal externo'
        ),
    ),
}


def politica_recuperacao_para(event_type: TipoEvento) -> PoliticaRecuperacao:
    """Retorna politica declarada; desconhecido e bloqueado por omissao."""
    return _POLITICAS.get(event_type, _NEGAR_POR_OMISSAO)
