# Matriz de Responsabilidades — Skills e Subagentes

**Versão:** 1.0
**Propósito:** Definir responsabilidade principal de cada função técnica e o que ela NÃO faz.

---

## Tabela principal

| Função | Responsabilidade principal | Não substitui | Depende de | Precede |
|---|---|---|---|---|
| **magnata-repository-safety** (Skill) | Verificar segurança do repositório, bloquear alterações proibidas | `architecture-governance`, `legacy-preservation` | Nenhuma | Todas as outras |
| **magnata-architecture-governance** (Skill) | Aplicar constituição arquitetural, exigir ADR | `legacy-preservation`, `documentation-consistency` | `repository-safety` | `architecture-reviewer`, `quality-gate` |
| **magnata-legacy-preservation** (Skill) | Proteger `app.py` e legado, impedir quebra de operação | `documentation-consistency`, `architecture-governance` | `repository-safety` | `legacy-guardian`, `quality-gate` |
| **magnata-documentation-consistency** (Skill) | Verificar coerência entre documentos e código | `architecture-governance`, `legacy-preservation` | `repository-safety` | `documentation-auditor`, `quality-gate` |
| **magnata-validation-gate** (Skill) | Consolidar validação final, emitir liberação ou bloqueio | Análises especializadas | Todas as 4 skills acima | Commit/PR/deploy |
| **repository-cartographer** (Agente) | Descobrir e registrar estrutura, relações | `architecture-reviewer`, `legacy-guardian`, `documentation-auditor` | `repository-safety` | Qualquer revisão especializada |
| **architecture-reviewer** (Agente) | Revisar aderência arquitetural | `legacy-guardian`, `documentation-auditor` | `repository-safety`, `architecture-governance` | `quality-gate-reviewer` |
| **legacy-guardian** (Agente) | Defender legado, exigir rollback | `documentation-auditor`, `architecture-reviewer` | `repository-safety`, `legacy-preservation` | `quality-gate-reviewer` |
| **documentation-auditor** (Agente) | Auditar consistência documental | `architecture-reviewer`, `legacy-guardian` | `repository-safety`, `documentation-consistency` | `quality-gate-reviewer` |
| **quality-gate-reviewer** (Agente) | Consolidar todos os pareceres, emitir liberação final | Nenhuma (é o último portão) | Todos os 4 agentes acima + 5 skills | Commit |

---

## Regras de delegação

1. **Um subagente não repete integralmente o trabalho de outro:**
   - `repository-cartographer` descobre; `architecture-reviewer` interpreta
   - `architecture-reviewer` avalia aderência; `legacy-guardian` avalia impacto
   - `legacy-guardian` identifica impacto; `documentation-auditor` verifica se documentado

2. **Um subagente deve citar parecer anterior quando depender dele:**
   ```
   "Segundo parecer de repository-cartographer, os componentes afetados são..."
   ```

3. **Conflito entre pareceres é registrado, não resolvido silenciosamente:**
   ```
   Parecer de architecture-reviewer: APROVADO
   Parecer de legacy-guardian: BLOQUEADO

   Conflito: ADR necessária antes de continuar.
   Não é permitido prosseguir com apenas um parecer favorável.
   ```

4. **Parecer bloqueante permanece bloqueante até revisão humana:**
   - Se `legacy-guardian` bloqueia, `quality-gate-reviewer` também bloqueia
   - Se `documentation-auditor` encontra conflito terminológico pendente, `quality-gate-reviewer` não pode ignorar

5. **Nenhum agente pode delegar para contornar proibição:**
   - Se `legacy-preservation` (skill) proíbe alterar `app.py`, nenhum agente pode repassar isso como "fora do escopo"
   - A proibição é global

6. **Delegação não amplia permissões:**
   - Se uma skill não pode fazer algo, o agente que a consulta também não pode
   - Permissões são herdadas, não estendidas

7. **Todos os agentes trabalham sob o mesmo escopo autorizado:**
   - Escopo: Etapa 3 (skills e subagentes técnicos controlados)
   - Autorização: Leitura de repositório, nenhuma alteração funcional
   - Limite: Nenhum acesso a produção, MCPs, hooks, agentes contínuos

---

## Fluxo de atuação recomendado

### Para uma alteração simples (ex.: documentação, relatório)

```
1. repository-cartographer
   ↓ (mapeia os arquivos afetados)
2. repository-safety (skill)
   ↓ (verifica se alteração é permitida)
3. architecture-governance (skill) [opcional se não toca código]
   ↓
4. documentation-consistency (skill)
   ↓ (se toca documentação)
5. quality-gate-reviewer
   ↓ (consolidação final)
✓ Liberado para commit
```

