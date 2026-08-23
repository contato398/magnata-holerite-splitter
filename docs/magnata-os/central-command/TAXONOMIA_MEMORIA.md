# TAXONOMIA DA MEMÓRIA — o que cada arquivo da Central Command É

**Etapa 12, 2026-08-23.** Requisito formalizado a partir de uma peça que
já existia na prática mas nunca tinha nome: desde a Etapa 1, o sensor
(`central_command_sensor.py`) e o Graphify (`graphify_regenerar.sh`) só
escrevem em dois arquivos (`ESTADO.json`, `ARQUITETURA_SNAPSHOT.json`) —
nunca em `DECISIONS.md`, nunca em `DIRECTIVES.md`. Essa fronteira nunca
foi violada, mas também nunca foi **declarada como regra**, só seguida
por hábito. Isto a declara.

**Não muda nenhum arquivo existente de categoria.** Só nomeia o que já
é verdade e torna a violação futura detectável.

---

## 1. As 6 categorias

| Categoria | Quem escreve | Pode ser sobrescrito automaticamente? | Exemplo real neste repositório |
|---|---|---|---|
| **AUTO_FACT** | Um sensor/script, sem julgamento | ✅ Sim — é o próprio propósito | `ESTADO.json` (`central_command_sensor.py --atualizar`) |
| **LIVE_STATE** | Consulta ao vivo a um sistema externo, no momento da consulta | ✅ Sim, mas expira — vale só no instante em que foi lido | Resultado de `pull_request_read`/`get_check_runs` nesta sessão; **nunca** commitado como se fosse permanente |
| **HUMAN_DECISION** | Pessoa, em mensagem distinta da que redigiu a proposta (`CLAUDE.md` §6-e) | ❌ **Nunca.** Só nova decisão humana supera decisão humana | `DECISIONS.md`, `DIRECTIVES.md`, autorização em `.magnata/app-py-authorizations/*.gitblob` |
| **DERIVED** | Ferramenta que **interpreta**, não só mede (Graphify, um relatório gerado) | 🟡 Regenerável, mas nunca autoridade — perde para AUTO_FACT/LIVE_STATE/HUMAN_DECISION em conflito | `ARQUITETURA_SNAPSHOT.json`, `GRAPH_REPORT.md` (nunca commitado inteiro — só o resumo) |
| **UNVERIFIED** | Sessão anterior, conversa, ou fonte sem confirmação técnica desta sessão | ❌ Não deve ser tratado como AUTO_FACT nunca | Números do lote Julho/2026 citados em conversa (ver `docs/magnata-os/memoria/fontes/`, quando existir) |
| **SUPERSEDED** | Marcado por correção declarada, nunca apagado | N/A — é o estado final de algo que já foi outra categoria | `SUPERSEDED_DECISIONS.md`; a "primeira correção declarada" de `DEC-009` |

## 2. Regra dura, a única que importa

> **Nenhum processo automático pode escrever em HUMAN_DECISION.**
> Nenhuma exceção, nenhum "só desta vez", nenhuma autoridade de fase
> autoriza isso — é o mesmo princípio de `CLAUDE.md` §6-e (decisão
> humana confirmada em mensagem distinta) aplicado à escrita de
> memória, não só à ação externa.

Consequência prática: um sensor pode **ler** `DECISIONS.md` para
detectar se um DEC-XXX ficou desatualizado (comparando contra
AUTO_FACT/LIVE_STATE), mas só pode **propor** a correção — nunca
escrevê-la sozinho. A escrita em `DECISIONS.md`/`DIRECTIVES.md`
continua exigindo uma sessão (humana ou assistida) que redige a
"correção declarada" explicitamente, como já acontece desde a Etapa 2.

## 3. Classificação de cada arquivo da Central Command hoje

