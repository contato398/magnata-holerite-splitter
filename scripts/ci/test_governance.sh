#!/bin/bash
# Magnata OS — Suíte de Testes de Governança
# Executa 32 cenários em repositório temporário isolado
# Não realiza testes destrutivos no repositório principal

set -euo pipefail

# Import patterns
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$PROJECT_ROOT/.magnata/patterns.sh"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Test results
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Temporary test repo
TEST_REPO="/tmp/magnata_governance_test"

# ============================================================================
# SETUP
# ============================================================================

setup_test_repo() {
  rm -rf "$TEST_REPO" 2>/dev/null || true
  mkdir -p "$TEST_REPO"
  cd "$TEST_REPO"

  # Initialize git repo with initial commit
  # Branch precisa ser a mesma exigida por gate_branch, senão esse gate
  # bloqueia sempre, independente do cenário sob teste.
  git init -q -b feat/magnata-os-claude-powerpack
  git config user.email "test@magnata.local"
  git config user.name "Test"
  git config core.hooksPath "$PROJECT_ROOT/.githooks"

  # Copy essential files
  mkdir -p .magnata scripts/ci .github/workflows .githooks
  cp "$PROJECT_ROOT/.magnata/patterns.sh" .magnata/
  cp "$PROJECT_ROOT/scripts/ci/validate_governance.sh" scripts/ci/
  chmod +x scripts/ci/validate_governance.sh
  # Necessários para os testes 13/14 (modos Git) terem um arquivo real
  # de cada categoria (EXECUTABLE_FILES / NON_EXECUTABLE_FILES) para checar.
  cp "$PROJECT_ROOT/.githooks/pre-commit" .githooks/
  chmod +x .githooks/pre-commit
  # Necessário para o Teste 26 (Gate 15 autossuficiente) exercitar a suíte
  # de hooks real, não apenas o "test-hooks.sh não encontrado" (warning).
  cp "$PROJECT_ROOT/.githooks/test-hooks.sh" "$PROJECT_ROOT/.githooks/commit-msg" "$PROJECT_ROOT/.githooks/pre-push" "$PROJECT_ROOT/.githooks/post-commit" .githooks/
  chmod +x .githooks/test-hooks.sh .githooks/commit-msg .githooks/pre-push .githooks/post-commit
  cp "$PROJECT_ROOT/.github/workflows/magnata-governance.yml" .github/workflows/
  chmod 644 .github/workflows/magnata-governance.yml

  # Create initial commit
  echo "# Test Repo" > README.md
  git add README.md .magnata scripts/ci .github .githooks
  git commit -m "chore: initial" --no-verify

  echo -e "${GREEN}✓ Repositório de teste inicializado${NC}"
}

cleanup_test_repo() {
  cd "$PROJECT_ROOT"
  rm -rf "$TEST_REPO" 2>/dev/null || true
}

# ============================================================================
# TEST HELPER FUNCTIONS
# ============================================================================

run_test() {
  local test_num="$1"
  local test_name="$2"
  EXPECTED_RESULT="$3"  # "PASS" ou "FAIL" — global, lido por test_result()

  TESTS_RUN=$((TESTS_RUN + 1))
  echo ""
  echo -e "${BLUE}[TEST $test_num] $test_name${NC}"
  echo "  Esperado: $EXPECTED_RESULT"
}

test_result() {
  local actual_result="$1"  # "PASS" ou "FAIL"

  if [ "$actual_result" = "$EXPECTED_RESULT" ]; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "${GREEN}  ✓ PASSOU${NC}"
    return 0
  else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "${RED}  ✗ FALHOU (obteve: $actual_result, esperado: $EXPECTED_RESULT)${NC}"
    return 1
  fi
}

# ============================================================================
# TESTS
# ============================================================================

# TEST 1: Alteração válida permitida
test_1_valid_change() {
  run_test 1 "Alteração válida permitida (Markdown)" "PASS"

  cd "$TEST_REPO"
  echo "# New Doc" > MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6_VALIDO.md
  git add MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6_VALIDO.md

  if bash scripts/ci/validate_governance.sh branch >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset HEAD MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6_VALIDO.md
}

