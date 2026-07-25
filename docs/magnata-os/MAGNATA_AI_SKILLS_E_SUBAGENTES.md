# Magnata AI — Skills e Subagentes Técnicos

**Versão:** 1.0
**Status:** Ativos e controlados
**Escopo:** Etapa 3 do Magnata AI Engineering Powerpack

---

## Objetivo desta camada

Estabelecer procedimentos reutilizáveis de engenharia e funções técnicas especializadas para garantir que:

- Leitura segura do repositório
- Governança arquitetural é aplicada
- Legado é preservado
- Análise documental é consistente
- Alterações são validadas
- Pareceres técnicos são controlados

Nenhuma skill ou subagente tem acesso autônomo a produção, executa tarefas contínuas ou modifica código funcional.

---

## Diferença: Skill vs. Subagente

| Aspecto | Skill | Subagente |
|---|---|---|
| **Tipo** | Procedimento/verificação reutilizável | Agente especializado que executa procedimento |
| **Reuso** | Pode ser consultada por múltiplos agentes | Executa por demanda, especializado em uma função |
| **Documentação** | Arquivo `.md` em `.claude/skills/` | Arquivo `.md` em `.claude/agents/` |
| **Autonomia** | Nenhuma (procedimento passivo) | Executa sob demanda, termina após parecer |
| **Exempl** | Verificar segurança (skill) | Revisor arquitetural (agente) |

---

## Skills (5 procedimentos)

Cada skill é um procedimento documentado que define:
- Responsabilidades
- Operações permitidas
- Operações proibidas
- Entrada esperada
- Saída mínima
- Condições de bloqueio

### Skill 1: magnata-repository-safety

**Localização:** `.claude/skills/magnata-repository-safety.md`

**Responsabilidade:** Verificar segurança do repositório antes de qualquer operação.

**Responsabilidades:**
- Confirmar branch
- Confirmar HEAD
- Verificar estado Git (merge, rebase em andamento)
- Bloquear alterações proibidas
- Impedir acesso não autorizado
- Emitir parecer `SEGURO | BLOQUEADO | DIVERGENTE`

**Nunca:** Alterar estado Git, mudar branch, acessar produção.

**Consulta:** Antes de tudo.

---

### Skill 2: magnata-architecture-governance

**Localização:** `.claude/skills/magnata-architecture-governance.md`

**Responsabilidade:** Aplicar a constituição arquitetural do Magnata OS.

**Responsabilidades:**
- Distinguir camadas de módulos
- Verificar aderência ao strangler pattern
- Identificar necessidade de ADR
- Preservar hierarquias paralelas (`frontend` / `magnata_os`)
- Impedir decisões silenciosas

**Nunca:** Aprovar ADR, implementar, renomear entidades.

**Consulta:** Quando proposta afeta arquitetura.

---

### Skill 3: magnata-legacy-preservation

**Localização:** `.claude/skills/magnata-legacy-preservation.md`

**Responsabilidade:** Proteger `app.py` e legado operacional.

**Responsabilidades:**
- Identificar impacto legado
- Detectar alteração funcional
- Exigir estratégia incremental
- Exigir plano de rollback
- Bloquear risco crítico

**Nunca:** Modificar legado, executar testes em produção, remover código.

**Consulta:** Quando alteração toca operação existente.

---

### Skill 4: magnata-documentation-consistency

**Localização:** `.claude/skills/magnata-documentation-consistency.md`

**Responsabilidade:** Verificar coerência documental.

**Responsabilidades:**
- Localizar contradições
- Identificar termos divergentes
- Detectar documentos desatualizados
- Verificar links e referências
- Preservar decisões pendentes

**Nunca:** Resolver ADR, normalizar termos, ocultar conflitos.

**Consulta:** Quando alteração toca documentação.

---

### Skill 5: magnata-validation-gate

**Localização:** `.claude/skills/magnata-validation-gate.md`

**Responsabilidade:** Consolidar validação final.

**Responsabilidades:**
- Executar validações Git
- Revisar escopo do diff
- Consolidar pareceres anteriores
- Emitir liberação ou bloqueio

**Nunca:** Criar commit, abrir PR, fazer merge, ignorar bloqueios.

**Consulta:** Antes de commit/PR/merge.

---

## Subagentes (5 agentes especializados)

