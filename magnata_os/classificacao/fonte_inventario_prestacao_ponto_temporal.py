"""Fonte de inventário para Folha/Cartão de Ponto com resolução temporal real.

Wiring ponta-a-ponta:
  PDF → ResolucaoDocumentalTemporalPonto (competência resolvida)
  → SegmentoTemporalAlocacao (cliente histórico comprovado/lacuna)
  → ItemInventarioPrestacao (somente COMPROVADO produz cliente)

Reutiliza fundação PR #129 (Posto↔Cliente) por porta neutra (Protocols).
Nunca importa Postgres; nunca duplica materializador; sem acoplamento.

COMPROVADO → cliente real
HISTORICO_NAO_COMPROVADO → cliente=None (nunca fabrica presença)
Múltiplos clientes comprovados → 1 item por cliente (idêntico documento_id)

NOTA IMPLEMENTAÇÃO: Modo funcional com callback injetável para
conversão de resultado semântico → ItemInventarioPrestacao. Quando
conversor não injetado, retorna tuple vazio (stub para testes de
lógica pura de filtragem).
"""
from __future__ import annotations

from typing import Optional, Protocol, Tuple

from .contratos import ReferenciaCanonica
from .inventario_prestacao import FonteInventarioPrestacao
from .prestacao_readiness import ItemInventarioPrestacao
from .resolucao_temporal_ponto import ResolucaoDocumentalTemporalPonto


class FonteSegmentosTemporaisPonto(Protocol):
    """Porta neutra: fornece SegmentoTemporalAlocacao já materializados.

    Consumidor não conhece Postgres, adapters ou materializador.
    Responsabilidade de quem injeta: chamar material realizador puro
    e passar resultado pronto.
    """

    def obter_segmentos(
        self, colaborador_id: str
    ) -> Tuple: ...  # Tuple[SegmentoTemporalAlocacao, ...]


class FonteResolucoesTemporaisPonto(Protocol):
    """Porta neutra: fornece ResolucaoDocumentalTemporalPonto.

    Implementado por adapter Postgres (magnata_os/documental/);
    classificacao/ nunca conhece esse detalhe.
    """

    def obter_resolucao(
        self, documento_id: str
    ) -> Optional[ResolucaoDocumentalTemporalPonto]: ...


class FonteInventarioPrestacaoPontoTemporal:
    """Implementa FonteInventarioPrestacao para Folha/Cartão de Ponto.

    Filtra segmentos comprovados via PR #129 (Protocols neutros).
    Converte resultado semântico → ItemInventarioPrestacao via callback injetado.
    Nunca fabrica cliente para HISTORICO_NAO_COMPROVADO.
    """

    def __init__(
        self,
        fonte_resolucoes: FonteResolucoesTemporaisPonto,
        fonte_segmentos: FonteSegmentosTemporaisPonto,
        fonte_documentos_ponto,  # Protocol: listar_ids_folha_ponto(cliente, competencia)
        conversor_resultado_para_item=None,  # Optional: (doc_id, cliente_ref, competencia_ref) -> ItemInventarioPrestacao | None
    ):
        """
        Args:
            fonte_resolucoes: Fornece ResolucaoDocumentalTemporalPonto por documento_id
            fonte_segmentos: Fornece SegmentoTemporalAlocacao por colaborador_id
            fonte_documentos_ponto: Fornece IDs de Folha já ingeridos
            conversor_resultado_para_item: Opcional. Se fornecido, callback que converte
                (documento_id, cliente_ref, competencia_ref) → ItemInventarioPrestacao | None.
                Se None, retorna tuple vazio (modo stub para testes de lógica pura).
        """
        self._resolucoes = fonte_resolucoes
        self._segmentos = fonte_segmentos
        self._documentos = fonte_documentos_ponto
        self._conversor = conversor_resultado_para_item

    def listar(
        self, cliente: ReferenciaCanonica, competencia: ReferenciaCanonica
    ) -> Tuple[ItemInventarioPrestacao, ...]:
        """Retorna items de Folha de Ponto para cliente/competência.

        Lógica:
        1. Itera documentos de Folha já processados
        2. Para cada doc, obtém ResolucaoDocumentalTemporalPonto
        3. Valida: competência RESOLVIDA, colaborador presente, períodos válidos
        4. Obtém segmentos (resultado de materializar_segmentos_alocacao_com_cliente)
        5. Filtra por interseção temporal com período do documento
        6. Extrai APENAS o cliente solicitado com status COMPROVADO
        7. Converte para ItemInventarioPrestacao usando callback (se disponível)
        8. Dedup por identidade_logica; retorna determinístico (ordenado).
        """
        if self._conversor is None:
            # Modo stub: retorna vazio (para testes de lógica pura de filtragem)
            return tuple()

        items = []
        vistos = set()

        # Itera documentos já ingeridos
        for documento_id in self._documentos.listar_ids_folha_ponto(
            cliente, competencia
        ):
            resolucao = self._resolucoes.obter_resolucao(documento_id)
            if resolucao is None:
                continue

            # Validações básicas
            if not resolucao.colaborador_id:
                continue
            if resolucao.periodo_inicio is None or resolucao.periodo_fim is None:
                continue
            if (
                resolucao.resolucao_competencia.estado
                != "RESOLVIDA"  # EstadoResolucaoDimensao.RESOLVIDA
            ):
                continue

            # Obtém segmentos materializados
            segmentos = self._segmentos.obter_segmentos(
                resolucao.colaborador_id
            )

            # Filtra por interseção temporal com período do documento
            segmentos_no_periodo = [
                seg
                for seg in segmentos
                if seg.segmento_de <= resolucao.periodo_fim
                and (
                    seg.segmento_ate is None
                    or seg.segmento_ate >= resolucao.periodo_inicio
                )
            ]

            # Extrai APENAS o cliente solicitado dos segmentos COMPROVADOS
            # (sem fabricar para HISTORICO_NAO_COMPROVADO)
            cliente_encontrado = None
            for seg in segmentos_no_periodo:
                if (seg.status == "COMPROVADO" and
                    seg.cliente_id == cliente.entidade_id):
                    cliente_encontrado = cliente
                    break

            if cliente_encontrado is None:
                # Cliente solicitado não tem segmento COMPROVADO
                continue

            # 1 item para o cliente solicitado (quando COMPROVADO neste período)
            # Converte para ItemInventarioPrestacao via callback
            item = self._conversor(documento_id, cliente_encontrado, competencia)
            if item is None:
                continue

            # Dedup por identidade_logica
            chave = item.identidade_logica
            if chave in vistos:
                continue
            vistos.add(chave)
            items.append(item)

        # Retorna determinístico (ordenado por documento + cliente)
        return tuple(
            sorted(items, key=lambda i: (i.documento_id, i.cliente.entidade_id))
        )
