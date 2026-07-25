# Skill: magnata-repository-safety

**Versão:** 1.0
**Status:** Controlada
**Escopo:** Verificação de segurança do repositório

---

## Objetivo

Garantir que qualquer tarefa comece com verificação de segurança do repositório. Esta skill é um portão de entrada — nenhuma operação deve prosseguir sem sua aprovação explícita.

---

## Responsabilidades

- Confirmar branch atual
- Confirmar HEAD (commit atual)
- Verificar estado do Git (merge, rebase, cherry-pick em andamento)
- Identificar arquivos permitidos para alteração
- Identificar operações proibidas
- Bloquear alterações fora do escopo
- Impedir acesso não autorizado a serviços
- Impedir uso de credenciais
- Emitir parecer de segurança

---

## Operações permitidas

```bash
git branch --show-current
git log --oneline
git status --short
git rev-parse HEAD
git diff --name-only
git diff --stat
ls -la
find (leitura apenas)
grep (leitura apenas)
cat (leitura apenas)
```

---

## Operações proibidas

- Corrigir estado do Git
- Mudar de branch
- Executar reset, rebase, cherry-pick
- Executar pull
- Excluir arquivos
- Criar commit
- Acessar Airtable
- Acessar Gmail
- Acessar Render
- Acessar PostgreSQL
- Acessar S3, R2
- Acessar Evolution API
- Acessar WhatsApp
- Acessar Make.com
- Acessar serviços de assinatura
- Enviar mensagens ou e-mails
- Executar deploy

---

## Entrada esperada

- Nenhuma (executa automaticamente antes de qualquer tarefa)

---

## Procedimento

1. Confirmar branch atual (`git branch --show-current`)
2. Confirmar HEAD (`git rev-parse HEAD`)
3. Verificar se alguma operação Git está em andamento
4. Listar arquivos modificados/staged (`git status --short`, `git diff --name-only`)
5. Verificar presença de credenciais ou segredos no diff
6. Confirmar que nenhuma operação proibida foi tentada
7. Emitir parecer

---

## Saída mínima

```
PARECER DE SEGURANÇA
====================
Branch: [nome da branch]
HEAD: [hash do commit]
Estado Git: [limpo | merge em andamento | rebase em andamento | cherry-pick em andamento]
Arquivos alterados: [lista ou nenhum]
Segredos detectados: [sim/não]
Operações proibidas detectadas: [sim/não]
Parecer: [SEGURO | BLOQUEADO | DIVERGENTE]
```

---

## Condições de bloqueio

Esta skill **bloqueia** qualquer continuação se:

1. Branch não é `feat/magnata-os-claude-powerpack`
2. HEAD não é o esperado (ed1b76a ou posterior)
3. Arquivo modificado está em `app.py`
4. Arquivo modificado está em `magnata_os/documental/modulo01/dominio*.py` ou contrato
5. Arquivo modificado está em migrations
6. Arquivo modificado está em `frontend/assets/brand/`
7. Merge, rebase ou cherry-pick está em andamento
8. Segredo, token ou credencial é detectado no diff
9. Qualquer operação proibida foi tentada

---

## Parecer bloqueante

Se qualquer bloqueio é detectado, o parecer é:

```
PARECER: BLOQUEADO

Razão: [motivo específico]
Ação necessária: [instruções claras]

Esta skill não permite continuação até resolução.
```

---

## Obediência aos CLAUDE.md

Esta skill segue:
1. `CLAUDE.md` (raiz) — §6 (Segurança), §7 (Arquivos protegidos), §9 (Git e PR)
2. Nenhum `CLAUDE.md` local sobrescreve as proibições globais

---

## Iteração

A skill pode ser executada quantas vezes necessário dentro de uma mesma tarefa para revalidar o estado.

---

## Não substitui

- `magnata-legacy-preservation` (verificação específica de impacto legado)
- `magnata-architecture-governance` (análise de aderência arquitetural)
- `magnata-validation-gate` (consolidação de validação final)