Cada subagente é um agente técnico especializado que executa um procedimento documentado.

### Subagente 1: repository-cartographer

**Localização:** `.claude/agents/magnata-repository-cartographer.md`

**Missão:** Mapear repositório sem alterar arquivos.

**Responsabilidades:**
- Descobrir estrutura de diretórios
- Localizar componentes
- Identificar relações aparentes
- Buscar referências cruzadas
- Registrar evidências

**Nunca:** Interpretar arquitetura além das evidências, atribuir responsabilidade sem prova.

**Skills que usa:** `magnata-repository-safety`

**Skills que não substitui:** `architecture-reviewer`, `legacy-guardian`, `documentation-auditor`

---

### Subagente 2: architecture-reviewer

**Localização:** `.claude/agents/magnata-architecture-reviewer.md`

**Missão:** Revisar aderência à constituição arquitetural.

**Responsabilidades:**
- Avaliar camadas e módulos
- Avaliar fronteiras
- Identificar necessidade de ADR
- Detectar mistura entre estado atual e alvo
- Emitir parecer arquitetural

**Nunca:** Implementar, aprovar ADR, substituir legacy-guardian.

**Skills que usa:** `magnata-architecture-governance`

**Skills que não substitui:** `legacy-guardian`, `documentation-auditor`

---

### Subagente 3: legacy-guardian

**Localização:** `.claude/agents/magnata-legacy-guardian.md`

**Missão:** Defender legado operacional.

**Responsabilidades:**
- Analisar impacto em `app.py`
- Localizar acoplamentos
- Exigir rollback
- Bloquear mudanças arriscadas
- Emitir parecer de preservação

**Nunca:** Modificar legado, executar em produção, aprovar deploy.

**Skills que usa:** `magnata-legacy-preservation`

**Skills que não substitui:** `documentation-auditor`, `architecture-reviewer`

---

### Subagente 4: documentation-auditor

**Localização:** `.claude/agents/magnata-documentation-auditor.md`

**Missão:** Auditar consistência documental.

**Responsabilidades:**
- Comparar documentos
- Conferir referências
- Identificar contradições
- Apontar terminologia divergente
- Preservar decisões pendentes

**Nunca:** Decidir arquitetura, resolver ADR, normalizar termos.

**Skills que usa:** `magnata-documentation-consistency`

**Skills que não substitui:** `architecture-reviewer`, `legacy-guardian`

---

### Subagente 5: quality-gate-reviewer

**Localização:** `.claude/agents/magnata-quality-gate-reviewer.md`

**Missão:** Revisão final consolidada.

**Responsabilidades:**
- Executar validações Git
- Revisar diff
- Conferir pareceres anteriores (dos 4 agentes acima)
- Consolidar resultado
- Emitir liberação ou bloqueio final

**Nunca:** Substituir análises especializadas, ignorar bloqueios.

**Skills que usa:** `magnata-validation-gate`

**Skills que não substitui:** Nenhuma (é o último portão)

---

## Matriz de Responsabilidades

Ver arquivo dedicado: `.claude/MATRIX_DE_RESPONSABILIDADES.md`

A matriz define:
- Responsabilidade principal de cada skill/agente
- O que ela NÃO faz
- Dependências
- Regras de delegação
- Fluxos recomendados
- Situações especiais

---

## Hierarquia dos CLAUDE.md

Toda skill e todo subagente segue:

1. **CLAUDE.md (raiz)** — constituição global
   - §1 Missão
   - §3 Arquitetura
   - §4 Regras de domínio
   - §6 Segurança
   - §7 Arquivos protegidos
   - §8 Processo obrigatório
   - §9 Git e PR
   - §10 Critérios de conclusão

2. **frontend/CLAUDE.md** (se toca frontend)
   - Identidade visual
   - Contratos API
   - Acessibilidade

3. **magnata_os/CLAUDE.md** (se toca magnata_os)
   - Pureza de domínio
   - Adapters
   - Estados e eventos

4. **magnata_os/.../migrations/CLAUDE.md** (se toca migrations)
   - Append-only
   - Rollback explícito
   - Idempotência

**Regra:** Instrução mais específica prevalece sobre geral, mas **nunca pode contornar proibição global**.

---

## Limites de autonomia

As skills e subagentes desta etapa:

