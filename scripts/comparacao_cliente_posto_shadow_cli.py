"""Roda a comparação diagnóstica Posto<->Cliente (shadow Postgres ×
Airtable) contra o ambiente real -- frente G ("saída progressiva do
Airtable"), seguindo a mesma missão de `comparacao_airtable.
comparar_cliente_do_posto_shadow_com_airtable` (já mesclada, PR #240).

    python scripts/comparacao_cliente_posto_shadow_cli.py --todos
    python scripts/comparacao_cliente_posto_shadow_cli.py --posto recXXXXXXXX --posto recYYYYYYYY

100% leitura -- nunca escreve em Postgres nem em Airtable, nunca
reconcilia automaticamente (mesma disciplina de `comparacao_airtable.py`:
divergência é sempre reportada, nunca corrigida sozinha). `--todos` usa
`RepositorioAlocacaoPostgres.postos_com_vigencia_cliente_registrada`
(novo método de leitura desta missão, zero schema novo) para enumerar os
postos já conhecidos pelo shadow; uma lista vazia aqui é esperada e
válida enquanto o bootstrap populacional de `vigencia_cliente_por_posto`
não tiver sido feito (fora de escopo desta CLI e da migration 0002).

Rodar contra o ambiente real (Postgres/Airtable de produção) é gate
humano (CLAUDE.md §6/§12-I) -- este script não decide isso; ele só
executa quando chamado, com as credenciais já presentes no ambiente
(`DATABASE_URL`, `AIRTABLE_API_KEY`), mesma disciplina de
`prestacao_diagnostico_real_cli.py`. Sem essas variáveis, falha
explícita -- nunca um default silencioso.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

RAIZ_REPOSITORIO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if RAIZ_REPOSITORIO not in sys.path:
    sys.path.insert(0, RAIZ_REPOSITORIO)

from magnata_os.documental.alocacao.adapters.postgres_alocacao import (  # noqa: E402
    RepositorioAlocacaoPostgres,
)
from magnata_os.documental.alocacao.comparacao_airtable import (  # noqa: E402
    comparar_cliente_do_posto_shadow_com_airtable,
)
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import (  # noqa: E402
    LeitorAirtableSomenteLeitura,
)
from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import (  # noqa: E402
    FonteVinculosPrestacaoAirtableShadow,
)
from magnata_os.documental.modulo01.adapters.conexao import abrir_conexao  # noqa: E402


class CredencialAusente(Exception):
    """`AIRTABLE_API_KEY` não configurada -- mesma disciplina de
    `abrir_conexao`/`ConfiguracaoBancoAusente`: nunca inferir, nunca
    seguir sem a credencial."""


def _ler_airtable_api_key(ambiente: "dict | None" = None) -> str:
    fonte = ambiente if ambiente is not None else os.environ
    valor = (fonte.get("AIRTABLE_API_KEY") or "").strip()
    if not valor:
        raise CredencialAusente(
            "AIRTABLE_API_KEY nao configurada -- a comparacao shadow real "
            "exige leitura do Airtable (ver airtable_leitura.py)."
        )
    return valor


def _analisar_argumentos(argv: "list[str]") -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument(
        "--posto", action="append", dest="postos", metavar="POSTO_ID",
        help="Airtable record id de um Local/Posto (repetível).",
    )
    grupo.add_argument(
        "--todos", action="store_true",
        help="Compara todos os postos já registrados em vigencia_cliente_por_posto.",
    )
    parser.add_argument(
        "--data", default=None,
        help="Data de referência (AAAA-MM-DD). Default: hoje.",
    )
    return parser.parse_args(argv)


def rodar_comparacao(
    postos: "tuple[str, ...]",
    data_referencia: date,
    repo,
    snapshot_airtable,
) -> dict:
    """Pura o suficiente para teste -- `repo`/`snapshot_airtable`
    injetados, nenhuma leitura de ambiente aqui (fica em `main`)."""
    resultados = {
        posto_id: comparar_cliente_do_posto_shadow_com_airtable(
            repo, snapshot_airtable, posto_id, data_referencia,
        ).value
        for posto_id in postos
    }
    resumo: dict = {}
    for estado in resultados.values():
        resumo[estado] = resumo.get(estado, 0) + 1
    return {
        "data_referencia": data_referencia.isoformat(),
        "total_postos": len(postos),
        "resumo_por_estado": resumo,
        "por_posto": resultados,
    }


def main(argv: "list[str] | None" = None) -> int:
    args = _analisar_argumentos(sys.argv[1:] if argv is None else argv)
    data_referencia = (
        date.fromisoformat(args.data) if args.data else date.today()
    )

    try:
        conexao = abrir_conexao()
        airtable_api_key = _ler_airtable_api_key()
    except Exception as exc:  # ConfiguracaoBancoAusente, FalhaConexaoBanco, CredencialAusente
        print(f"BLOQUEADO: {exc}", file=sys.stderr)
        return 2

    repo = RepositorioAlocacaoPostgres(conexao)
    try:
        if args.todos:
            postos = repo.postos_com_vigencia_cliente_registrada()
        else:
            postos = tuple(args.postos)

        leitor = LeitorAirtableSomenteLeitura(api_key=airtable_api_key)
        snapshot_airtable = FonteVinculosPrestacaoAirtableShadow(leitor)

        relatorio = rodar_comparacao(postos, data_referencia, repo, snapshot_airtable)
    finally:
        conexao.rollback()  # somente leitura -- nunca deixa transacao aberta
        conexao.close()

    print(json.dumps(relatorio, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
