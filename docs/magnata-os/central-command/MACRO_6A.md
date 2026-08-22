# MACRO 6A — reconciliação da Recuperação

**Etapa 3, 2026-08-22.** Responde ao pedido de classificar a Recuperação
Macro 6A em três grupos: **INCORPORADO**, **SUPERADO**, **AINDA NÃO
CONFIRMADO**.

## O que foi a Macro 6A

Auditoria e esteira documental segura. Entrou em `main` pelo **PR #19**,
mesclado em **2026-08-12T16:16:09Z**, base `261f4e5`.

A recuperação em si foi um episódio de engenharia: um patch precisava ser
aplicado, validado e publicado a partir de um container remoto sem
credenciais de GitHub. Gerou 7 relatórios e um bundle Git de 1,4 MB.

**Onde essas fontes vivem hoje:** ⚠️ **apenas em diretório de scratch de
sessão** — `RELATORIO_MACRO_6A.md`, `FINAL_STATUS.md`,
`FINAL_DELIVERY_REPORT.md`, `CLOSURE_SUMMARY.md`, `EVIDENCE_REPORT.md`,
`DETAILED_DIFFS.md`, `EXTERNAL_BLOCKER_REPORT.md`, `GIT_INVENTORY.txt`,
`AUDIT_INITIAL.txt`, `AUDIT_CURRENT_STATE.txt` e
`macro-6a-fix-bundle.git`. **Nenhum está versionado.** Scratch é
efêmero: quando o container for recuperado, some tudo.

---

## ✅ INCORPORADO — está em `main`, verificado

| Item | Evidência |
|---|---|
| **Código da Macro 6A** | PR #19 mesclado, base `261f4e5` |
| **8 arquivos de teste, 167 testes** | `test_competencia_fiscal.py` (23) · `test_fase_c_async_separar.py` (13) · `test_fila_envios_v2_23.py` (50) · `test_idempotencia_esteira.py` (14) · `test_idempotencia_pendencia_kit.py` (20) · `test_kit_admissao_identidade.py` (29) · `test_sanitizacao_v2_20.py` (7) · `test_seguranca_rotas_dp_fiscal.py` (11) |
| **Autorização por blob de `app.py`** | `.magnata/app-py-authorizations/macro-6a.gitblob`, blob `4dc30fc6b72c5d873ef6dc182992555af92e201e`, base `261f4e5`, 2026-08-12 |
| **Autorização de branch `claude/macro-6a-*`** | `^claude/macro-6a-[a-z0-9-]*$` em `AUTHORIZED_BRANCHES` (commit `e4ad857`) — **a Macro 6A deixou uma regra permanente de governança no repositório** |
| **8 exceções nominais em `ALLOWED_PATHS`** | Os 8 testes, cada um por igualdade exata de string, com o comentário explicando por que não é padrão genérico |
| **As duas branches da recuperação** | `fix/macro6a-auditoria-esteira-documental` e `claude/macro-6a-commit-recovery-k7rsly`: confirmadas ancestrais de `origin/main` por `git merge-base --is-ancestor` |

**Conclusão do grupo:** o conteúdo técnico da Macro 6A está
integralmente em `main`. Nada de código ficou para trás.

---

## ❌ SUPERADO — resolvido depois, não precisa de ação

| Item | Estado registrado no relatório | O que aconteceu depois |
|---|---|---|
| **Bloqueio de push (403 Forbidden)** | `EXTERNAL_BLOCKER_REPORT.md`: sandbox sem credenciais GitHub, push impossível | **Superado.** O PR #19 foi aberto e mesclado em 2026-08-12. O bundle portátil de 1,4 MB era plano B e nunca precisou ser usado |
| **Blob autorizado `afcb13e044f222f86985663f3cf3fe74ab048fd4`** | `RELATORIO_MACRO_6A.md` §2 | **Superado.** O `.gitblob` em `main` registra `4dc30fc6…` — o blob foi recalculado sobre a versão final de `app.py`. Divergência esperada, não erro |
| **"Limitação de ambiente: blinker impede instalar Flask"** | `FINAL_STATUS.md` §3 — testes funcionais não puderam rodar | **Superado.** Hoje a suíte roda: 642 testes coletados. A limitação era do container daquela sessão |
| **"15/15 gates"** | `FINAL_STATUS.md` §1 | **Superado por evolução.** Hoje são **14** validações no `pre-commit` e **16** gates no CI. A contagem mudou depois da Etapa 6 do Powerpack |
| **Branch remota `claude/macro-6a-commit-recovery-k7rsly`** | Branch de trabalho da recuperação | **Apagada no remoto** durante esta sessão (registrado por `git fetch --prune`). Sem perda: conteúdo já em `main` |

---

## 🔍 AINDA NÃO CONFIRMADO

| Item | Por que não pôde ser fechado |
|---|---|
| **Os 7 relatórios e o bundle nunca foram versionados** | Estão só em scratch. Não há como confirmar que sobrevivem — e a evidência aponta para o contrário. **Esta é a única lacuna acionável do grupo** |
| **Conteúdo de `DETAILED_DIFFS.md`, `EVIDENCE_REPORT.md`, `CLOSURE_SUMMARY.md`, `FINAL_DELIVERY_REPORT.md`** | Localizados e listados nesta etapa; conteúdo lido apenas parcialmente. Podem conter decisões de detalhe ainda não incorporadas |
| **Integridade do bundle** | `EXTERNAL_BLOCKER_REPORT.md` registra SHA-256 `b0605e0c…`; não foi reverificado |
| **6 das 19 falhas atuais tocam `test_fase_c_async_separar.py`, entregue pela Macro 6A** | São falhas de ambiente (`celery` ausente), **não** defeito da Macro 6A — mas isso é inferência por tipo de erro, não execução com `celery` instalado nesta etapa |

---

## Recomendação

**Versionar os relatórios da Macro 6A** — é a única ação que este grupo
ainda pede. O conteúdo técnico está seguro em `main`; o **registro de
como a recuperação foi feita** não está em lugar nenhum durável.

Não é urgente como a fundação documental ou `docs/historico/` (que
carregam decisões insubstituíveis). É importante porque é o único
registro de um procedimento que pode precisar ser repetido: publicar
trabalho de um ambiente sem credenciais.

**Fica como proposta, não executada** — versionar artefatos de scratch
significa decidir o que é registro institucional e o que é ruído de
sessão, e isso é decisão humana.
