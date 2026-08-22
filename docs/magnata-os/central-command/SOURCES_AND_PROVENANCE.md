# SOURCES_AND_PROVENANCE — Magnata OS

Índice de toda fonte histórica localizável a partir deste repositório
Git, com o que foi de fato auditado nesta etapa (Etapa 2 — Auditoria de
Memória e Proveniência, 2026-08-21) contra o que só foi localizado/citado.

**Regra de leitura:** "auditado" aqui significa lido nesta sessão ou na
sessão da Etapa 1 imediatamente anterior (mesma auditoria contínua).
Uma fonte "localizada, não auditada" existe e é rastreável, mas seu
conteúdo não foi extraído para os registros (`DECISIONS.md`,
`DIRECTIVES.md` etc.) — citá-la aqui não é o mesmo que tê-la processado.

---

## 1. Documentação institucional em `main`

| Fonte | Local | Auditado? |
|---|---|---|
| `CLAUDE.md` (raiz + 3 escopados) | `main` | ✅ sim (Etapa 1 e 2) |
| `MAGNATA_OS_MANIFESTO.md` | `main` | ✅ sim |
| `docs/magnata-os/README.md` + `CAPACIDADES`/`MODULOS`/`ROADMAP`/`MATRIZ_ARQUITETURAL`/`GATE_ESPECIFICACAO`/`HANDOFF_ATIVACAO_JULHO2026`/`CI_GOVERNANCA`/`HOOKS_LOCAIS` | `main`, `docs/magnata-os/` | ✅ sim |
| `docs/decisoes/pacote-holerite-folha-ponto.md`, `remetentes-dp-fiscal.md` | `main`, `docs/decisoes/` | ✅ sim |
| `MAGNATA_OS_DOCUMENTAL_MODULO01.md` + `_FASE2`/`_FASE3`/`_FASE4` | `main` | ✅ sim |
| `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md` (relatório CI) | `main` | ✅ sim |
| `OUTROS_DOCUMENTOS_CLI.md`, `MAGNATA_OS_IDENTIDADE_VISUAL.md`, `MAGNATA_OS_MODULO_01_FASE_0_OBSERVABILIDADE.md`, `MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1.md` | `main` | 🟡 lido por título/trecho, não integralmente nesta etapa |

## 2. Memória de continuidade — `docs/historico/` (achado central da Etapa 2)

**Só existe na branch `origin/fix/recibos-outros-documentos`, nunca
mesclada em `main`.** 30 arquivos + `MEMORY.md` (índice), cobrindo
12/06/2026 a 01/07/2026 — commit único
`1027fc8 docs: preserva historico de memoria do projeto (12/06 a 22/07/2026)`,
autor `Magnata Holerite Bot`, 2026-07-23. **Auditado integralmente
nesta etapa** — todos os 30 arquivos lidos, extraídos para
`DIRECTIVES.md`, `ACTIONS_COMPLETED.md`, `PENDING.md`,
`SUPERSEDED_DECISIONS.md`. Ver lista completa em `MEMORY.md` (mesma
branch) e a extração em `ACTIONS_COMPLETED.md` §histórico.

## 3. Fundação documental "fantasma" — `feat/magnata-os-claude-powerpack`

Branch aberta 2026-07-30, nunca mesclada (ver `CENTRAL_COMMAND_MAGNATA_OS.md`
§3, §9.3). Conteúdo auditado nesta etapa, além do que já foi auditado
na Etapa 1:

| Documento | Auditado nesta etapa? |
|---|---|
| `MAGNATA_AI_ENGINEERING_POWERPACK_INVENTARIO.md` | ✅ sim, integralmente |
| `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA1.md` | ✅ sim (seções 1-7 + parecer) |
| `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA4_DIVERGENCIAS_REVISAO.md` | ✅ sim, integralmente |
| `ARQUITETURA_FASE_2_DECISAO_FINAL.md` (histórico, pré-Manifesto, 2026-07-20) | 🟡 lido parcialmente (primeiras ~60 linhas) |
| `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA2.md`, `_ETAPA3.md`, `_ETAPA4.md`, `_ETAPA5.md`, `_ETAPA5_PARECERES.md`, `MAGNATA_ETAPA5B_VALIDACAO_MANUAL.md` | 🟡 só cabeçalhos/seções (`grep "^#"`), não lidos integralmente |
| `MAGNATA_OS_ARQUITETURA.md`, `_ENTIDADES`, `_DECISOES_ENTIDADES`, `_EVENTOS`, `_CONTRATOS`, `_ESTADOS`, `_ADR_001_...`, `_MODULO_01_INGESTAO`, `_MODULO_01_DECISOES_IMPLEMENTACAO` | ❌ **não lidos nesta etapa** — confirmados existentes (Etapa 1), conteúdo ainda não extraído para os registros. Maior lacuna conhecida desta auditoria, ver `COBERTURA.md` |
| `.claude/skills/*.md`, `.claude/agents/*.md`, `.claude/MATRIX_DE_RESPONSABILIDADES.md` | ❌ não lidos nesta etapa, só confirmados existentes |

