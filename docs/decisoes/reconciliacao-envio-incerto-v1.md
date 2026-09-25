# Gate 3 — Reconciliação humana de envio externo incerto (V1)

- **Data:** 2026-09-25
- **Base:** `main` @ `b284b96` (#187, obrigação de assinatura canônica)
- **Branch:** `fix/reconciliacao-envio-incerto-v1`
- **Natureza:** só código e testes. **Nenhuma migration**, nenhum endpoint, CLI ou UI novo, nenhum transporte, nenhum retry automático.

## Cláusulas

> **`FAILED_FINAL` não é reabrível de forma genérica.** A única exceção é `ultimo_erro_classe = ENVIO_EXTERNO_INCERTO`, e apenas por decisão humana com ator, motivo e evidência. `PERMANENT`, `INVALID_INPUT`, `HUMAN_GATE`, qualquer outra classe (inclusive nula ou escrita de outro jeito) e qualquer outro estado (`SUCCEEDED`, `PENDING`, `FAILED_RETRYABLE`, `EXECUTING`) são rejeitados.

> **Enquanto o envio continuar incerto, a ação não é `SUCCEEDED`, e as ações posteriores do mesmo `(event_id, preview_id, destinatario_sha256)` continuam bloqueadas.** Não existe operação de "prosseguir mesmo assim".

## Problema

Quando o transporte falha sem saber se a mensagem saiu (`FalhaEnvioIncerto`), o executor classifica a falha como `ENVIO_EXTERNO_INCERTO` e marca a ação `FAILED_FINAL`. Isso é o comportamento correto e fail-closed. Porém não havia um caminho auditado para um humano resolver a dúvida. A ação ficava terminal para sempre, e as posteriores do mesmo destinatário ficavam bloqueadas pelo predicado sequencial `_predicado_elegibilidade`.

## Decisão

Uma operação humana e explícita, com três casos:

| Caso | Evidência humana | Transição | Efeito nas posteriores |
|---|---|---|---|
| A | o envio **não** ocorreu | `FAILED_FINAL` → `FAILED_RETRYABLE` | continuam bloqueadas até esta chegar a `SUCCEEDED` |
| B | o envio **ocorreu** | `FAILED_FINAL` → `SUCCEEDED`, sem reenvio | a próxima fica elegível pelo predicado já existente |
| C | continua incerto | nenhuma (não existe função) | continuam bloqueadas |

Pontos de entrada, em `magnata_os/orquestrador/reconciliacao_execucao_orfa.py`, sempre chamados por um humano:

- `liberar_envio_incerto_sem_envio_confirmado(..., ator_referencia, motivo, evidencia_ausencia_envio, instante)`
- `confirmar_envio_incerto_como_enviado(..., ator_referencia, motivo, resultado_referencia_externo, evidencia_envio, instante)`

A visão somente leitura para inspeção é `RepositorioAcoesExecucaoPlanoPostgres.listar_envios_incertos()`. Ela expõe só ids e hashes já persistidos, nunca destinatário ou conteúdo em claro, e não decide nada.

### CAS

`_reconciliar_envio_incerto` executa um único `UPDATE ... RETURNING`, com todas estas condições:

- `acao_execucao_id` exato;
- `estado = 'FAILED_FINAL'`;
- `ultimo_erro_classe = 'ENVIO_EXTERNO_INCERTO'`;
- `claim_sha256 IS NOT DISTINCT FROM` o valor observado;
- `attempt =` o valor observado.

`attempt` identifica o incidente específico. Hoje os produtores (`ciclo_producao_v1` e `executar_canario_v1`) derivam `claim_referencia` do instante, mas o contrato não garante isso: um produtor que reutilize a mesma referência geraria o mesmo `claim_sha256`. Por isso a checagem de `attempt` é defesa em profundidade, e há teste dedicado para um snapshot que só difere em `attempt`. Se o humano decidiu olhando um snapshot antigo e a ação já foi reconciliada e falhou de novo, o CAS perde. O resultado é `None`, sem mudança e sem trilha, e nunca há insistência.

Duas decisões conflitantes e concorrentes (A e B sobre a mesma ação) serializam no lock de linha. A segunda reavalia o `WHERE` em READ COMMITTED e não encontra mais a linha. **Só uma vence.**

A validação de estado e classe acontece **duas vezes**: no domínio, que rejeita com erro explícito antes de tocar o banco, e no CAS. Um snapshot forjado como "incerto" também é recusado pelo banco.

### Auditoria atômica

A trilha usa a tabela existente `magnata_orquestrador.auditoria_recuperacao`. A coluna `decisao` é TEXT sem CHECK e a tabela é append-only, então **não precisa de migration**. A trilha é gravada **na mesma transação** do `UPDATE`, pelo gancho `na_mesma_transacao(cursor)` → `RepositorioExecucoesPostgres.registrar_recuperacao_na_transacao`. O gancho só roda se o CAS venceu. Se a auditoria falhar, há rollback e a ação não muda. Nunca existe ação reconciliada sem registro de quem decidiu.

A auditoria usa valores **próprios** de `DecisaoRecuperacao`, sem reaproveitar nenhum valor semanticamente falso:

- `RECONCILIACAO_MANUAL_ENVIO_INCERTO_SEM_ENVIO` (caso A)
- `RECONCILIACAO_MANUAL_ENVIO_INCERTO_ENVIADO` (caso B)

`estado_observado = 'FAILED_FINAL'`. O `motivo` traz o ator, o `acao_execucao_id`, o `attempt` e, no caso B, a referência externa. A `evidencia` guarda o texto humano.

### Efeitos por caso

- **A:** `estado = FAILED_RETRYABLE`, `concluido_em = NULL`, `proxima_tentativa_em = NULL` (elegível já, como na liberação de EXECUTING órfão) e `ultimo_erro_classe = ENVIO_INCERTO_LIBERADO_SEM_ENVIO`. Esse marcador tira a ação da classe incerta, então ela não pode ser "re-reconciliada" sem uma nova falha incerta real, e deixa rastro de que o próximo claim nasceu de decisão humana. `resultado_referencia` e `evidencia_sha256` ficam NULL.
- **B:** `estado = SUCCEEDED`, `concluido_em = instante`, `resultado_referencia` recebe o id externo, `evidencia_sha256 = hash_conteudo_comunicacao(evidencia)` (mesmo padrão de `reconciliar_envio_confirmado`) e `ultimo_erro_classe = NULL`.

### `attempt` e `MAX_TENTATIVAS`

- `attempt` **nunca é resetado nem incrementado** pela reconciliação. Só o próximo claim real incrementa, como sempre.
- `MAX_TENTATIVAS` continua sendo verificado só no executor, depois de uma falha (`retentavel = TRANSIENT and attempt < MAX_TENTATIVAS`). Uma liberação humana concede **no mínimo 1 e no máximo `max(1, MAX_TENTATIVAS - attempt + 1)`** novos claims:
  - falhas `TRANSIENT` abaixo do limite seguem o backoff normal;
  - `attempt` nunca volta, então o orçamento total de tentativas é o mesmo de qualquer ação;
  - uma ação que já estava em `attempt >= MAX_TENTATIVAS` ganha exatamente um claim.

  Nova falha incerta, `PERMANENT` ou `TRANSIENT` no limite devolve a ação a `FAILED_FINAL`. Sair dali de novo exige nova decisão humana, e só se a classe for `ENVIO_EXTERNO_INCERTO`. Não há retry ilimitado.

### O que não muda

- `_predicado_elegibilidade`, `listar_pares_elegiveis` e o claim ficam **inalterados**.
- A reconciliação de EXECUTING órfão (`liberar_acao_orfa_sem_envio_confirmado` e `reconciliar_acao_orfa_com_envio_confirmado`) continua como está.
- **Gate 1:** o observador seleciona só `a.estado = 'SUCCEEDED'`. Uma ação incerta ou liberada (caso A) não é observada. Uma confirmada (caso B) entra na seleção canônica sem regra nova. Há teste real em `test_conclusao_obrigacao_assinatura_postgres.py`.
- Nenhuma heurística sobre texto de erro. A comparação de classe é exata, e `envio_externo_incerto` em minúsculas é rejeitado.
- Distribuição genérica: nada depende do tipo documental (testes com `DOCUMENTO_A` e `DOCUMENTO_B`).

## Riscos declarados (não corrigidos aqui, fora do escopo)

1. **Reconciliação de EXECUTING órfão, caso C:** `reconciliar_acao_orfa_com_envio_confirmado` audita como `RETRY_EXECUTADO`, que é semanticamente falso porque nada foi retentado. Além disso, grava a auditoria em **transação separada** da mudança de estado. Se a auditoria falhar depois do commit da ação, a ação fica reconciliada sem trilha. Correção sugerida em gate próprio: usar o mesmo gancho `na_mesma_transacao` e um valor de decisão próprio.
2. `registrar_recuperacao_na_transacao` existe no adapter Postgres e no repositório em memória. `RepositorioExecucoesSQLite` não tem esse método. Se ele for passado por engano, o `AttributeError` acontece **dentro** da transação e provoca rollback (fail-closed).
3. A evidência humana é texto livre e fica em `auditoria_recuperacao.evidencia`, como já acontece na liberação de EXECUTING órfão. O operador não deve incluir dado pessoal: a LGPD vale para o texto que ele digita.
4. **Pré-existente, não criado aqui:** se a nova tentativa, depois do caso A, terminar em `FAILED_FINAL` com outra classe (`PERMANENT`, ou `TRANSIENT` no limite), a ação fica terminal e não reconciliável, e as posteriores do mesmo destinatário ficam bloqueadas para sempre. Isso vale para qualquer `FAILED_FINAL` genérico. O caminho de saída continua sendo o caso D do ADR do wiring: um novo plano, com novo `acao_execucao_id`.
5. `RepositorioExecucoesEmMemoria.registrar_recuperacao_na_transacao` ignora o cursor e grava na hora. Ele serve só para testes: combinado com o repositório de ações em Postgres, não é transacional. O protocolo `RepositorioExecucoes` não foi estendido para não quebrar a conformidade estrutural do adapter SQLite, então o requisito é documentado aqui e na assinatura.
6. `listar_envios_incertos`, como o `buscar` existente, deixa a conexão compartilhada em "idle in transaction" (só AccessShare, sem bloquear ninguém). Uma conexão de operador de vida longa deve fazer commit ou rollback depois de ler.
7. Ainda não há interface humana (CLI, endpoint ou UI). As funções existem só como API interna. Expor isso é um gate separado.

## Testes

- Unitários com cursor fake, em `test_repositorio_acoes_execucao_plano_postgres_orfao.py`: parâmetros do CAS, auditoria antes do commit, CAS perdido sem auditoria, rollback se a auditoria falhar, rejeição de todos os estados e classes não elegíveis, campos humanos obrigatórios e sem default, valores de decisão próprios, ausência de porta de transporte e de função "prosseguir".
- Postgres real, em `test_repositorio_acoes_execucao_plano_postgres_real.py` (job `postgres-real`): visão somente leitura, caso C bloqueando, isolamento por destinatário e por evento, caso A atômico (`concluido_em` limpo, `attempt` preservado, bloqueio até sucesso e liberação depois), nova falha incerta voltando a FINAL com o snapshot antigo inválido, caso B sem reenvio liberando a próxima, `FAILED_FINAL` genérico rejeitado mesmo com snapshot forjado, e duas decisões conflitantes concorrentes com um único vencedor.
- Gate 1 real, em `test_conclusao_obrigacao_assinatura_postgres.py`: seleção do observador antes e depois de A e B.
