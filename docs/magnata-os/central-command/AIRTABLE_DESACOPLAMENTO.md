# AIRTABLE — mapa de dependência e estratégia de desacoplamento

**Etapa 6 da Central Command, 2026-08-22.**
**Nenhum dado foi migrado, alterado ou escrito. Somente leitura de
schema — nomes de tabela e campo, zero registros, zero PII.**

Base `appaCpIVj7Q97VhFy` · **31 tabelas** lidas via schema.

---

## 1. Achado que corrige a Central Command

Rodadas anteriores classificaram **Financeiro** e **Comercial** como
"sem evidência". **Errado — e a correção importa.** A evidência não
estava no repositório porque **esses núcleos não vivem em código: vivem
no Airtable.**

| Núcleo | Tabelas encontradas | Nova classificação |
|---|---|---|
| **Financeiro** | `Pagamentos` (27 campos) · `Recebimentos` (16) · `Despesas` (38) · `Patrimônio` (10) | ✅ **EXISTE FORA DESTE REPOSITÓRIO** |
| **Contábil/Fiscal** | `Contabilidade Mensal` (42) · `Guias e Comprovantes` (21) · `Certidões` (16) · `FGTS Digital` (15) · `Escritórios Contabilidade` (7) | ✅ **EXISTE** — parte em código, parte só no Airtable |
| **Comercial** | `Clientes` (36) · `Locais` (22) | ✅ **EXISTE FORA DESTE REPOSITÓRIO** |
| **Marketing** | nenhuma | 🚫 **SEM EVIDÊNCIA** — confirmado nas duas fontes |
| **Diretoria/BI** | `DIA HOJE` (18) · `DIA QR CODE` (7) — parecem painéis operacionais | 🔍 **A CONFIRMAR** |

**Consequência:** o Magnata OS é maior do que o repositório desde
sempre. O Airtable não é só o banco do módulo documental — é o sistema
operacional de fato de metade da empresa.

---

## 2. As 31 tabelas por papel

**Núcleo documental/RH — fonte de verdade do que o código usa hoje:**
`Funcionários` (66 campos, a maior) · `Holerites` (25) ·
`Folha de Ponto` (50) · `Envios de Documentos` (46) ·
`Assinaturas Digitais` (18) · `Arquivos` (12) · `Processar Arquivos` (8) ·
`Emails Savian` (8) · `Outros documentos` (8) · `Pendências/Revisar` (8) ·
`Contratação/Recisão` (15) · `Férias` (20) · `Entrega EPI` (9) ·
`Extratos Mensais` (14)

**Ponto:** `Batidas de ponto` (16) · `Controle de Ponto` (6) ·
`Sem_Batida_Julho_2026` (10) · `Fechamento_Mai_Jun_2026` (16)

**Financeiro/Fiscal:** `Pagamentos` · `Recebimentos` · `Despesas` ·
`Contabilidade Mensal` · `Guias e Comprovantes` · `Certidões` ·
`FGTS Digital` · `Patrimônio` · `Escritórios Contabilidade`

**Cadastro:** `Clientes` · `Locais`

**Painéis:** `DIA HOJE` · `DIA QR CODE`

⚠️ **Sinal de dívida estrutural:** `Sem_Batida_Julho_2026` e
`Fechamento_Mai_Jun_2026` são **tabelas por competência** — o mês está
no *nome da tabela*, não num campo. Isso não escala e contraria o
Contrato de Competência já definido em `MAGNATA_OS_CONTRATOS.md`.

---

## 3. Campos com regra temporal — o que mais dói para migrar

Amostra verificada no schema:

- **Datas reais:** `Funcionários.Data de Admissão`,
  `Pagamentos.Data do Pagamento`, `Despesas.Data vencimento/pagamento`,
  `Certidões.Data Emissão/Vencimento/Pagamento`,
  `Guias.Data Emissão/Vencimento/Pagamento`, `Entrega EPI.Data Entrega/Devolução`
- 🔴 **Data duplicada como texto:** `Despesas.DATA ISO`,
  `Despesas.NUMERO_FATURA_DATA`, `Recebimentos.DATA ISO`,
  `Certidões.DATA TXT - EMISSAO`, `DATA TXT - VENCIMENTO`
- 🔴 **Tempo relativo materializado como campo:** `Despesas.Mes passado?`,
  `Despesas.ESTE MES`, `Guias.ESTE MES?`, `Guias.DATA HOJE`,
  `Clientes.IDA - EXTRATO MENSAL - MES PASSADO`,
  `Clientes.IDA - FGTS DIGITAL - mes passado`

