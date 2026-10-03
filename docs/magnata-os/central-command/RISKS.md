# RISKS — riscos priorizados

**Etapa 3, 2026-08-22.** Ordenados por **irreversibilidade**, não por
esforço nem por probabilidade. Um risco de perda permanente vem antes de
um bug corrigível.

---

## 🔴 Perda permanente de conhecimento

### RSK-001 — `docs/historico/` existe em um único lugar

31 arquivos, 30 registros de memória operacional (12/06 a 01/07/2026):
decisões da diretoria, bugs encontrados e corrigidos, regras de negócio
descobertas na prática. Vive só em `fix/recibos-outros-documentos`,
commit `1027fc8`, branch **106 commits atrás** de `main` e já classificada
por engano como obsoleta uma vez.

**Se a branch for apagada, a perda é total e não recuperável.** E
branches remotas deste repositório *são* apagadas — aconteceu nesta
sessão com `claude/macro-6a-commit-recovery-k7rsly`.

**Mitigação parcial já aplicada:** o SHA está registrado em
[`PRS_AND_BRANCHES.md`](PRS_AND_BRANCHES.md) §3.
**Mitigação real:** preservar em `main`. Gate humano.

### RSK-002 — a fundação documental existe em um único lugar

10 documentos, 9.600 linhas, incluindo **26 decisões aprovadas pela
Direção em 2026-07-22** e os 4 Modelos Conceituais oficiais. Só em
`feat/magnata-os-claude-powerpack`, PR **#12 fechado sem merge**.

Agravante: `CLAUDE.md` §2 manda desempatar conflito por
`MAGNATA_OS_CONTRATOS.md` e `MAGNATA_OS_ESTADOS.md` — **a regra de
precedência do projeto aponta para arquivos que não existem em `main`**.
E `docs/magnata-os/README.md`, que está em `main`, tem 13 links quebrados.

### RSK-003 — os relatórios da Macro 6A nunca foram versionados

7 relatórios + bundle de 1,4 MB, só em scratch de sessão. O conteúdo
técnico está salvo em `main`; o registro de **como** publicar trabalho
a partir de um ambiente sem credenciais, não.

---

## 🟠 Defeito conhecido em produção ou na suíte

### RSK-004 — 6 falhas vermelhas mascaram regressão nova

`test_pacote_assinatura_holerite_ponto.py`: a função real devolve
`'status_veio_inativo'`, o teste e o resto do sistema esperam
`'vinculo_nao_ativo'`. O bloqueio funciona — o rótulo diverge.

**O risco não é o bug; é o ruído.** Com 6 vermelhos permanentes,
ninguém distingue "as de sempre" de uma regressão nova. A correção
existe pronta no PR #20 desde 2026-08-17.

### RSK-005 — `pypdfium2` e `Pillow` não estão fixados

~~Entram como dependências transitivas de `pdfplumber`. São o que
renderiza a prévia de assinatura. Uma atualização silenciosa numa build
do Render quebra a tela que 100+ colaboradores usam para assinar — sem
nenhuma mudança de código do projeto.~~