✓ **Podem:**
- Ler repositório
- Executar validações locais
- Registrar inconsistências
- Emitir pareceres
- Bloquear continuação
- Consultar documentação
- Comparar código e docs

✗ **Não podem:**
- Alterar código funcional
- Alterar `app.py`
- Modificar migrations
- Modificar banco de dados
- Acessar Airtable, Gmail, Render, PostgreSQL, S3, Evolution API
- Enviar e-mails ou mensagens reais
- Executar deploy
- Criar hooks
- Instalar MCPs
- Executar em background
- Conceder autonomia operacional

---

## Operações proibidas (globalmente)

Nenhuma skill, subagente ou código criado nesta etapa pode:

- Alterar `app.py`
- Alterar código funcional
- Refatorar código
- Mover código
- Renomear entidades
- Renomear classes
- Renomear tabelas
- Alterar migrations
- Criar migrations
- Alterar banco de dados
- Alterar rotas
- Alterar APIs
- Instalar MCPs
- Criar hooks
- Acessar navegador controlado
- Criar agentes contínuos
- Acessar produção
- Enviar mensagens reais
- Executar deploy
- Abrir PR
- Realizar merge
- Fazer push automático

---

## Resposta ao conflito terminológico

Quando encontrar "Item de Ingestão" (documentação) vs. "Documento" (código):

**Obrigatoriamente registrar:**
```
CONFLITO TERMINOLÓGICO PENDENTE
================================
Termo A (documentação fundacional): Item de Ingestão
Termo B (código implementado): Documento
Status: PENDENTE RESOLUÇÃO POR ADR

Não permitido:
- Normalizar silenciosamente
- Declarar equivalência definitiva
- Renomear entidade

Resposta: DECISÃO DEPENDENTE DE ADR APROVADA
```

---

## Fluxo de execução recomendado

Para uma alteração típica:

```
1. Usuário descreve tarefa
   ↓
2. repository-safety (skill) valida estado
   ↓
3. repository-cartographer (agente) [opcional]
   ↓ (mapeia arquivos afetados)
4. [especialista apropriado] (skill + agente)
   ↓ (em paralelo, se apropriado)
   - architecture-governance + architecture-reviewer
   - legacy-preservation + legacy-guardian
   - documentation-consistency + documentation-auditor
5. validation-gate (skill)
   ↓ (consolidação das 4 skills anteriores)
6. quality-gate-reviewer (agente)
   ↓ (consolidação de todos os agentes anteriores)
7. [LIBERADO ou BLOQUEADO]
   ↓
8. Se LIBERADO: criar commit único
```

---

## Itens deliberadamente adiados

Os seguintes itens NÃO estão nesta etapa:

- **MCPs:** Nenhum instalado
- **Hooks:** Nenhum criado
- **Navegador controlado:** Nenhuma automação
- **Agentes contínuos:** Nenhuma execução em background
- **Acesso autônomo a produção:** Nenhuma permissão
- **Execução programada:** Nenhuma agendamento
- **Autorreparo:** Nenhuma auto-correção
- **Deploy automático:** Nenhum deploy
- **Alterações autônomas de banco:** Nenhuma execução de SQL
- **Envio de mensagens reais:** Nenhum e-mail/WhatsApp real

Serão avaliados em etapas posteriores do Powerpack.

---

## Critérios de evolução futura

Skills e subagentes podem evoluir se:

1. Necessidade comprovada (não hipotética)
2. Escopo permanece claramente delimitado
3. Nenhuma proibição global é contornada
4. Hierarquia dos `CLAUDE.md` é preservada
5. Matriz de responsabilidades é atualizada
6. Conflitos terminológicos são registrados
7. ADR é criada se necessário

Evolução nunca será silenciosa — sempre registrada neste documento ou em ADR.

---

## Versionamento

Toda alteração em skills ou subagentes:
- Incrementa versão deste documento
- É registrada em changelog
- Requer revisão de todas as etapas anteriores

Não é permitido editar uma skill ou subagente já criada sem decisão explícita.

---

## Referências relacionadas

- `CLAUDE.md` (raiz) — constituição global
- `.claude/MATRIX_DE_RESPONSABILIDADES.md` — matriz detalhada
- `.claude/skills/` — arquivos de todas as 5 skills
- `.claude/agents/` — arquivos de todos os 5 subagentes
- `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA3.md` — relatório da etapa
