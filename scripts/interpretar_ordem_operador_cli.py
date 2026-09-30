"""CLI -- intérprete de ordem em linguagem natural do operador (shadow
only): lê uma ordem de texto livre em português + o mesmo diagnóstico
real já usado pelas CLIs anteriores (`DiagnosticoPrestacao.como_dict()`)
e produz a `SelecaoEnvioOperador` equivalente -- OU, se houver QUALQUER
dúvida real (nome ambíguo, documento não encontrado/não pronto,
competência ausente e não inferível, destinatário não identificado),
uma pendência de esclarecimento explícita, nunca uma adivinhação.

    python scripts/interpretar_ordem_operador_cli.py \\
        --diagnostico diagnostico.json \\
        --ordem "manda pro Fulano e pro Beltrano o holerite de setembro, com assinatura digital e comprovante"

Fluxo completo (este passo é NOVO, ENTRA ANTES do 2º passo já existente):

    python scripts/prestacao_diagnostico_real_cli.py \\
        --cliente recXXXXXXXX --competencia 2026-09 > diagnostico.json
    python scripts/interpretar_ordem_operador_cli.py \\
        --diagnostico diagnostico.json --ordem "manda pro Fulano..." > selecao.json
    # (se "status" vier PENDENCIA_DE_ESCLARECIMENTO, o operador esclarece e roda de novo --
    # esta CLI NUNCA adivinha.)
    python scripts/selecao_envio_operador_cli.py \\
        --diagnostico diagnostico.json --selecao selecao.json
    python scripts/prestacao_compor_ordem_selecionada_cli.py \\
        --cliente recXXXXXXXX --competencia 2026-09 --selecao selecao.json \\
        --preset DOCUMENTO_UNITARIO_SEM_ASSINATURA --mensagem "Segue seu documento"

Responsabilidade ESTRITA desta CLI (nunca mais que isto):
    1. ler `--diagnostico` (MESMO formato de `DiagnosticoPrestacao.
       como_dict()`, já usado por `selecao_envio_operador_cli.py`);
    2. ler opcionalmente `--diretorio-nomes` (JSON `{colaborador_id:
       nome}`) -- ver limitação declarada abaixo e em
       `magnata_os/orquestrador/interpretar_ordem_operador_v1.py`;
    3. chamar `interpretar_ordem_contra_linhas_diagnostico` (núcleo puro
       de `magnata_os.orquestrador.interpretar_ordem_operador_v1`,
       INTOCADO);
    4. imprimir `ResultadoInterpretacaoOrdem.como_dict()` -- uma
       `SelecaoEnvioOperador` pronta OU uma pendência de esclarecimento,
       nunca os dois.

O JSON de saída, quando `status == SELECAO_INTERPRETADA_PRONTA_PARA_
VALIDACAO`, está no MESMO formato do `--selecao` que `selecao_envio_
operador_cli.py`/`prestacao_compor_ordem_selecionada_cli.py` já esperam
(campo `itens`) -- pode ser salvo direto em `selecao.json` e usado sem
adaptação.

**LIMITAÇÃO DECLARADA, não escondida:** `DiagnosticoPrestacao.
como_dict()` nunca carrega nome de colaborador, só `colaborador_id`
opaco (id do Airtable) -- proteção de dado pessoal deliberada (LGPD).
Uma ordem em linguagem natural cita pessoas pelo nome; por isso esta
CLI aceita `--diretorio-nomes`, um JSON SEPARADO e OPCIONAL mapeando
`colaborador_id -> nome`, nunca misturado ao diagnóstico. Sem ele, o
próprio `colaborador_id` é usado como "nome" de correspondência --
suficiente para os testes/ambiente sintético deste repositório, mas
insuficiente para um operador real digitar nome de pessoa física contra
um `colaborador_id` de produção (`recXXXXXXXX`). De onde viria esse
diretório em produção é pendência aberta, registrada em
`docs/decisoes/interpretar-ordem-operador-v1.md`, não resolvida aqui.

Modo sombra: este script NUNCA importa `porta_execucao`,
`transporte_real_habilitado`, nem qualquer adapter de transporte real.
Só interpreta texto e imprime uma `SelecaoEnvioOperador` (ou uma
pendência) -- não cria Ordem, não chama Postgres, não chama nenhum
serviço externo. Leitura de arquivos locais, nenhuma autenticação/rota
HTTP nova -- mesmo espírito das 3 CLIs anteriores desta cadeia.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

RAIZ_REPOSITORIO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if RAIZ_REPOSITORIO not in sys.path:
    sys.path.insert(0, RAIZ_REPOSITORIO)

from magnata_os.orquestrador.interpretar_ordem_operador_v1 import (  # noqa: E402
    InterpretacaoOrdemOperadorError,
    interpretar_ordem_contra_linhas_diagnostico,
)


def _linhas_do_diagnostico_json(diagnostico_json: dict) -> tuple:
    """MESMA lógica de `selecao_envio_operador_cli._linhas_do_
    diagnostico_json` -- intencionalmente duplicada (não importada),
    mesmo padrão já estabelecido neste repositório para pequenos
    helpers de leitura de JSON entre CLIs (scripts/ não formam um
    pacote Python)."""
    linhas = []
    for cliente in diagnostico_json.get('clientes', ()):
        for necessidade in cliente.get('necessidades', ()):
            linhas.append({
                'cliente_id': necessidade['cliente'],
                'competencia_id': necessidade['competencia'],
                'tipo_documental': necessidade['tipo_documental'],
                'colaborador_id': necessidade.get('colaborador'),
                'situacao': necessidade['situacao'],
            })
    return tuple(linhas)


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--diagnostico', required=True, help='caminho do JSON no formato DiagnosticoPrestacao.como_dict()')
    parser.add_argument('--ordem', required=True, help='ordem em linguagem natural (português) do operador')
    parser.add_argument('--diretorio-nomes', default=None,
                        help='opcional: caminho de JSON {colaborador_id: nome} -- ver limitação na docstring deste script')
    return parser.parse_args(argv)


def executar(diagnostico_path: str, ordem_texto: str, diretorio_nomes_path: str = None) -> dict:
    with open(diagnostico_path, 'r', encoding='utf-8') as arquivo:
        diagnostico_json = json.load(arquivo)

    diretorio_nomes = None
    if diretorio_nomes_path:
        with open(diretorio_nomes_path, 'r', encoding='utf-8') as arquivo:
            diretorio_nomes = json.load(arquivo)

    linhas = _linhas_do_diagnostico_json(diagnostico_json)
    resultado = interpretar_ordem_contra_linhas_diagnostico(ordem_texto, linhas, diretorio_nomes=diretorio_nomes)
    return resultado.como_dict()


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        saida = executar(args.diagnostico, args.ordem, args.diretorio_nomes)
    except FileNotFoundError as exc:
        print(f'ARQUIVO_NAO_ENCONTRADO: {exc}')
        return 2
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f'JSON_DE_ENTRADA_INVALIDO: {type(exc).__name__}: {exc}')
        return 2
    except InterpretacaoOrdemOperadorError as exc:
        print(f'ORDEM_INVALIDA: {type(exc).__name__}: {exc}')
        return 2

    print(json.dumps(saida, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
