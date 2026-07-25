# Skill: magnata-architecture-governance

**Versão:** 1.0
**Status:** Controlada
**Escopo:** Aplicação da constituição arquitetural do Magnata OS

---

## Objetivo

Aplicar a constituição arquitetural do Magnata OS a propostas, documentos, decisões e alterações. Garantir que nenhuma decisão arquitetural seja tomada em silêncio.

---

## Responsabilidades

- Distinguir camadas arquiteturais de módulos funcionais
- Distinguir estado atual de arquitetura-alvo
- Distinguir fato, hipótese e decisão pendente
- Verificar aderência ao strangler pattern
- Identificar necessidade de ADR (Architecture Decision Record)
- Preservar hierarquias paralelas (`frontend` e `magnata_os`)
- Impedir decisões silenciosas
- Avaliar fronteiras entre módulos
- Verificar conformidade com contratos oficiais

---

## Operações permitidas

- Ler documentação arquitetural
- Comparar código com documentação
- Identificar divergências entre planejamento e implementação
- Registrar necessidade de ADR
- Apontar conflitos terminológicos
- Verificar conformidade com `MAGNATA_OS_MANIFESTO.md`
- Ler código (sem alterar)

---

## Operações proibidas

- Aprovar ADR
- Alterar nomenclatura
- Implementar arquitetura
- Declarar componente como concluído sem evidência
- Conceder autonomia operacional a produção
- Renomear entidades
- Renomear módulos
- Decidir arquitetura unilateralmente
- Presumir arquitetura a partir de nomes de diretórios

---

## Entrada esperada

1. Proposta de alteração ou novo módulo
2. Documentação arquitetural relevante
3. Código relacionado (se aplicável)
4. Contexto de negócio (se disponível)

---

## Procedimento

1. **Mapear camadas vs. módulos:**
   - Camadas: Entrada, Inteligência, Transformação, Negócio, Entrega, Auditoria
   - Módulos: Ingestão, Classificação, Cadastro, RH, Ponto, Documentos, Distribuição, Assinatura, Auditoria, Plataforma
   - Confirmar que não há confusão entre as dimensões

2. **Conferir estado atual vs. alvo:**
   - Consultar `MAGNATA_OS_ARQUITETURA.md` §0 (linha de base)
   - Consultar plano de migração (strangler pattern)
   - Identificar se a proposta respeita migração incremental

3. **Validar fatos, hipóteses e decisões:**
   - Fatos: implementação já mesclada em `main`
   - Hipóteses: propostas não validadas
   - Decisões pendentes: apontadas em `MAGNATA_OS_DECISOES_ENTIDADES.md` como `PENDENTE`
   - Nunca tratar hipótese como fato

4. **Avaliar necessidade de ADR:**
   - Se a proposta altera arquitetura de um módulo, ADR é necessária
   - Se toca fronteira entre módulos, ADR é necessária
   - Se muda contrato de dados, ADR é necessária
   - Se afeta migração incremental, ADR é necessária

5. **Preservar conflito terminológico:**
   - Documentação fundacional: "Item de Ingestão"
   - Código implementado: "Documento"
   - Resposta obrigatória: `DECISÃO DEPENDENTE DE ADR APROVADA`
   - Nunca resolver silenciosamente

6. **Consolidar parecer:**
   - Listar aderências
   - Listar violações
   - Apontar decisões pendentes
   - Indicar necessidade de ADR

---

## Saída mínima

```
PARECER ARQUITETURAL
=====================
Proposta: [descrição breve]
Camadas afetadas: [lista ou nenhuma]
Módulos afetados: [lista ou nenhuma]
Aderências: [lista de requisitos cumpridos]
Violações: [lista de requisitos violados]
Decisões pendentes: [lista ou nenhuma]
ADR necessária: [sim/não | se sim, motivo]
Parecer: [APROVADO | APROVADO COM RESSALVA | BLOQUEADO | PENDENTE]

[Detalhes adicionais, se necessário]
```

---

## Condições de bloqueio

Esta skill **bloqueia** se:

1. Proposta altera nomenclatura sem ADR
2. Proposta mistura camadas e módulos
3. Proposta cria dois módulos com responsabilidade sobreposta
4. Proposta quebra strangler pattern
5. Proposta viola contratos de dados sem justificativa
6. Proposta trata "Item de Ingestão" e "Documento" como sinônimos resolvidos
7. Proposta implementa arquitetura sem documentação

---

## Obediência aos CLAUDE.md

Esta skill segue:
1. `CLAUDE.md` (raiz) — §3 (Arquitetura), §4 (Regras de domínio)
2. `magnata_os/CLAUDE.md` — estados e eventos
3. Nenhum `CLAUDE.md` local autoriza decisão arquitetural silenciosa

---

## Não substitui

- `magnata-legacy-guardian` (impacto no legado)
- `magnata-documentation-auditor` (consistência documental)
- `magnata-validation-gate` (consolidação final)
