# PRS_AND_BRANCHES — inventário completo

**Etapa 3, 2026-08-22.** Estado verificado contra a API do GitHub
(`state=all`) e contra `git merge-base --is-ancestor` executado uma a
uma sobre as 32 branches remotas. **PR mais recente existente: #30.**
Não há PR acima disso.

**Aviso de leitura:** o campo `merged` da API vem `false` até para PRs
mesclados. O sinal confiável é `merged_at`. Todo este inventário usa
`merged_at`, não `merged`.

---

## 1. Os 30 PRs

**Mesclados — 25:** #1 #2 #3 #4 #5 #6 #7 #8 #9 #10 #11 #13 #14 #15 #17
#18 #19 #23 #24 #25 #26 #27 #28 #29 #30.

### Abertos — 2

| PR | Branch | Base | Arquivos | Conteúdo | Decisão recomendada |
|---|---|---|---|---|---|
| **#20** | `fix/status-funcionario-pii` | `main` @ `60240b1` | `app.py` (+17/−16) + 1 `.gitblob` | Restaura `vinculo_nao_ativo`/`vinculo_indeterminado` em `_status_funcionario_elegivel` | **Rebasear e decidir.** Único item que limpa 6 falhas vermelhas da suíte. 18 commits atrás de `main` |
| **#22** | `fix/plano-modulo01-email-captura` | `main` @ `60240b1` | 3 arquivos novos, **nenhum toca `app.py`** | Plano de consolidação Ingestão→Distribuição (128 linhas) + `adapters/email_captura.py` (157) + teste com 7 casos (204) | **Decidir.** Risco baixo: aditivo, roda em paralelo ao Gmail Apps Script, não substitui nada |

### Fechados sem merge — 3

| PR | Branch | O que houve | Conteúdo perdido? |
|---|---|---|---|
| **#12** | `feat/magnata-os-claude-powerpack` | Fechado 2026-08-03T17:16:01Z, **2 min antes** de #13 ser mesclado | **SIM — 10 documentos fundacionais.** #13 trouxe o CI de governança e o índice, mas não a fundação que o índice referencia. Ver [`FOUNDATION.md`](FOUNDATION.md) |
| #16 | `claude/magnata-email-reconciliation-hru0jm` | Reaberto como #17, mesclado | Não |
| #21 | `claude/evolution-api-instances-1s9raa` | Reaberto como #22 (mesmo SHA `3d550d1`), segue aberto | Não |

**#12 é o único caso de perda real.** Os outros dois são
reabertura administrativa com conteúdo preservado.

---

## 2. As 8 branches remotas fora de `main`

Ordenadas por risco de perda irreversível.

