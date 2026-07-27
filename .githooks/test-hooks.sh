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

# Criar repositório temporário para testes
TEMP_REPO=$(mktemp -d)
trap "rm -rf $TEMP_REPO" EXIT

echo "Testando em: $TEMP_REPO"
cd "$TEMP_REPO"
git init > /dev/null 2>&1
git config user.email "test@magnata.local" > /dev/null 2>&1
git config user.name "Test Bot" > /dev/null 2>&1

# Copiar hooks para repo temporário
cp -r "$(git rev-parse --git-dir)/hooks" "$TEMP_REPO/.git/" > /dev/null 2>&1

TEST_PASS=0
TEST_FAIL=0

echo "[TESTE 1] Branch correta"
git checkout -b feat/magnata-os-claude-powerpack > /dev/null 2>&1
echo "test" > test.txt
git add test.txt
if git commit -m "test: initial commit" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ PASSOU${NC}"
  ((TEST_PASS++))
else
  echo -e "${RED}✗ FALHOU${NC}"
  ((TEST_FAIL++))
fi

echo "[TESTE 2] Branch incorreta (bloqueio esperado)"
git checkout -b main > /dev/null 2>&1
git checkout -b wrong-branch > /dev/null 2>&1
echo "test2" > test2.txt
git add test2.txt
if ! git commit -m "test: wrong branch" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ PASSOU (bloqueio funcionou)${NC}"
  ((TEST_PASS++))
else
  echo -e "${RED}✗ FALHOU (deveria ter bloqueado)${NC}"
  ((TEST_FAIL++))
fi

echo "[TESTE 3] Mensagem de commit válida"
git checkout feat/magnata-os-claude-powerpack > /dev/null 2>&1
echo "test3" > test3.txt
git add test3.txt
if git commit -m "docs: adiciona documentação" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ PASSOU${NC}"
  ((TEST_PASS++))
else
  echo -e "${RED}✗ FALHOU${NC}"
  ((TEST_FAIL++))
fi

echo "[TESTE 4] Mensagem de commit vaga (bloqueio esperado)"
echo "test4" > test4.txt
git add test4.txt
if ! git commit -m "update something" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ PASSOU (bloqueio funcionou)${NC}"
  ((TEST_PASS++))
else
  echo -e "${RED}✗ FALHOU (deveria ter bloqueado)${NC}"
  ((TEST_FAIL++))
fi

echo "[TESTE 5] Sem segredos"
echo "conteúdo normal" > normal.txt
git add normal.txt
if git commit -m "docs: arquivo sem segredos" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ PASSOU${NC}"
  ((TEST_PASS++))
else
  echo -e "${RED}✗ FALHOU${NC}"
  ((TEST_FAIL++))
fi

echo "[TESTE 6] Detecção de secreto (bloqueio esperado)"
echo "aws_access_key_id = AKIAIOSFODNN7EXAMPLE" > secret.txt
git add secret.txt
if ! git commit -m "test: fake secret" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ PASSOU (bloqueio funcionou)${NC}"
  ((TEST_PASS++))
  git reset secret.txt > /dev/null 2>&1
  rm secret.txt
else
  echo -e "${RED}✗ FALHOU (deveria ter bloqueado)${NC}"
  ((TEST_FAIL++))
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
