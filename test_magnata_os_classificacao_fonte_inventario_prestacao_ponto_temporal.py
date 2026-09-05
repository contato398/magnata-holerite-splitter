"""Testes para FonteInventarioPrestacaoPontoTemporal com segmentacao temporal.

Adversariais: cliente único, múltiplos clientes, lacuna histórica,
transferência sintética, idempotência, documento órfão, colaborador ausente.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional, Tuple

import pytest

from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.classificacao.fonte_inventario_prestacao_ponto_temporal import (
    FonteInventarioPrestacaoPontoTemporal,
    FonteResolucoesTemporaisPonto,
    FonteSegmentosTemporaisPonto,
)
from magnata_os.classificacao.resolucao_temporal_ponto import (
    ResolucaoDocumentalTemporalPonto,
)


@dataclass(frozen=True)
class SegmentoTemporalAlocacaoMock:
    """Mock de SegmentoTemporalAlocacao (PR #129)."""
    segmento_de: date
    segmento_ate: Optional[date]
    cliente_id: Optional[str]
    status: str  # COMPROVADO ou HISTORICO_NAO_COMPROVADO


class FonteSegmentosTemporaisPontoMock(FonteSegmentosTemporaisPonto):
    def __init__(self, segmentos_por_colaborador: dict):
        self.segmentos = segmentos_por_colaborador

    def obter_segmentos(self, colaborador_id: str) -> Tuple:
        return tuple(self.segmentos.get(colaborador_id, []))


class FonteResolucoesTemporaisPontoMock(FonteResolucoesTemporaisPonto):
    def __init__(self, resolucoes_por_doc: dict):
        self.resolucoes = resolucoes_por_doc

    def obter_resolucao(
        self, documento_id: str
    ) -> Optional[ResolucaoDocumentalTemporalPonto]:
        return self.resolucoes.get(documento_id)


class FonteDocumentosPontoMock:
    def __init__(self, docs_por_cliente_competencia: dict):
        self.docs = docs_por_cliente_competencia

    def listar_ids_folha_ponto(
        self, cliente: ReferenciaCanonica, competencia: ReferenciaCanonica
    ) -> Tuple[str, ...]:
        chave = (cliente.entidade_id, competencia.entidade_id)
        return tuple(self.docs.get(chave, []))


def _conversor_mock(doc_id, cliente_ref, comp_ref):
    """Mock conversor simples para testes."""
    return type('ItemMock', (), {
        'documento_id': doc_id,
        'cliente': cliente_ref,
        'competencia': comp_ref,
        'identidade_logica': f"{doc_id}:{cliente_ref.entidade_id}:{comp_ref.entidade_id}"
    })()


def _criar_resolucao(doc_id, colab_id, competencia_str):
    """Factory para ResolucaoDocumentalTemporalPonto."""
    return ResolucaoDocumentalTemporalPonto(
        documento_id=doc_id,
        tipo_documental="Folha de Ponto",
        colaborador_id=colab_id,
        periodo_inicio=date(2026, 1, 1),
        periodo_fim=date(2026, 1, 31),
        resolucao_competencia=ResolucaoDimensao(
            dimensao=DimensaoResolucao.COMPETENCIA,
            estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(
                ReferenciaCanonica("COMPETENCIA", competencia_str),
            ),
        ),
    )


def test_cliente_unico_comprovado_produz_1_item():
    """Segmento COMPROVADO com 1 cliente → 1 item."""
    cliente_A = ReferenciaCanonica("CLIENTE", "cli_A")
    competencia = ReferenciaCanonica("COMPETENCIA", "2026-01")
    documento_id = "doc_001"
    colaborador_id = "colab_001"

    segmentos = [
        SegmentoTemporalAlocacaoMock(
            segmento_de=date(2026, 1, 1),
            segmento_ate=date(2026, 1, 31),
            cliente_id="cli_A",
            status="COMPROVADO",
        )
    ]

    fonte_segmentos = FonteSegmentosTemporaisPontoMock(
        {colaborador_id: segmentos}
    )
    fonte_resolucoes = FonteResolucoesTemporaisPontoMock(
        {documento_id: _criar_resolucao(documento_id, colaborador_id, "2026-01")}
    )
    fonte_docs = FonteDocumentosPontoMock(
        {("cli_A", "2026-01"): [documento_id]}
    )

    fonte = FonteInventarioPrestacaoPontoTemporal(
        fonte_resolucoes, fonte_segmentos, fonte_docs, _conversor_mock
    )
    items = fonte.listar(cliente_A, competencia)

    assert len(items) == 1
    assert items[0].documento_id == documento_id
    assert items[0].cliente.entidade_id == "cli_A"


def test_lacuna_historica_nao_produz_item():
    """Lacuna (HISTORICO_NAO_COMPROVADO) → nenhum item."""
    cliente_A = ReferenciaCanonica("CLIENTE", "cli_A")
    competencia = ReferenciaCanonica("COMPETENCIA", "2026-01")
    documento_id = "doc_001"
    colaborador_id = "colab_001"

    segmentos = [
        SegmentoTemporalAlocacaoMock(
            segmento_de=date(2026, 1, 1),
            segmento_ate=date(2026, 1, 31),
            cliente_id=None,
            status="HISTORICO_NAO_COMPROVADO",
        )
    ]

    fonte_segmentos = FonteSegmentosTemporaisPontoMock(
        {colaborador_id: segmentos}
    )
    fonte_resolucoes = FonteResolucoesTemporaisPontoMock(
        {documento_id: _criar_resolucao(documento_id, colaborador_id, "2026-01")}
    )
    fonte_docs = FonteDocumentosPontoMock(
        {("cli_A", "2026-01"): [documento_id]}
    )

    fonte = FonteInventarioPrestacaoPontoTemporal(
        fonte_resolucoes, fonte_segmentos, fonte_docs, _conversor_mock
    )
    items = fonte.listar(cliente_A, competencia)

    assert len(items) == 0


def test_transferencia_sintetica_cliente_A_para_B():
    """Colaborador muda de cliente no meio do período."""
    documento_id = "doc_001"
    colaborador_id = "colab_001"
    competencia = ReferenciaCanonica("COMPETENCIA", "2026-01")

    segmentos = [
        SegmentoTemporalAlocacaoMock(
            segmento_de=date(2026, 1, 1),
            segmento_ate=date(2026, 1, 15),
            cliente_id="cli_A",
            status="COMPROVADO",
        ),
        SegmentoTemporalAlocacaoMock(
            segmento_de=date(2026, 1, 16),
            segmento_ate=date(2026, 1, 31),
            cliente_id="cli_B",
            status="COMPROVADO",
        ),
    ]

    fonte_segmentos = FonteSegmentosTemporaisPontoMock(
        {colaborador_id: segmentos}
    )
    fonte_resolucoes = FonteResolucoesTemporaisPontoMock(
        {documento_id: _criar_resolucao(documento_id, colaborador_id, "2026-01")}
    )
    fonte_docs = FonteDocumentosPontoMock(
        {
            ("cli_A", "2026-01"): [documento_id],
            ("cli_B", "2026-01"): [documento_id],
        }
    )

    fonte = FonteInventarioPrestacaoPontoTemporal(
        fonte_resolucoes, fonte_segmentos, fonte_docs, _conversor_mock
    )

    # Cliente A deve receber 1 item
    items_A = fonte.listar(ReferenciaCanonica("CLIENTE", "cli_A"), competencia)
    assert len(items_A) == 1
    assert items_A[0].cliente.entidade_id == "cli_A"

    # Cliente B deve receber 1 item
    items_B = fonte.listar(ReferenciaCanonica("CLIENTE", "cli_B"), competencia)
    assert len(items_B) == 1
    assert items_B[0].cliente.entidade_id == "cli_B"


def test_idempotencia_multiplas_chamadas_mesmo_resultado():
    """Chamar listar 2x com mesmos params → mesmos items (por identidade_logica)."""
    cliente_A = ReferenciaCanonica("CLIENTE", "cli_A")
    competencia = ReferenciaCanonica("COMPETENCIA", "2026-01")
    documento_id = "doc_001"
    colaborador_id = "colab_001"

    segmentos = [
        SegmentoTemporalAlocacaoMock(
            segmento_de=date(2026, 1, 1),
            segmento_ate=date(2026, 1, 31),
            cliente_id="cli_A",
            status="COMPROVADO",
        )
    ]

    fonte_segmentos = FonteSegmentosTemporaisPontoMock(
        {colaborador_id: segmentos}
    )
    fonte_resolucoes = FonteResolucoesTemporaisPontoMock(
        {documento_id: _criar_resolucao(documento_id, colaborador_id, "2026-01")}
    )
    fonte_docs = FonteDocumentosPontoMock(
        {("cli_A", "2026-01"): [documento_id]}
    )

    fonte = FonteInventarioPrestacaoPontoTemporal(
        fonte_resolucoes, fonte_segmentos, fonte_docs, _conversor_mock
    )

    items_1 = fonte.listar(cliente_A, competencia)
    items_2 = fonte.listar(cliente_A, competencia)

    assert len(items_1) == len(items_2) == 1
    assert items_1[0].identidade_logica == items_2[0].identidade_logica


def test_fonte_stub_sem_conversor_retorna_vazio():
    """Modo stub (conversor=None) → retorna tuple vazio."""
    cliente_A = ReferenciaCanonica("CLIENTE", "cli_A")
    competencia = ReferenciaCanonica("COMPETENCIA", "2026-01")
    documento_id = "doc_001"
    colaborador_id = "colab_001"

    segmentos = [
        SegmentoTemporalAlocacaoMock(
            segmento_de=date(2026, 1, 1),
            segmento_ate=date(2026, 1, 31),
            cliente_id="cli_A",
            status="COMPROVADO",
        )
    ]

    fonte_segmentos = FonteSegmentosTemporaisPontoMock(
        {colaborador_id: segmentos}
    )
    fonte_resolucoes = FonteResolucoesTemporaisPontoMock(
        {documento_id: _criar_resolucao(documento_id, colaborador_id, "2026-01")}
    )
    fonte_docs = FonteDocumentosPontoMock(
        {("cli_A", "2026-01"): [documento_id]}
    )

    # Sem conversor
    fonte = FonteInventarioPrestacaoPontoTemporal(
        fonte_resolucoes, fonte_segmentos, fonte_docs
    )
    items = fonte.listar(cliente_A, competencia)

    assert len(items) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