✅ **RESOLVIDO** — [PR #226](https://github.com/contato398/magnata-holerite-splitter/pull/226)
(mesclado, 2026-10-03) fixa `pypdfium2==5.13.0` e `pillow==12.3.0` em
`requirements.txt`. Suíte completa validada antes do push (3183
passed/112 skipped/0 falhas).

### RSK-006 — `--workers 2` pode não estar em vigor

~~`Procfile` e `render.yaml` declaram 2 workers. O log mostrava
`WEB_CONCURRENCY=1 by default`. Se o serviço foi criado à mão no Render,
o Start Command do painel sobrepõe o `Procfile` — e o ajuste de
capacidade some em silêncio, que é exatamente o que o comentário no
`render.yaml` alerta.~~

**CONFIRMADO em 2026-10-03 via API do Render** (Frente "infra e operação
24×7", `infra-operacao-24x7.md`): o serviço real (`srv-d8iqj3uk1jcs73ap1np0`,
plano `starter`) foi mesmo criado à mão e seu Start Command real é
`--workers 1 --max-requests 50` (sem `--max-requests-jitter`) —
divergente tanto de `render.yaml`/`Procfile` quanto do que este risco
registrava. `render.yaml` já foi corrigido para refletir o valor real
(PR da Frente E). **Não decidido:** se `--workers 1` é intencional
(limite de RAM do plano `starter`) ou resíduo — decisão de capacidade de
produção, gate humano (`CLAUDE.md` §12-I), não tomada por nenhuma
frente.

### RSK-007 — `EMAIL_WEBHOOK_KEY` com comportamento não explicado

Um disparo retornou 401 na primeira mensagem; uma sonda de risco zero
devolveu 400 (chave válida). A divergência nunca foi fechada.
Confirmado em código que a chave é validada **antes** de qualquer envio
— nenhuma mensagem saiu.

---

## 🟡 Estrutural — declarado, aceito, não resolvido

### RSK-008 — lógica crítica dentro do monólito

Cálculo de ponto, geração de holerite e distribuição seguem em `app.py`
(12.301 linhas). Risco "Crítico" declarado pelo próprio
`MAGNATA_OS_MODULOS.md` §12. É consequência aceita do strangler pattern
— vira problema se a migração parar.

### RSK-009 — cinco lacunas do fluxo de assinatura

Sem caminho para corrigir disparo errado · sem lembrete automático ·
links não expiram · sem painel de RH · 4 dígitos de CPF como
autenticação de documento trabalhista.

### RSK-010 — Airtable não registra visualização

Só assinatura concluída e tentativa de CPF errado. **"Ausente do log"
nunca prova "nunca clicou".** Toda análise de engajamento depende do log
do Render, que é parcial e rotativo.

### RSK-011 — Postgres declarado e não provisionado

~~`render.yaml` tem bloco `databases:` com `plan: free` marcado como
placeholder — e o próprio arquivo avisa que o tier gratuito expira e não
serve para persistência durável. Os adapters existem; o banco não. O
registro oficial continua sendo o Airtable.~~

**SUPERADO em parte — confirmado via API do Render em 2026-10-03**
(`infra-operacao-24x7.md`, Frente E): o Postgres de produção **já existe**
— `magnata-os-postgres` (`dpg-d9t3ig8n74is73fu2cl0-a`), plano
`basic_256mb`, estado `available`. Foi provisionado **manualmente**, não
por Blueprint (`GET /v1/blueprints` retorna vazio para esta conta) — ou
seja, `render.yaml` não governa esse banco; é documentação, não a fonte
real. O bloco `databases:` com `plan: free` neste arquivo é um
placeholder desatualizado em relação ao banco real, não uma previsão de
risco financeiro ainda pendente. **O que continua de fato não
provisionado:** o Cron Job do Orquestrador
(`magnata-orquestrador-ciclo-producao`) — confirmado ausente da lista
real de serviços na mesma investigação. Ver RSK-011-bis abaixo para o
que isso implica.

### RSK-011-bis — Cron do Orquestrador confirmado não provisionado

Nenhum serviço com o nome `magnata-orquestrador-ciclo-producao` existe
no Render (confirmado via API, 2026-10-03). O bloco `cron:` em
`render.yaml` é só declaração. Plano de ativação já pronto e revisado em
`plano-provisionamento-cron-orquestrador.md` — mapa de outra frente, não
versionado neste repositório; falta decisão financeira (custo do Cron
Job no Render, não verificado) e autorização de produção específica
(`CLAUDE.md` §12-I) antes de provisionar.

### RSK-012 — governança contornável por ausência de hooks

Duas branches receberam commits que os gates rejeitariam (branch não
autorizada, caminhos fora de `ALLOWED_PATHS`). Os hooks são locais: se
não estiverem instalados, não protegem. O CI cobre PRs — não cobre
trabalho que nunca vira PR.

---

## Matriz

| ID | Irreversível? | Afeta produção? | Ação disponível hoje |
|---|---|---|---|
| RSK-001 | ✅ Sim | Não | Gate humano — preservar |
| RSK-002 | ✅ Sim | Indireto | Gate humano — resgate documental |
| RSK-003 | ✅ Sim | Não | Gate humano — versionar |
| RSK-004 | Não | Não | PR #20 pronto |
| RSK-005 | Não | ✅ Sim | ✅ Resolvido — PR #226 mesclado |
| RSK-006 | Não | ✅ Sim | Confirmado via API (2026-10-03): decisão de capacidade pendente |
| RSK-007 | Não | ✅ Sim | Rotacionar chave |
| RSK-008 | Não | ✅ Sim | Continuar a migração |
| RSK-009 | Não | ✅ Sim | Decisão de produto |
| RSK-010 | Não | Não | Aceitar ou instrumentar |
| RSK-011 | Não | Não | Postgres confirmado provisionado (2026-10-03); cron ainda não (decisão financeira) |
| RSK-012 | Não | Não | Instalar hooks / exigir PR |

---

## Etapa 6 — 2026-08-22, pós-merge

### Resolvidos

- **RSK-002 (fundação em uma única branch)** → ✅ **ELIMINADO.** Está em `main` (`9f8a53f`).
- **RSK-001 (memória histórica)** → 🟡 **REDUZIDO.** A lição está em `main`; o texto bruto com PII continua dependendo da branch.

### Novos

### RSK-013 — nenhum CI roda a suíte de testes
`.github/workflows/` tem **um** workflow, de governança. **Nada executa
`pytest`.** As 6 falhas reais estão em `main` desde 2026-08-17 e nenhuma
automação as apontaria. É a causa de fundo de RSK-004 continuar aberto.
**Correção é barata:** um job que instala `requirements.txt` e roda a
suíte. Toca `.github/workflows/` — decisão de governança.

### RSK-014 — regra de negócio dentro do Airtable, não versionada
Campos como `ESTE MES`, `Mes passado?` e lookups de competência são
lógica avaliada na leitura, **fora do Git**: sem PR, sem teste, sem
auditoria. Uma migração que só copie dados perde essa lógica sem
perceber. Ver [`AIRTABLE_DESACOPLAMENTO.md`](AIRTABLE_DESACOPLAMENTO.md) §4.

### RSK-015 — tabelas nomeadas por competência
`Sem_Batida_Julho_2026`, `Fechamento_Mai_Jun_2026`: o mês está no **nome
da tabela**, não num campo. Não escala e contraria o Contrato de
Competência já definido em `MAGNATA_OS_CONTRATOS.md`.

### RSK-016 — Fase 5 parada com ~50 arquivos
`feat/...modulo01-fase5-painel` carrega um frontend inteiro (componentes,
views, testes) parado desde 2026-07-25, **77 commits atrás de `main`** e
nunca auditado em profundidade. Quanto mais tempo passa, mais caro fica
reconciliar.

### Reclassificado

- **RSK-004** deixa de ser "6 falhas mascarando regressão" e passa a ser
  **"6 falhas com correção provada e nenhum CI que as detecte"** — a
  correção leva a suíte a **642/0**, verificado em worktree isolado.

---

## Etapa 15 — 2026-10-03, catch-up pós-PR #225

Esta seção **acrescenta**; nada acima foi reescrito (`CLAUDE.md` §2/§4).
Fonte: `testes-ci-observabilidade.md` (auditoria de legado, thread
paralela desta mesma sessão de coordenação, só investigação — nenhum
código alterado para produzi-la) e reconfirmação direta nesta sessão.

### Observação de desatualização — RSK-013

**RSK-013 ("nenhum CI roda a suíte de testes") está superado, não
corrigido por este PR.** `.github/workflows/magnata-testes.yml` já
instala dependências e roda `pytest -q` em PR→`main`/push→`main` — a
auditoria de 2026-10-03 confirma isso no inventário de workflows. O
texto de RSK-013 acima não foi reescrito (histórico append-only); esta
nota só registra que a lacuna que ele descreve já foi fechada em algum
PR entre 2026-08-22 e agora, não identificado nesta auditoria (fora do
escopo: seria preciso vasculhar ~70 PRs para achar qual).

### Novos

### RSK-017 — sem medição de cobertura de testes
~~Não há `pytest-cov`/`coverage` em `requirements.txt` nem configuração
de pytest no repositório. "CI verde" hoje significa só "todos os testes
existentes passaram" — código novo sem teste correspondente passa
despercebido, sem nenhum sinal objetivo de que não foi exercitado.~~

**Correção pronta, não mesclada** — [PR #233](https://github.com/contato398/magnata-holerite-splitter/pull/233)
adiciona `pytest-cov` ao job `testes` (`--cov=.`, resumo no Step
Summary, `coverage.xml` como artifact). Sem `--cov-fail-under` — é
relatório, não um gate novo. Cobertura agregada medida: 86%. Verde,
pronto; não mesclado porque toca `.github/workflows/`, caminho crítico
que exige aprovação humana no GitHub Environment `governance-approval`
por desenho do próprio repositório — e porque o coordenador represou
todos os merges desta leva até o Magnata decidir a tensão entre "merge
autônomo com CI verde" e `CLAUDE.md` §9.

### RSK-018 — regressão em integração real fora de `alocacao`/`autenticacao`
O job `testes` do `magnata-testes.yml` é inteiramente mockado por
desenho (decisão deliberada pós-incidente de 2026-08-17). O job
`postgres-real` cobria só os módulos `alocacao` e `autenticacao` contra
um Postgres efêmero. Nenhum outro adapter externo (Airtable, WhatsApp/
Evolution, Gmail, S3/R2, Secullum) tem validação "real" em CI — uma
quebra de contrato com qualquer um desses serviços só aparece em
produção.

**Parcialmente endereçado, não mesclado** — [PR #238](https://github.com/contato398/magnata-holerite-splitter/pull/238)
adiciona ao job `postgres-real` um teste e2e real de distribuição
documental que já existia mas nunca estava listado (sempre pulado pelo
job mockado). Continua sem cobertura real de WhatsApp/Evolution, Gmail,
S3/R2 ou Secullum — risco reduzido, não eliminado. Mesma situação de
merge represado do RSK-017.

### RSK-019 — `/health` sempre HTTP 200, mesmo com dependência fora do ar
`/health` (`app.py`) faz uma chamada real ao Airtable e devolve
`airtable_ok`/`airtable_status` no corpo, mas **sempre responde 200**,
mesmo quando `airtable_ok` é `false`; não verifica Postgres. Um deploy
pode "ficar verde" no painel do Render com a aplicação funcionalmente
degradada. **Ainda não corrigido** — corrigir o comportamento de
`/health` mexe em `app.py`, legado protegido (`CLAUDE.md` §7): exige
autorização humana específica numa mensagem distinta, ainda não dada.
Diff já preparado e descrito (não implementado) em
`testes-ci-observabilidade.md` §5 "Item 3".

**Atualização 2026-10-03 (Frente "infra e operação 24×7", confirmado via
API do Render):** `render.yaml` já declara `healthCheckPath: /health`,
mas **sem efeito sobre o serviço real** — nenhum Blueprint foi aplicado,
e o serviço real confirmado no painel do Render está com
`healthCheckPath` vazio. Ou seja, mesmo o `/health` sempre-200 não está
hoje decidindo saúde/substituição de instância no Render; a declaração
em `render.yaml` só passa a valer no dia em que alguém rodar um
Blueprint — ação de produção, gate humano separado.

### RSK-020 — degradação do Orquestrador nunca vira vermelho em CI
O passo shadow do `orquestrador-sensor.yml` (supervisor de saúde/DLQ/
recovery) só publicava um artifact — por desenho, documentado no
próprio workflow ("nunca reivindica retry, nunca chama Ação, nunca
altera sistemas externos"). Um DLQ crescendo run após run não acionava
nenhum alarme; alguém precisava abrir o artifact manualmente para
notar.

**Correção pronta, não mesclada** — [PR #234](https://github.com/contato398/magnata-holerite-splitter/pull/234)
faz o workflow ler o snapshot já escrito e publicar `::warning::` +
Step Summary quando a saúde não é `VERDE` ou há DLQ/retry vencido > 0.
Continua shadow puro — nenhum `exit != 0`, nenhum gate novo (este
workflow nunca bloqueou merge) — mas agora pelo menos avisa visivelmente
em vez de exigir abrir o artifact manualmente. Mesma situação de merge
represado do RSK-017/RSK-018.

### RSK-021 — nenhum alerta automático de exceção em produção
Sem Sentry/Rollbar/Bugsnag/Datadog ou equivalente em nenhum lugar do
código. Toda observação de exceção depende de `logger` e do log do
próprio Render, já registrado como parcial e rotativo (RSK-010). Esta é
a razão estrutural pela qual RSK-018/RSK-019/RSK-020 podem continuar
invisíveis por muito tempo depois de acontecerem — lacuna de
*detecção*, não um gate que deveria ter pego e não pegou.

### Reconfirmado, ainda aberto (nota original desta seção — ver correção abaixo)

- ~~**RSK-011 (Postgres declarado e não provisionado)** — reconfirmado em
  2026-10-03 pela auditoria de Airtable/Postgres em thread paralela:
  `render.yaml` continua declarando blocos que podem não estar
  aplicados (plano free). **Pergunta ainda sem resposta verificada por
  esta sessão:** se o Postgres de produção (`magnata-os-db`) foi de fato
  provisionado no Render, se a migration do cadastro de colaborador
  persistente (PR #215) foi aplicada em banco real, e se algum cron do
  Orquestrador roda de fato no Render. Nenhuma ferramenta desta sessão
  alcança o painel do Render para confirmar — tratar como `LIVE_STATE`,
  não herdar suposição de nenhuma nota anterior.~~ **Superado horas
  depois, mesmo dia** — ver RSK-011 e RSK-011-bis acima (seção anterior,
  já corrigidos com os fatos confirmados via API do Render): o Postgres
  **está** provisionado (manualmente, `basic_256mb`); o Cron do
  Orquestrador **não** está. A migration do cadastro de colaborador
  persistente (PR #215) continua **não confirmada como aplicada** em
  banco real — nenhuma investigação até agora checou isso diretamente
  (rodar `\dt`/migration status contra o Postgres real é ação de
  produção, fora do alcance de uma auditoria só de documentação).

## Etapa 16 — 2026-10-03, reconciliação com a infraestrutura real (Render)

Fonte: `infra-operacao-24x7.md` (Frente "infra e operação 24×7",
levantamento direto via API do Render — `RENDER_API_KEY` injetada pelo
proxy, nunca impressa; nenhuma escrita em produção). Esta seção
**acrescenta**; RSK-011/RSK-006 acima já foram corrigidos in-line com
tachado, não reescritos silenciosamente.

### RSK-022 — Redis de produção nunca documentado, plano free sem persistência
O worker Celery usa um Redis real (`magnata-pdf-queue`,
`red-d9f2ttrbc2fs7390k2q0`) como broker e result backend — confirmado
via API e nos logs de boot do worker. Nunca apareceu em `render.yaml`
nem em nenhum mapa do projeto até esta investigação. Está no plano
`free` do Render (pode expirar/ser recriado por inatividade, sem alerta
no código se isso ocorrer) e com `persistenceMode: off` (qualquer tarefa
Celery enfileirada e não processada é perdida num restart do Redis). Não
verificado: se o fluxo de PDF (`tarefas_processar_pdf.py`) é
idempotente/reenfileirável o suficiente para tolerar essa perda.

### RSK-023 — worker com Auto-Deploy automático a cada merge em `main`
O serviço web foi criado com Auto-Deploy desligado (gate deliberado). O
worker tem Auto-Deploy **ligado** por commit em `main` — todo merge que
toca código que o worker importa já é, na prática, um deploy de
produção do worker, imediato e sem o mesmo gate que o web tem. Nenhum
erro encontrado nos logs recentes, mas isso significa que "merge
autônomo com CI verde" (autorizado nesta fase para trabalho técnico
reversível) pode estar silenciosamente pulando a distinção entre
"mesclar" e "fazer deploy" que `CLAUDE.md` §9/§12-I tratam como passos
separados, especificamente para o worker.

### RSK-024 — capacidade real do web divergente do declarado
Ver correção em RSK-006 acima: `--workers 1 --max-requests 50` real
contra `--workers 2 --max-requests 400 --max-requests-jitter 40`
declarado. Não decidido se é intencional (limite de RAM do plano
`starter`) ou resíduo de outra fase — decisão de capacidade de produção,
gate humano, não tomada por nenhuma frente até agora.
