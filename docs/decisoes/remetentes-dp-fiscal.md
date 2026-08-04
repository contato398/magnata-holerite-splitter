# Decisão — Remetentes monitorados de e-mail (DP e Fiscal)

**Data:** 2026-08-03
**Branch:** `fix/remetente-dp-email-intake`
**Status:** implementado em branch, aguardando autorização de publicação em produção

## Contexto

`apps_script_email_intake.gs` mantém uma lista de remetentes confiáveis
(`REMETENTES_CONFIAVEIS`) cujos e-mails são processados automaticamente
sem exigir label manual. O endereço configurado para Departamento
Pessoal, `dp.contabilidade1@hotmail.com`, não correspondia ao endereço
real usado pela contabilidade, `dpessoal.contabilidade1@hotmail.com`.

## Evidência

- E-mail "MAGNATA - HOLERITE E EXTRATO MENSAL 07/2026"
  (message_id `19fb9a9c39f77f8b`) confirmado no Gmail, remetente
  `dpessoal.contabilidade1@hotmail.com`, com os labels `CATEGORY_PERSONAL`,
  `Label_5`, `INBOX` — sem `Processado-Render`.
- Ausente em Emails Savian (Airtable), verificado manualmente por
  MESSAGE ID e por nome de arquivo.
- Holerites de Junho/2026 concluídos no Airtable; Julho/2026 ausente —
  isola a falha na etapa de captura (Apps Script), não no
  processamento (`app.py`).
- Backlog preliminar (evidência externa, não auditada item a item):
  ≥44 e-mails, ~120 PDFs, 09/06/2026 a 31/07/2026, todos sem
  `Processado-Render`.

## Causa

- Erro no repositório (`dp.contabilidade1@hotmail.com` em
  `REMETENTES_CONFIAVEIS`): confirmado por leitura direta do código.
- Compatibilidade desse erro com a falha observada: confirmada — o erro
  explica integralmente a falha observada.
- Identidade entre o código deste repositório e o Apps Script publicado
  em produção: **não verificada** nesta branch — não houve acesso ao
  projeto publicado.
- Causa em produção: hipótese principal, fortemente sustentada,
  dependente de comparação direta com o Apps Script publicado antes da
  publicação desta correção (Fase 0 do procedimento operacional,
  descrita abaixo).

## Decisão

Substituído `dp.contabilidade1@hotmail.com` por
`dpessoal.contabilidade1@hotmail.com` em `REMETENTES_CONFIAVEIS`
(`apps_script_email_intake.gs`, linha 37). Substituição, não adição.
`dpfiscal.contabilidade2@hotmail.com` permanece inalterado.

Introduzida capacidade administrativa mínima para reprocessamento
pontual por `MESSAGE ID`, sem gatilho, sem exposição automática:

- `verificarMessageIdAdministrativo()` — diagnóstico somente leitura,
  sem parâmetros, lê `ADMIN_MESSAGE_ID`; nunca chama Render, Airtable
  ou aplica label.
- `processarMensagemPorId_(messageId, dryRun)` — núcleo reutilizável,
  processa exatamente uma mensagem, nunca enumera outras mensagens da
  thread, nunca aplica label.
- `executarProcessamentoAdministrativo()` — executor sem parâmetros,
  chamável pelo editor (o botão Executar do Apps Script não aceita
  argumentos), controlado por Script Properties
  (`ADMIN_MESSAGE_ID`, `ADMIN_DRY_RUN`, `ADMIN_EXECUTION_ENABLED`),
  protegido por `LockService` compartilhado com `processarEmails()` e
  por checagem de gatilho ativo.

`ADMIN_APPLY_PROCESSED_LABEL` **não foi introduzida** nesta branch —
decisão explícita: o caminho administrativo nunca aplica
`Processado-Render` automaticamente, em nenhuma condição. A decisão de
marcar uma thread como processada, depois de reconciliar com
`verificarMessageIdAdministrativo()` (que também lista PDFs de outras
mensagens da mesma thread), é sempre humana e manual, feita
diretamente no Gmail.

## Posição na arquitetura do Magnata OS

Módulo de Ingestão — corrige o contrato de remetentes autorizados desse
módulo. Não altera Classificação, Transformação, Negócio, Entrega ou
Auditoria. É estabilização operacional, não decisão arquitetural nova.
Remetentes hardcoded em `REMETENTES_CONFIAVEIS` não representam a
arquitetura definitiva — evolução futura deve centralizar isso em
configuração controlada (pendência registrada, não implementada aqui).
`processarMensagemPorId_`/`executarProcessamentoAdministrativo` são
capacidade administrativa segura da esteira, deliberadamente sem visão
da thread inteira — não parte do fluxo automático.

