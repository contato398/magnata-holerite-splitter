#!/bin/bash
# Magnata OS — Padrões Canônicos de Governança
# Fonte única de verdade para validação de regras
# Importado por: .githooks/pre-commit, scripts/ci/validate_governance.sh

# ============================================================================
# BRANCHES AUTORIZADAS — Trabalho de desenvolvimento do Magnata OS
# ============================================================================
# Enumeração fechada, não regex genérica (ex. "feat/*") — toda branch de
# trabalho nova precisa ser adicionada aqui explicitamente. "main" não é
# branch de desenvolvimento local; eventos de CI sobre main (pull_request,
# push) já são tratados à parte, sem depender desta lista.

AUTHORIZED_BRANCHES=(
  "^feat/magnata-os-claude-powerpack$"
  "^feat/magnata-os-etapa6-governanca$"
  "^feat/magnata-os-etapa6-estabilizacao$"
)

# Verifica se uma branch está na lista de branches de trabalho autorizadas
is_authorized_branch() {
  local branch="$1"
  for pattern in "${AUTHORIZED_BRANCHES[@]}"; do
    if [[ "$branch" =~ $pattern ]]; then
      return 0
    fi
  done
  return 1
}

# ============================================================================
# ARQUIVOS PROTEGIDOS — Não podem ser alterados sem autorização explícita
# ============================================================================

PROTECTED_FILES=(
  "^app\.py$"
  "^magnata_os/documental/modulo01/migrations/"
  "^frontend/CLAUDE\.md$"
  "^frontend/assets/brand/"
)

# ============================================================================
# PADRÕES DE SEGREDO — Indicadores de chaves, tokens, credenciais
# ============================================================================

SECRET_PATTERNS=(
  "private[_-]?key"
  "BEGIN RSA PRIVATE KEY"
  "BEGIN PRIVATE KEY"
  "-----BEGIN"
  "api[_-]?key"
  "GITHUB[_-]?TOKEN"
  "github[_-]?token"
  "access[_-]?token"
  "secret[_-]?key"
  "bearer[[:space:]]"
  "password[[:space:]]*="
  "passwd[[:space:]]*="
  "credentials[[:space:]]*:"
  "aws[_-]?secret"
  "DATABASE[_-]?URL"
  "AIRTABLE[_-]?KEY"
  "SENDGRID[_-]?API"
  "RENDER[_-]?API"
  "stripe[_-]?secret"
  "jwt[_-]?secret"
)

# ============================================================================
# PADRÕES DOCUMENTAIS — Estruturas proibidas
# ============================================================================

# Gate 7: Segurança como 11º módulo funcional (proibido)
GATE_11_MODULE_PATTERNS=(
  "11º módulo"
  "módulo onze"
  "novo módulo.*Segurança"
  "módulo funcional.*adicional.*Segurança"
)

# Gate 8: Arquitetura de 9 camadas ou 6+3 (proibido)
GATE_9_LAYERS_PATTERNS=(
  "9 camadas"
  "nove camadas"
  "modelo 6\\+3"
  "seis.*mais.*três"
)

# Gate 9: Autonomia percentual abstrata (proibido)
GATE_AUTONOMY_PERCENT_PATTERNS=(
  "autonomia.*[0-9]+%"
  "[0-9]+%.*autônom"
  "nível de autonomia.*%"
)

# Gate 10: ADR silenciosa — renomeação sem referência (proibido)
GATE_ADR_SILENT_PATTERNS=(
  "Item de Ingestão.*renomeado.*Documento"
  "Documento substitui.*Item de Ingestão"
  "mudança de nomenclatura.*aprovada"
)

