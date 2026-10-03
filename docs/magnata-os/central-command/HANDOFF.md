# HANDOFF — ponto de entrada para a próxima sessão

**Gerado na Etapa 13, 2026-08-24. Catch-up da Etapa 15 em 2026-10-03 — ver §0-bis.**

Uma sessão nova deve conseguir continuar **lendo só este arquivo e os 4
canônicos abaixo** — sem a conversa Macro 6A, que está encerrada.

> Este arquivo **não duplica** a Central Command. Ele aponta.

## 0-bis. Catch-up Etapa 15 (2026-10-03) — leia isto antes do resto

⚠️ **O corpo deste documento (§1 em diante) descreve o estado de
2026-08-24 (`main` = `073e39d`, por volta do commit `76b0046`) e não foi
reescrito nesta passada.** Entre essa data e agora, `main` recebeu **105
commits / ~70 PRs adicionais** (até o merge do PR #225, 2026-10-03,
`a169353a`), incluindo frentes inteiras que o corpo abaixo trata como
"não existe" ou nem menciona. Esta seção é o catch-up mínimo — ela
**acrescenta**, não reescreve o histórico de Etapa 13 (`CLAUDE.md` §2/§4:
nenhum evento já registrado é editado ou apagado).

**Fonte desta seção:** auditoria de legado feita em thread paralela
nesta mesma sessão de coordenação, registrada em
`/mnt/project-files/magnata-os/mapa-legado.md` (2026-10-03, HEAD no
merge do PR #224) — usar esse mapa como complemento desta Central
Command para o período 2026-08-24 → hoje, não como substituto.

**Estado real agora** (reconferir com `python
scripts/ci/central_command_sensor.py` — ele compara isto contra
`ESTADO.json`, atualizado nesta mesma passada):

| | |
|---|---|
| **`main`** | `a169353a` — Merge pull request #225 (wiring de 2 linhas em `app.py`, autorizado, para servir o painel estático) |
| **Módulos que passaram a existir/avançar desde Etapa 13 e que o corpo abaixo NÃO cobre** | Prestação de Contas (quase todo o domínio, modo *shadow*); cadastro de colaborador persistente em Postgres (PR #215, migration **preparada, não aplicada**); OCR real via Google Vision (`MotorOcrGoogleVision`, PR #209, ativo quando `GOOGLE_VISION_API_KEY` existe); interpretação de ordem do operador em linguagem natural (shadow V1, PR #214); painel web servindo `frontend/` em `/painel` no mesmo domínio com login Google real (PR #224/#225); ingestão de documentos em lote pelo próprio painel, sem Shell (PR #221/#222); endpoint S3 customizado tipo R2 (PR #218) |
| **Não verificado nesta passada (depende de produção)** | Se o Postgres de produção (`magnata-os-db`) está de fato provisionado no Render; se a migration do cadastro de colaborador (PR #215) foi aplicada em banco real; se qualquer cron/worker do orquestrador roda de fato no Render. `render.yaml` continua declarando blocos que podem não estar aplicados (plano free) — **tratar como `LIVE_STATE`, não herdar "sim" nem "não" de nenhuma nota anterior sem reconfirmar** |
| **Suíte de testes** | Baseline preservada do snapshot anterior: 712 passando / 0 falhando. **Não remedida nesta sessão** — ambiente desta sessão não tem `pytest`/dependências instaladas, e esta é uma mudança só de documentação. Rodar `--com-testes` numa sessão com o ambiente completo antes de confiar neste número para uma decisão de código |
| **Branches fora de `main`** | 289 no momento desta nota (o sensor já tinha esse número como ponto fraco conhecido — a maioria é `fix/auto-orquestrador-*`, PRs já mesclados cujo branch remoto não foi apagado; não confundir com trabalho perdido sem conferir individualmente) |

**O que esta passada fez:** só documentação — `ESTADO.json` regravado
pelo sensor (`--atualizar`, sem `--com-testes`) e esta seção acrescentada
a `HANDOFF.md`. Nenhum código, `app.py`, migration ou workflow foi
tocado.

**O que esta passada NÃO fez, de propósito (fora do escopo pedido —
"só documentação"):** reescrever §1-§8 abaixo PR a PR para as ~70
fusões do período; reconciliar `PENDING.md`, `NEXT_ACTIONS.md`,
`RISKS.md`, `DECISIONS.md` e os demais documentos da Central Command
contra o mesmo intervalo — eles continuam na data que já tinham. Isso é
uma lacuna real, registrada aqui e não escondida (`CLAUDE.md` §11),
não um "concluído" disfarçado.

## 0-ter. Reconciliação completa Etapa 16 (2026-10-03) — pedida pelo coordenador

Continuação do §0-bis, pedida explicitamente pelo coordenador do
projeto após o merge dos PRs #227/#231: "reconciliação completa dos 4
documentos com as fusões desde 2026-08-24". Esta seção entrega o que é
praticável nesse pedido — um catálogo factual e verificado dos PRs
mesclados, mais as correções de infraestrutura mais importantes — e é
explícita sobre o que continua fora de alcance de uma única passada.

### A escala real descoberta nesta passada

Entre a base da Etapa 13 (`073e39d`) e o `main` no início desta seção
(`a169353a`→`dcf5b61`) há **72+ merge commits** (de `git log
--merges`), não ~70 como o §0-bis estimou — a estimativa anterior já
estava um pouco baixa na hora em que foi escrita e ficou mais baixa
ainda enquanto esta seção era escrita: **10 PRs novos se mesclaram só
durante a investigação desta seção** (#226, #227, #230, #231,
#235–#237, #239, #240, #242–#248). `main` no momento em que este PR foi
aberto: `dcf5b61` (merge do PR #240, "shadow cliente↔posto Airtable",
não catalogado individualmente abaixo — chegou depois do levantamento
de tema). Isto não é um projeto que se lê uma vez e documenta: múltiplas
frentes rodam em paralelo, continuamente. A tabela abaixo é um corte no
tempo, não um estado final — **reconferir com `git log --merges` antes
de confiar nela para uma decisão**.

### Catálogo por tema (PRs mesclados, `073e39d`..`main` atual)

| Tema | PRs | Fonte verificada |
|---|---|---|
| Governança/CI/qualidade de suíte | 154, 155, 180, 226, 233*, 234*, 238*, 244, 245, 246, 248 | `testes-ci-observabilidade.md` (leitura de código e diffs reais) |
| Prestação de Contas (núcleo + ponta a ponta) | 158, 160, 161, 164–168, 170, 171, 174, 199, 209–214, 242, 243 | `prestacao-contas.md` (leitura de código, estado shadow confirmado) |
| Distribuição documental / assinatura | 172, 173, 175, 179, 181, 183, 184, 186, 187, 189, 190, 196, 197, 230, 235, 237 | `documentos-assinatura.md` |
| Postgres / esteira / índice documental | 176, 195, 218 | `mapa-legado.md` §2 |
| RH / Admissão / Secullum / cadastro persistente | 198, 207, 215, 236 | `mapa-legado.md` §2 ("cadastro de colaborador persistente, migration preparada **não aplicada**") |
| OCR real (Google Vision) | 209 | `mapa-legado.md` §2 |
| Painel web (login, frontend, ingestão em lote) | 203, 204, 206, 221, 222, 224, 225 | `mapa-legado.md` §2 |
| Central Command (este catch-up) | 195, 227, 231 | este documento |
| Infraestrutura/Render (`render.yaml`, capacidade, Redis) | 239, 247 | `infra-operacao-24x7.md` (API real do Render, não suposição) |

`*` PRs #233/#234/#238 ainda **não mesclados** no momento em que esta
seção foi escrita — verdes, prontos, represados pela mesma tensão
§9/merge-autônomo descrita abaixo. Não confundir com os já integrados.

**Triagem separada, de PRs *abertos* anteriores a #226** (não fusões —
PRs antigos nunca mesclados, revisados e, na maioria, fechados como
superseded): ver `backlog-prs.md` (fora deste repositório, mapa de
outra frente — "Frente H"). Resumo: a maioria (#128, #182, #185, #188,
#191, #192 em parte, #200, #205, #208, #216, #219, #220, #223, #51,
#122, #149) já estava superada por trabalho mesclado depois; três PRs
substantivos (#49, #115, #169) seguem abertos sem substituto
encontrado; #192 teve sua parte exclusiva extraída para o novo #249
(aberto, não mesclado); #193 e #201 foram atualizados sobre `main` e
deixados verdes.

### Infraestrutura real do Render — confirmado via API, não suposição

Fonte: `infra-operacao-24x7.md` (`RENDER_API_KEY` injetada pelo proxy,
nunca impressa; nenhuma escrita de produção feita). Isto substitui
qualquer suposição anterior deste documento ou de `RISKS.md` sobre o
que está ou não provisionado:

| Recurso | Estado real |
|---|---|
| Web (`magnata-holerite-splitter`) | Provisionado manualmente, plano `starter`, `--workers 1 --max-requests 50` real (divergente do declarado) |
| Worker (`magnata-holerite-worker`) | Provisionado, plano `starter`, **Auto-Deploy ligado** — todo merge que toca código do worker já é deploy de produção dele |
| Postgres (`magnata-os-postgres`) | **Provisionado manualmente**, `basic_256mb`, `available` — RSK-011 estava errado nessa parte, já corrigido em `RISKS.md` |
| Redis (`magnata-pdf-queue`) | Provisionado, plano `free`, sem persistência — nunca documentado antes de hoje, novo RSK-022 |
| Cron do Orquestrador | **Não provisionado.** Plano de ativação pronto (`plano-provisionamento-cron-orquestrador.md`), falta decisão financeira + autorização de produção |
| Blueprint | Nenhum aplicado (`GET /v1/blueprints` vazio) — `render.yaml` é documentação, não governa nenhum desses recursos ainda |

Detalhe completo e os riscos derivados (RSK-005/006/011/011-bis/022/
023/024) em `RISKS.md`.

### Merges represados — tensão §9 vs. autorização de fase

Várias PRs desta leva (#233, #234, #238, e possivelmente outras) estão
verdes e prontas, mas **não mescladas**: o coordenador identificou
tensão entre a autorização de "merge autônomo quando CI verde" (política
deste projeto) e `CLAUDE.md` §9 ("não fazer merge") e levou a decisão ao
Magnata antes de qualquer merge adicional. Isto não é uma falha desta
reconciliação — é o gate funcionando como desenhado (`CLAUDE.md` §9/
§12-I nunca são dispensados por autonomia operacional, por mais ampla).

### O que esta passada não fez — e por que não é um patch incremental

`NEXT_ACTIONS.md` (Etapa 3, 2026-08-22) e `DECISIONS.md` continuam
inalterados além do aviso curto já adicionado no PR anterior (#231). A
investigação desta seção mostra por quê isso não é só "ainda
desatualizado": a maioria dos riscos que `NEXT_ACTIONS.md` lista como
"nenhum item abaixo foi executado" **já foi executada ou superada** —
RSK-005 resolvido (#226), RSK-006 reconfirmado e com decisão de
capacidade pendente mas já instrumentada, RSK-011 majoritariamente
resolvido. Remendar esse documento item a item, em vez de reescrevê-lo
do zero a partir do estado real, arrisca produzir uma lista que mistura
itens mortos com itens vivos de forma pior do que simplesmente marcá-lo
obsoleto. **Recomendação, não execução:** uma frente dedicada deveria
reescrever `NEXT_ACTIONS.md` do zero a partir de `RISKS.md` (Etapa 16) e
de `PENDING.md` (PEN-021 a PEN-023), não continuar herdando a estrutura
de 2026-08-22.

---

## 0. Protocolo operacional — SESSION_START / SESSION_END

**SESSION_START** (copiar isto para o início de uma sessão nova):

```
1. Ler: HANDOFF.md + ESTADO.json + INDEX.md — nada mais, de início.
2. Rodar: python scripts/ci/central_command_sensor.py
   (reporta main_sha real, divergência, e o bloco `contexto` —
   status NORMAL/ATENCAO/TROCAR_SESSAO do próprio bootstrap).
3. Código específico → Graphify (ARQUITETURA_SNAPSHOT.json), nunca
   ler o repositório inteiro para localizar um símbolo.
4. Detalhe (TAXONOMIA_MEMORIA/MATRIZ_AUTONOMIA/mestre/histórico) só
   quando a tarefa exigir — não por precaução.
```

**SESSION_END** (checklist de fechamento, curto de propósito):

```
1. ESTADO.json já reflete a realidade? (rodar o sensor de novo)
2. HANDOFF.md §1 bate com o que mudou nesta sessão? Atualizar só os
   fatos que mudaram — não reescrever o resto.
3. Branch, commits, PR: registrados em §3/§4 abaixo?
4. Alguma divergência nova encontrada (doc vs. código, não só
   número)? Registrar — nunca corrigir em silêncio (CLAUDE.md §2).
5. Próxima ação de maior valor (§8) ainda é a certa, ou mudou?
```

`scripts/ci/medir_contexto.py --json` mede os 3 tiers acima em números;
não precisa ser lido para seguir o protocolo, só existe para quem quer
o dado exato.

## 1. Onde o repositório está

> ⚠️ **Os números abaixo são de 2026-08-24 e envelhecem.** Não confie
> neles: **execute `python scripts/ci/central_command_sensor.py`** — ele
> compara o estado real com `ESTADO.json` e diz o que mudou, incluindo
> o bloco `contexto` (Etapa 13, ver abaixo).

| | |
|---|---|
| **`main`** | `073e39d` — *Merge pull request #62* (Gmail Readonly Shadow V1) |
| **Suíte** | **712 passando / 1 skip / 0 falhando** (verificado nesta sessão, `fix/contexto-progressivo` — inclui os 22 testes novos desta etapa) |
| **CI** | 3 workflows: governança (15/15 gates), `pytest`, **`orquestrador-sensor.yml`** (novo — ver §3) |
| **PII na árvore atual de `main`** | ✅ **nenhuma** (não reauditado a fundo nesta etapa, herdado) |
| **Central Command** | 30 documentos + `ESTADO.json` + `ARQUITETURA_SNAPSHOT.json` + `AUDITORIA_ORQUESTRADOR.jsonl` (novo) |
| **Graphify** | ✅ regenerado em cópia isolada após o PR #62: 88 arquivos, 15 módulos, 2.566 arestas `EXTRACTED`, nenhuma violação de acoplamento; inclui `email_gmail_readonly.py` |
| **Produção** | ❌ **NÃO VERIFICÁVEL** — não testado nesta etapa (herdado de Etapa 12) |
| **Grande Orquestrador** | 🟢 **NÚCLEO EXECUTÁVEL EXISTE** (`magnata_os/orquestrador/`) + **gatilho automático via GitHub Actions já mesclado** (PRs #45, #46, #47) — ver correção declarada abaixo |
| **Contexto (Etapa 13)** | TIER 0 ≈ 6.330 tokens — `status_contexto: NORMAL` (medido novamente após o PR #62) |
| **Gmail Readonly Shadow V1** | ✅ presente em `main`, inerte e somente leitura; adapter e testes específicos/integrados vieram pelo PR #62 |
| **PRs abertos** | **Não reconfirmado ao vivo nesta sessão** (sem acesso a `gh`/API do GitHub) — tratar como `LIVE_STATE` a reconsultar, nunca herdar o "Nenhum" da Etapa 12 |

### Correção declarada (Etapa 13, 2026-08-24)

`ORQUESTRADOR.md` §6.2 e `MATRIZ_AUTONOMIA.md` §4 (Etapa 12) afirmam que
**"nenhum gatilho automático roda sozinho"** e que isso "não foi
construído". **Superado, com evidência em `main`:** o commit `cb835cb`
("núcleo mínimo executável") e as duas fusões seguintes — `PR #46`
(`fix/orquestrador-nucleo-motor`) e `PR #47`
(`fix/orquestrador-gatilho-ci`) — já implementaram exatamente essa peça:
`magnata_os/orquestrador/` (motor de eventos, política de autonomia,
idempotência, retry) + `.github/workflows/orquestrador-sensor.yml`
(cron a cada 6h, abre PR, nunca commita em `main`, nunca mescla
sozinho). Nenhum texto anterior foi reescrito — os dois documentos
citados continuam com a afirmação original; esta é a correção, não uma
edição silenciosa. `ORQUESTRADOR.md` §6.2 e `MATRIZ_AUTONOMIA.md` §4
**precisam de uma etapa de auditoria dedicada** para reconciliar o texto
inteiro — isto aqui só registra que a lacuna que ambos descrevem como
aberta já foi fechada em código.

## 2. Ler primeiro, nesta ordem

1. **`CLAUDE.md`** — a constituição. Vence tudo abaixo.
2. **`docs/magnata-os/central-command/INDEX.md`** — mapa: qual arquivo responde qual pergunta.
3. **`TAXONOMIA_MEMORIA.md`** e **`MATRIZ_AUTONOMIA.md`** — o que um sensor pode escrever sozinho, e em qual nível de autonomia (Etapa 12, novo).
4. **`docs/magnata-os/MAGNATA_OS_CENTRAL_COMMAND.md`** §0-H a §0-J — as últimas etapas.
5. **`MACRO_6A_RECONCILIACAO.md`** §4 — os 6 erros que não devem se repetir.

Para saber se a memória está defasada, **não leia: execute.**

```
python scripts/ci/central_command_sensor.py
bash scripts/ci/graphify_regenerar.sh --comparar   # opcional, sensor estrutural
```

## 3. Merges recentes

**Após a Etapa 13 — evidência local em `main`:**

| PR | O que trouxe |
|---|---|
| **#62** | Gmail Readonly Shadow V1 inerte, adapter e testes — **MESCLADO** em `073e39d` |

**Etapa 13 (2026-08-24) — visíveis por evidência local de `git log`, não por consulta ao GitHub:**

| PR | O que trouxe |
|---|---|
| **#45** | Fundação do Orquestrador (`fix/etapa12-orquestrador-fundacao`) — **MESCLADO** |
| **#46** | Núcleo executável do Orquestrador — motor, eventos, política de autonomia, retry (`fix/orquestrador-nucleo-motor`) — **MESCLADO** |
| **#47** | Gatilho automático via GitHub Actions, sem sessão (`fix/orquestrador-gatilho-ci`) — **MESCLADO**. Fecha `MATRIZ_AUTONOMIA.md` §4 — ver correção declarada acima |

**Etapa 13 (2026-08-24) — desta sessão, branch `fix/contexto-progressivo`:**

- `scripts/ci/medir_contexto.py` + testes — mede TIER 0/1/2 de contexto e classifica NORMAL/ATENCAO/TROCAR_SESSAO.
- `scripts/ci/central_command_sensor.py` estendido — `coletar()` agora inclui `contexto`, `graphify_snapshot_status`, `session_handoff_freshness`. Flui automaticamente para `ESTADO.json` via `magnata_os/orquestrador/acoes/atualizar_auto_fact.py`, já existente — nenhuma mudança nesse caminho foi necessária. Testado ponta a ponta (`scripts/ci/orquestrador_sensor_ci.py`) em cópia isolada.
- Este HANDOFF.md — protocolo SESSION_START/END (§0) + correção declarada acima.

**Etapa 12 (2026-08-23):**

| PR | O que trouxe |
|---|---|
| **#41** | Correção do sensor (baseline não some mais sem `--com-testes`) — **MESCLADO** |
| **#22** | Adapter de captura de e-mail (Módulo 01) — **MESCLADO**. Adapter em `main`, **inerte** — nenhum caller real |
| **#44** | Central Command reconciliada com o merge do #22 |

## 4. PRs abertos

**Não reconfirmado ao vivo nesta sessão** — sem `gh`/API do GitHub disponível. O PR desta sessão (`fix/contexto-progressivo`) ainda não foi aberto no momento em que este HANDOFF foi escrito — ver §17 do relatório da missão para o link, se já existir quando você ler isto. Trate qualquer contagem de "PRs abertos" como `LIVE_STATE` (`TAXONOMIA_MEMORIA.md`) — reconsulte, nunca herde este número.

## 5. Riscos, em ordem (herdados — não reavaliados nesta etapa)

| # | Risco | Onde está descrito |
|---|---|---|
| 1 | 🔴 **PII em ~40 pontas de branch** e no histórico de `main` | `PII_HISTORICO_PLANO.md` |
| 2 | 🔴 **`480` fixo** — só o Airtable calcula extra, e só ele ignora 12x36 | `AIRTABLE_LOGICA_OCULTA.md` ANEXO B §B.5 (AT-21) |
| 3 | 🔴 **Make.com ativo sem `try/catch`** — falha silenciosa | ANEXO B §B.6 (AT-12) |
| 4 | 🔴 **Batida ímpar → `BLANK()`** sem alarme | `AIRTABLE_LOGICA_OCULTA.md` §3 |
| 5 | 🟠 **72% de `Folha de Ponto`** calculado dentro do Airtable | `BANCO_PROPRIO_MODELO.md` §2 |
| 6 | 🟠 **`F_FUNC_STATUS`** escrito fora do código, lido pelo `app.py` | mestre §0-H.7 |
| 7 | 🟡 **Retry/backoff do adapter de e-mail** — decisão adiada para quando (e se) ligar a fonte real | `PENDING.md` PEN-020 (Etapa 12) |
| ~~8~~ | ~~Nenhum gatilho automático aciona sensor/Graphify sem sessão no meio~~ — **RESOLVIDO na Etapa 13**, ver correção declarada em §1 | `MATRIZ_AUTONOMIA.md` §4 (texto do documento em si ainda não reconciliado) |
| 9 | 🟡 **`ORQUESTRADOR.md` §6.2 e `MATRIZ_AUTONOMIA.md` §4 desatualizados** — descrevem o gatilho automático como inexistente, e já existe em `main` desde `cb835cb`/PR #45-47 | Correção declarada, §1 acima — reconciliação de texto completa ainda pendente |

## 6. Gates humanos abertos

| Gate | Decisão |
|---|---|
| 🔴 Histórico do Git | Sanear por avanço, reescrever, ou aceitar o risco |
| 🔴 Jornada `480` / 12x36 | Regra trabalhista com efeito retroativo em folha |
| 🔴 Make.com | Manter · instrumentar · migrar · descomissionar |
| 🟠 Postgres real | Decisão financeira — `render.yaml` é `plan: free` |
| 🟠 `Locais` = `Posto de Trabalho`? | `BANCO_PROPRIO_MODELO.md` §8.3 |
| 🟠 ADR `Documento` vs. `Item de Ingestão` | `CLAUDE.md` §5 |
| 🟠 40 branches / apagar branch | `CLAUDE.md` §9 |
| 🟡 Ligar o adapter de e-mail a uma fonte real | `DECISIONS.md` DEC-009 — precisa autorização de fase (`CLAUDE.md` §6/§12-I) |
| ~~🟡 Automatizar disparo do sensor/Graphify sem sessão no meio~~ | **RESOLVIDO na Etapa 13** para o sensor (`.github/workflows/orquestrador-sensor.yml`) — Graphify continua fora de CI por desenho (`GRAPHIFY.md` §6 restrição 3, não um gate pendente) |
| 🟠 Reconciliar o texto de `ORQUESTRADOR.md` §6.2 e `MATRIZ_AUTONOMIA.md` §4 com o Orquestrador já existente | Auditoria dedicada — fora do escopo desta missão de contexto |

## 7. O que só a interface resolve

Nenhuma ferramenta desta sessão alcança:

1. **Filtros das 10 views** e **condições dos ramos** — Airtable.
2. **Confirmar que `Automation 1` está mesmo vazia** — Airtable.
3. **O que o cenário do Make.com faz** — Make.com. Bloqueia 3 das 4 opções.
4. **Produção** — rede (reconfirmado nesta etapa, `WebFetch` → `EGRESS_BLOCKED`).

## 8. Próxima ação de maior valor

**Instrumentar o `PROCESSAR ARQUIVOS` (Make.com) com tratamento de erro.**

Continua sendo o item que é, ao mesmo tempo: risco 🔴 ativo em produção,
correção pequena, sem mudar o caminho feliz, e sem dependência de
nenhuma decisão de negócio pendente. Mata AT-12 sem tocar em jornada,
folha ou fornecedor.

⚠️ Continua sendo **escrita fora deste repositório** (Make.com) — fora
do alcance de qualquer sessão sem acesso à interface, e mesmo com
acesso, é escrita externa: gate de `CLAUDE.md` §6, com autorização por
fase cumprindo (a)–(f).

**Dentro do que uma sessão de código alcança hoje** (Etapa 13,
2026-08-24): a lacuna de infraestrutura de disparo automático (item
acima, Etapas 12→13) está fechada. As duas maiores lacunas que restam
são:

1. **Reconciliar `ORQUESTRADOR.md` §6.2 e `MATRIZ_AUTONOMIA.md` §4** com
   o Orquestrador que já existe em código — auditoria de texto, sem
   risco, sem gate humano (é documentação alcançando o código, não o
   contrário).
2. **Adicionar mais `TipoEvento` ao Orquestrador** (ex.: `PR_MESCLADO`,
   `SUITE_DIVERGIU`, já previstos em `politica_autonomia.py` mas sem
   `detectar_evento`/Ação implementados) — cada um exige decisão
   explícita registrada em `DECISIONS.md` antes de ganhar
   `EXECUTE_SAFE` (`politica_autonomia.py`, comentário do próprio
   código) — **gate humano por desenho, não por omissão**.
