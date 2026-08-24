# Grande Orquestrador V1 — Reconciliação do Fechamento

**Data**: 2026-08-24
**Fase**: MISSÃO CORRETIVA — reconciliar o estado real, terminar trabalho incompleto, produzir veredito tecnicamente defensável
**Substitui**: `GRANDE_ORQUESTRADOR_V1_READINESS.md` (retratado — ver banner no topo daquele arquivo)

---

## Por que este documento existe

O relatório anterior encerrou a missão como "PRONTO PARA PRODUÇÃO" e
"AUTORIZAÇÃO PARA PRODUÇÃO: APROVADO". Essas duas frases foram
**revogadas** por instrução explícita do usuário e, na revalidação
desta missão corretiva, **uma delas se provou tecnicamente falsa** no
momento em que foi escrita: a alegação de "AT_MOST_ONCE garantido"
(Ponto 6 / pergunta K do relatório anterior) não tinha prova real —
os testes que a sustentavam não forçavam concorrência de verdade, só
passavam por sorte de escalonamento de threads. Uma prova
determinística (`threading.Barrier`, forçando dois workers dentro do
motor ao mesmo tempo) encontrou dupla execução real de uma Ação
externa para o mesmo `event_id`. Isso foi corrigido nesta missão — mas
não estava corrigido quando a frase foi escrita.

Produção **nunca foi verificada** (sem acesso a Render nesta sessão) e
**continua HUMAN_REQUIRED** — nenhuma parte deste documento autoriza
deploy.

---

## Resumo do que mudou nesta reconciliação

| # | Item | Antes | Depois |
|---|------|-------|--------|
| 1 | Chaos testing | 3/6 (declarado incompleto por limite de contexto) | **6/6** — os 3 restantes diagnosticados e corrigidos (2 bugs de teste, 1 capacidade real ausente) |
| 2 | Concorrência | "AT_MOST_ONCE garantido" (não provado) | Provado com corrida forçada; **lacuna real encontrada e corrigida** (`criar_se_novo` + recusa de retomada de evento em andamento) |
| 3 | Replay | Só `FAILED_FINAL` | Estendido para cobrir eventos presos "em andamento" após crash do worker (consequência direta do fix de concorrência) |
| 4 | Integração com `main` | 15 commits só na branch, nenhum em `main` | Ainda só na branch — **PR aberto nesta missão**, não mesclado (ver §16.C) |
| 5 | GitHub autônomo | Não verificado | **Confirmado bloqueado** — evidência de log real (ver §16.O) |
| 6 | Health persistence | Não verificado | **Confirmado não-persistente** — é o design documentado no próprio módulo (ver §16.L) |

---

## 1. Revalidação ao vivo

