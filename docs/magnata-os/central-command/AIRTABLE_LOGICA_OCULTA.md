# AIRTABLE — lógica de negócio que só existe lá

**Etapa 9 da Central Command, 2026-08-22.**
**Auditoria somente leitura. Nenhum registro, schema, fórmula, view ou
automação foi alterado. Zero dados pessoais lidos.**

Fecha o risco **RSK-014** — "regra de negócio dentro do Airtable, não
versionada". Este documento existe para que uma sessão futura consiga
responder **"qual regra hoje só existe dentro do Airtable?"** sem
redescobrir tudo.

⚠️ **Isto documenta a regra, não a substitui.** O Airtable continua
operacional e é a fonte de verdade do que está aqui descrito.

---

## 1. Panorama

| Item | Quantidade |
|---|---|
| Tabelas | **31** |
| Automações ativas (`deployed`) | **13** |
| Automações que rodam **script customizado** | **2** |
| Campos de `Folha de Ponto` | 50 — **36 derivados (72%)** |
| Fórmulas com constante de negócio embutida | ≥ 1 crítica (`480`) |
| Fórmulas com fuso horário embutido | 4 |

---

## 2. A regra mais crítica — jornada de 8 horas como constante

```
Horas Extras (fldniPH5c4SHPPdjL) = {Minutos - Total} - 480
```

**`480` minutos = 8 horas.** A jornada padrão da Magnata está **hardcoded
numa fórmula do Airtable**. Não está em `app.py`, não está em nenhum
documento fundacional, não tem teste.

| Campo | Valor |
|---|---|
| **Finalidade** | Calcular minutos de hora extra do dia |
| **Dependências** | `Minutos - Total`, que depende de toda a cadeia de batidas |
| **Regra em linguagem humana** | *"Hora extra é o que passou de 8 horas líquidas trabalhadas no dia."* |
| **Risco** | 🔴 **Crítico** — jornada diferente (12x36, 6h, estagiário) produz cálculo errado silenciosamente |
| **Temporalidade** | ❌ Nenhuma. Se a jornada mudar, todo o histórico é recalculado com o valor novo |
| **Fonte de verdade** | Airtable, exclusivamente |
| **Equivalente futuro** | Coluna `jornada_minutos` em `vinculo_trabalhista`, **com vigência** |
| **Permanece no Airtable?** | Não — é regra trabalhista |
| **Migra para backend?** | ✅ Sim |
| **Vira teste?** | ✅ **Sim, prioritário** |

🔴 **O sistema opera turnos 12x36** (documentado em `HISTORICO.md`,
`v2_49`/`v2_62`). Uma constante fixa de 480 é incompatível com 12x36 por
definição. **Isto é um gate da Direção, não uma correção técnica** — não
sei qual jornada se aplica a quem, e não vou adivinhar.

---

## 3. Fatiamento de batidas — a regra "com almoço / sem almoço"

O núcleo do cálculo de ponto. Seis fórmulas encadeadas sobre um array de
batidas ordenadas:

| Campo | Fórmula | Regra humana |
|---|---|---|
| `Qtd batidas` | `COUNTA({batidas})` | Quantas batidas o dia teve |
| `Entrada` | `IF(qtd > 0, ARRAYSLICE(batidas, 1, 1), "")` | 1ª batida |
| `Saída almoço` | `IF(qtd > 2, ARRAYSLICE(batidas, 2, 2), "")` | 2ª batida **só se houve almoço** |
| `Volta almoço` | `ARRAYSLICE(batidas, 3, 3)` | 3ª batida |
| `Saída` | `IF(qtd > 2, ARRAYSLICE(batidas, 4, 4), ARRAYSLICE(batidas, 2, 2))` | **4ª se com almoço, 2ª se sem** |
| `Intervalo` | `IF(qtd > 3, DATETIME_DIFF(volta, saída_almoço, 'minutes'), BLANK())` | Minutos de intervalo |
| `Total bruto` | `IF(saída = "", BLANK(), DATETIME_DIFF(saída, entrada, 'minutes'))` | Saída − entrada |
| `Total líquido` | `{bruto} − {intervalo}` | Descontado o almoço |

**Regra humana consolidada:** *"Se o dia teve mais de 2 batidas, houve
almoço: entrada, saída-almoço, volta-almoço, saída. Se teve 2, foi
direto: entrada e saída."*

