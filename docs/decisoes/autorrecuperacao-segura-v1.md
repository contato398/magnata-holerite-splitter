# Autorrecuperacao segura V1 do Grande Orquestrador

**Data:** 2026-08-25

**Estado:** nucleo V1 mesclado pelo PR #56; prova multiprocesso/restart
mesclada pelo PR #57; visao persistente da DLQ ativa mesclada pelo PR #58;
supervisor periodico em shadow mode mesclado pelo PR #59 em
`main@810b1e1d4d88cdb8cf1e495932cba946b0167b99`; sem modo ativo e sem deploy

**Base original:** `main@988722d0816315f9d60d89f83e683542463a3a88` (PR #55)

**Base da prova multiprocesso:**
`main@bc42bbccd5cf2d0794d3ab6d708ab9b7b0d20d74` (PR #56)

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

- O workflow periodico executa o supervisor somente em shadow mode. Ele gera
  snapshot de health, DLQ, retries vencidos e eventos em andamento, sem
  reivindicar retry, gravar auditoria ou chamar Acao.
- O modo ativo existe como composicao sobre o coordenador atual, mas exige gate
  explicito em codigo e ainda nao esta habilitado no workflow nem em producao.
- O SQLite do workflow atual e efemero em cada runner do GitHub Actions;
  portanto nao prova recuperacao entre runs autonomos.
- A fila de notificacao do processo continua em memoria, mas a DLQ ativa agora
  possui uma visao persistente, somente leitura, derivada dos registros em
  `FAILED_FINAL`. Ela sobrevive restart sem criar tabela ou fonte paralela.
- O historico de transicoes continua append-only na auditoria. A visao ativa
  nao guarda uma segunda copia historica do payload: depois de replay manual
  bem-sucedido, o item sai da fila ativa e sua passagem por `FAILED_FINAL`
  permanece na auditoria.
- Nenhum backend Postgres foi implementado ou provisionado.
- Nenhum acesso externo, deploy ou mudanca de configuracao foi realizado.

Esses limites impedem declarar autorrecuperacao operacional 24h ou pronta em
producao. A entrega desta fase e o nucleo local, persistente e testavel.

## 9. Aprofundamento de restart/recovery entre processos

A primeira prova de restart fechava e reabria o SQLite dentro do mesmo
interpretador Python. Isso comprova persistencia da conexao, mas nao reproduz
integralmente a morte abrupta de um worker nem a concorrencia entre processos
independentes.

A ampliacao sobre o PR #56 adiciona provas com processos criados por `spawn`:

1. um worker persiste `EXECUTING`, realiza um efeito local observavel e morre
   dentro da Acao por `os._exit`, sem `finally` nem fechamento gracioso;
2. a instancia seguinte encontra o evento preso, apresenta health `AMARELO`,
   registra `ESCALAR_HUMANO` e nao repete automaticamente o efeito;
3. dois processos independentes disputam o mesmo retry vencido e somente um
   atravessa o compare-and-swap do SQLite e executa a Acao;
4. a auditoria registra uma unica reivindicacao atomica e o evento termina com
   `attempt=2`, sem duplicacao.

Durante essa prova foi encontrado um defeito real no `salvar()` do SQLite:
depois da reivindicacao inicial, os campos `nivel_autonomia` e `acao` eram
atualizados apenas no objeto em memoria. O `ON CONFLICT` persistia estado e
resultado, mas deixava os dois metadados nos valores iniciais `-1` e vazio.
Isso comprometia proveniencia depois de restart. A ampliacao persiste ambos e
prova a reabertura com os valores efetivamente decididos pelo motor.

O timestamp da DLQ em memoria passa a ser UTC timezone-aware. Esta ampliacao
nao torna a DLQ materializada persistente, nao cria tabela nova e nao muda o
limite deliberado da secao 8.

## 10. Supervisor periodico em shadow mode

O supervisor nao e um segundo Orquestrador. Ele le o mesmo
`RepositorioExecucoes` usado pelo motor, health e DLQ, e produz um snapshot
serializavel para observabilidade e futuro painel. O cron existente chama o
modo `SHADOW`, que por contrato nao executa recuperacoes nem produz escrita
operacional.

O modo `ACTIVE` apenas delega ao `CoordenadorAutorrecuperacao` existente e
exige `autorizar_execucao_ativa=True` no ponto de composicao. Variavel de
ambiente isolada nao basta para remover esse gate. Essa separacao permite
acumular evidencia operacional antes de habilitar autonomia consequencial.

Cada ciclo agendado tambem preserva o JSON do snapshot como artifact do
GitHub Actions por 14 dias. O artifact e evidencia observacional temporaria:
nao contem o SQLite, nao e memoria operacional, nao habilita recovery e nao
se torna uma segunda fonte de verdade. A persistencia duravel entre runs
continua dependendo de um backend do `RepositorioExecucoes` explicitamente
projetado, testado e provisionado sob gate proprio.
