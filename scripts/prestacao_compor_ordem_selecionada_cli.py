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

**PRESETS COM ASSINATURA -- WIRING, não construção (ver
`docs/decisoes/prestacao-compor-ordem-selecionada-assinatura-wiring-v1.md`):**
esta CLI aceita qualquer `preset_id` conhecido de
`politica_preset_distribuicao_documental.resolver_preset` -- inclusive
`DOCUMENTO_UNITARIO_COM_ASSINATURA`/`PACOTE_2_DOCUMENTOS_1_LINK_COM_ASSINATURA`.
`materializador`/`porta_assinatura`/`repositorio_conclusao` já existem
como componentes REAIS neste repositório (`MaterializadorArquivoLegadoAirtable`,
`AdapterObrigacaoAssinaturaLegadoHttp`, `RepositorioConclusaoObrigacaoAssinaturaPostgres`)
e já são compostos a partir do ambiente por `distribuir_documento_v1.py`
(`_compor_materializador_a_partir_do_ambiente`/`_compor_obrigacao_
assinatura_a_partir_do_ambiente`/`_compor_repositorio_conclusao_a_
partir_do_ambiente`, reaproveitados aqui, nunca duplicados) -- esta CLI
só passa a chamá-los quando `resolver_preset(preset_id).exigir_
assinatura` for `True`, exatamente como `distribuir_documento_v1.py`
já faz para a Ordem não selecionada.

Um item de `--selecao` cujo `exigir_assinatura_digital_e_comprovante`
diverge do que o `--preset` desta execução exige continua REJEITADO
(isolado, fail-closed) por `PresetDaOrdemDivergeDaSelecaoOperador` --
nunca sai uma Ordem silenciosamente diferente do que o operador pediu;
os demais colaboradores da mesma seleção continuam normalmente. Como
antes, cada execução desta CLI usa 1 único `--preset` para toda a
seleção informada -- misturar colaboradores com e sem exigência de
assinatura na MESMA chamada continua exigindo 2 chamadas (1 por
preset), cada uma isolando quem não corresponde ao preset escolhido.

Continua estritamente SEM transporte real e SEM autorização humana
real: o ramo com assinatura chama o motor de assinatura de verdade
(`criar_ou_recuperar`, `disparar_whatsapp=false` no adapter legado) --
isto NÃO é WhatsApp real, é a mesma criação de obrigação/link que
`distribuir_documento_v1.py` já faz em produção para presets com
assinatura; a autorização que precede essa chamada continua sendo
`autorizar_preview_assinatura_shadow` (sintética), nunca decisão
humana real. Não existe, nem antes nem depois desta mudança, uma
barreira de "assinatura real" separada das 3 barreiras de transporte
real -- a única barreira aqui é a credencial de ambiente
(`AIRTABLE_API_KEY`/`ORQUESTRADOR_ASSINATURA_BASE_URL`/
`ORQUESTRADOR_ASSINATURA_API_KEY`) exigida fail-closed pelos próprios
compositores reaproveitados; sem elas configuradas, a CLI nunca chega a
tentar a chamada real (`RuntimeError` explícito). Rodar esta CLI com
essas credenciais reais configuradas e um preset com assinatura JÁ
CRIA uma obrigação de assinatura real (Airtable/app.py) -- gate humano
igual a qualquer outra ação externa real (CLAUDE.md §6), nunca decidido
por este módulo.

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
    _compor_materializador_a_partir_do_ambiente,
    _compor_obrigacao_assinatura_a_partir_do_ambiente,
    _compor_repositorio_acoes_a_partir_do_ambiente,
    _compor_repositorio_autorizacoes_a_partir_do_ambiente,
    _compor_repositorio_conclusao_a_partir_do_ambiente,
    _compor_repositorio_execucoes_a_partir_do_ambiente,
)
from magnata_os.orquestrador.executar_prestacao_selecionada_contato_ate_pending_shadow_v1 import (  # noqa: E402
    compor_chave_fernet_contato_a_partir_do_ambiente,
    compor_repositorio_contato_a_partir_do_ambiente,
    executar_prestacao_selecionada_contato_ate_pending_shadow_v1,
)
from magnata_os.orquestrador.politica_preset_distribuicao_documental import (  # noqa: E402
    PresetDistribuicaoDocumentalDesconhecido,
    resolver_preset,
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
                        help='obrigatório (decisão de negócio) -- qualquer preset_id conhecido de '
                             'politica_preset_distribuicao_documental (com ou sem assinatura)')
    parser.add_argument('--mensagem', required=True, help='obrigatório (decisão de negócio)')
    parser.add_argument('--tipo-documento', default='PRESTACAO_CONTAS',
                        help='tipo_documento da Ordem (default: PRESTACAO_CONTAS)')
    args = parser.parse_args(argv)
    try:
        resolver_preset(args.preset)
    except PresetDistribuicaoDocumentalDesconhecido as exc:
        parser.error(str(exc))
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

    # Compositores reais (`distribuir_documento_v1.py`, intocados, só
    # reaproveitados) só são chamados quando o PRESET desta execução
    # exige assinatura -- mesmo gate condicional já usado por
    # `distribuir_documento_v1.main` para a Ordem não selecionada. Sem
    # assinatura, nenhuma credencial de Airtable/motor de assinatura é
    # sequer olhada (fail-closed por omissão, nunca por exceção tardia).
    preset = resolver_preset(preset_id)
    materializador = _compor_materializador_a_partir_do_ambiente() if preset.exigir_assinatura else None
    porta_assinatura = _compor_obrigacao_assinatura_a_partir_do_ambiente() if preset.exigir_assinatura else None
    repositorio_conclusao = (
        _compor_repositorio_conclusao_a_partir_do_ambiente() if preset.exigir_assinatura else None
    )

    resultados = executar_prestacao_selecionada_contato_ate_pending_shadow_v1(
        contexto=contexto, selecao_operador=selecao,
        repositorio_contato=repositorio_contato, chave_fernet=chave_fernet,
        preset_id=preset_id, tipo_documento=tipo_documento,
        montar_mensagem_texto=lambda cliente, competencia: mensagem,
        repositorio_documentos=dependencias.repositorio_documentos,
        armazenamento=dependencias.armazenamento,
        materializador=materializador, porta_assinatura=porta_assinatura,
        repositorio_execucoes=repositorio_execucoes,
        repositorio_autorizacoes=repositorio_autorizacoes,
        repositorio_acoes=repositorio_acoes,
        ator_referencia=f'cli:{PROVENIENCIA}', proveniencia=PROVENIENCIA,
        instante=instante or datetime.now(timezone.utc),
        repositorio_conclusao=repositorio_conclusao,
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
    except RuntimeError as exc:
        # Config ausente para materializador/porta_assinatura (só surge
        # com preset com assinatura) -- mesmo fail-closed de
        # `compor_dependencias_a_partir_do_ambiente`, aqui porque a
        # falta só é descoberta dentro de `executar()` (o preset só é
        # resolvido depois que as dependências de contexto já foram
        # compostas).
        print(f'CONFIGURACAO_AUSENTE: {exc}')
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
