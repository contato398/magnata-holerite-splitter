# CENTRAL COMMAND — Magnata OS

**Tipo:** memória mestre persistente e verificável do estado real do projeto.
**Propósito:** ser o contexto inicial de qualquer nova conversa/sessão sobre o Magnata OS, substituindo a dependência de uma conversa longa como memória principal.
**Gerado em:** 2026-08-21 (Etapa 1 — auditoria técnica), ampliado em 2026-08-21 (Etapa 2 — auditoria de memória e proveniência) e em 2026-08-22 (Etapa 3 — consolidação macro e unificação de duas linhas divergentes; Etapa 4 — preservação canônica: fundação documental resgatada para `main`, memória histórica preservada dentro dos limites da LGPD). Repositório `contato398/magnata-holerite-splitter` (branch auditada: `main` em `d3546ba`; branches remotas verificadas: todas).
**Método:** nenhuma informação aqui vem de conversa anterior tratada como verdade absoluta. Tudo foi confirmado em código, documentação versionada, histórico de commits/branches ou execução real de teste nesta sessão. Onde isso não foi possível, o item está marcado 🔍 **PRECISA SER VALIDADO**, nunca apresentado como fato.
**Linhagem deste arquivo:** nasceu como `CENTRAL_COMMAND_MAGNATA_OS.md` na raiz, na branch `claude/magnata-central-command-0n0713` (commits `ea95ab6`, `27d12b1`). Foi movido para cá na Etapa 3 porque aquele caminho e aquela branch não passam nos gates de governança do próprio repositório — ver §0-B.2. O texto das Etapas 1 e 2 está preservado; a Etapa 3 acrescenta, corrige explicitamente onde errou, e nunca reescreve.

**Regra de manutenção:** este documento fica desatualizado no minuto em que o código muda. Ele **não substitui** `CLAUDE.md` nem `docs/magnata-os/README.md` — é uma camada de consolidação por cima deles, e deve ser regenerado por auditoria, não editado de memória.

**Legenda de status:**
✅ FUNCIONANDO/CONFIRMADO · 🟡 EM EVOLUÇÃO · ⚠️ PENDENTE · ❌ DESCARTADO/SUPERADO · 🔍 PRECISA SER VALIDADO · 🚫 PLANEJADO MAS NÃO EXECUTADO

---

## 0. Etapa 2 — Memória e proveniência (2026-08-21)

Esta seção resume o que a Etapa 2 acrescentou. O detalhe completo,
estruturado por ID e rastreável até a fonte exata (arquivo + branch +
commit), vive em `central-command/` — **deliberadamente fora
deste arquivo**, para não colocar toda a memória bruta num único
Markdown:

- [`SOURCES_AND_PROVENANCE.md`](central-command/SOURCES_AND_PROVENANCE.md) — índice de toda fonte histórica localizada, auditada ou não.
- [`DECISIONS.md`](central-command/DECISIONS.md) — 11 decisões arquiteturais/técnicas, com ID, evidência, status.
- [`DIRECTIVES.md`](central-command/DIRECTIVES.md) — 11 ordens da Direção, da diretiva fundacional ("arquiteto-chefe", 2026-07-22) a regras operacionais pontuais.
- [`ACTIONS_COMPLETED.md`](central-command/ACTIONS_COMPLETED.md) — 35 ações concluídas, 12/06/2026 a hoje.
- [`WORK_IN_PROGRESS.md`](central-command/WORK_IN_PROGRESS.md) — 8 frentes com código/documento real, não mescladas.
- [`PENDING.md`](central-command/PENDING.md) — 19 pendências ativas.
- [`ARCHITECTURE.md`](central-command/ARCHITECTURE.md) — linha do tempo completa de como a fundação documental chegou (ou não) a `main`.
- [`SUPERSEDED_DECISIONS.md`](central-command/SUPERSEDED_DECISIONS.md) — 7 trilhas `DECISÃO ANTIGA → SUPERADA POR → DECISÃO NOVA`.
- [`COBERTURA.md`](central-command/COBERTURA.md) — relatório de cobertura e lacunas, com a resposta objetiva a "a memória está completa?" (não).

**O achado mais importante da Etapa 2:** existe uma memória de
continuidade real do projeto (`docs/historico/`, 30 registros
cobrindo 12/06 a 01/07/2026, decisões da diretoria, bugs encontrados e
corrigidos, pendências) — mas ela vive **só** na branch
`fix/recibos-outros-documentos`, nunca mesclada em `main`. A Etapa 1
desta auditoria tinha classificado essa branch como "❌ aparenta
obsoleta/abandonada" por causa do volume de deleções no diff — **essa
leitura estava incompleta**: a branch carrega justamente o arquivo de
memória que este pedido de Etapa 2 buscava. Correção registrada aqui,
não escondida — ver `central-command/SOURCES_AND_PROVENANCE.md` §2.

**Limite que nenhuma auditoria futura vai conseguir remover:** esta
sessão não tem, e nenhuma sessão em container remoto efêmero jamais
terá, acesso às conversas brutas que geraram esses documentos — só ao
que foi escrito e commitado. `docs/historico/` e os relatórios de fase
**são** a memória de continuidade do projeto; não existe uma camada
"mais bruta" ainda por trás deles que este processo possa recuperar.
Ver a resposta completa em `COBERTURA.md`.

---

## 0-B. Etapa 3 — Consolidação macro e recuperação da fundação (2026-08-22)

A Etapa 3 fez três coisas que as anteriores não tinham feito: **leu o
conteúdo** dos documentos fundacionais (a lacuna nº 1 declarada em
`COBERTURA.md`), **fechou a lacuna temporal** de 01/07–20/07/2026, e
**consolidou duas linhas de Central Command que haviam divergido**.

### 0-B.1 Duas Central Commands existiam em paralelo — agora é uma

Em 2026-08-21 e 2026-08-22, duas sessões produziram, sem saber uma da
outra, dois documentos de consolidação distintos:

| Linha | Onde | Conteúdo |
|---|---|---|
| A (Etapas 1-2) | `claude/magnata-central-command-0n0713`, commits `ea95ab6` e `27d12b1` | `CENTRAL_COMMAND_MAGNATA_OS.md` (raiz) + 9 auxiliares em `docs/central-command/` |
| B (rodada isolada) | branch de trabalho, nunca publicada | `docs/magnata-os/MAGNATA_OS_CENTRAL_COMMAND.md`, documento único |

**A linha A é a canônica** — é anterior, mais completa e já tinha a
estrutura auxiliar correta. Este documento **é** a linha A, preservada
integralmente e ampliada. O que a linha B tinha de próprio (inventário
de PRs #1–#30, livro-razão das autorizações de `app.py`, classificação
das falhas de teste) foi absorvido nos auxiliares desta etapa. O arquivo
da linha B foi descartado como caminho duplicado antes de qualquer
publicação — nenhum conteúdo dele se perdeu, e nenhuma documentação
versionada foi apagada.

