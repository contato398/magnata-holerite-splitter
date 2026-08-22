# NEXT_ACTIONS — sequência recomendada

**Etapa 3, 2026-08-22.** Ordem por **risco de perda irreversível**
primeiro, depois por desbloqueio. Cada item diz quem decide.

**Nenhum item abaixo foi executado.** Todos cruzam um gate humano de
`CLAUDE.md` §9/§12-I ou uma instrução explícita desta missão ("não
resgate automaticamente documentos antigos para `main`").

---

## Bloco 1 — parar a sangria (gate humano, alta urgência)

### NXT-001 · Preservar `docs/historico/` em `main`
**Risco:** RSK-001 · **Esforço:** baixo · **Toca código?** não

31 arquivos de memória operacional presos numa branch 106 commits
atrás. Branch nova a partir de `main`, `git checkout
fix/recibos-outros-documentos -- docs/historico/`, PR só de documentação.

⚠️ `ALLOWED_PATHS` **não cobre** `^docs/historico/` — precisa de entrada
nova em `.magnata/patterns.sh` no mesmo PR, ou os arquivos vão para
`docs/magnata-os/historico/`, que já é coberto.

**Decide:** você. **Depois disso**, e só depois, faz sentido discutir o
destino da branch.

### NXT-002 · Resgate documental da fundação
**Risco:** RSK-002 · **Esforço:** médio · **Toca código?** não

10 documentos, 9.600 linhas, 26 decisões aprovadas pela Direção.
Estratégia completa em [`FOUNDATION.md`](FOUNDATION.md) §9: branch nova
a partir de `main`, `git checkout` por arquivo (nunca merge da branch
antiga), 3 divergências conhecidas viram nota, e os 13 links quebrados
de `README.md` são corrigidos no mesmo PR.

**Decide:** você — inclusive se os documentos entram como estão (com
nota) ou revisados.

### NXT-003 · Versionar os relatórios da Macro 6A
**Risco:** RSK-003 · **Esforço:** baixo · **Toca código?** não

Ver [`MACRO_6A.md`](MACRO_6A.md). Envolve decidir o que é registro
institucional e o que é ruído de sessão.

---

## Bloco 2 — desbloquear o que já está pronto

### NXT-004 · Decidir o PR #20
**Risco:** RSK-004 · **Esforço:** baixo · **Toca código?** ✅ `app.py`

Melhor relação custo/benefício do inventário: 2 arquivos, +17/−16, e
limpa 6 vermelhos permanentes da suíte. Está 18 commits atrás — precisa
de rebase antes.

**Decide:** você (§7 — `app.py` é legado protegido).

### NXT-005 · Decidir o PR #22
**Esforço:** baixo · **Toca código?** não toca `app.py`

Aditivo: plano de consolidação + adapter de e-mail que roda **em
paralelo** ao Gmail Apps Script, sem substituir nada. Registra também a
regra "não construir nada novo no Make.com". Sem ele, a próxima sessão
refaz a mesma análise do zero.

### NXT-006 · Decidir as 3 branches paradas
Fase 5 (painel visual, pronta há ~4 semanas, 72 commits atrás) ·
`fix/adr-modulo01-http-wiring` (ADR da fiação HTTP) ·
`claude/evolution-api-instances-1s9raa` (conteúdo já em #22).

---

## Bloco 3 — fechar produção

### NXT-007 · Confirmar `--workers 2` no painel do Render
**Risco:** RSK-006. Só olhar o Start Command. Se o painel sobrepõe o
`Procfile`, o ajuste de capacidade nunca entrou em vigor.

### NXT-008 · Fixar `pypdfium2` e `Pillow` no `requirements.txt`
**Risco:** RSK-005 · **Toca código?** só `requirements.txt`.
Uma atualização silenciosa quebra a tela de assinatura em produção.

### NXT-009 · Rotacionar a `EMAIL_WEBHOOK_KEY`
**Risco:** RSK-007 · gate de credencial.

### NXT-010 · Fechar o ciclo de Julho/2026
Resultado do disparo dos 25 pendentes · `log_reenvio_julho2026.csv` ·
janela de log do Render de 20/08 entre 15:30 e 16:19 · WhatsApp sem DDI
55 · os 11 casos deferidos (9 sem Folha de Ponto, 1 sem Holerite, 1 com
WhatsApp inválido).

---

## Bloco 4 — decisões de arquitetura e negócio

### NXT-011 · Responder as 3 decisões `PENDENTE` há um mês
`DEC-ENT-010` (Alerta de Ponto vira Pendência Documental?) ·
`DEC-ENT-011` (`Fechamento` e `SBJ`) · `DEC-ENT-012` (`Finalizado` e
`Pronto` existem no Airtable?). **Só a Direção da Magnata pode.**
`DEC-ENT-020` depende de `012`.

### NXT-012 · Decidir a ADR-001
Quatro alternativas, recomendação não vinculativa (C). Em aberto desde
julho. A `VALIDAÇÃO 12` do `pre-commit` impede que se resolva sozinha —
por desenho.

### NXT-013 · Decidir a taxonomia de núcleos
Existem hoje **três** recortes: 9 módulos (`ARQUITETURA` §2, 2026-07-22),
10 módulos (`MODULOS.md`, 2026-07-25, vigente) e 8 núcleos de negócio
(Documental, RH, Financeiro, Contábil/Fiscal, Comercial, Operações,
Marketing, Diretoria/BI). Os dois primeiros têm trilha de sucessão
resolvida. **O terceiro não tem ADR.**

Antes de arquitetura: **Financeiro, Comercial, Marketing e Diretoria/BI
já operam fora deste repositório (outra ferramenta, processo manual), ou
são aspiracionais?** A resposta muda tudo — no primeiro caso é
integração, no segundo é construção.

### NXT-014 · Instalar os hooks onde não estão
**Risco:** RSK-012. Duas branches receberam commits que os gates
rejeitariam. Barreira local só protege onde está instalada.

### NXT-015 · Avaliar o Graphify (sem instalar)
Confirmar o que extrai de fato, se roda local e read-only, e onde o
resultado seria versionado. A fronteira já está desenhada: **Central
Command** = memória/decisão/proveniência · **Graphify** = visão
verificável do código · **Airtable/bancos** = dados operacionais ·
**GitHub** = histórico técnico · **produção** = verdade de execução.

---

## Caminho crítico

```
NXT-001 ─┐
NXT-002 ─┼─► memória segura ─► NXT-013 ─► arquitetura dos núcleos
NXT-003 ─┘                        ▲
                                  │
NXT-004 ─► suíte limpa ───────────┘
NXT-005 ─► direção do Módulo 01
```

**NXT-001 e NXT-002 não têm dependência de nada e travam tudo que vem
depois.** Enquanto a fundação e a memória histórica estiverem numa
branch, qualquer decisão de arquitetura é tomada sem acesso às 26
decisões que a Direção já aprovou.

---

## Etapa 6 — reordenação por evidência (2026-08-22)

✅ **Concluídos:** NXT-002 (fundação em `main`) · NXT-001 parcial (lição
preservada; bruto pendente) · NXT-015 (Graphify avaliado com POC).

### Nova ordem por valor × risco

| # | Ação | Por quê agora | Gate |
|---|---|---|---|
| **1** | **Aplicar a correção de `_status_funcionario_elegivel`** | Provado: leva a suíte de 636/6 para **642/0**. Patch aplica limpo em `main` | 🔴 `app.py` (§7) |
| **2** | **Criar CI que rode a suíte** (RSK-013) | Sem isso, o item 1 volta a acontecer sem ninguém ver | 🟠 `.github/workflows/` |
| **3** | **Auditar as automações nativas do Airtable** (RSK-014) | Lógica de negócio invisível; bloqueia qualquer migração séria | 🟢 Leitura |
| **4** | Decidir o PR #22 (adapter de e-mail) | Aditivo, não toca `app.py` | 🟡 |
| **5** | Auditar a Fase 5 (RSK-016) | ~50 arquivos parados há 4 semanas | 🟢 Leitura |
| **6** | Fixar `pypdfium2` e `Pillow` | Quebra a tela de assinatura em produção sem aviso | 🟡 `requirements.txt` |
| **7** | Confirmar `--workers 2` no painel do Render | Não verificável desta sessão (rede bloqueada) | 🔴 Produção |
| **8** | Definir retenção de dado pessoal | Destrava a memória sensível | 🔴 Negócio |
| **9** | Responder `DEC-ENT-010/011/012` | Pendentes há um mês; `DEC-ENT-020` depende de `012` | 🔴 Direção |
| **10** | POC do Graphify sobre `app.py` | É onde ele paga o custo — 12.301 linhas que não cabem no contexto | 🟢 Isolado |
| **11** | Plano do Postgres | `free` não serve; bloqueia a Fase 2 do Airtable | 🔴 Custo |
| **12** | ADR da taxonomia de núcleos | Agora com evidência: Financeiro e Comercial **existem**, fora do repo | 🔴 Arquitetura |