# TEST 2: app.py alterado
test_2_app_py_altered() {
  run_test 2 "app.py alterado" "FAIL"

  cd "$TEST_REPO"
  echo "print('test')" > app.py
  git add app.py

  if bash scripts/ci/validate_governance.sh protected_app_py >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset HEAD app.py
  rm -f app.py
}

# TEST 3: Migration alterada
test_3_migration_altered() {
  run_test 3 "Migration alterada" "FAIL"

  cd "$TEST_REPO"
  mkdir -p magnata_os/documental/modulo01/migrations
  echo "SELECT 1;" > magnata_os/documental/modulo01/migrations/0999_test.sql
  git add magnata_os/documental/modulo01/migrations/0999_test.sql

  if bash scripts/ci/validate_governance.sh protected_migrations >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset HEAD magnata_os/
  rm -rf magnata_os/
}

# TEST 4: Frontend funcional alterado
test_4_frontend_altered() {
  run_test 4 "Frontend funcional alterado" "FAIL"

  cd "$TEST_REPO"
  mkdir -p frontend
  echo "# Frontend" > frontend/CLAUDE.md
  git add frontend/CLAUDE.md

  if bash scripts/ci/validate_governance.sh protected_frontend >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset HEAD frontend/
  rm -rf frontend/
}

# TEST 5: Segredo fictício
test_5_secret_detected() {
  run_test 5 "Segredo fictício detectado" "FAIL"

  cd "$TEST_REPO"
  echo "GITHUB_TOKEN=ghp_1234567890abcdefghij" > secret_test.md
  git add secret_test.md

  if bash scripts/ci/validate_governance.sh secrets >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset HEAD secret_test.md
  rm -f secret_test.md
}

# TEST 6: Trailing whitespace
test_6_trailing_whitespace() {
  run_test 6 "Trailing whitespace detectado" "FAIL"

  cd "$TEST_REPO"
  printf "Line with trailing space   \n" > whitespace_test.md
  git add whitespace_test.md

  if git diff --cached --check >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset HEAD whitespace_test.md
  rm -f whitespace_test.md
}

# TEST 7: Segurança como 11º módulo
test_7_11_module_security() {
  run_test 7 "Segurança como 11º módulo" "FAIL"

  cd "$TEST_REPO"
  # Fixture normativa (docs/magnata-os/MAGNATA_OS_MODULOS.md) em vez de nome
  # arbitrário — o gate agora só atua sobre documentos normativos.
  mkdir -p docs/magnata-os
  echo "## 11º módulo — Segurança
Novo módulo funcional para segurança." > docs/magnata-os/MAGNATA_OS_MODULOS.md
  git add docs/magnata-os/MAGNATA_OS_MODULOS.md

  if bash scripts/ci/validate_governance.sh 11_module >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset HEAD docs/magnata-os/MAGNATA_OS_MODULOS.md
  rm -f docs/magnata-os/MAGNATA_OS_MODULOS.md
}

# TEST 8: 9 camadas
test_8_9_layers() {
  run_test 8 "Arquitetura de 9 camadas" "FAIL"

  cd "$TEST_REPO"
  # Fixture normativa (MAGNATA_OS_ARQUITETURA.md) em vez de nome arbitrário.
  echo "Arquitetura oficial: 9 camadas sequenciais" > MAGNATA_OS_ARQUITETURA.md
  git add MAGNATA_OS_ARQUITETURA.md

  if bash scripts/ci/validate_governance.sh 9_layers >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset HEAD MAGNATA_OS_ARQUITETURA.md
  rm -f MAGNATA_OS_ARQUITETURA.md
}

# TEST 9: Autonomia percentual
test_9_autonomy_percent() {
  run_test 9 "Autonomia como percentual abstrato" "FAIL"

  cd "$TEST_REPO"
  # Fixture normativa (docs/magnata-os/MAGNATA_OS_CAPACIDADES.md — doc oficial
  # de maturidade/limites de autonomia) em vez de nome arbitrário.
  mkdir -p docs/magnata-os
  echo "Nível de autonomia: 70%" > docs/magnata-os/MAGNATA_OS_CAPACIDADES.md
  git add docs/magnata-os/MAGNATA_OS_CAPACIDADES.md

  if bash scripts/ci/validate_governance.sh autonomy_percent >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset HEAD docs/magnata-os/MAGNATA_OS_CAPACIDADES.md
  rm -f docs/magnata-os/MAGNATA_OS_CAPACIDADES.md
}

