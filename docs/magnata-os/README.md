# Magnata OS — Índice da Documentação Fundacional

**Este arquivo é um índice, não uma cópia.** Todo documento listado
aqui continua vivendo na **raiz do repositório**, com o nome de arquivo
que já tem hoje — de propósito, não por descuido. Ver "Por que os
arquivos não foram movidos para cá" no final.

---

## Qual documento é a fonte principal

Não existe um único documento que responda tudo — cada um é fonte
principal de uma coisa diferente:

- **Princípios que nada pode contrariar:** [`MAGNATA_OS_MANIFESTO.md`](../../MAGNATA_OS_MANIFESTO.md).
  É a constituição — não muda com cada feature, e qualquer código,
  decisão ou documento que o contrarie está errado por definição
  (ver a cláusula "Autoridade" no próprio Manifesto).
- **Estado real medido do sistema + plano de evolução:** [`MAGNATA_OS_ARQUITETURA.md`](../../MAGNATA_OS_ARQUITETURA.md).
- **Capacidades e maturidade:** [`MAGNATA_OS_CAPACIDADES.md`](MAGNATA_OS_CAPACIDADES.md).
  Inventário de 26+ capacidades (o que o sistema pode fazer), maturidade de cada uma, estado atual, riscos e limites de autonomia.
- **Definição dos dez módulos funcionais:** [`MAGNATA_OS_MODULOS.md`](MAGNATA_OS_MODULOS.md).
  Propósito, responsabilidades, critérios de entrada/saída e riscos de cada módulo.
- **Roadmap de 11 fases:** [`MAGNATA_OS_ROADMAP.md`](MAGNATA_OS_ROADMAP.md).
  Migração incremental do legado para Magnata OS (Fase 0 concluída, Fases 1-11 planejadas).
- **Matriz arquitetural:** [`MAGNATA_OS_MATRIZ_ARQUITETURAL.md`](MAGNATA_OS_MATRIZ_ARQUITETURAL.md).
  Relacionamento entre capacidades, módulos, camadas, componentes atuais vs. alvo, autonomia, riscos.
- **Modelo de entidades canônico:** [`MAGNATA_OS_ENTIDADES.md`](../../MAGNATA_OS_ENTIDADES.md),
  com seu histórico de decisão em [`MAGNATA_OS_DECISOES_ENTIDADES.md`](../../MAGNATA_OS_DECISOES_ENTIDADES.md).
- **Vocabulário de eventos:** [`MAGNATA_OS_EVENTOS.md`](../../MAGNATA_OS_EVENTOS.md).
- **Forma dos dados (contratos):** [`MAGNATA_OS_CONTRATOS.md`](../../MAGNATA_OS_CONTRATOS.md).
- **Máquinas de estado:** [`MAGNATA_OS_ESTADOS.md`](../../MAGNATA_OS_ESTADOS.md).
- **Registro de decisões arquiteturais:** [`MAGNATA_OS_ADR_001_NOMENCLATURA_ITEM_INGESTAO_VS_DOCUMENTO.md`](MAGNATA_OS_ADR_001_NOMENCLATURA_ITEM_INGESTAO_VS_DOCUMENTO.md).
  Primeira ADR: divergência não resolvida entre "Item de Ingestão" (docs) e "Documento" (código), com 4 alternativas propostas.
- **Hooks locais de segurança:** [`MAGNATA_AI_HOOKS_LOCAIS.md`](MAGNATA_AI_HOOKS_LOCAIS.md).
  Barreiras locais determinísticas para validar conformidade, proteger arquivos, detectar segredos.
- **O que já foi de fato implementado (Módulo 01 — Documental):**
  [`MAGNATA_OS_DOCUMENTAL_MODULO01.md`](../../MAGNATA_OS_DOCUMENTAL_MODULO01.md)
  e suas fases (`_FASE2` a `_FASE4`) — a fonte da verdade sobre o que
  **existe em código**, não sobre o que foi planejado.

## Ordem de leitura recomendada

Segue a ordem real de dependência declarada por cada documento na sua
própria seção "Fontes" — ler fora de ordem funciona, mas exige ir e
voltar:

