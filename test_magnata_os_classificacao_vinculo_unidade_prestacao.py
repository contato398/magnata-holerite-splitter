"""Testes de `vinculo_unidade_prestacao.py` (missão "EVIDÊNCIA
RELACIONAL DOCUMENTO↔DOCUMENTO + VÍNCULO/UNIDADE_POSTO REAIS"; corrigido
pelo "ADENDO PRÉ-MERGE AO PR #106 — CORREÇÃO DA SEMÂNTICA DE VÍNCULO
HISTÓRICO"). Casos A-H mapeados 1:1 à seção 8/9 do adendo."""
import pytest

from magnata_os.classificacao.contratos import DimensaoResolucao, EstadoResolucaoDimensao, ReferenciaCanonica, ResolucaoDimensao
from magnata_os.classificacao.vinculo_unidade_prestacao import (
    MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA,
    resolver_unidade_posto_validado,
    resolver_vinculo_validado,
)

_COLABORADOR = ReferenciaCanonica('COLABORADOR', 'colab-1')
_COMPETENCIA_CORRENTE = ReferenciaCanonica('COMPETENCIA', '2026-07')
_COMPETENCIA_HISTORICA = ReferenciaCanonica('COMPETENCIA', '2025-01')


class _FonteVinculoTemporalFake:
    """Fonte fake que simula uma fonte REAL: só conhece o vínculo
    corrente (`_COMPETENCIA_CORRENTE`) e, opcionalmente, uma competência
    histórica com vigência EXPLICITAMENTE comprovada -- nunca promove
    corrente a histórica por conta própria."""

    def __init__(self, cliente_id='cli-x', competencia_historica_comprovada=None, sem_evidencia=False):
        self._cliente_id = cliente_id
        self._competencia_historica_comprovada = competencia_historica_comprovada
        self._sem_evidencia = sem_evidencia

    def resolver_vinculo(self, colaborador, competencia):
        if self._sem_evidencia:
            return ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA)
        if competencia == _COMPETENCIA_CORRENTE:
            return ResolucaoDimensao(
                dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.RESOLVIDA,
                valores_confirmados=(ReferenciaCanonica('VINCULO', f'local-real-{self._cliente_id}'),),
            )
        if self._competencia_historica_comprovada is not None and competencia == self._competencia_historica_comprovada:
            return ResolucaoDimensao(
                dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.RESOLVIDA,
                valores_confirmados=(ReferenciaCanonica('VINCULO', f'local-real-historico-{self._cliente_id}'),),
            )
        # Só conhece o corrente -- para qualquer outra competência, sem
        # vigência comprovada: nunca RESOLVIDA (§3 do adendo).
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
            motivos=(MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA,),
        )


class _FonteVinculoDoisVinculosFake:
    def resolver_vinculo(self, colaborador, competencia):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(
                ReferenciaCanonica('VINCULO', 'local-real-a'), ReferenciaCanonica('VINCULO', 'local-real-b'),
            ),
        )


class _FonteUnidadePostoTemporalFake:
    def __init__(self, postos=(ReferenciaCanonica('UNIDADE_POSTO', 'posto-1'),), so_corrente=False):
        self._postos = postos
        self._so_corrente = so_corrente

    def resolver_unidade_posto(self, colaborador, competencia):
        if self._so_corrente and competencia != _COMPETENCIA_CORRENTE:
            return ResolucaoDimensao(
                dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
                motivos=(MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA,),
            )
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=self._postos,
        )


# --- Caso A: sem vínculo real fornecido -- nunca cria identidade artificial ---

def test_caso_a_sem_evidencia_real_nunca_resolve_nem_fabrica_identidade():
    fonte = _FonteVinculoTemporalFake(sem_evidencia=True)
    resultado = resolver_vinculo_validado(fonte, _COLABORADOR, _COMPETENCIA_CORRENTE)
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert resultado.valores_confirmados == ()


def test_caso_a_modulo_nao_expoe_nenhuma_funcao_de_fabricacao_de_vinculo():
    """Nenhuma função pública deste módulo deriva VINCULO a partir de
    COLABORADOR+CLIENTE -- só via Fonte real (Protocol)."""
    import magnata_os.classificacao.vinculo_unidade_prestacao as modulo
    nomes_publicos = [nome for nome in dir(modulo) if not nome.startswith('_')]
    assert 'resolucao_vinculo_a_partir_de_cliente' not in nomes_publicos


