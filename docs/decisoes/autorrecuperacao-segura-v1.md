# Autorrecuperacao segura V1 do Grande Orquestrador

**Data:** 2026-08-25

**Estado:** implementada em branch local, ainda sem commit/PR/merge/deploy

**Base:** `main@988722d0816315f9d60d89f83e683542463a3a88` (PR #55)

## 1. Problema

O health persistente informa `VERDE`, `AMARELO` ou `VERMELHO`, mas nao
decide sozinho o que fazer. Retentar indiscriminadamente e inseguro: uma
falha transitória pode ocorrer depois de um efeito parcial, e dois workers
podem tentar recuperar o mesmo evento ao mesmo tempo.

## 2. Decisao

A autorrecuperacao e um coordenador sobre o motor existente, nao um segundo
Orquestrador. O coordenador:

1. le `RepositorioExecucoes`, a mesma fonte usada pelo health persistente;
2. considera apenas `FAILED_RETRYABLE` para retry automatico;
3. respeita `next_retry_at`;
4. exige politica explicita de recuperacao e idempotencia conhecida;
5. reavalia politica de autonomia e KILL_SWITCH antes da nova Acao;
6. usa o proprio `MotorOrquestrador` para executar;
7. persiste cada decisao numa trilha append-only separada;
8. abre circuito quando o health persistente esta `VERMELHO`;
9. nunca executa replay automatico de evento preso ou `FAILED_FINAL`.

Ausencia de politica e sempre `ESCALAR_HUMANO`, nunca permissao por omissao.

## 3. Politica V1

Somente `GIT_MAIN_AVANCOU` admite retry automatico nesta V1. A Acao
recalcula o AUTO_FACT a partir do Git e substitui o mesmo snapshot derivado;
nao envia mensagem, nao escreve em producao e nao altera HUMAN_DECISION.

`PR_MESCLADO`, `SUITE_DIVERGIU`, `ESTRUTURA_CODIGO_DIVERGIU` e qualquer tipo
futuro permanecem bloqueados ate receberem politica de recuperacao propria.
Ser `EXECUTE_SAFE` na primeira chamada nao implica ser automaticamente
seguro para repeticao.

## 4. Concorrencia e crash

`RepositorioExecucoes.reivindicar_retry()` faz compare-and-swap atomico:

`FAILED_RETRYABLE -> EXECUTING`, incremento de `attempt` e auditoria
pertencem a uma unica secao critica/transacao. Apenas um worker ganha.

O motor tambem persiste `EXECUTING` antes de chamar a Acao na primeira
tentativa. Se o processo morrer durante o efeito, o restart encontra um
evento preso em `EXECUTING`; o coordenador apenas escala. O replay continua
exigindo confirmacao humana de que o worker anterior morreu e de que repetir
a Acao e seguro.

Isso garante **at-most-once por reivindicacao do motor**. Nao promete
exactly-once e nao compensa efeito parcial dentro de servico externo.

## 5. Auditoria

A tabela local `auditoria_recuperacao` e append-only e separada do historico
de transicoes. Ela registra autorizacao do retry, execucao, backoff, abertura
de circuito, concorrencia perdida e escalonamento. Decisoes identicas em
ciclos consecutivos nao sao duplicadas.

Essa DDL pertence ao SQLite local do Orquestrador. Nenhuma migration ou
alteracao de schema de producao foi executada.

## 6. Perimetro obrigatorio de nao regressao

Esta fase nao altera nem substitui:

- a esteira `magnata_os/documental/modulo01/`;
- `src/services/secullum_ponto.py` e `src/ingestao_secullum.py`;
- `apps_script_email_intake.gs` e seus remetentes DP/Fiscal;
- o PR #49 de Gmail read-only, que continua fora de `main`;
- `app.py`, migrations documentais, frontend e assets de marca;
- Airtable, Render, Gmail, WhatsApp, Secullum ou qualquer producao real.

Esses componentes sao dominios/adapters coordenados futuramente por eventos;
nunca serao reimplementados dentro da autorrecuperacao.

## 7. Provas implementadas

Os testes cobrem:

- backoff ainda nao vencido;
- retry devido que termina em sucesso;
- politica ausente;
- health vermelho/circuit breaker;
- KILL_SWITCH ativado entre tentativas;
- falha da auditoria bloqueando efeito antes da Acao;
- evento `EXECUTING` antigo sem auto-replay;
- persistencia da trilha depois de restart;
- dois workers concorrentes realizando exatamente um retry;
- E2E: retry -> esgotamento -> DLQ em memoria -> restart -> escalonamento ->
  replay manual -> sucesso -> health verde.

## 8. Limites restantes

- O coordenador ainda nao esta conectado a um scheduler/servico permanente.
- O SQLite do workflow atual e efemero em cada runner do GitHub Actions;
  portanto nao prova recuperacao entre runs autonomos.
- A `FilaDesistenciaEmMemoria` continua em memoria. `FAILED_FINAL` e a
  auditoria persistem no repositorio, mas a lista materializada da DLQ nao
  sobrevive restart. Tornar a DLQ persistentemente append-only exige uma
  decisao propria de armazenamento.
- Nenhum backend Postgres foi implementado ou provisionado.
- Nenhum acesso externo, deploy ou mudanca de configuracao foi realizado.

Esses limites impedem declarar autorrecuperacao operacional 24h ou pronta em
producao. A entrega desta fase e o nucleo local, persistente e testavel.
