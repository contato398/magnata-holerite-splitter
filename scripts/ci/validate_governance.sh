#!/bin/bash
# Magnata OS — Validador de Governança e Qualidade
# Executa os 16 gates de conformidade
# Uso: validate_governance.sh [gate_name|report_final] [base_ref] [head_ref]
#
# base_ref/head_ref são opcionais. Quando fornecidos, os gates que dependem
# do que mudou comparam base_ref...head_ref (todo o conjunto de commits do
# PR/push, via merge-base — mesma semântica que o GitHub usa para "Files
# changed" de um PR). Quando ausentes, mantém o comportamento anterior
# (staged, ou fallback HEAD^..HEAD) — usado localmente e pela suíte de testes.

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

# ============================================================================
# CONTRATO BASE/HEAD (Etapa 6 — correção de escopo de CI)
# ============================================================================
#
# base_ref/head_ref (2º/3º argumento posicional) são o contrato explícito
# de intervalo de diff. Todo evento de CI (pull_request, push,
# workflow_dispatch) DEVE fornecer os dois — o workflow garante isso e
# nunca invoca este script sem eles para esses três eventos.
#
# O fallback (staged, ou HEAD^..HEAD) existe SOMENTE para execução local
# humana (nenhum dos dois argumentos fornecido) e emite aviso explícito.
# Referência inválida em qualquer um dos dois argumentos é ERRO INTERNO —
# nunca é tratado como aprovação nem como bloqueio de gate comum.

BASE_REF="${2:-}"
HEAD_REF="${3:-}"
MIGRATION_AUTHORIZATION_FILE="${4:-}"

if [[ -n "$BASE_REF" && -n "$HEAD_REF" ]]; then
  if ! git cat-file -e "${BASE_REF}^{commit}" 2>/dev/null; then
    echo -e "${RED}${MSG_ERROR}: base_ref inválida ou inexistente: '${BASE_REF}'${NC}"
    exit 2
  fi
  if ! git cat-file -e "${HEAD_REF}^{commit}" 2>/dev/null; then
    echo -e "${RED}${MSG_ERROR}: head_ref inválida ou inexistente: '${HEAD_REF}'${NC}"
    exit 2
  fi
elif [[ -n "$BASE_REF" || -n "$HEAD_REF" ]]; then
  # Contrato incompleto: só um dos dois foi fornecido — não é modo local
  # (que exige os dois ausentes) nem intervalo válido. Erro interno.
  echo -e "${RED}${MSG_ERROR}: contrato base/head incompleto — base_ref='${BASE_REF}' head_ref='${HEAD_REF}'${NC}"
  exit 2
else
  echo -e "${YELLOW}MODO LOCAL — INTERVALO PADRÃO LIMITADO${NC}"
fi

# Lista de arquivos alterados no intervalo relevante
get_changed_files() {
  if [[ -n "$BASE_REF" && -n "$HEAD_REF" ]]; then
    git diff "${BASE_REF}...${HEAD_REF}" --name-only 2>/dev/null || echo ""
  else
    git diff --cached --name-only 2>/dev/null || git diff HEAD^..HEAD --name-only 2>/dev/null || echo ""
  fi
}

get_changed_files_with_status() {
  if [[ -n "$BASE_REF" && -n "$HEAD_REF" ]]; then
    git diff "${BASE_REF}...${HEAD_REF}" --name-status 2>/dev/null || echo ""
  else
    git diff --cached --name-status 2>/dev/null || echo ""
  fi
}

# Conteúdo do diff no intervalo relevante (para grep de padrão)
get_changed_diff() {
  if [[ -n "$BASE_REF" && -n "$HEAD_REF" ]]; then
    git diff "${BASE_REF}...${HEAD_REF}" 2>/dev/null || echo ""
  else
    git diff --cached 2>/dev/null || git diff HEAD^..HEAD 2>/dev/null || echo ""
  fi
}

