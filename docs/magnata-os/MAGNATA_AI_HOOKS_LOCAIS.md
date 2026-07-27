# Magnata OS — Hooks Locais de Segurança

**Versão:** 1.0
**Etapa:** 5 — Barreiras Locais
**Data:** 2026-07-26
**Status:** Implementado

---

## 1. Objetivo dos Hooks

Implementar barreiras locais, determinísticas e reversíveis para:

- Validar conformidade com regras de governança
- Proteger arquivos sensíveis
- Detectar segredos acidentais
- Validar mensagens de commit
- Impedir operações perigosas
- Forçar revisão humana antes de push

**Importante:** Hooks são **local-only**. Não substituem controles de servidor.

---

## 2. Estrutura Adotada

**Diretório:** `.git/hooks/`
**Formato:** Shell scripts (POSIX bash)
**Compatibilidade:** Git nativo (sem dependências)
**Reversibilidade:** Arquivos removíveis; sem alterações irreversíveis

### Justificativa

- Git nativo = sem dependências especiais
- Shell scripts = determinísticos, sem magic strings
- `.git/hooks/` = local ao repositório, versionável
- Executáveis em CI/CD, desktop, WSL/MSYS

---

## 3. Catálogo de Hooks

### 3.1 `pre-commit`

**Evento:** Antes de cada commit
**Função:** Validações de segurança, escopo e conformidade
**Bloqueios:** Branch, proteção de arquivos, segredos, whitespace, escopo, scratch

### 3.2 `commit-msg`

**Evento:** Após digitação da mensagem, antes do commit
**Função:** Validar qualidade e formato da mensagem
**Regras:** Prefixo válido, descrição, sem vagueza

### 3.3 `pre-push`

**Evento:** Antes de `git push`
**Função:** Bloqueio absoluto de push automático
**Regra:** Bloqueia TODOS os pushes na Etapa 5

### 3.4 `post-commit` (informativo)

**Evento:** Após commit bem-sucedido
**Função:** Informação visual

---

## 4. Limitações Técnicas

Os hooks:

- Validam localmente
- Bloqueiam operações inseguras
- Informam violações
- Não fazem correções automáticas
- Não acessam produção
- Não executam de forma contínua

---

## 5. Procedimento de Desativação

### Remover um hook

```bash
rm .git/hooks/pre-commit
```

### Desativar temporariamente

```bash
git commit --no-verify -m "mensagem"
```

---

## 6. Referências

- [Git Hooks Documentation](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks)
- `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA5.md` — Relatório completo
- `.git/hooks/pre-commit`, `.git/hooks/commit-msg`, `.git/hooks/pre-push`

---

**Documento de governança local para Magnata OS — Etapa 5**