### Para uma alteração com impacto legado

```
1. repository-safety (skill)
   ↓
2. legacy-preservation (skill)
   ↓ (verifica risco)
3. legacy-guardian (agente)
   ↓ (detalhes de impacto)
4. architecture-governance (skill) [se toca design]
   ↓
5. documentation-consistency (skill)
   ↓
6. quality-gate-reviewer
   ↓ (consolidação final)
✓ Liberado ou ✗ Bloqueado
```

### Para uma proposta arquitetural

```
1. repository-safety (skill)
   ↓
2. architecture-governance (skill)
   ↓ (exige ADR?)
3. architecture-reviewer (agente)
   ↓ (detalhes de aderência)
4. legacy-preservation (skill) [se toca legado]
   ↓
5. legacy-guardian (agente) [se toca legado]
   ↓
6. documentation-consistency (skill)
   ↓ (verifica se documentação contradiz)
7. documentation-auditor (agente)
   ↓
8. quality-gate-reviewer
   ↓ (consolidação final)
✓ Liberado ou ✗ Bloqueado
```

---

## Situações especiais

### Conflito terminológico "Item de Ingestão" vs "Documento"

**Responsável:** `documentation-auditor` + `documentation-consistency` (skill)

**Resposta obrigatória:** `DECISÃO DEPENDENTE DE ADR APROVADA`

**Nenhum agente pode:**
- Resolver silenciosamente
- Normalizar um dos termos
- Declarar equivalência definitiva
- Renomear entidade
- Tratar como erro simples

### Decisão pendente tratada como resolvida

**Responsável:** `documentation-auditor` + `documentation-consistency` (skill)

**Ação:** Bloquear e alertar que ADR ainda está `PENDENTE`

**Nenhum agente pode:**
- Prosseguir como se estivesse resolvida
- Tomar implementação com base em pendência

### Parecer bloqueante de múltiplas fontes

**Responsável:** `quality-gate-reviewer`

**Ação:** Registrar conflito e não permitir continuação

Exemplo:
```
repository-safety: BLOQUEADO (segredo detectado)
legacy-guardian: BLOQUEADO (risco crítico sem rollback)

quality-gate-reviewer: BLOQUEADO (múltiplos bloqueios)
```

---

## Matriz de evitação de sobreposição

| Aspecto | Skill A | Skill B | Diferença |
|---|---|---|---|
| **Segurança** | repository-safety | — | Primeira camada de defesa |
| **Arquitetura** | architecture-governance | documentation-consistency | Governança vs. consistência |
| **Legado** | legacy-preservation | documentation-consistency | Impacto vs. documentação |
| **Validação** | validation-gate | architecture-governance | Consolidação final vs. análise específica |
| **Mapeamento** | repository-cartographer | architecture-governance | Descoberta vs. interpretação |
| **Impacto** | legacy-guardian | architecture-reviewer | Operacional vs. conceitual |

---

## Obediência aos CLAUDE.md

Toda skill e todo agente:
1. Lê `CLAUDE.md` (raiz) antes de começar
2. Identifica se há `CLAUDE.md` específico do diretório
3. Aplica instruções cumulativamente
4. Dá precedência à instrução mais específica
5. Não utiliza instrução local para contornar proibição global
6. Registra conflito em vez de decidir silenciosamente

---

## Itens deliberadamente adiados

Os seguintes itens NÃO estão no escopo das skills e subagentes desta etapa:

- **MCPs:** Nenhum MCP foi instalado
- **Hooks:** Nenhum hook foi criado (pré-commit, post-commit, etc.)
- **Navegador controlado:** Nenhuma automação de navegador
- **Agentes contínuos:** Nenhum agente executando em background
- **Acesso autônomo a produção:** Nenhuma permissão para alterar/consultar produção
- **Execução programada:** Nenhuma agendamento (cron, etc.)
- **Autorreparo:** Nenhuma skill corrige a si própria
- **Deploy automático:** Nenhuma skill pode deployar
- **Alterações autônomas de banco:** Nenhuma skill pode executar migrations ou queries
- **Envio real de mensagens:** Nenhuma skill envia e-mail/WhatsApp reais

Esses itens serão avaliados em etapas posteriores do Magnata AI Engineering Powerpack.

---

## Revisão desta matriz

Se novos conflitos forem descobertos:
1. Registrar o conflito neste documento
2. Indicar qual skill/agente encontrou
3. Descrever o cenário
4. Propor resolução (se óbvia) ou marcar como `PENDENTE`
5. Não ocultar o conflito

Nenhuma skill ou agente pode alterar esta matriz sem autorização expressa.