### 0-B.2 Achado de governança: a Etapa 1-2 foi commitada fora das regras

Verificado mecanicamente contra `.magnata/patterns.sh` nesta etapa:

- `claude/magnata-central-command-0n0713` **não passa** em
  `is_authorized_branch()` — o único padrão `claude/*` aceito é
  `^claude/macro-6a-[a-z0-9-]*$`.
- `CENTRAL_COMMAND_MAGNATA_OS.md` na raiz e `docs/central-command/*`
  **não batem** com nenhum item de `ALLOWED_PATHS`.

Ou seja: aqueles dois commits só existem porque os hooks locais não
estavam ativos naquela sessão. Não há má-fé nenhuma nisso — mas
significa que **aquele trabalho não poderia entrar em `main` como
está**, e que o CI de governança o rejeitaria.

**Correção aplicada nesta etapa, sem perder nada:** todo o conteúdo foi
movido para caminhos que `ALLOWED_PATHS` já autoriza —
`docs/magnata-os/MAGNATA_OS_CENTRAL_COMMAND.md` (mestre) e
`docs/magnata-os/central-command/*.md` (auxiliares) — numa branch que
`is_authorized_branch()` aceita. As referências internas foram
reescritas para o novo caminho. A branch de origem **não foi apagada**.

### 0-B.3 Fundação documental — conteúdo finalmente extraído

`COBERTURA.md` §7 apontava como lacuna nº 1: "ler o conteúdo integral
dos 9 documentos fundacionais — hoje só confirmamos que existem". Isso
foi feito nesta etapa (9.600 linhas inventariadas). O resultado
estruturado está em
[`central-command/FOUNDATION.md`](central-command/FOUNDATION.md).

O achado de maior valor — **nunca registrado em nenhuma Central Command
até agora**: existe um **Modelo Conceitual aprovado pela Direção da
Magnata em 2026-07-22**, vocabulário oficial da plataforma, que não está
em `main`:

```text
Empresa Magnata
└── Cliente
    └── Contrato Comercial
        └── Posto de Trabalho

Colaborador
└── Vínculo Trabalhista
    └── Alocação
        └── Posto de Trabalho
```

Junto dele, mais três modelos conceituais igualmente aprovados na mesma
data (Documental, Distribuição e Entrega, Assinatura) e **26 das 29
decisões `DEC-ENT-*` marcadas `APROVADA`**. Isso não é plano nem
proposta: é decisão de negócio tomada, que hoje sobrevive apenas numa
branch cujo PR foi fechado sem merge.

### 0-B.4 Conflito dos "9 vs 10 módulos" — resolvido, não era contradição

As Etapas 1 e 2 registraram como divergência aberta o fato de
`CLAUDE.md` §3 citar "9 módulos oficiais... documentados em
`MAGNATA_OS_ARQUITETURA.md` §2" enquanto `MAGNATA_OS_MODULOS.md` declara
dez. Lendo `MAGNATA_OS_ARQUITETURA.md` §2 diretamente nesta etapa:
**ele de fato lista exatamente 9 módulos.** `CLAUDE.md` está correto ao
citá-lo.

Não é contradição — são **duas taxonomias sucessivas**, e o mapeamento
entre elas é exato:

| `ARQUITETURA` §2 (2026-07-22, 9) | `MODULOS.md` v1.0 (2026-07-25, 10) |
|---|---|
| 1 Ingestão · 2 Classificação · 3 Cadastro | idem (1, 2, 3) |
| — | **4 RH — desmembrado, é o único módulo novo** |
| 4 Ponto/Secullum | 5 Ponto (Secullum) |
| 5 Folha/Documentos | 6 Documentos |
| 6 Distribuição · 7 Assinatura | 7 Distribuição · 8 Assinaturas |
| 8 Auditoria/Observabilidade · 9 Plataforma | 9 Auditoria · 10 Plataforma |

A taxonomia de dez **supera** a de nove por ser posterior. Registrado
como trilha em [`central-command/SUPERSEDED_DECISIONS.md`](central-command/SUPERSEDED_DECISIONS.md).
O que continua verdadeiro é o problema real por trás: `CLAUDE.md` aponta
para um arquivo que não existe em `main`.

### 0-B.5 Lacuna temporal 01/07–20/07/2026 — fechada

`COBERTURA.md` §3 marcava esse intervalo como "⚠️ Baixa — sem fonte de
memória de continuidade encontrada", com a hipótese de ser baixa
atividade ou memória perdida. **Nenhuma das duas.** O período teve
atividade intensa: cerca de 35 commits, versões `v2.67` a `v3.17`,
cobrindo a arquitetura definitiva do fechamento de Folha de Ponto
(`v3.00`), o pipeline fiscal (`v2.67`, `v2.97`), o Extrato Bancário
Consolidador (`v3.15`–`v3.17`), o processamento assíncrono com Celery e
a Assinatura Nativa automática ao fatiar Folha de Ponto (`v2.98`).

A memória desse período **existe** — vive nas mensagens de commit, não
em `docs/historico/` (que para em 01/07). O título do commit `1027fc8`
("12/06 a 22/07/2026") é impreciso quanto ao conteúdo, como a Etapa 2
já havia notado.

### 0-B.6 Correções de fato aos registros anteriores

Registradas, não silenciadas:

| Afirmação anterior | Correção verificada nesta etapa |
|---|---|
| "13 arquivos de autorização registrados" (§6) | São **12** — `ls .magnata/app-py-authorizations/*.gitblob` |
| "as 19 falhas são pré-existentes de ambiente" (linha B) | **13** são de ambiente (`celery` ausente); **6** são divergência real código×teste. Com `cffi` e `celery` instalados: 636 passando / 6 falhando |
| "fontes 'Central Command' e 'Auditoria de Memória' não localizadas" (linha B) | **Localizadas** — são exatamente os commits `ea95ab6` e `27d12b1`. A conclusão anterior era correta para os refs disponíveis naquele momento e está superada |
| "`fix/recibos-outros-documentos` não auditada" (linha B) | Auditada: carrega `docs/historico/`, **31 arquivos**, commit `1027fc8` |


---

## 0-C. Etapa 4 — Preservação canônica da memória (2026-08-22)

Esta etapa executou NXT-001 + NXT-002 como uma fase única de
preservação. **O que mudou em relação a tudo que veio antes:** a §3
deste documento e a Etapa 2 descreviam corretamente que a fundação e a
memória histórica estavam presas em branches. **A fundação não está
mais.** A memória histórica está preservada em conhecimento, mas não em
texto bruto — e o motivo é LGPD, não descuido.

### 0-C.1 Rastro canônico — `ORIGEM HISTÓRICA → ARQUIVO CANÔNICO → STATUS`

