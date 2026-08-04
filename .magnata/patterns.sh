#!/bin/bash
# Magnata OS — Padrões Canônicos de Governança
# Fonte única de verdade para validação de regras
# Importado por: .githooks/pre-commit, scripts/ci/validate_governance.sh

# ============================================================================
# BRANCHES AUTORIZADAS — Trabalho de desenvolvimento do Magnata OS
# ============================================================================
# Enumeração fechada para branches "feat/..." — toda branch feat/ nova
# precisa ser adicionada aqui explicitamente, um nome exato por vez. "main"
# não é branch de desenvolvimento local; eventos de CI sobre main
# (pull_request, push) já são tratados à parte, sem depender desta lista.
#
# Exceção restrita, registrada explicitamente (não em silêncio): branches
# "fix/..." usam um padrão único, não uma lista de nomes exatos, porque
# correções pontuais (como fix/remetente-dp-email-intake) são mais
# numerosas e de vida mais curta que as branches feat/ de módulo. O padrão
# abaixo é deliberadamente restrito — não é "^fix/.*$" — e não abre nenhum
# outro prefixo (feat/, chore/, docs/, test/ continuam exigindo entrada
# exata nesta lista, como antes).

AUTHORIZED_BRANCHES=(
  "^feat/magnata-os-claude-powerpack$"
  "^feat/magnata-os-etapa6-governanca$"
  "^feat/magnata-os-etapa6-estabilizacao$"
  "^fix/[a-z0-9][a-z0-9-]*$"
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
# PADRÕES DE SEGREDO — segredo real vs. identificador/header/placeholder
# ============================================================================
# A versão anterior (SECRET_PATTERNS, bare grep -qi por arquivo inteiro)
# bloqueava qualquer ocorrência do NOME de uma variável/header sensível
# (ex.: "apiKey", "'X-API-KEY'", "DATABASE_URL" como identificador), mesmo
# sem nenhum valor literal de segredo presente — falso positivo confirmado
# em apps_script_email_intake.gs (branch fix/remetente-dp-email-intake,
# 2026-08-03): a variável `apiKey` e o header `'X-API-KEY'` já existiam no
# código original, sem nenhuma credencial real.
#
# Duas camadas, ambas operando só sobre CONTEÚDO STAGED e só linhas
# ADICIONADAS (ver linha_contem_segredo_real, arquivo_staged_tem_segredo,
# usadas por .githooks/pre-commit e por scripts/ci/validate_governance.sh
# — mesma fonte, para hook local e CI nunca divergirem):
#
#   1. SECRET_PATTERNS_ABSOLUTOS — formato inequívoco (chave privada,
#      formato reconhecível de credencial de provedor, Bearer com valor,
#      URL com credencial embutida). Qualquer ocorrência já basta — não
#      precisa de contexto de atribuição, o formato em si é a prova.
#
#   2. SECRET_CONTEXT_KEYWORDS — nomes sensíveis (api_key, token,
#      password, secret, database_url, airtable_key etc. — inclui os
#      mesmos termos que já estavam no SECRET_PATTERNS anterior) só
#      bloqueiam quando atribuídos a um valor LITERAL (aspas ou token
#      solto até o fim da linha) que não é vazio nem um placeholder
#      conhecido (ver SECRET_PLACEHOLDER_REGEX). Nome de variável, header,
#      chamada a getenv/getProperty, ou referência a outra variável nunca
#      batem, porque o valor não é uma string literal.

SECRET_PATTERNS_ABSOLUTOS=(
  "BEGIN RSA PRIVATE KEY"
  "BEGIN PRIVATE KEY"
  "BEGIN OPENSSH PRIVATE KEY"
  "-----BEGIN"
  "AKIA[0-9A-Z]{16}"
  "gh[posur]_[A-Za-z0-9]{20,}"
  "Bearer[[:space:]]+[A-Za-z0-9._-]{8,}"
  "://[^/[:space:]:]+:[^/[:space:]@]+@"
)

SECRET_CONTEXT_KEYWORDS='private[_-]?key|api[_-]?key|secret[_-]?key|access[_-]?key|access[_-]?token|client[_-]?secret|password|passwd|token|secret|credentials|aws[_-]?secret|database[_-]?url|airtable[_-]?key|sendgrid[_-]?api|render[_-]?api|stripe[_-]?secret|jwt[_-]?secret|github[_-]?token'

# Placeholder/valor vazio — nunca é segredo real, mesmo em atribuição
# literal. Âncorado (^...$) contra o VALOR capturado inteiro, não contra um
# prefixo — cada alternativa casa o valor INTEIRO (exceto as com sufixo
# [a-z0-9_-]* explícito, únicas com continuação livre, por já terem um
# marcador de placeholder inequívoco no início). Nunca usar alternativa
# vazia solta aqui — "()*"-like construções combinadas com sufixo genérico
# greedy classificariam QUALQUER valor alfanumérico como placeholder
# (armadilha real encontrada e corrigida durante os testes desta correção).
SECRET_PLACEHOLDER_REGEX='^$|^(changeme|change_me|xxx+|placeholder|todo|fixme|exemplo|example|dummy|fake|test|sample)$|^(cole[_-]?aqui|your[_-][a-z_]*key)[a-z0-9_-]*$|^<[^>]*>$|^\*{3,}$|^\.{3,}$'

# Verifica se um VALOR já capturado (sem aspas) é placeholder/vazio.
# Retorno: 0 = é placeholder (seguro); 1 = não é (segue candidato a segredo).
_valor_e_placeholder() {
  local valor="$1"
  local nocase_ja_ligado=0
  shopt -q nocasematch && nocase_ja_ligado=1
  shopt -s nocasematch
  local resultado=1
  if [[ "$valor" =~ $SECRET_PLACEHOLDER_REGEX ]]; then
    resultado=0
  fi
  [ $nocase_ja_ligado -eq 0 ] && shopt -u nocasematch
  return $resultado
}

# Verifica se UMA linha de conteúdo (sem prefixo "+"/"-" de diff) contém um
# segredo real. Retorno: 0 = segredo real encontrado; 1 = linha limpa
# (identificador, header, placeholder, ou valor vazio).
linha_contem_segredo_real() {
  local linha="$1"
  local nocase_ja_ligado=0
  shopt -q nocasematch && nocase_ja_ligado=1
  shopt -s nocasematch

  local achou=1

  for pat in "${SECRET_PATTERNS_ABSOLUTOS[@]}"; do
    if [[ "$linha" =~ $pat ]]; then
      achou=0
      break
    fi
  done

  # Valor entre aspas: '"'"'chave'"'"' = '"'"'valor'"'"' ou "chave": "valor"
  if [ $achou -ne 0 ]; then
    local regex_aspas="['\"]?(${SECRET_CONTEXT_KEYWORDS})['\"]?[[:space:]]*[:=][[:space:]]*['\"]([^'\"]*)['\"]"
    if [[ "$linha" =~ $regex_aspas ]]; then
      if ! _valor_e_placeholder "${BASH_REMATCH[2]}"; then
        achou=0
      fi
    fi
  fi

  # Valor sem aspas até o fim da linha (estilo .env / shell): CHAVE=valor —
  # exige fim de linha logo após o token, para não capturar o início de uma
  # chamada de função/expressão (ex.: "apiKey = Foo.getBar().getX('K');"
  # não termina em token solto, continua com ".getBar()...").
  if [ $achou -ne 0 ]; then
    local regex_livre="['\"]?(${SECRET_CONTEXT_KEYWORDS})['\"]?[[:space:]]*[:=][[:space:]]*([A-Za-z0-9_+/=-]+)[[:space:]]*;?[[:space:]]*\$"
    if [[ "$linha" =~ $regex_livre ]]; then
      if ! _valor_e_placeholder "${BASH_REMATCH[2]}"; then
        achou=0
      fi
    fi
  fi

  return $achou
}

# Escaneia um arquivo staged por segredo real — só conteúdo do índice
# (git diff --cached), só linhas adicionadas. Imprime achados mascarados
# (arquivo, linha, categoria — nunca o valor) em stdout.
# Retorno: 0 = achou segredo; 1 = arquivo limpo.
arquivo_staged_tem_segredo() {
  local arquivo="$1"
  local encontrou=1
  local linha_num=0

  while IFS= read -r linha_diff; do
    if [[ "$linha_diff" =~ ^@@[[:space:]]-[0-9]+(,[0-9]+)?[[:space:]]\+([0-9]+) ]]; then
      linha_num="${BASH_REMATCH[2]}"
      continue
    fi
    if [[ "$linha_diff" == "+++"* ]]; then
      continue
    fi
    if [[ "$linha_diff" == "+"* ]]; then
      local conteudo="${linha_diff:1}"
      if linha_contem_segredo_real "$conteudo"; then
        echo "  Arquivo: $arquivo"
        echo "  Linha: $linha_num"
        echo "  Categoria: valor literal em campo sensível (ou formato de credencial reconhecível)"
        encontrou=0
      fi
      linha_num=$((linha_num + 1))
    fi
  done < <(git diff --cached --unified=0 -- "$arquivo" 2>/dev/null)

  return $encontrou
}

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

# Arquivos que definem ou testam os próprios padrões proibidos (segredo,
# 11º módulo, 9 camadas, autonomia %, ADR silenciosa) — não são violação
# real, são a fonte canônica de detecção (este arquivo) ou fixtures da
# suíte de testes do CI de governança. Movida para cá (antes vivia só
# dentro de .githooks/pre-commit) porque scripts/ci/validate_governance.sh
# também precisa dela — hook local e CI não podem divergir sobre o que é
# "fonte do próprio padrão" vs. violação real.
is_gate_pattern_source_file() {
  local file="$1"
  [[ "$file" == .githooks/* ]] || \
  [[ "$file" == ".magnata/patterns.sh" ]] || \
  [[ "$file" == "scripts/ci/test_governance.sh" ]] || \
  [[ "$file" == "scripts/ci/validate_governance.sh" ]]
}

# Verifica se um arquivo staged contém segredo real — alias mantido por
# compatibilidade de nome; delega inteiramente a arquivo_staged_tem_segredo
# (conteúdo do índice, só linhas adicionadas, valor literal não-placeholder).
# A versão anterior desta função escaneava o arquivo inteiro no working
# tree por bare match de identificador — substituída (ver cabeçalho da
# seção PADRÕES DE SEGREDO acima para o porquê).
has_secret_pattern() {
  local file="$1"
  arquivo_staged_tem_segredo "$file" > /dev/null
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
export PROTECTED_FILES SECRET_PATTERNS_ABSOLUTOS SECRET_CONTEXT_KEYWORDS SECRET_PLACEHOLDER_REGEX GATE_11_MODULE_PATTERNS
export GATE_9_LAYERS_PATTERNS GATE_AUTONOMY_PERCENT_PATTERNS GATE_ADR_SILENT_PATTERNS
export REQUIRED_DOCS CLAUDE_HIERARCHY EXECUTABLE_FILES NON_EXECUTABLE_FILES
export ALLOWED_PATHS SCRATCH_PATTERNS NORMATIVE_DOC_PATTERNS AUTHORIZED_BRANCHES
export MSG_APPROVED MSG_BLOCKED MSG_WARNING MSG_INFO MSG_ERROR
export EXIT_APPROVED EXIT_BLOCKED EXIT_WARNING EXIT_ERROR
export -f is_protected_file is_gate_pattern_source_file has_secret_pattern _valor_e_placeholder linha_contem_segredo_real arquivo_staged_tem_segredo get_file_mode is_normative_doc is_authorized_branch is_claude_hierarchy_path
