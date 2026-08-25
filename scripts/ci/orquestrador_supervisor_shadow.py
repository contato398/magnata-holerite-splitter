#!/usr/bin/env python3
"""Executa um ciclo observacional do supervisor, sem side effects."""
from __future__ import annotations

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


def main() -> int:
    repo = RepositorioExecucoesSQLite(
        RAIZ / '.orquestrador_ci' / 'execucoes.db'
    )
    try:
        snapshot = SupervisorOrquestrador(
            repo,
            modo=ModoSupervisor.SHADOW,
        ).executar_ciclo()
        print(json.dumps(snapshot.resumo_json(), ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        repo.fechar()


if __name__ == '__main__':
    sys.exit(main())
