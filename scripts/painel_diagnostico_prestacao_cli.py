"""CLI somente leitura do Painel de Diagnóstico da Prestação de Contas.

Lê um JSON no formato de `DiagnosticoPrestacao.como_dict()`
(`magnata_os/classificacao/composicao_ciclo_persistente_prestacao.py`)
e imprime o relatório Markdown produzido por
`magnata_os.classificacao.painel_diagnostico_prestacao.
renderizar_diagnostico_prestacao_markdown`.

Não chama `diagnosticar_prestacao` diretamente porque monta-lo exige o
mesmo `ContextoComposicaoPrestacao` completo do ciclo real (inventário,
fontes de localização, repositórios) -- fora do escopo desta V1 do
painel, que só formata o resultado já disponível (em log estruturado,
num teste ou numa execução futura que grave `.como_dict()` em disco).
Um caminho futuro que já produza esse JSON (rota Flask, worker,
notebook) pode ser apontado para este mesmo renderizador sem duplicar
lógica de formatação -- ver `docs/decisoes/painel-operacional-
prestacao-v1.md`.

Uso:
    python scripts/painel_diagnostico_prestacao_cli.py caminho/diagnostico.json
    cat diagnostico.json | python scripts/painel_diagnostico_prestacao_cli.py

Somente leitura: nenhuma escrita em arquivo, banco, Airtable ou rede.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


RAIZ_REPOSITORIO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if RAIZ_REPOSITORIO not in sys.path:
    sys.path.insert(0, RAIZ_REPOSITORIO)

from magnata_os.classificacao.painel_diagnostico_prestacao import (
    renderizar_diagnostico_prestacao_markdown,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "arquivo",
        nargs="?",
        default=None,
        help="Caminho do JSON de DiagnosticoPrestacao.como_dict(); "
        "sem argumento, lê de stdin.",
    )
    args = parser.parse_args(argv)

    if args.arquivo:
        with open(args.arquivo, "r", encoding="utf-8") as handle:
            diagnostico = json.load(handle)
    else:
        diagnostico = json.load(sys.stdin)

    print(renderizar_diagnostico_prestacao_markdown(diagnostico))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
