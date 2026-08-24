# HANDOFF — ponto de entrada para a próxima sessão

**Gerado na Etapa 12, 2026-08-23.**

Uma sessão nova deve conseguir continuar **lendo só este arquivo e os 4
canônicos abaixo** — sem a conversa Macro 6A, que está encerrada.

> Este arquivo **não duplica** a Central Command. Ele aponta.

---

## 1. Onde o repositório está

> ⚠️ **Os números abaixo são de 2026-08-23 e envelhecem.** Não confie
> neles: **execute `python scripts/ci/central_command_sensor.py`** — ele
> compara o estado real com `ESTADO.json` e diz o que mudou.

| | |
|---|---|
| **`main`** | `1409454` — *Merge pull request #44* (Etapa 12) |
| **Suíte** | **659 passando / 0 falhando** |
| **CI** | 2 workflows, ambos verdes: governança (15/15 gates) e `pytest` |
| **PII na árvore atual de `main`** | ✅ **nenhuma** |
| **Central Command** | 30 documentos + `ESTADO.json` + `ARQUITETURA_SNAPSHOT.json` |
| **Graphify** | ✅ **exercitado sobre o repositório inteiro** (com `app.py`) — zero violação de `CLAUDE.md` §3. Ver `GRAPHIFY.md` §8 |
| **Produção** | ❌ **NÃO VERIFICÁVEL** — reconfirmado por `WebFetch` nesta etapa (`EGRESS_BLOCKED`) |
| **PRs abertos** | **Nenhum** |

## 2. Ler primeiro, nesta ordem

1. **`CLAUDE.md`** — a constituição. Vence tudo abaixo.
2. **`docs/magnata-os/central-command/INDEX.md`** — mapa: qual arquivo responde qual pergunta.
3. **`TAXONOMIA_MEMORIA.md`** e **`MATRIZ_AUTONOMIA.md`** — o que um sensor pode escrever sozinho, e em qual nível de autonomia (Etapa 12, novo).
4. **`docs/magnata-os/MAGNATA_OS_CENTRAL_COMMAND.md`** §0-H a §0-J — as últimas etapas.
5. **`MACRO_6A_RECONCILIACAO.md`** §4 — os 6 erros que não devem se repetir.

Para saber se a memória está defasada, **não leia: execute.**

```
python scripts/ci/central_command_sensor.py
bash scripts/ci/graphify_regenerar.sh --comparar   # opcional, sensor estrutural
```

## 3. Merges recentes (Etapa 12)

| PR | O que trouxe |
|---|---|
| **#41** | Correção do sensor (baseline não some mais sem `--com-testes`) — revalidado, rebaseado e **MESCLADO** |
| **#22** | Adapter de captura de e-mail (Módulo 01) — auditado adversarialmente (3 lacunas de teste fechadas), rebaseado e **MESCLADO**. Adapter em `main`, **inerte** — nenhum caller real |
| **#44** | Central Command reconciliada com o merge do #22 (DEC-009, WIP-004, NXT-005, PEN-020) |

## 4. PRs abertos

