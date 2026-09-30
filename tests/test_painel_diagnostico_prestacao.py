"""Testes do Painel de Diagnóstico da Prestação de Contas (V1, somente
leitura). Dados sintéticos apenas -- nenhum CPF, nome real ou nome de
arquivo (LGPD, `/CLAUDE.md` §6)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import (
    SituacaoNecessidade,
)
from magnata_os.classificacao.painel_diagnostico_prestacao import (
    _LEGENDA_SITUACAO_NECESSIDADE,
    _MARCADOR_SITUACAO,
    renderizar_diagnostico_prestacao_markdown,
)


RAIZ_REPOSITORIO = Path(__file__).resolve().parent.parent


def _necessidade(situacao: str, **overrides) -> dict:
    base = {
        'cliente': 'cliente-sintetico-001',
        'competencia': '2026-08',
        'tipo_documental': 'HOLERITE',
        'colaborador': 'colaborador-sintetico-001',
        'situacao': situacao,
        'documentos_avaliados': [],
        'documentos_elegiveis': [],
        'localizacao': None,
    }
    base.update(overrides)
    return base


def _cliente(estado_pacote: str, ordem_pronta: bool, necessidades: list) -> dict:
    return {
        'cliente': 'cliente-sintetico-001',
        'competencia': '2026-08',
        'estado_pacote': estado_pacote,
        'ordem_pronta': ordem_pronta,
        'necessidades': necessidades,
    }


def _diagnostico(clientes: list) -> dict:
    return {'competencia_base': '2026-08', 'clientes': clientes}


# ---- cobertura de schema: a legenda nunca fica desatualizada em
# relação ao Enum real (evita drift entre `SituacaoNecessidade` e o
# texto estático do painel).


def test_legenda_cobre_todas_as_situacoes_do_enum_real():
    valores_enum = {s.value for s in SituacaoNecessidade}
    assert set(_LEGENDA_SITUACAO_NECESSIDADE.keys()) == valores_enum
    assert set(_MARCADOR_SITUACAO.keys()) == valores_enum


# ---- estados principais renderizados corretamente


def test_diagnostico_vazio_nao_quebra():
    saida = renderizar_diagnostico_prestacao_markdown(_diagnostico([]))
    assert 'Nenhum cliente' in saida
    assert '2026-08' in saida


def test_cliente_pronto_sem_necessidades_aparece_pronto():
    necessidade = _necessidade(
        SituacaoNecessidade.PRONTO.value,
        documentos_avaliados=['doc-001'],
        documentos_elegiveis=['doc-001'],
    )
    diagnostico = _diagnostico([_cliente('PRONTO', True, [necessidade])])
    saida = renderizar_diagnostico_prestacao_markdown(diagnostico)

    assert 'Ordem pronta para sair: **SIM**' in saida
    assert 'PRONTO' in saida
    assert '✅' in saida
    # Estado PRONTO não entra na seção de rastro (não é uma das
    # situações que exigem investigação).
    assert 'Rastro de localização' not in saida


def test_conflito_aparece_bloqueado_mesmo_com_documentos_elegiveis():
    necessidade = _necessidade(
        SituacaoNecessidade.CONFLITO.value,
        documentos_avaliados=['doc-001', 'doc-002'],
        documentos_elegiveis=['doc-001', 'doc-002'],
    )
    # `ordem_pronta` reflete a regra real (`DiagnosticoCliente.ordem_pronta`):
    # nunca True havendo CONFLITO -- aqui simulado como o produtor real faria.
    diagnostico = _diagnostico([_cliente('PRONTO', False, [necessidade])])
    saida = renderizar_diagnostico_prestacao_markdown(diagnostico)

    assert 'Ordem pronta para sair: **NÃO**' in saida
    assert 'CONFLITO' in saida
    assert '⚠️' in saida


def test_ausente_com_rastro_de_localizacao_aparece_na_secao_de_rastro():
    localizacao = {
        'decisao': 'NAO_LOCALIZADO',
        'motivo': 'nenhuma fonte teve candidato',
        'fonte_selecionada': None,
        'documento_selecionado': None,
        'candidatos': [],
        'consultas': [
            {
                'fonte': 'inventario-interno',
                'status': 'CONSULTADA',
                'documento_ids': [],
                'erro_tipo': None,
                'detalhes': {},
            },
        ],
    }
    necessidade = _necessidade(SituacaoNecessidade.AUSENTE.value, localizacao=localizacao)
    diagnostico = _diagnostico([_cliente('INCOMPLETO', False, [necessidade])])
    saida = renderizar_diagnostico_prestacao_markdown(diagnostico)

    assert 'Rastro de localização' in saida
    assert 'NAO_LOCALIZADO' in saida
    assert 'fonte `inventario-interno`: CONSULTADA' in saida


def test_em_revisao_e_erro_de_leitura_e_fonte_indisponivel_e_sem_fonte():
    necessidades = [
        _necessidade(SituacaoNecessidade.EM_REVISAO.value, tipo_documental='FOLHA_PONTO'),
        _necessidade(SituacaoNecessidade.ERRO_DE_LEITURA.value, tipo_documental='RECIBO'),
        _necessidade(SituacaoNecessidade.FONTE_INDISPONIVEL.value, tipo_documental='EXTRATO'),
        _necessidade(SituacaoNecessidade.SEM_FONTE.value, tipo_documental='OUTROS'),
        _necessidade(SituacaoNecessidade.ENCONTRADO_NAO_ELEGIVEL.value, tipo_documental='HOLERITE'),
    ]
    diagnostico = _diagnostico([_cliente('BLOQUEADO', False, necessidades)])
    saida = renderizar_diagnostico_prestacao_markdown(diagnostico)

    for situacao in (
        'EM_REVISAO', 'ERRO_DE_LEITURA', 'FONTE_INDISPONIVEL', 'SEM_FONTE',
        'ENCONTRADO_NAO_ELEGIVEL',
    ):
        assert situacao in saida


def test_necessidade_a_nivel_cliente_sem_colaborador_nao_quebra():
    necessidade = _necessidade(SituacaoNecessidade.PRONTO.value, colaborador=None)
    diagnostico = _diagnostico([_cliente('PRONTO', True, [necessidade])])
    saida = renderizar_diagnostico_prestacao_markdown(diagnostico)
    assert '(nível cliente)' in saida


def test_resumo_geral_conta_prontos_e_bloqueados_corretamente():
    cliente_pronto = _cliente(
        'PRONTO', True, [_necessidade(SituacaoNecessidade.PRONTO.value)],
    )
    cliente_bloqueado = _cliente(
        'BLOQUEADO', False, [_necessidade(SituacaoNecessidade.AUSENTE.value)],
    )
    diagnostico = _diagnostico([cliente_pronto, cliente_bloqueado])
    saida = renderizar_diagnostico_prestacao_markdown(diagnostico)
    assert '2 cliente(s)' in saida
    assert '1 com Ordem pronta' in saida
    assert '1 bloqueado' in saida


def test_nenhum_cpf_ou_nome_de_arquivo_no_relatorio_com_dado_sintetico():
    """Confirma que o painel só reflete o que veio no dict -- não
    inventa nem injeta nenhum campo além do já sintético/opaco."""
    necessidade = _necessidade(SituacaoNecessidade.PRONTO.value)
    diagnostico = _diagnostico([_cliente('PRONTO', True, [necessidade])])
    saida = renderizar_diagnostico_prestacao_markdown(diagnostico)
    for termo_proibido in ('.pdf', '.jpg', 'CPF', '@'):
        assert termo_proibido not in saida


def test_renderizar_diagnostico_prestacao_objeto_delega_para_como_dict():
    from magnata_os.classificacao.painel_diagnostico_prestacao import (
        renderizar_diagnostico_prestacao_objeto,
    )

    class _FakeDiagnostico:
        def como_dict(self):
            return _diagnostico([_cliente('PRONTO', True, [
                _necessidade(SituacaoNecessidade.PRONTO.value),
            ])])

    saida = renderizar_diagnostico_prestacao_objeto(_FakeDiagnostico())
    assert 'Ordem pronta para sair: **SIM**' in saida


# ---- CLI


def test_cli_le_arquivo_e_imprime_markdown(tmp_path):
    diagnostico = _diagnostico([_cliente('PRONTO', True, [
        _necessidade(SituacaoNecessidade.PRONTO.value),
    ])])
    arquivo = tmp_path / 'diagnostico.json'
    arquivo.write_text(json.dumps(diagnostico), encoding='utf-8')

    resultado = subprocess.run(
        [sys.executable, 'scripts/painel_diagnostico_prestacao_cli.py', str(arquivo)],
        cwd=RAIZ_REPOSITORIO,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert 'Painel de Diagnóstico' in resultado.stdout
    assert 'Ordem pronta para sair: **SIM**' in resultado.stdout


def test_cli_le_stdin_quando_sem_argumento():
    diagnostico = _diagnostico([_cliente('BLOQUEADO', False, [
        _necessidade(SituacaoNecessidade.AUSENTE.value),
    ])])
    resultado = subprocess.run(
        [sys.executable, 'scripts/painel_diagnostico_prestacao_cli.py'],
        cwd=RAIZ_REPOSITORIO,
        input=json.dumps(diagnostico),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert 'AUSENTE' in resultado.stdout
