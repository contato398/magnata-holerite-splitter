"""Fonte shadow pura sobre resultados documentais ja processados."""

from __future__ import annotations

from magnata_os.documental.importacao_lote.contratos import (
    ClassificacaoCorrespondencia,
    ResultadoCompetencia,
    ResultadoItem,
    TipoDocumental,
)

from .contratos import ReferenciaCanonica
from .prestacao_readiness import ItemInventarioPrestacao


class FonteInventarioPrestacaoResultadosShadow:
    """Traduz resultados confirmados para o inventario neutro, sem I/O."""

    def __init__(self, resultados: tuple[ResultadoItem, ...]):
        self._resultados = tuple(resultados)

    def listar(
        self,
        cliente: ReferenciaCanonica,
        competencia: ReferenciaCanonica,
    ) -> tuple[ItemInventarioPrestacao, ...]:
        if cliente.tipo_entidade != "CLIENTE":
            raise ValueError("cliente deve ser referencia canonica de CLIENTE")
        if competencia.tipo_entidade != "COMPETENCIA":
            raise ValueError(
                "competencia deve ser referencia canonica de COMPETENCIA"
            )

        itens: dict[str, ItemInventarioPrestacao] = {}
        for resultado in self._resultados:
            item = _converter_resultado(resultado)
            if (
                item is not None
                and item.cliente == cliente
                and item.competencia == competencia
            ):
                itens[item.documento_id] = item
        return tuple(itens[chave] for chave in sorted(itens))


def _converter_resultado(
    resultado: ResultadoItem,
) -> ItemInventarioPrestacao | None:
    # Em ResultadoItem, somente EXTRATO_CLIENTE resolve diretamente uma
    # entidade CLIENTE. Holerite resolve FUNCIONARIO e nao pode ser promovido
    # silenciosamente a cliente sem a relacao oficial funcionario/unidade.
    if resultado.tipo_documental != TipoDocumental.EXTRATO_CLIENTE:
        return None
    if resultado.classificacao != ClassificacaoCorrespondencia.EXACT:
        return None
    if not resultado.entidade_resolvida or not resultado.identidade_documental:
        return None
    if resultado.resultado_competencia != ResultadoCompetencia.CONFIRMADA:
        return None
    if resultado.competencia_ano_mes_extraido is None:
        return None

    ano, mes = resultado.competencia_ano_mes_extraido
    competencia = ReferenciaCanonica("COMPETENCIA", f"{ano:04d}-{mes:02d}")
    cliente = ReferenciaCanonica("CLIENTE", resultado.entidade_resolvida)
    return ItemInventarioPrestacao(
        documento_id=resultado.identidade_documental,
        tipo_documental=resultado.tipo_documental.value,
        cliente=cliente,
        competencia=competencia,
    )