1. [`MAGNATA_OS_MANIFESTO.md`](../../MAGNATA_OS_MANIFESTO.md) — por que o sistema existe e o que nunca pode ser violado.
2. [`MAGNATA_OS_ARQUITETURA.md`](../../MAGNATA_OS_ARQUITETURA.md) — onde o sistema está hoje e para onde vai.
3. [`MAGNATA_OS_CAPACIDADES.md`](MAGNATA_OS_CAPACIDADES.md) — o que o sistema consegue fazer (26+ capacidades inventariadas).
4. [`MAGNATA_OS_MODULOS.md`](MAGNATA_OS_MODULOS.md) — os dez módulos funcionais.
5. [`MAGNATA_OS_ROADMAP.md`](MAGNATA_OS_ROADMAP.md) — as 11 fases de migração incremental.
6. [`MAGNATA_OS_MATRIZ_ARQUITETURAL.md`](MAGNATA_OS_MATRIZ_ARQUITETURAL.md) — relacionamento entre capacidades, módulos, camadas, estados.
7. [`MAGNATA_OS_ENTIDADES.md`](../../MAGNATA_OS_ENTIDADES.md) — o que existe (as "coisas" do domínio).
8. [`MAGNATA_OS_DECISOES_ENTIDADES.md`](../../MAGNATA_OS_DECISOES_ENTIDADES.md) — por que o modelo de entidades é o que é (pauta de decisão, algumas ainda `PENDENTE`).
9. [`MAGNATA_OS_EVENTOS.md`](../../MAGNATA_OS_EVENTOS.md) — o que acontece (fatos de negócio).
10. [`MAGNATA_OS_CONTRATOS.md`](../../MAGNATA_OS_CONTRATOS.md) — a forma exata dos dados.
11. [`MAGNATA_OS_ESTADOS.md`](../../MAGNATA_OS_ESTADOS.md) — como cada entidade transiciona.
12. [`MAGNATA_OS_ADR_001_NOMENCLATURA_ITEM_INGESTAO_VS_DOCUMENTO.md`](MAGNATA_OS_ADR_001_NOMENCLATURA_ITEM_INGESTAO_VS_DOCUMENTO.md) — primeira decisão arquitetural pendente (nomenclatura).
13. [`MAGNATA_OS_MODULO_01_INGESTAO.md`](../../MAGNATA_OS_MODULO_01_INGESTAO.md) — plano do primeiro módulo real, construído sobre 1-12.
14. [`MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md`](../../MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md) — decisões que destravaram o código do Módulo 01.
15. [`MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1.md`](../../MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1.md) e [`MAGNATA_OS_MODULO_01_FASE_0_OBSERVABILIDADE.md`](../../MAGNATA_OS_MODULO_01_FASE_0_OBSERVABILIDADE.md) — plano técnico das primeiras fases.
16. [`MAGNATA_OS_DOCUMENTAL_MODULO01.md`](../../MAGNATA_OS_DOCUMENTAL_MODULO01.md) → `_FASE2` → `_FASE3` → `_FASE4` → `_FASE5` (não mesclada ainda) — o que **de fato foi implementado**, fase a fase.
17. [`MAGNATA_OS_IDENTIDADE_VISUAL.md`](../../MAGNATA_OS_IDENTIDADE_VISUAL.md) — independente da cadeia acima (identidade de marca, não de domínio).

## Relação entre os documentos

```
MANIFESTO (princípios, nunca contrariados)
   │
   ▼
ARQUITETURA (estado real + plano)
   │
   ▼
┌──────────────────────────────────────────┐
│ CAPACIDADES, MODULOS, ROADMAP, MATRIZ    │
│ (visão de 11 fases, 26+ capacidades,     │
│  10 módulos, maturidade, autonomia)      │
└──────────────────────────────────────────┘
   │
   ▼
ENTIDADES ──────► DECISOES_ENTIDADES (decisão por trás do modelo)
   │
   ▼
EVENTOS ────────► CONTRATOS ────────► ESTADOS
   │                   │
   │                   ▼
   │          ADR_001_NOMENCLATURA (Item de Ingestão vs. Documento)
   │
   └──────────────┬───────────────────────┘
                   ▼
     MODULO_01_INGESTAO (plano do 1º módulo)
                   │
                   ▼
     MODULO_01_DECISOES_IMPLEMENTACAO (decisões que destravam o código)
                   │
                   ▼
     MODULO_01_PLANO_TECNICO_FASES_0_1 / FASE_0_OBSERVABILIDADE
                   │
                   ▼
     DOCUMENTAL_MODULO01 → FASE2 → FASE3 → FASE4 → (FASE5, branch própria)
     (implementação REAL, em magnata_os/documental/modulo01/)
```

