# HANDOFF — ponto de entrada para a próxima sessão

**Gerado na Etapa 11, 2026-08-23.**

Uma sessão nova deve conseguir continuar **lendo só este arquivo e os 4
canônicos abaixo** — sem a conversa Macro 6A, que está encerrada.

> Este arquivo **não duplica** a Central Command. Ele aponta.

---

## 1. Onde o repositório está

| | |
|---|---|
| **`main`** | `007a4e5` — *Merge pull request #38* |
| **Suíte** | **649 passando / 0 falhando** (642 + 7 do PR #41) |
| **CI** | 2 workflows, ambos verdes: governança (15/16 gates) e `pytest` |
| **PII na árvore atual de `main`** | ✅ **nenhuma** |
| **Central Command** | 28 documentos + `ESTADO.json` + `ARQUITETURA_SNAPSHOT.json` |
| **Produção** | ❌ **NÃO VERIFICÁVEL** — rede da sessão bloqueia (`HTTP 000`) |

## 2. Ler primeiro, nesta ordem

1. **`CLAUDE.md`** — a constituição. Vence tudo abaixo.
2. **`docs/magnata-os/central-command/INDEX.md`** — mapa: qual arquivo responde qual pergunta.
3. **`docs/magnata-os/MAGNATA_OS_CENTRAL_COMMAND.md`** §0-H e §0-I — as duas últimas etapas.
4. **`docs/magnata-os/central-command/MACRO_6A_RECONCILIACAO.md`** §4 — os 6 erros que não devem se repetir.

Para saber se a memória está defasada, **não leia: execute.**

```
python scripts/ci/central_command_sensor.py
```

## 3. Merges recentes

| PR | O que trouxe |
|---|---|
| **#37** | Inventário da lógica oculta do Airtable · Graphify regenerável |
| **#39** | ANEXO A — os 2 `customScript` e as views |
| **#40** | Central Command Etapas 9 e 10 |
| **#38** | **Remoção de CPF e nome real** de código versionado (LGPD) |

## 4. PRs abertos

| PR | Estado | O que falta |
|---|---|---|
| **#41** | 🟡 correção do sensor — CI verde | **Gate humano:** é mudança funcional (§12-I) |
| **#42** | 🟡 Etapa 11 — documental | Merge |
| **#22** | 🟡 aberto há várias etapas | ⚠️ **NÃO está superado.** Carrega 489 linhas que não existem em `main`: plano de consolidação, adapter `email_captura.py` e 204 linhas de teste. **Fechar destruiria trabalho** — precisa ser avaliado, não descartado |

## 5. Riscos, em ordem

| # | Risco | Onde está descrito |
|---|---|---|
| 1 | 🔴 **PII em 40 pontas de branch** e no histórico de `main` | `PII_HISTORICO_PLANO.md` |
| 2 | 🔴 **`480` fixo** — só o Airtable calcula extra, e só ele ignora 12x36 | ANEXO B §B.5 (AT-21) |
| 3 | 🔴 **Make.com ativo sem `try/catch`** — falha silenciosa | ANEXO B §B.6 (AT-12) |
| 4 | 🔴 **Batida ímpar → `BLANK()`** sem alarme | `AIRTABLE_LOGICA_OCULTA.md` §3 |
| 5 | 🟠 **72% de `Folha de Ponto`** calculado dentro do Airtable | `BANCO_PROPRIO_MODELO.md` §2 |
| 6 | 🟠 **`F_FUNC_STATUS`** escrito fora do código, lido pelo `app.py` | mestre §0-H.7 |

## 6. Gates humanos abertos

| Gate | Decisão |
|---|---|
| 🔴 Histórico do Git | Sanear por avanço, reescrever, ou aceitar o risco |
| 🔴 Jornada `480` / 12x36 | Regra trabalhista com efeito retroativo em folha |
| 🔴 Make.com | Manter · **instrumentar** · migrar · descomissionar |
| 🔴 Merge do PR #41 | Correção funcional |
| 🟠 Postgres real | Decisão financeira — `render.yaml` é `plan: free` |
| 🟠 `Locais` = `Posto de Trabalho`? | `BANCO_PROPRIO_MODELO.md` §8.3 |
| 🟠 ADR `Documento` vs. `Item de Ingestão` | `CLAUDE.md` §5 |
| 🟠 40 branches / apagar branch | `CLAUDE.md` §9 |

## 7. O que só a interface resolve

Nenhuma ferramenta desta sessão alcança:

1. **Filtros das 10 views** e **condições dos ramos** — Airtable.
2. **Confirmar que `Automation 1` está mesmo vazia** — Airtable.
3. **O que o cenário do Make.com faz** — Make.com. Bloqueia 3 das 4 opções.
4. **Produção** — rede.

## 8. Próxima ação de maior valor

**Instrumentar o `PROCESSAR ARQUIVOS` com tratamento de erro.**

É o único item que é, ao mesmo tempo: risco 🔴 ativo em produção, de
correção pequena, sem mudar o caminho feliz, e que **não depende** de
nenhuma decisão de negócio pendente. Mata AT-12 sem tocar em jornada,
folha ou fornecedor.

⚠️ Continua sendo **escrita no Airtable** — gate de `CLAUDE.md` §6, com
autorização por fase cumprindo (a)–(f).
