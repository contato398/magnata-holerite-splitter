# Central Command — índice

**Entrada única da memória consolidada do Magnata OS.**
Documento mestre: [`../MAGNATA_OS_CENTRAL_COMMAND.md`](../MAGNATA_OS_CENTRAL_COMMAND.md)

A Central Command **não** substitui `CLAUDE.md` nem
[`../README.md`](../README.md) — é camada de consolidação por cima
deles. A escala de precedência continua sendo a de `CLAUDE.md` §2.

**Princípio:** este diretório aponta para as fontes, não as copia.
Cadeia: **fonte → decisão → implementação → PR/commit → estado atual.**

**Regra explícita (Etapa 13): nunca carregar todas as fontes por
padrão.** Este índice existe para que uma sessão leia só a linha que
responde a pergunta que ela tem — não o documento inteiro, e nunca as
30 fontes de uma vez. Roteamento por categoria, antes da tabela
detalhada abaixo:

| Categoria | Onde vai |
|---|---|
| **PROJECT STATUS** | `HANDOFF.md` (bootstrap) → `ESTADO.json` (fato) |
| **CODE** | `ARQUITETURA_SNAPSHOT.json` (Graphify, snapshot já gerado) → só então o arquivo específico |
| **GIT / PR / CI** | GitHub ao vivo (`LIVE_STATE` — nunca herdar número de sessão anterior) |
| **DECISIONS** | `DECISIONS.md` / `DIRECTIVES.md` (documento temático, `HUMAN_DECISION`) |
| **HISTORY** | `HISTORICO.md` — só sob demanda, nunca por padrão |
| **AIRTABLE** | Consulta ao vivo, read-only, só quando a tarefa exigir dado operacional real |
| **PRODUCTION** | `RISKS.md` + sensor específico — hoje não verificável desta sessão |

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
| A Central Command está desatualizada? | `scripts/ci/central_command_sensor.py` — compara com [`ESTADO.json`](ESTADO.json), inclui `graphify_snapshot_status` e `session_handoff_freshness` (Etapa 13) |
| Quanto custa ler a Central Command? O bootstrap está caro? | `scripts/ci/medir_contexto.py` — TIER 0/1/2 + `status_contexto` (`NORMAL`/`ATENCAO`/`TROCAR_SESSAO`), Etapa 13 |
| O Orquestrador roda sozinho, sem sessão? | Sim — `.github/workflows/orquestrador-sensor.yml` (cron 6h) + `magnata_os/orquestrador/`. Ver correção declarada em [`HANDOFF.md`](HANDOFF.md) §1 |
| Como será o banco próprio? | [`BANCO_PROPRIO_MODELO.md`](BANCO_PROPRIO_MODELO.md) |
| A arquitetura do código mudou? | `scripts/ci/graphify_snapshot.py` — só arestas EXTRACTED |
| Devemos adotar o Graphify? | [`GRAPHIFY.md`](GRAPHIFY.md) — POC executada |
| Como sair do Airtable? | [`AIRTABLE_DESACOPLAMENTO.md`](AIRTABLE_DESACOPLAMENTO.md) — 4 fases |
| Que regra só existe dentro do Airtable? | [`AIRTABLE_LOGICA_OCULTA.md`](AIRTABLE_LOGICA_OCULTA.md) — 13 automações · ANEXO A: scripts e views · ANEXO B: `480`, Make.com e o que a API não alcança |
| Onde guardar dado sensível? | [`MEMORIA_SENSIVEL.md`](MEMORIA_SENSIVEL.md) |
| Onde ainda existe PII, e como sair? | [`PII_HISTORICO_PLANO.md`](PII_HISTORICO_PLANO.md) — 3 opções com impacto |
| A Macro 6A pode ser abandonada? | [`MACRO_6A_RECONCILIACAO.md`](MACRO_6A_RECONCILIACAO.md) |
| **Sou uma sessão nova. Por onde começo?** | **[`HANDOFF.md`](HANDOFF.md)** |
| Que erros já cometemos e não devem se repetir? | [`MACRO_6A_RECONCILIACAO.md`](MACRO_6A_RECONCILIACAO.md) §4 |
| Qual fonte vence qual, em caso de conflito? | [`ORQUESTRADOR.md`](ORQUESTRADOR.md) §6 |
| Que núcleos de negócio existem de fato? | [`ORQUESTRADOR.md`](ORQUESTRADOR.md) §1 |
| Qual camada é verdade sobre o quê? | [`ORQUESTRADOR.md`](ORQUESTRADOR.md) §3 |
| Qual a memória operacional de jun-jul/2026? | [`HISTORICO.md`](HISTORICO.md) — 30 registros, livre de PII |
| O que está em produção? | mestre §6 · [`RISKS.md`](RISKS.md) |
| Quais integrações existem? | mestre §5 |
| Quais módulos existem? | mestre §4 (10 módulos) e §13 (8 núcleos de negócio) |
| O que pode ser sobrescrito por um sensor, e o que só decisão humana altera? | [`TAXONOMIA_MEMORIA.md`](TAXONOMIA_MEMORIA.md) — 6 categorias |
| O que age sozinho, o que propõe, o que exige gate? | [`MATRIZ_AUTONOMIA.md`](MATRIZ_AUTONOMIA.md) — 6 níveis, mapeados contra casos reais |
| Como uma fonte externa vira estado do domínio? | [`ARQUITETURA_EVENTOS.md`](ARQUITETURA_EVENTOS.md) — 1 caso real completo (`email_captura.py`) |
| O Graphify já foi rodado sobre o repositório inteiro (com `app.py`)? | [`GRAPHIFY.md`](GRAPHIFY.md) §8 — sim, zero violação de acoplamento detectada |

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
| 6 | 2026-08-22 | **PR #31 MESCLADO — `main` = `9f8a53f`** · falhas classificadas por execução (642 passando com a correção) · produção não verificável (rede) · Graphify avaliado com POC · desacoplamento do Airtable mapeado (31 tabelas) · memória sensível especificada · arbitragem de fontes definida | esta branch |
| 7 | 2026-08-22 | **PRs #31 e #32 mesclados** · correção do vínculo (PR #33, 642/0) · CI de testes (PR #34) · Fase 5 auditada · **primeiro sensor de atualização automática** · integração do Graphify desenhada | esta branch |
| 8 | 2026-08-22 | **PRs #33, #34 e #35 MESCLADOS — main = `75dd8fc`, suíte 642/0, CI de testes ATIVO** · sensor de arquitetura (1,42 MB → 32 KB) · modelo do banco próprio com temporalidade · proposta mínima de ALLOWED_PATHS | esta branch |
| 9 | 2026-08-22 | **PR #36 mesclado · PR #20 fechado como superado** · lógica oculta do Airtable inventariada (RSK-014 fechado) · modelo do banco próprio · **72% de `Folha de Ponto` é calculado dentro do Airtable** | mestre §0-G |
| 10 | 2026-08-22 | **PR #37 MESCLADO — `main` = `a74cd1c`, suíte 642/0** · #38 auditado adversarialmente e **NÃO mesclado** (gate humano) · 2 `customScript` e 7 views lidos · Make.com ativo descoberto · riscos AT-11..AT-16 | mestre §0-H |
| 11 | 2026-08-23 | **PRs #39, #40 e #38 MESCLADOS — `main` = `007a4e5`, suíte 649/0** · PII removida da árvore (inclusive o nome real que o #38 deixou) · **40 de 42 branches ainda contaminadas** · `Automation 1` resolvida (script vazio) · `480` não existe no código · Make.com classificado com 4 opções · sensor corrigido (PR #41) · Macro 6A reconciliada · handoff produzido | mestre §0-I |
| 12 | 2026-08-23 | **PR #41 revalidado e MESCLADO — `main` = `98e32d2`** · **PR #22 (adapter de e-mail) auditado adversarialmente, 3 lacunas de teste fechadas, rebaseado e MESCLADO — `main` = `a18d4b2`** · Central Command reconciliada em PR documental próprio (`main` = `1409454`) · **Graphify rodado sobre o repositório inteiro (com `app.py`)** — zero violação de `CLAUDE.md` §3, comparação entre execuções provada · taxonomia da memória formalizada (`TAXONOMIA_MEMORIA.md`) · matriz de autonomia formalizada e mapeada contra casos reais (`MATRIZ_AUTONOMIA.md`) · arquitetura de eventos formalizada (`ARQUITETURA_EVENTOS.md`) · produção reconfirmada não verificável (rede bloqueada) · lacuna de disparo automático (sem sessão no meio) registrada explicitamente, não resolvida | esta branch |
| 13 | 2026-08-24 | **PRs #45, #46, #47 MESCLADOS (fora desta sessão) — `main` = `76b0046`** — núcleo executável do Orquestrador + gatilho automático via GitHub Actions, fechando a lacuna que a Etapa 12 registrou como aberta · **correção declarada**: `ORQUESTRADOR.md` §6.2 e `MATRIZ_AUTONOMIA.md` §4 ainda descrevem essa lacuna como aberta — texto não reconciliado, só apontado em `HANDOFF.md` §1 · missão de contexto progressivo: `scripts/ci/medir_contexto.py` (TIER 0/1/2, alerta NORMAL/ATENCAO/TROCAR_SESSAO) integrado a `central_command_sensor.py` e, por herança, ao AUTO_FACT do Orquestrador (`ESTADO.json['contexto']`) — testado ponta a ponta · `HANDOFF.md` ganhou protocolo SESSION_START/END (§0) · `INDEX.md` ganhou roteamento por categoria | branch `fix/contexto-progressivo` |