**Por que isto é o item mais crítico da migração:** "este mês" e "mês
passado" são `lookup`/`formula` **avaliados no momento da leitura**.
Não têm histórico. Uma migração ingênua congela o valor do dia da
migração e **perde a semântica**. Em banco próprio isso vira consulta
sobre uma data real — nunca coluna.

E os campos `DATA TXT` / `DATA ISO` são a mesma data guardada duas vezes,
em formatos diferentes: **duas fontes de verdade para o mesmo fato**, com
risco de divergirem. Precisam colapsar em uma na migração.

---

## 4. Automações que dependem diretamente do Airtable

| Dependência | Onde | Acoplamento |
|---|---|---|
| `app.py` inteiro | Legado em produção | 🔴 **Total** — Field IDs literais no código |
| Apps Script de e-mail | Gmail → `/email/webhook` → `Emails Savian` | 🔴 Alto |
| `importacao_lote/adapters/airtable_*.py` | Módulo novo | 🟠 **Isolado por adapter** — é o modelo correto |
| Fórmulas/lookups de competência | Dentro do Airtable | 🔴 Alto — lógica de negócio fora do código |
| Automações nativas do Airtable | Dentro do Airtable | 🔍 **Não auditadas** |

🔴 **Risco de lock-in mais grave:** há **regra de negócio dentro do
Airtable** (fórmulas, lookups, campos "ESTE MES"). Isso não está
versionado, não passa por PR, não tem teste e não aparece em nenhuma
auditoria de código. Uma migração que só copie dados **perde essa
lógica** sem perceber.

---

## 5. Estratégia em 4 fases — nenhuma executada

### FASE 1 — Airtable permanece fonte principal *(estado atual)*
Nada muda operacionalmente. O trabalho é de **preparação**:
- Inventariar as automações e fórmulas nativas do Airtable — a lógica
  não versionada é o maior risco e ainda não foi auditada.
- Congelar a criação de novas tabelas por competência.
- Todo acesso novo passa por adapter, nunca driver direto
  (`CLAUDE.md` §3). O Módulo 01 já faz isso.
- ⚠️ **Bloqueador:** Postgres declarado em `render.yaml` com
  `plan: free`, marcado como placeholder e **não provisionado**. Sem
  banco real, a Fase 2 não começa. É decisão financeira.

### FASE 2 — Sincronização, Airtable ainda manda
- Provisionar Postgres real (gate humano, custo).
- Aplicar as migrations que já existem em
  `magnata_os/documental/modulo01/migrations/`.
- Espelhar em modo sombra, começando pelo **núcleo documental**
  (`Funcionários`, `Holerites`, `Folha de Ponto`, `Envios`, `Assinaturas`)
   — é onde o código novo já tem contrato, estado e evento definidos.
- Reconciliar por hash e por chave canônica. **Nunca por nome** — a
  regra `DEC-ENT` de identidade e o incidente real de colisão de nome
  já provaram isso.
- Critério de avanço: divergência zero por N competências, medida — não
  presumida.

### FASE 3 — Banco próprio vira fonte de verdade
- Inverter a direção da escrita, **um domínio por vez**.
- Documental e RH primeiro (têm contrato e máquina de estado prontos).
- Financeiro/Fiscal por último — hoje **só** existe no Airtable, sem
  contrato canônico nem código.
- Cada inversão é gate humano com plano de rollback.

### FASE 4 — Airtable vira painel opcional
- Leitura e operação manual continuam, mas sem ser origem.
- Só faz sentido quando existir substituto de interface — a Fase 5 do
  Módulo 01 (painel visual) é candidata natural, e está pronta numa
  branch não mesclada.

---

## 6. O que precisa ser decidido antes de qualquer fase

1. **Plano do Postgres** — `free` não serve para persistência durável
   (o próprio `render.yaml` avisa). Decisão financeira, bloqueia a Fase 2.
2. **Auditar as automações nativas do Airtable** — é a lógica de negócio
   invisível. Deveria vir antes de qualquer migração.
3. **Financeiro/Comercial entram no Magnata OS?** Agora sabemos que
   existem e onde. Falta decidir se são integrados ou permanecem fora.
4. **Contrato canônico para Financeiro/Fiscal** — não existe. Migrar sem
   contrato repetiria o erro que a fundação documental corrigiu.