`MAGNATA_OS_IDENTIDADE_VISUAL.md` fica fora dessa cadeia — trata da
marca (símbolo, cores, lockups), não do modelo de domínio.

## Documentos vigentes

Todos os listados acima estão em vigor. Dentro deles, nuances:

- `MAGNATA_OS_CAPACIDADES.md` — **versão 1.0**, inventário de 26+ capacidades mapeadas com maturidade 1-9.
- `MAGNATA_OS_MODULOS.md` — **versão 1.0**, definição canônica de 10 módulos funcionais.
- `MAGNATA_OS_ROADMAP.md` — **versão 1.0**, 11 fases de migração (Fase 0 concluída, Fases 1-11 planejadas).
- `MAGNATA_OS_MATRIZ_ARQUITETURAL.md` — **versão 1.0**, matriz de capacidades × módulos × camadas × estado.
- `MAGNATA_OS_ADR_001_NOMENCLATURA_ITEM_INGESTAO_VS_DOCUMENTO.md` — **PROPOSTA (não decidida)**, 4 alternativas sem recomendação vinculativa.
- `MAGNATA_OS_DECISOES_ENTIDADES.md` tem **26 de 29 decisões
  `APROVADA`** e **3 ainda `PENDENTE`** (`DEC-ENT-010`, `DEC-ENT-011`,
  `DEC-ENT-012`, ver §12 do próprio documento) — as pendentes não
  bloqueiam o restante, mas também não foram decididas; tratá-las como
  aprovadas seria alterar uma decisão de negócio em silêncio, o que
  este índice explicitamente não faz.
- `MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md` tem 12 decisões
  `APROVADA` e 1 `APROVADA POR CONTINUIDADE OPERACIONAL` (`DEC-MOD01-010`).
- [`MAGNATA_OS_HANDOFF_ATIVACAO_JULHO2026.md`](MAGNATA_OS_HANDOFF_ATIVACAO_JULHO2026.md)
  — runbook executável para a ativação real da esteira de importação em
  lote (Postgres + Airtable, Julho/2026), preparado numa sessão sem
  ferramenta de provisionamento Render/Postgres disponível; a execução
  externa em si fica para uma sessão/ambiente com esse acesso.

## Documentos históricos

- **`ARQUITETURA_FASE_2_DECISAO_FINAL.md`** (raiz do repo, 2026-07-20,
  anterior ao Manifesto) — decisão de arquitetura pontual para
  classificação de documentos, citada pelo próprio
  `MAGNATA_OS_ARQUITETURA.md` §0 como exemplo do padrão antigo
  ("documento avulso e não versionado como sistema") que a fundação
  atual substitui. Preservado como precedente histórico, **não** faz
  parte da cadeia de precedência atual.

## Regra de atualização

Cada documento já declara a própria regra, e este índice não a
substitui:

- `MAGNATA_OS_ARQUITETURA.md`: mudança relevante ganha entrada de
  changelog no final do arquivo, com data e motivo — **nunca reescrever
  histórico, só adicionar**.
- `MAGNATA_OS_ENTIDADES.md` / `MAGNATA_OS_EVENTOS.md` / `MAGNATA_OS_CONTRATOS.md` / `MAGNATA_OS_ESTADOS.md`:
  documentos **canônicos versionados** (`Versão: 1.0`) — uma mudança de
  significado é uma nova versão, não uma edição silenciosa do mesmo
  texto.
- `MAGNATA_OS_DECISOES_ENTIDADES.md`: decisão só deixa de ser
  `PENDENTE` quando a Direção da Magnata responde — nenhuma outra
  sessão (humana ou agente) marca uma decisão como `APROVADA` em nome
  dela.
