# Seleção/Curadoria Humana de Envio (Operador) V1

## Necessidade de negócio (registrada por completo, não só na conversa)

Pedido literal do operador: "O que a gente quer é ter total autonomia
para escolher quais documentos enviar, para quantos colaboradores
enviar -- se envia um ou mais documentos para um ou mais colaboradores
-- se vai com assinatura digital e comprovante da assinatura ou não."

## Lacuna encontrada (investigação, antes de qualquer código)

- **Correção de escopo da missão**: os caminhos `magnata_os/
  classificacao/painel_diagnostico_prestacao.py` e `scripts/painel_
  diagnostico_prestacao_cli.py`, citados na missão como já existentes,
  **não existem** no repositório. `diagnosticar_prestacao`/
  `DiagnosticoPrestacao`/`DiagnosticoCliente`/`DiagnosticoNecessidade`/
  `SituacaoNecessidade` estão, de fato, dentro de `magnata_os/
  classificacao/composicao_ciclo_persistente_prestacao.py` (mesmo
  arquivo de `resultados_aquisicao_prontos_por_colaborador`). Nenhum
  painel/CLI de diagnóstico publicado existe hoje -- confirmado por
  leitura direta, registrado aqui em vez de presumido.
- **Contrato genérico de distribuição** (`OrdemDistribuicaoDocumental`,
  `magnata_os/orquestrador/wiring_distribuicao_documental_shadow.py`)
  já suporta 1..N documentos para 1 destinatário (`ItemDocumentoOrdem`
  em tupla + política `DOCUMENTOS_SEPARADOS`/`AGRUPADO_1_LINK`), mas é,
  por contrato, de **destinatário único** por Ordem -- N destinatários
  sempre são N Ordens. A obrigação de assinatura/comprovante já existe
  como par de campos booleanos sempre iguais entre si
  (`exigir_assinatura`/`exigir_comprovante`) em todo preset de
  `politica_preset_distribuicao_documental._PRESETS_V1` -- vocabulário
  **reaproveitado**, nunca duplicado, pela seleção do operador (1 único
  campo combinado).
