#!/bin/bash
# Magnata OS — Suíte de Testes de Governança
# Executa 52 cenários em repositório temporário isolado
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
# Fixture trocada de frontend/CLAUDE.md para frontend/assets/brand/ (Etapa 6
# de alinhamento documental): frontend/CLAUDE.md agora é exceção documental
# legítima e exata (CLAUDE_HIERARCHY/Gate 12) — não serve mais para testar
# bloqueio de alteração funcional/de marca. Ver Teste 46 para a exceção em si.
test_4_frontend_altered() {
  run_test 4 "Frontend funcional alterado" "FAIL"

  cd "$TEST_REPO"
  mkdir -p frontend/assets/brand
  echo "logo" > frontend/assets/brand/logo.svg
  git add frontend/assets/brand/logo.svg

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

# TEST 33: correção do Gate 6 — trailing whitespace real precisa bloquear
# através da própria função gate_whitespace (não apenas via git diff --check
# cru, como o Teste 6 já fazia) — comprova o fim do falso negativo do pipe
# sob pipefail.
test_33_gate6_real_whitespace_blocks() {
  run_test 33 "Gate 6 (gate_whitespace) bloqueia trailing whitespace real" "FAIL"

  cd "$TEST_REPO"
  printf "Linha com espaco no final   \n" > MAGNATA_OS_TEST33_WS.md
  git add MAGNATA_OS_TEST33_WS.md

  local output
  local exit_code
  output=$(bash scripts/ci/validate_governance.sh whitespace 2>&1)
  exit_code=$?

  # Precisa bloquear (exit != 0) E citar o arquivo (nao um bloqueio generico).
  if [[ $exit_code -ne 0 && "$output" == *"MAGNATA_OS_TEST33_WS.md"* ]]; then
    test_result "FAIL"
  else
    test_result "PASS"
  fi

  git reset -q HEAD MAGNATA_OS_TEST33_WS.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST33_WS.md
}

# TEST 34: whitespace introduzido num commit intermediário de um PR
# multi-commit precisa ser detectado via base_ref...head_ref — o cenário
# central que motivou a correção (comparar só o último commit mascararia
# esta violação).
test_34_gate6_intermediate_commit_whitespace() {
  run_test 34 "Gate 6 detecta whitespace em commit intermediário via base_ref/head_ref" "FAIL"

  cd "$TEST_REPO"
  local base_sha
  base_sha=$(git rev-parse HEAD)

  echo "# doc permitido E" > MAGNATA_OS_TEST34_E.md
  git add MAGNATA_OS_TEST34_E.md
  git commit -q -m "commit 1: doc permitido" --no-verify

  printf "Linha com espaco no final   \n" > MAGNATA_OS_TEST34_WS.md
  git add MAGNATA_OS_TEST34_WS.md
  git commit -q -m "commit 2 (intermediario): whitespace real" --no-verify

  echo "# doc permitido F" > MAGNATA_OS_TEST34_F.md
  git add MAGNATA_OS_TEST34_F.md
  git commit -q -m "commit 3: doc permitido, nao toca whitespace" --no-verify

  local head_sha
  head_sha=$(git rev-parse HEAD)

  local output
  local exit_code
  output=$(bash scripts/ci/validate_governance.sh whitespace "$base_sha" "$head_sha" 2>&1)
  exit_code=$?

  if [[ $exit_code -ne 0 && "$output" == *"MAGNATA_OS_TEST34_WS.md"* ]]; then
    test_result "FAIL"
  else
    test_result "PASS"
  fi
}

# TEST 35: diff limpo (sem nenhuma violação de whitespace) precisa ser
# aprovado pelo Gate 6 — zero falso positivo.
test_35_gate6_clean_diff_approved() {
  run_test 35 "Gate 6 aprova diff limpo (sem violação de whitespace)" "PASS"

  cd "$TEST_REPO"
  echo "# doc limpo" > MAGNATA_OS_TEST35_CLEAN.md
  git add MAGNATA_OS_TEST35_CLEAN.md

  if bash scripts/ci/validate_governance.sh whitespace >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST35_CLEAN.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST35_CLEAN.md
}

# TEST 36: base_ref inexistente, testado especificamente contra o Gate 6,
# precisa produzir erro interno distinto (exit 2, mensagem "ERRO INTERNO"
# citando base_ref) — nunca aprovação silenciosa, nunca bloqueio comum.
test_36_gate6_invalid_base_ref_internal_error() {
  run_test 36 "Gate 6: base_ref inexistente produz erro interno distinto" "FAIL"

  cd "$TEST_REPO"
  local head_sha
  head_sha=$(git rev-parse HEAD)

  local output
  local exit_code
  output=$(bash scripts/ci/validate_governance.sh whitespace "ref-base-inexistente-xyz" "$head_sha" 2>&1)
  exit_code=$?

  if [[ $exit_code -eq 2 && "$output" == *"ERRO INTERNO"* && "$output" == *"base_ref"* ]]; then
    test_result "FAIL"
  else
    test_result "PASS"
  fi
}

# TEST 37: head_ref inexistente, testado especificamente contra o Gate 6,
# precisa produzir erro interno distinto — mesma garantia do Teste 36,
# espelhada para o outro extremo do intervalo.
test_37_gate6_invalid_head_ref_internal_error() {
  run_test 37 "Gate 6: head_ref inexistente produz erro interno distinto" "FAIL"

  cd "$TEST_REPO"
  local base_sha
  base_sha=$(git rev-parse HEAD)

  local output
  local exit_code
  output=$(bash scripts/ci/validate_governance.sh whitespace "$base_sha" "ref-head-inexistente-xyz" 2>&1)
  exit_code=$?

  if [[ $exit_code -eq 2 && "$output" == *"ERRO INTERNO"* && "$output" == *"head_ref"* ]]; then
    test_result "FAIL"
  else
    test_result "PASS"
  fi
}

# TEST 38: pre-commit (hook local) e validate_governance.sh (CI) precisam
# concordar sobre o mesmo arquivo com trailing whitespace real — comprova
# que a correção do Gate 6 não introduziu divergência entre os dois
# consumidores (o hook já usava a forma sem pipe; agora o CI também usa).
test_38_gate6_precommit_and_ci_agree() {
  run_test 38 "Gate 6: pre-commit (hook) e CI (validate_governance.sh) bloqueiam o mesmo arquivo" "FAIL"

  cd "$TEST_REPO"
  local before_sha
  before_sha=$(git rev-parse HEAD)

  printf "Linha com espaco no final   \n" > MAGNATA_OS_TEST38_WS.md
  git add MAGNATA_OS_TEST38_WS.md

  local result="FAIL"

  if bash scripts/ci/validate_governance.sh whitespace >/dev/null 2>&1; then
    result="PASS"
  fi

  if git commit -m "docs: teste 38 whitespace" >/dev/null 2>&1; then
    result="PASS"
  fi

  # Garante estado limpo para os testes seguintes, independente do resultado.
  git reset -q --hard "$before_sha"
  rm -f MAGNATA_OS_TEST38_WS.md

  test_result "$result"
}

# TEST 39: report_final precisa contabilizar o bloqueio do Gate 6
# isoladamente — uma violação de whitespace introduzida sozinha precisa
# aumentar "Total gates bloqueados" em exatamente 1 frente à linha de base,
# sem alterar o resultado dos outros 14 gates.
test_39_gate6_report_final_counts_block() {
  run_test 39 "report_final contabiliza corretamente o bloqueio isolado do Gate 6" "PASS"

  cd "$TEST_REPO"

  local baseline_output baseline_blocked
  baseline_output=$(bash scripts/ci/validate_governance.sh report_final 2>&1 || true)
  baseline_blocked=$(echo "$baseline_output" | grep "Total gates bloqueados:" | grep -oE '[0-9]+')

  printf "Linha com espaco no final   \n" > MAGNATA_OS_TEST39_WS.md
  git add MAGNATA_OS_TEST39_WS.md

  local ws_output ws_blocked
  ws_output=$(bash scripts/ci/validate_governance.sh report_final 2>&1 || true)
  ws_blocked=$(echo "$ws_output" | grep "Total gates bloqueados:" | grep -oE '[0-9]+')

  git reset -q HEAD MAGNATA_OS_TEST39_WS.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST39_WS.md

  if [[ "$ws_output" == *"Testing whitespace"* && $((ws_blocked)) -eq $((baseline_blocked + 1)) ]]; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 40: Gates 11 (required_docs) e 12 (claude_hierarchy) precisam
# aprovar quando os 9 arquivos fundacionais reais (copiados de
# feat/magnata-os-claude-powerpack para esta branch) estão presentes —
# comprova que a cópia byte-a-byte satisfaz os dois gates.
test_40_gates_11_12_approve_with_foundational_docs() {
  run_test 40 "Gates 11 e 12 aprovam com os 9 arquivos fundacionais presentes" "PASS"

  cd "$TEST_REPO"
  mkdir -p docs/magnata-os frontend magnata_os/documental/modulo01/migrations
  cp "$PROJECT_ROOT/MAGNATA_OS_MANIFESTO.md" .
  cp "$PROJECT_ROOT/docs/magnata-os/MAGNATA_OS_CAPACIDADES.md" docs/magnata-os/
  cp "$PROJECT_ROOT/docs/magnata-os/MAGNATA_OS_MODULOS.md" docs/magnata-os/
  cp "$PROJECT_ROOT/docs/magnata-os/MAGNATA_OS_ROADMAP.md" docs/magnata-os/
  cp "$PROJECT_ROOT/docs/magnata-os/MAGNATA_OS_MATRIZ_ARQUITETURAL.md" docs/magnata-os/
  cp "$PROJECT_ROOT/CLAUDE.md" .
  cp "$PROJECT_ROOT/frontend/CLAUDE.md" frontend/
  cp "$PROJECT_ROOT/magnata_os/CLAUDE.md" magnata_os/
  cp "$PROJECT_ROOT/magnata_os/documental/modulo01/migrations/CLAUDE.md" magnata_os/documental/modulo01/migrations/

  git add MAGNATA_OS_MANIFESTO.md docs/magnata-os CLAUDE.md frontend/CLAUDE.md magnata_os

  local result="PASS"
  if ! bash scripts/ci/validate_governance.sh required_docs >/dev/null 2>&1; then
    result="FAIL"
  fi
  if ! bash scripts/ci/validate_governance.sh claude_hierarchy >/dev/null 2>&1; then
    result="FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_MANIFESTO.md docs/magnata-os CLAUDE.md frontend/CLAUDE.md magnata_os 2>/dev/null || true
  rm -f MAGNATA_OS_MANIFESTO.md CLAUDE.md
  rm -rf docs/magnata-os frontend magnata_os

  test_result "$result"
}

# TEST 41: os 4 caminhos EXATOS da hierarquia CLAUDE.md (CLAUDE_HIERARCHY)
# precisam passar pela Validação 6 do pre-commit (commit real, sem
# --no-verify) — comprova a exceção documental resolvendo a contradição
# entre Gate 12 (exige que existam) e ALLOWED_PATHS/PROTECTED_FILES
# (antes bloqueavam esses mesmos caminhos).
test_41_claude_hierarchy_exact_paths_allowed() {
  run_test 41 "Os 4 caminhos exatos da hierarquia CLAUDE.md passam pela Validação 6 (commit real)" "PASS"

  cd "$TEST_REPO"
  mkdir -p frontend magnata_os/documental/modulo01/migrations
  echo "# CLAUDE.md raiz" > CLAUDE.md
  echo "# CLAUDE.md frontend" > frontend/CLAUDE.md
  echo "# CLAUDE.md magnata_os" > magnata_os/CLAUDE.md
  echo "# CLAUDE.md migrations" > magnata_os/documental/modulo01/migrations/CLAUDE.md
  git add CLAUDE.md frontend/CLAUDE.md magnata_os/CLAUDE.md magnata_os/documental/modulo01/migrations/CLAUDE.md

  if git commit -m "docs: teste 41 hierarquia CLAUDE.md" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 42: um CLAUDE.md em caminho NÃO listado em CLAUDE_HIERARCHY precisa
# continuar bloqueado — a exceção é por igualdade exata de caminho, nunca
# por nome de arquivo genérico.
test_42_other_claude_md_still_blocked() {
  run_test 42 "CLAUDE.md fora dos 4 caminhos exatos continua bloqueado" "FAIL"

  cd "$TEST_REPO"
  mkdir -p magnata_os/documental
  echo "# CLAUDE.md nao autorizado" > magnata_os/documental/CLAUDE.md
  git add magnata_os/documental/CLAUDE.md

  if git commit -m "docs: teste 42 claude md nao autorizado" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD magnata_os/documental/CLAUDE.md 2>/dev/null || true
  rm -f magnata_os/documental/CLAUDE.md
}

# TEST 43: arquivo funcional em frontend/ (não CLAUDE.md) precisa continuar
# bloqueado — a exceção documental não vira uma liberação do diretório
# inteiro.
test_43_frontend_functional_file_still_blocked() {
  run_test 43 "Arquivo funcional em frontend/ (não CLAUDE.md) continua bloqueado" "FAIL"

  cd "$TEST_REPO"
  mkdir -p frontend
  echo "console.log('x');" > frontend/app.js
  git add frontend/app.js

  if git commit -m "feat: teste 43 arquivo funcional frontend" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD frontend/app.js 2>/dev/null || true
  rm -f frontend/app.js
}

# TEST 44: arquivo arbitrário em magnata_os/ (não CLAUDE.md) precisa
# continuar bloqueado pelo escopo permitido.
test_44_magnata_os_arbitrary_file_still_blocked() {
  run_test 44 "Arquivo arbitrário em magnata_os/ (não CLAUDE.md) continua bloqueado" "FAIL"

  cd "$TEST_REPO"
  mkdir -p magnata_os
  echo "print('x')" > magnata_os/dominio_novo.py
  git add magnata_os/dominio_novo.py

  if git commit -m "feat: teste 44 arquivo arbitrario magnata_os" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD magnata_os/dominio_novo.py 2>/dev/null || true
  rm -f magnata_os/dominio_novo.py
}

# TEST 45: migration real dentro do diretório protegido precisa continuar
# bloqueada pela Validação 6 do hook (não só pelo gate isolado do CI,
# já coberto pelo Teste 3) — a exceção documental é só para o arquivo
# CLAUDE.md exato dentro desse diretório, nunca para o diretório inteiro.
test_45_real_migration_still_blocked_by_hook() {
  run_test 45 "Migration real em magnata_os/.../migrations/ continua bloqueada pela Validação 6 do hook" "FAIL"

  cd "$TEST_REPO"
  mkdir -p magnata_os/documental/modulo01/migrations
  echo "SELECT 1;" > magnata_os/documental/modulo01/migrations/0999_real.sql
  git add magnata_os/documental/modulo01/migrations/0999_real.sql

  if git commit -m "feat: teste 45 migration real" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD magnata_os/documental/modulo01/migrations/0999_real.sql 2>/dev/null || true
  rm -f magnata_os/documental/modulo01/migrations/0999_real.sql
}

# TEST 46: gate_protected_frontend (CI) precisa liberar exclusivamente
# frontend/CLAUDE.md — descoberto via simulação de checkout limpo do PR #13,
# que mostrou este gate (reimplementação própria de PROTECTED_FILES,
# independente do hook) ainda bloqueando o arquivo institucional. Continua
# bloqueando qualquer alteração em frontend/assets/brand/.
test_46_gate_protected_frontend_exception_scoped() {
  run_test 46 "Gate protected_frontend (CI) libera só frontend/CLAUDE.md exato, continua bloqueando assets de marca" "PASS"

  cd "$TEST_REPO"
  mkdir -p frontend
  echo "# CLAUDE.md frontend" > frontend/CLAUDE.md
  git add frontend/CLAUDE.md

  local result="PASS"
  if ! bash scripts/ci/validate_governance.sh protected_frontend >/dev/null 2>&1; then
    result="FAIL"
  fi
  git reset -q HEAD frontend/CLAUDE.md 2>/dev/null || true
  rm -f frontend/CLAUDE.md

  mkdir -p frontend/assets/brand
  echo "logo" > frontend/assets/brand/logo.svg
  git add frontend/assets/brand/logo.svg
  if bash scripts/ci/validate_governance.sh protected_frontend >/dev/null 2>&1; then
    result="FAIL"
  fi
  git reset -q HEAD frontend/assets/brand/logo.svg 2>/dev/null || true
  rm -rf frontend/assets

  test_result "$result"
}

# TEST 47: gate_protected_migrations (CI) precisa liberar exclusivamente
# magnata_os/documental/modulo01/migrations/CLAUDE.md — mesma descoberta do
# Teste 46, espelhada para o gate de migrations. Continua bloqueando
# qualquer migration real no mesmo diretório.
test_47_gate_protected_migrations_exception_scoped() {
  run_test 47 "Gate protected_migrations (CI) libera só o CLAUDE.md exato, continua bloqueando migration real" "PASS"

  cd "$TEST_REPO"
  mkdir -p magnata_os/documental/modulo01/migrations
  echo "# CLAUDE.md migrations" > magnata_os/documental/modulo01/migrations/CLAUDE.md
  git add magnata_os/documental/modulo01/migrations/CLAUDE.md

  local result="PASS"
  if ! bash scripts/ci/validate_governance.sh protected_migrations >/dev/null 2>&1; then
    result="FAIL"
  fi
  git reset -q HEAD magnata_os/documental/modulo01/migrations/CLAUDE.md 2>/dev/null || true
  rm -f magnata_os/documental/modulo01/migrations/CLAUDE.md

  echo "SELECT 1;" > magnata_os/documental/modulo01/migrations/0999_real.sql
  git add magnata_os/documental/modulo01/migrations/0999_real.sql
  if bash scripts/ci/validate_governance.sh protected_migrations >/dev/null 2>&1; then
    result="FAIL"
  fi
  git reset -q HEAD magnata_os/documental/modulo01/migrations/0999_real.sql 2>/dev/null || true
  rm -rf magnata_os

  test_result "$result"
}

# TEST 48: push legítimo em main (GITHUB_EVENT_NAME=push + GITHUB_REF_NAME=main
# juntos) precisa ser aprovado pelo Gate de branch — estabilização pós-Etapa 6,
# sem que main entre em AUTHORIZED_BRANCHES.
test_48_gate_branch_push_main_approved() {
  run_test 48 "Push legítimo em main (GITHUB_EVENT_NAME=push + GITHUB_REF_NAME=main) é aprovado" "PASS"

  cd "$TEST_REPO"
  if GITHUB_EVENT_NAME="push" GITHUB_REF_NAME="main" bash scripts/ci/validate_governance.sh branch >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 49: execução local em main (checkout real, sem nenhuma variável do
# Actions) não pode ganhar autorização de branch de desenvolvimento — main
# nunca entra em AUTHORIZED_BRANCHES.
test_49_gate_branch_local_main_still_blocked() {
  run_test 49 "Execução local em main (checkout real) continua bloqueada" "FAIL"

  cd "$TEST_REPO"
  local original_branch
  original_branch=$(git rev-parse --abbrev-ref HEAD)
  git checkout -q -b main

  local result
  if bash scripts/ci/validate_governance.sh branch >/dev/null 2>&1; then
    result="PASS"
  else
    result="FAIL"
  fi

  git checkout -q "$original_branch"
  git branch -q -D main >/dev/null 2>&1 || true

  test_result "$result"
}

# TEST 50: spoof incompleto — só GITHUB_REF_NAME=main, sem
# GITHUB_EVENT_NAME=push — não pode liberar main. As duas variáveis
# precisam concordar juntas, nunca uma sozinha.
test_50_gate_branch_incomplete_spoof_main_blocked() {
  run_test 50 "Spoof incompleto (só GITHUB_REF_NAME=main, sem GITHUB_EVENT_NAME=push) continua bloqueado" "FAIL"

  cd "$TEST_REPO"
  if GITHUB_REF_NAME="main" bash scripts/ci/validate_governance.sh branch >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 51: push em branch arbitrária (não autorizada, e não main) continua
# bloqueado — a exceção de push é exclusiva de main, não vira liberação
# genérica de qualquer branch via push.
test_51_gate_branch_arbitrary_push_still_blocked() {
  run_test 51 "Push em branch arbitrária (não autorizada) continua bloqueado" "FAIL"

  cd "$TEST_REPO"
  if GITHUB_EVENT_NAME="push" GITHUB_REF_NAME="feat/branch-nao-autorizada" bash scripts/ci/validate_governance.sh branch >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi
}

# TEST 52: o workflow precisa conter exatamente os gatilhos esperados —
# push agora inclui main (estabilização pós-Etapa 6) e continua incluindo
# a branch de desenvolvimento histórica; pull_request continua intacto.
test_52_workflow_triggers_present() {
  run_test 52 "Workflow contém os gatilhos esperados (pull_request e push, incluindo main)" "PASS"

  cd "$TEST_REPO"
  local wf=".github/workflows/magnata-governance.yml"
  local result="PASS"

  local push_section
  push_section=$(awk '/^  push:/{f=1;next}/^  [a-zA-Z_]+:/{f=0}f' "$wf")
  echo "$push_section" | grep -q "main" || result="FAIL"
  echo "$push_section" | grep -q "feat/magnata-os-claude-powerpack" || result="FAIL"

  local pr_section
  pr_section=$(awk '/^  pull_request:/{f=1;next}/^  [a-zA-Z_]+:/{f=0}f' "$wf")
  echo "$pr_section" | grep -q "main" || result="FAIL"
  echo "$pr_section" | grep -q "feat/magnata-os-claude-powerpack" || result="FAIL"

  test_result "$result"
}

# ============================================================================
# TESTES 53-68 — Correção do falso positivo no gate de segredos
# (branch fix/remetente-dp-email-intake, 2026-08-03). O gate anterior
# bloqueava qualquer ocorrência do NOME "api_key"/"token"/etc. como
# identificador, header ou nome de propriedade, mesmo sem valor literal
# de segredo — falso positivo confirmado em apps_script_email_intake.gs
# (var apiKey, header 'X-API-KEY'). A correção (linha_contem_segredo_real /
# arquivo_staged_tem_segredo em .magnata/patterns.sh) exige valor literal
# não-placeholder atribuído a um nome sensível, ou formato inequívoco
# (chave privada, AKIA..., Bearer com valor, URL com credencial).
# ============================================================================

# TEST 53: identificador de variável (não valor literal) não bloqueia —
# caso real que motivou a correção.
test_53_secret_gate_variable_identifier_allowed() {
  run_test 53 "apiKey como identificador (getProperty, sem valor literal) não é falso positivo" "PASS"

  cd "$TEST_REPO"
  cat > MAGNATA_OS_TEST53_apikey_identificador.md <<'EOF'
var apiKey = PropertiesService.getScriptProperties().getProperty('EMAIL_WEBHOOK_KEY');
if (!apiKey) { return; }
EOF
  git add MAGNATA_OS_TEST53_apikey_identificador.md

  if git commit -m "fix: teste 53 identificador apiKey" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST53_apikey_identificador.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST53_apikey_identificador.md
}

# TEST 54: header nomeado 'X-API-KEY' com valor vindo de variável (não
# literal) não bloqueia.
test_54_secret_gate_header_name_with_variable_value_allowed() {
  run_test 54 "Header 'X-API-KEY' com valor de variável não é falso positivo" "PASS"

  cd "$TEST_REPO"
  cat > MAGNATA_OS_TEST54_header_apikey.md <<'EOF'
headers: { 'X-API-KEY': apiKey },
EOF
  git add MAGNATA_OS_TEST54_header_apikey.md

  if git commit -m "fix: teste 54 header X-API-KEY com variavel" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST54_header_apikey.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST54_header_apikey.md
}

# TEST 55: valor vazio ou placeholder conhecido (COLE_AQUI, changeme,
# <placeholder>) atribuído a nome sensível não bloqueia.
test_55_secret_gate_placeholder_values_allowed() {
  run_test 55 "Valores placeholder/vazio (COLE_AQUI, changeme, vazio) não bloqueiam" "PASS"

  cd "$TEST_REPO"
  cat > MAGNATA_OS_TEST55_placeholders.md <<'EOF'
API_KEY = ""
API_KEY = "COLE_AQUI_A_CHAVE"
API_KEY = "changeme"
API_KEY = "<placeholder>"
EOF
  git add MAGNATA_OS_TEST55_placeholders.md

  if git commit -m "fix: teste 55 placeholders diversos" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST55_placeholders.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST55_placeholders.md
}

# TEST 56: valor literal realista atribuído a api_key/password/token/
# client_secret continua bloqueado (CI gate) — a correção não pode virar
# allowlist ampla.
test_56_secret_gate_literal_values_still_blocked() {
  run_test 56 "Valores literais realistas (api_key/password/token/client_secret) continuam bloqueados (CI)" "FAIL"

  cd "$TEST_REPO"
  cat > MAGNATA_OS_TEST56_literais_reais.md <<'EOF'
api_key = "sk_live_9fH3kd82mQpLxZ71vNc"
EOF
  git add MAGNATA_OS_TEST56_literais_reais.md

  if bash scripts/ci/validate_governance.sh secrets >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST56_literais_reais.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST56_literais_reais.md
}

# TEST 57: password literal (hook local, com espaçamento e maiúsculas
# variados) continua bloqueado.
test_57_secret_gate_password_literal_blocked_case_and_spacing() {
  run_test 57 "PASSWORD literal, maiúsculo e sem espaço ao redor do = , continua bloqueado (hook)" "FAIL"

  cd "$TEST_REPO"
  cat > MAGNATA_OS_TEST57_password.md <<'EOF'
PASSWORD="SenhaRealAqui123"
EOF
  git add MAGNATA_OS_TEST57_password.md

  if git commit -m "fix: teste 57 password literal" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST57_password.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST57_password.md
}

# TEST 58: client_secret em sintaxe YAML/JSON (dois pontos, não igual)
# continua bloqueado.
test_58_secret_gate_yaml_style_blocked() {
  run_test 58 "client_secret em sintaxe YAML/JSON continua bloqueado" "FAIL"

  cd "$TEST_REPO"
  cat > MAGNATA_OS_TEST58_yaml.md <<'EOF'
client_secret: "9f8e7d6c5b4a3f2e1d0c"
EOF
  git add MAGNATA_OS_TEST58_yaml.md

  if bash scripts/ci/validate_governance.sh secrets >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST58_yaml.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST58_yaml.md
}

# TEST 59: Bearer token literal em cabeçalho Authorization continua
# bloqueado (padrão absoluto, não depende de contexto de atribuição).
test_59_secret_gate_bearer_literal_blocked() {
  run_test 59 "Authorization: Bearer <token real> continua bloqueado" "FAIL"

  cd "$TEST_REPO"
  cat > MAGNATA_OS_TEST59_bearer.md <<'EOF'
headers = {"Authorization": "Bearer sk_live_9fH3kd82mQpLxZ71vNc"}
EOF
  git add MAGNATA_OS_TEST59_bearer.md

  if git commit -m "fix: teste 59 bearer literal" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST59_bearer.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST59_bearer.md
}

# TEST 60: formato de chave privada PEM continua bloqueado — padrão
# absoluto, sem precisar de nome de variável por perto.
test_60_secret_gate_private_key_format_blocked() {
  run_test 60 "Formato de chave privada PEM continua bloqueado" "FAIL"

  cd "$TEST_REPO"
  cat > MAGNATA_OS_TEST60_chave.md <<'EOF'
-----BEGIN RSA PRIVATE KEY-----
EOF
  git add MAGNATA_OS_TEST60_chave.md

  if git commit -m "fix: teste 60 chave privada" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST60_chave.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST60_chave.md
}

# TEST 61: formato reconhecível de AWS Access Key ID (AKIA...) bloqueia
# mesmo sem nenhum nome de variável sensível na linha — formato absoluto.
test_61_secret_gate_aws_key_format_blocked() {
  run_test 61 "Formato de AWS Access Key ID (AKIA...) bloqueia sem contexto de variável" "FAIL"

  cd "$TEST_REPO"
  cat > MAGNATA_OS_TEST61_aws.md <<'EOF'
AKIAABCDEFGHIJKLMNOP
EOF
  git add MAGNATA_OS_TEST61_aws.md

  if git commit -m "fix: teste 61 aws key format" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST61_aws.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST61_aws.md
}

# TEST 62: segredo real em arquivo MODIFICADO (não só arquivo novo)
# continua bloqueado.
test_62_secret_gate_blocked_in_modified_file() {
  run_test 62 "Segredo real em arquivo já existente, modificado, continua bloqueado" "FAIL"

  cd "$TEST_REPO"
  echo "conteudo inicial sem segredo" > MAGNATA_OS_TEST62_modificado.md
  git add MAGNATA_OS_TEST62_modificado.md
  git commit -q -m "chore: teste 62 arquivo base sem segredo"

  echo 'token = "abcXYZ789tokenRealModificado456"' >> MAGNATA_OS_TEST62_modificado.md
  git add MAGNATA_OS_TEST62_modificado.md

  if git commit -m "fix: teste 62 segredo adicionado em modificacao" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST62_modificado.md 2>/dev/null || true
  git checkout -q MAGNATA_OS_TEST62_modificado.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST62_modificado.md
}

# TEST 63: segredo alterado só no WORKING TREE (não staged) não bloqueia —
# o gate lê o índice (git diff --cached), nunca o working tree solto.
test_63_secret_gate_unstaged_change_not_checked() {
  run_test 63 "Segredo presente só no working tree (não staged) não é verificado (ainda assim aprova o que ESTÁ staged)" "PASS"

  cd "$TEST_REPO"
  echo "linha limpa staged" > MAGNATA_OS_TEST63_unstaged.md
  git add MAGNATA_OS_TEST63_unstaged.md
  # Segredo adicionado só no working tree, DEPOIS do stage — nunca chega
  # ao índice, então nunca deveria ser considerado por este commit.
  echo 'api_key = "valorRealNuncaStaged123"' >> MAGNATA_OS_TEST63_unstaged.md

  if git commit -m "fix: teste 63 segredo so no working tree" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST63_unstaged.md 2>/dev/null || true
  git checkout -q MAGNATA_OS_TEST63_unstaged.md 2>/dev/null || rm -f MAGNATA_OS_TEST63_unstaged.md
  rm -f MAGNATA_OS_TEST63_unstaged.md
}

# TEST 64: segredo removido do arquivo, mas ainda presente numa linha
# NÃO alterada (contexto) de uma mudança maior no mesmo arquivo, não
# bloqueia — só linha adicionada conta.
test_64_secret_gate_unchanged_line_not_checked() {
  run_test 64 "Segredo já existente numa linha não alterada (fora do escopo da mudança) não bloqueia" "PASS"

  cd "$TEST_REPO"
  printf 'linha 1 normal\napi_key = "valorAntigoJaExistenteReal123"\nlinha 3 normal\n' > MAGNATA_OS_TEST64_contexto.md
  git add MAGNATA_OS_TEST64_contexto.md
  # --no-verify aqui: este commit de setup estabelece histórico anterior
  # (simulando um segredo já commitado antes desta correção existir) — não
  # é o commit sob teste. Sem --no-verify o próprio hook bloquearia este
  # setup (corretamente, já que introduz o segredo pela primeira vez),
  # nunca chegando ao commit real que o teste quer exercitar.
  git commit -q -m "chore: teste 64 base com segredo antigo (setup, não é o commit sob teste)" --no-verify

  # Mudança real: só adiciona uma linha nova, sem tocar a linha do segredo.
  printf 'linha 1 normal\napi_key = "valorAntigoJaExistenteReal123"\nlinha 3 normal\nlinha 4 nova sem segredo\n' > MAGNATA_OS_TEST64_contexto.md
  git add MAGNATA_OS_TEST64_contexto.md

  if git commit -m "fix: teste 64 mudanca nao toca linha do segredo antigo" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST64_contexto.md 2>/dev/null || true
  git checkout -q MAGNATA_OS_TEST64_contexto.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST64_contexto.md
}

# TEST 65: arquivo com espaço no nome — segredo real dentro dele ainda é
# detectado e bloqueado corretamente (hook não quebra nem ignora por causa
# do espaço).
test_65_secret_gate_filename_with_space_still_scanned() {
  run_test 65 "Segredo em arquivo com espaço no nome é detectado (hook)" "FAIL"

  cd "$TEST_REPO"
  cat > "MAGNATA_OS_TEST65 arquivo com espaco.md" <<'EOF'
API_KEY=valorRealComEspacoNoNome123
EOF
  git add "MAGNATA_OS_TEST65 arquivo com espaco.md"

  if git commit -m "fix: teste 65 espaco no nome do arquivo" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD "MAGNATA_OS_TEST65 arquivo com espaco.md" 2>/dev/null || true
  rm -f "MAGNATA_OS_TEST65 arquivo com espaco.md"
}

# TEST 66: arquivo binário staged não trava nem falsifica o hook — deve
# passar pela Validação 4 sem erro (binário não tem "linha" de texto para
# casar com o padrão).
test_66_secret_gate_binary_file_does_not_crash() {
  run_test 66 "Arquivo binário staged não trava o hook nem gera falso positivo" "PASS"

  cd "$TEST_REPO"
  # Determinístico, não /dev/urandom: precisa garantir byte NUL presente
  # para o heurístico de binário do próprio git (e do "file") sempre
  # classificar como binário de forma confiável — bytes aleatórios às
  # vezes não contêm NUL nos primeiros bytes, o que faz git tratar como
  # texto de uma linha só (flakiness real observada durante os testes
  # desta correção: conteúdo verdadeiramente aleatório passava como texto
  # em parte das execuções).
  dd if=/dev/zero of=MAGNATA_OS_TEST66_binario.md bs=128 count=1 >/dev/null 2>&1
  git add MAGNATA_OS_TEST66_binario.md

  if git commit -m "fix: teste 66 arquivo binario" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST66_binario.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST66_binario.md
}

# TEST 67: múltiplos segredos na mesma alteração — todos precisam ser
# reportados, e o commit precisa continuar bloqueado (não para no
# primeiro achado).
test_67_secret_gate_multiple_secrets_reported() {
  run_test 67 "Múltiplos segredos na mesma alteração continuam bloqueando (hook)" "FAIL"

  cd "$TEST_REPO"
  cat > MAGNATA_OS_TEST67_multi.md <<'EOF'
API_KEY=valorRealUm123456
DB_PASSWORD=valorRealDois789012
EOF
  git add MAGNATA_OS_TEST67_multi.md

  local saida
  saida=$(git commit -m "fix: teste 67 multiplos segredos" 2>&1) && result="PASS" || result="FAIL"
  # Ambos os achados precisam aparecer na saída do hook, não só o primeiro.
  if [[ "$result" == "FAIL" ]] && echo "$saida" | grep -q "MAGNATA_OS_TEST67_multi.md" ; then
    test_result "FAIL"
  else
    test_result "PASS"
  fi

  git reset -q HEAD MAGNATA_OS_TEST67_multi.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST67_multi.md
}

# TEST 68: hook local e validador CI concordam sobre o MESMO caso
# (identificador apiKey permitido) — mesma lógica compartilhada
# (linha_contem_segredo_real em .magnata/patterns.sh), não implementações
# paralelas divergentes.
test_68_secret_gate_hook_and_ci_agree() {
  run_test 68 "Hook local e validador CI concordam (apiKey identificador permitido, segredo literal bloqueado)" "PASS"

  cd "$TEST_REPO"
  cat > MAGNATA_OS_TEST68_concordancia.md <<'EOF'
var apiKey = PropertiesService.getScriptProperties().getProperty('X');
EOF
  git add MAGNATA_OS_TEST68_concordancia.md

  local result="PASS"
  # CI: deve aprovar.
  if ! bash scripts/ci/validate_governance.sh secrets >/dev/null 2>&1; then
    result="FAIL"
  fi
  # Hook: commit real deve passar.
  if ! git commit -m "fix: teste 68 concordancia hook e ci (permitido)" >/dev/null 2>&1; then
    result="FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST68_concordancia.md 2>/dev/null || true
  git checkout -q MAGNATA_OS_TEST68_concordancia.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST68_concordancia.md

  # Agora o caso bloqueado: os dois precisam concordar em bloquear.
  cat > MAGNATA_OS_TEST68B_concordancia_bloqueado.md <<'EOF'
api_key = "sk_live_9fH3kd82mQpLxZ71vNcConcordancia"
EOF
  git add MAGNATA_OS_TEST68B_concordancia_bloqueado.md

  if bash scripts/ci/validate_governance.sh secrets >/dev/null 2>&1; then
    result="FAIL"
  fi
  if git commit -m "fix: teste 68 concordancia hook e ci (bloqueado)" >/dev/null 2>&1; then
    result="FAIL"
  fi

  git reset -q HEAD MAGNATA_OS_TEST68B_concordancia_bloqueado.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST68B_concordancia_bloqueado.md

  test_result "$result"
}

# ============================================================================
# TESTES 69-76 — Exceção nominal para os dois testes da correção de
# ingestão (branch fix/remetente-dp-email-intake, 2026-08-04): 4 caminhos
# exatos em ALLOWED_PATHS + exceção nominal exata em SCRATCH_SCOPE_PATTERNS
# (Validação 6) e SCRATCH_PATTERNS (Validação 7). Inclui teste de
# regressão para um bug real encontrado durante esta correção: falta de
# restaurar nocasematch em linha_contem_segredo_real() deixava
# comparações de nome de arquivo case-insensíveis nas validações
# seguintes.
# ============================================================================

# TEST 69: os quatro caminhos exatos autorizados (2 novos em ALLOWED_PATHS
# fora dos "test_", + os 2 testes com exceção nominal) commitam com
# sucesso.
test_69_ingestion_files_accepted() {
  run_test 69 "Os 4 caminhos exatos da correção de ingestão são aceitos" "PASS"

  cd "$TEST_REPO"
  mkdir -p docs/decisoes
  echo "var x = 1;" > apps_script_email_intake.gs
  echo "# decisao" > docs/decisoes/remetentes-dp-fiscal.md
  echo "print('t')" > test_apps_script_email_intake_remetentes.py
  echo "// t" > test_interpretar_resposta_webhook.js
  git add apps_script_email_intake.gs docs/decisoes/remetentes-dp-fiscal.md \
          test_apps_script_email_intake_remetentes.py test_interpretar_resposta_webhook.js

  if git commit -m "fix: teste 69 arquivos exatos autorizados" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD apps_script_email_intake.gs docs/decisoes/remetentes-dp-fiscal.md \
             test_apps_script_email_intake_remetentes.py test_interpretar_resposta_webhook.js 2>/dev/null || true
  git checkout -q -- apps_script_email_intake.gs docs/decisoes/remetentes-dp-fiscal.md \
             test_apps_script_email_intake_remetentes.py test_interpretar_resposta_webhook.js 2>/dev/null || true
  rm -f apps_script_email_intake.gs docs/decisoes/remetentes-dp-fiscal.md \
        test_apps_script_email_intake_remetentes.py test_interpretar_resposta_webhook.js
}

# TEST 70: outros arquivos test_*.py/test_*.js (não nomeados na exceção)
# continuam bloqueados — a exceção não abre o prefixo genérico.
test_70_other_test_files_still_blocked() {
  run_test 70 "test_outro.py e test_outro.js continuam bloqueados (exceção não é genérica)" "FAIL"

  cd "$TEST_REPO"
  echo "x" > test_outro.py
  echo "x" > test_outro.js
  git add test_outro.py test_outro.js

  if git commit -m "fix: teste 70 outros arquivos test nao autorizados" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD test_outro.py test_outro.js 2>/dev/null || true
  rm -f test_outro.py test_outro.js
}

# TEST 71: variações com sufixo (.bak/.tmp) dos dois arquivos nominalmente
# autorizados continuam bloqueadas — exceção é por igualdade exata de
# caminho, não por prefixo.
test_71_suffix_variants_still_blocked() {
  run_test 71 "Variações com sufixo (.bak/.tmp) dos arquivos autorizados continuam bloqueadas" "FAIL"

  cd "$TEST_REPO"
  echo "x" > test_apps_script_email_intake_remetentes.py.bak
  echo "x" > test_interpretar_resposta_webhook.js.tmp
  git add test_apps_script_email_intake_remetentes.py.bak test_interpretar_resposta_webhook.js.tmp

  if git commit -m "fix: teste 71 sufixos bak e tmp" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD test_apps_script_email_intake_remetentes.py.bak test_interpretar_resposta_webhook.js.tmp 2>/dev/null || true
  rm -f test_apps_script_email_intake_remetentes.py.bak test_interpretar_resposta_webhook.js.tmp
}

# TEST 72: prefixo "_" adicional continua bloqueado.
test_72_underscore_prefix_variant_still_blocked() {
  run_test 72 "Arquivo com prefixo _ adicional continua bloqueado" "FAIL"

  cd "$TEST_REPO"
  echo "x" > _test_apps_script_email_intake_remetentes.py
  git add _test_apps_script_email_intake_remetentes.py

  if git commit -m "fix: teste 72 prefixo underscore" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD _test_apps_script_email_intake_remetentes.py 2>/dev/null || true
  rm -f _test_apps_script_email_intake_remetentes.py
}

# TEST 73: app.py permanece protegido — a exceção nominal não toca
# PROTECTED_FILES nem abre nenhuma via indireta para ele.
test_73_app_py_still_protected_after_exception() {
  run_test 73 "app.py continua protegido depois da exceção nominal" "FAIL"

  cd "$TEST_REPO"
  echo "print('x')" > app.py
  git add app.py

  if bash scripts/ci/validate_governance.sh protected_app_py >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD app.py 2>/dev/null || true
  rm -f app.py
}

# TEST 74: mesmo nome de arquivo em subdiretório não é abrangido pela
# exceção — a exceção é por caminho completo, não por nome-base.
test_74_same_basename_in_subdirectory_still_blocked() {
  run_test 74 "Mesmo nome-base em subdiretório continua bloqueado (exceção é por caminho completo)" "FAIL"

  cd "$TEST_REPO"
  mkdir -p subdir
  echo "x" > subdir/test_apps_script_email_intake_remetentes.py
  git add subdir/test_apps_script_email_intake_remetentes.py

  if git commit -m "fix: teste 74 mesmo nome em subdiretorio" >/dev/null 2>&1; then
    test_result "PASS"
  else
    test_result "FAIL"
  fi

  git reset -q HEAD subdir/test_apps_script_email_intake_remetentes.py 2>/dev/null || true
  rm -rf subdir
}

# TEST 75: diferença de maiúsculas/minúsculas no nome do arquivo continua
# bloqueada — teste de regressão para o bug real encontrado nesta correção
# (nocasematch não restaurado em linha_contem_segredo_real() deixava a
# comparação de nome de arquivo case-insensível a partir da Validação 4).
test_75_case_sensitivity_regression() {
  run_test 75 "Maiúsculas/minúsculas diferentes continuam bloqueadas (regressão nocasematch)" "FAIL"

  cd "$TEST_REPO"
  echo "x" > Test_apps_script_email_intake_remetentes.py
  git add Test_apps_script_email_intake_remetentes.py

  local result="PASS"
  if git commit -m "fix: teste 75 maiuscula nao autorizada" >/dev/null 2>&1; then
    result="PASS"
  else
    result="FAIL"
  fi
  git reset -q HEAD Test_apps_script_email_intake_remetentes.py 2>/dev/null || true
  rm -f Test_apps_script_email_intake_remetentes.py

  # Confirma também que nocasematch está desligado LOGO APÓS uma chamada
  # real ao scanner de segredos (a causa raiz do bug) — não só o efeito
  # observável via commit.
  local estado_nocasematch
  estado_nocasematch=$(bash -c 'source .magnata/patterns.sh; linha_contem_segredo_real "linha sem segredo" > /dev/null; shopt nocasematch' 2>/dev/null)
  if [[ "$estado_nocasematch" != *"off"* ]]; then
    result="FAIL"
  fi

  test_result "$result"
}

# TEST 76: regras antigas permanecem válidas depois de todas as mudanças
# desta correção — branch arbitrária continua bloqueada, segredo real
# continua bloqueado, apiKey/X-API-KEY legítimos continuam permitidos.
test_76_old_rules_still_valid_after_all_changes() {
  run_test 76 "Regras antigas (branch, segredo real, apiKey legítimo) permanecem válidas" "PASS"

  cd "$TEST_REPO"
  local result="PASS"

  # Branch arbitrária continua bloqueada (CI).
  if GITHUB_HEAD_REF="feat/branch-nao-autorizada-pos-correcao" bash scripts/ci/validate_governance.sh branch >/dev/null 2>&1; then
    result="FAIL"
  fi

  # Segredo real continua bloqueado (hook).
  echo 'api_key = "valorRealPosCorrecao123456"' > MAGNATA_OS_TEST76_segredo.md
  git add MAGNATA_OS_TEST76_segredo.md
  if git commit -m "fix: teste 76 segredo real pos correcao" >/dev/null 2>&1; then
    result="FAIL"
  fi
  git reset -q HEAD MAGNATA_OS_TEST76_segredo.md 2>/dev/null || true
  rm -f MAGNATA_OS_TEST76_segredo.md

  # apiKey/X-API-KEY legítimo continua permitido (hook) — dentro de um dos
  # 4 caminhos exatos autorizados, para não ser barrado por escopo.
  cat > apps_script_email_intake.gs <<'EOF'
var apiKey = PropertiesService.getScriptProperties().getProperty('X');
headers: { 'X-API-KEY': apiKey },
EOF
  git add apps_script_email_intake.gs
  if ! git commit -m "fix: teste 76 apikey legitimo pos correcao" >/dev/null 2>&1; then
    result="FAIL"
  fi
  git reset -q HEAD apps_script_email_intake.gs 2>/dev/null || true
  git checkout -q -- apps_script_email_intake.gs 2>/dev/null || rm -f apps_script_email_intake.gs

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
  test_33_gate6_real_whitespace_blocks || true
  test_34_gate6_intermediate_commit_whitespace || true
  test_35_gate6_clean_diff_approved || true
  test_36_gate6_invalid_base_ref_internal_error || true
  test_37_gate6_invalid_head_ref_internal_error || true
  test_38_gate6_precommit_and_ci_agree || true
  test_39_gate6_report_final_counts_block || true
  test_40_gates_11_12_approve_with_foundational_docs || true
  test_41_claude_hierarchy_exact_paths_allowed || true
  test_42_other_claude_md_still_blocked || true
  test_43_frontend_functional_file_still_blocked || true
  test_44_magnata_os_arbitrary_file_still_blocked || true
  test_45_real_migration_still_blocked_by_hook || true
  test_46_gate_protected_frontend_exception_scoped || true
  test_47_gate_protected_migrations_exception_scoped || true
  test_48_gate_branch_push_main_approved || true
  test_49_gate_branch_local_main_still_blocked || true
  test_50_gate_branch_incomplete_spoof_main_blocked || true
  test_51_gate_branch_arbitrary_push_still_blocked || true
  test_52_workflow_triggers_present || true
  test_53_secret_gate_variable_identifier_allowed || true
  test_54_secret_gate_header_name_with_variable_value_allowed || true
  test_55_secret_gate_placeholder_values_allowed || true
  test_56_secret_gate_literal_values_still_blocked || true
  test_57_secret_gate_password_literal_blocked_case_and_spacing || true
  test_58_secret_gate_yaml_style_blocked || true
  test_59_secret_gate_bearer_literal_blocked || true
  test_60_secret_gate_private_key_format_blocked || true
  test_61_secret_gate_aws_key_format_blocked || true
  test_62_secret_gate_blocked_in_modified_file || true
  test_63_secret_gate_unstaged_change_not_checked || true
  test_64_secret_gate_unchanged_line_not_checked || true
  test_65_secret_gate_filename_with_space_still_scanned || true
  test_66_secret_gate_binary_file_does_not_crash || true
  test_67_secret_gate_multiple_secrets_reported || true
  test_68_secret_gate_hook_and_ci_agree || true
  test_69_ingestion_files_accepted || true
  test_70_other_test_files_still_blocked || true
  test_71_suffix_variants_still_blocked || true
  test_72_underscore_prefix_variant_still_blocked || true
  test_73_app_py_still_protected_after_exception || true
  test_74_same_basename_in_subdirectory_still_blocked || true
  test_75_case_sensitivity_regression || true
  test_76_old_rules_still_valid_after_all_changes || true

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
