"""
Serializacao JSON dos contratos da API de esteira (Modulo 01, Fase 4).

Os contratos (contratos.py) ja armazenam so tipos JSON-primitivos
(`str`/`int`/`float`/`bool`/`dict`/`tuple`/`None` -- nunca Enum,
datetime ou MappingProxyType) *dentro* de cada campo escalar; o que
falta para virar JSON de verdade e so achatar a ESTRUTURA (dataclass
aninhado -> dict, tupla -> lista), recursivamente. `para_json()` e essa
unica funcao -- nenhum adapter web precisa reimplementar conversao de
contrato nenhuma vez.
"""
from __future__ import annotations

import dataclasses
from typing import Any


def para_json(valor: Any) -> Any:
    """
    Converte um contrato (ou qualquer estrutura aninhada de contratos,
    tuplas, dicts e primitivos) para algo diretamente aceito por
    `json.dumps()`. Nunca deixa passar um Enum, datetime ou outro tipo
    nao-JSON-nativo adiante -- se algum contrato futuro introduzir um
    campo assim, `json.dumps()` no chamador falha alto (TypeError), o
    que e preferivel a serializar de forma inconsistente/silenciosa.
    """
    if dataclasses.is_dataclass(valor) and not isinstance(valor, type):
        return {campo.name: para_json(getattr(valor, campo.name)) for campo in dataclasses.fields(valor)}
    if isinstance(valor, (list, tuple)):
        return [para_json(item) for item in valor]
    if isinstance(valor, dict):
        return {chave: para_json(item) for chave, item in valor.items()}
    return valor
