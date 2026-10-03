"""CLI -- forma direta e imediatamente utilizável de o operador expressar
a seleção/curadoria de envio (necessidade de negócio: autonomia total
para escolher quais documentos enviar, para quantos colaboradores, com
qual combinação, e se cada envio exige assinatura digital + comprovante
ou não), sem depender do painel publicado -- que ainda não está exposto
publicamente.

Mesmo espírito de `prestacao_readiness_shadow_real.py`: script manual,
leitura de arquivos locais, nenhuma autenticação/rota HTTP nova.

Responsabilidade ESTRITA (nunca mais que isto):
    1. ler 2 arquivos JSON: o diagnóstico (`--diagnostico`, no MESMO
       formato de `DiagnosticoPrestacao.como_dict()`) e a seleção do
       operador (`--selecao`);
    2. montar `SelecaoEnvioOperador` a partir do JSON;
    3. validar a seleção contra o diagnóstico
       (`validar_selecao_contra_linhas_diagnostico`, núcleo puro de
       `magnata_os.orquestrador.selecao_envio_operador_v1`, INTOCADO);
    4. imprimir o resultado -- OU o erro fail-closed, claro, nunca
       silencioso.

**LIMITE CONHECIDO, DECLARADO (não escondido):** esta CLI NÃO chama
`executar_prestacao_selecionada_ate_distribuicao_documental_shadow` (a
composição real da Ordem) porque a composição real de
`ContextoComposicaoPrestacao` a partir de fontes reais (Airtable) AINDA
NÃO EXISTE em nenhum lugar deste repositório -- gap já documentado em
`magnata_os/orquestrador/executar_prestacao_contato_ate_pending_shadow_
v1.py` (linhas 69-72), não recriado nem contornado aqui. Esta CLI entrega
o que É possível hoje sem inventar composição real: validar e prever
exatamente o que a seleção do operador produziria, contra um diagnóstico
já gerado (por quem quer que hoje produza `DiagnosticoPrestacao`, ex. um
teste, um script interno, ou uma futura missão que exponha
`diagnosticar_prestacao` de ponta a ponta). Ligar esta seleção à
composição real da Ordem contra dados reais é a próxima etapa, quando a
composição real do contexto existir -- registrado aqui como pendência,
não como "pronto".

Modo sombra: este script NUNCA importa `porta_execucao`,
`transporte_real_habilitado`, nem qualquer adapter de transporte/
Evolution/Airtable de escrita. Não cria Ordem, não chama Postgres, não
chama nenhum serviço externo -- é validação pura, local, offline.

Formato de `--diagnostico` (mesmo shape de `DiagnosticoPrestacao.
como_dict()`):
    {
      "competencia_base": "2026-09",
      "clientes": [
        {
          "cliente": "cliente-1", "competencia": "2026-09",
          "estado_pacote": "PRONTO", "ordem_pronta": true,
          "necessidades": [
            {"cliente": "cliente-1", "competencia": "2026-09",
             "tipo_documental": "HOLERITE", "colaborador": "colab-1",
             "situacao": "PRONTO", "documentos_avaliados": ["doc-1"],
             "documentos_elegiveis": ["doc-1"], "localizacao": null}
          ]
        }
      ]
    }

Formato de `--selecao`:
    {
      "itens": [
        {"cliente_id": "cliente-1", "competencia_id": "2026-09",
         "colaborador_id": "colab-1", "tipos_documentais": ["HOLERITE"],
         "exigir_assinatura_digital_e_comprovante": false}
      ]
    }

Uso:
    python scripts/selecao_envio_operador_cli.py \\
        --diagnostico diagnostico.json --selecao selecao.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

RAIZ_REPOSITORIO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if RAIZ_REPOSITORIO not in sys.path:
    sys.path.insert(0, RAIZ_REPOSITORIO)

from magnata_os.orquestrador.selecao_envio_operador_v1 import (  # noqa: E402
    ItemSelecaoEnvioOperador,
    SelecaoEnvioOperador,
    SelecaoEnvioOperadorError,
    validar_selecao_contra_linhas_diagnostico,
)


def _linhas_do_diagnostico_json(diagnostico_json: dict) -> tuple:
    """Mesmas colunas de `selecao_envio_operador_v1._linhas_do_
    diagnostico`, extraídas diretamente do JSON no formato de
    `DiagnosticoPrestacao.como_dict()` -- nunca reconstrói as
    dataclasses completas (`ReferenciaCanonica`/`NecessidadeDocumento
    Prestacao`/...), porque a única coisa que a validação de fato
    precisa são estas 5 colunas opacas."""
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


def _selecao_do_json(selecao_json: dict) -> SelecaoEnvioOperador:
    itens = tuple(
        ItemSelecaoEnvioOperador(
            cliente_id=item['cliente_id'],
            competencia_id=item['competencia_id'],
            colaborador_id=item['colaborador_id'],
            tipos_documentais=tuple(item['tipos_documentais']),
            exigir_assinatura_digital_e_comprovante=item['exigir_assinatura_digital_e_comprovante'],
        )
        for item in selecao_json.get('itens', ())
    )
    return SelecaoEnvioOperador(itens=itens)


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--diagnostico', required=True, help='caminho do JSON no formato DiagnosticoPrestacao.como_dict()')
    parser.add_argument('--selecao', required=True, help='caminho do JSON da seleção do operador')
    return parser.parse_args(argv)


def executar(diagnostico_path: str, selecao_path: str) -> dict:
    with open(diagnostico_path, 'r', encoding='utf-8') as arquivo:
        diagnostico_json = json.load(arquivo)
    with open(selecao_path, 'r', encoding='utf-8') as arquivo:
        selecao_json = json.load(arquivo)

    selecao = _selecao_do_json(selecao_json)
    linhas = _linhas_do_diagnostico_json(diagnostico_json)

    if not selecao.itens:
        return {
            'status': 'SELECAO_VAZIA_NENHUMA_ORDEM',
            'itens_validados': [],
            'aviso': 'seleção sem itens é o padrão seguro -- nenhuma Ordem seria criada.',
        }

    validados = validar_selecao_contra_linhas_diagnostico(linhas, selecao)
    return {
        'status': 'SELECAO_VALIDA_PRONTA_PARA_ORDEM',
        'itens_validados': [
            {
                'cliente_id': v.cliente_id, 'competencia_id': v.competencia_id,
                'colaborador_id': v.colaborador_id, 'tipos_documentais': list(v.tipos_documentais),
                'exigir_assinatura_digital_e_comprovante': v.exigir_assinatura_digital_e_comprovante,
            }
            for v in validados
        ],
        'aviso': (
            'ESTA CLI NÃO ENVIA NADA DE VERDADE E NÃO CRIA ORDEM -- só valida a seleção contra o '
            'diagnóstico informado. Virar Ordem real (ainda em modo sombra, sujeita às 3 barreiras de '
            'transporte real) é responsabilidade de '
            'executar_prestacao_selecionada_ate_distribuicao_documental_shadow, chamada por quem compuser '
            'o ContextoComposicaoPrestacao real (peça ainda não existente neste repositório).'
        ),
    }


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        saida = executar(args.diagnostico, args.selecao)
    except FileNotFoundError as exc:
        print(f'ARQUIVO_NAO_ENCONTRADO: {exc}')
        return 2
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f'JSON_DE_ENTRADA_INVALIDO: {type(exc).__name__}: {exc}')
        return 2
    except SelecaoEnvioOperadorError as exc:
        print(f'SELECAO_REJEITADA: {type(exc).__name__}: {exc}')
        return 2

    print(json.dumps(saida, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
