# Magnata OS — CI de Governança e Qualidade

**Versão:** 1.0
**Etapa:** 6 — CI de Governança
**Data:** 2026-07-29
**Status:** IMPLEMENTADO LOCALMENTE — não commitado, não enviado ao GitHub

---

## 1. Objetivo

Automatizar, em GitHub Actions, as mesmas verificações de governança
que os hooks locais da Etapa 5 já fazem — sem invasão, sem acesso a
produção, sem escrita, sem segredo.

**Importante:** "implementado localmente" significa que o workflow, o
script e a fonte de padrões existem no working tree e passam nos
testes locais. **Não** significa que o workflow já rodou no GitHub —
isso só acontece depois de commit + push, o que não foi feito.

---

## 2. Fonte única de verdade

`.magnata/patterns.sh` é o arquivo canônico. Contém, como arrays bash
exportados:

| Variável | Conteúdo |
|---|---|
| `PROTECTED_FILES` | Regex dos arquivos/diretórios protegidos (app.py, migrations, frontend) |
| `SECRET_PATTERNS` | Regex de indícios de segredo |
| `GATE_11_MODULE_PATTERNS` | Regex de "segurança como 11º módulo" |
| `GATE_9_LAYERS_PATTERNS` | Regex de "9 camadas"/"6+3" |
| `GATE_AUTONOMY_PERCENT_PATTERNS` | Regex de autonomia como percentual |
| `GATE_ADR_SILENT_PATTERNS` | Regex de renomeação Item de Ingestão → Documento sem ADR |
| `REQUIRED_DOCS` | Documentos fundacionais obrigatórios |
| `CLAUDE_HIERARCHY` | Os 4 níveis obrigatórios de `CLAUDE.md` |
| `EXECUTABLE_FILES` / `NON_EXECUTABLE_FILES` | Modos Git esperados (755/644) |
| `ALLOWED_PATHS` | Escopo de caminhos que o CI/hook aceitam alterar |
| `SCRATCH_PATTERNS` | Padrões de arquivo de scratch, proibidos em commit |

**Quem importa:**
- `scripts/ci/validate_governance.sh` — importa e usa **todas** as
  variáveis acima, uma por gate.
- `.githooks/pre-commit` — importa o arquivo inteiro, mas hoje só
  consulta `PROTECTED_FILES` e `ALLOWED_PATHS` dele. As demais
  validações do hook (segredo, gates documentais, scratch) mantêm
  listas próprias, paralelas — ver limitação na seção 6.

**Quem não duplica nada:** `.github/workflows/magnata-governance.yml`
não tem nenhum array de padrão — cada step chama
`./scripts/ci/validate_governance.sh <gate>` e nada mais.

---

## 3. Os 16 gates

Ver tabela completa em
`MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md` §4. Resumo por categoria:

- **Segurança/legado (1–4):** branch correta, `app.py`, migrations e
  frontend protegidos.
- **Qualidade (5–6):** segredos, whitespace.
- **Documental (7–10):** 11º módulo, 9 camadas, autonomia %, ADR
  silenciosa — todos vindos do plano da Etapa 4/5, sem mudança de
  regra aqui.
- **Estrutura (11–14):** documentos obrigatórios, hierarquia de
  `CLAUDE.md`, modos Git.
- **Consolidação (15–16):** suíte de hooks aprovada, relatório final.

Cada gate é uma função `gate_<nome>()` em `validate_governance.sh`,
invocável isoladamente:

```bash
scripts/ci/validate_governance.sh secrets
scripts/ci/validate_governance.sh report_final
```

---

## 4. Suíte de testes isolada

`scripts/ci/test_governance.sh` cria um repositório Git **temporário**
(`/tmp/magnata_governance_test`), copia para lá os arquivos
necessários (`patterns.sh`, `validate_governance.sh`, um hook real, o
workflow real) e simula 25 cenários — a maioria deve bloquear
(violação, erro interno ou nome de arquivo sensível detectado), os
demais devem passar (mudança válida / suíte limpa / intervalo limpo
multi-commit / menção documental sem segredo real). Os cenários 16–19
validam o contrato base/head: violação no primeiro de dois commits
(16), intervalo limpo sem falso positivo (17), violação no commit
intermediário de três (18), referência inválida como erro interno
(19). Os cenários 20–22 validam a classificação segredo-vs-arquivo-sensível
do hook (ver 6.1): menção documental sem falso positivo (20), arquivo
`credentials.json` real ainda bloqueado (21), token real em doc
permitido ainda bloqueado (22). Os cenários 23–25 validam a
classificação documento-normativo-vs-técnico dos gates semânticos (ver
6.1B): menção técnica sem falso positivo (23), redefinição normativa
real ainda bloqueada (24), segredo real em doc técnico ainda bloqueado
(25). Nunca toca no repositório real. Resultado na última execução:
**25/25 aprovados**.

---

## 5. Workflow

`.github/workflows/magnata-governance.yml`:

- Gatilhos: `pull_request` (para `main` e
  `feat/magnata-os-claude-powerpack`), `push` (para
  `feat/magnata-os-claude-powerpack`), `workflow_dispatch` (com inputs
  obrigatórios `base_ref`/`head_ref`, `required: true`).
- Permissões: `contents: read`, `pull-requests: read` — só leitura.
- `concurrency`: cancela execução anterior do mesmo ref.
- `timeout-minutes: 10`.
- Uma única action de terceiros: `actions/checkout@v4` (oficial).
- 20 steps: 16 gates, 1 diagnóstico de ambiente, 1 checkout, 1 cálculo
  de base/head do diff (ver 6.1), 1 resultado final.