| Campo | Valor |
|---|---|
| **Risco** | 🔴 **Crítico** — depende de **ordem** e **paridade** das batidas |
| **Falha silenciosa** | ✅ **Sim.** Batida ímpar (esquecer de bater a saída) produz `BLANK()` sem alarme. O `HISTORICO.md` (`v2_49`) já registrava "batida ímpar" como trava conhecida |
| **Duplicidade** | 🔴 **Sim** — a mesma regra existe **também** nas 4 automações `PONTO BATIDO`, com views separadas para "COM ALMOÇO" e "SEM ALMOÇO" |
| **Equivalente futuro** | Função pura sobre a lista de `registro_ponto`, testável |
| **Vira teste?** | ✅ Sim — casos: 0, 1, 2, 3, 4, 5 batidas; fora de ordem; virada de dia |

---

## 4. Identidade por concatenação — anti-padrão já proibido

```
Name = DATETIME_FORMAT({Data}, 'DD/MM/YY') & " - " & {Funcionário} & {Funcionário Extra}
```

O campo primário de `Folha de Ponto` é **data + nome do funcionário**.

Isso contraria diretamente `MAGNATA_OS_CONTRATOS.md` §16 e
`MAGNATA_OS_ENTIDADES.md` §8 — *"nome não é identificador confiável"* —
regra nascida de um **incidente real de colisão de identidade**
(`HISTORICO.md` §2.2).

**Risco:** 🟠 Alto. Dois colaboradores de nome parecido no mesmo dia
produzem chaves visualmente idênticas.
**Equivalente futuro:** chave sintética (`uuid`), com o rótulo legível
como campo de apresentação.

---

## 5. Fuso horário embutido em fórmula

Quatro campos aplicam `SET_TIMEZONE(..., 'America/Sao_Paulo')` — entrada,
saída-almoço, volta e saída, todos formatados como `HH:mm`.

É a **mesma classe de defeito** que o PR #30 corrigiu em `_fmt_quando`:
fuso resolvido na apresentação, não no dado. Aqui está correto por sorte
(a Magnata opera só em BRT), mas é regra de exibição travada em fórmula.

