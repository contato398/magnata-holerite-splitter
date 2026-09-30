"""Diagnóstico REAL da Prestação de um cliente/competência (J4 -- elo que
faltava entre a composição real do contexto e a seleção/curadoria do
operador).

    python scripts/prestacao_diagnostico_real_cli.py \\
        --cliente recXXXXXXXX --competencia 2026-09 > diagnostico.json

Reaproveita, sem duplicar nada:
    - `magnata_os.orquestrador.composicao_prestacao_real_v1.
      compor_dependencias_a_partir_do_ambiente` -- monta as dependências
      REAIS (Postgres, S3, motor OCR opcional, leitor Airtable somente
      leitura via `AIRTABLE_API_KEY`), o mesmo compositor já usado por
      `prestacao_cliente_competencia_v1.py`;
    - `montar_contexto_prestacao` -- o mesmo contexto REAL da Prestação
      para 1 cliente/1 competência (J4), também já usado por
      `prestacao_cliente_competencia_v1.py`;
    - `magnata_os.classificacao.composicao_ciclo_persistente_prestacao.
      diagnosticar_prestacao` -- o núcleo já existente, somente leitura
      (nunca grava Documento/blob/evento real -- ver
      `_contexto_somente_leitura` no próprio módulo).

Responsabilidade ESTRITA desta CLI (nunca mais que isto): montar as 3
peças acima e imprimir `DiagnosticoPrestacao.como_dict()` como JSON --
NADA além disso. Em particular, este script NUNCA chama
`--ate-pending`/`executar_prestacao_contato_ate_pending_shadow_v1`
(isso já existe em `prestacao_cliente_competencia_v1.py`, intocado, para
quem precisar) e NUNCA chama a seleção/curadoria do operador nem a
composição da Ordem -- essa é a responsabilidade de
`scripts/selecao_envio_operador_cli.py` (PR #210), a jusante, num
segundo passo manual do operador. Ver
`docs/decisoes/prestacao-diagnostico-real-cli-v1.md` para o fluxo
completo ponta a ponta.

Por que não reusar `executar_prestacao_cliente_competencia` diretamente:
essa função (em `prestacao_cliente_competencia_v1.py`) empacota o
diagnóstico dentro de um relatório maior (`modo`, `coleta`,
`busca_incompleta`, `ordens`...) porque cobre também `--ate-pending` e
coleta de e-mail -- responsabilidades fora do escopo desta CLI. Chamar
`diagnosticar_prestacao` direto, sobre o MESMO contexto que
`montar_contexto_prestacao` já produz, devolve exatamente
`DiagnosticoPrestacao.como_dict()`, sem nenhum campo extra -- o formato
que `selecao_envio_operador_cli.py` já espera em `--diagnostico`,
confirmado lendo os dois lados (`_linhas_do_diagnostico_json` só lê
`clientes[*].necessidades[*]` com as chaves
cliente/competencia/tipo_documental/colaborador/situacao -- exatamente
o que `DiagnosticoNecessidade.como_dict()` produz). Nenhuma adaptação de
formato foi necessária.

Rodar contra o ambiente real (Postgres/S3/Airtable de produção) é gate
humano (CLAUDE.md §6/§12-I) -- este módulo não decide isso; ele só
executa quando chamado, com as credenciais já presentes no ambiente
(mesma disciplina de `compor_dependencias_a_partir_do_ambiente`: sem
`AIRTABLE_API_KEY`, falha explícita, nunca default silencioso).

Modo sombra: este script NUNCA importa `porta_execucao`,
`transporte_real_habilitado`, nem qualquer adapter de transporte real ou
de escrita no Airtable -- é diagnóstico, 100% somente leitura.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

RAIZ_REPOSITORIO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if RAIZ_REPOSITORIO not in sys.path:
    sys.path.insert(0, RAIZ_REPOSITORIO)

from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import diagnosticar_prestacao  # noqa: E402

from magnata_os.orquestrador.composicao_prestacao_real_v1 import (  # noqa: E402
    ClienteNaoAtivo,
    DependenciasPrestacaoReal,
    compor_dependencias_a_partir_do_ambiente,
    fechar_dependencias,
    montar_contexto_prestacao,
    parse_competencia,
)


def executar_diagnostico_real(
    *,
    cliente_id: str,
    competencia_base: str,
    dependencias: DependenciasPrestacaoReal,
    competencia_snapshot_airtable_comprovada=None,
) -> dict:
    """Monta o contexto REAL (mesma peça de `prestacao_cliente_
    competencia_v1.executar_prestacao_cliente_competencia`) e devolve
    `DiagnosticoPrestacao.como_dict()` -- sem nenhum campo extra, sem
    gravar nada. Erro de cliente inexistente/inativo ou competência mal
    formada propaga (`ClienteNaoAtivo`/`ValueError`) -- nunca é
    mascarado como diagnóstico vazio."""
    contexto = montar_contexto_prestacao(
        cliente_id=cliente_id,
        competencia_base=competencia_base,
        dependencias=dependencias,
        competencia_snapshot_airtable_comprovada=competencia_snapshot_airtable_comprovada,
    )
    diagnostico = diagnosticar_prestacao(contexto)
    return dict(diagnostico.como_dict())


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cliente', required=True, help='id do cliente (registro Airtable recXXX)')
    parser.add_argument('--competencia', required=True, help='competência-base AAAA-MM')
    parser.add_argument('--snapshot-airtable-comprovado', default=None,
                        help='AAAA-MM: SÓ se o vínculo Funcionário->Local de hoje vale para essa competência')
    args = parser.parse_args(argv)
    try:
        parse_competencia(args.competencia)
        if args.snapshot_airtable_comprovado:
            parse_competencia(args.snapshot_airtable_comprovado)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    snapshot = parse_competencia(args.snapshot_airtable_comprovado) if args.snapshot_airtable_comprovado else None
    try:
        dependencias = compor_dependencias_a_partir_do_ambiente()
    except RuntimeError as exc:
        print(f'CONFIGURACAO_AUSENTE: {exc}')
        return 2

    try:
        diagnostico = executar_diagnostico_real(
            cliente_id=args.cliente, competencia_base=args.competencia, dependencias=dependencias,
            competencia_snapshot_airtable_comprovada=snapshot,
        )
    except ClienteNaoAtivo as exc:
        print(f'CLIENTE_NAO_ENCONTRADO_OU_INATIVO: {exc}')
        return 2
    except ValueError as exc:
        print(f'PARAMETRO_INVALIDO: {exc}')
        return 2
    finally:
        fechar_dependencias(dependencias)

    print(json.dumps(diagnostico, ensure_ascii=False, indent=2, default=str, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