# ============================================================================
# DOCUMENTOS NORMATIVOS — Arquitetura-de-registro do Magnata OS
# ============================================================================
# Escopo EXCLUSIVO dos gates semânticos 7-10 (11º módulo, 9 camadas,
# autonomia %, ADR silenciosa). Enumeração fechada por caminho exato — não
# regex genérica — de propósito: documentação técnica de CI/hooks/testes
# (docs/magnata-os/MAGNATA_AI_*.md, .githooks/README.md) e relatórios de
# etapa (MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA*.md, pareceres, planos,
# validações) NÃO entram aqui — podem citar os padrões proibidos em prosa,
# ao descrever o próprio gate, sem que isso seja uma violação real.

NORMATIVE_DOC_PATTERNS=(
  "^MAGNATA_OS_MANIFESTO\.md$"
  "^MAGNATA_OS_ARQUITETURA\.md$"
  "^MAGNATA_OS_CONTRATOS\.md$"
  "^MAGNATA_OS_ESTADOS\.md$"
  "^MAGNATA_OS_EVENTOS\.md$"
  "^MAGNATA_OS_ENTIDADES\.md$"
  "^MAGNATA_OS_DECISOES_ENTIDADES\.md$"
  "^MAGNATA_OS_DOCUMENTAL_MODULO01\.md$"
  "^MAGNATA_OS_DOCUMENTAL_MODULO01_FASE2\.md$"
  "^MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3\.md$"
  "^MAGNATA_OS_DOCUMENTAL_MODULO01_FASE4\.md$"
  "^MAGNATA_OS_MODULO_01_INGESTAO\.md$"
  "^MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO\.md$"
  "^MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1\.md$"
  "^MAGNATA_OS_MODULO_01_FASE_0_OBSERVABILIDADE\.md$"
  "^docs/magnata-os/MAGNATA_OS_CAPACIDADES\.md$"
  "^docs/magnata-os/MAGNATA_OS_MODULOS\.md$"
  "^docs/magnata-os/MAGNATA_OS_ROADMAP\.md$"
  "^docs/magnata-os/MAGNATA_OS_MATRIZ_ARQUITETURAL\.md$"
  "^docs/magnata-os/MAGNATA_OS_ADR_001_NOMENCLATURA_ITEM_INGESTAO_VS_DOCUMENTO\.md$"
)

# ============================================================================
# DOCUMENTOS OBRIGATÓRIOS — Devem estar presentes
# ============================================================================

REQUIRED_DOCS=(
  "MAGNATA_OS_MANIFESTO.md"
  "MAGNATA_OS_CAPACIDADES.md"
  "MAGNATA_OS_MODULOS.md"
  "MAGNATA_OS_ROADMAP.md"
  "MAGNATA_OS_MATRIZ_ARQUITETURAL.md"
)

# ============================================================================
# CLAUDE.md OBRIGATÓRIOS — 4 níveis de hierarquia
# ============================================================================

CLAUDE_HIERARCHY=(
  "CLAUDE.md"
  "frontend/CLAUDE.md"
  "magnata_os/CLAUDE.md"
  "magnata_os/documental/modulo01/migrations/CLAUDE.md"
)

# Verifica se um caminho é EXATAMENTE um dos 4 arquivos da hierarquia
# CLAUDE.md — comparação de igualdade de string contra CLAUDE_HIERARCHY,
# nunca por padrão/regex. É a única exceção documental reconhecida por
# PROTECTED_FILES e ALLOWED_PATHS (Validação 6 do pre-commit): libera
# exclusivamente estes 4 caminhos exatos, nunca um diretório inteiro nem
# qualquer outro CLAUDE.md fora desta lista.
is_claude_hierarchy_path() {
  local file="$1"
  local path
  for path in "${CLAUDE_HIERARCHY[@]}"; do
    if [[ "$file" == "$path" ]]; then
      return 0
    fi
  done
  return 1
}

# ============================================================================
# MODOS GIT — Permissões obrigatórias
# ============================================================================

# Executáveis (100755)
EXECUTABLE_FILES=(
  ".githooks/pre-commit"
  ".githooks/post-commit"
  ".githooks/pre-push"
  ".githooks/commit-msg"
  ".githooks/test-hooks.sh"
  "scripts/ci/validate_governance.sh"
  "scripts/ci/test_governance.sh"
)

