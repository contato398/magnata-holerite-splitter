"""
Politica de autonomia executavel -- MATRIZ_AUTONOMIA.md (Central Command,
Etapa 12) virando codigo, nao so tabela em markdown.

Regra dura, sem excecao (MATRIZ_AUTONOMIA.md paragrafo 1, "fail-safe,
nunca fail-open"): TipoEvento sem politica declarada e HUMAN_REQUIRED
por padrao. Isto e testado explicitamente -- ver
test_magnata_os_orquestrador_nucleo.py,
test_tipo_sem_politica_declarada_e_sempre_human_required.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Mapping

from .eventos import TipoEvento


class NivelAutonomia(IntEnum):
    OBSERVE = 0
    DETECT = 1
    CLASSIFY = 2
    PROPOSE = 3
    EXECUTE_SAFE = 4
    HUMAN_REQUIRED = 5


# Politica declarada -- SO estes tipos tem nivel < 5, e SO porque cada
# um escreve apenas em AUTO_FACT/DERIVED (TAXONOMIA_MEMORIA.md), nunca
# em HUMAN_DECISION, producao, Airtable, Make.com ou app.py. Adicionar
# um TipoEvento aqui com EXECUTE_SAFE e, por definicao, uma decisao
# arquitetural -- registrar em DECISIONS.md, nunca so no codigo.
_POLITICA: Mapping[TipoEvento, NivelAutonomia] = {
    TipoEvento.GIT_MAIN_AVANCOU: NivelAutonomia.EXECUTE_SAFE,
    TipoEvento.PR_MESCLADO: NivelAutonomia.EXECUTE_SAFE,
    TipoEvento.SUITE_DIVERGIU: NivelAutonomia.EXECUTE_SAFE,
    TipoEvento.ESTRUTURA_CODIGO_DIVERGIU: NivelAutonomia.PROPOSE,
    # Comunicacao operacional jamais executa por simples deteccao de uma
    # origem pronta. O V1 apenas registra/propoe e para em WAITING_GATE.
    # Uma futura mudanca deste nivel exigira decisao arquitetural explicita.
    TipoEvento.COMUNICACAO_SOLICITADA: NivelAutonomia.HUMAN_REQUIRED,
}


def nivel_para(event_type: TipoEvento) -> NivelAutonomia:
    """Fail-safe: TipoEvento ausente de _POLITICA volta HUMAN_REQUIRED,
    nunca EXECUTE_SAFE por omissao."""
    return _POLITICA.get(event_type, NivelAutonomia.HUMAN_REQUIRED)


def pode_executar_automaticamente(event_type: TipoEvento) -> bool:
    return nivel_para(event_type) == NivelAutonomia.EXECUTE_SAFE