| Arquivo | Categoria | Por quê |
|---|---|---|
| `ESTADO.json` | **AUTO_FACT** | Só o sensor escreve; nunca interpretação |
| `ARQUITETURA_SNAPSHOT.json` | **DERIVED** | Graphify interpreta (comunidades, grau) — não é medição direta como `git log` |
| `DECISIONS.md` | **HUMAN_DECISION** | Autoridade só de pessoa; correção só por "correção declarada" explícita |
| `DIRECTIVES.md` | **HUMAN_DECISION** | Ordens da Direção |
| `SUPERSEDED_DECISIONS.md` | **SUPERSEDED** | Por definição |
| `ACTIONS_COMPLETED.md` | **HUMAN_DECISION** (narrativa) apoiada em **AUTO_FACT** (evidência) | O texto é escrito por sessão; a evidência citada (commit, PR) é verificável |
| `WORK_IN_PROGRESS.md` / `PENDING.md` / `NEXT_ACTIONS.md` | **HUMAN_DECISION** (narrativa) | Julgamento de prioridade, não medição |
| `RISKS.md` | **HUMAN_DECISION** (narrativa) apoiada em AUTO_FACT/DERIVED | Severidade é julgamento; a evidência é fato |
| `PRS_AND_BRANCHES.md` | **HUMAN_DECISION** (narrativa) + tabelas **AUTO_FACT** citadas | Classificação de branch é julgamento; contagem de PR é fato verificável |
| `SOURCES_AND_PROVENANCE.md` / `COBERTURA.md` / `FORA_DO_GIT.md` | **UNVERIFIED** (sobre o que descrevem) tratado com rigor — o documento em si é **HUMAN_DECISION** sobre como registrar a incerteza | — |
| `GRAPHIFY.md` / `ORQUESTRADOR.md` / `AIRTABLE_*.md` / `BANCO_PROPRIO_MODELO.md` | **HUMAN_DECISION** (requisito/proposta, nunca arquitetura aprovada) | Todos se autodeclaram "registro de requisito, não decisão" |
| `HANDOFF.md` / `INDEX.md` | **HUMAN_DECISION** (curadoria) apoiada em AUTO_FACT (números que "envelhecem", já avisados como tal) | — |
| `HISTORICO.md` | **UNVERIFIED → SUPERSEDED-como-fonte** | Memória operacional livre de PII; números com 30-60 dias de idade, nunca reconfirmados |
| Qualquer resultado de `pull_request_read`, `get_check_runs`, consulta Airtable ao vivo nesta sessão | **LIVE_STATE** | Verdadeiro no instante da consulta; expira — próxima sessão precisa reconsultar, nunca herdar como fato permanente |

## 4. O que isto habilita, concretamente

1. **Verificação de violação por sensor** (não implementada nesta etapa,
   registrada como próximo passo): um script poderia, no futuro,
   escanear se algum commit alterou `DECISIONS.md`/`DIRECTIVES.md` sem
   o padrão textual de "correção declarada" — mas **detectar** não é o
   mesmo que **bloquear**; bloquear via CI é decisão de governança
   nova, fora do escopo desta etapa.
2. **Explicar por que o sensor nunca teve esse bug**: `central_command_sensor.py`
   e `graphify_snapshot.py` só produzem/gravam `ESTADO.json` e
   `ARQUITETURA_SNAPSHOT.json` — a fronteira AUTO_FACT/DERIVED vs.
   HUMAN_DECISION já existe em código, confirmado por leitura: nenhuma
   função nesses dois scripts abre `DECISIONS.md`, `DIRECTIVES.md` ou
   qualquer arquivo fora dos dois snapshots para escrita.
3. **Nomear o erro que já aconteceu uma vez**: a fonte conversacional do
   lote Julho/2026 (ver `RELATORIO_COBERTURA_LACUNAS`/handoffs
   anteriores) é **UNVERIFIED** — foi corretamente tratada como tal
   quando confrontada com AUTO_FACT (a suíte real divergiu do número
   citado em conversa). Esta taxonomia só dá nome ao que a auditoria já
   fazia por instinto.