- **A lacuna real**: `resultados_aquisicao_prontos_por_colaborador` +
  `executar_prestacao_ate_distribuicao_documental_shadow` (`wiring_
  prestacao_distribuicao_documental_shadow.py`) fazem TODA necessidade
  `PRONTO` de um cliente/competência virar Ordem automaticamente, sem
  nenhuma seleção humana no meio -- confirmado lendo o corpo da função
  (itera todos os trios devolvidos, sem nenhum filtro de curadoria).
  Essa função continua, hoje, só "script manual, nunca chamado pelo
  Cron Job" (docstring de `distribuir_documento_v1.py`/`executar_
  prestacao_contato_ate_pending_shadow_v1.py`) -- nunca esteve wireada
  em produção real.

## O que foi construído

1. **Contrato + validação pura** --
   `magnata_os/orquestrador/selecao_envio_operador_v1.py`:
   - `ItemSelecaoEnvioOperador` (cliente_id, competencia_id,
     colaborador_id, tipos_documentais: 1..N, `exigir_assinatura_
     digital_e_comprovante: bool`) e `SelecaoEnvioOperador` (tupla de
     itens; vazia = seleção explicitamente ausente).
   - `validar_selecao_contra_diagnostico(diagnostico, selecao)`:
     função pura que recebe o `DiagnosticoPrestacao` já existente e
     devolve só os itens validados -- fail-closed (erro claro, nunca
     silencioso) se a seleção apontar para cliente/competência
     inexistente, colaborador/tipo_documental inexistente, ou uma
     necessidade que não está `PRONTO`.
   - Núcleo puro reaproveitável, `validar_selecao_contra_linhas_
     diagnostico`, opera sobre as MESMAS colunas que `DiagnosticoPrestacao.
     como_dict()` exporia (cliente_id/competencia_id/tipo_documental/
     colaborador_id/situacao) -- 1 única regra, usada tanto contra as
     dataclasses em memória quanto contra o diagnóstico já em JSON
     (CLI).

2. **Filtro real na composição da Ordem** --
   `magnata_os/orquestrador/wiring_prestacao_distribuicao_documental_
   shadow.py` (aditivo; `executar_prestacao_ate_distribuicao_
   documental_shadow`, já existente, permanece **INTOCADA**, zero
   regressão):
   - `filtrar_trios_por_selecao_operador(trios, selecao_operador)`:
     filtra a saída de `resultados_aquisicao_prontos_por_colaborador`
     para só os trios (cliente+competência+colaborador) e só os
     `tipo_documental` que o operador selecionou.
   - `executar_prestacao_selecionada_ate_distribuicao_documental_
     shadow(...)`: novo composition root, mesmo shape de `executar_
     prestacao_ate_distribuicao_documental_shadow` + `selecao_operador`
     obrigatório. **Padrão seguro por default**: `selecao_operador.
     itens == ()` devolve `()` imediatamente, sem tocar nenhuma
     dependência -- nunca "sem seleção, manda tudo". Mesma disciplina
     de isolamento por colaborador (erro de domínio de 1 nunca
     contamina os demais) e mesma garantia de modo sombra (zero import
     de `porta_execucao`/transporte real/barreiras) da função
     original.
   - `PresetDaOrdemDivergeDaSelecaoOperador`: fail-closed adicional --
     se `resolver_parametros_ordem` devolver um `preset_id` cujo
     `exigir_assinatura`/`exigir_comprovante` não bate com o
     `exigir_assinatura_digital_e_comprovante` que o operador escolheu
     para aquele colaborador, a Ordem daquele colaborador é rejeitada
     (isolada, não derruba os demais) em vez de silenciosamente sair
     diferente do que o operador pediu. A escolha de QUAL `preset_id`
     satisfaz a decisão do operador continua sendo do `resolver_
     parametros_ordem` (mesmo ponto de extensão já existente) -- este
     módulo nunca inventa uma tabela paralela de mapeamento preset<->
     booleano.

3. **CLI** -- `scripts/selecao_envio_operador_cli.py`:
   - Lê `--diagnostico` (JSON no formato de `DiagnosticoPrestacao.
     como_dict()`) e `--selecao` (JSON da seleção do operador), valida
     a segunda contra a primeira e imprime o resultado -- mesmo
     espírito de `scripts/prestacao_readiness_shadow_real.py`
     (script manual, leitura local, nenhuma autenticação/rota nova).
   - **Limite conhecido, declarado, não escondido**: esta CLI NÃO chama
     `executar_prestacao_selecionada_ate_distribuicao_documental_
     shadow` (a composição real da Ordem), porque a composição real de
     `ContextoComposicaoPrestacao` a partir de fontes reais (Airtable)
     **ainda não existe** em nenhum lugar deste repositório -- gap já
     documentado em `magnata_os/orquestrador/executar_prestacao_
     contato_ate_pending_shadow_v1.py` (linhas 69-72), não recriado nem
     contornado aqui. Ligar esta seleção à composição real da Ordem
     contra dados reais é a próxima etapa, quando essa composição real
     existir -- pendência explícita, não escondida como "pronto".

## Como o operador usa isso na prática (hoje)

1. Obtém um `DiagnosticoPrestacao.como_dict()` (de onde quer que hoje
   produza um -- teste, script interno, ou uma futura exposição de
   `diagnosticar_prestacao`) e salva como `diagnostico.json`.
2. Escreve `selecao.json` com os pacotes que quer montar: para cada
   colaborador que vai receber algo, 1 item com `cliente_id`/
   `competencia_id`/`colaborador_id`, a lista de `tipos_documentais`
   (1 = documento único, N = pacote) e `exigir_assinatura_digital_e_
   comprovante` (true/false).
3. Roda:
   ```
   python scripts/selecao_envio_operador_cli.py \
       --diagnostico diagnostico.json --selecao selecao.json
   ```
4. Recebe `SELECAO_VALIDA_PRONTA_PARA_ORDEM` (com os itens confirmados)
   ou um erro claro (`SELECAO_REJEITADA: ...`) explicando exatamente o
   que não bate -- necessidade não `PRONTO`, colaborador/tipo
   inexistente, etc.
5. **Isso não envia nada de verdade.** Virar Ordem de fato (ainda em
   modo sombra, parando em PENDING) exige chamar `executar_prestacao_
   selecionada_ate_distribuicao_documental_shadow` com um `contexto`
   real -- dependência que só existirá quando a composição real de
   `ContextoComposicaoPrestacao` (Airtable) for construída, em missão
   futura e separada. Depois disso, a Ordem resultante segue exatamente
   sujeita às mesmas 3 barreiras de sempre (`autorizar_transporte_real`,
   `ORQUESTRADOR_TRANSPORTE_REAL_AUTORIZADO`,
   `ORQUESTRADOR_DRY_RUN`) para virar envio real -- nenhuma delas foi
   tocada, contornada ou aproximada por este trabalho.

## Testes

- `test_selecao_envio_operador_v1.py` (14 testes): contrato,
  validação pura, todas as combinações pedidas (1x1, Nx1, 1xN,
  assinatura true/false lado a lado, rejeição de necessidade não
  pronta, rejeição de colaborador/documento inexistente, seleção vazia
  = sem Ordem, idempotência).
- `test_wiring_prestacao_selecao_operador_shadow.py` (11 testes):
  integração real com `filtrar_trios_por_selecao_operador`/`executar_
  prestacao_selecionada_ate_distribuicao_documental_shadow` --
  chegada a PENDING sem e com assinatura, 1 documento para N
  destinatários produzindo N Ordens (com um colaborador não
  selecionado ficando de fora, provando "resto continua diagnosticado
  mas não vira Ordem"), preset divergente da seleção isolado por
  colaborador, seleção vazia = zero Ordem, idempotência (2 chamadas =
  mesmo `event_id`/`acao_execucao_id`).
- Suíte completa do repositório: `3041 passed, 103 skipped, 0 failed`
  (skips pré-existentes, nada relacionado a esta mudança).
- Gates de governança locais (`scripts/ci/validate_governance.sh`):
  15/15 aprovados -- branch `feat/selecao-envio-operador-v1` adicionada
  a `AUTHORIZED_BRANCHES` em `.magnata/patterns.sh` (único ajuste feito
  nesse arquivo).

## Riscos/pendências declarados

- A interface hoje é CLI + 2 arquivos JSON, **nunca uma tela** -- uma
  tela de seleção no painel (ainda não publicado) é trabalho futuro
  separado, fora de escopo aqui.
- A CLI só valida/prevê a seleção contra um diagnóstico já fornecido;
  não compõe `ContextoComposicaoPrestacao` real nem chama a composição
  real da Ordem -- porque essa composição real (Airtable) não existe
  ainda em nenhum lugar do repositório (gap pré-existente, não criado
  por esta missão).
- `executar_prestacao_ate_distribuicao_documental_shadow` (a função
  "manda tudo que está PRONTO") continua existindo, intocada, para
  quem precisar dela sem curadoria (prova de ponta a ponta, scripts
  internos) -- não foi removida nem teve o comportamento alterado. A
  partir desta missão, `executar_prestacao_selecionada_ate_
  distribuicao_documental_shadow` é o caminho recomendado para qualquer
  fluxo real de distribuição a colaboradores, porque é o único que
  respeita a curadoria humana.
- Tudo permanece em modo sombra: nenhuma linha nova chama transporte
  real, nenhuma das 3 barreiras foi tocada.
