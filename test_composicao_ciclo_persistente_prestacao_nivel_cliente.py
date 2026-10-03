"""Testes da integração do nível cliente (`IntencaoDistribuicaoCliente`,
`pacote_prestacao.py`) com o pipeline real de aquisição/readiness da
Prestação (`composicao_ciclo_persistente_prestacao.py`).

Extraído e adaptado do PR #192 (`fix/prestacao-upstream-real-v1`) sobre o
`main` atual, a pedido do coordenador -- ver `backlog-prs.md`. Escritos do
zero (não migrados de `test_correlacao_documento_prestacao.py` nem de
`test_aquisicao_prestacao_corredor_real_j1.py`, ambos entrelaçados com o
índice J3/migration 0007 já superado por outro caminho, migration 0011).

Estratégia: `particionar_nivel_cliente`/`resultados_aquisicao_prontos_
nivel_cliente`/`intencoes_distribuicao_cliente_*` são PUROS sobre trios já
calculados por `resultados_aquisicao_prontos_por_cliente` -- cujo
comportamento real (corredor, readiness, elegibilidade) já é provado à
exaustão por testes existentes (`test_aquisicao_prestacao_corredor_real_
j1.py`, `test_materializar_documento_pre_canario_operador_real_v1.py`).
Reaproveitamos esse mesmo padrão: `resultados_aquisicao_prontos_por_cliente`
é substituído por um fake determinístico só aqui -- não duplicamos o
corredor/readiness pesado (mesmo racional de `test_wiring_prestacao_
selecao_operador_shadow.py`, docstring do próprio arquivo)."""
from unittest.mock import patch

import pytest

from magnata_os.classificacao.ciclo_prestacao import NecessidadeDocumentoPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
import magnata_os.classificacao.composicao_ciclo_persistente_prestacao as modulo
from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    EVENTO_CLIENTE_FALHOU_INTENCAO_DISTRIBUICAO,
    EVENTO_DOCUMENTO_COM_COLABORADOR_FORA_INTENCAO_CLIENTE,
    ResultadoAquisicaoPorNecessidade,
    intencoes_distribuicao_cliente_de_trios,
    intencoes_distribuicao_cliente_prontas,
    particionar_nivel_cliente,
    resultados_aquisicao_prontos_nivel_cliente,
)
from types import SimpleNamespace

from magnata_os.classificacao.contratos import DimensaoResolucao, EstadoResolucaoDimensao
from magnata_os.classificacao.pacote_prestacao import PapelDestinatarioOrganizacional

_CLIENTE = ReferenciaCanonica('CLIENTE', 'rec_cliente_a')
_OUTRO_CLIENTE = ReferenciaCanonica('CLIENTE', 'rec_cliente_b')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')
_COLABORADOR = ReferenciaCanonica('COLABORADOR', 'colab-x')


def _necessidade(tipo, *, cliente=_CLIENTE, competencia=_COMPETENCIA, colaborador=None):
    return NecessidadeDocumentoPrestacao(
        cliente=cliente, competencia=competencia, tipo_documental=tipo,
        motivo_exigencia='teste-nivel-cliente', colaborador=colaborador,
    )


def _resultado(documento_id, tipo, *, cliente=_CLIENTE, colaborador=None, resultados_corredor=()):
    return ResultadoAquisicaoPorNecessidade(
        necessidade=_necessidade(tipo, cliente=cliente, colaborador=colaborador),
        documento_id=documento_id, hash_sha256=documento_id[-1] * 64,
        resultados_corredor=resultados_corredor,
    )


def _execucao_com_dimensao_colaborador(estado=EstadoResolucaoDimensao.RESOLVIDA):
    """Execução de corredor sintética (duck-typed -- `_documento_
    identifica_colaborador` só lê `.resultado_corredor.resolucao_
    semantica.resolucoes[].dimensao/.estado`, nunca faz isinstance) cuja
    resolução semântica identifica a dimensão COLABORADOR -- usado para
    provar que `_separar_nivel_cliente` rejeita documento com
    granularidade de pessoa mesmo quando a necessidade que o buscou é de
    nível cliente."""
    item_resolucao = SimpleNamespace(dimensao=DimensaoResolucao.COLABORADOR, estado=estado)
    resolucao = SimpleNamespace(resolucoes=(item_resolucao,))
    corredor = SimpleNamespace(resolucao_semantica=resolucao)
    return (SimpleNamespace(resultado_corredor=corredor),)


# ---------------------------------------------------------------------
# particionar_nivel_cliente / resultados_aquisicao_prontos_nivel_cliente
# ---------------------------------------------------------------------

def test_particionar_nivel_cliente_separa_resultados_sem_colaborador():
    trios = (
        (_CLIENTE, _COMPETENCIA, (
            _resultado('doc-a', 'EXTRATO'),
            _resultado('doc-b', 'HOLERITE', colaborador=_COLABORADOR),
        )),
    )
    (saida,) = particionar_nivel_cliente(trios)
    cliente, competencia, resultados = saida
    assert cliente == _CLIENTE and competencia == _COMPETENCIA
    assert [r.documento_id for r in resultados] == ['doc-a']


def test_particionar_nivel_cliente_omite_cliente_sem_nenhum_documento_de_nivel_cliente():
    trios = ((_CLIENTE, _COMPETENCIA, (_resultado('doc-b', 'HOLERITE', colaborador=_COLABORADOR),)),)
    assert particionar_nivel_cliente(trios) == ()