- Documentos de fase (`MAGNATA_OS_DOCUMENTAL_MODULO01_FASE*.md`): cada
  fase é um arquivo novo, a fase anterior nunca é reescrita.

## Quem prevalece em caso de conflito

Ordem de precedência (definida nesta etapa do Powerpack, item 6):

1. **Decisões arquiteturais aprovadas e implementadas** — se o código em
   `magnata_os/` (mesclado em `main`) faz algo de um jeito e um
   documento de planejamento descreve outro, **o código prevalece
   sobre o plano**, mas a divergência deve ser **registrada
   explicitamente**, nunca corrigida em silêncio num dos dois lados
   (ver conflito já detectado nesta etapa, `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA1.md`).
2. **Contratos e estados oficiais** — `MAGNATA_OS_CONTRATOS.md` e
   `MAGNATA_OS_ESTADOS.md`, para tudo que ainda não foi implementado.
3. **Documentação do módulo** — `MAGNATA_OS_MODULO_01_*` e
   `MAGNATA_OS_DOCUMENTAL_MODULO01*`.
4. **Roadmap** — ainda não existe (`MAGNATA_OS_ROADMAP.md` não foi
   criado; ver `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA1.md`, pendências).
5. **Notas e documentos históricos** — `ARQUITETURA_FASE_2_DECISAO_FINAL.md`,
   itens `PENDENTE` de `MAGNATA_OS_DECISOES_ENTIDADES.md`.

`MAGNATA_OS_MANIFESTO.md` fica **fora** dessa escala numerada porque
não compete com os outros documentos — é a autoridade sobre princípios
que nenhum item de 1 a 5 pode contrariar, em nenhuma circunstância.

## Camada técnica: Skills e Subagentes (Etapa 3)

**Documentação:** [`MAGNATA_AI_SKILLS_E_SUBAGENTES.md`](MAGNATA_AI_SKILLS_E_SUBAGENTES.md)

**Propósito:** Estabelecer procedimentos reutilizáveis de engenharia e
agentes técnicos especializados para verificação, governança e validação.

**Composição:**

- **5 Skills** (procedimentos):
  1. `magnata-repository-safety` — segurança do repositório
  2. `magnata-architecture-governance` — governança arquitetural
  3. `magnata-legacy-preservation` — proteção do legado
  4. `magnata-documentation-consistency` — coerência documental
  5. `magnata-validation-gate` — consolidação final

- **5 Subagentes** (agentes especializados):
  1. `repository-cartographer` — mapeamento estrutural
  2. `architecture-reviewer` — análise arquitetural
  3. `legacy-guardian` — proteção operacional
  4. `documentation-auditor` — auditoria documental
  5. `quality-gate-reviewer` — revisão final

**Matriz de responsabilidades:** [`.claude/MATRIX_DE_RESPONSABILIDADES.md`](../../.claude/MATRIX_DE_RESPONSABILIDADES.md)

**Limite de escopo:** Todos trabalham em leitura segura do repositório.
Nenhum acesso autônomo a produção. Nenhuma alteração de código. Nenhum
MCP, hook ou agente contínuo instalado.

## Camada técnica: CI de Governança (Etapa 6)

**Status:** MESCLADO EM `main` — PR #13, merge commit
`d616d521082db5d97e1824daf14c6cfdb4618f31`. 47/47 testes da suíte
isolada aprovados, 6/6 hooks reais aprovados, 15/15 gates aprovados
numa simulação de checkout limpo do PR contra `origin/main` antes do
merge. Nenhum deploy, nenhuma alteração de código funcional (`app.py`,
frontend, `magnata_os/`, migrations reais) em nenhum commit da etapa.

**Documentação:**
- [`MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6_PLANO.md`](../../MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6_PLANO.md) — plano original aprovado.
- [`MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md`](../../MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md) — relatório da implementação, correções e fechamento final pós-merge.
- [`MAGNATA_AI_CI_GOVERNANCA.md`](MAGNATA_AI_CI_GOVERNANCA.md) — arquitetura, fonte única de verdade, os 16 gates, limitações conhecidas.

**Propósito:** Estabelecer validação automática de governança e conformidade
documental via GitHub Actions, sem autonomia de produção.