# --- Caso B: competência corrente + vínculo comprovado por fonte -> RESOLVIDA ---

def test_caso_b_competencia_corrente_vinculo_comprovado_resolve():
    fonte = _FonteVinculoTemporalFake()
    resultado = resolver_vinculo_validado(fonte, _COLABORADOR, _COMPETENCIA_CORRENTE)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert len(resultado.valores_confirmados) == 1
    assert resultado.valores_confirmados[0].tipo_entidade == 'VINCULO'


# --- Caso C: competência histórica + só vínculo corrente -> NÃO RESOLVIDA ---

def test_caso_c_competencia_historica_sem_prova_nunca_resolve():
    fonte = _FonteVinculoTemporalFake()
    resultado = resolver_vinculo_validado(fonte, _COLABORADOR, _COMPETENCIA_HISTORICA)
    assert resultado.estado != EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA in resultado.motivos


# --- Caso D: vínculo histórico comprovado por fonte temporal -> RESOLVIDA ---

def test_caso_d_competencia_historica_com_prova_real_resolve():
    fonte = _FonteVinculoTemporalFake(competencia_historica_comprovada=_COMPETENCIA_HISTORICA)
    resultado = resolver_vinculo_validado(fonte, _COLABORADOR, _COMPETENCIA_HISTORICA)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA


# --- Caso E: 2 vínculos reais legítimos -- cardinalidade preservada ---

def test_caso_e_dois_vinculos_reais_cardinalidade_preservada():
    fonte = _FonteVinculoDoisVinculosFake()
    resultado = resolver_vinculo_validado(fonte, _COLABORADOR, _COMPETENCIA_CORRENTE)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert len(resultado.valores_confirmados) == 2


# --- Caso F: posto corrente em competência corrente -> RESOLVIDA ---

def test_caso_f_posto_corrente_competencia_corrente_resolve():
    fonte = _FonteUnidadePostoTemporalFake(so_corrente=True)
    resultado = resolver_unidade_posto_validado(fonte, _COLABORADOR, _COMPETENCIA_CORRENTE)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA


# --- Caso G: posto corrente usado p/ competência histórica sem vigência -> NÃO RESOLVIDA ---

def test_caso_g_posto_corrente_competencia_historica_sem_vigencia_nao_resolve():
    fonte = _FonteUnidadePostoTemporalFake(so_corrente=True)
    resultado = resolver_unidade_posto_validado(fonte, _COLABORADOR, _COMPETENCIA_HISTORICA)
    assert resultado.estado != EstadoResolucaoDimensao.RESOLVIDA


# --- Caso H: dois postos válidos na competência -- dois valores preservados ---

def test_caso_h_dois_postos_validos_preservados():
    dois_postos = (ReferenciaCanonica('UNIDADE_POSTO', 'posto-a'), ReferenciaCanonica('UNIDADE_POSTO', 'posto-b'))
    fonte = _FonteUnidadePostoTemporalFake(postos=dois_postos)
    resultado = resolver_unidade_posto_validado(fonte, _COLABORADOR, _COMPETENCIA_CORRENTE)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert len(resultado.valores_confirmados) == 2


# --- Invariantes estruturais (Protocol validado) ---

class _FonteVinculoInvalida:
    def resolver_vinculo(self, colaborador, competencia):
        return ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA)


def test_resolver_vinculo_validado_rejeita_colaborador_com_tipo_errado():
    with pytest.raises(ValueError):
        resolver_vinculo_validado(_FonteVinculoTemporalFake(), ReferenciaCanonica('CLIENTE', 'x'), _COMPETENCIA_CORRENTE)


def test_resolver_vinculo_validado_rejeita_dimensao_errada_devolvida_pela_fonte():
    with pytest.raises(ValueError):
        resolver_vinculo_validado(_FonteVinculoInvalida(), _COLABORADOR, _COMPETENCIA_CORRENTE)


def test_resolver_unidade_posto_validado_rejeita_competencia_com_tipo_errado():
    with pytest.raises(ValueError):
        resolver_unidade_posto_validado(_FonteUnidadePostoTemporalFake(), _COLABORADOR, ReferenciaCanonica('CLIENTE', 'x'))
