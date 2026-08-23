"""
Classificacao de falha para decidir retry.

O motor nunca decide sozinho, por heuristica de texto de mensagem de
erro, se uma excecao e "tentar de novo" ou "gate humano" -- texto de
erro pode conter dado sensivel e nunca vira criterio de decisao nem e
persistido inteiro (ver RegistroExecucao.last_error_classe: so a
CLASSE, nunca a mensagem). A classificacao e por TIPO de excecao,
declarada aqui.
"""
from __future__ import annotations

from enum import Enum


class ClasseFalha(str, Enum):
    TRANSIENT = 'TRANSIENT'          # rede, timeout -- retry com backoff
    PERMANENT = 'PERMANENT'          # bug/dado invalido -- nunca retry
    HUMAN_GATE = 'HUMAN_GATE'        # cruzou CLAUDE.md paragrafo 12-I -- para, sempre
    INVALID_INPUT = 'INVALID_INPUT'  # evento malformado -- nunca retry


class FalhaGateHumano(Exception):
    """Uma Acao levanta isto explicitamente quando descobre, em tempo de
    execucao, que cruzaria um gate humano -- nunca inferido pelo motor
    a partir do texto do erro."""


class FalhaTransitoria(Exception):
    """Uma Acao levanta isto para sinalizar falha que vale a pena tentar
    de novo (timeout, erro de rede transitorio)."""


_MAPA: dict = {
    FalhaGateHumano: ClasseFalha.HUMAN_GATE,
    FalhaTransitoria: ClasseFalha.TRANSIENT,
    ValueError: ClasseFalha.INVALID_INPUT,
}


def classificar(exc: BaseException) -> ClasseFalha:
    for tipo, classe in _MAPA.items():
        if isinstance(exc, tipo):
            return classe
    # Fail-safe: excecao de tipo desconhecido NUNCA e tratada como
    # transitoria (retry automatico de algo desconhecido pode repetir
    # dano) -- vira falha permanente, visivel no audit log para revisao
    # humana, nunca reprocessada sozinha.
    return ClasseFalha.PERMANENT