- Nenhum `secrets.*`, nenhuma escrita, nenhum deploy, nenhuma chamada
  de rede externa além do checkout.

---

## 6. Limitações reais conhecidas

### 6.1 Escopo de diff no CI — corrigido

Os gates 2–10 (tudo que depende de "o que mudou no commit/PR") usavam,
incondicionalmente, dentro de `validate_governance.sh`:

```bash
git diff --cached --name-only 2>/dev/null || git diff HEAD^..HEAD --name-only 2>/dev/null
```

Num checkout de GitHub Actions **nada fica staged**, então o segundo
ramo (`HEAD^..HEAD`) era sempre o executado — e ele só enxergava o
**último commit**, não o PR inteiro contra a branch-base. Confirmado
por teste local: um PR simulado de 2 commits (o primeiro altera
`app.py`, o segundo é trivial) resultava em diff vazio para `app.py`
nesse fallback — a violação passaria pelo CI sem ser detectada.

**Corrigido, em duas rodadas.** `validate_governance.sh` aceita
`base_ref`/`head_ref` como 2º/3º argumento posicional; quando ambos
válidos, os gates usam `git diff base_ref...head_ref` (semântica de
merge-base, igual ao "Files changed" do GitHub). Sem os dois, cai no
comportamento antigo (staged, ou `HEAD^..HEAD`) — mas **isso agora só
acontece em execução manual/local**, nunca quando o workflow chama o
script, e é anunciado explicitamente (`MODO LOCAL — INTERVALO PADRÃO
LIMITADO`). Uma referência inválida, ou só um dos dois argumentos
fornecido, é `✘ ERRO INTERNO` com `exit 2` — nunca aprovação, nunca
bloqueio de gate comum.

O workflow garante base/head válidos nos três eventos, sem exceção:
`pull_request` usa `base.sha`/`head.sha` do PR inteiro; `push` usa
`before`/`github.sha`, com merge-base contra `origin/main` para push
de branch nova (nunca `HEAD^` automático, falha se não houver base
confiável); `workflow_dispatch` exige os inputs obrigatórios
`base_ref`/`head_ref` e valida ambos antes de prosseguir. Qualquer
evento sem base/head válido falha o job antes de rodar um gate sequer.
Ver `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md` §7 (evidência: Testes
16–19).

### 6.1A Classificação segredo vs. arquivo sensível no hook — corrigida

A VALIDAÇÃO 4 (segredos) do hook misturava dois tipos de padrão:
conteúdo de segredo real (token, chave, senha) e nome de arquivo
sensível (`.env`, `credentials.json`). O segundo tipo já era protegido,
separadamente, pela VALIDAÇÃO 3 (bloqueia o arquivo em si) — mas por
estar duplicado como padrão de *texto* na VALIDAÇÃO 4, qualquer
documento que apenas **mencionasse** esses nomes em prosa disparava um
falso positivo de "segredo detectado". Corrigido: removidos de
`SECRETS_PATTERNS` os dois padrões de nome de arquivo; mantidos todos
os padrões de conteúdo. Nenhuma mudança em `is_gate_pattern_source_file()`
nem em `.magnata/patterns.sh`. Ver
`MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md` §7A (evidência: Testes
20–22).

### 6.1B Classificação normativo vs. técnico/relatório nos gates semânticos — corrigida

Os gates 7–10 (11º módulo, 9 camadas, autonomia %, ADR silenciosa)
rodavam sobre qualquer arquivo fora da mesma lista de 4 arquivos-fonte
(`is_gate_pattern_source_file()`) — nunca isentando documentação
técnica de CI/hooks nem relatórios de etapa, que legitimamente citam a
expressão proibida para *descrever* o gate. Corrigido: nova
classificação `NORMATIVE_DOC_PATTERNS`/`is_normative_doc()` em
`.magnata/patterns.sh` (enumeração fechada dos documentos que **são**
a arquitetura-de-registro), consumida por ambos, hook e validador. Os
4 gates semânticos agora só aplicam o padrão a arquivos normativos;
segredo, whitespace, arquivos protegidos, escopo, modos Git e o
contrato base/head não mudaram. Ver
`MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md` §7B (evidência: Testes
23–25).

### 6.2 Divergência entre hook e CI para alguns gates

`.githooks/pre-commit` mantém listas próprias (não conectadas à fonte
única) para: detecção de segredo, gates documentais (11º módulo, 9
camadas, autonomia %, ADR silenciosa) e arquivos de scratch. Cada uma
diverge em algum detalhe da lista canônica em `.magnata/patterns.sh` —
não são idênticas, mas também não são substituíveis sem risco (uma,
inclusive, é mais restritiva no lado canônico). Ver
`MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md` §5.2.

### 6.3 Sem `GITHUB_STEP_SUMMARY`

O workflow não produz resumo estruturado ao final da execução — usa
apenas `echo` no último step. Não bloqueia nada, é lacuna de
usabilidade.

### 6.4 Suíte de testes não cobre o hook local diretamente

`test_governance.sh` testa `validate_governance.sh` (o script de CI).
Não existe suíte automatizada equivalente para `.githooks/pre-commit`
isoladamente — a Etapa 5 validou o hook manualmente, sem harness
automatizado próprio.

---

## 7. Rollback

Ver `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md` §10.

---

## 8. Referências

- `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6_PLANO.md` — plano original aprovado.
- `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md` — relatório desta implementação.
- `MAGNATA_AI_HOOKS_LOCAIS.md` — hooks locais (Etapa 5).
- `.githooks/README.md` — operação dos hooks locais.

---

**Documento de governança técnica para Magnata OS — Etapa 6**
