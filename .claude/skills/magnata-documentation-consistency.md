# Skill: magnata-documentation-consistency

**Versão:** 1.0
**Status:** Controlada
**Escopo:** Verificação de coerência entre documentos, código e decisões

---

## Objetivo

Verificar coerência entre documentação fundacional, código, testes e decisões registradas. Detectar contradições, termos divergentes e documentação desatualizada sem ocultar divergências.

---

## Responsabilidades

- Localizar contradições entre documentos
- Identificar termos divergentes
- Detectar documentos desatualizados
- Verificar links e referências
- Diferenciar documentação normativa de descritiva
- Identificar afirmações sem evidência
- Preservar decisões pendentes como pendentes
- Verificar alinhamento com os `CLAUDE.md`

---

## Operações permitidas

- Ler documentação
- Ler código (sem alterar)
- Comparar documentos
- Rastrear referências cruzadas
- Verificar links
- Localizar divergências terminológicas
- Consultar `CLAUDE.md` em cascata
- Registrar inconsistências

---

## Operações proibidas

- Alterar código
- Resolver ADR
- Ocultar divergências
- Normalizar terminologia silenciosamente
- Declarar o legado incompatível sem prova
- Editar documentação fundacional
- Marcar decisão `PENDENTE` como `APROVADA` sem autorização
- Remover conflito terminológico registrado

---

## Entrada esperada

1. Documentação a auditar (ou pergunta específica)
2. Código relacionado (se aplicável)
3. Contexto de mudança (se aplicável)

---

## Procedimento

1. **Identificar documentos relevantes:**
   - Documento sendo auditado
   - Documentos que o referem
   - Documentos que o próprio referencia
   - Código relacionado

2. **Comparar termos:**
   - Listar todos os nomes de entidades usados
   - Listar todos os nomes de estados usados
   - Listar todos os nomes de eventos usados
   - Verificar se dois termos representam o mesmo conceito
   - Verificar se um termo tem múltiplos significados

3. **Verificar links e referências:**
   - Localizar todas as citações de arquivo
   - Verificar se arquivos citados existem
   - Verificar se linha citada corresponde ao conteúdo
   - Identificar links quebrados

4. **Diferenciar normativo de descritivo:**
   - Normativo: "deve", "é obrigatório", "proibido"
   - Descritivo: "é", "contém", "registra"
   - Verificar se normativo está no `CLAUDE.md` ou ADR
   - Verificar se descritivo está testado no código

5. **Localizar afirmações sem evidência:**
   - Afirmação: "o módulo X é responsável por Y"
   - Evidência: código em `magnata_os/` ou contrato em `MAGNATA_OS_CONTRATOS.md`
   - Se sem evidência, apontar como "hipótese" não comprovada

6. **Preservar decisões pendentes:**
   - Listar todas as decisões marcadas `PENDENTE` em `MAGNATA_OS_DECISOES_ENTIDADES.md`
   - Verificar se alguma foi silenciosamente resolvida
   - Alertar se proposta trata `PENDENTE` como resolvido

7. **Consolidar parecer:**
   - Listar inconsistências por severidade
   - Apontar afirmações não comprovadas
   - Indicar necessidade de atualização documental
   - Registrar decisões pendentes relacionadas

---

## Saída mínima

```
PARECER DE CONSISTÊNCIA DOCUMENTAL
====================================
Documentação auditada: [lista]
Inconsistências encontradas: [número]
  - Severa: [lista com impacto direto em operação]
  - Média: [lista com impacto em clareza]
  - Baixa: [lista cosmética]

Termos divergentes:
  - [termo A] vs [termo B]: [descrição da divergência]

Afirmações sem evidência:
  - [afirmação]: [evidência necessária]

Decisões pendentes relacionadas:
  - [DEC-ENT-XXX]: [descrição]

Links verificados: [número OK / número quebrado]

Parecer: [CONSISTENTE | INCONSISTÊNCIAS MENORES | INCONSISTÊNCIAS MAIORES | PENDENTE RESOLUÇÃO]

[Detalhes adicionais se necessário]
```

---

## Condições de bloqueio

Esta skill **alerta** (não bloqueia, mas sinaliza necessidade de correção) se:

1. Contradição direta entre documentos normativo e código
2. Termo central tem múltiplos significados sem desambiguação
3. Referência a arquivo que não existe
4. ADR é citada mas decisão está `PENDENTE`
5. Código implementa algo descrito como "ainda não decidido"
6. Decisão `PENDENTE` é tratada como aprovada

---

## Conflito terminológico obrigatório

Quando encontrar:
- Documentação fundacional: "Item de Ingestão"
- Código implementado: "Documento"

Saída obrigatória:

```
CONFLITO TERMINOLÓGICO PENDENTE
================================
Termo A (canônico em documentação): Item de Ingestão
Termo B (implementado em código): Documento
Status: PENDENTE RESOLUÇÃO POR ADR

Não é permitido:
- Normalizar silenciosamente um dos dois
- Declarar equivalência definitiva
- Renomear entidade
- Tratar como erro simples de nomenclatura

Resposta: DECISÃO DEPENDENTE DE ADR APROVADA
```

---

## Obediência aos CLAUDE.md

Esta skill segue:
1. `CLAUDE.md` (raiz) — §2 (Fontes oficiais, Precedência)
2. `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA1.md` — §4 (Conflitos detectados)
3. Nenhum `CLAUDE.md` autoriza normalizar terminologia silenciosamente

---

## Não substitui

- `magnata-architecture-governance` (análise arquitetural)
- `magnata-legacy-guardian` (impacto no legado)
- `magnata-validation-gate` (consolidação final)
