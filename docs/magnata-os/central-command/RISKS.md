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