## Comparação do fluxo automático — antes e depois

| | Antes | Depois |
|---|---|---|
| Condição de label | `code === 200 && !DRY_RUN` | `!DRY_RUN && resultado.aplicarLabelPermitido`, com `aplicarLabelPermitido = (httpCode === 200 && !dryRun)` |
| Corpo JSON válido e consistente | rotula | rotula — **idêntico** |
| Corpo malformado/inconsistente com HTTP 200 | rotulava mesmo assim (nunca inspecionava o corpo) | **não rotula** — única diferença intencional, motivada por segurança |
| Nº de chamadas ao Render | 1 por mensagem com ≥1 PDF | idêntico |
| Concorrência | inexistente | `LockService` compartilhado com o executor administrativo |

Nenhuma nova política de "sucesso parcial" foi introduzida no fluxo
automático — `sucessoParcial`/`pendencia` continuam informativos, nunca
usados para decidir o label ali.

## Achado prioritário fora de escopo — registrado

**"Ingestão retomável e reconciliável por anexo."** `Emails Savian` é
criado antes da conclusão do loop de anexos (`app.py:5096-5108`); não
existe `@app.errorhandler` no `app.py`, então uma falha no meio do loop
produz HTTP 500 sem corpo JSON estruturado, deixando anexos já gravados
sem rollback e o `message_id` "gasto" no dedup — uma nova tentativa do
mesmo e-mail encontra `duplicado_message_id` e nunca retoma os anexos
que faltaram.

Proposta futura (não implementada nesta branch) deve conter: estados do
e-mail e estados individuais por anexo; contagem de tentativas; erro
por anexo; retomada de anexos incompletos sem reprocessar os já
concluídos; idempotência por hash (já existente, reaproveitável);
reconciliação Gmail × Emails Savian × Arquivos × Processar Arquivos;
nenhuma exclusão de registro em nenhum cenário.

Classificação: risco arquitetural prioritário. Não implementado nesta
branch. Não bloqueia o teste administrativo isolado (que já é seguro
por desenho, mesmo com essa fragilidade presente no backend).
**Bloqueia a reativação definitiva do gatilho automático** até decisão
posterior — reativar sem resolver isso reexpõe o backlog inteiro ao
mesmo risco de estado parcial preso.

## Fora de escopo desta branch

Alterações em `app.py`; retomada automática por anexo; correção
transacional do backend; tratamento de RAR (endpoint
`/email/alerta-formato-invalido` não conectado ao `.gs` — achado
registrado em rodada anterior, não corrigido aqui); centralização
definitiva dos remetentes; painel administrativo; processamento do
backlog; nova política ampla de labels; alterações de schema do
Airtable; deploy; publicação do Apps Script.

## Procedimento operacional para a fase seguinte (não executado nesta branch)

**Fase 0 — comparação:** comparar manualmente o Apps Script publicado
com este arquivo antes de colar a correção; registrar qualquer
diferença encontrada; não sobrescrever sem essa revisão.

**Fase 1 — confirmação do ID:** `ADMIN_MESSAGE_ID = 19fb9a9c39f77f8b`,
rodar `verificarMessageIdAdministrativo()`; zero chamada ao Render,
zero label, zero Airtable.

**Fase 2 — dry-run:** `ADMIN_DRY_RUN = true`,
`ADMIN_EXECUTION_ENABLED = true`, rodar
`executarProcessamentoAdministrativo()`; revisar log e resultado
estruturado; confirmar autodesabilitação da flag; parar.

**Fase 3 — autorização:** apresentar evidências da Fase 2; aguardar
autorização humana expressa antes de qualquer execução real.

**Fase 4 — execução real isolada:** gatilho automático continua
desligado; `ADMIN_DRY_RUN = false`, `ADMIN_EXECUTION_ENABLED = true`
reabilitado explicitamente; reconciliar Gmail × Airtable × resultado
estruturado; qualquer resultado inesperado vai para Pendências/Revisar,
nunca excluído.

**Fase 5 — marcação e retomada:** decisão humana separada sobre aplicar
`Processado-Render` manualmente; auditoria do backlog antes de
considerar reativar o gatilho; reativação só mediante autorização
posterior e separada.

## Autorização de publicação em produção

Pendente.