# TEST 10: ADR silenciosa
test_10_adr_silent() {
  run_test 10 "ADR silenciosa (renomeação sem referência)" "FAIL"

  cd "$TEST_REPO"
  # Fixture normativa (docs/magnata-os/MAGNATA_OS_ADR_001_...md) em vez de
  # nome arbitrário.
  mkdir -p docs/magnata-os
  echo "Item de Ingestão foi renomeado para Documento." > docs/magnata-os/MAGNATA_OS_ADR_001_NOMENCLATURA_ITEM_INGESTAO_VS_DOCUMENTO.md
  git add docs/magnata-os/MAGNATA_OS_ADR_001_NOMENCLATURA_ITEM_INGESTAO_VS_DOCUMENTO.md

  if bash scripts/ci/validate_governance.sh adr_silent >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset HEAD docs/magnata-os/MAGNATA_OS_ADR_001_NOMENCLATURA_ITEM_INGESTAO_VS_DOCUMENTO.md
  rm -f docs/magnata-os/MAGNATA_OS_ADR_001_NOMENCLATURA_ITEM_INGESTAO_VS_DOCUMENTO.md
}

# TEST 11: Documento obrigatório ausente
test_11_required_doc_missing() {
  run_test 11 "Documento obrigatório ausente" "FAIL"

  cd "$TEST_REPO"

  if bash scripts/ci/validate_governance.sh required_docs >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 12: CLAUDE.md hierarquia incompleta
test_12_claude_hierarchy_incomplete() {
  run_test 12 "CLAUDE.md hierarquia incompleta" "FAIL"

  cd "$TEST_REPO"

  if bash scripts/ci/validate_governance.sh claude_hierarchy >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 13: Hook sem modo 755
test_13_hook_mode_755() {
  run_test 13 "Hook sem modo 100755" "FAIL"

  cd "$TEST_REPO"
  # Quebra o modo Git de um EXECUTABLE_FILES real (100755 -> 100644) no índice
  git update-index --chmod=-x .githooks/pre-commit

  if bash scripts/ci/validate_governance.sh script_mode_755 >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  # Restaura o modo correto no índice do repositório de teste
  git update-index --chmod=+x .githooks/pre-commit
}

# TEST 14: Workflow sem modo 644
test_14_workflow_mode_644() {
  run_test 14 "Workflow sem modo 100644" "FAIL"

  cd "$TEST_REPO"
  # Quebra o modo Git de um NON_EXECUTABLE_FILES real (100644 -> 100755) no índice
  git update-index --chmod=+x .github/workflows/magnata-governance.yml

  if bash scripts/ci/validate_governance.sh config_mode_644 >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  # Restaura o modo correto no índice do repositório de teste
  git update-index --chmod=-x .github/workflows/magnata-governance.yml
}

# TEST 15: Suíte completa aprovada
test_15_full_suite() {
  run_test 15 "Suíte completa aprovada e pronta para commit" "PASS"

  cd "$TEST_REPO"

  # Run validation on clean repo
  if bash scripts/ci/validate_governance.sh branch >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 16: Escopo de diff do CI — violação em commit não-final do PR é detectada
# quando base_ref/head_ref são passados explicitamente (corrige o falso
# negativo em que só o último commit era comparado).
test_16_ci_diff_scope() {
  run_test 16 "Violação em commit não-final do PR/push é detectada (base/head explícitos)" "FAIL"

  cd "$TEST_REPO"
  local base_sha
  base_sha=$(git rev-parse HEAD)

  # Commit 1 (não-final): altera app.py — violação real
  echo "print('HACKED')" > app.py
  git add app.py
  git commit -q -m "commit 1: altera app.py (violacao)" --no-verify

  # Commit 2 (final): trivial, não toca em app.py
  echo "trivial" >> README.md
  git add README.md
  git commit -q -m "commit 2: trivial" --no-verify

  local head_sha
  head_sha=$(git rev-parse HEAD)

  if bash scripts/ci/validate_governance.sh protected_app_py "$base_sha" "$head_sha" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 17: Intervalo limpo, dois commits, ambos em arquivos permitidos —
# não pode gerar falso positivo.
test_17_clean_multi_commit_range() {
  run_test 17 "Intervalo limpo com dois commits (só arquivos permitidos)" "PASS"

  cd "$TEST_REPO"
  local base_sha
  base_sha=$(git rev-parse HEAD)

  echo "# doc permitido A" > MAGNATA_OS_TEST17_A.md
  git add MAGNATA_OS_TEST17_A.md
  git commit -q -m "commit 1: doc permitido A" --no-verify

  echo "# doc permitido B" > MAGNATA_OS_TEST17_B.md
  git add MAGNATA_OS_TEST17_B.md
  git commit -q -m "commit 2: doc permitido B" --no-verify

  local head_sha
  head_sha=$(git rev-parse HEAD)

  if bash scripts/ci/validate_governance.sh protected_app_py "$base_sha" "$head_sha" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 18: Push com violação no commit intermediário (não o primeiro, não o
# último) — precisa ser detectada mesmo estando "escondida" no meio do range.
test_18_push_intermediate_violation() {
  run_test 18 "Violação em commit intermediário de push (3 commits) é detectada" "FAIL"

  cd "$TEST_REPO"
  local base_sha
  base_sha=$(git rev-parse HEAD)

  echo "# doc permitido C" > MAGNATA_OS_TEST18_C.md
  git add MAGNATA_OS_TEST18_C.md
  git commit -q -m "commit 1: doc permitido" --no-verify

  echo "print('HACKED 18')" > app.py
  git add app.py
  git commit -q -m "commit 2 (intermediario): altera app.py (violacao)" --no-verify

  echo "# doc permitido D" > MAGNATA_OS_TEST18_D.md
  git add MAGNATA_OS_TEST18_D.md
  git commit -q -m "commit 3: doc permitido, nao toca em app.py" --no-verify

  local head_sha
  head_sha=$(git rev-parse HEAD)

  local output
  local exit_code
  output=$(bash scripts/ci/validate_governance.sh protected_app_py "$base_sha" "$head_sha" 2>&1)
  exit_code=$?

  # Precisa bloquear E citar app.py especificamente (não um bloqueio genérico).
  if [[ $exit_code -ne 0 && "$output" == *"app.py"* ]]; then
    test_result "FAIL"
  else
    test_result "PASS"
  fi
}

# TEST 19: base_ref inexistente — deve ser ERRO INTERNO (nunca gate comum,
# nunca aprovação), com exit code distinto de um bloqueio de gate normal.
test_19_invalid_base_ref() {
  run_test 19 "base_ref inválida/inexistente é erro interno bloqueante" "FAIL"

  cd "$TEST_REPO"
  local head_sha
  head_sha=$(git rev-parse HEAD)

  local output
  local exit_code
  output=$(bash scripts/ci/validate_governance.sh protected_app_py "ref-que-nao-existe-xyz123" "$head_sha" 2>&1)
  exit_code=$?

  # Critério: bloqueia (exit != 0), NÃO é o exit code de bloqueio comum (1) —
  # é erro interno (exit 2) — e a mensagem confirma a classificação distinta.
  if [[ $exit_code -eq 2 && "$output" == *"ERRO INTERNO"* ]]; then
    test_result "FAIL"
  else
    test_result "PASS"
  fi
}

# TEST 20 (Cenário A): menção documental a nomes de arquivo sensível (.env,
# secrets.json, credentials.json) em prosa não pode ser falso positivo da
# Validação 4 do hook — esses nomes são responsabilidade da Validação 3.
test_20_secret_gate_doc_mention_not_false_positive() {
  run_test 20 "Menção documental a nomes de arquivo sensível não é falso positivo (hook)" "PASS"

  cd "$TEST_REPO"
  cat > MAGNATA_OS_TEST20_MENCAO.md <<'EOF'
# Doc de teste
Protege .env, secrets.json e credentials.json como arquivos sensiveis.
EOF
  git add MAGNATA_OS_TEST20_MENCAO.md

  if git commit -m "docs: teste 20 mencao documental" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 21 (Cenário B): arquivo de fato chamado credentials.json continua
# bloqueado — pela Validação 3, não pela 4.
test_21_sensitive_filename_blocked() {
  run_test 21 "Arquivo credentials.json real é bloqueado pela Validação 3 (hook)" "FAIL"

  cd "$TEST_REPO"
  echo '{"key": "fake"}' > credentials.json
  git add credentials.json

  if git commit -m "docs: teste 21 arquivo sensivel" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD credentials.json 2>/dev/null || true
  rm -f credentials.json
}

# TEST 22 (Cenário C): segredo real (token) dentro de um documento permitido
# ainda precisa ser bloqueado pela Validação 4 — documentação não é isenta
# de detecção de segredo real.
test_22_real_secret_in_doc_blocked() {
  run_test 22 "Token real em documento permitido é bloqueado pela Validação 4 (hook)" "FAIL"

  cd "$TEST_REPO"
  cat > MAGNATA_OS_TEST22_SEGREDO.md <<'EOF'
# Doc de teste
GITHUB_TOKEN=ghp_1234567890abcdefghij
EOF
  git add MAGNATA_OS_TEST22_SEGREDO.md

  if git commit -m "docs: teste 22 segredo real" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST22_SEGREDO.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST22_SEGREDO.md
}

# TEST 23: menção técnica a "9 camadas" num documento de CI (não normativo)
# descrevendo o próprio gate não pode ser falso positivo.
test_23_semantic_gate_technical_mention_not_false_positive() {
  run_test 23 "Menção técnica a '9 camadas' em doc de CI (não normativo) não é falso positivo" "PASS"

  cd "$TEST_REPO"
  mkdir -p docs/magnata-os
  cat > docs/magnata-os/MAGNATA_AI_CI_GOVERNANCA.md <<'EOF'
# Doc tecnico de CI
O Gate 8 proibe declarar a arquitetura como 9 camadas sequenciais.
EOF
  git add docs/magnata-os/MAGNATA_AI_CI_GOVERNANCA.md

  if bash scripts/ci/validate_governance.sh 9_layers >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD docs/magnata-os/MAGNATA_AI_CI_GOVERNANCA.md 2>/dev/null || true
  rm -f docs/magnata-os/MAGNATA_AI_CI_GOVERNANCA.md
}

# TEST 24: a mesma expressão, mas redefinindo a arquitetura num documento
# normativo real, precisa continuar bloqueada — zero falso negativo.
test_24_semantic_gate_normative_redefinition_blocked() {
  run_test 24 "Redefinição de '9 camadas' em documento normativo é bloqueada" "FAIL"

  cd "$TEST_REPO"
  echo "Arquitetura oficial: 9 camadas sequenciais" > MAGNATA_OS_ARQUITETURA.md
  git add MAGNATA_OS_ARQUITETURA.md

  if bash scripts/ci/validate_governance.sh 9_layers >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_ARQUITETURA.md 2>/dev/null || true
  rm -f MAGNATA_OS_ARQUITETURA.md
}

# TEST 25: segredo real num documento técnico (não normativo) precisa
# continuar bloqueado — a classificação normativa não pode virar isenção
# geral de segredo para documentação.
test_25_secret_in_technical_doc_still_blocked() {
  run_test 25 "Segredo real em documento técnico de CI continua bloqueado (sem isenção geral)" "FAIL"

  cd "$TEST_REPO"
  mkdir -p docs/magnata-os
  cat > docs/magnata-os/MAGNATA_AI_CI_GOVERNANCA_TEST25.md <<'EOF'
# Doc tecnico de CI
GITHUB_TOKEN=ghp_1234567890abcdefghij
EOF
  git add docs/magnata-os/MAGNATA_AI_CI_GOVERNANCA_TEST25.md

  if bash scripts/ci/validate_governance.sh secrets >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD docs/magnata-os/MAGNATA_AI_CI_GOVERNANCA_TEST25.md 2>/dev/null || true
  rm -f docs/magnata-os/MAGNATA_AI_CI_GOVERNANCA_TEST25.md
}

# TEST 26: Gate 15 (hooks_suite) precisa aprovar num clone limpo, sem
# nenhum hook do Magnata instalado em .git/hooks/ — exatamente a condição
# de um runner de CI recém-clonado (install-hooks.sh nunca roda lá). Este
# repositório de teste já usa core.hooksPath apontando para .githooks/, não
# para .git/hooks/, então .git/hooks/ nunca recebeu os hooks do Magnata.
test_26_gate15_self_sufficient_no_installed_hooks() {
  run_test 26 "Gate 15 aprova em clone limpo sem hooks instalados em .git/hooks/ (autossuficiente)" "PASS"

  cd "$TEST_REPO"
  if bash scripts/ci/validate_governance.sh hooks_suite >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 27: Gate 16 (relatório final) precisa testar todos os 15 gates e
# reportar a contagem — não abortar logo após "Testing branch" por causa
# do bug de aritmética "((var++))" sob set -e quando var começa em 0.
test_27_gate16_report_final_completes() {
  run_test 27 "Gate 16 (relatório final) completa todos os gates, sem abortar prematuramente" "PASS"

  cd "$TEST_REPO"
  local output
  output=$(bash scripts/ci/validate_governance.sh report_final 2>&1)

  if [[ "$output" == *"Testing hooks_suite"* && "$output" == *"Total gates aprovados"* ]]; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 28: o gate de branch precisa distinguir execução local, push e
# pull_request. Em pull_request, actions/checkout deixa o HEAD destacado
# (git rev-parse --abbrev-ref HEAD retorna "HEAD" literal) — o gate precisa
# usar GITHUB_HEAD_REF/GITHUB_REF_NAME quando disponíveis, sem abrir mão do
# bloqueio quando nenhum dos dois está presente.
test_28_gate_branch_context_aware() {
  run_test 28 "Gate de branch usa GITHUB_HEAD_REF/GITHUB_REF_NAME com HEAD destacado (PR/push)" "PASS"

  cd "$TEST_REPO"
  local commit_sha
  commit_sha=$(git rev-parse HEAD)
  git checkout -q --detach "$commit_sha"

  local result="PASS"

  if ! GITHUB_HEAD_REF="feat/magnata-os-claude-powerpack" bash scripts/ci/validate_governance.sh branch >/dev/null 2>&1; then
    result="FAIL"
  fi

  if ! GITHUB_REF_NAME="feat/magnata-os-claude-powerpack" bash scripts/ci/validate_governance.sh branch >/dev/null 2>&1; then
    result="FAIL"
  fi

  # Sem nenhuma variável do Actions, HEAD destacado continua bloqueando —
  # não pode virar aprovação silenciosa por acidente.
  if bash scripts/ci/validate_governance.sh branch >/dev/null 2>&1; then
    result="FAIL"
  fi

  git checkout -q feat/magnata-os-claude-powerpack

  test_result "$result"
}

# TEST 29: a branch antiga (feat/magnata-os-claude-powerpack) precisa
# continuar autorizada depois da migração para fonte canônica de branches.
test_29_authorized_branch_old() {
  run_test 29 "Branch antiga autorizada (feat/magnata-os-claude-powerpack) aprova" "PASS"

  cd "$TEST_REPO"
  if GITHUB_HEAD_REF="feat/magnata-os-claude-powerpack" bash scripts/ci/validate_governance.sh branch >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 30: a branch nova da Etapa 6 (feat/magnata-os-etapa6-governanca)
# precisa aprovar — inclusive no cenário real de PR (com base/head, como o
# PR #13), não só numa checagem isolada de nome.
test_30_authorized_branch_new_etapa6() {
  run_test 30 "Branch nova da Etapa 6 (feat/magnata-os-etapa6-governanca) aprova, inclusive com base/head reais" "PASS"

  cd "$TEST_REPO"
  local base_sha head_sha
  base_sha=$(git rev-parse HEAD)
  head_sha=$(git rev-parse HEAD)

  local result="PASS"
  if ! GITHUB_HEAD_REF="feat/magnata-os-etapa6-governanca" bash scripts/ci/validate_governance.sh branch >/dev/null 2>&1; then
    result="FAIL"
  fi
  if ! GITHUB_HEAD_REF="feat/magnata-os-etapa6-governanca" bash scripts/ci/validate_governance.sh branch "$base_sha" "$head_sha" >/dev/null 2>&1; then
    result="FAIL"
  fi

  test_result "$result"
}

# TEST 31: branch arbitrária, não enumerada em AUTHORIZED_BRANCHES,
# continua bloqueada — comprova que a fonte canônica é uma enumeração
# fechada, não um regex genérico tipo "feat/*".
test_31_arbitrary_branch_still_blocked() {
  run_test 31 "Branch arbitrária não listada continua bloqueada (sem regex genérica)" "FAIL"

  cd "$TEST_REPO"
  if GITHUB_HEAD_REF="feat/branch-nao-autorizada" bash scripts/ci/validate_governance.sh branch >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 32: hook local (pre-commit) e validador (CI) precisam concordar
# sobre a mesma branch nova autorizada — comprova que os dois consomem a
# mesma fonte canônica (AUTHORIZED_BRANCHES em .magnata/patterns.sh), não
# listas paralelas divergentes.
test_32_hook_and_validator_agree_on_new_branch() {
  run_test 32 "Hook local e validador concordam sobre feat/magnata-os-etapa6-governanca" "PASS"

  cd "$TEST_REPO"
  local original_branch
  original_branch=$(git rev-parse --abbrev-ref HEAD)

  git checkout -q -b feat/magnata-os-etapa6-governanca
  echo "# doc permitido" > MAGNATA_OS_TEST32.md
  git add MAGNATA_OS_TEST32.md

  local result="PASS"
  # Validador (CI): mesma branch, via GITHUB_HEAD_REF.
  if ! GITHUB_HEAD_REF="feat/magnata-os-etapa6-governanca" bash scripts/ci/validate_governance.sh branch >/dev/null 2>&1; then
    result="FAIL"
  fi
  # Hook local: commit real na branch nova precisa passar pela VALIDAÇÃO 1.
  if ! git commit -m "docs: teste 32 branch nova no hook" >/dev/null 2>&1; then
    result="FAIL"
  fi

  git checkout -q "$original_branch"
  git branch -q -D feat/magnata-os-etapa6-governanca >/dev/null 2>&1 || true

  test_result "$result"
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
  echo -e "${BLUE}===================================="
  echo "SUÍTE DE TESTES DE GOVERNANÇA"
  echo "===================================${NC}"
  echo ""

  # Setup
  setup_test_repo || {
    echo -e "${RED}Falha ao setup do repositório de teste${NC}"
    return 1
  }

  trap cleanup_test_repo EXIT

  # Run all tests — cada teste roda até o fim mesmo se um caso falhar
  # (o resultado é contabilizado via TESTS_FAILED, não via aborto do script)
  test_1_valid_change || true
  test_2_app_py_altered || true
  test_3_migration_altered || true
  test_4_frontend_altered || true
  test_5_secret_detected || true
  test_6_trailing_whitespace || true
  test_7_11_module_security || true
  test_8_9_layers || true
  test_9_autonomy_percent || true
  test_10_adr_silent || true
  test_11_required_doc_missing || true
  test_12_claude_hierarchy_incomplete || true
  test_13_hook_mode_755 || true
  test_14_workflow_mode_644 || true
  test_15_full_suite || true
  test_16_ci_diff_scope || true
  test_17_clean_multi_commit_range || true
  test_18_push_intermediate_violation || true
  test_19_invalid_base_ref || true
  test_20_secret_gate_doc_mention_not_false_positive || true
  test_21_sensitive_filename_blocked || true
  test_22_real_secret_in_doc_blocked || true
  test_23_semantic_gate_technical_mention_not_false_positive || true
  test_24_semantic_gate_normative_redefinition_blocked || true
  test_25_secret_in_technical_doc_still_blocked || true
  test_26_gate15_self_sufficient_no_installed_hooks || true
  test_27_gate16_report_final_completes || true
  test_28_gate_branch_context_aware || true
  test_29_authorized_branch_old || true
  test_30_authorized_branch_new_etapa6 || true
  test_31_arbitrary_branch_still_blocked || true
  test_32_hook_and_validator_agree_on_new_branch || true

  # Report
  echo ""
  echo -e "${BLUE}===================================="
  echo "RESULTADO DOS TESTES"
  echo "===================================${NC}"
  echo ""
  echo "Testes executados: $TESTS_RUN"
  echo -e "${GREEN}Testes aprovados: $TESTS_PASSED${NC}"
  echo -e "${RED}Testes falhados: $TESTS_FAILED${NC}"
  echo ""

  if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ TODOS OS $TESTS_RUN TESTES APROVADOS${NC}"
    return 0
  else
    echo -e "${RED}✗ ALGUNS TESTES FALHARAM${NC}"
    return 1
  fi
}

main "$@"
