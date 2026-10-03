# Diagnóstico REAL da Prestação -- elo entre a composição real e a seleção do operador (V1)

## Necessidade de negócio (registrada por completo, não só na conversa)

O PR #210 (`feat/selecao-envio-operador-v1`, aberto -- ver "Estado desta
branch em relação ao PR #210" abaixo) construiu `magnata_os/orquestrador/
selecao_envio_operador_v1.py` (contrato `SelecaoEnvioOperador`) e
`scripts/selecao_envio_operador_cli.py`: uma CLI que recebe um
`diagnostico.json` (montado manualmente) + uma seleção do operador, e
devolve os itens selecionados válidos.

`magnata_os/orquestrador/composicao_prestacao_real_v1.py` já tem
`compor_dependencias_a_partir_do_ambiente()` -- monta
`DependenciasPrestacaoReal` real, lendo Airtable de verdade via
`LeitorAirtableComCache` (`AIRTABLE_API_KEY`), e as demais dependências
reais (Postgres, S3, motor OCR). `magnata_os/orquestrador/
prestacao_cliente_competencia_v1.py` (`executar_prestacao_cliente_
competencia`) já usa essas dependências reais para rodar
`diagnosticar_prestacao` de verdade contra um cliente/competência real.

**A lacuna**: a CLI de seleção de envio exigia que o operador montasse
`diagnostico.json` NA MÃO. Faltava uma forma de pegar o diagnóstico REAL
(contra Airtable de verdade) de um cliente/competência específico, e
alimentar isso na seleção -- sem montar JSON manualmente.

## O que foi construído

`scripts/prestacao_diagnostico_real_cli.py` -- nova CLI, reaproveitando
sem duplicar:

- `compor_dependencias_a_partir_do_ambiente()` (`composicao_prestacao_
  real_v1.py`) -- as mesmas dependências reais que `prestacao_cliente_
  competencia_v1.py` já usa;
- `montar_contexto_prestacao(...)` (`composicao_prestacao_real_v1.py`) --
  o mesmo contexto REAL da Prestação para 1 cliente/1 competência (J4);
- `diagnosticar_prestacao(contexto)` (`composicao_ciclo_persistente_
  prestacao.py`) -- o núcleo já existente, somente leitura.

A função nova, `executar_diagnostico_real`, monta essas 3 peças e devolve
`DiagnosticoPrestacao.como_dict()` **sem nenhum campo extra**. `main`
lê `--cliente`/`--competencia` (mesmo formato de `prestacao_cliente_
competencia_v1.py`) e imprime esse dicionário como JSON.

### Por que não foi preciso adaptar nenhum formato

O contrato `DiagnosticoPrestacao.como_dict()` já produz exatamente:

```json
{
  "competencia_base": "2026-09",
  "clientes": [
    {
      "cliente": "cliente-1", "competencia": "2026-09",
      "estado_pacote": "PRONTO", "ordem_pronta": true,
      "necessidades": [
        {"cliente": "cliente-1", "competencia": "2026-09",
         "tipo_documental": "Holerite", "colaborador": "colab-1",
         "situacao": "PRONTO", "documentos_avaliados": ["doc-1"],
         "documentos_elegiveis": ["doc-1"], "localizacao": null}
      ]
    }
  ]
}
```

E `selecao_envio_operador_cli._linhas_do_diagnostico_json` (o lado que lê
`--diagnostico`) só consome `clientes[*].necessidades[*]` com as chaves
`cliente`/`competencia`/`tipo_documental`/`colaborador`/`situacao` --
exatamente as mesmas chaves. Confirmado lendo os dois lados (não
presumido): nenhuma mudança de contrato foi necessária dos dois lados,
nenhuma adaptação de serialização precisou ser inventada no script novo
além de "imprimir `como_dict()` direto".

**Por que não reaproveitar `executar_prestacao_cliente_competencia`
diretamente**: essa função empacota o diagnóstico dentro de um relatório
maior (`modo`, `coleta`, `busca_incompleta`, `ordens`...), porque cobre
também `--ate-pending` e coleta de e-mail -- fora do escopo desta CLI
(que é só diagnóstico). Chamar `montar_contexto_prestacao` +
`diagnosticar_prestacao` direto, o mesmo par que essa função já chama por
baixo, devolve só o formato puro que `selecao_envio_operador_cli.py`
espera, sem nenhum campo extra a ignorar.

## Fluxo completo ponta a ponta que o operador agora consegue rodar

```bash
python scripts/prestacao_diagnostico_real_cli.py --cliente <id> --competencia <AAAA-MM> > diagnostico.json
# operador edita/cria selecao.json escolhendo o que enviar
python scripts/selecao_envio_operador_cli.py --diagnostico diagnostico.json --selecao selecao.json
```

**Isso ainda não envia nada de verdade nem cria Ordem real** -- é
diagnóstico real (contra Airtable/Postgres/S3 de produção, somente
leitura) + validação pura da seleção do operador contra esse diagnóstico.
`prestacao_diagnostico_real_cli.py` nunca grava nada (mesma garantia de
`diagnosticar_prestacao`/`_contexto_somente_leitura`: nenhum Documento,
blob ou evento de histórico real é criado) e nunca chama transporte --
não importa `porta_execucao`, `transporte_real_habilitado`, nem qualquer
adapter de escrita no Airtable. `selecao_envio_operador_cli.py`, por sua
vez, também não chama transporte nem cria Ordem -- só valida a seleção.

## Decisão de escopo: diagnóstico real, não composição de Ordem real (com justificativa)

A missão permitia estender até a composição real de Ordem em modo sombra
**se** isso fosse uma extensão pequena e segura, e pedia para registrar
qual caminho foi seguido e por quê caso a investigação mostrasse o
contrário. Decisão: **ficar só no diagnóstico real** (este documento),
sem ligar a seleção validada à composição real da Ordem. Motivos,
encontrados lendo o código antes de decidir:

1. **Materializar uma Ordem real (ainda que parando em PENDING) exige
   decisões de negócio que este script não deveria tomar por conta
   própria** -- preset e mensagem, exatamente como `prestacao_cliente_
   competencia_v1.py` já exige (`--preset`/`--mensagem`, "decisão de
   negócio -- sempre informados por quem roda, sem default"). O caminho
   de composição real de Ordem (`executar_prestacao_selecionada_ate_
   distribuicao_documental_shadow`, em `wiring_prestacao_distribuicao_
   documental_shadow.py`) tem essa mesma exigência, mais a necessidade de
   compor `ParametrosOrdemPrestacao` e, para presets com assinatura,
   depender de `materializador`/`porta_assinatura` que `prestacao_
   cliente_competencia_v1.py` explicitamente deixa de fora da V1
   (`PRESETS_SEM_ASSINATURA`, fail-closed para qualquer outro preset).
2. **É uma mudança funcional material, não um "só ler diagnóstico real"**
   -- construir `SelecaoEnvioOperador` a partir de `ItemSelecaoValidada`
   (que já existe, do lado do PR #210) e alimentá-la num `contexto` real
   junto com presets/mensagem é uma nova superfície de decisão
   operacional (quais presets aceitar, como validar preset x seleção do
   operador -- `PresetDaOrdemDivergeDaSelecaoOperador` já existe para
   isso, mas quem resolve o `preset_id` a partir da escolha do operador
   ainda precisa ser decidido/testado ponta a ponta), não uma extensão de
   "leitura" de baixo risco como esta CLI de diagnóstico.
3. A missão anterior (PR #210) já registrou essa mesma pendência
   (`docs/decisoes/selecao-envio-operador-v1.md`, seção "Riscos/pendências
   declaradas"): "a CLI só valida/prevê a seleção contra um diagnóstico
   já fornecido; não compõe `ContextoComposicaoPrestacao` real nem chama a
   composição real da Ordem". Esta missão fecha a PRIMEIRA metade dessa
   pendência (o diagnóstico real agora existe e é fácil de obter) --
   a segunda metade (seleção validada -> Ordem real composta, ainda em
   sombra) continua pendência explícita, agora **menor** (só falta ligar
   presets/mensagem à seleção validada, já com o diagnóstico e o contexto
   reais prontos), mas ainda fora do escopo de "ler diagnóstico real sem
   montar JSON na mão".

## Estado desta branch em relação ao PR #210

Esta branch (`feat/prestacao-diagnostico-real-cli-v1`) foi criada a
partir de `main` atualizada. Na data desta missão, o PR #210
(`selecao_envio_operador_v1.py`/`selecao_envio_operador_cli.py`) ainda
**não estava mesclado em `main`** -- estava aberto, com
`mergeable_state: blocked`. `scripts/prestacao_diagnostico_real_cli.py`
não depende de nenhum código do PR #210 (só de peças já em `main`:
`composicao_prestacao_real_v1.py`, `composicao_ciclo_persistente_
prestacao.py`) -- funciona hoje, independente da ordem de merge. O fluxo
de 2 passos documentado acima só fica completo na prática quando o PR
#210 também estiver em `main` (o segundo comando, `selecao_envio_
operador_cli.py`, não existe fora daquele branch/PR ainda).

## Testes

`tests/test_scripts_prestacao_diagnostico_real_cli.py` (11 testes),
reusando os mesmos fakes de `test_orquestrador_prestacao_cliente_
competencia_v1.py` (`_LeitorAirtableFake`, repositórios em memória --
nenhuma chamada de rede real):

- o diagnóstico real produzido tem exatamente as chaves que
  `DiagnosticoPrestacao.como_dict()` define (nenhum campo extra de
  `modo`/`coleta`) e bate, linha a linha, com o formato que a extração de
  `selecao_envio_operador_cli.py` já lê;
- nada é gravado nos repositórios reais (somente leitura);
- cliente inexistente/inativo e competência mal formada falham com erro
  explícito (`ClienteNaoAtivo`/`ValueError`), nunca silenciosamente;
- `--cliente`/`--competencia` obrigatórios e competência precisa ser
  `AAAA-MM` (`_parse_args`);
- `main`: código de saída 0 com JSON correto no caminho feliz; código 2 e
  mensagem clara (`CLIENTE_NAO_ENCONTRADO_OU_INATIVO`,
  `CONFIGURACAO_AUSENTE`) nos caminhos de erro; `fechar_dependencias`
  sempre chamado (inclusive em erro);
  configuração ausente (`AIRTABLE_API_KEY`) nunca tenta abrir conexão
  real;
- teste dedicado que instrumenta `socket.socket.connect` para provar que
  nenhuma chamada de rede real acontece durante a suíte;
- `--help` é invocável como processo sem efeito colateral (só formação de
  `argparse`).

Suíte completa do repositório: `3027 passed, 103 skipped, 0 failed`
(skips pré-existentes, nada relacionado a esta mudança).

Gates de governança locais (`scripts/ci/validate_governance.sh`): branch
`feat/prestacao-diagnostico-real-cli-v1` adicionada a
`AUTHORIZED_BRANCHES` em `.magnata/patterns.sh` (único ajuste feito nesse
arquivo).

## Riscos/pendências declaradas

- **Composição real de Ordem a partir da seleção validada continua fora
  de escopo** -- ver "Decisão de escopo" acima. Trabalho futuro separado.
- **O fluxo de 2 passos só fica utilizável ponta a ponta quando o PR
  #210 também estiver em `main`** (hoje aberto, `mergeable_state:
  blocked`) -- `scripts/selecao_envio_operador_cli.py` não existe fora
  daquele branch ainda.
- Rodar `scripts/prestacao_diagnostico_real_cli.py` contra o ambiente
  real (Postgres/S3/Airtable de produção) é gate humano (CLAUDE.md
  §6/§12-I) -- nenhuma execução real foi feita durante esta missão; toda
  validação usou fakes/mocks, nenhuma chamada de rede real foi feita.
- Tudo permanece em modo sombra: nenhuma linha nova chama transporte
  real, nenhuma das 3 barreiras foi tocada.