**Escopo:**
- CI não invasivo em pull requests, pushes na branch de desenvolvimento
  histórica e push pós-merge em `main`
- 16 quality gates (segurança, proteção, conformidade, documentação, modos Git)
- Fonte única de verdade (`.magnata/patterns.sh`) compartilhada entre hook local e CI
- Política canônica de branches autorizadas (`AUTHORIZED_BRANCHES`,
  enumeração fechada) — `main` nunca entra nessa lista; push pós-merge
  em `main` é reconhecido pelo Gate de branch como contexto distinto,
  só quando `GITHUB_EVENT_NAME=push` e `GITHUB_REF_NAME=main` ocorrem
  juntos (nunca por execução local ou por uma das duas variáveis
  isolada)
- Hierarquia dos 4 `CLAUDE.md` institucionais (`CLAUDE_HIERARCHY`)
  liberada por igualdade exata de caminho, nunca por padrão amplo —
  qualquer outro arquivo nos mesmos diretórios continua protegido
- Read-only, sem secrets, sem deploy

**Composição:**
- `.github/workflows/magnata-governance.yml` — workflow principal (só orquestra)
- `scripts/ci/validate_governance.sh` — os 16 gates
- `scripts/ci/test_governance.sh` — suíte isolada (52/52 aprovados)
- `.magnata/patterns.sh` — padrões canônicos

**Correções aplicadas antes do merge:** o falso negativo do Gate 6
(whitespace) sob `pipefail`, e a divergência entre `CLAUDE_HIERARCHY`/Gate
12 e `ALLOWED_PATHS`/`PROTECTED_FILES` — ambas descritas com causa e
correção em `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md`. A antiga
limitação do fallback `git diff HEAD^..HEAD` (só via o último commit de
um PR) foi substituída pelo contrato explícito `base_ref...head_ref`,
usado em todos os eventos de CI.

## Por que os arquivos não foram movidos para cá

Os 9 documentos fundacionais se referenciam uns aos outros **pelo nome
de arquivo exato**, em prosa, centenas de vezes (`MAGNATA_OS_ARQUITETURA.md`
sozinho é citado 58 vezes pelos outros; `MAGNATA_OS_ENTIDADES.md`, 77
vezes). Pelo menos um documento **já versionado em `main`**
(`MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1.md`) já referencia vários
desses arquivos pelo nome atual. Renomear ou mover agora, sem reescrever
todas essas referências, quebraria links de forma silenciosa — exatamente
o risco que esta etapa foi instruída a evitar.

**Reorganização futura proposta** (não executada nesta etapa):

```
docs/magnata-os/
  00-manifesto.md                    ← MAGNATA_OS_MANIFESTO.md
  01-arquitetura.md                  ← MAGNATA_OS_ARQUITETURA.md
  02-capacidades.md                  ← MAGNATA_OS_CAPACIDADES.md (criado Etapa 4)
  03-modulos.md                      ← MAGNATA_OS_MODULOS.md (criado Etapa 4)
  04-roadmap.md                      ← MAGNATA_OS_ROADMAP.md (criado Etapa 4)
  05-matriz-arquitetural.md          ← MAGNATA_OS_MATRIZ_ARQUITETURAL.md (criado Etapa 4)
  06-entidades.md                    ← MAGNATA_OS_ENTIDADES.md
  06a-decisoes-entidades.md          ← MAGNATA_OS_DECISOES_ENTIDADES.md
  07-contratos.md                    ← MAGNATA_OS_CONTRATOS.md
  08-estados.md                      ← MAGNATA_OS_ESTADOS.md
  09-eventos.md                      ← MAGNATA_OS_EVENTOS.md
  10-adr-001-nomenclatura.md          ← MAGNATA_OS_ADR_001_NOMENCLATURA_ITEM_INGESTAO_VS_DOCUMENTO.md (criado Etapa 4)
```

Quando essa reorganização for feita de verdade, precisa ser numa etapa
própria que: (1) liste toda referência cruzada existente (comando usado
nesta etapa: buscar `MAGNATA_OS_[A-Z0-9_]*\.md` em todos os `.md` do
repositório); (2) mova os arquivos; (3) reescreva cada referência
encontrada; (4) confirme, por busca, que nenhum nome antigo restou.
