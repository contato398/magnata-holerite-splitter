# HANDOFF — ponto de entrada para a próxima sessão

**Gerado na Etapa 13, 2026-08-24.**

Uma sessão nova deve conseguir continuar **lendo só este arquivo e os 4
canônicos abaixo** — sem a conversa Macro 6A, que está encerrada.

> Este arquivo **não duplica** a Central Command. Ele aponta.

---

## 0. Protocolo operacional — SESSION_START / SESSION_END

**SESSION_START** (copiar isto para o início de uma sessão nova):

```
1. Ler: HANDOFF.md + ESTADO.json + INDEX.md — nada mais, de início.
2. Rodar: python scripts/ci/central_command_sensor.py
   (reporta main_sha real, divergência, e o bloco `contexto` —
   status NORMAL/ATENCAO/TROCAR_SESSAO do próprio bootstrap).
3. Código específico → Graphify (ARQUITETURA_SNAPSHOT.json), nunca
   ler o repositório inteiro para localizar um símbolo.
4. Detalhe (TAXONOMIA_MEMORIA/MATRIZ_AUTONOMIA/mestre/histórico) só
   quando a tarefa exigir — não por precaução.
```

**SESSION_END** (checklist de fechamento, curto de propósito):

```
1. ESTADO.json já reflete a realidade? (rodar o sensor de novo)
2. HANDOFF.md §1 bate com o que mudou nesta sessão? Atualizar só os
   fatos que mudaram — não reescrever o resto.
3. Branch, commits, PR: registrados em §3/§4 abaixo?
4. Alguma divergência nova encontrada (doc vs. código, não só
   número)? Registrar — nunca corrigir em silêncio (CLAUDE.md §2).
5. Próxima ação de maior valor (§8) ainda é a certa, ou mudou?
```

`scripts/ci/medir_contexto.py --json` mede os 3 tiers acima em números;
não precisa ser lido para seguir o protocolo, só existe para quem quer
o dado exato.

## 1. Onde o repositório está

> ⚠️ **Os números abaixo são de 2026-08-24 e envelhecem.** Não confie
> neles: **execute `python scripts/ci/central_command_sensor.py`** — ele
> compara o estado real com `ESTADO.json` e diz o que mudou, incluindo
> o bloco `contexto` (Etapa 13, ver abaixo).