## 4. Outras branches não mescladas com conteúdo de decisão

| Branch | Documento | Auditado? |
|---|---|---|
| `fix/adr-modulo01-http-wiring` | `docs/decisoes/modulo01-fiacao-http.md` | ✅ sim, integralmente |
| `claude/evolution-api-instances-1s9raa` (= `fix/plano-modulo01-email-captura`) | `docs/decisoes/plano-consolidacao-ingestao-distribuicao.md` | ✅ sim, integralmente |
| `feat/magnata-os-documental-modulo01-fase5-painel` | `MAGNATA_OS_DOCUMENTAL_MODULO01_FASE5.md` + código do painel | ❌ não lido nesta etapa |
| `fix/status-funcionario-pii` | diff de `app.py`/teste | 🟡 só o diff relevante ao bug já reportado na Etapa 1 |
| Demais 20+ branches `fix/*` de produção (histórico completo em `CENTRAL_COMMAND_MAGNATA_OS.md` §9.3) | commits individuais | 🟡 só título de commit e status merged/não-merged, não diff completo |

## 5. Código e configuração

| Fonte | Auditado? |
|---|---|
| `magnata_os/documental/{modulo01,importacao_lote}/` | ✅ sim (Etapa 1) — domínio, contratos, testes lidos/executados |
| `app.py` (12.301 linhas) | 🟡 auditado por `grep`, testes e documentos de decisão — **nunca lido linha a linha** |
| `src/`, `scripts/` | 🟡 lido por listagem/grep, não integralmente |
| `render.yaml`, `Procfile`, `requirements.txt`, `.github/workflows/`, `.magnata/patterns.sh` | ✅ sim |
| `.magnata/app-py-authorizations/*.gitblob`, `.magnata/migration-authorizations/*.gitblob` | 🟡 listados por nome, conteúdo binário não decodificado |
| Suíte de testes (`test_*.py`, 302 arquivos coletáveis) | ✅ executada integralmente nesta sessão (Etapa 1): 636 passed / 6 failed |

## 6. Histórico de commits/PRs

- 150+ commits em `main`, auditados por `git log --oneline`/título e
  `git log --diff-filter` direcionado — **não** por leitura de corpo de
  commit + diff completo de cada um.
- PRs: só inferidos pelos commits de merge (`Merge pull request #NN`)
  presentes no log — **nenhum PR foi lido via GitHub** (descrição,
  comentários, revisão) nesta auditoria; esta sessão não tem acesso
  configurado ao GitHub MCP para este repositório além do que o Git
  local expõe.

## 7. Fontes citadas, mas **inacessíveis a esta sessão** (confirmado, não presumido)

- **`RELATORIO_SCHEMA_AIRTABLE_COMPLETO.md`** — citado em
  `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA1.md` §6 item 4 como existente
  só na máquina Windows local do usuário (`C:\Users\Lenovo\...`),
  nunca commitado. Busca em todas as branches deste repositório: **zero
  resultado.** Contém "volume de IDs operacionais de produção" —
  inacessível e potencialmente ainda em risco de perda (não há como
  esta sessão confirmar se ainda existe).
- **`ENTREGA_FASES_A_B_C_D.md`** e o cluster de documentos
  `FASE_A..D.md`, citados no mesmo item do mesmo relatório como
  pré-existentes e nunca versionados (uma iniciativa anterior ao
  Magnata OS). Busca em todas as branches: **zero resultado.**
  Inacessível.
- **Transcrições brutas de conversas anteriores** (`.jsonl` em
  `~/.claude/projects/` na máquina Windows do usuário, citadas em
  `MAGNATA_AI_ENGINEERING_POWERPACK_INVENTARIO.md` §1 como existentes)
  — **este ambiente é um container remoto isolado, sem acesso a esse
  disco.** Nenhuma conversa histórica bruta é, nem nunca foi, acessível
  a partir deste repositório Git. Tudo que esta auditoria conhece de
  "conversas antigas" vem exclusivamente do que foi **escrito e
  commitado** como documento (memória de continuidade, relatório de
  fase, decisão) — nunca da conversa em si.
- **Airtable, Render, Secullum, Evolution API, Gmail/Apps Script reais**
  — não acessados nesta auditoria (regra `CLAUDE.md` §6). Qualquer
  número/estado desses sistemas citado nos documentos históricos (ex.:
  "1.140 registros travados", "13 bloqueados por limite de plano") é o
  que foi lido **quando aquele documento foi escrito** — não uma
  confirmação de agora. Ver `PENDING.md` para o tratamento disso.

## 8. Como interpretar "cobertura" a partir desta tabela

Ver `COBERTURA.md` para o relatório consolidado. Resumo aqui: as
maiores lacunas conhecidas são (1) os 9 documentos fundacionais do
Magnata OS na branch powerpack ainda não tiveram o conteúdo extraído
para os registros estruturados (só confirmada a existência), e (2)
qualquer coisa que só existiu como conversa e nunca virou documento
está, por definição, fora do alcance de qualquer auditoria futura —
não só desta.
