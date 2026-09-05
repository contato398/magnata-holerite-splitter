"""Testes puros do resolvedor temporal de segmentos (23 casos obrigatórios).

Todos os testes são funções puras — zero banco, zero I/O, zero Airtable,
zero Flask. Testes mockam TuplaAlocacaoComClientes diretamente.

Missão "CORREÇÃO DEFINITIVA DO PR #129 — RESOLUÇÃO TEMPORAL POSTO↔CLIENTE V1".
"""
from datetime import date
from typing import Optional, Tuple

import pytest

from magnata_os.documental.alocacao.resolucao_segmentos_temporais import (
    materializar_segmentos_alocacao_com_cliente,
)
from magnata_os.documental.alocacao.temporal import (
    SegmentoTemporalAlocacao,
    SobreposicaoClientePorPostoError,
    StatusSegmentoTemporal,
    TuplaAlocacaoComClientes,
)


def _fazer_tupla(
    alocacao_id: str,
    posto_id: str,
    cliente_id: Optional[str],
    cliente_vigente_de: Optional[date],
    cliente_vigente_ate: Optional[date],
) -> TuplaAlocacaoComClientes:
    """Helper para criar tupla mock do adapter."""
    return TuplaAlocacaoComClientes(
        vinculo_id="v1",
        colaborador_id="c1",
        alocacao_id=alocacao_id,
        posto_id=posto_id,
        cliente_id=cliente_id,
        alocacao_vigente_de=date(2026, 6, 1),
        alocacao_vigente_ate=date(2026, 7, 31),
        cliente_vigente_de=cliente_vigente_de,
        cliente_vigente_ate=cliente_vigente_ate,
    )