| Branch | À frente | Atrás | Último | Conteúdo | Risco | Decisão recomendada |
|---|---|---|---|---|---|---|
| **`fix/recibos-outros-documentos`** | 10 | **106** | 2026-07-24 | **`docs/historico/` — 31 arquivos, a memória operacional do projeto** (commit `1027fc8`, 2026-07-23) | 🔴 **Crítico** | **Preservar `docs/historico/` antes de qualquer outra coisa.** O código de recibos foi superado por `fix/outros-documentos-fila-dedup` (mesclado); a memória não |
| **`feat/magnata-os-claude-powerpack`** | 20 | 72 | 2026-07-30 | Fundação documental completa + skills/subagentes (PR #12) | 🔴 **Crítico** | Resgate documental puro — estratégia em [`FOUNDATION.md`](FOUNDATION.md) §9 |
| `fix/status-funcionario-pii` | 2 | 18 | 2026-08-17 | Correção da divergência de motivo de bloqueio (PR #20) | 🟠 Alto | Rebasear sobre `main` e decidir |
| `claude/magnata-central-command-0n0713` | 2 | **0** | 2026-08-21 | Central Command Etapas 1-2 | 🟡 Médio | **Já incorporada** nesta linha consolidada. Manter até confirmação |
| `fix/plano-modulo01-email-captura` | 1 | 18 | 2026-08-17 | Plano + adapter de e-mail (PR #22) | 🟡 Médio | Decidir |
| `fix/adr-modulo01-http-wiring` | 1 | 32 | 2026-08-13 | ADR de como expor a API do Módulo 01 via HTTP | 🟡 Médio | 🔍 Auditar conteúdo e decidir |
| `claude/evolution-api-instances-1s9raa` | 1 | 18 | 2026-08-17 | Mesmo SHA de origem do PR #22 | 🟢 Baixo | Conteúdo já vive em #22 |
| `feat/...modulo01-fase5-painel` | 1 | **72** | 2026-07-25 | Painel visual do Módulo 01, Fase 5 | 🟡 Médio | Trabalho pronto, parado há ~4 semanas |

**As 22 restantes** já são ancestrais de `main` — conteúdo integrado,
nenhuma ação necessária. **Nenhuma branch foi apagada nesta etapa.**

---

## 3. Alerta operacional: branches remotas estão sendo apagadas

Durante esta sessão, o `git fetch --prune` registrou:

```
- [deleted]  (none) -> origin/claude/macro-6a-commit-recovery-k7rsly
```

Aquela branch tinha o conteúdo já mesclado em `main`, então nada se
perdeu. **Mas o fato importa:** branches remotas deste repositório
são apagadas na prática. As duas branches marcadas 🔴 acima carregam
conteúdo que existe **em nenhum outro lugar** — se forem apagadas antes
de resgatadas, a perda é permanente.

**SHAs registrados aqui justamente para sobreviver ao apagamento:**

| Conteúdo | Commit | Branch |
|---|---|---|
| `docs/historico/` (31 arquivos) | `1027fc8a0c774de88715e6fecc447fc3ae1a94f4` | `fix/recibos-outros-documentos` (HEAD `e1fefb3`) |
| Fundação documental (10 docs) | HEAD `053acada09dfc70bda71d2293aacbf2bca9ed43e` | `feat/magnata-os-claude-powerpack` |
| Central Command Etapas 1-2 | `ea95ab6` (Etapa 1) · `27d12b1` (Etapa 2) | `claude/magnata-central-command-0n0713` |

---

## 4. Conformidade de governança das branches

Verificado com `is_authorized_branch()` de `.magnata/patterns.sh`:

| Branch | Passa no gate? |
|---|---|
| `fix/*` (todas) | ✅ — `^fix/[a-z0-9][a-z0-9-]*$` |
| `feat/magnata-os-claude-powerpack` | ✅ — nome exato na enumeração |
| `feat/...modulo01-fase5-painel` | ❌ — `feat/` exige entrada exata, e não tem |
| `claude/macro-6a-*` | ✅ |
| `claude/magnata-central-command-0n0713` | ❌ |
| `claude/evolution-api-instances-1s9raa` | ❌ |

As branches ❌ só puderam receber commits porque os hooks locais não
estavam ativos naquelas sessões. Não é irregularidade de conteúdo — mas
significa que **o CI de governança rejeitaria esses commits**, e é uma
razão adicional para não tratar essas branches como caminho de entrada
para `main` sem antes reposicionar o trabalho.

---

## 5. Reclassificação funcional — Etapa 4, 2026-08-22

O pedido desta fase foi explícito: **não tratar o PR #20 como "próximo PR"
por numeração.** A numeração é ordem de abertura, não ordem de
importância nem sequência obrigatória. O repositório já tem PRs
posteriores mesclados (#23 a #30) que passaram por cima dele.

Reclassificação pelo estado real do GitHub, por **função e pendência**:

| Classe | PRs | O que significa operacionalmente |
|---|---|---|
| **MERGED** | #1–#11, #13–#15, #17–#19, #23–#30 (25) | Conteúdo em `main`. Nenhuma ação |
| **OPEN** | #20, #22 | Aguardam decisão humana |
| **CLOSED WITHOUT MERGE** | #12, #16, #21 | #16 e #21 foram reabertos; **#12 não** |
| **SUPERSEDED** | #16 → por #17 · #21 → por #22 · #12 → **parcialmente** por #13 | #13 trouxe o CI e o índice; **não** trouxe a fundação que o índice cita |
| **CONTÉM TRABALHO NÃO INCORPORADO** | **#20**, **#22**, **#12** | Ver abaixo |

### 5.1 Trabalho ainda não incorporado — por função

**#12 — fundação documental.** ✅ **Resolvido nesta etapa.** Os 10
documentos e os 8 relatórios de Etapa foram resgatados para `main` com
proveniência. Resta apenas `.claude/` (skills, subagentes, matriz), fora
de `ALLOWED_PATHS`.

**#20 — divergência no rótulo do motivo de bloqueio.**
Registrado **por função, não por número**:

- **Função:** `_status_funcionario_elegivel` devolve
  `'status_veio_inativo'`; o resto do sistema e os testes esperam
  `'vinculo_nao_ativo'`/`'vinculo_indeterminado'`.
- **Efeito hoje:** o bloqueio de vínculo inativo **funciona** — não há
  risco de assinatura indevida. O que quebra é o **rótulo**, e com ele
  **6 testes vermelhos permanentes** que mascaram regressão nova.
- **Onde a correção existe:** `origin/fix/status-funcionario-pii`,
  2 arquivos, +17/−16 em `app.py`, **18 commits atrás de `main`**.
- **Independência:** esta pendência **não depende** do número do PR. Se
  o #20 for fechado, a correção continua necessária e continua
  disponível naquela branch. Pode ser reaberta como PR novo sobre
  `main` atual sem nenhuma perda.
- **Gate:** toca `app.py` — legado protegido, `CLAUDE.md` §7.

**#22 — direção do Módulo 01 (captura de e-mail).**

- **Função:** registra a decisão de não construir automação nova no
  Make.com e entrega um adapter de e-mail que roda **em paralelo** ao
  Gmail Apps Script, sem substituir nada.
- **Risco de não agir:** a análise se perde e a próxima sessão a refaz.
- **Independência:** aditivo, não toca `app.py`, 3 arquivos novos.

### 5.2 O que mudou nesta reclassificação

A leitura anterior colocava o #20 como "próxima ação de maior valor" em
parte pela numeração baixa. **Corrigido:** as ações de maior valor eram
as de preservação (executadas nesta etapa), porque envolviam risco de
perda irreversível. O #20 é a melhor ação **de código** disponível — mas
código sempre pode ser reescrito; memória perdida, não.

---

## 6. Estado pós-merge — Etapa 6, 2026-08-22

**PR #31 MESCLADO.** `main` = `9f8a53f`. Último PR existente: **#31**.

| Classe | PRs |
|---|---|
| **MERGED** | #1–#11 · #13–#15 · #17–#19 · #23–#31 **(26)** |
| **OPEN** | **#20** · **#22** |
| **CLOSED WITHOUT MERGE** | #12 · #16 · #21 |
| **SUPERSEDED** | #16→#17 · #21→#22 · **#12 → resolvido pelo #31** |
| **WORK STILL UNIQUE** | #20 · #22 · e 3 branches sem PR (abaixo) |

### 6.1 Branches — classificação final

| Branch | Conteúdo único | Classe | Risco | Ação |
|---|---|---|---|---|
| `fix/status-funcionario-pii` | `app.py` +17/−16 · 1 `.gitblob` | **UNIQUE WORK** | 🟠 Alto | **Patch aplica limpo em `main` e leva a suíte a 642/0 — provado em worktree isolado.** Gate: toca `app.py` |
| `fix/plano-modulo01-email-captura` | plano + adapter de e-mail + 7 testes | **UNIQUE WORK** | 🟡 Médio | Aditivo, não toca `app.py`. Precisa decisão |
| `feat/...modulo01-fase5-painel` | **~50 arquivos de frontend** + doc da Fase 5 | **UNIQUE WORK** | 🟠 Alto | Muito trabalho pronto, parado desde 25/07. **Nunca auditado em profundidade** |
| `fix/adr-modulo01-http-wiring` | `docs/decisoes/modulo01-fiacao-http.md` (113 linhas) + 5 linhas em `patterns.sh` | **UNIQUE WORK** | 🟡 Médio | Resgatável como PR documental — **mas exige alterar `ALLOWED_PATHS`**, que é decisão de governança |
| `feat/magnata-os-claude-powerpack` | só `.claude/` (skills, agentes, matriz) | **PARCIALMENTE SUPERSEDED** | 🟡 Médio | Documentos resgatados pelo #31. Resta `.claude/`, fora de `ALLOWED_PATHS` |
| `fix/recibos-outros-documentos` | **29 históricos brutos com PII** | **UNIQUE WORK** | 🔴 **Crítico** | **NÃO APAGAR.** Lição já preservada; texto bruto não. Gate: desidentificação |
| `claude/magnata-central-command-0n0713` | Central Command Etapas 1-2 | **SUPERSEDED** | 🟢 Baixo | Conteúdo em `main` pelo #31. `SAFE TO ARCHIVE` — mas só com sua decisão |
| `claude/evolution-api-instances-1s9raa` | mesmo SHA do #22 | **SUPERSEDED** | 🟢 Baixo | `SAFE TO ARCHIVE` |

**Nenhuma branch foi apagada.** `SAFE TO ARCHIVE` é classificação, não
autorização — exclusão de branch é gate humano.

---

## 7. Estado pós-PR #41 — auditoria e reconciliação do PR #22, 2026-08-23

Nada abaixo reescreve as seções 1-6; corrige e estende, com data.

**PR #41 MESCLADO.** `main` = `98e32d2`. Suíte 649/0.

### 7.1 PR #22 — auditoria adversarial completa

Decomposto nos 3 arquivos que carrega, cada um auditado item a item
(idempotência, adapter/driver, erro por anexo, falha de rede, PII,
efeitos colaterais) — não apenas classificado em bloco:

| Arquivo | Classificação | Achado |
|---|---|---|
| `docs/decisoes/plano-consolidacao-ingestao-distribuicao.md` | **B — AINDA VÁLIDA E ÚTIL**, com **C — precisava atualização pontual** | Recomendação (não construir no Make.com; priorizar Módulo 01) segue de pé — nada no repositório desde 17/08 a contradiz; a linha de `Status` estava desatualizada ("não implementado" — corrigida, factual) |
| `magnata_os/documental/modulo01/adapters/email_captura.py` | **B — AINDA VÁLIDA E ÚTIL** | Respeita adapter/driver (`Protocol`, zero import de cliente real), reusa `ServicoCriacaoLote` (porta oficial, não duplica nada), idempotência corretamente delegada e comprovada por teste. **Gaps reais encontrados:** falha de rede na busca (`buscar_novas_mensagens`) não tinha tratamento nem teste (fail-loud, agora documentado e travado por teste); "erro parcial" dentro de um lote não tinha teste. Nenhum dos dois exigiu mudar comportamento — só documentar/testar o que já existia |
| `test_magnata_os_documental_modulo01_email_captura.py` | **C — válida, precisava atualização** | 7→10 casos. 3 novos: anexo vazio/inválido, erro parcial, falha de API propagando sem ser engolida. Verificado adversarialmente (defeito reintroduzido de propósito, testes pegaram) |

**Nenhum código único deste PR já existe em `main` por outro caminho**
— confirmado por busca (`email_captura`, `plano-consolidacao-ingestao`
ausentes em `main` antes desta reconciliação).

### 7.2 Ação tomada

PR #22 rebaseado sobre `main` (`98e32d2`) em worktree isolado — **zero
conflito** (aditivo puro). Suíte geral 649→**659**, 0 regressão.
Governança 15/15 (a única marca "bloqueada" numa rodada foi o nome da
branch de trabalho local, não a branch real do PR — falso alarme,
descartado e confirmado). `git diff --check` limpo. Sem CPF, sem
segredo, `app.py` intocado. `mergeable_state`: **`clean`**. CI
(`pytest`, governança): **verde**.

### 7.3 Estratégia escolhida — **B (atualizar) já executada; merge é gate humano**

Não é **A (merge direto)** porque não chegou inalterado — recebeu 3
testes novos e 1 correção factual. Não é **C (dividir)** — os 3
arquivos são uma unidade coesa (doc explica o porquê do adapter; testes
sem o adapter não têm sentido; splitar perderia a proveniência). Não é
**D/E** — nada aqui está superseded ou obsoleto.

**Por que não foi mesclado automaticamente**, apesar de tecnicamente
tão seguro quanto o PR #41: PR #41 era uma correção isolada de
ferramenta interna (sensor). O PR #22 introduz **capacidade nova** (um
adapter que ainda não existe em `main`) e **formaliza uma decisão de
direção** ("não construir no Make.com; priorizar Módulo 01") num
documento que vira fonte citável. Mesmo sendo aditivo, testado e
zero-risco de produção (nada o chama ainda), isso é "decisão
arquitetural"/"mudança de escopo de capacidade", que `CLAUDE.md` §12-I
e a missão desta etapa (§13) mantêm como gate humano — a própria
classificação anterior desta Central Command (§5, "**Decidir.**") já
apontava nessa direção antes desta auditoria.

**Atualiza:** `DECISIONS.md` DEC-009 · `WORK_IN_PROGRESS.md` WIP-004 ·
`NEXT_ACTIONS.md` NXT-005.
