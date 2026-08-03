# Magnata AI Engineering Powerpack — Etapa 6

**Relatório de Implementação: CI de Governança e Qualidade**

**Data:** 2026-07-29 (fechamento final em 2026-08-03 — ver seção 12)
**Status:** MESCLADO EM `main` — PR #13, merge commit `d616d521082db5d97e1824daf14c6cfdb4618f31`
**Escopo:** Automação de validação de governança e conformidade documental
**Branch:** `feat/magnata-os-claude-powerpack` (implementação original) →
`feat/magnata-os-etapa6-governanca` (PR #13, mesclado) →
`feat/magnata-os-etapa6-estabilizacao` (estabilização pós-merge, seção 12)
**HEAD-base preservado:** `2debc13ea0d6b869e6be93eded5effe87e45b8a1`

---

## 1. Objetivo da Etapa

Implementar, a partir do plano aprovado
(`MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6_PLANO.md`), um CI de
governança não invasivo que:

- reutilize as mesmas regras dos hooks locais da Etapa 5, a partir de
  uma única fonte de verdade;
- rode 16 gates de conformidade (segurança, proteção de legado,
  segredos, estrutura documental, modos de arquivo Git);
- não acesse produção, não faça deploy, não grave nada, não use
  segredos.

---

## 2. Arquitetura implementada

```
.magnata/patterns.sh              ← fonte única de verdade (regex, listas)
        │
        ├── importado por ──► .githooks/pre-commit        (barreira local)
        └── importado por ──► scripts/ci/validate_governance.sh  (gates de CI)
                                       │
                                       └── orquestrado por ──► .github/workflows/magnata-governance.yml
```

- `.magnata/patterns.sh` concentra: arquivos protegidos, padrões de
  segredo, padrões documentais proibidos (11º módulo, 9 camadas,
  autonomia %, ADR silenciosa), documentos obrigatórios, hierarquia de
  `CLAUDE.md`, modos Git esperados (755/644) e escopo permitido.
- `scripts/ci/validate_governance.sh` implementa os 16 gates, cada um
  invocável isoladamente (`validate_governance.sh <gate>`) ou em
  conjunto (`report_final`).
- `.github/workflows/magnata-governance.yml` **apenas orquestra** —
  chama cada gate como um step do GitHub Actions, sem lógica de
  detecção própria.
- `scripts/ci/test_governance.sh` roda os 16 gates contra um
  repositório Git temporário e isolado (`/tmp/magnata_governance_test`),
  sem tocar no repositório real.

---

## 3. Arquivos criados e modificados

**Criados:**
- `.github/workflows/magnata-governance.yml`
- `.magnata/patterns.sh`
- `scripts/ci/validate_governance.sh`
- `scripts/ci/test_governance.sh`
- `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md` (este arquivo)
- `docs/magnata-os/MAGNATA_AI_CI_GOVERNANCA.md`

**Modificados:**
- `.githooks/pre-commit` — passou a importar `.magnata/patterns.sh`
  como fonte única para `PROTECTED_FILES` e `ALLOWED_PATHS`; removida
  uma lista própria de arquivos protegidos que duplicava (e, num dos
  três itens, nem sequer batia com) o que a fonte canônica já cobre.
- `docs/magnata-os/README.md` — seção da Etapa 6 atualizada de
  "Planejado" para "Implementado localmente".
- `.githooks/README.md` — referência à fonte única de padrões.
- `docs/magnata-os/MAGNATA_AI_HOOKS_LOCAIS.md` — nota sobre a
  centralização de padrões na Etapa 6.

**Protegidos (confirmados intactos, não tocados):**
- `app.py`
- `magnata_os/documental/modulo01/migrations/**`
- `frontend/CLAUDE.md`, `frontend/assets/brand/**`

---

## 4. Os 16 Gates

| # | Gate | O que verifica |
|---|------|------------------|
| 1 | `branch` | Branch atual é `feat/magnata-os-claude-powerpack` |
| 2 | `protected_app_py` | `app.py` não foi alterado |
| 3 | `protected_migrations` | Migrations do Módulo 01 não foram alteradas |
| 4 | `protected_frontend` | `frontend/CLAUDE.md` e `frontend/assets/brand/` não foram alterados |
| 5 | `secrets` | Nenhum padrão de segredo no diff |
| 6 | `whitespace` | Sem trailing whitespace |
| 7 | `11_module` | Segurança não é declarada como 11º módulo funcional |
| 8 | `9_layers` | Arquitetura não é descrita como "9 camadas" ou "6+3" |
| 9 | `autonomy_percent` | Autonomia não é expressa como percentual abstrato |
| 10 | `adr_silent` | Renomeação Item de Ingestão → Documento não é resolvida em silêncio |
| 11 | `required_docs` | Documentos fundacionais obrigatórios presentes |
| 12 | `claude_hierarchy` | Hierarquia de 4 níveis de `CLAUDE.md` presente |
| 13 | `script_mode_755` | Hooks e scripts de CI com modo Git 100755 |
| 14 | `config_mode_644` | Workflow, `patterns.sh` e docs de governança com modo Git 100644 |
| 15 | `hooks_suite` | Suíte de testes de governança aprovada |
| 16 | `report_final` | Relatório consolidado (soma dos 15 gates) |

---

## 5. Correções realizadas nesta rodada de fechamento técnico

Três pendências concretas, identificadas na revisão do diff staged (não
no plano original):

### 5.1 Testes 13 e 14 eram apenas informativos

`test_governance.sh` continha, para os testes de modo Git, apenas um
aviso (`"Modo de arquivo pode variar por plataforma"`) sem nenhuma
asserção real — os dois "passavam" sempre, independente do
comportamento do validador.

**Correção:** o repositório de teste isolado passou a incluir uma
cópia real de `.githooks/pre-commit` (100755) e do workflow (100644).
Cada teste agora quebra o modo Git de um desses arquivos no índice
(`git update-index --chmod`), executa o gate correspondente
(`script_mode_755` / `config_mode_644`), **exige bloqueio** e restaura
o modo correto. Verificado manualmente fora da suíte: as mensagens de
erro citam o modo exato detectado (`modo git: 100644` /
`modo git: 100755`), confirmando que o bloqueio ocorre pelo motivo
certo, não por acidente.

**Nota de escopo:** o enunciado desta pendência descrevia o Teste 14
como "modo de um script shell do CI para 100644" — mas o próprio nome
do teste ("Workflow sem modo 100644") e o gate 14 do validador
(`config_mode_644`) tratam de arquivos **não-executáveis**, não de
scripts do CI. Optei por testar o gate 14 com o arquivo de workflow
(que é, de fato, um `NON_EXECUTABLE_FILES`), porque a leitura literal
alternativa deixaria o gate `config_mode_644` sem nenhuma cobertura de
teste. Registro a divergência de leitura aqui, não silenciosamente.

### 5.2 Duplicação comprovada em `.githooks/pre-commit`

A validação 3 do hook ("Arquivos sensíveis não podem ser alterados")
mantinha uma lista própria `PROTECTED_FILES` com `app.py`,
`migrations/` e `frontend/assets/brand/` — todos já cobertos pela
validação 6 (que importa a lista canônica de `.magnata/patterns.sh`).
Pior: o item `"migrations/"` usava match de prefixo
(`$file == migrations/*`), que **nunca** bate com o caminho real
protegido (`magnata_os/documental/modulo01/migrations/`) — ou seja,
essa entrada específica nunca funcionou, dava falsa sensação de
proteção.

**Correção:** removidos os três itens duplicados/mortos. Mantidos
`.env`, `secrets.json`, `credentials.json` — que não têm equivalente
na fonte canônica e representam cobertura real, não duplicação.
Verificado: hook continua aprovando as 14 validações contra o diff
real da Etapa 6.

**Divergência residual documentada, não removida:** as validações 4
(segredos), 7 (scratch), 9, 10, 11 e 12 (gates documentais) do hook
mantêm listas de padrão **próprias e paralelas** às de
`.magnata/patterns.sh` — importam a fonte canônica (via `source`), mas
não a consultam para essas validações específicas. Cada uma diverge em
detalhe da versão canônica: em alguns casos a lista canônica é
superconjunto estrito da do hook (11º módulo, 9 camadas — trocar seria
seguro), em outros a relação é bidirecional (segredos, scratch,
autonomia %, ADR silenciosa — cada lado tem item que o outro não tem, e
num caso — ADR silenciosa — a versão canônica é mais **restrita**, não
mais ampla, que a do hook). Não foram unificadas nesta rodada porque a
unificação seria mudança de comportamento maior do que "remover
duplicação comprovada", e não há suíte automatizada dedicada ao hook em
si (só à CI) para validar cada ajuste com segurança. Registrado como
risco remanescente, não escondido.

### 5.3 Documentação (este conjunto de arquivos)

Ver seção 3.

### 5.4 Correção do escopo de diff no CI (rodada seguinte, mesmo dia)

Ver seção 7 — a limitação bloqueante identificada na primeira rodada
desta validação foi corrigida nesta mesma data, numa correção separada
e objetiva, sem tocar no que já estava aprovado (gates, testes 1-14,
modos Git, permissões, documentação anterior).

---

## 6. Resultado da suíte de testes (28 cenários, 15 gates + relatório final + contrato base/head + classificação segredo/arquivo sensível + classificação documental normativo/técnico + execução real em runner de CI)

**Comando:** `bash scripts/ci/test_governance.sh`
**Resultado:** 28/28 testes aprovados, 0 reprovados, 0 SKIP, 0 erro
interno inesperado.

| # | Cenário | Esperado | Obtido | Gate | Parecer |
|---|---------|----------|--------|------|---------|
| 1 | Alteração válida (Markdown) | PASS | PASS | branch | ✓ |
| 2 | app.py alterado | FAIL | FAIL | protected_app_py | ✓ |
| 3 | Migration alterada | FAIL | FAIL | protected_migrations | ✓ |
| 4 | Frontend funcional alterado | FAIL | FAIL | protected_frontend | ✓ |
| 5 | Segredo fictício | FAIL | FAIL | secrets | ✓ |
| 6 | Trailing whitespace | FAIL | FAIL | whitespace | ✓ |
| 7 | 11º módulo | FAIL | FAIL | 11_module | ✓ |
| 8 | 9 camadas | FAIL | FAIL | 9_layers | ✓ |
| 9 | Autonomia % | FAIL | FAIL | autonomy_percent | ✓ |
| 10 | ADR silenciosa | FAIL | FAIL | adr_silent | ✓ |
| 11 | Documento obrigatório ausente | FAIL | FAIL | required_docs | ✓ |
| 12 | CLAUDE.md hierarquia incompleta | FAIL | FAIL | claude_hierarchy | ✓ |
| 13 | Hook sem modo 100755 | FAIL | FAIL | script_mode_755 | ✓ (asserção real, ver 5.1) |
| 14 | Workflow sem modo 100644 | FAIL | FAIL | config_mode_644 | ✓ (asserção real, ver 5.1) |
| 15 | Suíte completa aprovada | PASS | PASS | branch | ✓ |
| 16 | Violação em commit não-final do PR/push (base/head explícitos) | FAIL | FAIL | protected_app_py | ✓ |
| 17 | Intervalo limpo, 2 commits, só arquivos permitidos | PASS | PASS | protected_app_py | ✓ zero falso positivo |
| 18 | Violação no commit intermediário de 3 (push) | FAIL | FAIL | protected_app_py | ✓ cita `app.py` |
| 19 | `base_ref` inexistente, `head_ref` válido | FAIL (erro interno) | FAIL (erro interno, exit 2) | validação de contrato | ✓ |
| 20 | Menção documental a `.env`/`secrets.json`/`credentials.json` em prosa | PASS | PASS | hook VALIDAÇÃO 4 | ✓ zero falso positivo |
| 21 | Arquivo real `credentials.json` no stage | FAIL | FAIL | hook VALIDAÇÃO 3 | ✓ nome sensível continua protegido |
| 22 | Token real (variável de token do GitHub com valor atribuído) em doc permitido | FAIL | FAIL | hook VALIDAÇÃO 4 | ✓ segredo real continua detectado |
| 23 | Menção técnica a "9 camadas" em doc de CI (não normativo) | PASS | PASS | 9_layers | ✓ zero falso positivo |
| 24 | Redefinição de "9 camadas" em documento normativo real | FAIL | FAIL | 9_layers | ✓ zero falso negativo |
| 25 | Segredo real em documento técnico de CI (não normativo) | FAIL | FAIL | secrets | ✓ sem isenção geral de Markdown |
| 26 | Gate 15 em clone limpo, sem hooks instalados em `.git/hooks/` | PASS | PASS | hooks_suite | ✓ autossuficiente, condição real do runner |
| 27 | Gate 16 (relatório final) testa todos os 15 gates | PASS | PASS | report_final | ✓ não aborta em "Testing branch" |
| 28 | Gate de branch com HEAD destacado + `GITHUB_HEAD_REF`/`GITHUB_REF_NAME` | PASS | PASS | branch | ✓ distingue local/push/pull_request |

Suíte roda em repositório Git isolado e temporário
(`/tmp/magnata_governance_test`), nunca no repositório real.

---

## 7. Contrato base/head — completo em todos os eventos do CI

Esta seção substitui a versão anterior (rodada de correção inicial) e
descreve o contrato **final**, aplicado a `pull_request`, `push` e
`workflow_dispatch` sem exceção.

### 7.1 O problema original

Os gates que dependem de "o que mudou" (`protected_app_py`,
`protected_migrations`, `protected_frontend`, `secrets`, `whitespace`,
`11_module`, `9_layers`, `autonomy_percent`, `adr_silent`) usavam,
incondicionalmente:

```bash
git diff --cached --name-only 2>/dev/null || git diff HEAD^..HEAD --name-only 2>/dev/null
```

Em um checkout de CI, nada fica staged, então o fallback
`git diff HEAD^..HEAD` era sempre o caminho executado — só o último
commit, nunca o PR/push inteiro.

### 7.2 Contrato do validador

`validate_governance.sh` aceita `base_ref`/`head_ref` como 2º/3º
argumento posicional:

```bash
scripts/ci/validate_governance.sh <gate> [base_ref] [head_ref]
```

Três estados possíveis, verificados **antes de qualquer diff**:

1. **Ambos fornecidos e válidos** (`git cat-file -e "<ref>^{commit}"`
   confirma que cada um resolve para um commit real) → os gates usam
   `git diff base_ref...head_ref` (merge-base, mesma semântica do
   "Files changed" do GitHub).
2. **Nenhum fornecido** → `MODO LOCAL — INTERVALO PADRÃO LIMITADO` é
   impresso, e o script cai no comportamento antigo (staged, ou
   `HEAD^..HEAD`) — **só acontece em execução manual/local**, nunca
   quando o workflow chama o script.
3. **Só um dos dois fornecido, ou uma referência inválida** →
   `✘ ERRO INTERNO` impresso, `exit 2` — nunca é tratado como
   aprovação nem como bloqueio de gate comum (que usa `exit 1`).

### 7.3 Contrato do workflow, por evento

O step "Determinar base e head do diff" **falha o job imediatamente**
(sem rodar nenhum gate) se não conseguir produzir um `base`/`head`
válido — nenhum dos três eventos pode silenciosamente cair no
fallback local:

- **`pull_request`:** `base = github.event.pull_request.base.sha`,
  `head = github.event.pull_request.head.sha`. Cobre todos os commits
  do PR, não só o último.
- **`push`:** `base = github.event.before`, `head = github.sha`.
  **Push de branch nova** (`before` é SHA nulo): calcula
  `git merge-base origin/${MAIN_BRANCH} head` (branch principal
  configurável via `env.MAIN_BRANCH`, hoje `main`). Se `origin/main`
  não existir localmente, ou não houver merge-base, o step falha com
  `::error::` e `exit 1` — **nunca** usa `HEAD^` nem árvore vazia como
  substituto automático.
- **`workflow_dispatch`:** exige os inputs obrigatórios `base_ref` e
  `head_ref` (`required: true` na definição do evento). O step valida
  que nenhum dos dois está vazio e que ambos resolvem para commits
  reais (`git cat-file -e`) — se qualquer verificação falhar, o step
  falha com `::error::` e `exit 1`. Execução manual sem esses dois
  inputs não é possível.
- **Evento inesperado** (nenhum dos três): falha explicitamente —
  nunca deixa `base`/`head` vazios passarem adiante.

Os gates 2–10 e 16 (relatório final) recebem `base`/`head`; os gates
1, 11–15 não dependem de diff e não foram alterados. Os steps "Gate
16" e "Resultado" (antes `if: always()`) agora só rodam se o step de
cálculo de base/head **de fato teve sucesso**
(`steps.diffrange.outcome == 'success'`) — do contrário, o
`if: always()` antigo mascararia exatamente esse tipo de falha,
imprimindo "sucesso" mesmo com o contrato quebrado.

### 7.4 Evidência

- **Teste 16:** violação no primeiro de dois commits é detectada com
  `base_ref`/`head_ref` explícitos (sem eles, ainda aprova — modo
  local, comportamento preservado de propósito).
- **Teste 17:** intervalo limpo de dois commits (só arquivos
  permitidos) aprova — zero falso positivo.
- **Teste 18:** violação no commit **intermediário** de três (nem o
  primeiro, nem o último) é detectada, e a mensagem cita `app.py`
  especificamente.
- **Teste 19:** `base_ref` inexistente produz `✘ ERRO INTERNO` com
  `exit 2` — distinto do `exit 1` de um bloqueio de gate comum.
- **Simulação da lógica do workflow** (fora do GitHub, com git real,
  já que este ambiente não acessa o GitHub): merge-base de push-de-branch-nova
  contra `origin/main` calculado corretamente; falha correta quando
  `origin/main` não existe; falha correta com inputs de
  `workflow_dispatch` vazios ou inválidos; sucesso correto com inputs
  válidos.

---

## 7A. Falso positivo na tentativa de commit — classificação segredo vs. arquivo sensível

Na tentativa de commit desta implementação, o hook bloqueou em
`[4/14] Verificando presença de segredos`, apontando `credentials.json`
como padrão detectado em `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md`
linha 150 — que apenas **menciona**, em prosa, os nomes de arquivo que
a Validação 3 protege. Não havia segredo real.

**Causa:** a VALIDAÇÃO 4 (`SECRETS_PATTERNS`) de `.githooks/pre-commit`
misturava dois tipos de padrão: detecção de **conteúdo** de segredo
(token, chave, senha — ex. `api[_-]?key`, identificador de token da
plataforma, padrão de senha seguido de atribuição) e detecção de
**nome de arquivo** sensível (`^\.env`, `credentials\.json`). Os dois
últimos disparam em qualquer menção
textual ao nome, não só quando o arquivo em si está sendo commitado —
e o nome do arquivo já era protegido, separadamente e corretamente,
pela VALIDAÇÃO 3 (que bloqueia o arquivo, não o texto que o cita).

**Correção:** removidos de `SECRETS_PATTERNS` os dois padrões que
detectam apenas nome de arquivo (`^\.env`, `credentials\.json`).
Mantidos todos os padrões de conteúdo (chave, token, senha,
assignment). Nenhuma mudança em `is_gate_pattern_source_file()` — não
foi ampliada a isenção por arquivo; a correção foi na classificação do
próprio padrão. Nenhuma mudança em `.magnata/patterns.sh` (fonte
canônica usada pelo CI) — o problema era específico da lista paralela
do hook, já documentado como divergência residual (seção 5.2).

**Evidência (Testes 20–22, seção 6):**
- Teste 20: documento permitido que só *menciona* `.env`/
  `secrets.json`/`credentials.json` em prosa — commit aprova
  (zero falso positivo).
- Teste 21: arquivo de fato chamado `credentials.json` no stage —
  ainda bloqueado, pela Validação 3.
- Teste 22: token real (variável de token do GitHub com valor
  atribuído) dentro de um documento permitido — ainda bloqueado, pela
  Validação 4.

---

## 7B. Segundo falso positivo — classificação normativo vs. técnico/relatório

Ao corrigir o falso positivo da seção 7A, o próprio relatório da Etapa 6
(este arquivo) e `docs/magnata-os/MAGNATA_AI_CI_GOVERNANCA.md` — ambos
descrevendo o Gate 8 — passaram a disparar o gate documental de "9
camadas", porque esses documentos citam a expressão proibida para
*explicar* a regra, não para redefinir a arquitetura.

**Causa:** os gates 7–10 (11º módulo, 9 camadas, autonomia %, ADR
silenciosa) rodavam sobre qualquer arquivo não pertencente à lista de
4 arquivos-fonte do próprio padrão (`is_gate_pattern_source_file`).
Documentação técnica sobre CI/hooks e relatórios de etapa nunca
estiveram nessa lista, então qualquer menção em prosa virava violação.

**Correção:** adicionada em `.magnata/patterns.sh` uma nova
classificação — `NORMATIVE_DOC_PATTERNS` (enumeração fechada e exata,
não regex genérica) e o helper `is_normative_doc()` — cobrindo os
documentos que **são** a arquitetura-de-registro (Manifesto,
Arquitetura, Contratos, Estados, Eventos, Entidades, Decisões de
Entidades, Documental Módulo 01 e fases, Módulo 01 (Ingestão, Decisões,
Plano Técnico, Fase 0), e em `docs/magnata-os/`: Capacidades, Módulos,
Roadmap, Matriz Arquitetural, ADR 001). Os gates 7–10, em
`validate_governance.sh` e nas VALIDAÇÕES 9–12 do hook, passaram a
iterar arquivo a arquivo e só aplicar o padrão semântico quando
`is_normative_doc()` retorna verdadeiro. Nenhuma mudança em segredo,
whitespace, arquivos protegidos, escopo, modos Git ou no contrato
base/head — só os 4 gates semânticos mudaram de escopo.

**Ajuste de fixtures dos Testes 7–10 (mesma rodada):** esses 4 testes,
já existentes, usavam nomes de arquivo arbitrários
(`modules_test.md`, `layers_test.md`, `autonomy_test.md`,
`adr_test.md`) — que nunca foram, nem precisavam ser, documentos
normativos reais. Com o novo escopo, esses nomes deixaram de ser
reconhecidos como normativos e os gates passaram a aprová-los, em vez
de bloquear — uma regressão real, detectada pela suíte. Corrigido
trocando **somente o caminho da fixture** de cada teste por um
documento normativo real e tematicamente coerente (Teste 7 →
`docs/magnata-os/MAGNATA_OS_MODULOS.md`; Teste 8 →
`MAGNATA_OS_ARQUITETURA.md`; Teste 9 →
`docs/magnata-os/MAGNATA_OS_CAPACIDADES.md`; Teste 10 →
`docs/magnata-os/MAGNATA_OS_ADR_001_NOMENCLATURA_ITEM_INGESTAO_VS_DOCUMENTO.md`),
dentro do repositório de teste isolado — nenhum documento real do
repositório principal foi tocado. Asserção, resultado esperado e
mensagem de cada teste permanecem exatamente os mesmos; só o arquivo
usado para prová-los mudou.

**Evidência (Testes 23–25, seção 6):**
- Teste 23: menção técnica a "9 camadas" num documento de CI não
  normativo — aprova (zero falso positivo).
- Teste 24: redefinição real de "9 camadas" num documento normativo —
  bloqueia (zero falso negativo).
- Teste 25: segredo real num documento técnico não normativo — ainda
  bloqueia (sem isenção geral de Markdown).

---

## 7C. Falhas reais no PR #12 (GitHub Actions) — Gate 15 e Gate 16

Primeira execução real do workflow (fora deste sandbox, no runner do
GitHub Actions do PR #12). Duas falhas relatadas pelo usuário, mais uma
terceira encontrada ao investigar o mesmo tipo de divergência
ambiente-local-vs-runner.

**Gate 15 (`hooks_suite`) — causa:** `.githooks/test-hooks.sh` copiava
`.git/hooks/` do ambiente **chamador** (`cp -r "$(git rev-parse
--git-dir)/hooks" ...`) para testar contra eles. Isso só funciona se
`install-hooks.sh` já rodou ali antes — o que nunca acontece
automaticamente num checkout novo de CI. No runner, `.git/hooks/` só
tinha os `.sample` padrão do Git (não-executáveis), então os hooks
"copiados" para o teste não faziam nada — 3 dos 6 testes internos
(que esperam bloqueio) commitavam sem serem barrados, e a suíte
reprovava. **Correção:** copiar da fonte versionada (`.githooks/`,
resolvida por `BASH_SOURCE`), junto com `.magnata/patterns.sh` (que o
hook importa e também estava faltando no repositório temporário).
Achado adicional na mesma investigação: um "unborn branch" (branch
criada sem nenhum commit ainda) faz `git rev-parse --abbrev-ref HEAD`
retornar `HEAD` literal neste ambiente — corrigido adicionando um
commit inicial antes dos cenários de teste, como o resto da suíte já
faz.

**Gate 16 (`report_final`) — causa:** o contador usava `((total_approved++))`/
`((total_blocked++))` (forma de comando aritmético). Sob `set -e`
(ativo no topo do script), o pós-incremento de uma variável que começa
em `0` avalia como falso na primeira vez — abortando o script
imediatamente após testar o primeiro gate (`branch`), exatamente o
sintoma relatado ("Testing branch..." e nada mais). Bug pré-existente,
nunca exercitado pela suíte automatizada (nenhum dos testes 1–25 chama
`report_final` ou `hooks_suite` diretamente — só os steps reais do
workflow chamam). **Correção:** forma de atribuição
(`total_approved=$((total_approved + 1))`), imune a esse efeito
colateral de `set -e`. O mesmo padrão existia em
`.githooks/test-hooks.sh` (`TEST_PASS`/`TEST_FAIL`) e foi corrigido
igual.

**Achado adicional, mesma classe de problema (branch em `pull_request`):**
`gate_branch()` usava só `git rev-parse --abbrev-ref HEAD`. Em eventos
`pull_request`, `actions/checkout` deixa o HEAD **destacado** (aponta
para o merge commit), e isso retorna `HEAD` literal, não o nome da
branch — bloquearia todo PR real, mesmo com o código correto. Não fazia
parte dos dois sintomas relatados, mas é a mesma classe de divergência
ambiente-local-vs-runner, e o usuário pediu explicitamente para checar
isso nesta investigação. **Correção:** usar `GITHUB_HEAD_REF` (PR) ou
`GITHUB_REF_NAME` (push) quando disponíveis, caindo para `git
rev-parse` só em execução local — sem abrir mão do bloqueio quando
nenhuma das duas variáveis está presente.

**Evidência (Testes 26–28, seção 6, mais simulação manual):**
confirmado com git real que: (a) Gate 15 aprova num clone genuinamente
sem hooks instalados; (b) Gate 16 completa os 15 gates e imprime a
contagem final, em vez de abortar; (c) o gate de branch aprova com HEAD
destacado quando `GITHUB_HEAD_REF`/`GITHUB_REF_NAME` estão corretos, e
continua bloqueando quando nenhum dos dois está presente ou aponta
para a branch errada.

---

## 8. Validação do workflow (checagem local, sem acesso ao GitHub)

- Sintaxe YAML: válida (parse via PyYAML).
- Eventos: `pull_request` (main, feat/magnata-os-claude-powerpack),
  `push` (feat/magnata-os-claude-powerpack), `workflow_dispatch`.
- Permissões: `contents: read`, `pull-requests: read` — só leitura.
- `concurrency`: grupo por workflow+ref, `cancel-in-progress: true`.
- `timeout-minutes: 10`.
- Nenhuma referência a `secrets.*`.
- Nenhuma chamada de rede externa (`curl`/`wget`/URL).
- Nenhum `git push`, deploy ou escrita.
- Única action usada: `actions/checkout@v4` (oficial, pinada por tag).
- **Sem `GITHUB_STEP_SUMMARY`** — o workflow não escreve resumo
  estruturado ao final; usa apenas `echo` no step "Resultado". Não é
  um bloqueio, é uma lacuna de usabilidade; segue fora do objetivo
  único desta rodada (contrato base/head) — não alterado.
- **`workflow_dispatch` com inputs obrigatórios:** `base_ref` e
  `head_ref`, ambos `required: true` — execução manual sem os dois não
  é possível pela UI/API do GitHub, e o step valida novamente
  (não-vazio + `git cat-file -e`) antes de prosseguir.
- **`push` de branch nova:** merge-base com `origin/${MAIN_BRANCH}`
  (`main`, configurável), nunca `HEAD^` nem árvore vazia. Falha
  explicitamente se a branch principal não existir localmente ou não
  houver merge-base.
- **Referência inválida, em qualquer evento:** o job falha no step de
  cálculo de base/head (`exit 1`, anotação `::error::`) antes de rodar
  qualquer gate — e, independentemente disso, o próprio
  `validate_governance.sh` rejeita referência inválida com
  `✘ ERRO INTERNO` e `exit 2` (defesa em profundidade).
- **Nenhum evento cai no fallback local:** `pull_request`, `push` e
  `workflow_dispatch` sempre produzem `base`/`head` válidos ou falham
  o job — nunca os dois vazios chegam a um gate num evento de CI real.
- 20 steps no total (sem mudança de quantidade desde a rodada
  anterior); nenhum step de gate foi removido, reordenado ou teve
  lógica de detecção alterada — só o step "Determinar base e head"
  ganhou os ramos de `push`/`workflow_dispatch` mais rigorosos, e
  "Gate 16"/"Resultado" ganharam a condição
  `steps.diffrange.outcome == 'success'`.

---

## 9. Conformidade com CLAUDE.md

✓ Seção 3: nenhum arquivo funcional alterado
✓ Seção 6: nenhum segredo revelado; segredo fictício de teste nunca é
  real e não sai do repositório de teste temporário
✓ Seção 7: `app.py`, migrations, frontend intactos (confirmado por
  `git diff --cached --name-status`)
✓ Seção 8: falha real encontrada foi registrada por escrito antes de
  ser corrigida (não escondida), e a correção ficou registrada
  separadamente da falha original (seção 7)
✓ Seção 9: nenhum commit, push, PR, merge ou deploy realizado
✓ Seção 10: critérios de conclusão satisfeitos — ver parecer final

---

## 10. Rollback (histórico — situação em 2026-07-29, superada)

**Esta seção descreve um estado que não existe mais.** Na época,
nada tinha sido commitado. Desde então, a implementação foi commitada,
teve dois defeitos reais corrigidos (Gate 6 e escopo documental — ver
seção 12), foi mesclada em `main` via PR #13, e recebeu uma
estabilização pós-merge própria. Reverter hoje exige `git revert` dos
commits mesclados em `main`, não os comandos abaixo (mantidos só como
registro do que teria sido usado naquele momento):

```bash
git restore --staged .githooks/pre-commit .github/workflows .magnata scripts/ci
git checkout -- .githooks/pre-commit
git clean -fd .github/workflows .magnata scripts/ci MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md docs/magnata-os/MAGNATA_AI_CI_GOVERNANCA.md
```

(Comando de referência da época — **não executado**; nunca foi usado.)

---

## 11. Parecer final (histórico — situação em 2026-07-29, superada)

**Este parecer descreve o estado da implementação antes do commit, do
PR #13 e do merge.** O parecer vigente está na seção 12.

**ETAPA 6 VALIDADA E PRONTA PARA APROVAÇÃO DE COMMIT** *(superado — ver
seção 12 para o resultado real pós-commit e pós-merge)*

O contrato base/head agora é completo e comprovado nos três eventos do
CI (`pull_request`, `push` — incluindo criação de branch —,
`workflow_dispatch`), com referência inválida tratada como erro
interno, nunca como aprovação ou bloqueio de gate comum. A
classificação segredo-vs-arquivo-sensível no hook foi corrigida
(seção 7A), assim como a classificação documento-normativo-vs-técnico
dos gates semânticos (seção 7B), sem perder detecção de segredo real,
proteção de nome de arquivo sensível, ou bloqueio de redefinição
arquitetural real. As duas falhas reais observadas no PR #12 do
GitHub Actions (Gate 15 e Gate 16), mais uma terceira da mesma classe
encontrada na investigação (gate de branch em `pull_request`), foram
corrigidas e comprovadas (seção 7C). 28/28 testes aprovados, 0 falhas,
0 SKIP, 0 erro interno inesperado. Workflow permanece read-only, sem
segredo, sem deploy, sem escrita. `app.py`, migrations e frontend
intactos.

**Risco declarado na época, resolvido em seguida:** divergência
residual entre `.githooks/pre-commit` e `.magnata/patterns.sh` para os
gates de segredo, scratch e parte dos gates documentais (seção 5.2).
Ausência de `GITHUB_STEP_SUMMARY` — lacuna de usabilidade, não de
correção, permanece em aberto (ver seção 12, riscos remanescentes).

---

## 12. Fechamento final — PR #13 mesclado + estabilização pós-merge

**Data:** 2026-08-03

**PR #13:** mesclado em `main`. Merge commit
`d616d521082db5d97e1824daf14c6cfdb4618f31` (pais `f1c0edc9` — `main`
anterior — e `5faf0c68` — tip de `feat/magnata-os-etapa6-governanca`).
7 commits incorporados, 23 arquivos alterados. PR #12 (anterior) foi
fechado sem merge.

**Defeitos reais encontrados e corrigidos antes do merge:**
- **Gate 6 (whitespace):** falso negativo por `git diff --check | grep -q`
  sob `pipefail` — o exit code do `git diff` vazava e derrotava o
  resultado do `grep`, mascarando violações reais. Corrigido capturando
  saída/exit code de `get_changed_check()` diretamente (sem pipe), com
  classificação por `case` (0=aprovado; 1|2=bloqueado; outro=erro
  interno).
- **Escopo documental:** `ALLOWED_PATHS`/`PROTECTED_FILES` nunca
  previam os 4 `CLAUDE.md` institucionais exigidos pelo Gate 12
  (`CLAUDE_HIERARCHY`). Corrigido com `is_claude_hierarchy_path()` —
  igualdade exata de caminho (nunca padrão amplo) — aplicada na
  Validação 6 do hook e nos gates `protected_frontend`/
  `protected_migrations` do CI (esta segunda aplicação só foi descoberta
  numa simulação de checkout limpo do PR, não no hook).

**Testes:** suíte isolada com 47/47 aprovados no momento do merge (32
da rodada anterior + 8 do Gate 6 + 5 da exceção da hierarquia CLAUDE.md
+ 2 dos gates de CI protected_frontend/protected_migrations).

**Estabilização pós-merge (branch `feat/magnata-os-etapa6-estabilizacao`):**
achados registrados nesta seção — workflow sem gatilho `push` para
`main` (nenhuma revalidação automática rodava depois de um merge
direto) e esta própria documentação desatualizada. Corrigidos: `push`
passou a incluir `main`; `gate_branch()` reconhece push pós-merge em
`main` só quando `GITHUB_EVENT_NAME=push` e `GITHUB_REF_NAME=main`
ocorrem juntos (nunca isoladamente, nunca por execução local), sem que
`main` entre em `AUTHORIZED_BRANCHES`. Suíte cresceu para 52/52
aprovados (5 testes novos: push legítimo em main aprova; execução
local em main continua bloqueada; spoof incompleto não libera main;
branch arbitrária via push continua bloqueada; gatilhos do workflow
conferidos estaticamente).

**Riscos remanescentes declarados, não bloqueantes:**
- Ausência de `GITHUB_STEP_SUMMARY` — lacuna de usabilidade, herdada
  da rodada original (seção 11), ainda não corrigida.
- Warning de depreciação do Node.js observado no GitHub Actions —
  fonte exata não confirmada nesta sessão (sem acesso a log do
  Actions); único action pinado no workflow é `actions/checkout@v4`
  (versão major atual). Classificado como manutenção futura
  recomendada, não correção urgente.
- `git diff --check` limpo, nenhuma alteração funcional em `app.py`,
  frontend, `magnata_os/` ou migrations reais em nenhum commit desta
  etapa nem da estabilização.

**Parecer final vigente:** ETAPA 6 ENCERRADA COM INTEGRIDADE, MAIN
SINCRONIZADA, ESTABILIZAÇÃO PÓS-MERGE CONCLUÍDA.

---

**Relatório preparado em:** 2026-07-29 (atualizado no mesmo dia, três
vezes: implementação inicial, correção do escopo de diff, e
fechamento completo do contrato base/head em todos os eventos — seção
7). Fechamento final e estabilização pós-merge registrados em
2026-08-03 (seção 12).
**Commit:** ver seção 12 — mesclado em `main` via PR #13
(`d616d521082db5d97e1824daf14c6cfdb4618f31`)