Três delas ainda embrulham em `IF(ISERROR(...), "", ...)` — **erro
mascarado como string vazia**, o que contraria `CLAUDE.md` §4 ("falha
nunca silenciosa").

---

## 6. As 13 automações ativas

Todas `deployed` e `valid`. Nenhuma foi desativada, alterada ou testada.

| # | Nome | Gatilho | Tabela | Ação | Classificação |
|---|---|---|---|---|---|
| 1 | `INATIVAR MES CONTABIL` | entra na view | Contabilidade Mensal | updateRecord | 🟡 MIGRAR FUTURAMENTE |
| 2 | `VENCEU GUIA` | entra na view | Guias e Comprovantes | updateRecord | 🟡 MIGRAR FUTURAMENTE |
| 3 | `INATIVA GUIA` | entra na view | Guias e Comprovantes | updateRecord | 🟡 MIGRAR FUTURAMENTE |
| 4 | **`PROCESSAR ARQUIVOS`** | **registro criado** | Processar Arquivos | **`customScript`** | 🔴 **PRECISA DE DECISÃO** |
| 5 | `VENCER CERTIDAO` | entra na view | Certidões | updateRecord | 🟡 MIGRAR FUTURAMENTE |
| 6 | `Concluido-arquivado processos` | entra na view | Processar Arquivos | updateRecord | 🟡 MIGRAR FUTURAMENTE |
| 7 | **`INATIVA FUNCIONARIO QUANDO RECISÂO`** | condições | **Funcionários** | updateRecord | 🔴 **PRECISA DE DECISÃO** |
| 8 | `PONTO BATIDO - COM ALMOÇO` | entra na view | Batidas de ponto | find + 4 ramos × (create/update) | 🔴 PRECISA DE DECISÃO |
| 9 | `PONTO EXTRA BATIDO - COM ALMOÇO` | entra na view | Batidas de ponto | idem | 🔴 PRECISA DE DECISÃO |
| 10 | `PONTO BATIDO - SEM ALMOÇO` | entra na view | Batidas de ponto | find + 2 ramos | 🔴 PRECISA DE DECISÃO |
| 11 | `PONTO EXTRA BATIDO - SEM ALMOÇO` | entra na view | Batidas de ponto | idem | 🔴 PRECISA DE DECISÃO |
| 12 | `CONCLUIDO - FOLHA PONTO` | entra na view | Folha de Ponto | updateRecord | 🟡 MIGRAR FUTURAMENTE |
| 13 | **`Automation 1`** | `inputReceivedFromConnection` | Holerites | **`customScript`** | 🔴 **PRECISA DE DECISÃO** |

### 6.1 A que interage com o código que acabamos de corrigir

**`INATIVA FUNCIONARIO QUANDO RECISÂO`** dispara por condição em
`Funcionários` e **escreve o campo `fld5T04dlg1Yt6Xj8`** — que é
exatamente `F_FUNC_STATUS`, o campo que `_status_funcionario_elegivel`
lê para decidir se o colaborador pode assinar.

🔴 **Consequência real:** existe uma automação do Airtable que **muda a
elegibilidade de assinatura** sem passar por nenhuma linha de código do
Magnata OS, sem log no sistema e sem evento na esteira. O PR #33 corrigiu
como o sistema **lê** esse campo; **quem escreve** continua fora do Git.

### 6.2 As duas que rodam script

`PROCESSAR ARQUIVOS` e `Automation 1` executam `customScript` dentro do
Airtable. **O código-fonte desses scripts não foi lido nesta auditoria** —
a API de automações devolve a estrutura (gatilho, nós, tipo), não o corpo
do script.

🔴 **Esta é a maior lacuna que resta.** São dois blocos de código
executando em produção, disparados por criação de registro e por conexão
externa, **completamente fora do Git, sem teste e sem revisão.**

`Automation 1` sem nome descritivo e sem descrição é agravante: ninguém
sabe o que ela faz sem abrir o Airtable.

### 6.3 Views como condição invisível

**8 das 13** automações disparam por `recordEntersView`. Isso significa
que **a condição real está na definição da view**, não na automação. Uma
view alterada muda o comportamento do sistema sem alterar automação
nenhuma — e sem deixar rastro auditável.

---

## 7. Riscos consolidados

| ID | Risco | Severidade |
|---|---|---|
| AT-01 | Jornada de 8h como constante `480`, incompatível com 12x36 | 🔴 Crítico |
| AT-02 | Dois `customScript` em produção, fora do Git | 🔴 Crítico |
| AT-03 | Automação escreve `Status` do funcionário — muda elegibilidade de assinatura sem passar pelo código | 🔴 Crítico |
| AT-04 | Fatiamento de batidas falha em silêncio com batida ímpar | 🔴 Crítico |
| AT-05 | Lógica de ponto duplicada: fórmula **e** 4 automações | 🟠 Alto |
| AT-06 | 8 automações com condição escondida em view | 🟠 Alto |
| AT-07 | Identidade por concatenação data+nome | 🟠 Alto |
| AT-08 | `IF(ISERROR(...), "", ...)` mascara erro | 🟡 Médio |
| AT-09 | Fuso embutido em fórmula | 🟡 Médio |
| AT-10 | Tabelas nomeadas por competência (RSK-015) | 🟡 Médio |

---

## 8. O que ainda não foi auditado

Declarado, não escondido:

1. 🔴 **Corpo dos 2 `customScript`** — a API devolve estrutura, não código.
   Exige leitura na interface do Airtable.
2. 🔴 **Definição das 8 views** que servem de condição.
3. 🟠 **Filtros e condições dos ramos** das automações de ponto.
4. 🟠 **Fórmulas das outras 30 tabelas** — só `Folha de Ponto` foi
   auditada campo a campo, por ser a mais densa (72% derivados).
5. 🟡 Automações desativadas ou em rascunho.

---

## 9. Próximo passo — e por que não avancei sozinho

O caminho está claro: ler os dois scripts e as oito views. **Mas isso
exige a interface do Airtable**, e o que eu obtiver ali é regra de
negócio real que precisa ser conferida por quem a escreveu.

**O que NÃO deve acontecer:** migrar qualquer uma destas regras antes de
a Direção confirmar quais estão corretas. Várias podem estar erradas há
meses — `480` fixo com 12x36 é candidato forte. **Migrar uma regra errada
só a torna permanente.**
