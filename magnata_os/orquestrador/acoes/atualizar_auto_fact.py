"""
Unica Acao Nivel 4 (EXECUTE_SAFE) implementada nesta etapa -- ver
docs/magnata-os/central-command/MATRIZ_AUTONOMIA.md.

Coordena o que ja existe (scripts/ci/central_command_sensor.py) -- nao
reimplementa deteccao de HEAD/suite/branches. So adiciona: virar Evento
(deteccao), decidir por politica (motor.py) e um caminho de escrita
auditado (este arquivo).

Escreve SO em ESTADO.json (AUTO_FACT, TAXONOMIA_MEMORIA.md). Nunca
DECISIONS.md, app.py nem producao -- reforcado em motor.py via
CAMINHOS_PROIBIDOS, nao so aqui (defesa em profundidade: mesmo que este
arquivo tivesse um bug, o motor rejeitaria a escrita).
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from typing import Optional

from ..eventos import Evento, Sensibilidade, TipoEvento, agora, novo_event_id
from ..motor import ResultadoAcao

RAIZ = pathlib.Path(__file__).resolve().parents[3]
_SENSOR_PATH = RAIZ / 'scripts' / 'ci' / 'central_command_sensor.py'


def _carregar_sensor():
    """Mesmo padrao de carregamento usado em
    scripts/ci/test_central_command_sensor.py -- o sensor e um script,
    nao um pacote, entao precisa de importlib para virar modulo
    importavel a partir daqui."""
    spec = importlib.util.spec_from_file_location('central_command_sensor', _SENSOR_PATH)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules.setdefault('central_command_sensor', modulo)
    spec.loader.exec_module(modulo)
    return modulo


def _ler_snapshot_anterior(sensor) -> dict:
    if not sensor.SNAPSHOT.exists():
        return {}
    return json.loads(sensor.SNAPSHOT.read_text(encoding='utf-8'))


def detectar_evento() -> Optional[Evento]:
    """FASE DE DETECCAO (Nivel 1) -- so leitura, nunca escreve nada.
    Se main avancou desde o ultimo ESTADO.json commitado, produz um
    Evento; senao, None (nada a fazer)."""
    sensor = _carregar_sensor()
    atual = sensor.coletar(com_testes=False)
    anterior = _ler_snapshot_anterior(sensor)

    sha_atual = atual.get('main_sha')
    sha_anterior = anterior.get('main_sha')
    if not sha_atual or sha_atual == sha_anterior:
        return None

    quando = agora()
    return Evento(
        event_id=novo_event_id(TipoEvento.GIT_MAIN_AVANCOU, sha_atual, quando),
        event_type=TipoEvento.GIT_MAIN_AVANCOU,
        source='git',
        occurred_at=quando,
        received_at=quando,
        correlation_id=sha_atual,
        entity_type='commit',
        entity_id=sha_atual,
        payload_referencia=f'main_sha={sha_atual}',
        sensibilidade=Sensibilidade.PUBLICO,
        proveniencia='scripts/ci/central_command_sensor.py:coletar',
    )


def executar(evento: Evento) -> ResultadoAcao:
    """A Acao registrada no motor para TipoEvento.GIT_MAIN_AVANCOU.
    Roda o sensor de verdade COM suite (e o unico jeito honesto de saber
    se regrediu -- nunca assume) e regrava so o ESTADO.json, usando
    preservar_baseline (mesma protecao do PR #41 -- nunca apaga a
    baseline em silencio)."""
    sensor = _carregar_sensor()
    atual = sensor.coletar(com_testes=True)
    anterior = _ler_snapshot_anterior(sensor)
    a_gravar, aviso = sensor.preservar_baseline(atual, anterior)

    sensor.SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    sensor.SNAPSHOT.write_text(
        json.dumps(a_gravar, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )

    testes = a_gravar.get('testes') or {}
    evidencia = f"main={a_gravar.get('main_sha')} testes={testes.get('passando')}/{testes.get('falhando')}"
    if aviso:
        evidencia += f' AVISO: {aviso}'

    return ResultadoAcao(
        sucesso=True,
        evidencia=evidencia,
        caminhos_escritos=(str(sensor.SNAPSHOT.relative_to(RAIZ)),),
    )