| Origem histórica | Arquivo canônico agora | Status |
|---|---|---|
| `powerpack:MAGNATA_OS_ARQUITETURA.md` | `MAGNATA_OS_ARQUITETURA.md` | ✅ Preservado · 🟡 §2 superada por `MODULOS.md`, com nota |
| `powerpack:MAGNATA_OS_ENTIDADES.md` | `MAGNATA_OS_ENTIDADES.md` | ✅ Preservado · vigente |
| `powerpack:MAGNATA_OS_DECISOES_ENTIDADES.md` | `MAGNATA_OS_DECISOES_ENTIDADES.md` | ✅ Preservado · **26 decisões aprovadas + 4 Modelos Conceituais**, com nota sobre o cabeçalho desatualizado |
| `powerpack:MAGNATA_OS_CONTRATOS.md` | `MAGNATA_OS_CONTRATOS.md` | ✅ Preservado · vigente · **`CLAUDE.md` §2 volta a ter alvo real** |
| `powerpack:MAGNATA_OS_ESTADOS.md` | `MAGNATA_OS_ESTADOS.md` | ✅ Preservado · vigente · idem |
| `powerpack:MAGNATA_OS_EVENTOS.md` | `MAGNATA_OS_EVENTOS.md` | ✅ Preservado · vigente |
| `powerpack:MAGNATA_OS_MODULO_01_INGESTAO.md` | `MAGNATA_OS_MODULO_01_INGESTAO.md` | ✅ Preservado · 🟡 plano anterior ao código, com nota de precedência |
| `powerpack:..._MODULO_01_DECISOES_IMPLEMENTACAO.md` | mesmo nome | ✅ Preservado · 13 decisões |
| `powerpack:docs/magnata-os/ADR_001...` | `docs/magnata-os/MAGNATA_OS_ADR_001_...md` | ✅ Preservado · ⚠️ **continua sem decisão**, por desenho |
| `powerpack:docs/magnata-os/MAGNATA_AI_SKILLS_E_SUBAGENTES.md` | mesmo caminho | ✅ Preservado (documento) |
| `powerpack:` 8 relatórios de Etapa do Powerpack | raiz, mesmos nomes | ✅ Preservados · 📜 relatórios históricos |
| `recibos:docs/historico/` (31 arquivos) | `central-command/HISTORICO.md` + 2 originais em `docs/magnata-os/historico/` | 🟡 **Conhecimento preservado, texto bruto não** — LGPD, ver 0-C.3 |
| `powerpack:.claude/skills/*`, `agents/*`, `MATRIX_*` | — | ⚠️ **Ainda fora** — caminhos não cobertos por `ALLOWED_PATHS` |
| `fase5-painel:MAGNATA_OS_DOCUMENTAL_MODULO01_FASE5.md` | — | ⚠️ **Ainda fora** — Fase 5 não mesclada; trazer só o documento afirmaria algo que o código não sustenta |

### 0-C.2 Reconciliação, não cópia cega

Cada arquivo resgatado leva um bloco de **proveniência** no topo (branch,
HEAD, PR de origem, data do fechamento sem merge). Três receberam
**NOTA DE RECONCILIAÇÃO** visível, porque tinham divergência conhecida:

1. `ARQUITETURA.md` — o mapa de 9 módulos é anterior ao de 10; o resto
   não foi superado.
2. `DECISOES_ENTIDADES.md` — o cabeçalho diz "pauta aberta"; a §12 do
   mesmo arquivo lista 26 aprovadas. A nota aponta qual das duas
   declarações internas é a posterior. **Nenhum status foi alterado.**
3. `MODULO_01_INGESTAO.md` — é plano anterior às Fases 1-4 já
   implementadas; a nota registra que o código prevalece.

**Nenhuma decisão aprovada pela Direção foi alterada, reinterpretada ou
marcada de outra forma.** Plano antigo continua rotulado como plano.

### 0-C.3 LGPD travou a cópia dos 31 históricos — e isso é um achado

Auditoria obrigatória antes de qualquer cópia:

- **8 de 31** arquivos com **CPF real de funcionário**;
- **29 de 31** com **nome completo de funcionário real**;
- apenas **2** livres de dado pessoal;
- pior caso: **51** candidatos a nome num único arquivo.

`CLAUDE.md` §6 proíbe dado pessoal em commit, e §12-I diz que a
autonomia nunca dispensa §6. Mascaramento automático em massa foi
**avaliado e rejeitado** — com 29 arquivos, um nome escapando viraria
violação permanente na linha canônica.

**O que foi feito:** `central-command/HISTORICO.md` preserva a lição, a
decisão e a proveniência (blob SHA) dos **30 registros**, verificadamente
livre de PII; os **2 arquivos limpos** foram preservados na íntegra.
Três regras vivas em produção hoje ganharam finalmente registro de
origem — "nome não é identificador", "envio combinado numa mensagem só"
e "assinatura nativa com evidência de IP/CPF".

**O que continua dependendo da branch:** o texto bruto dos 29 arquivos.
Desidentificá-los é trabalho próprio e **gate humano** — envolve dado
pessoal dos funcionários.

### 0-C.4 Referências que apontavam para o vazio — corrigidas

Antes: **13 documentos** citados por `docs/magnata-os/README.md` e por
`CLAUDE.md` §2/§5 não existiam em `main`.
Depois: **zero** referências quebradas em `CLAUDE.md` e no `README.md`.

Nenhuma regra de negócio foi alterada para resolver link. O caminho foi
o inverso — confirmar qual documento é canônico e **trazer o documento**.
O `README.md` recebeu nota declarando o que foi resgatado e o que
continua fora.


---

## 1. Visão geral

O Magnata OS é a plataforma operacional modular da Magnata, em migração
incremental (*strangler pattern*) a partir de um monólito Flask legado
(`app.py`, 12.301 linhas, em produção no Render). Holerite, ponto,
admissão, assinatura e distribuição são **módulos** dessa plataforma —
não o produto inteiro.

**Estado real em uma frase:** existe uma constituição de engenharia
madura (`CLAUDE.md`, na raiz, em vigor), um legado grande e ativo em
produção (`app.py` + Airtable + Render), e um primeiro módulo novo
(**Documental — Módulo 01**) com código real, testado e isolado do
legado — mas a maior parte da documentação fundacional que esse módulo
deveria seguir (contratos, estados, entidades, ADR, skills/subagentes)
**não está mesclada em `main`**: vive numa branch aberta desde
30/07/2026 (`feat/magnata-os-claude-powerpack`) que nunca virou PR
mesclado. Isso é a divergência mais importante encontrada nesta
auditoria — ver §5 e §10.

---

## 2. Arquitetura

Visão de 6 estágios (`CLAUDE.md` §3), simplificação dos módulos
oficiais:

**Entrada → Inteligência → Transformação → Negócio → Entrega → Auditoria**

com **Plataforma** como camada transversal (infraestrutura, adapters,
segurança) por baixo de todas.

Princípios em vigor (confirmados no código, não só no papel):
- ✅ **Domínio sem dependência de Flask/Airtable/Render** — confirmado:
  `magnata_os/documental/{modulo01,importacao_lote}/dominio*.py` não
  importam Flask, `psycopg`, `boto3` nem cliente Airtable diretamente.