As Etapas 1-2 nasceram em `claude/magnata-central-command-0n0713`, em
caminhos que os gates do repositório não autorizam. A Etapa 3 moveu tudo
para caminhos conformes **sem alterar o texto** e sem apagar a branch de
origem — ver mestre §0-B.2.

**Correções declaradas na Etapa 10** (nenhum texto de etapa anterior foi
reescrito):

1. As Etapas 6, 7 e 8 estavam listadas fora de ordem numérica (8, 7, 6).
   As linhas foram **reordenadas, não alteradas** — cada palavra é a
   original.
2. A **Etapa 9 nunca foi registrada** nesta tabela nem no mestre quando
   aconteceu. Fica registrada agora, com a lacuna declarada em §0-G.
3. `BANCO_PROPRIO_MODELO.md` traz no cabeçalho "Etapa 8"; é **Etapa 9**.
   Corrigido por declaração aqui e em §0-G.3 — o cabeçalho original
   permanece como está.

**Correções declaradas na Etapa 11:**

4. A varredura de PII em branches acusou **42 de 42** contaminadas,
   incluindo `main`. Errado: o heurístico de nome próprio capturou a
   declaração de variável `TEXTO_CARTAO_PONTO_REAL`. O número é **40 de
   42**, e `main` está limpa — ver `PII_HISTORICO_PLANO.md` §1.1.
5. O mestre §0-H.4 registrou que a API do Airtable *"não devolveu o corpo"*
   de `Automation 1`. **Superado por evidência:** a API devolve corpo de
   script; esse nó simplesmente não tem um — ver ANEXO B §B.1.
6. O ANEXO A §A.1 disse que o input de `PROCESSAR ARQUIVOS` era
   `recordId`. O nome real da chave é **`Cliente`**, ligada a `trigger.id`
   — o efeito estava certo, o rótulo não.

---

## Regra de manutenção

Este conjunto **fica desatualizado no minuto em que o código muda.**
Deve ser regenerado por auditoria, nunca editado de memória.

Append-only: uma etapa nova acrescenta e corrige explicitamente onde
errou; nunca reescreve o texto de uma etapa anterior. Correção de fato
entra como linha de correção declarada, não como edição silenciosa.
