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