- ✅ **Adapters para serviço externo** — `adapters/postgres_repositorio.py`,
  `adapters/s3_armazenamento.py`, `adapters/airtable_leitura.py`,
  `adapters/airtable_escrita.py`, `adapters/postgres_execucao.py`
  existem e isolam I/O do domínio puro.
- ✅ **Contratos antes de integração real** — o Módulo 01 tem `contratos.py`
  próprio (API) antes de qualquer rota HTTP real existir.
- 🔍 **PostgreSQL como metadados oficiais / S3 para binários** — é a
  direção do código (`adapters/postgres_repositorio.py`,
  `adapters/s3_armazenamento.py`, migrations 0001-0009 existem), mas
  **nenhum Postgres real foi provisionado** — ver §6.

---

## 3. Fonte de verdade de cada informação — auditada, não presumida

`CLAUDE.md` §2 declara uma escala de precedência e aponta
`docs/magnata-os/README.md` como índice. Auditando o que esse índice
promete contra o que **de fato existe em `main`**:

| Documento citado por `CLAUDE.md`/README como fundacional | Existe em `main`? | Onde de fato está |
|---|---|---|
| `MAGNATA_OS_MANIFESTO.md` | ✅ sim (raiz) | `main` |
| `MAGNATA_OS_ARQUITETURA.md` | ❌ **não** | só em `origin/feat/magnata-os-claude-powerpack` |
| `MAGNATA_OS_ENTIDADES.md` | ❌ **não** | idem |
| `MAGNATA_OS_DECISOES_ENTIDADES.md` | ❌ **não** | idem |
| `MAGNATA_OS_EVENTOS.md` | ❌ **não** | idem |
| `MAGNATA_OS_CONTRATOS.md` | ❌ **não** | idem |
| `MAGNATA_OS_ESTADOS.md` | ❌ **não** | idem |
| `MAGNATA_OS_ADR_001_...md` | ❌ **não** | idem (`docs/magnata-os/`) |
| `MAGNATA_OS_MODULO_01_INGESTAO.md` | ❌ **não** | idem |
| `MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md` | ❌ **não** | idem |
| `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA1.md` a `ETAPA5*` | ❌ **não** | idem |
| `MAGNATA_AI_SKILLS_E_SUBAGENTES.md` + `.claude/skills/*` + `.claude/agents/*` | ❌ **não** | idem |
| `.claude/MATRIX_DE_RESPONSABILIDADES.md` | ❌ **não** | idem |
| `MAGNATA_OS_CAPACIDADES.md` | ✅ sim | `docs/magnata-os/`, `main` |
| `MAGNATA_OS_MODULOS.md` | ✅ sim | `docs/magnata-os/`, `main` |
| `MAGNATA_OS_ROADMAP.md` | ✅ sim | `docs/magnata-os/`, `main` |
| `MAGNATA_OS_MATRIZ_ARQUITETURAL.md` | ✅ sim | `docs/magnata-os/`, `main` |
| `MAGNATA_OS_DOCUMENTAL_MODULO01.md` + `_FASE2/3/4` | ✅ sim | raiz, `main` |
| `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md` (relatório) | ✅ sim | raiz, `main` |
| `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6_PLANO.md` | ❌ **não** | só na branch powerpack |
| `MAGNATA_AI_CI_GOVERNANCA.md`, `MAGNATA_AI_HOOKS_LOCAIS.md` | ✅ sim | `docs/magnata-os/`, `main` |
| `MAGNATA_OS_GATE_ESPECIFICACAO.md` | ✅ sim (proposta, não implementada) | `docs/magnata-os/`, `main` |
| `MAGNATA_OS_HANDOFF_ATIVACAO_JULHO2026.md` | ✅ sim | `docs/magnata-os/`, `main` |

**Conclusão registrada, não corrigida em silêncio:** `docs/magnata-os/README.md`
(que está em `main`) afirma que a Fase 0 do roadmap está "CONCLUÍDA" com
entregável "Contratos oficiais definidos" e "Máquinas de estado
documentadas" — mas `MAGNATA_OS_CONTRATOS.md` e `MAGNATA_OS_ESTADOS.md`
**não existem em `main`**. A fundação documental citada existe, mas
**presa numa branch nunca mesclada** (`feat/magnata-os-claude-powerpack`,
5 commits, último em 2026-07-30, 20 commits à frente do ponto onde
divergiu de `main` — e `main` já avançou 70 commits além desse mesmo
ponto). Isso não é um código quebrado; é uma lacuna de merge. Ver §10
para o que fazer com isso (decisão que **não é técnica** — envolve
reconciliar 70 commits de `main` com o conteúdo dessa branch).

Adicionalmente: `CLAUDE.md` §3 fala em "9 módulos oficiais... já
documentados em `MAGNATA_OS_ARQUITETURA.md` §2" — mas `MAGNATA_OS_ARQUITETURA.md`
não existe em `main` (ver tabela acima), e o documento que **de fato
existe** e define módulos, `MAGNATA_OS_MODULOS.md`, declara **dez**
módulos funcionais (Ingestão, Classificação, Cadastro, RH, Ponto,
Documentos, Distribuição, Assinaturas, Auditoria, Plataforma), não
nove. Divergência registrada aqui — não é resolvida por esta sessão.

---

## 4. Módulos — estado real por módulo (10 módulos, `MAGNATA_OS_MODULOS.md`)

| # | Módulo | Doc diz (v1.0, 2026-07-25) | Código real hoje | Status |
|---|---|---|---|---|
| 1 | Ingestão | Legado operacional (Gmail/Apps Script) | `apps_script_email_intake.gs` ativo; `magnata_os/documental/modulo01/servico_entrada*.py` isolado, testado, não plugado ao legado | 🟡 EM EVOLUÇÃO |
| 2 | Classificação | Não implementado | Nenhum código de classificação automática encontrado | 🚫 PLANEJADO MAS NÃO EXECUTADO |
| 3 | Cadastro | Legado parcial (Secullum, Airtable) | `src/sync_new_employees.py`, `src/ingestao_secullum.py` — legado operacional | ✅ FUNCIONANDO (legado) / 🚫 módulo novo não iniciado |
| 4 | RH | Legado em `app.py` (admissão manual) | Kit Admissão em `app.py` + `test_kit_admissao_identidade.py` (31 testes, passando) | ✅ FUNCIONANDO (legado) |
| 5 | Ponto (Secullum) | Legado (cálculo em `app.py`) | `src/services/secullum_ponto.py`, colunar em `app.py`, testes próprios | ✅ FUNCIONANDO (legado) |
| 6 | Documentos (Folha/FGTS/Guias) | Legado (template em `app.py`) | Geração de holerite/FGTS em `app.py`; **Módulo 01 Documental novo** (`magnata_os/documental/modulo01/`) cobre entrada/esteira/consulta de qualquer documento, não geração de holerite em si | 🟡 EM EVOLUÇÃO (dois sistemas coexistindo por desenho) |
| 7 | Distribuição | Legado (4 rotas duplicadas) | Confirmado em `app.py`; pacote atômico Holerite+Ponto implementado recentemente (`docs/decisoes/pacote-holerite-folha-ponto.md`) | ✅ FUNCIONANDO (legado, com evolução ativa) |
| 8 | Assinaturas | Legado (formulário simples, IP/CPF) | `app.py`, ampla suíte `test_pacote_assinatura_holerite_ponto.py` (68 testes) | 🟡 EM EVOLUÇÃO — **6 testes falhando hoje em `main`**, ver §9 |
| 9 | Auditoria/Observabilidade | Parcialmente estruturado | `src/observability.py`, `test_observabilidade_fase0.py`; histórico append-only real em `magnata_os/documental/modulo01/` (trigger de banco impede update/delete — migration `0003`) | 🟡 EM EVOLUÇÃO |
| 10 | Plataforma | Monólito legado + extratos em `src/` | Render + Celery + Airtable confirmados; Postgres declarado em `render.yaml` mas **não provisionado** | 🟡 EM EVOLUÇÃO |

