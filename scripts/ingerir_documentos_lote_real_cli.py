"""Ingestão REAL em lote do conteúdo de documento de UM cliente/UMA
competência (Airtable -> S3/R2 + Postgres).

    python scripts/ingerir_documentos_lote_real_cli.py \\
        --cliente recXXXXXXXX --competencia 2026-09

Motivação (ver docs/decisoes/ingestao-documento-lote-real-v1.md):
`prestacao_diagnostico_real_cli.py`, rodado pela primeira vez contra
Postgres + R2/S3 reais, encontrou 133 registros de `Documento` já
existentes sem NENHUM conteúdo real no armazenamento (bucket R2
recém-criado, metadado órfão) -- nenhum CLI existente ingeria o
BINÁRIO real a partir do Airtable; todos pressupõem que a entrada já
aconteceu. Este CLI fecha essa lacuna.

Reaproveita, sem duplicar nada:
    - `magnata_os.orquestrador.composicao_prestacao_real_v1.
      compor_dependencias_a_partir_do_ambiente` -- as MESMAS dependências
      REAIS (Postgres, S3/R2, leitor Airtable somente leitura) já usadas
      por `prestacao_diagnostico_real_cli.py`;
    - `magnata_os.documental.importacao_lote.
      ingestao_documentos_lote_real.ingerir_documentos_lote` -- núcleo
      que descobre os documentos do cliente+competência (via os MESMOS
      inventários reais já usados pela Prestação) e os ingere via
      `AdaptadorEntradaDuravel` (porta oficial, idempotente por hash).

Disparo SEMPRE manual -- este script nunca é referenciado por
cron/scheduler/render.yaml (ver CLAUDE.md §9/§12-I). Nenhum dado
pessoal (CPF, nome) é impresso -- a saída é só o resumo estruturado
(`ResumoIngestaoLote.como_dict()`): contagens, ids de registro Airtable
e hash SHA-256, nunca nome/CPF.

Rodar contra o ambiente real (Postgres/S3/Airtable de produção) é gate
humano (CLAUDE.md §6/§12-I) -- este módulo não decide isso; ele só
executa quando chamado, com as credenciais já presentes no ambiente.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

RAIZ_REPOSITORIO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if RAIZ_REPOSITORIO not in sys.path:
    sys.path.insert(0, RAIZ_REPOSITORIO)

from magnata_os.documental.importacao_lote.ingestao_documentos_lote_real import (  # noqa: E402
    CompetenciaInvalida,
    ingerir_documentos_lote,
    parse_competencia,
)

from magnata_os.orquestrador.composicao_prestacao_real_v1 import (  # noqa: E402
    compor_dependencias_a_partir_do_ambiente,
    fechar_dependencias,
)


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cliente', required=True, help='id do cliente (registro Airtable recXXX)')
    parser.add_argument('--competencia', required=True, help='competência-base AAAA-MM')
    args = parser.parse_args(argv)
    try:
        parse_competencia(args.competencia)
    except CompetenciaInvalida as exc:
        parser.error(str(exc))
    return args


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    try:
        dependencias = compor_dependencias_a_partir_do_ambiente()
    except RuntimeError as exc:
        print(f'CONFIGURACAO_AUSENTE: {exc}')
        return 2

    try:
        resumo = ingerir_documentos_lote(
            leitor=dependencias.leitor_airtable,
            armazenamento=dependencias.armazenamento,
            repositorio_documentos=dependencias.repositorio_documentos,
            repositorio_historico=dependencias.repositorio_historico,
            cliente_id=args.cliente,
            competencia_base=args.competencia,
        )
    except (ValueError, CompetenciaInvalida) as exc:
        print(f'PARAMETRO_INVALIDO: {exc}')
        return 2
    finally:
        fechar_dependencias(dependencias)

    print(json.dumps(resumo.como_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not resumo.falhas else 1


if __name__ == '__main__':
    raise SystemExit(main())
