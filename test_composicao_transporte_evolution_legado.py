"""Testes da composição canônica de `TransporteEvolutionLegado`
(Incremento 2, missão "IMPLEMENTAÇÃO LOCAL CONTROLADA — EXTRAÇÃO
EVOLUTION + CANÁRIO NOMINAL V1").

Prova: import isolado sem Flask/app.py; a composição usa as callables
reais do cliente extraído; o transporte real só pode ser usado através
de `compor_porta_execucao` com as 3 barreiras abertas -- nenhum atalho
instancia `ExecutorEvolutionLegado` diretamente."""
from __future__ import annotations

import sys

import pytest


def test_import_isolado_nunca_carrega_flask_nem_app():
    modulos_antes = set(sys.modules)
    from magnata_os.orquestrador.composicao_transporte_evolution_legado import (
        compor_transporte_evolution_real,
    )
    modulos_depois = set(sys.modules)
    novos = modulos_depois - modulos_antes
    assert 'flask' not in novos
    assert 'app' not in novos
    assert compor_transporte_evolution_real is not None


def test_compor_transporte_usa_as_callables_reais_do_cliente_extraido():
    from magnata_os.orquestrador.adapters import evolution_cliente_legado
    from magnata_os.orquestrador.composicao_transporte_evolution_legado import (
        compor_transporte_evolution_real,
    )
    transporte = compor_transporte_evolution_real()
    assert transporte.enviar_texto_legado is evolution_cliente_legado._evolution_enviar_texto
    assert transporte.enviar_video_legado is evolution_cliente_legado._evolution_enviar_video
    assert transporte.enviar_documento_legado is evolution_cliente_legado._evolution_enviar_documento


def test_compor_porta_execucao_com_barreira_fechada_nunca_usa_transporte_real(monkeypatch):
    """Mesmo passando transporte_evolution real, autorizar_transporte_real=False
    (o padrão) nunca constrói ExecutorEvolutionLegado."""
    from magnata_os.orquestrador.ciclo_producao_v1 import compor_porta_execucao
    from magnata_os.orquestrador.composicao_transporte_evolution_legado import (
        compor_transporte_evolution_real,
    )
    from magnata_os.orquestrador.executor_persistente_fake import ExecutorAcaoDryRun

    porta = compor_porta_execucao(
        autorizar_transporte_real=False, transporte_evolution=compor_transporte_evolution_real(),
    )
    assert isinstance(porta, ExecutorAcaoDryRun)


def test_compor_porta_execucao_com_as_3_barreiras_abertas_usa_o_transporte_composto(monkeypatch):
    from magnata_os.orquestrador.adapters.executor_evolution_legado import ExecutorEvolutionLegado
    from magnata_os.orquestrador.ciclo_producao_v1 import compor_porta_execucao
    from magnata_os.orquestrador.composicao_transporte_evolution_legado import (
        compor_transporte_evolution_real,
    )

    monkeypatch.setenv('ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO', '1')
    monkeypatch.delenv('ORQUESTRADOR_DRY_RUN', raising=False)
    transporte = compor_transporte_evolution_real()
    porta = compor_porta_execucao(autorizar_transporte_real=True, transporte_evolution=transporte)
    assert isinstance(porta, ExecutorEvolutionLegado)
    assert porta.transporte is transporte


def test_nenhum_atalho_instancia_executor_evolution_legado_fora_de_compor_porta_execucao():
    """Auditoria estática mínima: confirma que este módulo de composição
    nunca IMPORTA `ExecutorEvolutionLegado` (o nome pode aparecer só na
    docstring, explicando o porquê) -- só compõe o transporte, nunca
    decide sozinho se ele deve ser usado."""
    import ast
    import inspect

    import magnata_os.orquestrador.composicao_transporte_evolution_legado as modulo
    arvore = ast.parse(inspect.getsource(modulo))
    nomes_importados = {
        alias.asname or alias.name
        for node in ast.walk(arvore)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert 'ExecutorEvolutionLegado' not in nomes_importados