def test_particionar_nivel_cliente_rejeita_documento_que_identifica_colaborador(caplog):
    trios = (
        (_CLIENTE, _COMPETENCIA, (
            _resultado('doc-a', 'EXTRATO', resultados_corredor=_execucao_com_dimensao_colaborador()),
        )),
    )
    with caplog.at_level('WARNING'):
        assert particionar_nivel_cliente(trios) == ()
    assert any(EVENTO_DOCUMENTO_COM_COLABORADOR_FORA_INTENCAO_CLIENTE in r.message for r in caplog.records)


def test_particionar_nivel_cliente_ordem_deterministica_independente_da_fonte():
    resultados = (_resultado('doc-b', 'DOCUMENTO_B'), _resultado('doc-a', 'DOCUMENTO_A'))
    trios = ((_CLIENTE, _COMPETENCIA, resultados),)
    (saida,) = particionar_nivel_cliente(trios)
    _, _, ordenados = saida
    assert [r.documento_id for r in ordenados] == ['doc-a', 'doc-b']


def test_resultados_aquisicao_prontos_nivel_cliente_reusa_pipeline_real_de_aquisicao():
    """Prova que a função chama `resultados_aquisicao_prontos_por_cliente`
    (o MESMO gate de readiness/elegibilidade real já usado pelas Ordens de
    colaborador) -- nunca um segundo motor de descoberta/aquisição."""
    trios_fake = ((_CLIENTE, _COMPETENCIA, (_resultado('doc-a', 'EXTRATO'),)),)
    with patch.object(modulo, 'resultados_aquisicao_prontos_por_cliente', return_value=trios_fake) as mock_pipeline:
        contexto_sentinela = object()
        (saida,) = resultados_aquisicao_prontos_nivel_cliente(contexto_sentinela)
    mock_pipeline.assert_called_once_with(contexto_sentinela)
    assert saida[0] == _CLIENTE


# ---------------------------------------------------------------------
# intencoes_distribuicao_cliente_de_trios / _prontas
# ---------------------------------------------------------------------

def test_intencoes_distribuicao_cliente_de_trios_monta_1_intencao_por_cliente():
    trios = (
        (_CLIENTE, _COMPETENCIA, (_resultado('doc-a', 'EXTRATO'), _resultado('doc-b', 'FGTS'))),
        (_OUTRO_CLIENTE, _COMPETENCIA, (_resultado('doc-c', 'DCTFWEB', cliente=_OUTRO_CLIENTE),)),
    )
    intencoes = intencoes_distribuicao_cliente_de_trios(trios)
    assert len(intencoes) == 2
    por_cliente = {i.cliente: i for i in intencoes}
    assert por_cliente[_CLIENTE].documento_ids == ('doc-a', 'doc-b')
    assert por_cliente[_OUTRO_CLIENTE].documento_ids == ('doc-c',)
    assert all(i.papel_destinatario == PapelDestinatarioOrganizacional.CLIENTE_INSTITUCIONAL for i in intencoes)


def test_intencoes_distribuicao_cliente_de_trios_isola_falha_de_1_cliente(caplog):
    """`IntencaoDistribuicaoClienteError` de 1 cliente não derruba os
    demais -- isolamento por cliente, mesmo racional de `resultados_
    aquisicao_prontos_por_cliente` (readiness por cliente, nunca em
    lote)."""
    trios = (
        (_CLIENTE, _COMPETENCIA, ()),  # sem documentos -> erro de domínio
        (_OUTRO_CLIENTE, _COMPETENCIA, (_resultado('doc-c', 'DCTFWEB', cliente=_OUTRO_CLIENTE),)),
    )
    with caplog.at_level('ERROR'):
        intencoes = intencoes_distribuicao_cliente_de_trios(trios)
    assert len(intencoes) == 1
    assert intencoes[0].cliente == _OUTRO_CLIENTE
    assert any(EVENTO_CLIENTE_FALHOU_INTENCAO_DISTRIBUICAO in r.message for r in caplog.records)


def test_intencoes_distribuicao_cliente_prontas_encadeia_pipeline_e_particao_e_montagem():
    """Teste de integração do encadeamento completo: pipeline real
    (fake) -> partição de nível cliente -> montagem da intenção --
    provando que as 3 camadas novas se conectam sem recomputar nada."""
    trios_fake = (
        (_CLIENTE, _COMPETENCIA, (
            _resultado('doc-a', 'EXTRATO'),
            _resultado('doc-b', 'HOLERITE', colaborador=_COLABORADOR),  # nunca entra na intenção
        )),
    )
    with patch.object(modulo, 'resultados_aquisicao_prontos_por_cliente', return_value=trios_fake):
        (intencao,) = intencoes_distribuicao_cliente_prontas(contexto=object())
    assert intencao.cliente == _CLIENTE
    assert intencao.documento_ids == ('doc-a',)


def test_intencoes_distribuicao_cliente_prontas_sem_nenhum_cliente_de_nivel_cliente():
    trios_fake = ((_CLIENTE, _COMPETENCIA, (_resultado('doc-b', 'HOLERITE', colaborador=_COLABORADOR),)),)
    with patch.object(modulo, 'resultados_aquisicao_prontos_por_cliente', return_value=trios_fake):
        assert intencoes_distribuicao_cliente_prontas(contexto=object()) == ()