# Saída de --check (whitespace) no intervalo relevante
get_changed_check() {
  if [[ -n "$BASE_REF" && -n "$HEAD_REF" ]]; then
    git diff "${BASE_REF}...${HEAD_REF}" --check 2>/dev/null
  else
    git diff --cached --check 2>/dev/null
  fi
}

# Diff de um único arquivo, no intervalo relevante (gates semânticos 7-10 —
# aplicados só a documentos normativos, ver is_normative_doc em patterns.sh)
get_changed_file_diff() {
  local file="$1"
  if [[ -n "$BASE_REF" && -n "$HEAD_REF" ]]; then
    git diff "${BASE_REF}...${HEAD_REF}" -- "$file" 2>/dev/null || echo ""
  else
    git diff --cached -- "$file" 2>/dev/null || git diff HEAD^..HEAD -- "$file" 2>/dev/null || echo ""
  fi
}

# State file for multi-gate runs
STATE_FILE="/tmp/magnata_governance_state.txt"
APPROVALS=0
BLOCKAGES=0
WARNINGS=0

# ============================================================================
# GATE 1: Branch Correta
# ============================================================================

gate_branch() {
  local branch
  if [[ -n "${GITHUB_HEAD_REF:-}" ]]; then
    # pull_request: actions/checkout deixa o HEAD destacado (aponta para o
    # merge commit), então git rev-parse --abbrev-ref HEAD retornaria "HEAD"
    # literal. GITHUB_HEAD_REF é a branch de origem real do PR.
    branch="$GITHUB_HEAD_REF"
  elif [[ "${GITHUB_EVENT_NAME:-}" == "push" && "${GITHUB_REF_NAME:-}" == "main" ]]; then
    # Push pós-merge em main: reconhecido só quando as DUAS variáveis do
    # Actions concordam (evento="push" E ref="main") — uma só, sozinha, não
    # basta (evita spoof incompleto/incoerente). Contexto distinto de
    # "branch de desenvolvimento autorizada": nunca passa por
    # is_authorized_branch, e main nunca entra em AUTHORIZED_BRANCHES.
    echo -e "${GREEN}${MSG_APPROVED}: push pós-merge em main (evento de CI legítimo)${NC}"
    return $EXIT_APPROVED
  elif [[ -n "${GITHUB_REF_NAME:-}" ]]; then
    # push (ou outro evento de Actions com ref de branch real) que não é
    # o par push+main acima — segue como branch de desenvolvimento comum.
    branch="$GITHUB_REF_NAME"
  else
    # Execução local/manual — usa o HEAD do git normalmente. Inclui
    # execução local em main: main nunca está em AUTHORIZED_BRANCHES, então
    # continua bloqueada aqui (nunca vira branch de desenvolvimento).
    branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "UNKNOWN")
  fi

  if ! is_authorized_branch "$branch"; then
    echo -e "${RED}${MSG_BLOCKED}: Branch incorreta${NC}"
    echo "  Branch atual: $branch"
    echo "  Branches autorizadas: ${AUTHORIZED_BRANCHES[*]}"
    return $EXIT_BLOCKED
  fi

  echo -e "${GREEN}${MSG_APPROVED}: Branch correta ($branch)${NC}"
  return $EXIT_APPROVED
}

# ============================================================================
# GATE 2: app.py Protegido
# ============================================================================