- **HEAD de `main`**: `76b0046b17883fb20f7102d3cf24cf2b90c2f26c` (merge do PR #47)
- **Branch de trabalho**: `claude/magnata-memory-audit-2c6bps`, 17 commits à frente de `main`, merge-base = HEAD de `main` (nenhum conflito, fast-forward possível)
- **PRs abertos no repositório**: 1 — PR #49 (`feat(modulo01): ClienteGmailReadOnly — Fase 1 do modo sombra`), CI verde, `mergeable_state: clean`, **não mesclado**
- **CI**: workflow "Magnata OS — Suíte de Testes" e "Validação de Governança e Conformidade" — verdes no PR #49; suite local nesta branch: **794 passed, 1 skipped, 0 failed**, estável em 3 execuções consecutivas
- **Workflow autônomo do Orquestrador** (`orquestrador-sensor.yml`): 4 execuções registradas, **todas com falha** no passo de abrir PR — ver §16.O para o log exato

## 2. Reconciliação dos commits da branch de trabalho

Os 17 commits em `claude/magnata-memory-audit-2c6bps` (à frente do merge-base com `main`) são:

- **Todos exclusivos da branch** — nenhum está em `main`. Nenhuma dessas capacidades (DLQ, auditoria append-only, replay, health monitor, DRY_RUN/KILL_SWITCH, os fixes de concorrência desta missão) está em produção ou mesmo na branch principal do repositório até que um PR seja mesclado.
- **Nenhum duplicado, nenhum superseded, nenhum conflito** com `main` — merge-base é exatamente o HEAD atual de `main`.
- **Classificação**: todos são "prontos para PR" — nenhum toca `app.py`, Airtable, Render, credencial real, ou schema de produção. São 100% mudanças internas ao motor do Orquestrador (`magnata_os/orquestrador/`) e seus testes.

## 3. PR de integração

**PR aberto**: ver link entregue ao usuário nesta resposta. Título e corpo descrevem o escopo (motor do Orquestrador: DLQ, auditoria, replay, concorrência) e apontam este documento.

**Regra dura mantida**: CLAUDE.md §9 — "Não fazer merge" — é um gate que a §12 explicitamente nunca dispensa. Esta missão pediu para "mesclar automaticamente mudanças internas e reversíveis, se a governança permitir" — **isso conflita com a proibição absoluta de merge do CLAUDE.md**, que tem precedência declarada sobre qualquer instrução de sessão. Registrando o conflito explicitamente (CLAUDE.md §1: "Nenhuma decisão arquitetural é tomada em silêncio"): **o PR foi aberto, mas não mesclado.** Merge requer decisão humana explícita.

## 4. Chaos — 6/6 completo, causas reais

Os 3 cenários que ficaram pendentes na sessão anterior foram reabertos e diagnosticados individualmente — nenhum encerrado por limite de contexto:

1. **`test_audit_indisponivel_graceful_degradation`** — **TESTE INCORRETO**. Chamava `repo.fechar()` em `RepositorioExecucoesEmMemoria`, que não tinha esse método (só a implementação SQLite tinha, fora do `Protocol`). Fix: `fechar()` promovido ao `Protocol RepositorioExecucoes` e implementado como no-op na versão em memória — paridade de interface real, não workaround de teste.
2. **`test_evento_sem_event_type_necessario`** — **CAPACIDADE AUSENTE, real**. `Evento(event_type=None, ...)` não levantava nenhum erro na construção — `dataclass` não valida type hints em runtime. O erro só apareceria depois, como `AttributeError` no primeiro despacho em `motor.py` (não é uma falha silenciosa, mas também não é o ponto mais cedo/claro para falhar). Fix: `Evento.__post_init__` agora rejeita `event_type=None` explicitamente, mesmo padrão já usado para `event_id` vazio.
3. **`test_falha_acao_e_falha_auditoria`** — mesma causa do item 1.

Suite completa após os 3 fixes: **792 passed, 1 skipped, 0 failed** (antes: 789 passed, 3 failed).

## 5. DLQ — confirmado no motor real, não só em teste isolado

`magnata_os/orquestrador/motor.py` linhas 294-301 e 308-318: toda transição para `FAILED_FINAL` (nos dois pontos onde ela ocorre — falha classificada como permanente, e esgotamento de `MAX_TENTATIVAS`) chama `extrair_para_fila_desistencia(registro)` e `self._fila_desistencia.registrar(item_dlq)`. Isso está no caminho de execução real do motor, não é um mock de teste. Replay manual (`motor.replay()`) sai de `FAILED_FINAL` de volta para `RECEIVED` — confirmado no código, coberto por 7 testes dedicados.

## 6. Concorrência — o que a arquitetura realmente garante agora

**Antes desta missão**: nada. `processar()` fazia `buscar_por_event_id()` (check) e só persistia algo bem depois (act) — sem exclusão mútua entre as duas etapas. Provado com um probe determinístico (`threading.Barrier` forçando dois workers dentro do motor simultaneamente para o mesmo `event_id` **novo**): dupla execução real da Ação.

**Fix aplicado** (duas camadas, mesma causa raiz — ver commit `1c6af5d`):

1. `criar_se_novo()`: reivindicação atômica para evento novo, apoiada na `PRIMARY KEY` do SQLite (garantia do próprio motor de banco entre conexões/threads/processos — não um lock em Python) e, na versão em memória, um `threading.Lock` real.
2. Um segundo `processar()` para um evento já existente mas **não-terminal** (`RECEIVED`/`VALIDATED`/`CLASSIFIED`/`EXECUTING`/`WAITING_GATE`) agora recusa e devolve o registro como está — nunca reexecuta a Ação. Isso fecha a mesma classe de corrida um passo depois do primeiro fix.

**O que isso garante, com precisão**:
- **Idempotência de evento** (dedup por `event_id` em estado terminal): garantida desde o início, nunca esteve quebrada.
- **Exclusão mútua na reivindicação de evento novo**: garantida agora, provada com corrida forçada real (não timing por sorte).
- **AT_MOST_ONCE para a Ação (efeito externo)**: garantida agora para o caso comum (workers concorrentes, nenhum crash).
- **Exactly-once**: **não garantida e não é o que este fix entrega** — se o worker que reivindicou um evento morrer (crash) antes de um estado terminal, o evento fica preso nesses estados **para sempre por design**, porque retomar automaticamente reabriria a mesma corrida. A única saída é `replay()` manual, com um humano confirmando fora de banda que o worker original morreu. Isso é uma troca deliberada (favorecer "nunca duplicar efeito externo" sobre "nunca travar"), documentada no código e nos testes, não uma lacuna escondida.

**Janela residual que continua existindo, documentada explicitamente**: se a própria Ação tiver um efeito colateral parcial (ex.: enviou metade de uma requisição HTTP) e o processo morrer no meio da chamada, esse efeito parcial não é revertido por nada aqui — a responsabilidade de idempotência da Ação em si (ex.: usar uma chave de idempotência na API externa) continua sendo do autor de cada Ação registrada, o motor só garante que **ele mesmo** não chama a Ação duas vezes para o mesmo evento.

## 7. Auditoria — persistente e append-only, confirmado sob restart e concorrência

- **Restart**: `test_auditoria_persiste_entre_sessoes_sqlite` — fecha e reabre o repositório, histórico idêntico.
- **Concorrência**: `test_concorrencia_nao_corrompe_auditoria` — 3 workers concorrentes, transições continuam ordenadas e com timestamps monotonicamente crescentes.
- **Falha de escrita**: `test_audit_indisponivel_graceful_degradation` (agora passando) — auditoria falhando não trava o processamento (`_transicionar` captura a exceção e emite um evento de erro, nunca propaga silenciosamente nem interrompe o fluxo principal).
- **Imutabilidade real, não só em memória**: `RegistroAuditoria` é `@dataclasses.dataclass(frozen=True)` — `dataclasses.FrozenInstanceError` é levantado em qualquer tentativa de mutação, verificado em teste. Na tabela SQLite, a tabela `auditoria` só recebe `INSERT` (nunca `UPDATE`/`DELETE`) em todo o código — confirmado por leitura direta do repositório, não só do teste.

## 8. Health — NÃO persiste, classificação correta é PARCIAL

O próprio módulo declara isso na primeira linha do docstring: *"Sem estatefulidade persistida -- metricas em memoria do processo atual."* `MonitorSaudemotor` é um contador em memória do processo — reinicia zerado a cada novo processo. Isso não é um bug a corrigir nesta missão (seria uma capacidade nova, fora do escopo de "consolidação, integração, correção e prova" desta missão) — é uma limitação real que a classificação anterior ("✅ PRONTO") escondia ao não mencionar. Classificação correta: **PARCIAL** — funciona corretamente dentro de um processo, não sobrevive restart.

## 9. Central Command / AUTO_FACT

O sensor de CI (`scripts/ci/orquestrador_sensor_ci.py`) roda o motor real contra um único tipo de evento (`GIT_MAIN_AVANCOU`) e grava um append-only `AUDITORIA_ORQUESTRADOR.jsonl` versionado — esse é o AUTO_FACT persistente entre execuções de CI (a tabela SQLite em si é efêmera por run). As capacidades novas desta reconciliação (fix de concorrência, chaos 6/6, replay estendido) **beneficiam automaticamente** esse sensor porque ele importa o mesmo `motor.py` — mas nenhum AUTO_FACT novo foi criado especificamente sobre essas capacidades, e não deveria ser (isso seria uma decisão de negócio/documental separada, fora do escopo desta missão de consolidação técnica).

## 10. GitHub autônomo — confirmado ainda bloqueado

Evidência direta do log da última execução (`run 32701118406`, `job 97352639928`, passo "Abrir PR com o AUTO_FACT atualizado"):

```
pull request create failed: GraphQL: GitHub Actions is not permitted to create or approve pull requests (createPullRequest)
##[error]Process completed with exit code 1.
```

As 4 execuções registradas do workflow `orquestrador-sensor.yml` (3 agendadas + 1 manual) **falharam todas no mesmo ponto**: o `git push` da branch funciona (`fix/auto-orquestrador-76b0046-N` foi criada e empurrada com sucesso em cada tentativa), mas `gh pr create` é rejeitado pela política do repositório/organização no GitHub — "Allow GitHub Actions to create and approve pull requests" está desligado nas configurações do repositório. Isso não é um problema de código do workflow; é uma configuração do GitHub que só o dono do repositório pode alterar (Settings → Actions → General → Workflow permissions).

**Efeito colateral não limpo**: cada execução falha deixou uma branch órfã (`fix/auto-orquestrador-76b0046-2`, `-3`, `-4`) sem PR associado. Não apaguei essas branches nesta missão — apagar branch é uma ação destrutiva fora do escopo desta reconciliação e não foi pedida; fica registrado aqui para o usuário decidir.

**Resposta direta**: o workflow **NÃO** fecha ponta-a-ponta. PR não é criado sem uma sessão Claude (ou um humano) intervindo — a automação "sem sessão" fica pela metade: ela detecta a mudança, roda o motor, escreve o AUTO_FACT localmente e empurra a branch, mas não consegue abrir o PR sozinha. Chamar isso de "Orquestrador autônomo completo" seria incorreto.

## 11. Gmail Fase 1 — PR #49

- **Aberto**: sim, `#49`, título "feat(modulo01): ClienteGmailReadOnly — Fase 1 do modo sombra de captura de e-mail"
- **CI**: verde (pytest + Validação de Governança, ambos `success`)
- **Mergeado**: **não**
- **SHA head**: `1a5fcb805b9e9a89ba7ab2ff694909f64c87dff2`, base `main@76b0046`
- **`mergeable_state`**: `clean`
- **Inerte**: sim — o PR descreve explicitamente que a Fase 2 (execução real, credencial real) fica bloqueada até autorização de fase conforme CLAUDE.md §6a-f. Nenhuma conexão real ao Gmail foi feita nesta missão.

## 12. E2E interno

Não executado como um cenário único e explícito nesta missão (orçamento de tempo priorizou fechar a lacuna de concorrência, que era um risco de correção maior do que cobertura E2E adicional). Os componentes individuais (event → store → classify → policy → action → retry/DLQ → audit → health) estão cobertos por testes de integração dedicados (`test_magnata_os_orquestrador_integracao_dlq.py`, os testes de auditoria, os testes de crash consistency), mas não há um único teste que percorra a cadeia inteira em uma execução. **Risco declarado, não escondido**: cobertura de integração ponto-a-ponto existe por pares de componentes, não como uma trilha E2E única.

## 13. Ultrareview adversarial — achados desta missão

- **Dupla execução**: encontrada e corrigida (§6 acima) — o achado mais significativo desta missão.
- **Crash window**: comportamento agora é "trava até replay manual" em vez de "retoma automaticamente" — trade-off documentado, não uma lacuna nova.
- **Bypass de policy/kill switch/dry run**: nenhum novo achado — os testes adversariais da sessão anterior (Pontos 7-9) continuam válidos e passando; não foram razão de retratação.
- **PII/secrets/path traversal/command injection**: nenhum novo achado nesta revalidação; os testes de segurança adversarial (Ponto 10) continuam válidos.
- **Self-trigger / workflow privilege**: o workflow `orquestrador-sensor.yml` roda com `contents: write` + `pull-requests: write` via `GITHUB_TOKEN` padrão — escopo mínimo necessário para a tarefa (escrever `docs/magnata-os/central-command/` e abrir PR), sem segredo novo. Não encontrei escalonamento de privilégio além do que o próprio workflow já declara e documenta em seus comentários.
- **Falsa afirmação documental**: encontrada — é o próprio motivo desta missão corretiva (retratação de "AT_MOST_ONCE garantido").

## 14. Produção

**NÃO VERIFICÁVEL nesta sessão** — sem acesso a Render. Nenhum deploy foi feito, nenhuma autorização de produção foi dada ou é dada por este documento. Produção permanece `HUMAN_REQUIRED`.

## 15. Distinção de estados (obrigatória, não tratada como equivalente)

| Estado | Vale para |
|---|---|
| **Implementado na branch** | Todas as 17 commits desta missão + as anteriores (DLQ, auditoria, replay, health, DRY_RUN/KILL_SWITCH, fix de concorrência) |
| **Implementado em `main`** | **Nada disso** — zero dessas capacidades está em `main` |
| **Testado** | Sim, para tudo acima — 794 passed, 1 skipped, 0 failed, localmente, na branch |
| **Integrado** | Parcialmente — os componentes se integram entre si (motor + repositório + DLQ + auditoria), mas não com o restante do sistema em produção |
| **Autônomo** | Não — o único gatilho sem sessão (`orquestrador-sensor.yml`) está bloqueado na criação de PR |
| **Production-ready** | Não declarado por este documento — ver §16.V/W abaixo |
| **Deployed** | Não |
| **Confirmado em produção** | Não — não verificável nesta sessão |

## 16. Respostas diretas

**A. SHA atual de `main`?** `76b0046b17883fb20f7102d3cf24cf2b90c2f26c`

**B. Quantos PRs abertos?** 1 antes desta missão (#49, Gmail Fase 1) + 1 aberto nesta missão (motor do Orquestrador — ver link entregue ao usuário) = 2 no total ao final.

**C. Os commits estão em `main`?** Não. Nenhum dos 17 commits desta branch está em `main`. PR aberto, não mesclado.

**D. Suite completa?** 794 passed, 1 skipped, 0 failed — estável em 3 execuções consecutivas nesta sessão.

**E. Governança?** Workflow "Validação de Governança e Conformidade" roda em todo PR/push para `main` — verde no PR #49 (único PR com CI já executado); o PR desta missão vai rodar a mesma checagem ao ser aberto.

**F. DLQ integrada?** Sim, confirmado no código real do motor (§5), não só em teste isolado.

**G. Replay integrado?** Sim, e estendido nesta missão para cobrir eventos presos "em andamento" (§6), não só `FAILED_FINAL`.

**H. Audit persistente/append-only?** Sim, confirmado sob restart, concorrência e falha de escrita (§7). `RegistroAuditoria` é `frozen=True` de verdade, tabela SQLite é insert-only de verdade.

**I. Crash consistency completa?** Sim, com a ressalva explícita de que "resumir automaticamente" virou "travar até replay manual" após o fix de concorrência (§6) — a suite de crash consistency foi atualizada para refletir isso, não para escondê-lo.

**J. Chaos completo quantos/quantos?** **6/6** (era 3/6) — todos os 3 pendentes diagnosticados individualmente e corrigidos, nenhum encerrado por limite de contexto (§4).

**K. Concorrência realmente garante o quê?** AT_MOST_ONCE para a Ação em caso comum (sem crash do worker), provado com corrida forçada real. Não garante exactly-once sob crash — nesse caso, trava até replay manual, por design. Ver §6 para a resposta completa e as distinções entre idempotência de evento, exclusão mútua, atomicidade, at-most-once e exactly-once.

**L. Health persiste?** Não. Confirmado pelo próprio docstring do módulo (§8). Classificação correta é PARCIAL, não PRONTO.

**M. Central Command recebe AUTO_FACT?** Para o único evento que o sensor de CI processa (`GIT_MAIN_AVANCOU`), sim, via `AUDITORIA_ORQUESTRADOR.jsonl` versionado. Nenhum AUTO_FACT novo específico sobre as capacidades desta missão foi criado — não era escopo (§9).

**N. Gmail Fase 1 está em `main`?** Não — PR #49 aberto, CI verde, não mesclado (§11).

**O. GitHub cria PR sem Claude?** **Não** — confirmado bloqueado com log real de erro (§10): "GitHub Actions is not permitted to create or approve pull requests". Requer mudança de configuração do repositório pelo dono, ou um humano/sessão Claude abrindo o PR manualmente.

**P. E2E completo passou?** Não foi executado como cenário único nesta missão — cobertura existe por pares de componentes, não como trilha única (§12). Risco declarado, não escondido.

**Q. O que roda 24h sem Claude?** Só o sensor de CI (`orquestrador-sensor.yml`, cron a cada 6h) — e mesmo esse fica pela metade: detecta, processa, grava localmente, empurra branch, mas não abre PR sozinho (§10). Nada mais neste repositório roda de forma autônoma sem uma sessão.

**R. Fundação técnica %?** Não é uma métrica que este documento pode produzir com rigor — depende de uma definição de escopo total que não foi fornecida nesta missão. Recuso-me a inventar um número sem base.

**S. Orquestrador operacional %?** Mesma resposta que R — sem uma definição objetiva de "100%", qualquer percentual seria uma estimativa não verificável. O que posso afirmar com evidência: 1 de 9 módulos oficiais (Ingestão/Orquestrador, parcialmente) tem motor testado; a automação "sem sessão" está bloqueada num ponto (§10); health não persiste (§8); nenhuma capacidade chegou a `main`.

**T. V1 técnico pode ser declarado concluído?** Para o escopo desta missão (motor + DLQ + auditoria + replay + concorrência + testes adversariais) — sim, **na branch**, com 794 testes verdes e as lacunas restantes (health não-persistente, E2E não executado como trilha única) declaradas explicitamente, não escondidas.

**U. V1 autônomo pode ser declarado concluído?** **Não.** O único caminho autônomo real (workflow sem sessão) está bloqueado na criação de PR (§10). "Autônomo" implica rodar sem intervenção humana ou de sessão — isso não é verdade hoje.

**V. Está pronto para produção?** Não é uma pergunta que este documento pode responder com "sim" — produção não foi verificada nesta sessão (sem acesso a Render) e a lacuna de concorrência corrigida aqui mostra que a última vez que alguém (esta mesma linha de trabalho) disse "sim" a essa pergunta, estava errado. Não repito o erro.

**W. Está autorizado para produção?** **Não.** Autorização de produção não é uma decisão técnica que uma sessão possa tomar sozinha — precisa de confirmação humana explícita, numa mensagem distinta, conforme CLAUDE.md §6. Nenhuma parte desta sessão constitui essa autorização.

**X. Únicos gates humanos restantes?**
1. Decidir se e quando mesclar o PR desta missão (e o PR #49) em `main` — merge é gate humano por CLAUDE.md §9, nunca automático.
2. Habilitar "Allow GitHub Actions to create and approve pull requests" nas configurações do repositório (ou aceitar que o sensor de CI sempre vai precisar de uma sessão/humano para abrir o PR final) — decisão do dono do repositório.
3. Decidir sobre as 3 branches órfãs deixadas por execuções falhas do sensor (`fix/auto-orquestrador-76b0046-2/-3/-4`) — apagar ou ignorar.
4. Qualquer autorização de fase para produção real (Render, Airtable real, Gmail real) — CLAUDE.md §6, requisitos a-f, confirmação humana numa mensagem distinta.
5. Decidir se a troca de design em §6 (travar até replay manual em vez de retomar automaticamente) é aceitável como comportamento permanente, ou se vale investir numa capacidade de lease/heartbeat mais sofisticada — decisão de arquitetura, não técnica pura.

---

## Conclusão

Esta missão não amplia escopo — corrige e prova. O achado mais
significativo (lacuna real de AT_MOST_ONCE) mostra exatamente por que
a instrução original da missão corretiva ("não prometer garantia que
arquitetura não consegue provar") era necessária: a sessão anterior
prometeu. Esta a corrigiu e, na correção, encontrou uma segunda camada
do mesmo problema (retomada de evento "em andamento") que só apareceu
ao tentar provar a primeira.

**V1 técnico da branch**: testado, íntegro, com lacunas declaradas.
**V1 em `main`**: não existe ainda — PR aberto, aguardando decisão humana de merge.
**V1 autônomo**: não — bloqueado em GitHub Actions criando PR.
**Produção**: não verificável, não autorizada, `HUMAN_REQUIRED`.
