# Composição REAL da Ordem a partir da seleção do operador (V1, modo sombra)

## Necessidade de negócio (registrada por completo, não só na conversa)

`docs/decisoes/selecao-envio-operador-v1.md` (PR #210) e
`docs/decisoes/prestacao-diagnostico-real-cli-v1.md` (PR #211) deixaram
a mesma pendência registrada duas vezes: existe hoje (a) validação pura
da seleção do operador contra um diagnóstico e (b) diagnóstico REAL
contra Airtable/Postgres/S3 — mas nada ligava a seleção VALIDADA à
composição de uma Ordem real (`OrdemDistribuicaoDocumental`), ainda em
modo sombra. Faltava fechar "seleção validada -> Ordem real composta em
sombra", com o operador conseguindo rodar isso de ponta a ponta sem
inventar nenhuma peça de infraestrutura nova.

## O que já existia (confirmado por leitura, não presumido)

Antes de escrever qualquer código, foi lido:
`magnata_os/orquestrador/wiring_prestacao_distribuicao_documental_shadow.py`,
`magnata_os/orquestrador/selecao_envio_operador_v1.py`,
`magnata_os/orquestrador/executar_prestacao_contato_ate_pending_shadow_v1.py`,
`magnata_os/orquestrador/resolver_parametros_ordem_prestacao_contato_v1.py`,
`magnata_os/orquestrador/prestacao_cliente_competencia_v1.py`,
`magnata_os/orquestrador/composicao_prestacao_real_v1.py`,
`scripts/selecao_envio_operador_cli.py`, `scripts/prestacao_diagnostico_real_cli.py`
e as duas suítes de teste já existentes
(`test_wiring_prestacao_selecao_operador_shadow.py`,
`test_integracao_prestacao_contato_ate_pending.py`).

Confirmado: `executar_prestacao_selecionada_ate_distribuicao_documental_shadow`
(PR #210, em `wiring_prestacao_distribuicao_documental_shadow.py`) **JÁ
FAZ** o elo completo — filtra os trios prontos pela `SelecaoEnvioOperador`
(`filtrar_trios_por_selecao_operador`, reaproveitando `validar_selecao_
contra_linhas_diagnostico`), isola erro de domínio por colaborador,
rejeita fail-closed preset divergente da exigência de assinatura do
operador (`PresetDaOrdemDivergeDaSelecaoOperador`) e materializa a Ordem
real via `materializar_prestacao_distribuicao_documental_shadow` até
PENDING, sem transporte. Isso já tinha 11 testes de integração cobrindo
1x1, Nx1, 1xN, com/sem assinatura, isolamento e idempotência
(`test_wiring_prestacao_selecao_operador_shadow.py`) — todos usando
resolvedores FAKE.

**A lacuna real, confirmada**: nada no repositório ligava essa função a
(a) um `ContextoComposicaoPrestacao` REAL (Airtable, via
`composicao_prestacao_real_v1.montar_contexto_prestacao`) e (b) um
resolvedor REAL de destinatário (`construir_resolvedor_parametros_
ordem_prestacao_contato_v1`, Contato Canônico de Colaborador V1,
Postgres). O módulo irmão que já faz essa mesma ligação
(`executar_prestacao_contato_ate_pending_shadow_v1.py`) só chama a
versão SEM curadoria (`executar_prestacao_ate_distribuicao_documental_
shadow`, "manda tudo que está PRONTO") — nunca a versão COM seleção do
operador. Não havia CLI nem função de composição juntando as 3 peças
(contexto real + resolvedor real + seleção real do operador).

Conclusão: a missão não precisou reconstruir a validação nem a
composição filtrada (ambas já prontas e testadas) — só precisava do elo
final entre elas e o mundo real, e de prova ponta a ponta desse elo.

## O que foi construído nesta missão

1. **`magnata_os/orquestrador/executar_prestacao_selecionada_contato_
   ate_pending_shadow_v1.py`** (novo módulo, ~180 linhas) — módulo
   irmão de `executar_prestacao_contato_ate_pending_shadow_v1.py`, com
   o MESMO aviso de segurança (autorização SHADOW sintética, nunca
   operacional de produção). Único código novo: liga o resolvedor real
   de destinatário (`construir_resolvedor_parametros_ordem_prestacao_
   contato_v1`, intocado) a `executar_prestacao_selecionada_ate_
   distribuicao_documental_shadow` (intocado, PR #210) — reexporta os 2
   compositores de ambiente já existentes
   (`compor_repositorio_contato_a_partir_do_ambiente`/`compor_chave_
   fernet_contato_a_partir_do_ambiente`), sem reimplementá-los.

2. **`scripts/prestacao_compor_ordem_selecionada_cli.py`** (nova CLI) —
   o terceiro passo do fluxo do operador: monta o contexto real
   (`--cliente`/`--competencia`, mesmo par de `prestacao_diagnostico_
   real_cli.py`), lê `--selecao` (MESMO formato JSON de `selecao_envio_
   operador_cli.py --selecao`), monta o resolvedor real com `--preset`/
   `--mensagem` (decisão de negócio, sempre explícita — mesma
   disciplina de `--ate-pending` em `prestacao_cliente_competencia_
   v1.py`) e chama o módulo do item 1. Imprime as Ordens compostas
   (`funcionario_id`, `event_id`, `estado_acao`, `assinatura_link`) e um
   aviso explícito de que nada foi enviado de verdade.

   **Limite conhecido, declarado**: assim como `--ate-pending` em
   `prestacao_cliente_competencia_v1.py`, esta CLI só aceita presets SEM
   assinatura (`PRESETS_SEM_ASSINATURA`) — presets com assinatura
   exigem compositores reais de `materializador`/`porta_assinatura` a
   partir do ambiente que ainda não existem neste repositório (mesmo
   gap já documentado naquele módulo, não recriado nem escondido aqui).
   Um item de `--selecao` com `exigir_assinatura_digital_e_comprovante:
   true` é isolado (fail-closed, via `PresetDaOrdemDivergeDaSelecaoOperador`,
   já existente) e não vira Ordem — os demais colaboradores da mesma
   seleção continuam normalmente.

## Fluxo completo de 3 passos que o operador agora consegue rodar

```bash
python scripts/prestacao_diagnostico_real_cli.py \
    --cliente recXXXXXXXX --competencia 2026-09 > diagnostico.json

# operador edita/cria selecao.json a partir do diagnostico.json:
# escolhe quais colaboradores recebem o quê, e se exige assinatura+comprovante

python scripts/selecao_envio_operador_cli.py \
    --diagnostico diagnostico.json --selecao selecao.json
# confirma que a seleção bate com o diagnóstico (SELECAO_VALIDA_PRONTA_PARA_ORDEM)

python scripts/prestacao_compor_ordem_selecionada_cli.py \
    --cliente recXXXXXXXX --competencia 2026-09 --selecao selecao.json \
    --preset DOCUMENTO_UNITARIO_SEM_ASSINATURA \
    --mensagem "Segue seu documento"
# compõe as Ordens reais, em modo sombra, paradas em PENDING
```

**Isso ainda não envia nada de verdade.** O terceiro comando compõe
Ordens reais que param em PENDING (modo sombra) — sujeitas às MESMAS 3
barreiras de sempre (`autorizar_transporte_real`,
`ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO`, `ORQUESTRADOR_DRY_RUN`) para
qualquer envio real. Nenhuma delas foi tocada, contornada ou aproximada
por este trabalho. Ligar essas Ordens PENDING a um envio real exige,
além dessas 3 barreiras, uma decisão humana real depois de
`WAITING_GATE` — trabalho de fase futura e distinta, fora de escopo
aqui (mesmo aviso já presente no módulo irmão desde antes desta missão).

## Testes

- `tests/test_scripts_prestacao_compor_ordem_selecionada_cli.py` (13
  testes novos), reaproveitando os mesmos fakes de
  `test_orquestrador_prestacao_cliente_competencia_v1.py`
  (`_LeitorAirtableFake`, `DependenciasPrestacaoReal` com repositórios
  em memória) mais `RepositorioContatoColaboradorEmMemoria`:
  - só os colaboradores selecionados viram Ordem, os demais ficam
    diagnosticados mas de fora (Nx1);
  - seleção vazia nunca toca o resolvedor nem cria Ordem;
  - colaborador sem contato cadastrado fica isolado (fail-closed),
    resto segue;
  - seleção pedindo assinatura com preset sem assinatura é isolada só
    para aquele colaborador, resto segue;
  - seleção apontando para necessidade não pronta é rejeitada com erro
    claro;
  - idempotência: rodar a mesma seleção 2 vezes não duplica ação
    (mesmo `event_id`, mesmas 2 linhas reais — texto + documento, Gate
    J1b);
  - `main()`: cliente inexistente, arquivo de seleção inexistente,
    preset inválido, configuração ausente — todos com erro claro e
    código de saída não-zero;
  - nenhuma chamada de rede real (instrumentado via `socket.socket.connect`);
  - `--help` executável como processo sem efeito colateral.
- Suíte completa do repositório: `3065 passed, 103 skipped, 0 failed`
  (skips pré-existentes, nada relacionado a esta mudança; baseline
  anterior era `3041 passed` antes do merge do PR #210, mais os testes
  já trazidos por ele — nenhuma regressão nova).
- Gates de governança locais (`scripts/ci/validate_governance.sh`):
  15/15 aprovados — branch
  `feat/prestacao-compor-ordem-selecionada-shadow-v1` adicionada a
  `AUTHORIZED_BRANCHES` em `.magnata/patterns.sh` (único ajuste feito
  nesse arquivo).

## Riscos/pendências declarados

- **Presets com assinatura continuam fora do alcance desta CLI** — ver
  "Limite conhecido, declarado" acima. Fechar isso exige compositores
  reais de `materializador`/`porta_assinatura` a partir do ambiente,
  que não existem hoje em nenhuma CLI deste repositório (mesmo gap já
  presente em `prestacao_cliente_competencia_v1.py --ate-pending`) —
  trabalho futuro separado, não escondido aqui.
- **Isso não liga a distribuição real** — as Ordens compostas por esta
  CLI param em PENDING, modo sombra, sujeitas às mesmas 3 barreiras de
  transporte real de sempre; nenhuma delas foi tocada, nenhum envio real
  foi feito ou testado. Uma decisão humana real depois de `WAITING_GATE`
  continua sendo pré-requisito de qualquer envio real, fora de escopo
  desta missão.
- Rodar `scripts/prestacao_compor_ordem_selecionada_cli.py` contra o
  ambiente real (Postgres/S3/Airtable de produção) é gate humano
  (CLAUDE.md §6/§12-I) — nenhuma execução real foi feita durante esta
  missão; toda validação usou fakes/mocks, nenhuma chamada de rede real
  foi feita (instrumentado e provado por teste dedicado).
- Tudo permanece em modo sombra: nenhuma linha nova chama transporte
  real, nenhuma das 3 barreiras foi tocada.
