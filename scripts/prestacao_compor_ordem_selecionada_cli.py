"""Compõe a ORDEM REAL da Prestação a partir da seleção/curadoria do
operador -- terceiro e último passo do fluxo, sempre em modo sombra
(termina em PENDING), sujeita às mesmas 3 barreiras de transporte real de
sempre.

Fluxo completo de 3 passos que esta CLI fecha:

    python scripts/prestacao_diagnostico_real_cli.py \\
        --cliente recXXXXXXXX --competencia 2026-09 > diagnostico.json
    # operador edita/cria selecao.json a partir do diagnostico.json
    python scripts/selecao_envio_operador_cli.py \\
        --diagnostico diagnostico.json --selecao selecao.json
    python scripts/prestacao_compor_ordem_selecionada_cli.py \\
        --cliente recXXXXXXXX --competencia 2026-09 --selecao selecao.json \\
        --preset DOCUMENTO_UNITARIO_SEM_ASSINATURA \\
        --mensagem "Segue seu documento"

Fecha a pendência declarada em `docs/decisoes/selecao-envio-operador-v1.md`
e `docs/decisoes/prestacao-diagnostico-real-cli-v1.md` -- "seleção
validada -> Ordem real composta, ainda em sombra" -- reaproveitando, SEM
DUPLICAR:

    - `compor_dependencias_a_partir_do_ambiente`/`montar_contexto_
      prestacao` (`composicao_prestacao_real_v1.py`, já existentes e
      intocados) -- as mesmas dependências e o mesmo contexto REAL que
      `prestacao_diagnostico_real_cli.py`/`prestacao_cliente_
      competencia_v1.py` já usam;
    - `executar_prestacao_selecionada_contato_ate_pending_shadow_v1`
      (novo módulo desta missão, `magnata_os/orquestrador/`) -- que por
      sua vez só liga, sem duplicar, `construir_resolvedor_parametros_
      ordem_prestacao_contato_v1` (resolvedor real de destinatário,
      intocado) a `executar_prestacao_selecionada_ate_distribuicao_
      documental_shadow` (composição já filtrada pela seleção do
      operador, `wiring_prestacao_distribuicao_documental_shadow.py`,
      PR #210, intocada).

Responsabilidade ESTRITA desta CLI (nunca mais que isto):
    1. montar as dependências e o contexto reais (`--cliente`/
       `--competencia`, mesmo formato das outras CLIs de Prestação);
    2. ler `--selecao` (JSON, MESMO formato de `selecao_envio_operador_
       cli.py --selecao`) e montar `SelecaoEnvioOperador`;
    3. montar o resolvedor real de destinatário/preset/mensagem a partir
       de `--preset`/`--mensagem` (decisão de negócio, sempre informada
       por quem roda -- nunca um default, mesma disciplina de
       `--ate-pending` em `prestacao_cliente_competencia_v1.py`);
    4. chamar `executar_prestacao_selecionada_contato_ate_pending_
       shadow_v1` e imprimir o resultado (ou o erro fail-closed, nunca
       silencioso).

**LIMITE CONHECIDO, DECLARADO (não escondido):** assim como
`--ate-pending` em `prestacao_cliente_competencia_v1.py`, esta CLI só
aceita presets SEM assinatura (`PRESETS_SEM_ASSINATURA`, reaproveitado
de lá, não duplicado) -- presets com assinatura exigem compositores de
`materializador`/`porta_assinatura` a partir do ambiente que ainda não
existem neste repositório (mesmo gap já documentado naquele módulo).
Um item de `--selecao` com `exigir_assinatura_digital_e_comprovante:
true`, combinado com o preset sem assinatura desta CLI, é REJEITADO
(isolado, fail-closed) por `PresetDaOrdemDivergeDaSelecaoOperador` --
nunca sai uma Ordem silenciosamente diferente do que o operador pediu;
os demais colaboradores da mesma seleção continuam normalmente. Ligar
esta CLI a presets com assinatura é pendência futura separada, quando a
composição real de `materializador`/`porta_assinatura` a partir do
ambiente existir -- registrado aqui, não escondido como "pronto".

Rodar contra o ambiente real (Postgres/S3/Airtable de produção) é gate
humano (CLAUDE.md §6/§12-I) -- este módulo não decide isso; ele só
executa quando chamado, com as credenciais já presentes no ambiente.

Modo sombra: este script NUNCA importa `porta_execucao`,
`transporte_real_habilitado`, nem qualquer adapter de transporte real.
Termina estritamente em PENDING -- as mesmas 3 barreiras de sempre
continuam intactas para qualquer envio real.

Formato de `--selecao` (idêntico ao de `selecao_envio_operador_cli.py`):
    {
      "itens": [
        {"cliente_id": "cliente-1", "competencia_id": "2026-09",
         "colaborador_id": "colab-1", "tipos_documentais": ["HOLERITE"],
         "exigir_assinatura_digital_e_comprovante": false}
      ]
    }
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

RAIZ_REPOSITORIO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if RAIZ_REPOSITORIO not in sys.path:
    sys.path.insert(0, RAIZ_REPOSITORIO)

from magnata_os.orquestrador.composicao_prestacao_real_v1 import (  # noqa: E402
    ClienteNaoAtivo,
    compor_dependencias_a_partir_do_ambiente,
    fechar_dependencias,
    montar_contexto_prestacao,
    parse_competencia,
)
from magnata_os.orquestrador.distribuir_documento_v1 import (  # noqa: E402
    _compor_repositorio_acoes_a_partir_do_ambiente,
    _compor_repositorio_autorizacoes_a_partir_do_ambiente,
    _compor_repositorio_execucoes_a_partir_do_ambiente,
)
from magnata_os.orquestrador.executar_prestacao_selecionada_contato_ate_pending_shadow_v1 import (  # noqa: E402
    compor_chave_fernet_contato_a_partir_do_ambiente,
    compor_repositorio_contato_a_partir_do_ambiente,
    executar_prestacao_selecionada_contato_ate_pending_shadow_v1,
)
from magnata_os.orquestrador.prestacao_cliente_competencia_v1 import (  # noqa: E402
    PRESETS_SEM_ASSINATURA,
)
from magnata_os.orquestrador.selecao_envio_operador_v1 import (  # noqa: E402
    ItemSelecaoEnvioOperador,
    SelecaoEnvioOperador,
    SelecaoEnvioOperadorError,
)
from magnata_os.orquestrador.wiring_prestacao_distribuicao_documental_shadow import (  # noqa: E402
    PrestacaoDistribuicaoDocumentalError,
)
from magnata_os.orquestrador.wiring_distribuicao_documental_shadow import (  # noqa: E402
    DistribuicaoDocumentalError,
)

PROVENIENCIA = 'prestacao_compor_ordem_selecionada_cli'


def _selecao_do_json(selecao_json: dict) -> SelecaoEnvioOperador:
    """MESMA lógica de `selecao_envio_operador_cli._selecao_do_json` --
    intencionalmente duplicada (não importada), mesmo padrão já
    estabelecido neste repositório para pequenos helpers de leitura de
    JSON entre CLIs (ver docstring de `test_integracao_prestacao_
    contato_ate_pending.py`, "fixtures duplicadas, não importadas"):
    scripts em `scripts/` não formam um pacote Python e este helper é
    pequeno o bastante para não justificar extrair um módulo novo só
    para ele."""
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
    parser.add_argument('--cliente', required=True, help='id do cliente (registro Airtable recXXX)')
    parser.add_argument('--competencia', required=True, help='competência-base AAAA-MM')
    parser.add_argument('--snapshot-airtable-comprovado', default=None,
                        help='AAAA-MM: SÓ se o vínculo Funcionário->Local de hoje vale para essa competência')
    parser.add_argument('--selecao', required=True, help='caminho do JSON da seleção do operador')
    parser.add_argument('--preset', required=True,
                        help=f'obrigatório (decisão de negócio) -- um de {sorted(PRESETS_SEM_ASSINATURA)}')
    parser.add_argument('--mensagem', required=True, help='obrigatório (decisão de negócio)')
    parser.add_argument('--tipo-documento', default='PRESTACAO_CONTAS',
                        help='tipo_documento da Ordem (default: PRESTACAO_CONTAS)')
    args = parser.parse_args(argv)
    if args.preset not in PRESETS_SEM_ASSINATURA:
        parser.error(f'--preset deve ser um de {sorted(PRESETS_SEM_ASSINATURA)}')
    try:
        parse_competencia(args.competencia)
        if args.snapshot_airtable_comprovado:
            parse_competencia(args.snapshot_airtable_comprovado)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def executar(
    *,
    cliente_id: str,
    competencia_base: str,
    selecao_path: str,
    preset_id: str,
    mensagem: str,
    tipo_documento: str,
    dependencias,
    competencia_snapshot_airtable_comprovada=None,
    instante=None,
) -> dict:
    with open(selecao_path, 'r', encoding='utf-8') as arquivo:
        selecao_json = json.load(arquivo)
    selecao = _selecao_do_json(selecao_json)

    if not selecao.itens:
        return {
            'status': 'SELECAO_VAZIA_NENHUMA_ORDEM',
            'ordens': [],
            'aviso': 'seleção sem itens é o padrão seguro -- nenhuma Ordem foi criada, nenhuma dependência real foi consultada além do contexto.',
        }

    contexto = montar_contexto_prestacao(
        cliente_id=cliente_id, competencia_base=competencia_base, dependencias=dependencias,
        competencia_snapshot_airtable_comprovada=competencia_snapshot_airtable_comprovada,
    )

    repositorio_contato = compor_repositorio_contato_a_partir_do_ambiente()
    chave_fernet = compor_chave_fernet_contato_a_partir_do_ambiente()
    repositorio_execucoes = _compor_repositorio_execucoes_a_partir_do_ambiente()
    repositorio_autorizacoes = _compor_repositorio_autorizacoes_a_partir_do_ambiente()
    repositorio_acoes = _compor_repositorio_acoes_a_partir_do_ambiente()

    resultados = executar_prestacao_selecionada_contato_ate_pending_shadow_v1(
        contexto=contexto, selecao_operador=selecao,
        repositorio_contato=repositorio_contato, chave_fernet=chave_fernet,
        preset_id=preset_id, tipo_documento=tipo_documento,
        montar_mensagem_texto=lambda cliente, competencia: mensagem,
        repositorio_documentos=dependencias.repositorio_documentos,
        armazenamento=dependencias.armazenamento,
        materializador=None, porta_assinatura=None,
        repositorio_execucoes=repositorio_execucoes,
        repositorio_autorizacoes=repositorio_autorizacoes,
        repositorio_acoes=repositorio_acoes,
        ator_referencia=f'cli:{PROVENIENCIA}', proveniencia=PROVENIENCIA,
        instante=instante or datetime.now(timezone.utc),
    )

    itens_selecionados = sum(len(item.tipos_documentais) and 1 or 0 for item in selecao.itens)
    return {
        'status': 'ORDENS_COMPOSTAS_EM_SOMBRA_PENDING',
        'itens_na_selecao': itens_selecionados,
        'ordens_compostas': len(resultados),
        'ordens': [
            {
                'funcionario_id': r.funcionario_id,
                'event_id': r.event_id,
                'estado_acao': r.acao_persistida.estado.value,
                'assinatura_link': r.assinatura_link,
            }
            for r in resultados
        ],
        'aviso': (
            'ESTA CLI NÃO ENVIA NADA DE VERDADE. As Ordens acima pararam em PENDING (modo sombra), sujeitas às '
            'mesmas 3 barreiras de sempre (autorizar_transporte_real, ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO, '
            'ORQUESTRADOR_DRY_RUN) para qualquer envio real -- nenhuma delas foi tocada por este comando. Item(s) '
            'da seleção que não geraram Ordem (ex.: destinatário sem contato cadastrado, preset divergente da '
            'exigência de assinatura do operador) ficam isolados e registrados em log -- nunca contaminam os '
            'demais; conferir "ordens_compostas" contra "itens_na_selecao" para identificar divergência.'
        ),
    }


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    snapshot = parse_competencia(args.snapshot_airtable_comprovado) if args.snapshot_airtable_comprovado else None
    try:
        dependencias = compor_dependencias_a_partir_do_ambiente()
    except RuntimeError as exc:
        print(f'CONFIGURACAO_AUSENTE: {exc}')
        return 2

    try:
        saida = executar(
            cliente_id=args.cliente, competencia_base=args.competencia, selecao_path=args.selecao,
            preset_id=args.preset, mensagem=args.mensagem, tipo_documento=args.tipo_documento,
            dependencias=dependencias, competencia_snapshot_airtable_comprovada=snapshot,
        )
    except ClienteNaoAtivo as exc:
        print(f'CLIENTE_NAO_ENCONTRADO_OU_INATIVO: {exc}')
        return 2
    except (FileNotFoundError,) as exc:
        print(f'ARQUIVO_NAO_ENCONTRADO: {exc}')
        return 2
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f'JSON_DE_ENTRADA_INVALIDO: {type(exc).__name__}: {exc}')
        return 2
    except SelecaoEnvioOperadorError as exc:
        print(f'SELECAO_REJEITADA: {type(exc).__name__}: {exc}')
        return 2
    except (PrestacaoDistribuicaoDocumentalError, DistribuicaoDocumentalError) as exc:
        print(f'COMPOSICAO_REJEITADA: {type(exc).__name__}: {exc}')
        return 2
    except ValueError as exc:
        print(f'PARAMETRO_INVALIDO: {exc}')
        return 2
    finally:
        fechar_dependencias(dependencias)

    print(json.dumps(saida, ensure_ascii=False, indent=2, default=str, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
