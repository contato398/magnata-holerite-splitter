#!/usr/bin/env python3
"""
Ponto de entrada de CI do nucleo do Orquestrador -- o gatilho automatico
sem sessao (docs/magnata-os/central-command/MATRIZ_AUTONOMIA.md paragrafo 4,
fechado nesta etapa).

Roda o motor real (magnata_os/orquestrador/) contra o unico evento que
o Orquestrador hoje sabe processar sozinho (GIT_MAIN_AVANCOU, Nivel
EXECUTE_SAFE): detecta se `main` avancou desde o ultimo `ESTADO.json`
commitado, executa a Acao (sensor completo, com suite), e imprime o
que mudou -- para o workflow decidir se abre PR.

NUNCA commita nem faz push sozinho -- isso e responsabilidade do
workflow do GitHub Actions que chama este script, que sempre abre PR,
nunca escreve direto em `main` (CLAUDE.md paragrafo 9).

Codigo de saida:
  0  nada mudou (nenhum evento) OU evento processado com SUCCEEDED
  1  evento processado mas foi para WAITING_GATE/FAILED -- workflow nao
     deve abrir PR, so registrar e alertar
  2  erro inesperado antes de chegar a processar o evento
"""
from __future__ import annotations

import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from magnata_os.orquestrador.eventos import EstadoExecucao, TipoEvento  # noqa: E402
from magnata_os.orquestrador.motor import MotorOrquestrador  # noqa: E402
from magnata_os.orquestrador.observabilidade import Observador  # noqa: E402
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesSQLite  # noqa: E402
from magnata_os.orquestrador.acoes import atualizar_auto_fact  # noqa: E402

AUDITORIA = RAIZ / 'docs' / 'magnata-os' / 'central-command' / 'AUDITORIA_ORQUESTRADOR.jsonl'


def _registrar_auditoria(registro, evento) -> None:
    """AUTO_FACT append-only (TAXONOMIA_MEMORIA.md) -- uma linha por
    execucao, nunca reescreve linha anterior. Isto e o audit log
    PERSISTENTE entre execucoes de CI (a tabela SQLite em si e efemera
    por run; este arquivo, comitado via PR, acumula historico real)."""
    linha = {
        'event_id': registro.event_id,
        'event_type': registro.event_type,
        'estado': registro.estado.value,
        'nivel_autonomia': registro.nivel_autonomia,
        'resultado': registro.resultado,
        'evidencia': registro.evidencia,
        'attempt': registro.attempt,
        'fonte': evento.source,
        'correlation_id': evento.correlation_id,
        'proveniencia': evento.proveniencia,
        'criado_em': registro.criado_em.isoformat(),
        'atualizado_em': registro.atualizado_em.isoformat(),
    }
    AUDITORIA.parent.mkdir(parents=True, exist_ok=True)
    with AUDITORIA.open('a', encoding='utf-8') as f:
        f.write(json.dumps(linha, ensure_ascii=False) + '\n')


def main() -> int:
    evento = atualizar_auto_fact.detectar_evento()
    if evento is None:
        print('SEM_MUDANCA: ESTADO.json ja reflete o main_sha atual -- nada a fazer.')
        return 0

    print(f'EVENTO_DETECTADO: {evento.event_type.value} entity_id={evento.entity_id}')

    repo = RepositorioExecucoesSQLite(RAIZ / '.orquestrador_ci' / 'execucoes.db')
    obs = Observador()
    motor = MotorOrquestrador(
        repo,
        acoes={TipoEvento.GIT_MAIN_AVANCOU.value: atualizar_auto_fact.executar},
        observador=obs,
    )

    registro = motor.processar(evento)
    _registrar_auditoria(registro, evento)

    print(f'RESULTADO: estado={registro.estado.value} evidencia={registro.evidencia}')
    print(f'CONTADORES: {obs.resumo()}')

    if registro.estado == EstadoExecucao.SUCCEEDED:
        return 0
    print(
        f'ATENCAO: evento nao chegou a SUCCEEDED (estado={registro.estado.value}) -- '
        f'workflow nao deve abrir PR de atualizacao automatica para isto.'
    )
    return 1


if __name__ == '__main__':
    sys.exit(main())
