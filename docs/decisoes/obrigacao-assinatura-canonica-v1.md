# Gate 1 — Registro canônico da obrigação de assinatura (V1)

- **Data:** 2026-09-25
- **Base:** `main` @ `6585f83` (#184 distribuição genérica 1..N e #186 `/assinatura/consulta` por Field ID)
- **Natureza:** código; **reutiliza a migration 0006, sem schema novo**. Nenhuma migration aplicada, nenhum backfill, zero transporte.

## Cláusulas

> **A presença de uma obrigação de assinatura é determinada por estado persistido e correlacionado ao `acao_execucao_id`, nunca pelo tipo documental, pelo tipo físico da ação ou pelo conteúdo da mensagem.**

> **`acao_execucao_id` é uma identidade opaca para o observador.** Diferentes produtores históricos podem derivá-la de formas diferentes sem alterar o contrato.

## Problema

O observador de assinatura escolhia candidatas por um **proxy histórico**: `listar_succeeded_recentes()`, que filtrava `estado = SUCCEEDED AND tipo = 'texto'`. O filtro veio do commit `baebef1` sem justificativa documentada, e só funcionava porque os ramos com assinatura produzem uma única ação, de texto com o link. Consequências:

- toda mensagem de texto **sem** assinatura também era consultada no adapter legado (HTTP → Airtable);
- uma assinatura representada por outra forma de ação ficaria invisível.

Não havia nenhum marcador persistido de "esta ação tem obrigação".

## Decisão: reutilizar a migration 0006

A tabela `magnata_orquestrador.conclusao_obrigacao_assinatura` já existe no repositório e é suficiente. Ela tem:

- `acao_execucao_id` com FK para `acoes_execucao_plano`, que é chave primária na 0003;
- estados `AGUARDANDO_ASSINATURA`, `ASSINADO`, `COMPROVANTE_VALIDADO` e `CONCLUIDO`;
- correlação externa e evidência;
- trigger append-only;
- índice `(acao_execucao_id, id)`.

A **primeira linha `AGUARDANDO_ASSINATURA` é o marcador canônico da existência da obrigação.**

### Ordem de persistência (respeita a FK)

1. Obrigação criada ou recuperada (`PortaObrigacaoAssinatura`).
2. Numa **única transação** (`RepositorioAcoesExecucaoPlanoPostgres.materializar_registros`, gancho `na_mesma_transacao`):
   - a ação `PENDING` é persistida;
   - logo em seguida, o marcador `AGUARDANDO_ASSINATURA` é gravado sob o **mesmo** `acao_execucao_id` (`registrar_obrigacao_inicial_na_transacao`), respeitando a FK.

   A ação **nunca** fica reivindicável ou enviável sem o marcador. Uma falha no marcador (por exemplo, 0006 ausente) desfaz a ação.
3. A ação eventualmente vira `SUCCEEDED`, e o observador seleciona **só** ações com obrigação persistida e ainda não `CONCLUIDO`.
4. O observador consulta o adapter e registra transições append-only (`registrar_transicao_se_mudou`).

A primeira versão desta missão gravava o marcador numa transação separada, depois da ação. A Ultrareview apontou a janela: se o processo caísse entre os dois commits, e o ciclo enviasse a ação nesse intervalo, a assinatura nunca seria observada. A escrita atômica fecha essa janela por construção.

### Idempotência e concorrência (sem schema novo)

- **`registrar_obrigacao_inicial`** grava o marcador só se **não existir nenhum** histórico. Não é "se diferente do último": no replay de uma obrigação já `ASSINADO`, isso regrediria o estado.
- **`registrar_transicao_se_mudou`** grava só se o estado difere do último persistido.
- **Serialização por ação:** as duas operações fazem check-then-insert na **mesma transação**, sob `pg_advisory_xact_lock(6006, hashtext(acao_execucao_id))`. A forma de duas chaves `int4` fica num espaço separado do lock global do ciclo, e o lock é liberado no commit ou rollback.
- **Por que não `FOR UPDATE`:** travar a linha em `acoes_execucao_plano` faria o claim (`SKIP LOCKED`) pular a ação.
- **Prova com Postgres real:** 8 conexões concorrentes sobre a mesma ação geram exatamente 1 marcador.

### Recuperação após crash

| Fronteira | Replay |
|---|---|
| Obrigação criada, ação não persistida | recupera a obrigação (mesma correlação) e persiste ação + marcador juntos |
| Ação persistida sem marcador | **impossível por construção** (mesma transação); uma falha no marcador faz rollback da ação, e o replay grava os dois |
| Marcador gravado (ou estado posterior) | nenhuma transição nova |
| Queda depois de `SUCCEEDED`, antes da observação | o próximo ciclo seleciona e observa |

O reparo avulso continua disponível: `registrar_obrigacao_inicial` roda em transação própria e é idempotente.

### Seleção canônica do observador

- **Nova consulta:** `listar_acoes_para_observacao` parte das **obrigações** e pega o último estado por ação (`DISTINCT ON`, coberto pelo índice), juntando com a ação `SUCCEEDED`.
- **Estados observados:** exclui `CONCLUIDO`. Continuam observados `AGUARDANDO_ASSINATURA`, `ASSINADO` (esperando comprovante) e `COMPROVANTE_VALIDADO`, que o observador V1 não emite.
- **Sem proxy:** nenhum filtro por tipo. Ação sem obrigação nunca é selecionada, então **nunca gera consulta ao adapter**.
- **Proxy removido:** `listar_succeeded_recentes` saiu do repositório de ações.

### Os dois produtores convergem

| Produtor | Origem do `acao_execucao_id` | Marcador |
|---|---|---|
| `wiring_assinatura_comunicacao_shadow` (fluxo antigo) | identidade genérica (`criar_registro_acao_plano`) | `registrar_obrigacao_inicial` depois de persistir |
| `wiring_distribuicao_documental_shadow` (núcleo genérico) | derivado do `event_id` (`_derivar_acao_execucao_id_assinatura`) | idem |

- No núcleo, `repositorio_conclusao` é **obrigatório quando há assinatura**, com fail-closed antes de qualquer I/O **do núcleo**.
  - Os wirings de orquestração da Prestação e do Contato apenas repassam o parâmetro.
  - Na cadeia da Prestação, o evento canônico da Ordem é registrado antes de o núcleo falhar. O erro é logado e isolado por colaborador.
- O CLI `distribuir_documento_v1` compõe o repositório a partir do ambiente quando há assinatura.

## Obrigações históricas: sem backfill

| Grupo | Situação |
|---|---|
| Rotas antigas do `app.py` (correlação `req<16hex>`) | nunca criaram linha em `acoes_execucao_plano` e nunca foram observadas; continuam sem observação, sem mudança |
| Obrigações do Orquestrador já em produção | **não existem**: a 0004 (Envelope) nunca foi aplicada (`envelope-executavel-persistente-v1.md`), então nenhuma ação com Envelope existe em produção |
| Amostra live do Airtable (Gate 2) | só correlações `req<16hex>` |

**Conclusão:** nenhum backfill é necessário para não perder obrigação ativa.

## Plano de rollout (nada aplicado nesta missão)

Pré-requisitos já existentes no repositório: 0001–0003 aplicadas; 0004 inerte; 0006 inerte, com gitblob de autorização preparado (`ativacao-orquestrador-postgres-0006-v1.gitblob`).

1. **Backup** do Postgres de produção.
2. **Aplicar a 0004** (Envelope), exigida por todo o caminho atual de ações. Precisa de autorização própria.
3. **Aplicar a 0006.** Só cria tabela, índice e trigger, sem efeito sobre dados existentes.
4. **Smoke test só de leitura:** `to_regclass` das tabelas, `SELECT` vazio em `listar_acoes_para_observacao` e o trigger rejeitando `UPDATE`.
5. **Deploy do código.**

**Por que a ordem importa:**
- Com o código antes da 0006:
  - o ciclo registra `ERROR` e pula a observação sem cair, porque há um `try` na seleção e rollback da conexão;
  - um envio **com assinatura** falha fechado: o marcador na mesma transação desfaz a ação, e nada é enviado.
- Ainda assim, **a 0006 deve vir antes do código**, para não bloquear envios assinados. A 0006 antes do código é inofensiva: nada lê nem grava nela até o deploy.

## Riscos

- **Integridade da sequência de estados:** o banco não impõe "primeira linha = `AGUARDANDO`", nem ordem de transição, nem `CONCLUIDO` como terminal. A integridade vem dos repositórios, que são o único caminho de escrita.
- **Limite da seleção (starvation):** `limite=200`, ordenado pelas ações atualizadas mais recentemente, a mesma ordenação do proxy antigo. O `atualizado_em` da ação não muda depois de `SUCCEEDED`, e obrigações que nunca concluem (por exemplo, `ASSINADO` sem comprovante) continuam selecionáveis.
  - **Consequência:** com **mais de 200** obrigações não concluídas, as mais antigas **deixam de ser observadas** enquanto houver 200 mais novas. Elas não "esperam o próximo ciclo".
  - **Por que não corrigi agora:** um rodízio justo exige persistir "última observação" (schema novo, gate) ou uma regra de negócio de expiração (decisão humana). Por isso ficou fora desta missão.
  - **Custo:** até 200 consultas HTTP por ciclo em regime estável, o mesmo teto do proxy antigo.
- **Regressão pelo observador:** o observador ainda pode registrar `AGUARDANDO_ASSINATURA` depois de `ASSINADO`, se o legado "voltar" para Pendente. Isso já existia antes; só o marcador **inicial** é protegido contra regressão.
- **Teste do ciclo:** o teste de "zero consultas ao adapter" usa um repositório fake. A garantia no SQL é provada pelo teste Postgres real de seleção, que roda na CI.
- **Fluxo antigo com token novo no replay** (`wiring_assinatura_comunicacao_shadow`): um token novo gera outro id e outra obrigação. É pré-existente, e o fluxo não tem caller em produção.
- **Testes Postgres reais** (concorrência, FK, seleção): rodam só na CI (job `postgres-real`); localmente não há Postgres.
