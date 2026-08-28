"""Fonte shadow pura sobre resultados documentais ja processados."""

from __future__ import annotations

from magnata_os.documental.importacao_lote.contratos import (
    ClassificacaoCorrespondencia,
    ResultadoCompetencia,
    ResultadoItem,
    TipoDocumental,
)

from .contratos import (
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
)
from .prestacao_readiness import ItemInventarioPrestacao
from .vinculos_prestacao import (
    FonteVinculosPrestacao,
    resolver_clientes_validado,
)


class FonteInventarioPrestacaoResultadosShadow:
    """Traduz resultados confirmados para o inventario neutro, sem I/O."""

    def __init__(
        self,
        resultados: tuple[ResultadoItem, ...],
        fonte_vinculos: FonteVinculosPrestacao | None = None,
    ):
        self._resultados = tuple(resultados)
        self._fonte_vinculos = fonte_vinculos

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
            item = _converter_resultado(resultado, self._fonte_vinculos)
            if (
                item is not None
                and item.cliente == cliente
                and item.competencia == competencia
            ):
                itens[item.documento_id] = item
        return tuple(itens[chave] for chave in sorted(itens))


def _converter_resultado(
    resultado: ResultadoItem,
    fonte_vinculos: FonteVinculosPrestacao | None,
) -> ItemInventarioPrestacao | None:
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
    if resultado.tipo_documental == TipoDocumental.EXTRATO_CLIENTE:
        cliente = ReferenciaCanonica("CLIENTE", resultado.entidade_resolvida)
    elif resultado.tipo_documental == TipoDocumental.HOLERITE:
        if fonte_vinculos is None:
            return None
        origem = ReferenciaCanonica("FUNCIONARIO", resultado.entidade_resolvida)
        try:
            resolucao = resolver_clientes_validado(
                fonte_vinculos,
                origem,
                competencia,
            )
        except Exception:
            return None
        if (
            resolucao.estado != EstadoResolucaoDimensao.RESOLVIDA
            or len(resolucao.valores_confirmados) != 1
        ):
            return None
        cliente = resolucao.valores_confirmados[0]
    else:
        return None
    return ItemInventarioPrestacao(
        documento_id=resultado.identidade_documental,
        tipo_documental=resultado.tipo_documental.value,
        cliente=cliente,
        competencia=competencia,
    )
