"""Porta neutra para resolucao canonica de clientes da prestacao."""

from __future__ import annotations

from typing import Protocol

from .contratos import (
    DimensaoResolucao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)


_ORIGENS_SUPORTADAS = frozenset(
    {"COLABORADOR", "FUNCIONARIO", "UNIDADE_POSTO"}
)


class FonteVinculosPrestacao(Protocol):
    """Fonte substituivel de vinculos canonicos para cliente."""

    def resolver_clientes(
        self,
        origem: ReferenciaCanonica,
        competencia: ReferenciaCanonica,
    ) -> ResolucaoDimensao: ...


def resolver_clientes_validado(
    fonte: FonteVinculosPrestacao,
    origem: ReferenciaCanonica,
    competencia: ReferenciaCanonica,
) -> ResolucaoDimensao:
    """Executa a porta e valida somente as invariantes estruturais."""

    if origem.tipo_entidade not in _ORIGENS_SUPORTADAS:
        raise ValueError("origem deve ser COLABORADOR, FUNCIONARIO ou UNIDADE_POSTO")
    if competencia.tipo_entidade != "COMPETENCIA":
        raise ValueError("competencia deve ser referencia canonica de COMPETENCIA")

    resultado = fonte.resolver_clientes(origem, competencia)
    if resultado.dimensao != DimensaoResolucao.CLIENTE:
        raise ValueError("resolucao de vinculos deve pertencer a dimensao CLIENTE")
    referencias = resultado.valores_confirmados + resultado.candidatos
    if any(referencia.tipo_entidade != "CLIENTE" for referencia in referencias):
        raise ValueError("resolucao de clientes aceita somente referencias CLIENTE")
    return resultado