gate_protected_app_py() {
  local changed=$(get_changed_files)

  if echo "$changed" | grep -q "^app\.py$"; then
    # Verificar se há autorização por blob exato
    local authorization_found=0
    local actual_blob

    if [[ -n "$HEAD_REF" ]]; then
      actual_blob=$(git rev-parse "${HEAD_REF}:app.py" 2>/dev/null || echo "")
    else
      actual_blob=$(git hash-object --filters --path="app.py" "$PROJECT_ROOT/app.py" 2>/dev/null || echo "")
    fi

    # Procurar em todos os arquivos de autorização de app.py
    if [[ -d "$PROJECT_ROOT/.magnata/app-py-authorizations" ]]; then
      while IFS= read -r auth_file; do
        if [[ -z "$auth_file" ]] || [[ ! -f "$auth_file" ]]; then
          continue
        fi
        while read -r expected_blob authorized_path; do
          [[ -z "$expected_blob" || "$expected_blob" == \#* ]] && continue
          if [[ "$authorized_path" == "app.py" && "${expected_blob,,}" == "$actual_blob" ]]; then
            authorization_found=1
            break 2
          fi
        done < "$auth_file"
      done < <(find "$PROJECT_ROOT/.magnata/app-py-authorizations" -name "*.gitblob" -type f)
    fi

    if [[ $authorization_found -eq 0 ]]; then
      echo -e "${RED}${MSG_BLOCKED}: app.py foi alterado${NC}"
      echo "  app.py é arquivo protegido (legado)"
      echo "  Blob atual: $actual_blob"
      echo "  Nenhuma autorização válida por blob exato encontrada"
      return $EXIT_BLOCKED
    fi
  fi

  echo -e "${GREEN}${MSG_APPROVED}: app.py intacto ou autorizado${NC}"
  return $EXIT_APPROVED
}

# ============================================================================
# GATE 3: Migrations Protegidas
# ============================================================================

gate_protected_migrations() {
  local changed_with_status
  changed_with_status=$(get_changed_files_with_status)

  local authorization_ready=0
  if [[ -n "$MIGRATION_AUTHORIZATION_FILE" && -f "$PROJECT_ROOT/$MIGRATION_AUTHORIZATION_FILE" ]]; then
    local authorization_status
    authorization_status=$(printf '%s\n' "$changed_with_status" | awk -v file="$MIGRATION_AUTHORIZATION_FILE" '$1 == "A" && $2 == file { print $1 }')
    if [[ "$authorization_status" == "A" ]]; then
      authorization_ready=1
    fi
  fi

  while IFS=$'\t' read -r status file; do
    if [[ -z "$file" ]]; then continue; fi
    if [[ "$file" == *"magnata_os/documental/modulo01/migrations/"* ]]; then
      if is_claude_hierarchy_path "$file"; then
        continue
      fi

      # Somente migration nova, com manifesto novo no mesmo diff e hash exato.
      # Modificação/remoção continua sempre bloqueada e manifesto antigo não
      # pode ser reutilizado em outro PR.
      if [[ "$status" == "A" && $authorization_ready -eq 1 ]]; then
        local actual_blob expected_blob authorized_path
        if [[ -n "$HEAD_REF" ]]; then
          actual_blob=$(git rev-parse "${HEAD_REF}:$file")
        else
          actual_blob=$(git hash-object --filters --path="$file" "$PROJECT_ROOT/$file")
        fi
        while read -r expected_blob authorized_path; do
          [[ -z "$expected_blob" || "$expected_blob" == \#* ]] && continue
          if [[ "$authorized_path" == "$file" && "${expected_blob,,}" == "$actual_blob" ]]; then
            continue 2
          fi
        done < "$PROJECT_ROOT/$MIGRATION_AUTHORIZATION_FILE"
      fi

      echo -e "${RED}${MSG_BLOCKED}: Migrations foram alteradas${NC}"
      echo "  $file não possui autorização por objeto Git válida e nova neste diff"
      return $EXIT_BLOCKED
    fi
  done <<< "$changed_with_status"

  echo -e "${GREEN}${MSG_APPROVED}: Migrations intactas${NC}"
  return $EXIT_APPROVED
}

# ============================================================================
# GATE 4: Frontend Protegido
# ============================================================================

gate_protected_frontend() {
  local changed=$(get_changed_files)

  # Exceção documental (mesma is_claude_hierarchy_path de .magnata/patterns.sh
  # usada pela Validação 6 do pre-commit): só o caminho EXATO
  # frontend/CLAUDE.md atravessa — frontend/assets/brand/** e qualquer outro
  # arquivo continuam bloqueados.
  while IFS= read -r file; do
    if [[ -z "$file" ]]; then continue; fi
    if [[ "$file" =~ (frontend/CLAUDE\.md|frontend/assets/brand/) ]]; then
      if is_claude_hierarchy_path "$file"; then
        continue
      fi
      echo -e "${RED}${MSG_BLOCKED}: Frontend foi alterado${NC}"
      echo "  frontend/CLAUDE.md e frontend/assets/brand/** são protegidas"
      return $EXIT_BLOCKED
    fi
  done <<< "$changed"

  echo -e "${GREEN}${MSG_APPROVED}: Frontend intacto${NC}"
  return $EXIT_APPROVED
}

# ============================================================================
# GATE 5: Detecção de Segredos
# ============================================================================

gate_secrets() {
  # Mesma lógica do hook local (linha_contem_segredo_real, fonte única em
  # .magnata/patterns.sh): valor literal real, não bare match de
  # identificador/header sensível. Exclui arquivo-fonte dos próprios
  # padrões (is_protected... não, is_gate_pattern_source_file — os arrays
  # de padrão citam literalmente as palavras que eles mesmos detectam) e
  # considera só linhas ADICIONADAS de cada arquivo alterado.
  local files
  files=$(get_changed_files)
  local encontrou=0

  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    if is_gate_pattern_source_file "$file"; then
      continue
    fi

    local diff_arquivo
    diff_arquivo=$(get_changed_file_diff "$file")

    while IFS= read -r linha; do
      [[ "$linha" == "+++"* ]] && continue
      [[ "$linha" == "+"* ]] || continue
      local conteudo="${linha:1}"
      if linha_contem_segredo_real "$conteudo"; then
        echo "  Arquivo: $file"
        encontrou=1
      fi
    done <<< "$diff_arquivo"
  done <<< "$files"

  if [ $encontrou -eq 1 ]; then
    echo -e "${RED}${MSG_BLOCKED}: Padrão de segredo detectado (ver arquivo(s) acima)${NC}"
    return $EXIT_BLOCKED
  fi

  echo -e "${GREEN}${MSG_APPROVED}: Nenhum segredo detectado${NC}"
  return $EXIT_APPROVED
}

# ============================================================================
# GATE 6: Trailing Whitespace
# ============================================================================

gate_whitespace() {
  # Captura em variável, nunca em pipe: sob set -o pipefail, "git diff
  # --check | grep" faria o exit code do git vazar e derrotar o
  # resultado do grep, mascarando o bloqueio. Sem pipe, o código de
  # saída de get_changed_check() é exatamente o de "git diff --check":
  # 0 = limpo; 1 ou 2 = achou whitespace/marcador de conflito
  # (confirmado empiricamente: esta versão do git usa 2); qualquer
  # outro valor = falha real do git (erro interno, não bloqueio comum).
  local check_output
  local check_exit=0
  # "|| check_exit=$?", não uma atribuição simples: sob set -e, uma
  # atribuição simples cujo comando substituído falha aborta o script
  # inteiro imediatamente (confirmado empiricamente). Como parte de um
  # "||", a falha é isenta do gatilho do set -e — captura segura.
  check_output=$(get_changed_check) || check_exit=$?

  case "$check_exit" in
    0)
      echo -e "${GREEN}${MSG_APPROVED}: Whitespace válido${NC}"
      return $EXIT_APPROVED
      ;;
    1|2)
      echo -e "${RED}${MSG_BLOCKED}: Trailing whitespace detectado${NC}"
      echo "$check_output"
      return $EXIT_BLOCKED
      ;;
    *)
      echo -e "${RED}${MSG_ERROR}: git diff --check falhou de forma inesperada (exit $check_exit)${NC}"
      echo "$check_output"
      return 2
      ;;
  esac
}

# ============================================================================
# GATE 7: Segurança não é 11º Módulo
# ============================================================================

gate_11_module() {
  local changed_files=$(get_changed_files)

  local file
  while IFS= read -r file; do
    if [[ -z "$file" ]]; then continue; fi
    if ! is_normative_doc "$file"; then continue; fi

    local filtered=$(get_changed_file_diff "$file" | grep -v "GATE_11_MODULE_PATTERNS=" | grep -v "  \"")

    for pattern in "${GATE_11_MODULE_PATTERNS[@]}"; do
      if echo "$filtered" | grep -Eqi -- "$pattern" 2>/dev/null; then
        echo -e "${RED}${MSG_BLOCKED}: Segurança como módulo funcional detectado${NC}"
        echo "  Arquivo: $file"
        echo "  Padrão: $pattern"
        echo "  Segurança é camada transversal, não módulo funcional"
        return $EXIT_BLOCKED
      fi
    done
  done <<< "$changed_files"

  echo -e "${GREEN}${MSG_APPROVED}: Arquitetura sem 11º módulo funcional${NC}"
  return $EXIT_APPROVED
}

# ============================================================================
# GATE 8: Arquitetura não é 9 Camadas
# ============================================================================

gate_9_layers() {
  local changed_files=$(get_changed_files)

  local file
  while IFS= read -r file; do
    if [[ -z "$file" ]]; then continue; fi
    if ! is_normative_doc "$file"; then continue; fi

    local filtered=$(get_changed_file_diff "$file" | grep -v "GATE_9_LAYERS_PATTERNS=" | grep -v "  \"")

    for pattern in "${GATE_9_LAYERS_PATTERNS[@]}"; do
      if echo "$filtered" | grep -Eqi -- "$pattern" 2>/dev/null; then
        echo -e "${RED}${MSG_BLOCKED}: Arquitetura de 9 camadas detectada${NC}"
        echo "  Arquivo: $file"
        echo "  Padrão: $pattern"
        echo "  Arquitetura oficial: Entrada → Inteligência → Transformação → Negócio → Entrega → Auditoria"
        return $EXIT_BLOCKED
      fi
    done
  done <<< "$changed_files"

  echo -e "${GREEN}${MSG_APPROVED}: Arquitetura conforme especificação${NC}"
  return $EXIT_APPROVED
}

# ============================================================================
# GATE 9: Autonomia não é Percentual Abstrato
# ============================================================================

gate_autonomy_percent() {
  local changed_files=$(get_changed_files)

  local file
  while IFS= read -r file; do
    if [[ -z "$file" ]]; then continue; fi
    if ! is_normative_doc "$file"; then continue; fi

    local filtered=$(get_changed_file_diff "$file" | grep -v "GATE_AUTONOMY_PERCENT_PATTERNS=" | grep -v "  \"")

    for pattern in "${GATE_AUTONOMY_PERCENT_PATTERNS[@]}"; do
      if echo "$filtered" | grep -Eqi -- "$pattern" 2>/dev/null; then
        echo -e "${RED}${MSG_BLOCKED}: Autonomia como percentual abstrato detectada${NC}"
        echo "  Arquivo: $file"
        echo "  Padrão: $pattern"
        echo "  Autonomia não é expressa como %"
        return $EXIT_BLOCKED
      fi
    done
  done <<< "$changed_files"

  echo -e "${GREEN}${MSG_APPROVED}: Autonomia sem percentual abstrato${NC}"
  return $EXIT_APPROVED
}

# ============================================================================
# GATE 10: ADR não Resolvida Silenciosamente
# ============================================================================

gate_adr_silent() {
  local changed_files=$(get_changed_files)

  local file
  while IFS= read -r file; do
    if [[ -z "$file" ]]; then continue; fi
    if ! is_normative_doc "$file"; then continue; fi

    local filtered=$(get_changed_file_diff "$file" | grep -v "GATE_ADR_SILENT_PATTERNS=" | grep -v "  \"")

    for pattern in "${GATE_ADR_SILENT_PATTERNS[@]}"; do
      if echo "$filtered" | grep -Eqi -- "$pattern" 2>/dev/null; then
        echo -e "${RED}${MSG_BLOCKED}: ADR resolvida silenciosamente detectada${NC}"
        echo "  Arquivo: $file"
        echo "  Padrão: $pattern"
        echo "  Decisão de nomeação requer ADR explícita"
        return $EXIT_BLOCKED
      fi
    done
  done <<< "$changed_files"

  echo -e "${GREEN}${MSG_APPROVED}: Sem ADR resolvida silenciosamente${NC}"
  return $EXIT_APPROVED
}

# ============================================================================
# GATE 11: Documentos Obrigatórios
# ============================================================================

gate_required_docs() {
  local missing=0

  for doc in "${REQUIRED_DOCS[@]}"; do
    # Check both root and docs/magnata-os/
    if [ ! -f "$PROJECT_ROOT/$doc" ] && [ ! -f "$PROJECT_ROOT/docs/magnata-os/$doc" ]; then
      echo -e "${RED}Documento ausente: $doc${NC}"
      missing=1
    fi
  done

  if [ $missing -eq 1 ]; then
    echo -e "${RED}${MSG_BLOCKED}: Documentos obrigatórios ausentes${NC}"
    return $EXIT_BLOCKED
  fi

  echo -e "${GREEN}${MSG_APPROVED}: Documentos obrigatórios presentes${NC}"
  return $EXIT_APPROVED
}

# ============================================================================
# GATE 12: CLAUDE.md Hierarquia (4 Níveis)
# ============================================================================

gate_claude_hierarchy() {
  local missing=0

  for file in "${CLAUDE_HIERARCHY[@]}"; do
    if [ ! -f "$PROJECT_ROOT/$file" ]; then
      echo -e "${RED}CLAUDE.md ausente: $file${NC}"
      missing=1
    fi
  done

  if [ $missing -eq 1 ]; then
    echo -e "${RED}${MSG_BLOCKED}: Hierarquia CLAUDE.md incompleta${NC}"
    return $EXIT_BLOCKED
  fi

  echo -e "${GREEN}${MSG_APPROVED}: CLAUDE.md hierarquia completa (4 níveis)${NC}"
  return $EXIT_APPROVED
}

# ============================================================================
# GATE 13: Scripts Shell com modo 100755
# ============================================================================

gate_script_mode_755() {
  local has_error=0

  for file in "${EXECUTABLE_FILES[@]}"; do
    if [ -f "$PROJECT_ROOT/$file" ]; then
      local git_mode=$(git ls-files --stage "$PROJECT_ROOT/$file" 2>/dev/null | awk '{print $1}' || echo "")
      if [[ -n "$git_mode" && "$git_mode" != "100755" ]]; then
        echo -e "${RED}Script sem modo 100755: $file (modo git: $git_mode)${NC}"
        has_error=1
      fi
    fi
  done

  if [ $has_error -eq 1 ]; then
    echo -e "${RED}${MSG_BLOCKED}: Scripts shell sem modo 100755${NC}"
    return $EXIT_BLOCKED
  fi

  echo -e "${GREEN}${MSG_APPROVED}: Scripts shell com modo correto (100755)${NC}"
  return $EXIT_APPROVED
}

# ============================================================================
# GATE 14: Workflows e Migrations com modo 100644
# ============================================================================

gate_config_mode_644() {
  local has_error=0

  for file in "${NON_EXECUTABLE_FILES[@]}"; do
    if [ -f "$PROJECT_ROOT/$file" ]; then
      local git_mode=$(git ls-files --stage "$PROJECT_ROOT/$file" 2>/dev/null | awk '{print $1}' || echo "")
      if [[ -n "$git_mode" && "$git_mode" != "100644" ]]; then
        echo -e "${RED}Config sem modo 100644: $file (modo git: $git_mode)${NC}"
        has_error=1
      fi
    fi
  done

  if [ $has_error -eq 1 ]; then
    echo -e "${RED}${MSG_BLOCKED}: Workflows/migrations sem modo 100644${NC}"
    return $EXIT_BLOCKED
  fi

  echo -e "${GREEN}${MSG_APPROVED}: Workflows/migrations com modo correto (100644)${NC}"
  return $EXIT_APPROVED
}

# ============================================================================
# GATE 15: Suite de Hooks Aprovada
# ============================================================================

gate_hooks_suite() {
  if [ -f "$PROJECT_ROOT/.githooks/test-hooks.sh" ]; then
    if bash "$PROJECT_ROOT/.githooks/test-hooks.sh" >/dev/null 2>&1; then
      echo -e "${GREEN}${MSG_APPROVED}: Suite de hooks aprovada (15/15)${NC}"
      return $EXIT_APPROVED
    else
      echo -e "${RED}${MSG_BLOCKED}: Suite de hooks reprovada${NC}"
      return $EXIT_BLOCKED
    fi
  else
    echo -e "${YELLOW}${MSG_WARNING}: test-hooks.sh não encontrado${NC}"
    return $EXIT_WARNING
  fi
}

# ============================================================================
# GATE 16: Relatório Final
# ============================================================================

report_final() {
  echo ""
  echo -e "${BLUE}================================"
  echo "RELATÓRIO FINAL DE GOVERNANÇA"
  echo "================================${NC}"
  echo ""

  # Run all gates
  local total_blocked=0
  local total_approved=0

  gates=("branch" "protected_app_py" "protected_migrations" "protected_frontend" "secrets" "whitespace" "11_module" "9_layers" "autonomy_percent" "adr_silent" "required_docs" "claude_hierarchy" "script_mode_755" "config_mode_644" "hooks_suite")

  for gate in "${gates[@]}"; do
    echo "[Gate] Testing $gate..."
    if gate_${gate} >/dev/null 2>&1; then
      # Forma de atribuição, não "((var++))": sob set -e, o pós-incremento
      # de 0 avalia como falso e aborta o script no primeiro gate testado.
      total_approved=$((total_approved + 1))
    else
      total_blocked=$((total_blocked + 1))
    fi
  done

  echo ""
  echo "Total gates aprovados: $total_approved"
  echo "Total gates bloqueados: $total_blocked"
  echo ""

  if [ $total_blocked -eq 0 ]; then
    echo -e "${GREEN}✓ Conformidade aprovada - Pronto para commit${NC}"
    return $EXIT_APPROVED
  else
    echo -e "${RED}✗ Conformidade bloqueada - Correções necessárias${NC}"
    return $EXIT_BLOCKED
  fi
}

# ============================================================================
# MAIN
# ============================================================================

main() {
  local command="${1:-report_final}"

  case "$command" in
    gate_branch|branch)
      gate_branch
      ;;
    gate_protected_app_py|protected_app_py)
      gate_protected_app_py
      ;;
    gate_protected_migrations|protected_migrations)
      gate_protected_migrations
      ;;
    gate_protected_frontend|protected_frontend)
      gate_protected_frontend
      ;;
    gate_secrets|secrets)
      gate_secrets
      ;;
    gate_whitespace|whitespace)
      gate_whitespace
      ;;
    gate_11_module|11_module)
      gate_11_module
      ;;
    gate_9_layers|9_layers)
      gate_9_layers
      ;;
    gate_autonomy_percent|autonomy_percent)
      gate_autonomy_percent
      ;;
    gate_adr_silent|adr_silent)
      gate_adr_silent
      ;;
    gate_required_docs|required_docs)
      gate_required_docs
      ;;
    gate_claude_hierarchy|claude_hierarchy)
      gate_claude_hierarchy
      ;;
    gate_script_mode_755|script_mode_755)
      gate_script_mode_755
      ;;
    gate_config_mode_644|config_mode_644)
      gate_config_mode_644
      ;;
    gate_hooks_suite|hooks_suite)
      gate_hooks_suite
      ;;
    report_final|report)
      report_final
      ;;
    *)
      echo "Uso: $0 [gate_branch|gate_protected_app_py|gate_secrets|...|report_final]"
      exit 1
      ;;
  esac
}

main "$@"