### Módulo 01 — Documental (o único módulo novo com código substancial)

Único módulo com arquitetura de domínio isolada, testada e revisada em
múltiplas fases, todas **mescladas em `main`**:

- **Fase 1 — Entrada central:** `dominio.py`, `repositorio.py`,
  `servico_entrada.py`. Modelo `Documento` imutável, idempotência por
  SHA-256, histórico append-only. 13 testes.
- **Fase 2 — Persistência:** adapters Postgres + S3 reais (código, não
  conexão real ativa), `armazenamento.py`, `servico_entrada_persistente.py`.
- **Fase 3 — Esteira operacional:** `dominio_esteira.py`
  (`etapa_atual`/`situacao`/`motivo_bloqueio`/`proxima_acao` sempre
  separados, por princípio de `CLAUDE.md` §4), `servico_avanco_esteira.py`,
  `servico_lote.py`, `consultas_esteira.py`.
- **Fase 4 — API de consulta:** `api/` — handlers Python puros
  (`handlers.py`), contratos JSON-primitivos (`contratos.py`),
  autorização por perfil (`autorizacao.py`), filtros/paginação/ordenação
  seguros (`filtros.py`), erros sem vazamento (`erros.py`). **Nenhuma
  rota HTTP registrada ainda** — é a camada que um adapter web futuro vai
  consumir.
- **Verificado nesta sessão:** `pytest` nas 4 fases → **133/133 passed.**
- 🚫 **Fase 5 — Painel visual:** existe (`origin/feat/magnata-os-documental-modulo01-fase5-painel`,
  1 commit, 2026-07-25), **não mesclada em `main`**.

### Importação em lote (`magnata_os/documental/importacao_lote/`)

Motor de classificação/gravação de um pacote real de holerites/extratos
(competência Julho/2026), com dry-run, escritor idempotente,
versionamento lógico. **Verificado nesta sessão:** `pytest` → **134/134
passed.** Runbook de ativação real (Postgres + Airtable) está pronto e
documentado (`MAGNATA_OS_HANDOFF_ATIVACAO_JULHO2026.md`) mas **não
executado** — ver §6.

---

## 5. Integrações

| Integração | Estado real | Fonte |
|---|---|---|
| **Airtable** (base `appaCpIVj7Q97VhFy`) | ✅ sistema de registro ativo do legado (Funcionários, Clientes, Holerites, Envios, Assinaturas etc.) | `app.py`, confirmado por várias tabelas/Field IDs citados em `docs/decisoes/*.md` |
| **Secullum** (ponto) | ✅ ativo em produção | `src/ingestao_secullum.py`, `src/services/secullum_ponto.py` |
| **Gmail + Apps Script** (captura de e-mail) | ✅ ativo, com lista de remetentes confiáveis corrigida recentemente (`docs/decisoes/remetentes-dp-fiscal.md`) | `apps_script_email_intake.gs` |
| **Evolution API** (WhatsApp) | ✅ ativo no legado para envio | citado em `MAGNATA_OS_MODULOS.md` §7, uso confirmado em `app.py` |
| **SMTP** (e-mail de saída) | ✅ ativo (`_smtp_enviar_email` em `app.py`) | `app.py` |
| **PostgreSQL (Render)** | 🚫 **declarado, não provisionado.** `render.yaml` tem bloco `databases:` comentado como "NAO executado/aplicado nesta fase" | `render.yaml`, confirmado nesta sessão |
| **S3/R2** (armazenamento de binário) | 🚫 adapter de código existe (`adapters/s3_armazenamento.py`), nenhum bucket real conectado | código + ausência de credencial/config real |
| **Redis/Celery** | ✅ worker ativo em produção (`celery_app.py`, serviço `magnata-holerite-worker` no `render.yaml`) | `render.yaml`, `celery_app.py` |
| **Graphify** | 🚫 não instalado, nenhuma referência no repositório | busca nesta sessão (`grep -ri graphify` → vazio) — ver §12 |

---

## 6. Produção atual

- **Serviço web:** Flask (`app.py`) via Gunicorn, 2 workers, Render
  (`Procfile` e `render.yaml` idênticos de propósito, com comentário
  explícito no `render.yaml` alertando para nunca deixarem divergir).
