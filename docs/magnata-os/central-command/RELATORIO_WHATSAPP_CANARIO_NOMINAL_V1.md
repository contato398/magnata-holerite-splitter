# Relatório — WhatsApp Canário Nominal V1 (Etapa C)

Data: 2026-09-14
Base: `origin/main` @ `439ec220ca5ca225496f88351aecb81eb5fac7b7` (Etapas A e B já mescladas, PRs #162 e #163)
Branch: `fix/composicao-canario-nominal-v2`
Commit funcional: `910aa0f`

## Objetivo

Compor o transporte WhatsApp real do Orquestrador a partir do cliente
Evolution já extraído (Etapa A, `magnata_os/orquestrador/adapters/evolution_cliente_legado.py`)
e disponibilizar um script one-shot de canário nominal para o primeiro
disparo controlado de WhatsApp + Assinatura V1 — sem habilitar
transporte real nesta etapa e sem tocar `app.py`.

## Decisão implementada

Dois módulos novos, nenhuma alteração em código já existente:

1. `magnata_os/orquestrador/composicao_transporte_evolution_legado.py`
   — único ponto do repositório autorizado a construir
   `TransporteEvolutionLegado` com as callables reais do cliente
   Evolution extraído. Não duplica cliente HTTP, autenticação nem
   payload; não decide sozinho sobre transporte real.
2. `magnata_os/orquestrador/executar_canario_v1.py` — script manual,
   nunca referenciado por cron/scheduler, que executa o canário
   nominal sobre exatamente 1 par `(event_id, preview_id)`.

## Invariantes de segurança preservados

- **Composição, nunca reimplementação.** `compor_transporte_evolution_real()`
  só monta `TransporteEvolutionLegado` com as 3 callables já extraídas
  (`_evolution_enviar_texto`/`_evolution_enviar_video`/`_evolution_enviar_documento`);
  nenhuma lógica HTTP, endpoint, autenticação ou payload é duplicada.
- **Nenhuma fila, scheduler ou motor novo.** O canário nunca chama
  `listar_pares_elegiveis` (mecanismo de descoberta ampla do ciclo de
  produção) — opera exclusivamente sobre o par nominal fixado pelas
  constantes `EVENT_ID_CANARIO_NOMINAL`/`PREVIEW_ID_CANARIO_NOMINAL`
  (`None` por padrão, fail-closed).
- **Reivindicação/execução 100% legada.** Reaproveita
  `executar_proxima_acao_persistente` (que já delega a
  `reivindicar_acao_exata`, CAS por `acao_execucao_id`) sem nenhuma
  lógica de lock/allowlist paralela.
- **Limite explícito de ações.** `LIMITE_ACOES_POR_EXECUCAO = 5`; o
  loop nunca excede esse limite.
- **Terminal correto.** O ciclo só é considerado `todas_sucedidas`
  quando termina de forma limpa via `SEM_ACAO_ELEGIVEL` **e** toda
  ação efetivamente tentada terminou `SUCCEEDED`. Atingir o limite de
  ações sem nunca ver `SEM_ACAO_ELEGIVEL` **nunca** conta como
  sucesso — condição corrigida e travada por teste de regressão
  (achado MÉDIO da Ultrareview multiagente original, ver Auditoria
  abaixo).
- **Sem retry cego.** `ENVIO_EXTERNO_INCERTO` (`ClasseFalha`) nunca é
  retentado automaticamente dentro do loop — qualquer resultado
  diferente de `SUCCEEDED`/`SEM_ACAO_ELEGIVEL` interrompe o
  processamento do par imediatamente.
- **As três barreiras de transporte real continuam obrigatórias e
  inalteradas.** `autorizacao_transporte_real.py` não foi tocado; a
  única barreira "estrutural" adicional é a constante literal
  `AUTORIZACAO_ESTRUTURAL_CANARIO_V1 = True` deste script (revisável
  só via PR), que nunca substitui as barreiras 2 (env var exata) e 3
  (veto dry-run) — ambas continuam decididas exclusivamente dentro de
  `compor_porta_execucao`. `ciclo_producao_v1.main()` (alvo do cron)
  continua com `autorizar_transporte_real=False`, inalterado.
- **Esta etapa não habilita transporte real.** Nenhum valor real foi
  atribuído a `EVENT_ID_CANARIO_NOMINAL`/`PREVIEW_ID_CANARIO_NOMINAL`;
  o script falha fechado (`CanarioNaoConfiguradoError`) enquanto
  permanecerem `None`.
- **Fronteiras de domínio preservadas.** A correlação ação→assinatura
  usa exclusivamente `observador_assinatura.observar_e_registrar_transicao`
  e `RepositorioConclusaoObrigacaoAssinaturaPostgres` — nenhuma regra
  de negócio de obrigação de assinatura/Prestação foi duplicada ou
  movida para o módulo de WhatsApp/canário. O canário opera somente
  sobre IDs opacos (`event_id`, `preview_id`, `acao_execucao_id`) —
  nenhum dado pessoal (CPF, nome real) é lido ou registrado.

## Compatibilidade com o legado

`app.py` não é tocado nem importado por nenhum dos dois módulos novos
(confirmado: diff vazio em `app.py` no commit `910aa0f`). Nenhuma
migration, `render.yaml` ou asset de marca foi alterado.

## Auditoria — Ultrareview multiagente read-only (4 agentes, mesmo snapshot git)

- **Agente A (Orquestrador/Evolution):** APROVÁVEL, sem achados —
  confirmou as 3 barreiras intactas e nenhum bypass de
  `ExecutorEvolutionLegado` fora de `compor_porta_execucao`.
- **Agente B (Canário/idempotência):** APROVÁVEL, sem achados —
  confirmou seleção exata por par, CAS reaproveitado, limite de
  ações, ausência de retry cego, e o fix do achado MÉDIO sobre
  `todas_sucedidas` corretamente implementado e testado.
- **Agente C (Assinatura/correlação):** APROVÁVEL, com 2 achados
  **BAIXO** (pendências de teste, não bugs — ver seção abaixo).
- **Agente D (Governança/testes/legado):** APROVÁVEL, com 1 achado
  **MÉDIO** — ausência de registro documental formal deste módulo
  (o motivo direto deste próprio relatório).

## Validação técnica

- 18/18 testes específicos da Etapa C verdes
  (`test_composicao_transporte_evolution_legado.py` +
  `test_executar_canario_v1.py`).
- Suíte geral: 2497 passed, 77 skipped, 0 falhas — sem regressão.
- Governança: 15/15 gates aprovados.
- `git diff --check` limpo; scan de segredo/PII sem ocorrência.
- Mutation testing do caso `todas_sucedidas`: reintroduzida a
  condição antiga (sem exigir término via `SEM_ACAO_ELEGIVEL`),
  confirmado que quebra exatamente
  `test_limite_de_acoes_e_respeitado_mesmo_sem_sem_acao_elegivel`,
  revertido.

Nenhuma integração real, deploy, migration ou envio WhatsApp foi
executado nesta etapa.

## Pendências declaradas (não bloqueiam esta publicação)

1. **[BAIXO]** Falta teste explícito de correlação ação→assinatura
   com 2+ ações `SUCCEEDED` antes do `SEM_ACAO_ELEGIVEL`, confirmando
   que `observar_e_registrar_transicao` recebe o `acao_execucao_id`
   da última ação tentada (e não um elemento bruto da lista).
2. **[BAIXO]** Falta teste de falha genuinamente parcial (ex.:
   1ª ação `SUCCEEDED`, 2ª ação `FAILED_FINAL`), distinto do caso já
   coberto de falha na primeira ação.

Decisão do Chat Projeto: estas duas lacunas de teste ficam como
reforço a fazer antes do disparo real do canário — não são condição
para publicar a Etapa C, porque o comportamento central já está
coberto e a mutação já provou o teste de `todas_sucedidas`.

## Próxima etapa técnica

Após publicação (push + PR) e merge desta Etapa C: preparação
controlada do primeiro canário nominal real (materialização de
`event_id`/`preview_id` reais fora deste script, autorização de fase
específica para habilitar transporte real, nos moldes de `CLAUDE.md`
§6). Os dois testes pendentes listados acima devem ser fechados antes
dessa autorização de fase.
