# Skill: magnata-validation-gate

**Versão:** 1.0
**Status:** Controlada
**Escopo:** Validação final consolidada de uma etapa

---

## Objetivo

Executar a validação final consolidada de uma etapa antes de commit, PR, merge ou deploy. Revisar escopo do diff, executar validações Git, consolidar pareceres dos revisores especializados e bloquear avanço se existir falha.

---

## Responsabilidades

- Revisar escopo do diff
- Executar validações Git
- Verificar ausência de arquivos proibidos
- Verificar ausência de código funcional alterado
- Detectar credenciais
- Confirmar ausência de acesso real
- Consolidar pareceres dos revisores
- Emitir liberação ou bloqueio final

---

## Operações permitidas

- Executar validações Git (`git diff --check`, `git status`, etc.)
- Analisar diff
- Verificar presença de credenciais
- Ler código (sem alterar)
- Ler documentação (sem alterar)
- Revisar pareceres anteriores
- Consolidar resultado

---

## Operações proibidas

- Corrigir automaticamente código
- Criar commit sem autorização expressa
- Abrir PR
- Fazer merge
- Fazer deploy
- Ignorar parecer bloqueante
- Autorizar continuação sem passar por todas as validações

---

## Entrada esperada

1. Diff completo da etapa
2. Pareceres anteriores (de outras skills se aplicável)
3. Contexto da etapa
4. Lista de arquivos esperados no diff

---

## Procedimento

1. **Executar validações Git:**
   ```bash
   git diff --check        # whitespace issues
   git diff --stat         # resumo das mudanças
   git diff --name-only    # lista de arquivos
   git status --short      # estado do repositório
   ```

2. **Verificar escopo do diff:**
   - `app.py` não deve aparecer
   - Nenhum arquivo funcional deve aparecer
   - Nenhuma migration deve aparecer
   - Nenhum arquivo de configuração de produção deve aparecer
   - Arquivos esperados devem estar presentes
   - Nenhum arquivo não esperado deve estar presente

3. **Verificar infraestrutura:**
   - Nenhum MCP foi instalado ou configurado
   - Nenhum hook foi criado
   - Nenhuma credencial foi incluída
   - Nenhum token foi exposto
   - Nenhum endpoint real foi chamado
   - Nenhum serviço real foi acessado

4. **Revisar pareceres anteriores:**
   - Se `magnata-repository-safety` foi executado: verificar se resultado é `SEGURO`
   - Se `magnata-architecture-governance` foi executado: verificar se não há `BLOQUEADO`
   - Se `magnata-legacy-preservation` foi executado: verificar se não há `BLOQUEADO`
   - Se `magnata-documentation-consistency` foi executado: registrar inconsistências
   - Se qualquer parecer é `BLOQUEADO`, esta skill deve bloquear também

5. **Consolidar resultado:**
   - Listar todas as validações executadas
   - Listar resultado de cada uma
   - Indicar bloqueios se existirem
   - Emitir parecer final

6. **Confirmar operações não executadas:**
   - Nenhuma branch foi trocada
   - Nenhuma alteração foi feita em branch paralela (fase-5)
   - Nenhuma PR foi aberta
   - Nenhum deploy foi realizado
   - Nenhum agente contínuo foi executado
   - As skills possuem escopo delimitado
   - Os subagentes possuem escopo delimitado

---

## Saída mínima

```
VALIDAÇÃO FINAL
================
Validações Git:
  git diff --check: [OK / FALHA]
  git diff --stat: [resumo]
  Arquivos alterados: [lista]

Verificação de escopo:
  app.py presente: [não]
  Código funcional: [não]
  Migrations: [não]
  Segredos: [não]
  Credenciais: [não]
  Acesso real: [não]

Pareceres anteriores:
  [skill 1]: [parecer]
  [skill 2]: [parecer]
  [skill 3]: [parecer]
  [skill 4]: [parecer]

Bloqueios: [nenhum | lista]

PARECER FINAL: [LIBERADO | BLOQUEADO]

Descrição: [motivo de bloqueio, se aplicável]
```

---

## Condições de bloqueio

Esta skill **bloqueia** se:

1. `git diff --check` retorna erros
2. `app.py` está no diff
3. Arquivo funcional está no diff
4. Credencial ou token está no diff
5. Qualquer parecer anterior é `BLOQUEADO`
6. Arquivo não esperado está presente
7. Arquivo esperado está faltando
8. Branch foi trocada
9. PR foi aberta
10. Deploy foi realizado

---

## Parecer bloqueante permanente

Se algum bloqueio é detectado:

```
PARECER FINAL: BLOQUEADO

Razão: [motivo específico]

Esta validação não permite avanço até resolução.
Não é possível criar commit, abrir PR, fazer merge ou deploy.

Ações necessárias:
1. [correção 1]
2. [correção 2]
3. Re-executar validação

Contato: [responsável pela etapa]
```

---

## Obediência aos CLAUDE.md

Esta skill segue:
1. `CLAUDE.md` (raiz) — §8 (Processo obrigatório), §9 (Git e PR), §10 (Critérios de conclusão)
2. Não autoriza bypass das validações

---

## Não substitui

- `magnata-repository-safety` (verificação de segurança)
- `magnata-architecture-governance` (análise arquitetural)
- `magnata-legacy-preservation` (proteção legada)
- `magnata-documentation-consistency` (consistência documental)

Todos esses pareceres são **prerequisitos** para liberação desta skill.
