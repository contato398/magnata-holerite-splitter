#!/bin/bash
# Script de testes para hooks do Magnata OS — Etapa 5
# Executa testes locais em repositório temporário

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "================================"
echo "HOOKS TEST SUITE — Etapa 5"
echo "================================"
echo ""

# Fonte versionada dos hooks e dos padrões canônicos, capturada ANTES de
# entrar no repositório temporário. Não depende de .git/hooks/ já estar
# instalado no ambiente chamador (install-hooks.sh não roda automaticamente
# num runner de CI) — torna a suíte autossuficiente em qualquer máquina.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Criar repositório temporário para testes
TEMP_REPO=$(mktemp -d)
trap "rm -rf $TEMP_REPO" EXIT

echo "Testando em: $TEMP_REPO"
cd "$TEMP_REPO"
git init > /dev/null 2>&1
git config user.email "test@magnata.local" > /dev/null 2>&1
git config user.name "Test Bot" > /dev/null 2>&1

# Copiar hooks da fonte versionada (.githooks/), não de .git/hooks/ do
# ambiente chamador. Copiar também .magnata/patterns.sh, que o pre-commit
# importa (VALIDAÇÃO 6) — sem ele o hook falha ao sourcing, não ao validar.
mkdir -p "$TEMP_REPO/.git/hooks" "$TEMP_REPO/.magnata" "$TEMP_REPO/docs/magnata-os"
cp "$SCRIPT_DIR/pre-commit" "$SCRIPT_DIR/commit-msg" "$SCRIPT_DIR/pre-push" "$SCRIPT_DIR/post-commit" "$TEMP_REPO/.git/hooks/" 2>/dev/null
chmod +x "$TEMP_REPO/.git/hooks/"*
cp "$PROJECT_ROOT/.magnata/patterns.sh" "$TEMP_REPO/.magnata/patterns.sh"

# Arquivos de teste ficam sob docs/magnata-os/ — caminho já permitido em
# ALLOWED_PATHS (patterns.sh), para não serem bloqueados pela VALIDAÇÃO 6
# (escopo) por motivo alheio ao que cada teste realmente verifica.

# Commit inicial (--no-verify, sem hook) antes de criar a branch de teste —
# numa branch sem nenhum commit ainda ("unborn branch"), "git rev-parse
# --abbrev-ref HEAD" não resolve o nome real da branch neste ambiente, o
# que faria o VALIDAÇÃO 1 do hook bloquear por motivo alheio ao teste. Não
# ocorre em uso real: um repositório de trabalho sempre já tem histórico.
git commit --allow-empty -q -m "chore: initial" --no-verify > /dev/null 2>&1

TEST_PASS=0
TEST_FAIL=0

echo "[TESTE 1] Branch correta"
git checkout -b feat/magnata-os-claude-powerpack > /dev/null 2>&1
echo "test" > docs/magnata-os/test.txt
git add docs/magnata-os/test.txt
if git commit -m "test: initial commit" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ PASSOU${NC}"
  TEST_PASS=$((TEST_PASS + 1))
else
  echo -e "${RED}✗ FALHOU${NC}"
  TEST_FAIL=$((TEST_FAIL + 1))
fi

echo "[TESTE 2] Branch incorreta (bloqueio esperado)"
git checkout -b main > /dev/null 2>&1
git checkout -b wrong-branch > /dev/null 2>&1
echo "test2" > docs/magnata-os/test2.txt
git add docs/magnata-os/test2.txt
if ! git commit -m "test: wrong branch" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ PASSOU (bloqueio funcionou)${NC}"
  TEST_PASS=$((TEST_PASS + 1))
else
  echo -e "${RED}✗ FALHOU (deveria ter bloqueado)${NC}"
  TEST_FAIL=$((TEST_FAIL + 1))
fi

echo "[TESTE 3] Mensagem de commit válida"
git checkout feat/magnata-os-claude-powerpack > /dev/null 2>&1
echo "test3" > docs/magnata-os/test3.txt
git add docs/magnata-os/test3.txt
if git commit -m "docs: adiciona documentação" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ PASSOU${NC}"
  TEST_PASS=$((TEST_PASS + 1))
else
  echo -e "${RED}✗ FALHOU${NC}"
  TEST_FAIL=$((TEST_FAIL + 1))
fi

echo "[TESTE 4] Mensagem de commit vaga (bloqueio esperado)"
echo "test4" > docs/magnata-os/test4.txt
git add docs/magnata-os/test4.txt
if ! git commit -m "update something" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ PASSOU (bloqueio funcionou)${NC}"
  TEST_PASS=$((TEST_PASS + 1))
else
  echo -e "${RED}✗ FALHOU (deveria ter bloqueado)${NC}"
  TEST_FAIL=$((TEST_FAIL + 1))
fi

echo "[TESTE 5] Sem segredos"
echo "conteúdo normal" > docs/magnata-os/normal.txt
git add docs/magnata-os/normal.txt
if git commit -m "docs: arquivo sem segredos" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ PASSOU${NC}"
  TEST_PASS=$((TEST_PASS + 1))
else
  echo -e "${RED}✗ FALHOU${NC}"
  TEST_FAIL=$((TEST_FAIL + 1))
fi

echo "[TESTE 6] Detecção de secreto (bloqueio esperado)"
echo "aws_access_key_id = AKIAIOSFODNN7EXAMPLE" > docs/magnata-os/secret.txt
git add docs/magnata-os/secret.txt
if ! git commit -m "test: fake secret" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ PASSOU (bloqueio funcionou)${NC}"
  TEST_PASS=$((TEST_PASS + 1))
  git reset docs/magnata-os/secret.txt > /dev/null 2>&1
  rm docs/magnata-os/secret.txt
else
  echo -e "${RED}✗ FALHOU (deveria ter bloqueado)${NC}"
  TEST_FAIL=$((TEST_FAIL + 1))
fi

echo ""
echo "================================"
echo "RESUMO DOS TESTES"
echo "================================"
echo -e "Testes passaram: ${GREEN}$TEST_PASS${NC}"
echo -e "Testes falharam: ${RED}$TEST_FAIL${NC}"
echo ""

if [ $TEST_FAIL -eq 0 ]; then
  echo -e "${GREEN}✓ TODOS OS TESTES APROVADOS${NC}"
  exit 0
else
  echo -e "${RED}✗ ALGUNS TESTES FALHARAM${NC}"
  exit 1
fi
