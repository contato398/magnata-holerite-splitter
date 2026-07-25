# Skill: magnata-legacy-preservation

**Versão:** 1.0
**Status:** Controlada
**Escopo:** Proteção do código legado, migrations e contratos operacionais

---

## Objetivo

Proteger `app.py`, código legado, migrations aplicadas e contratos operacionais. Garantir que migração incremental (strangler pattern) nunca interrompe operação em produção.

---

## Responsabilidades

- Identificar impacto direto e indireto no legado
- Detectar alteração funcional disfarçada de documentação
- Verificar risco sobre rotas, contratos, banco e integrações
- Exigir estratégia incremental
- Exigir plano de rollback em futuras alterações
- Identificar acoplamentos com legado
- Bloquear mudança sem evidência e plano

---

## Operações permitidas

- Analisar diff
- Comparar código novo com legado
- Localizar chamadas cruzadas
- Verificar dependências
- Identificar testes relacionados
- Registrar impactos
- Ler código (sem alterar)

---

## Operações proibidas

- Modificar `app.py`
- Modificar migrations
- Modificar banco de dados
- Executar testes contra produção
- Acessar integrações reais
- Propor remoção imediata do legado
- Alterar contrato de dados do legado
- Corrigir "inconsistências" do legado sem ADR

---

## Entrada esperada

1. Alteração proposta ou código novo
2. Documentação de impacto (se disponível)
3. Teste de cobertura (se aplicável)
4. Plano de migração (se toca legado)

---

## Procedimento

1. **Identificar componentes legados potencialmente afetados:**
   - Verificar se alteração toca `app.py`
   - Verificar se altera contrato de dados do Airtable
   - Verificar se altera rota Flask
   - Verificar se altera chamada a serviço externo
   - Verificar se altera estado de um processo operacional

2. **Classificar tipo de impacto:**
   - Direto: alteração muda o próprio legado
   - Indireto: alteração é consomida pelo legado
   - Estrutural: alteração altera contrato que o legado depende
   - Nenhum: isolado do legado

3. **Avaliar risco:**
   - Risco baixo: alteração é aditiva, nunca remove
   - Risco médio: alteração altera estrutura não usada hoje
   - Risco alto: alteração altera o que está em uso
   - Risco crítico: alteração afeta processo em produção

4. **Verificar caminho de rollback:**
   - Como o legado continua funcionando se a mudança nova falhar?
   - Existe uma migration de reversão?
   - Existe um plano de ativação/desativação?
   - É possível executar em paralelo?

5. **Consolidar parecer:**
   - Listar componentes afetados
   - Classificar tipo de impacto
   - Avaliar risco
   - Exigir plano se necessário
   - Bloquear se risco é crítico e sem plano

---

## Saída mínima

```
PARECER DE PRESERVAÇÃO LEGADA
==============================
Alteração: [descrição breve]
Componentes legados afetados: [lista ou nenhum]
Tipo de impacto: [direto | indireto | estrutural | nenhum]
Risco: [baixo | médio | alto | crítico]
Plano de rollback: [sim/não]
Estratégia incremental: [sim/não]
Parecer: [LIBERADO | LIBERADO COM CONDIÇÃO | BLOQUEADO]

[Detalhes adicionais se necessário]
```

---

## Condições de bloqueio

Esta skill **bloqueia** se:

1. `app.py` será modificado (sempre exige autorização explícita separada)
2. Risco é crítico e não existe plano de rollback
3. Alteração remove funcionalidade do legado sem migração planejada
4. Alteração não pode ser desfeita
5. Teste não cobre caminho afetado do legado
6. Contrato de dados é alterado sem ADR

---

## Obediência aos CLAUDE.md

Esta skill segue:
1. `CLAUDE.md` (raiz) — §1 (Operação preservada), §7 (Arquivos protegidos)
2. `MAGNATA_OS_MANIFESTO.md` — Operação preservada, Migração incremental
3. Nenhum `CLAUDE.md` autoriza quebra de operação em produção

---

## Não substitui

- `magnata-repository-safety` (validação de segurança do repositório)
- `magnata-architecture-governance` (análise arquitetural)
- `magnata-validation-gate` (consolidação final)