# Não-executáveis (100644)
NON_EXECUTABLE_FILES=(
  ".github/workflows/magnata-governance.yml"
  ".magnata/patterns.sh"
  "MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md"
  "docs/magnata-os/MAGNATA_AI_CI_GOVERNANCA.md"
)

# ============================================================================
# CAMINHOS PERMITIDOS — Escopo do CI
# ============================================================================

ALLOWED_PATHS=(
  "^\.github/workflows/"
  "^\.magnata/"
  "^\.githooks/"
  "^scripts/ci/"
  "^docs/magnata-os/"
  "^MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA[0-9]+.*\.md$"
  "^MAGNATA_OS_.*\.md$"
  "^\.github/README\.md$"
  "^\.githooks/README\.md$"
)

# ============================================================================
# PADRÕES DE SCRATCH — Arquivos temporários proibidos em commit
# ============================================================================

SCRATCH_PATTERNS=(
  "^_"
  "^test_"
  "\.tmp$"
  "\.bak$"
  "\.swp$"
  "\.swo$"
)

# ============================================================================
# MENSAGENS E CÓDIGOS DE SAÍDA
# ============================================================================

MSG_APPROVED="✓ APROVADO"
MSG_BLOCKED="✗ BLOQUEADO"
MSG_WARNING="⚠ AVISO"
MSG_INFO="ℹ INFORMAÇÃO"
MSG_ERROR="✘ ERRO INTERNO"

EXIT_APPROVED=0
EXIT_BLOCKED=1
EXIT_WARNING=0      # Avisos não bloqueiam
EXIT_ERROR=1        # Erro interno sempre bloqueia

# ============================================================================
# FUNÇÕES ÚTEIS
# ============================================================================

# Verifica se arquivo é protegido
is_protected_file() {
  local file="$1"
  for pattern in "${PROTECTED_FILES[@]}"; do
    if [[ "$file" =~ $pattern ]]; then
      return 0  # É protegido
    fi
  done
  return 1  # Não é protegido
}

# Verifica se arquivo contém segredo
has_secret_pattern() {
  local file="$1"
  for pattern in "${SECRET_PATTERNS[@]}"; do
    if grep -qi "$pattern" "$file" 2>/dev/null; then
      return 0  # Contém segredo
    fi
  done
  return 1  # Sem segredo
}

# Verifica modo Git de arquivo
get_file_mode() {
  local file="$1"
  git ls-files --stage "$file" | awk '{print $1}' | sed 's/^0//'
}

# Verifica se arquivo é documento normativo (escopo dos gates semânticos 7-10)
is_normative_doc() {
  local file="$1"
  for pattern in "${NORMATIVE_DOC_PATTERNS[@]}"; do
    if [[ "$file" =~ $pattern ]]; then
      return 0  # É normativo
    fi
  done
  return 1  # Não é normativo (técnico, relatório, ou outro)
}

# Exporta funções e variáveis
export PROTECTED_FILES SECRET_PATTERNS GATE_11_MODULE_PATTERNS
export GATE_9_LAYERS_PATTERNS GATE_AUTONOMY_PERCENT_PATTERNS GATE_ADR_SILENT_PATTERNS
export REQUIRED_DOCS CLAUDE_HIERARCHY EXECUTABLE_FILES NON_EXECUTABLE_FILES
export ALLOWED_PATHS SCRATCH_PATTERNS NORMATIVE_DOC_PATTERNS AUTHORIZED_BRANCHES
export MSG_APPROVED MSG_BLOCKED MSG_WARNING MSG_INFO MSG_ERROR
export EXIT_APPROVED EXIT_BLOCKED EXIT_WARNING EXIT_ERROR
export -f is_protected_file has_secret_pattern get_file_mode is_normative_doc is_authorized_branch is_claude_hierarchy_path
