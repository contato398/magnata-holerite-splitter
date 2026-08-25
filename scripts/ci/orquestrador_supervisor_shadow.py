#!/usr/bin/env python3
"""Executa um ciclo observacional do supervisor, sem side effects."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from magnata_os.orquestrador.repositorio_execucoes import (  # noqa: E402
    RepositorioExecucoesSQLite,
)
from magnata_os.orquestrador.supervisor import (  # noqa: E402
    ModoSupervisor,
    SupervisorOrquestrador,
)


def _argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--db',
        type=pathlib.Path,
        default=RAIZ / '.orquestrador_ci' / 'execucoes.db',
        help='SQLite observado pelo supervisor.',
    )
    parser.add_argument(
        '--output',
        type=pathlib.Path,
        help='Arquivo JSON opcional para preservar a evidencia do ciclo.',
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    repo = RepositorioExecucoesSQLite(args.db)
    try:
        snapshot = SupervisorOrquestrador(
            repo,
            modo=ModoSupervisor.SHADOW,
        ).executar_ciclo()
        conteudo = json.dumps(
            snapshot.resumo_json(), ensure_ascii=False, indent=2, sort_keys=True
        )
        print(conteudo)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporario = args.output.with_suffix(args.output.suffix + '.tmp')
            temporario.write_text(conteudo + '\n', encoding='utf-8')
            temporario.replace(args.output)
        return 0
    finally:
        repo.fechar()


if __name__ == '__main__':
    sys.exit(main())