- **Worker:** Celery, 2 workers, mesmo `render.yaml`.
- **Banco de metadados oficial hoje:** **Airtable** — não Postgres.
  `DATABASE_URL` está referenciado no `render.yaml` mas aponta para um
  banco (`magnata-os-db`) que o próprio arquivo documenta como **não
  provisionado** ("`plan: free` é um placeholder seguro... NÃO é uma
  recomendação para produção").
- **`app.py`:** 12.301 linhas — legado protegido (`CLAUDE.md` §7).
  Confirmado zero diferença estrutural relatada nos handoffs mais
  recentes; alterações só entram via `.magnata/app-py-authorizations/`
  (mecanismo de autorização por hash, confirmado presente:
  13 arquivos de autorização registrados, ex.:
  `pacote-holerite-ponto-entrega-real.gitblob`,
  `fuso-horario-brt-na-exibicao.gitblob`).
- **CI de governança:** ✅ **mesclado em `main`** (PR #13,
  `d616d521`), workflow `.github/workflows/magnata-governance.yml`
  ativo em `pull_request` e `push` (incl. `main`), 16 gates, fonte
  única `.magnata/patterns.sh`. Confirmado presente em `main` nesta
  sessão.
- **Lote de Julho/2026 (importação real):** dry-run reconfirmado e
  congelado (135 itens: 114 prontos, 21 em fila de exceção), canário
  selecionado, **execução real contra Postgres/Airtable ainda não
  ocorreu** — depende de gate humano de provisionamento de infra (fora
  do alcance desta sessão e desta auditoria). 🚫 PLANEJADO MAS NÃO
  EXECUTADO.

---

## 7. Decisões permanentes (confirmadas em documento ou código)

- Migração por *strangler pattern* — nunca reescrita de uma vez
  (`MAGNATA_OS_MANIFESTO.md`, `CLAUDE.md` §1).
- `etapa_atual`/`situacao`/`motivo_bloqueio`/`proxima_acao` sempre
  campos separados — **implementado**, não só documentado
  (`magnata_os/documental/modulo01/dominio_esteira.py`).
- Histórico append-only, imutável — **implementado com trigger de
  banco** (migration `0003_trigger_eventos_append_only.sql`), não só
  disciplina de código.
- Idempotência obrigatória em toda entrada — **implementada e testada**
  (hash SHA-256 em `servico_entrada.py`; dedup em `importacao_lote`).
- Arquivo original imutável, hash divergente é erro a relatar — mesmo
  princípio, mesmo módulo.
- Nomenclatura `Documento` (não "Item de Ingestão") em código novo —
  **em vigor**, confirmado: nenhuma ocorrência de "Item de Ingestão"
  como nome de classe em `magnata_os/`. O ADR que formalizaria essa
  divergência (`MAGNATA_OS_ADR_001_...md`) existe só na branch não
  mesclada (§3) — a prática já é a de `CLAUDE.md` §5, mas o registro
  formal (ADR) ainda não chegou a `main`.
- `app.py`, `render.yaml`/`Procfile`, `frontend/assets/brand/`,
  migrations aplicadas: protegidos, alteração só com autorização
  explícita — mecanismo de autorização por hash confirmado em uso real
  (`.magnata/app-py-authorizations/`, `.magnata/migration-authorizations/`).

---

## 8. Regras de negócio importantes (confirmadas)

- Pacote atômico de assinatura Holerite + Folha de Ponto: um único link
  de assinatura entrega os dois documentos juntos; whitelist de tipo
  documental da Assinatura Nativa tinha lacuna real (`HOLERITE` fora da
  lista), corrigida — 65 registros reais ficaram travados até a
  correção (`docs/decisoes/pacote-holerite-folha-ponto.md`).
- Vínculo trabalhista inativo bloqueia o pacote de assinatura antes de
  tocar no documento (`_status_funcionario_elegivel`) — **regra
  correta em intenção, código com bug real hoje** (ver §9).
- Remetentes de e-mail confiáveis (DP, Fiscal) processados sem label
  manual — lista corrigida recentemente
  (`docs/decisoes/remetentes-dp-fiscal.md`).
- Outros Documentos → Envio: aplicação **manual, um `envio_id` por vez**,
  nunca em lote, sempre com dry-run interno antes de escrever, exige
  digitar `CONFIRMAR` (`OUTROS_DOCUMENTOS_CLI.md`).
- Dados pessoais (CPF, nome, holerite real): nunca em teste, commit, log
  ou documento de exemplo — confirmado como prática seguida nos
  documentos de decisão auditados (uso de IDs de registro, nunca CPF).

---

## 9. Pendências e riscos

### 9.1 Risco ativo confirmado nesta sessão (não presunção)

**6 testes falhando em `main`, hoje, em `test_pacote_assinatura_holerite_ponto.py`**
(`test_vinculo_desligado_e_bloqueado` e 5 relacionados) — a função real
`_status_funcionario_elegivel` em `app.py` retorna o motivo
`'status_veio_inativo'`, mas o teste (e o restante do sistema, que
depende da string `'vinculo_nao_ativo'` em outros pontos) espera
`'vinculo_nao_ativo'`. **A correção já existe**, pronta, numa branch não
mesclada: `origin/fix/status-funcionario-pii` (commit
`448978d fix: restaura vinculo_nao_ativo/vinculo_indeterminado em _status_funcionario_elegivel`,
de 2026-08-17). Essa branch está **18 commits atrás de `main`** — não
foi rebaseada nem mesclada, e `main` seguiu evoluindo sem essa correção.
**Ação recomendada (decisão humana, fora do escopo desta auditoria):**
rebasear `fix/status-funcionario-pii` sobre `main` atual e abrir PR.

Confirmado por execução real de `pytest` nesta sessão: 636 passed, 6
failed (suíte completa, ambiente corrigido — ver §11 "limitação de
ambiente"). As demais 630 passam, incluindo toda a suíte de
Módulo 01/importação em lote.

### 9.2 Pendências documentais

- Fundação documental completa (`MAGNATA_OS_ARQUITETURA.md`,
  `_ENTIDADES`, `_EVENTOS`, `_CONTRATOS`, `_ESTADOS`, ADR-001,
  skills/subagentes) presa em branch não mesclada — §3, §10.
- `MAGNATA_OS_DECISOES_ENTIDADES.md`: documento não existe em `main`
  (só na branch powerpack); mesmo lá, tinha 3 decisões `PENDENTE`
  (`DEC-ENT-010/011/012`) segundo o próprio índice.
- ADR-001 (nomenclatura Item de Ingestão vs. Documento): proposta sem
  decisão vinculativa, e nem a proposta chegou a `main`.
- `magnata gate`: especificado (`docs/magnata-os/MAGNATA_OS_GATE_ESPECIFICACAO.md`),
  **não implementado** — proposta explícita, aguardando decisão.

### 9.3 Branches abertas relevantes não mescladas (mapeadas nesta sessão)

| Branch | Última alteração | Conteúdo | Risco de não agir |
|---|---|---|---|
| `feat/magnata-os-claude-powerpack` | 2026-07-30 | Fundação documental completa + skills/subagentes (§3) | Alto — documentação oficial "fantasma" |
| `feat/magnata-os-documental-modulo01-fase5-painel` | 2026-07-25 | Painel visual do Módulo 01 | Médio — trabalho pronto, parado |
| `fix/status-funcionario-pii` | 2026-08-17 | Correção da regressão do §9.1 | Alto — bug real e conhecido segue em `main` |
| `fix/adr-modulo01-http-wiring` | 2026-08-13 | Decisão de como expor a API do Módulo 01 via HTTP | Médio |
| `fix/plano-modulo01-email-captura` | 2026-08-17 | Plano de captura de e-mail para o módulo novo | Médio |
| `claude/evolution-api-instances-1s9raa` | 2026-08-17 | Trabalho em instâncias da Evolution API | 🔍 não avaliado em profundidade nesta auditoria |
| `fix/recibos-outros-documentos` | 2026-07-24 (base antiga) + commit `1027fc8` de 2026-07-23 preservando `docs/historico/` | **Correção pós-Etapa 2:** carrega a única memória de continuidade operacional do projeto (30 registros, 12/06-01/07/2026) — não é lixo, ver §0 e `central-command/`. O volume de -30.893 linhas é diff contra o `main` atual (a branch é antiga, ficou para trás), não sinal de abandono do conteúdo que ela preserva | Alto — memória real presa numa branch que parecia descartável |

### 9.4 Riscos estruturais declarados nos próprios documentos (não novidade desta sessão)

- Nenhum módulo tem autonomia de produção antes da Fase 11 do roadmap
  (regra explícita, respeitada até aqui).
- Cálculo de ponto, geração de holerite e distribuição seguem como
  lógica crítica dentro do monólito `app.py` — risco "Crítico"
  declarado no próprio `MAGNATA_OS_MODULOS.md` §12 para Ponto e
  Documentos.
- Isolamento de ambiente (prod/staging/dev) ainda incompleto no Render
  (`MAGNATA_OS_CAPACIDADES.md` §3.10).

---

## 10. Itens descartados / superados

- ❌ **`ARQUITETURA_FASE_2_DECISAO_FINAL.md`** — documento histórico
  citado pelo índice como precedente superado pela fundação atual;
  **localizado na Etapa 2** na branch `feat/magnata-os-claude-powerpack`
  (não em `main`) — lido parcialmente, é decisão pré-Manifesto sobre
  reaproveitamento de campos Airtable. Ver `central-command/DECISIONS.md`
  DEC-011 e `SUPERSEDED_DECISIONS.md` SUP-006.
- **Correção pós-Etapa 2:** `fix/recibos-outros-documentos` **não é**
  uma branch abandonada a descartar — carrega a memória de continuidade
  do projeto (§0). O que de fato pode ser candidato a fechamento é só o
  **código** dessa branch (o trabalho original sobre recibos de outros
  documentos, se já superado por `fix/outros-documentos-fila-dedup`,
  que está mesclado) — decisão ainda não tomada, e agora informada
  corretamente: fechar a branch só depois de extrair/preservar
  `docs/historico/` para um lugar versionado em `main` (ver §14).
- 🔍 Qualquer capacidade listada como "nível 9 — Autorizada para
  produção" nos documentos de capacidade **não existe** — a escala
  inteira do Magnata OS está entre níveis 2 e 8 hoje, por desenho
  (regra explícita: nível 9 exige aprovação formal, nunca automática).

---

## 11. Limitações desta auditoria (declaradas, não escondidas)

- A suíte de testes só pôde ser executada depois de corrigir uma
  dependência de ambiente (`cffi`) ausente neste container — sem isso,
  16 arquivos de teste falhavam na coleta por um `pyo3_runtime.PanicException`
  não relacionado ao código do projeto. Corrigido nesta sessão só para
  fins de verificação (instalação de pacote Python, sem alterar
  código/config do repositório).
- Não foi feita leitura linha a linha de `app.py` (12.301 linhas) —
  a avaliação de "legado operacional" para os módulos que vivem lá se
  apoia em grep, testes existentes e documentos de decisão, não em
  auditoria de segurança completa do arquivo.
- Não foi acessado Airtable, Render, Secullum, Evolution API nem
  qualquer sistema externo real nesta sessão — nada em §4-§8 vem de
  consulta ao vivo a produção; vem de código e documento versionados.
  Onde um documento (ex.: handoff de ativação) cita números vindos de
  uma consulta ao vivo de uma sessão anterior, isso está identificado
  como tal, não reconfirmado aqui.
- Branches não mescladas foram inspecionadas por `git log`/`git diff
  --stat`/`grep` direcionado — não por leitura integral de cada uma.
  `claude/evolution-api-instances-1s9raa` em particular não foi
  aprofundada.
- Não foi avaliado o conteúdo funcional exato de "Graphify" além do que
  é de conhecimento geral sobre ferramentas de grafo de
  código/arquitetura — nenhuma documentação própria do produto foi
  encontrada neste repositório. Ver §12.

---

## 12. Onde o GRAPHIFY poderia entrar (avaliação, sem instalação)

**Não instalado. Nenhuma referência a Graphify neste repositório** —
confirmado por busca nesta sessão. A avaliação abaixo é conceitual, a
partir do que a Central Command precisa, não de uma leitura da
ferramenta em si (🔍 especificações reais do Graphify precisam ser
confirmadas antes de qualquer decisão de adoção).

**Onde faria sentido, hipoteticamente:**
1. **Fonte automática do mapa de módulos/dependências real** — hoje
   `MAGNATA_OS_MODULOS.md` e `MAGNATA_OS_MATRIZ_ARQUITETURAL.md` são
   mantidos manualmente e já mostram sinais de desatualização (§3, §4).
   Uma ferramenta que extrai grafo de import/dependência direto do
   código (`magnata_os/`, `src/`, `app.py`) geraria a "foto real" para
   comparar contra o que os documentos afirmam — exatamente o tipo de
   verificação que este documento fez manualmente.
2. **Detecção de acoplamento indevido** — verificar mecanicamente a
   regra "domínio não importa Flask/driver/Airtable" (`CLAUDE.md` §3),
   hoje confirmada por `grep` manual nesta auditoria.
3. **Alimentar a seção "Fonte de verdade" deste documento** — se o
   Graphify (ou equivalente) rodar como parte do CI de governança já
   existente (`.github/workflows/magnata-governance.yml`), a Central
   Command poderia ter um bloco gerado automaticamente (grafo de
   módulos, lista de imports proibidos violados) em vez de depender de
   auditoria manual a cada consolidação.
4. **Não substitui** a auditoria de branches não mescladas, de
   documentos fantasmas, nem de decisões de negócio — isso é
   raciocínio sobre histórico Git e texto, não estrutura de código.

**Antes de instalar (fora do escopo desta etapa, por instrução
explícita):** confirmar o que o Graphify realmente extrai (import graph?
schema de banco? chamadas HTTP?), se roda local/read-only (compatível
com `CLAUDE.md` §6 — nenhuma ação externa de produção), e onde o
resultado seria versionado (arquivo gerado no repo vs. serviço externo
— este último exigiria gate de "escrita externa" por §6).

---

## 13. Organograma técnico — Central Command sobre núcleos de negócio

**Nota de enquadramento, registrada explicitamente:** a lista de
núcleos abaixo (Documental, RH, Financeiro, Contábil/Fiscal, Comercial,
Operações, Marketing, Diretoria) é o recorte de **negócio** pedido
nesta etapa. Ela **não é idêntica** ao recorte de **10 módulos
funcionais** já documentado em `MAGNATA_OS_MODULOS.md` (Ingestão,
Classificação, Cadastro, RH, Ponto, Documentos, Distribuição,
Assinaturas, Auditoria, Plataforma). Os dois recortes se sobrepõem
parcialmente. Esta seção é um **mapeamento desta auditoria**, não uma
nova arquitetura aprovada — reconciliar os dois vocabulários (se for o
caso) é decisão arquitetural futura, não algo que este documento decide
sozinho.

```
                     ┌───────────────────────────┐
                     │  CENTRAL COMMAND /         │
                     │  ORQUESTRADOR              │
                     │  🚫 não existe como sistema │
                     │  em execução — este         │
                     │  documento é seu primeiro   │
                     │  artefato (memória mestre)  │
                     └──────────────┬─────────────┘
        ┌───────────┬───────────┬───┴───────┬───────────┬───────────┬───────────┐
        ▼           ▼           ▼           ▼           ▼           ▼           ▼
   Documental      RH      Financeiro  Contábil/    Comercial   Operações   Marketing   Diretoria
                                        Fiscal
```

| Núcleo | Existe hoje | Funcionando | Sendo construído | Só planejado |
|---|---|---|---|---|
| **Documental** | ✅ Sim, em dois sistemas: legado (`app.py` — split/geração de holerite, assinatura, distribuição) e Módulo 01 novo (`magnata_os/documental/`) | ✅ Legado, em produção real, e Fases 1-4 do Módulo 01 (133/133 testes) | 🟡 Fase 5 (painel visual, branch aberta); wiring HTTP do Módulo 01 (`fix/adr-modulo01-http-wiring`, branch aberta) | 🚫 Classificação automática de documentos (Módulo 2 da doc de módulos) |
| **RH** | ✅ Sim, legado (`app.py`: Kit Admissão, vínculo trabalhista) | ✅ Admissão manual, 31 testes de identidade passando | 🔍 Não identificado código de "Módulo RH" isolado além do legado | 🚫 Workflow de admissão/encerramento como módulo próprio (`MAGNATA_OS_MODULOS.md` #4) |
| **Financeiro** | 🔍 Não identificado como conceito próprio no código nem na documentação de módulos | 🔍 Nenhuma evidência de contas a pagar/receber, faturamento, fluxo de caixa no repositório | — | 🚫 Não documentado como módulo em nenhum dos documentos fundacionais auditados — gap a esclarecer com a Direção antes de tratar como módulo real |
| **Contábil/Fiscal** | ✅ Sim, parcial: intake de e-mail de remetentes DP/Fiscal, rotas com segurança dedicada (`test_seguranca_rotas_dp_fiscal.py`), tabela "Contabilidade Mensal" no Airtable | ✅ Captura de e-mail e roteamento para o fluxo de holerite/extrato | 🟡 Correção recente de remetente fiscal (`docs/decisoes/remetentes-dp-fiscal.md`) | 🚫 Nenhum módulo fiscal formal (apuração de imposto, guias fiscais) documentado |
| **Comercial** | 🔍 Nenhuma evidência encontrada no repositório | — | — | 🚫 Não aparece em nenhum documento fundacional auditado |
| **Operações** | ✅ Sim, como consequência dos módulos Ponto/Distribuição/Assinatura, não como núcleo isolado | ✅ Ponto (Secullum), distribuição (4 canais legado + pacote atômico novo), Celery worker | 🟡 Unificação de canais de distribuição é item de roadmap (Fase 9, não iniciada como módulo) | 🚫 "Módulo Operações" como entidade própria não existe nos documentos |
| **Marketing** | 🔍 Nenhuma evidência encontrada no repositório | — | — | 🚫 Não aparece em nenhum documento fundacional auditado |
| **Diretoria** | 🔍 Nenhum painel executivo/BI encontrado | — | 🟡 Painel visual do Módulo 01 (não mesclado) é o artefato mais próximo, mas é operacional (esteira documental), não executivo | 🚫 "Painel operacional" citado como capacidade em `MAGNATA_OS_CAPACIDADES.md` §3.9, maturidade 2 (identificada, sem implementação) |

**Leitura honesta desta tabela:** dos 8 núcleos pedidos, só
**Documental** tem arquitetura nova real, testada e documentada por
fases. **RH**, **Contábil/Fiscal** e **Operações** têm legado
funcionando em produção, mas nenhum módulo novo isolado dedicado a
eles ainda. **Financeiro**, **Comercial**, **Marketing** e
**Diretoria/BI** não têm evidência de existir no código ou na
documentação técnica auditada — antes de planejar arquitetura para
eles, vale confirmar com a Direção se são núcleos que já operam fora
deste repositório (outra ferramenta, processo manual) ou se são
aspiracionais para o Magnata OS.

---

## 14. Próximos passos (sugeridos, não decididos — todos exigem gate humano por `CLAUDE.md` §9/§12-I)

Em ordem de risco/impacto, não de preferência:

1. **Preservar `docs/historico/` em `main`** (achado da Etapa 2, §0) —
   antes de qualquer decisão sobre fechar/limpar
   `fix/recibos-outros-documentos`, extrair e mesclar esses 30
   registros (ou o commit inteiro) para um lugar versionado em `main`.
   É a memória de continuidade mais concreta que existe do projeto e
   hoje está a um `git branch -D` de distância de ficar só no reflog.
2. **Decidir o destino de `feat/magnata-os-claude-powerpack`** (§3, §9.3)
   — é a lacuna mais estrutural encontrada: a fundação documental que
   `CLAUDE.md` cita como existente não está em `main`. Precisa de
   decisão humana: reconciliar com os 70 commits que `main` já tem à
   frente (provável trabalho de merge não trivial, não um simples
   fast-forward), ou reconstruir só o que ainda é válido. A Etapa 2
   (`central-command/ARCHITECTURE.md`) já reconstruiu a linha do
   tempo completa de como e por que essa branch ficou presa.
3. **Ler por conteúdo os 9 documentos fundacionais ainda não extraídos**
   (`central-command/COBERTURA.md` §7, item 1) — é o que falta
   para a Central Command deixar de depender de "existência confirmada"
   e passar a ter as ~29 decisões de `MAGNATA_OS_DECISOES_ENTIDADES.md`
   e o restante da fundação de fato incorporados aos registros.
4. **Corrigir a regressão confirmada** (§9.1) — rebasear
   `fix/status-funcionario-pii` sobre `main` e abrir PR; é uma correção
   pequena, isolada, com causa raiz já identificada nesta auditoria.
5. **Decidir sobre as branches órfãs** (§9.3) — painel visual do
   Módulo 01, wiring HTTP, plano de captura de e-mail: todas prontas ou
   quase prontas, todas paradas.
6. **Esclarecer os núcleos sem evidência de código** (Financeiro,
   Comercial, Marketing, Diretoria/BI) — decisão de negócio, não
   técnica: são escopo futuro do Magnata OS ou vivem fora dele?
7. **Avaliar formalmente o Graphify** (§12) — depois de entender a
   ferramenta de verdade, decidir se ela é a fonte automática do mapa
   de módulos/dependências, mantendo a Central Command atualizada sem
   auditoria manual a cada consolidação.
8. Só depois disso: retomar o roadmap de 11 fases a partir da Fase 1
   (Observabilidade), que os próprios documentos de módulo já apontam
   como caminho recomendado.

**Sobre a pergunta de fechamento desta Etapa 2 — "a memória está
completa?":** não. Ver a resposta objetiva e o que falta especificamente
em `central-command/COBERTURA.md` (última seção).

---

**Fim do documento. Nenhum código foi alterado, nenhum commit além
deste documento foi feito, nenhuma integração real (Airtable, Render,
Secullum, e-mail, WhatsApp) foi acessada nesta auditoria.**