class TestResolvedorTemporalSegmentos:
    """Testes puros do resolvedor de segmentação temporal."""

    def test_1_nenhum_cliente_em_toda_janela(self):
        """Sem cliente em nenhum período → 1 segmento NULL-HISTORICO."""
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuple(),
        )
        assert len(resultado) == 1
        seg = resultado[0]
        assert seg.cliente_id is None
        assert seg.status == StatusSegmentoTemporal.HISTORICO_NAO_COMPROVADO
        assert seg.segmento_de == date(2026, 6, 1)
        assert seg.segmento_ate == date(2026, 7, 31)

    def test_2_cliente_cobre_tudo(self):
        """Cliente único que cobre período inteiro → 1 COMPROVADO."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), date(2026, 7, 31)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        assert len(resultado) == 1
        seg = resultado[0]
        assert seg.cliente_id == "cl-A"
        assert seg.status == StatusSegmentoTemporal.COMPROVADO

    def test_3_lacuna_inicial_cliente(self):
        """Lacuna inicial + cliente → 2 segmentos (NULL, COMPROVADO)."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 15), date(2026, 7, 31)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        assert len(resultado) == 2
        assert resultado[0].cliente_id is None
        assert resultado[0].segmento_ate == date(2026, 6, 14)
        assert resultado[1].cliente_id == "cl-A"

    def test_4_lacuna_final_cliente(self):
        """Cliente + lacuna final → 2 segmentos (COMPROVADO, NULL)."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), date(2026, 7, 15)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        assert len(resultado) == 2
        assert resultado[0].cliente_id == "cl-A"
        assert resultado[1].cliente_id is None
        assert resultado[1].segmento_de == date(2026, 7, 16)

    def test_5_lacuna_intermediaria(self):
        """Cliente A + lacuna + Cliente B → 3 segmentos."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), date(2026, 6, 30)),
            _fazer_tupla("a1", "p1", "cl-B", date(2026, 7, 5), date(2026, 7, 31)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        assert len(resultado) == 3
        assert resultado[0].cliente_id == "cl-A"
        assert resultado[1].cliente_id is None
        assert resultado[1].segmento_de == date(2026, 7, 1)
        assert resultado[1].segmento_ate == date(2026, 7, 4)
        assert resultado[2].cliente_id == "cl-B"

    def test_6_a_para_b_sem_lacuna(self):
        """Cliente A → Cliente B contiguos → 2 COMPROVADO (sem lacuna)."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), date(2026, 6, 30)),
            _fazer_tupla("a1", "p1", "cl-B", date(2026, 7, 1), date(2026, 7, 31)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        assert len(resultado) == 2
        assert all(seg.status == StatusSegmentoTemporal.COMPROVADO for seg in resultado)

    def test_7_multiplas_trocas_3_clientes(self):
        """3 clientes com transições → 3 COMPROVADO, sem lacunas."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), date(2026, 6, 10)),
            _fazer_tupla("a1", "p1", "cl-B", date(2026, 6, 11), date(2026, 6, 20)),
            _fazer_tupla("a1", "p1", "cl-C", date(2026, 6, 21), date(2026, 7, 31)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        assert len(resultado) == 3

    def test_8_cliente_fora_antes(self):
        """Cliente totalmente antes da alocação → lacuna inteira."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 5, 1), date(2026, 5, 31)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        assert len(resultado) == 1
        assert resultado[0].cliente_id is None

    def test_9_cliente_fora_depois(self):
        """Cliente totalmente depois da alocação → lacuna inteira."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 8, 1), date(2026, 8, 31)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        assert len(resultado) == 1
        assert resultado[0].cliente_id is None

    def test_10_alocacao_aberta_cliente_fechado(self):
        """Alocação aberta (NULL) + cliente fechado → lacuna após cliente."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), date(2026, 6, 30)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=None,  # aberta
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        assert len(resultado) == 2
        assert resultado[0].cliente_id == "cl-A"
        assert resultado[1].cliente_id is None

    def test_11_alocacao_aberta_cliente_aberto(self):
        """Alocação aberta + cliente aberto → cliente até fim da janela."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), None),  # aberto
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=None,
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        assert len(resultado) == 1
        assert resultado[0].cliente_id == "cl-A"
        assert resultado[0].segmento_ate == date(2026, 7, 31)

    def test_12_janela_menor_que_alocacao(self):
        """Janela subset da alocação → cobertura apenas da janela."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), date(2026, 7, 31)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 10),
            janela_fim=date(2026, 7, 20),
            tuplas_do_adapter=tuplas,
        )
        assert len(resultado) == 1
        assert resultado[0].segmento_de == date(2026, 6, 10)
        assert resultado[0].segmento_ate == date(2026, 7, 20)

    def test_13_alocacao_menor_que_janela(self):
        """Alocação subset da janela → cobertura APENAS da interseção (alocação)."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 15), date(2026, 7, 15)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 15),
            vigente_ate=date(2026, 7, 15),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        # intervalo_efetivo = INTERSEÇÃO(alocação, janela) = 6/15-7/15
        # Cobertura é APENAS esse período, não há lacunas fora da intersecção
        assert len(resultado) == 1
        assert resultado[0].cliente_id == "cl-A"
        assert resultado[0].segmento_de == date(2026, 6, 15)
        assert resultado[0].segmento_ate == date(2026, 7, 15)

    def test_14_dia_unico(self):
        """Período de 1 dia → segmento sem divisão arbitrária."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 15), date(2026, 6, 15)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 15),
            vigente_ate=date(2026, 6, 15),
            janela_inicio=date(2026, 6, 15),
            janela_fim=date(2026, 6, 15),
            tuplas_do_adapter=tuplas,
        )
        assert len(resultado) == 1
        assert resultado[0].segmento_de == resultado[0].segmento_ate

    def test_15_bordas_inclusivas(self):
        """Bordas inclusivas → sem sobreposição no resultado."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), date(2026, 6, 15)),
            _fazer_tupla("a1", "p1", "cl-B", date(2026, 6, 16), date(2026, 7, 31)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        assert len(resultado) == 2
        assert resultado[0].segmento_ate == date(2026, 6, 15)
        assert resultado[1].segmento_de == date(2026, 6, 16)

    def test_16_entrada_desordenada(self):
        """Entrada com tuplas desordenadas → reordena internamente."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-B", date(2026, 7, 5), date(2026, 7, 31)),
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), date(2026, 6, 30)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        # Deve estar em ordem: A, lacuna, B
        assert resultado[0].cliente_id == "cl-A"
        assert resultado[1].cliente_id is None
        assert resultado[2].cliente_id == "cl-B"

    def test_17_cobertura_integral(self):
        """Cobertura integral: soma de segmentos = período alocação."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), date(2026, 6, 20)),
            _fazer_tupla("a1", "p1", "cl-B", date(2026, 7, 10), date(2026, 7, 31)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        # Verificar que não há gaps na cobertura
        esperado = 61  # 30 dias em junho + 31 em julho
        coberto = 0
        for seg in resultado:
            dias = (seg.segmento_ate - seg.segmento_de).days + 1
            coberto += dias
        assert coberto == esperado

    def test_18_zero_sobreposicao_resultado(self):
        """Segmentos resultado não se sobrepõem."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), date(2026, 6, 15)),
            _fazer_tupla("a1", "p1", "cl-B", date(2026, 6, 20), date(2026, 7, 31)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        for i in range(len(resultado) - 1):
            prox_inicio = (resultado[i].segmento_ate + date.resolution).toordinal()
            atual_fim = resultado[i + 1].segmento_de.toordinal()
            assert prox_inicio <= atual_fim

    def test_19_cliente_nunca_inventado(self):
        """Cliente nunca é fabricado; cliente_id é apenas de fatos reais."""
        tuplas = tuple()  # sem clientes
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 1),
            janela_fim=date(2026, 7, 31),
            tuplas_do_adapter=tuplas,
        )
        for seg in resultado:
            assert seg.cliente_id is None

    def test_20_tupla_outro_alocacao_id_erro(self):
        """Tupla de outro alocacao_id → ValueError explícito."""
        tuplas = (
            _fazer_tupla("a99", "p1", "cl-A", date(2026, 6, 1), date(2026, 7, 31)),
        )
        with pytest.raises(ValueError, match="alocacao_id"):
            materializar_segmentos_alocacao_com_cliente(
                alocacao_id="a1",
                posto_id="p1",
                vigente_de=date(2026, 6, 1),
                vigente_ate=date(2026, 7, 31),
                janela_inicio=date(2026, 6, 1),
                janela_fim=date(2026, 7, 31),
                tuplas_do_adapter=tuplas,
            )

    def test_21_tupla_outro_posto_id_erro(self):
        """Tupla de outro posto_id → ValueError explícito."""
        tuplas = (
            _fazer_tupla("a1", "p99", "cl-A", date(2026, 6, 1), date(2026, 7, 31)),
        )
        with pytest.raises(ValueError, match="posto_id"):
            materializar_segmentos_alocacao_com_cliente(
                alocacao_id="a1",
                posto_id="p1",
                vigente_de=date(2026, 6, 1),
                vigente_ate=date(2026, 7, 31),
                janela_inicio=date(2026, 6, 1),
                janela_fim=date(2026, 7, 31),
                tuplas_do_adapter=tuplas,
            )

    def test_22_clientes_diferentes_sobrepostos_erro(self):
        """Clientes diferentes sobrepostos → SobreposicaoClientePorPostoError."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), date(2026, 6, 15)),
            _fazer_tupla("a1", "p1", "cl-B", date(2026, 6, 10), date(2026, 6, 30)),
        )
        with pytest.raises(SobreposicaoClientePorPostoError):
            materializar_segmentos_alocacao_com_cliente(
                alocacao_id="a1",
                posto_id="p1",
                vigente_de=date(2026, 6, 1),
                vigente_ate=date(2026, 7, 31),
                janela_inicio=date(2026, 6, 1),
                janela_fim=date(2026, 7, 31),
                tuplas_do_adapter=tuplas,
            )

    def test_23_janela_totalmente_dentro_cliente(self):
        """Janela totalmente dentro vigência de um cliente."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), date(2026, 7, 31)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 6, 10),
            janela_fim=date(2026, 7, 20),
            tuplas_do_adapter=tuplas,
        )
        assert len(resultado) == 1
        assert resultado[0].cliente_id == "cl-A"
        assert resultado[0].segmento_de == date(2026, 6, 10)
        assert resultado[0].segmento_ate == date(2026, 7, 20)

    def test_janela_sem_intersecao_retorna_vazio(self):
        """Janela totalmente fora da alocação → tuple() vazio."""
        tuplas = (
            _fazer_tupla("a1", "p1", "cl-A", date(2026, 6, 1), date(2026, 7, 31)),
        )
        resultado = materializar_segmentos_alocacao_com_cliente(
            alocacao_id="a1",
            posto_id="p1",
            vigente_de=date(2026, 6, 1),
            vigente_ate=date(2026, 7, 31),
            janela_inicio=date(2026, 8, 1),
            janela_fim=date(2026, 8, 31),
            tuplas_do_adapter=tuplas,
        )
        assert resultado == tuple()

    def test_janela_invalida_erro(self):
        """janela_fim < janela_inicio → ValueError explícito."""
        with pytest.raises(ValueError, match="janela_fim"):
            materializar_segmentos_alocacao_com_cliente(
                alocacao_id="a1",
                posto_id="p1",
                vigente_de=date(2026, 6, 1),
                vigente_ate=date(2026, 7, 31),
                janela_inicio=date(2026, 7, 31),
                janela_fim=date(2026, 6, 1),  # inválida
                tuplas_do_adapter=tuple(),
            )
