# Central Command — índice

**Entrada única da memória consolidada do Magnata OS.**
Documento mestre: [`../MAGNATA_OS_CENTRAL_COMMAND.md`](../MAGNATA_OS_CENTRAL_COMMAND.md)

A Central Command **não** substitui `CLAUDE.md` nem
[`../README.md`](../README.md) — é camada de consolidação por cima
deles. A escala de precedência continua sendo a de `CLAUDE.md` §2.

**Princípio:** este diretório aponta para as fontes, não as copia.
Cadeia: **fonte → decisão → implementação → PR/commit → estado atual.**

---

## Onde procurar cada coisa

| Pergunta | Arquivo |
|---|---|
| Onde o projeto está hoje? | mestre §1-§6 · [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| O que já foi construído? | [`ACTIONS_COMPLETED.md`](ACTIONS_COMPLETED.md) — 35 ações |
| O que foi decidido, e por quê? | [`DECISIONS.md`](DECISIONS.md) · [`FOUNDATION.md`](FOUNDATION.md) §2-§4 |
| Que ordens a Direção deu? | [`DIRECTIVES.md`](DIRECTIVES.md) — 11 diretivas |
| O que mudou de ideia no caminho? | [`SUPERSEDED_DECISIONS.md`](SUPERSEDED_DECISIONS.md) |
| O que está em andamento? | [`WORK_IN_PROGRESS.md`](WORK_IN_PROGRESS.md) — 8 frentes |
| O que está parado esperando? | [`PENDING.md`](PENDING.md) — 19 pendências |
| Que PRs e branches ainda carregam trabalho útil? | [`PRS_AND_BRANCHES.md`](PRS_AND_BRANCHES.md) |
| O que a fundação documental diz? | [`FOUNDATION.md`](FOUNDATION.md) |
| A Macro 6A foi toda incorporada? | [`MACRO_6A.md`](MACRO_6A.md) |
| O que pode dar errado, em que ordem? | [`RISKS.md`](RISKS.md) — 12 riscos |
| O que fazer em seguida? | [`NEXT_ACTIONS.md`](NEXT_ACTIONS.md) — 15 ações |
| De onde veio cada informação? | [`SOURCES_AND_PROVENANCE.md`](SOURCES_AND_PROVENANCE.md) |
| O que ainda não sabemos? | [`COBERTURA.md`](COBERTURA.md) |
| O que existe mas não está no Git, e por quê? | [`FORA_DO_GIT.md`](FORA_DO_GIT.md) |
| A Fase 5 pode ser recuperada? | [`FASE5_AUDITORIA.md`](FASE5_AUDITORIA.md) |
| A Central Command está desatualizada? | `scripts/ci/central_command_sensor.py` — compara com [`ESTADO.json`](ESTADO.json) |
| Como será o banco próprio? | [`BANCO_PROPRIO_MODELO.md`](BANCO_PROPRIO_MODELO.md) |
| A arquitetura do código mudou? | `scripts/ci/graphify_snapshot.py` — só arestas EXTRACTED |
| Devemos adotar o Graphify? | [`GRAPHIFY.md`](GRAPHIFY.md) — POC executada |
| Como sair do Airtable? | [`AIRTABLE_DESACOPLAMENTO.md`](AIRTABLE_DESACOPLAMENTO.md) — 4 fases |
| Onde guardar dado sensível? | [`MEMORIA_SENSIVEL.md`](MEMORIA_SENSIVEL.md) |
| Qual fonte vence qual, em caso de conflito? | [`ORQUESTRADOR.md`](ORQUESTRADOR.md) §6 |
| Que núcleos de negócio existem de fato? | [`ORQUESTRADOR.md`](ORQUESTRADOR.md) §1 |
| Qual camada é verdade sobre o quê? | [`ORQUESTRADOR.md`](ORQUESTRADOR.md) §3 |
| Qual a memória operacional de jun-jul/2026? | [`HISTORICO.md`](HISTORICO.md) — 30 registros, livre de PII |
| O que está em produção? | mestre §6 · [`RISKS.md`](RISKS.md) |
| Quais integrações existem? | mestre §5 |
| Quais módulos existem? | mestre §4 (10 módulos) e §13 (8 núcleos de negócio) |

---

## Legenda de status

✅ FUNCIONANDO/CONFIRMADO · 🟡 EM EVOLUÇÃO · ⚠️ PENDENTE ·
❌ DESCARTADO/SUPERADO · 🔍 PRECISA SER VALIDADO ·
🚫 PLANEJADO MAS NÃO EXECUTADO

**Distinções que nunca se colapsam:** discutido ≠ autorizado ≠
implementado ≠ testado ≠ integrado ≠ implantado ≠ funcionando em
produção.

---

## Linhagem

| Etapa | Data | O que fez | Origem |
|---|---|---|---|
| 1 | 2026-08-21 | Auditoria técnica: estado real, módulos, integrações, produção | `ea95ab6` |
| 2 | 2026-08-21 | Memória e proveniência: `docs/historico/`, decisões, diretivas, superadas | `27d12b1` |
| 3 | 2026-08-22 | Conteúdo da fundação extraído · lacuna temporal fechada · duas linhas de Central Command unificadas · PRs/branches inventariados · Macro 6A reconciliada · riscos priorizados | `26b9754` |
| 4 | 2026-08-22 | **Fundação documental resgatada para `main`** (10 documentos + 8 relatórios, com proveniência e notas de reconciliação) · memória histórica preservada como conhecimento livre de PII · 13 referências quebradas corrigidas · PRs reclassificados por função | esta branch |
| 5 | 2026-08-22 | PR #31 aberto · diff auditado · CI 15/15 · suíte idêntica ao baseline · fontes fora do Git registradas · núcleos classificados por evidência · requisito de camada de memória segura registrado | esta branch |
| 8 | 2026-08-22 | **PRs #33, #34 e #35 MESCLADOS — main = `75dd8fc`, suíte 642/0, CI de testes ATIVO** · sensor de arquitetura (1,42 MB → 32 KB) · modelo do banco próprio com temporalidade · proposta mínima de ALLOWED_PATHS | esta branch |
| 7 | 2026-08-22 | **PRs #31 e #32 mesclados** · correção do vínculo (PR #33, 642/0) · CI de testes (PR #34) · Fase 5 auditada · **primeiro sensor de atualização automática** · integração do Graphify desenhada | esta branch |
| 6 | 2026-08-22 | **PR #31 MESCLADO — `main` = `9f8a53f`** · falhas classificadas por execução (642 passando com a correção) · produção não verificável (rede) · Graphify avaliado com POC · desacoplamento do Airtable mapeado (31 tabelas) · memória sensível especificada · arbitragem de fontes definida | esta branch |

As Etapas 1-2 nasceram em `claude/magnata-central-command-0n0713`, em
caminhos que os gates do repositório não autorizam. A Etapa 3 moveu tudo
para caminhos conformes **sem alterar o texto** e sem apagar a branch de
origem — ver mestre §0-B.2.

---

## Regra de manutenção

Este conjunto **fica desatualizado no minuto em que o código muda.**
Deve ser regenerado por auditoria, nunca editado de memória.

Append-only: uma etapa nova acrescenta e corrige explicitamente onde
errou; nunca reescreve o texto de uma etapa anterior. Correção de fato
entra como linha de correção declarada, não como edição silenciosa.