**Nenhum.** Único PR aberto anterior (#22) foi mesclado nesta etapa.

## 5. Riscos, em ordem (herdados — não reavaliados nesta etapa)

| # | Risco | Onde está descrito |
|---|---|---|
| 1 | 🔴 **PII em ~40 pontas de branch** e no histórico de `main` | `PII_HISTORICO_PLANO.md` |
| 2 | 🔴 **`480` fixo** — só o Airtable calcula extra, e só ele ignora 12x36 | `AIRTABLE_LOGICA_OCULTA.md` ANEXO B §B.5 (AT-21) |
| 3 | 🔴 **Make.com ativo sem `try/catch`** — falha silenciosa | ANEXO B §B.6 (AT-12) |
| 4 | 🔴 **Batida ímpar → `BLANK()`** sem alarme | `AIRTABLE_LOGICA_OCULTA.md` §3 |
| 5 | 🟠 **72% de `Folha de Ponto`** calculado dentro do Airtable | `BANCO_PROPRIO_MODELO.md` §2 |
| 6 | 🟠 **`F_FUNC_STATUS`** escrito fora do código, lido pelo `app.py` | mestre §0-H.7 |
| 7 | 🟡 **Retry/backoff do adapter de e-mail** — decisão adiada para quando (e se) ligar a fonte real | `PENDING.md` PEN-020 (Etapa 12) |
| 8 | 🟡 **Nenhum gatilho automático** aciona sensor/Graphify sem sessão no meio | `MATRIZ_AUTONOMIA.md` §4 (Etapa 12) |

## 6. Gates humanos abertos

| Gate | Decisão |
|---|---|
| 🔴 Histórico do Git | Sanear por avanço, reescrever, ou aceitar o risco |
| 🔴 Jornada `480` / 12x36 | Regra trabalhista com efeito retroativo em folha |
| 🔴 Make.com | Manter · instrumentar · migrar · descomissionar |
| 🟠 Postgres real | Decisão financeira — `render.yaml` é `plan: free` |
| 🟠 `Locais` = `Posto de Trabalho`? | `BANCO_PROPRIO_MODELO.md` §8.3 |
| 🟠 ADR `Documento` vs. `Item de Ingestão` | `CLAUDE.md` §5 |
| 🟠 40 branches / apagar branch | `CLAUDE.md` §9 |
| 🟡 Ligar o adapter de e-mail a uma fonte real | `DECISIONS.md` DEC-009 — precisa autorização de fase (`CLAUDE.md` §6/§12-I) |
| 🟡 Automatizar disparo do sensor/Graphify sem sessão no meio (novo job de CI) | `MATRIZ_AUTONOMIA.md` §4 — decisão de governança de CI, não técnica |

## 7. O que só a interface resolve

Nenhuma ferramenta desta sessão alcança:

1. **Filtros das 10 views** e **condições dos ramos** — Airtable.
2. **Confirmar que `Automation 1` está mesmo vazia** — Airtable.
3. **O que o cenário do Make.com faz** — Make.com. Bloqueia 3 das 4 opções.
4. **Produção** — rede (reconfirmado nesta etapa, `WebFetch` → `EGRESS_BLOCKED`).

## 8. Próxima ação de maior valor

**Instrumentar o `PROCESSAR ARQUIVOS` (Make.com) com tratamento de erro.**

Continua sendo o item que é, ao mesmo tempo: risco 🔴 ativo em produção,
correção pequena, sem mudar o caminho feliz, e sem dependência de
nenhuma decisão de negócio pendente. Mata AT-12 sem tocar em jornada,
folha ou fornecedor.

⚠️ Continua sendo **escrita fora deste repositório** (Make.com) — fora
do alcance de qualquer sessão sem acesso à interface, e mesmo com
acesso, é escrita externa: gate de `CLAUDE.md` §6, com autorização por
fase cumprindo (a)–(f).

**Dentro do que uma sessão de código alcança hoje**, a maior lacuna
registrada nesta etapa é a de **infraestrutura de disparo automático**
(`MATRIZ_AUTONOMIA.md` §4) — decidir se um job de CI pode abrir PR
automático com o snapshot do sensor, sem nunca commitar direto em
`main`.

---

## Checkpoint de sessão — 2026-08-24

> ⚠️ Checkpoint aditivo de fechamento de sessão — **não é a
> reescrita completa** deste `HANDOFF.md` (essa reescrita está
> planejada mas não executada, ver "Missão pendente" abaixo). As
> seções acima (Etapa 12) continuam sendo a última auditoria formal;
> este checkpoint só registra o que mudou nesta sessão, para nenhum
> fato importante ficar só no histórico do chat (`CLAUDE.md` §11/§12-N).

**O que foi concluído:**
- Motor do Orquestrador (`magnata_os/orquestrador/`): DLQ integrada ao
  caminho real do motor, auditoria append-only (imutável, persistente,
  resiliente a falha de escrita), replay manual estendido (cobre
  eventos presos "em andamento", não só `FAILED_FINAL`), chaos testing
  6/6 (era 3/6), suite adversarial (DRY_RUN/KILL_SWITCH/retry limits),
  testes de segurança adversarial.
- **Retratação formal**: relatório anterior desta sessão
  (`GRANDE_ORQUESTRADOR_V1_READINESS.md`) declarou "AT_MOST_ONCE
  garantido" sem prova real — retratado. Um probe determinístico
  (`threading.Barrier`) provou dupla execução real de Ação externa.
  Corrigido com reivindicação atômica (`criar_se_novo`, `PRIMARY KEY`
  do SQLite) + recusa de retomada de evento "em andamento". Ver
  `GRANDE_ORQUESTRADOR_V1_RECONCILIACAO.md` (substitui o relatório
  retratado como fonte de verdade).
- Suite completa local: **794 passed, 1 skipped, 0 failed**, estável
  em múltiplas execuções — na branch, **não em `main`**.
- Governança local: 15/15 gates.
- Migração de branch: `claude/magnata-memory-audit-2c6bps` (não casava
  a allowlist de nome de branch) → `fix/orquestrador-v1-reconciliacao`
  (18 commits preservados, mesmos SHAs, mais 1 commit de whitespace).
  PR **#50 fechado**, **PR #51 aberto** no lugar — CI verde,
  `mergeable_state: clean`, **não mesclado** (gate humano, `CLAUDE.md`
  §9, nunca dispensado).
- Investigação de uma nova missão (otimização de contexto/tokens):
  confirmado que `HANDOFF.md`/`ESTADO.json`/`INDEX.md` já cumprem o
  papel de bootstrap/manifest que a missão pedia sob outros nomes;
  usuário decidiu consolidar em vez de duplicar. Plano aprovado.

**O que ficou incompleto:**
- **Missão pendente**: implementação do plano de consolidação de
  contexto (aprovado, zero código escrito). Plano completo em
  `/root/.claude/plans/async-nibbling-toucan.md` — **só existe na
  máquina desta sessão, não versionado no repositório.** Próxima
  sessão precisa: (a) pedir o conteúdo do plano de novo se a máquina
  não persistir, ou (b) reconstruir a partir deste checkpoint + do
  pedido original do usuário. Resumo do plano: formalizar contratos
  L0-L4 sobre os arquivos já existentes (sem duplicar), estender
  `central_command_sensor.py --atualizar` com campos novos
  (`generated_at`, `orchestrator_status`, `active_prs`, etc.), criar
  `scripts/ci/contexto_cli.py` + testes (única lacuna real sem
  cobertura hoje), medir antes/depois (34k→2,3k palavras já medido
  sem código novo), abrir PR numa branch compatível com a allowlist
  desde o início.
- PR #51 não mesclado (decisão do usuário).
- 3 branches órfãs de execuções falhas do sensor de CI
  (`fix/auto-orquestrador-76b0046-{2,3,4}`) não apagadas (sem
  autorização explícita).
- E2E interno como trilha única não executado (declarado, não
  escondido — ver `GRANDE_ORQUESTRADOR_V1_RECONCILIACAO.md` §12).

**Arquivos alterados nesta sessão** (todos em
`fix/orquestrador-v1-reconciliacao`, não em `main`):
`magnata_os/orquestrador/{motor,eventos,repositorio_execucoes}.py`,
7 arquivos `test_magnata_os_orquestrador_*.py` (novos ou reescritos),
`GRANDE_ORQUESTRADOR_V1_READINESS.md` (retratado, banner),
`GRANDE_ORQUESTRADOR_V1_RECONCILIACAO.md` (novo, fonte de verdade
atual), `docs/decisoes/grande-orquestrador-v1-respostas-tecnicas.md`
(whitespace), e este checkpoint em `HANDOFF.md`/`ESTADO.json`.

**Branch atual:** `fix/orquestrador-v1-reconciliacao` (local e remota),
19 commits à frente de `main` (HEAD `a5fbcbd` antes deste checkpoint).

**PRs:** #49 aberto (Gmail Fase 1, não tocado nesta sessão) · #50
fechado (substituído) · #51 aberto, CI verde, aguardando decisão de
merge.

**Bugs/gates confirmados com evidência (não suposição):**
- GitHub Actions bloqueado de criar PR (log real:
  "GitHub Actions is not permitted to create or approve pull
  requests") — `orquestrador-sensor.yml` nunca fecha ponta-a-ponta
  sozinho.
- Health monitor não persiste entre execuções (design documentado no
  próprio módulo).
- Merge de PR continua gate humano absoluto (`CLAUDE.md` §9/§12-I) —
  nenhuma instrução de missão o dispensa.

**Próximo passo exato:** implementar o plano aprovado em
`/root/.claude/plans/async-nibbling-toucan.md` — 6 mudanças concretas
(`central_command_sensor.py`, `INDEX.md`, `HANDOFF.md`, `PRS_AND_BRANCHES.md`,
`scripts/ci/contexto_cli.py` novo, `scripts/ci/test_contexto_cli.py`
novo), rodar a suite completa de verificação (10 passos, listados no
plano), abrir PR numa branch já compatível com a allowlist desde o
início.
