"""Verifica a credencial efetiva de conexao ao Postgres (somente leitura).

Contexto: bloqueio operacional no Render -- o `magnata-holerite-worker`
precisa comprovar que está conectando ao banco `magnata_os` como o usuario
`magnata_worker_rot2` (credencial rotacionada) antes de:
  - aplicar a migration 0003 (`magnata_os/orquestrador/migrations/0003_*`);
  - ativar a persistencia real do executor do Orquestrador.

Este script NAO altera nada -- abre uma unica conexao via
`magnata_os.documental.modulo01.adapters.conexao.abrir_conexao` (o UNICO
ponto do pacote que importa `psycopg`, ver CLAUDE.md do modulo) e roda
tres leituras:

    SELECT current_database();
    SELECT current_user;
    SELECT 1;

Nunca imprime a DATABASE_URL nem qualquer credencial -- so o resultado das
tres consultas. Sai com codigo 0 somente se as tres provas baterem com o
esperado (banco e usuario esperados sao parametros, nunca hardcoded).

Uso (a partir de uma sessao com acesso real a DATABASE_URL de producao --
este ambiente de desenvolvimento nao tem essa credencial):

    DATABASE_URL="postgres://..." python scripts/verificar_credencial_worker_postgres.py \\
        --banco-esperado magnata_os --usuario-esperado magnata_worker_rot2

Este script e so a PROVA, nao a correcao. A correcao (fazer o worker do
Render usar a credencial certa) e uma acao de producao fora do escopo do
que este script faz -- exige autorizacao de fase propria (ver
CLAUDE.md, §6) e execucao no painel do Render, nao aqui.
"""

from __future__ import annotations

import argparse
import os
import sys

RAIZ_REPOSITORIO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if RAIZ_REPOSITORIO not in sys.path:
    sys.path.insert(0, RAIZ_REPOSITORIO)

from magnata_os.documental.modulo01.adapters.conexao import (  # noqa: E402
    ConfiguracaoBancoAusente,
    FalhaConexaoBanco,
    abrir_conexao,
)


class ProvaCredencialFalhou(Exception):
    """Uma ou mais das tres provas exigidas nao bateu com o esperado."""


def _analisar_argumentos(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--banco-esperado",
        default="magnata_os",
        help="Nome esperado de current_database() (default: magnata_os).",
    )
    parser.add_argument(
        "--usuario-esperado",
        default="magnata_worker_rot2",
        help="Usuario esperado de current_user (default: magnata_worker_rot2).",
    )
    return parser.parse_args(argv)


def verificar_credencial(
    banco_esperado: str,
    usuario_esperado: str,
    abrir_conexao_fn=abrir_conexao,
) -> dict:
    """Abre uma conexao, roda as tres provas e devolve um relatorio dict.

    Levanta ProvaCredencialFalhou se qualquer prova nao bater. Nunca inclui
    a DATABASE_URL no relatorio ou em qualquer excecao.
    """
    conexao = abrir_conexao_fn()
    try:
        cursor = conexao.cursor()
        try:
            cursor.execute("SELECT current_database(), current_user")
            banco_atual, usuario_atual = cursor.fetchone()

            cursor.execute("SELECT 1")
            (select_um,) = cursor.fetchone()
        finally:
            cursor.close()
    finally:
        conexao.rollback()  # somente leitura -- nunca deixa transacao aberta
        conexao.close()

    relatorio = {
        "current_database": banco_atual,
        "current_user": usuario_atual,
        "select_1_ok": select_um == 1,
        "banco_esperado": banco_esperado,
        "usuario_esperado": usuario_esperado,
        "banco_confere": banco_atual == banco_esperado,
        "usuario_confere": usuario_atual == usuario_esperado,
    }
    relatorio["prova_completa"] = (
        relatorio["banco_confere"]
        and relatorio["usuario_confere"]
        and relatorio["select_1_ok"]
    )

    if not relatorio["prova_completa"]:
        raise ProvaCredencialFalhou(
            "Prova de credencial NAO bateu -- "
            f"current_database()={banco_atual!r} (esperado {banco_esperado!r}), "
            f"current_user={usuario_atual!r} (esperado {usuario_esperado!r}), "
            f"SELECT 1 ok={relatorio['select_1_ok']}"
        )
    return relatorio


def main(argv: list[str] | None = None) -> int:
    args = _analisar_argumentos(sys.argv[1:] if argv is None else argv)

    try:
        relatorio = verificar_credencial(args.banco_esperado, args.usuario_esperado)
    except ConfiguracaoBancoAusente as exc:
        print(f"BLOQUEADO: {exc}", file=sys.stderr)
        return 2
    except FalhaConexaoBanco as exc:
        print(f"FALHA_CONEXAO: {exc}", file=sys.stderr)
        return 2
    except ProvaCredencialFalhou as exc:
        print(f"PROVA_FALHOU: {exc}", file=sys.stderr)
        return 1

    print("PROVA_OK")
    print(f"  current_database() = {relatorio['current_database']}")
    print(f"  current_user       = {relatorio['current_user']}")
    print(f"  SELECT 1           = {'sucesso' if relatorio['select_1_ok'] else 'falha'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