| | |
|---|---|
| **`main`** | `073e39d` — *Merge pull request #62* (Gmail Readonly Shadow V1) |
| **Suíte** | **712 passando / 1 skip / 0 falhando** (verificado nesta sessão, `fix/contexto-progressivo` — inclui os 22 testes novos desta etapa) |
| **CI** | 3 workflows: governança (15/15 gates), `pytest`, **`orquestrador-sensor.yml`** (novo — ver §3) |
| **PII na árvore atual de `main`** | ✅ **nenhuma** (não reauditado a fundo nesta etapa, herdado) |
| **Central Command** | 30 documentos + `ESTADO.json` + `ARQUITETURA_SNAPSHOT.json` + `AUDITORIA_ORQUESTRADOR.jsonl` (novo) |
| **Graphify** | ✅ regenerado em cópia isolada após o PR #62: 88 arquivos, 15 módulos, 2.566 arestas `EXTRACTED`, nenhuma violação de acoplamento; inclui `email_gmail_readonly.py` |
| **Produção** | ❌ **NÃO VERIFICÁVEL** — não testado nesta etapa (herdado de Etapa 12) |
| **Grande Orquestrador** | 🟢 **NÚCLEO EXECUTÁVEL EXISTE** (`magnata_os/orquestrador/`) + **gatilho automático via GitHub Actions já mesclado** (PRs #45, #46, #47) — ver correção declarada abaixo |
| **Contexto (Etapa 13)** | TIER 0 ≈ 6.330 tokens — `status_contexto: NORMAL` (medido novamente após o PR #62) |
| **Gmail Readonly Shadow V1** | ✅ presente em `main`, inerte e somente leitura; adapter e testes específicos/integrados vieram pelo PR #62 |
| **PRs abertos** | **Não reconfirmado ao vivo nesta sessão** (sem acesso a `gh`/API do GitHub) — tratar como `LIVE_STATE` a reconsultar, nunca herdar o "Nenhum" da Etapa 12 |

### Correção declarada (Etapa 13, 2026-08-24)

`ORQUESTRADOR.md` §6.2 e `MATRIZ_AUTONOMIA.md` §4 (Etapa 12) afirmam que
**"nenhum gatilho automático roda sozinho"** e que isso "não foi
construído". **Superado, com evidência em `main`:** o commit `cb835cb`
("núcleo mínimo executável") e as duas fusões seguintes — `PR #46`
(`fix/orquestrador-nucleo-motor`) e `PR #47`
(`fix/orquestrador-gatilho-ci`) — já implementaram exatamente essa peça:
`magnata_os/orquestrador/` (motor de eventos, política de autonomia,
idempotência, retry) + `.github/workflows/orquestrador-sensor.yml`
(cron a cada 6h, abre PR, nunca commita em `main`, nunca mescla
sozinho). Nenhum texto anterior foi reescrito — os dois documentos
citados continuam com a afirmação original; esta é a correção, não uma
edição silenciosa. `ORQUESTRADOR.md` §6.2 e `MATRIZ_AUTONOMIA.md` §4
**precisam de uma etapa de auditoria dedicada** para reconciliar o texto
inteiro — isto aqui só registra que a lacuna que ambos descrevem como
aberta já foi fechada em código.

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

## 3. Merges recentes

**Após a Etapa 13 — evidência local em `main`:**

| PR | O que trouxe |
|---|---|
| **#62** | Gmail Readonly Shadow V1 inerte, adapter e testes — **MESCLADO** em `073e39d` |

**Etapa 13 (2026-08-24) — visíveis por evidência local de `git log`, não por consulta ao GitHub:**

| PR | O que trouxe |
|---|---|
| **#45** | Fundação do Orquestrador (`fix/etapa12-orquestrador-fundacao`) — **MESCLADO** |
| **#46** | Núcleo executável do Orquestrador — motor, eventos, política de autonomia, retry (`fix/orquestrador-nucleo-motor`) — **MESCLADO** |
| **#47** | Gatilho automático via GitHub Actions, sem sessão (`fix/orquestrador-gatilho-ci`) — **MESCLADO**. Fecha `MATRIZ_AUTONOMIA.md` §4 — ver correção declarada acima |

**Etapa 13 (2026-08-24) — desta sessão, branch `fix/contexto-progressivo`:**

- `scripts/ci/medir_contexto.py` + testes — mede TIER 0/1/2 de contexto e classifica NORMAL/ATENCAO/TROCAR_SESSAO.
- `scripts/ci/central_command_sensor.py` estendido — `coletar()` agora inclui `contexto`, `graphify_snapshot_status`, `session_handoff_freshness`. Flui automaticamente para `ESTADO.json` via `magnata_os/orquestrador/acoes/atualizar_auto_fact.py`, já existente — nenhuma mudança nesse caminho foi necessária. Testado ponta a ponta (`scripts/ci/orquestrador_sensor_ci.py`) em cópia isolada.
- Este HANDOFF.md — protocolo SESSION_START/END (§0) + correção declarada acima.

**Etapa 12 (2026-08-23):**

| PR | O que trouxe |
|---|---|
| **#41** | Correção do sensor (baseline não some mais sem `--com-testes`) — **MESCLADO** |
| **#22** | Adapter de captura de e-mail (Módulo 01) — **MESCLADO**. Adapter em `main`, **inerte** — nenhum caller real |
| **#44** | Central Command reconciliada com o merge do #22 |

## 4. PRs abertos

**Não reconfirmado ao vivo nesta sessão** — sem `gh`/API do GitHub disponível. O PR desta sessão (`fix/contexto-progressivo`) ainda não foi aberto no momento em que este HANDOFF foi escrito — ver §17 do relatório da missão para o link, se já existir quando você ler isto. Trate qualquer contagem de "PRs abertos" como `LIVE_STATE` (`TAXONOMIA_MEMORIA.md`) — reconsulte, nunca herde este número.

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
| ~~8~~ | ~~Nenhum gatilho automático aciona sensor/Graphify sem sessão no meio~~ — **RESOLVIDO na Etapa 13**, ver correção declarada em §1 | `MATRIZ_AUTONOMIA.md` §4 (texto do documento em si ainda não reconciliado) |
| 9 | 🟡 **`ORQUESTRADOR.md` §6.2 e `MATRIZ_AUTONOMIA.md` §4 desatualizados** — descrevem o gatilho automático como inexistente, e já existe em `main` desde `cb835cb`/PR #45-47 | Correção declarada, §1 acima — reconciliação de texto completa ainda pendente |

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
| ~~🟡 Automatizar disparo do sensor/Graphify sem sessão no meio~~ | **RESOLVIDO na Etapa 13** para o sensor (`.github/workflows/orquestrador-sensor.yml`) — Graphify continua fora de CI por desenho (`GRAPHIFY.md` §6 restrição 3, não um gate pendente) |
| 🟠 Reconciliar o texto de `ORQUESTRADOR.md` §6.2 e `MATRIZ_AUTONOMIA.md` §4 com o Orquestrador já existente | Auditoria dedicada — fora do escopo desta missão de contexto |

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

**Dentro do que uma sessão de código alcança hoje** (Etapa 13,
2026-08-24): a lacuna de infraestrutura de disparo automático (item
acima, Etapas 12→13) está fechada. As duas maiores lacunas que restam
são:

1. **Reconciliar `ORQUESTRADOR.md` §6.2 e `MATRIZ_AUTONOMIA.md` §4** com
   o Orquestrador que já existe em código — auditoria de texto, sem
   risco, sem gate humano (é documentação alcançando o código, não o
   contrário).
2. **Adicionar mais `TipoEvento` ao Orquestrador** (ex.: `PR_MESCLADO`,
   `SUITE_DIVERGIU`, já previstos em `politica_autonomia.py` mas sem
   `detectar_evento`/Ação implementados) — cada um exige decisão
   explícita registrada em `DECISIONS.md` antes de ganhar
   `EXECUTE_SAFE` (`politica_autonomia.py`, comentário do próprio
   código) — **gate humano por desenho, não por omissão**.
