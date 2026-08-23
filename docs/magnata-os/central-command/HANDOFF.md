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
