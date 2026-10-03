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

Entram como dependências transitivas de `pdfplumber`. São o que renderiza
a prévia de assinatura. Uma atualização silenciosa numa build do Render
quebra a tela que 100+ colaboradores usam para assinar — sem nenhuma
mudança de código do projeto.

### RSK-006 — `--workers 2` pode não estar em vigor

`Procfile` e `render.yaml` declaram 2 workers. O log mostrava
`WEB_CONCURRENCY=1 by default`. Se o serviço foi criado à mão no Render,
o Start Command do painel sobrepõe o `Procfile` — e o ajuste de
capacidade some em silêncio, que é exatamente o que o comentário no
`render.yaml` alerta.

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

`render.yaml` tem bloco `databases:` com `plan: free` marcado como
placeholder — e o próprio arquivo avisa que o tier gratuito expira e não
serve para persistência durável. Os adapters existem; o banco não. O
registro oficial continua sendo o Airtable.

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
| RSK-005 | Não | ✅ Sim | Fixar versões |
| RSK-006 | Não | ✅ Sim | Verificar painel do Render |
| RSK-007 | Não | ✅ Sim | Rotacionar chave |
| RSK-008 | Não | ✅ Sim | Continuar a migração |
| RSK-009 | Não | ✅ Sim | Decisão de produto |
| RSK-010 | Não | Não | Aceitar ou instrumentar |
| RSK-011 | Não | Não | Decisão financeira |
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
Não há `pytest-cov`/`coverage` em `requirements.txt` nem configuração de
pytest no repositório. "CI verde" hoje significa só "todos os testes
existentes passaram" — código novo sem teste correspondente passa
despercebido, sem nenhum sinal objetivo de que não foi exercitado.

### RSK-018 — regressão em integração real fora de `alocacao`/`autenticacao`
O job `testes` do `magnata-testes.yml` é inteiramente mockado por
desenho (decisão deliberada pós-incidente de 2026-08-17). O job
`postgres-real` cobre só os módulos `alocacao` e `autenticacao` contra
um Postgres efêmero. Nenhum outro adapter externo (Airtable, WhatsApp/
Evolution, Gmail, S3/R2, Secullum) tem validação "real" em CI — uma
quebra de contrato com qualquer um desses serviços só aparece em
produção.

### RSK-019 — `/health` sempre HTTP 200, mesmo com dependência fora do ar
`/health` (`app.py`) faz uma chamada real ao Airtable e devolve
`airtable_ok`/`airtable_status` no corpo, mas **sempre responde 200**,
mesmo quando `airtable_ok` é `false`; não verifica Postgres; e
`render.yaml` não declara `healthCheckPath`. Um deploy pode "ficar
verde" no painel do Render com a aplicação funcionalmente degradada.
Corrigir o comportamento de `/health` mexe em `app.py` — legado
protegido, `CLAUDE.md` §7: exige autorização humana específica numa
mensagem distinta antes de qualquer PR nessa frente.

### RSK-020 — degradação do Orquestrador nunca vira vermelho em CI
O passo shadow do `orquestrador-sensor.yml` (supervisor de saúde/DLQ/
recovery) só publica um artifact — por desenho, documentado no próprio
workflow ("nunca reivindica retry, nunca chama Ação, nunca altera
sistemas externos"). Um DLQ crescendo run após run não aciona nenhum
alarme; alguém precisa abrir o artifact manualmente para notar.

### RSK-021 — nenhum alerta automático de exceção em produção
Sem Sentry/Rollbar/Bugsnag/Datadog ou equivalente em nenhum lugar do
código. Toda observação de exceção depende de `logger` e do log do
próprio Render, já registrado como parcial e rotativo (RSK-010). Esta é
a razão estrutural pela qual RSK-018/RSK-019/RSK-020 podem continuar
invisíveis por muito tempo depois de acontecerem — lacuna de
*detecção*, não um gate que deveria ter pego e não pegou.

### Reconfirmado, ainda aberto

- **RSK-011 (Postgres declarado e não provisionado)** — reconfirmado em
  2026-10-03 pela auditoria de Airtable/Postgres em thread paralela:
  `render.yaml` continua declarando blocos que podem não estar
  aplicados (plano free). **Pergunta ainda sem resposta verificada por
  esta sessão:** se o Postgres de produção (`magnata-os-db`) foi de fato
  provisionado no Render, se a migration do cadastro de colaborador
  persistente (PR #215) foi aplicada em banco real, e se algum cron do
  Orquestrador roda de fato no Render. Nenhuma ferramenta desta sessão
  alcança o painel do Render para confirmar — tratar como `LIVE_STATE`,
  não herdar suposição de nenhuma nota anterior.
