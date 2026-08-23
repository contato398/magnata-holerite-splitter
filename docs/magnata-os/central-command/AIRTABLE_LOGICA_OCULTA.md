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

---

# ANEXO A — Etapa 10 (2026-08-22): os 2 `customScript` e as views

Fecha a lacuna nº 1 e nº 2 declaradas na §8. Leitura via API, somente
leitura. **Nenhum segredo é reproduzido aqui.**

## A.1 `PROCESSAR ARQUIVOS` — 🔴 CRÍTICO

| Campo | Valor |
|---|---|
| Gatilho | `recordCreated` em `Processar Arquivos` |
| Input | apenas o **ID do registro** disparado |
| Tabelas lidas | nenhuma |
| Tabelas escritas | **nenhuma** |
| Efeito externo | ✅ **`fetch` HTTP para um webhook do Make.com** |
| Secret referenciado | a URL do webhook está **hardcoded no script** — é credencial de fato, e **não é reproduzida aqui** |
| Tratamento de erro | ❌ **nenhum** — `await fetch()` sem `try/catch`, sem checar status |
| Idempotência | ❌ **nenhuma** — dispara a cada criação de registro |
| Risco de PII | 🟢 Baixo — só o ID vai na query string |
| Risco financeiro | 🟡 consome operações do plano Make a cada registro |

**Regra humana:** *"Sempre que um arquivo novo entra em `Processar
Arquivos`, avise um cenário do Make.com passando o ID do registro."*

🔴 **Três problemas:**

1. **Contradiz decisão documentada.** O plano do PR #22 registra a regra
   *"não construir nada novo no Make.com"*. Existe integração ativa do
   Make **em produção**, disparando em toda criação de registro — e o
   plano foi escrito sem saber disso.
2. **Falha silenciosa** — `CLAUDE.md` §4 é explícito. Se o Make estiver
   fora, o arquivo entra e ninguém é avisado. Sem log, sem retry, sem
   pendência.
3. **URL de webhook em texto claro** dentro da automação — quem tiver
   acesso de leitura ao Airtable tem a credencial.

## A.2 `Automation 1` — 🔍 PRECISA SER VALIDADO

| Campo | Valor |
|---|---|
| Gatilho | `inputReceivedFromConnection` em `Holerites` |
| Input declarado | `recordId` com template **vazio** (`[""]`) |
| Corpo do script | ⚠️ **não retornado pela API** — ao contrário do anterior, que veio completo |
| Status | `deployed`, `configurationStatus: valid` |

**Não sei o que esta automação faz.** O que sei: está publicada, é
disparada por conexão externa sobre a tabela de `Holerites`, e o input
que ela declara está vazio.

Duas leituras possíveis, e **não vou escolher sem evidência**: ou é um
rascunho publicado por engano com script vazio, ou a API não devolve o
corpo neste caso. **Só a interface do Airtable resolve.**

⚠️ Uma automação sem nome descritivo, sem descrição e com input vazio,
publicada sobre a tabela de holerites, é exatamente o tipo de coisa que
ninguém lembra de ter criado.

## A.3 As views — a condição que não está em lugar nenhum

7 das 8 mapeadas. **A view define a regra; a automação só executa.**

| View | Tabela | Automação | Regra humana |
|---|---|---|---|
| `NORMAL` | Batidas de ponto | `PONTO BATIDO - COM ALMOÇO` | Ponto normal **com** intervalo |
| `NORMAL - SEM ALMOCO` | Batidas de ponto | `PONTO BATIDO - SEM ALMOÇO` | Ponto normal **sem** intervalo |
| `EXTRA` | Batidas de ponto | `PONTO EXTRA BATIDO - COM ALMOÇO` | Ponto extra **com** intervalo |
| `EXTRA - SEM ALMOÇO` | Batidas de ponto | `PONTO EXTRA BATIDO - SEM ALMOÇO` | Ponto extra **sem** intervalo |
| `VENCIDO` | Guias e Comprovantes | `VENCEU GUIA` | Guia passou do vencimento |
| `INATIVO` | Guias e Comprovantes | `INATIVA GUIA` | Guia deixou de valer |
| `Pronto` | Processar Arquivos | `Concluido-arquivado processos` | Arquivo terminou o processamento |
| `VENCEU` | Certidões | `VENCER CERTIDAO` | Certidão passou do vencimento |
| `CONCLUIDOS-ONTEM OU DPS` | Folha de Ponto | `CONCLUIDO - FOLHA PONTO` | Folha concluída **de ontem em diante** |
| 🔍 (não mapeada) | Contabilidade Mensal | `INATIVAR MES CONTABIL` | Mês contábil a encerrar |

**Confirmação importante:** a divisão **"com almoço / sem almoço"** é a
condição da *view*, não da automação. Ela existe **três vezes** no
sistema — na view, na automação e na fórmula (§3). Três lugares que
precisam concordar, e nenhum teste garante que concordem.

⚠️ **Limite declarado:** `list_views_for_table` devolve id, nome e tipo —
**não os filtros**. Os nomes são autoexplicativos, mas *"o que exatamente
faz um registro entrar em `NORMAL`"* continua só na interface.
`CONCLUIDOS-ONTEM OU DPS` embute uma **regra temporal relativa** no nome.

## A.4 Riscos acrescentados

| ID | Risco | Severidade |
|---|---|---|
| AT-11 | Integração ativa com Make.com contradizendo decisão documentada | 🔴 Crítico |
| AT-12 | Webhook sem `try/catch` — falha silenciosa (§4) | 🔴 Crítico |
| AT-13 | URL de webhook em texto claro na automação | 🟠 Alto |
| AT-14 | `Automation 1` publicada sobre `Holerites`, propósito desconhecido | 🟠 Alto |
| AT-15 | Regra "com/sem almoço" triplicada sem teste de concordância | 🟠 Alto |
| AT-16 | Filtros das views inacessíveis por API | 🟡 Médio |

## A.5 O que ainda falta

1. 🔴 Corpo de `Automation 1` — só pela interface.
2. 🔴 Filtros exatos das 9 views.
3. 🟠 View de `Contabilidade Mensal` não mapeada.
4. 🟠 Condições dos ramos das 4 automações de ponto.

---

# ANEXO B — Etapa 11 (2026-08-23): o que a API resolveu e o que ela não alcança

Fecha o que o ANEXO A deixou aberto, **com evidência**, e corrige duas
afirmações minhas que estavam erradas. Leitura somente. Nada alterado.

## B.1 `Automation 1` — resolvida: o script está VAZIO

**Correção de conclusão anterior.** O ANEXO A §A.2 disse que *"o corpo do
script não foi retornado pela API"* e listou duas leituras possíveis sem
escolher. A escolha agora é possível, por comparação direta:

| Automação | Nó | A API devolveu `script`? |
|---|---|---|
| `PROCESSAR ARQUIVOS` | `customScript` | ✅ **sim, completo** |
| `Automation 1` | `customScript` | ❌ **a chave `script` não existe** |

A API **devolve** corpo de script — provado pelo primeiro caso, lido na
mesma sessão, com a mesma credencial e a mesma ferramenta. A ausência da
chave no segundo caso não é limitação: é **ausência de conteúdo**.

Somando ao `recordId` com template vazio (`[""]`) e ao nome genérico:

> 🟠 **`Automation 1` é, com alta probabilidade, um rascunho publicado por
> engano.** Publicada sobre `Holerites`, `deployed`, `configurationStatus:
> valid`, e **sem nada para executar**.

⚠️ **O que continua não provado:** que ela seja inofensiva. `valid` +
`deployed` com nó vazio deveria ser inerte, mas isso é inferência sobre o
motor do Airtable, não observação. **Confirmação pela interface continua
sendo o gate** — e agora é uma conferência de 30 segundos, não uma
investigação.

## B.2 `PROCESSAR ARQUIVOS` — correção do nome do input

O ANEXO A §A.1 disse *"passando apenas o ID do registro"*, o que está
certo no efeito, mas **errado no nome**: a chave do input é `Cliente`,
ligada a `trigger.id`. O valor é o ID do registro; o rótulo diz "Cliente".

Isso não é preciosismo: um rótulo que não descreve o que carrega é
exatamente o que faz a próxima pessoa ler errado.

O restante do §A.1 está confirmado e **inalterado**: `fetch` para webhook
do Make.com **hardcoded**, sem `try/catch`, sem checagem de status, sem
idempotência. A URL continua tratada como credencial e **não é
reproduzida em lugar nenhum deste repositório**.

## B.3 As 8 views — mapeamento completo

A view que faltava é **`INATIVOS`**, em `Contabilidade Mensal`
(`tblWITpkSbPg4SBAR`), disparando `INATIVAR MES CONTABIL`.

| # | View | Tabela | Automação |
|---|---|---|---|
| 1 | `NORMAL` | Batidas de ponto | `PONTO BATIDO - COM ALMOÇO` |
| 2 | `NORMAL - SEM ALMOCO` | Batidas de ponto | `PONTO BATIDO - SEM ALMOÇO` |
| 3 | `EXTRA` | Batidas de ponto | `PONTO EXTRA BATIDO - COM ALMOÇO` |
| 4 | `EXTRA - SEM ALMOÇO` | Batidas de ponto | `PONTO EXTRA BATIDO - SEM ALMOÇO` |
| 5 | `VENCIDO` | Guias e Comprovantes | `VENCEU GUIA` |
| 6 | `INATIVO` | Guias e Comprovantes | `INATIVA GUIA` |
| 7 | `Pronto` | Processar Arquivos | `Concluido-arquivado processos` |
| 8 | `VENCEU` | Certidões | `VENCER CERTIDAO` |
| 9 | `CONCLUIDOS-ONTEM OU DPS` | Folha de Ponto | `CONCLUIDO - FOLHA PONTO` |
| 10 | **`INATIVOS`** | **Contabilidade Mensal** | `INATIVAR MES CONTABIL` |

**Assimetria confirmada nos ramos:** as automações **COM ALMOÇO** têm
**4 ramos** condicionais; as **SEM ALMOÇO**, apenas **2**. A diferença é
real e está na estrutura, não no nome — mas *qual* condição separa cada
ramo continua invisível (ver B.4).

🟡 **Achado lateral:** `Contabilidade Mensal` tem uma view chamada
**`MES ATIVO copy`**. Cópia esquecida é candidata a virar gatilho por
engano se alguém plugar uma automação nela.

## B.4 ❌ NÃO OBSERVÁVEL POR API — declarado, não inferido

| O que falta | Por quê |
|---|---|
| **Filtros de todas as views** | `list_views_for_table` devolve id, nome e tipo. Não há endpoint de filtro |
| **Condições dos ramos** dos `conditionalGroup` | `list_automations` devolve a árvore de nós, sem as condições |
| **Corpo de `Automation 1`** | Não existe corpo a devolver (B.1) |

**Caminho manual necessário** — o único que resolve:

1. Abrir cada view no Airtable e transcrever o filtro.
2. Abrir cada `conditionalGroup` e transcrever as condições dos ramos.
3. Abrir `Automation 1` e confirmar se o script está mesmo vazio.

**Não infiro filtro a partir de dado.** Seria possível comparar quais
registros aparecem em cada view, mas isso significa ler registros reais —
e `CLAUDE.md` §6 proíbe dado pessoal em log, saída ou documento. Uma
regra deduzida de amostra também não é a regra: é uma hipótese que
combina com a amostra.

## B.5 `480` — o mapeamento pedido, com um achado que muda a conclusão

🔴 **`480` não existe em nenhum arquivo do repositório.**

Verificado por varredura em todo o código versionado (`*.py`, `*.js`,
fora de `docs/`): **zero ocorrências**. A constante vive **exclusivamente
dentro da fórmula `Horas Extras` do Airtable**.

**Consequência prática:** não há nada a corrigir no código. Mudar a
jornada é, hoje, **necessariamente** uma alteração no Airtable — que é
gate humano por `CLAUDE.md` §6.

### Onde a escala existe de fato

O código **conhece** 12x36; ele simplesmente não calcula hora extra.
`src/services/secullum_ponto.py` trata a escala com cuidado real:

- linha 82-85: decisão de produto de 24/06/2026 — focar em faltas porque
  *"em escalas 12x36 gera muitos falsos positivos"* com extras;
- linha 188: reconhece turno **SOLO 12x36 sem intervalo**;
- linha 566: interpreta `"12x36 19h - 07h IMPAR"` para classificar noturno;
- linha 630-636: a escala teórica do dia (FOLGA/Feriado) vem do próprio
  `/Calcular` da Secullum, que **já resolve 12x36, 5x2 etc. internamente**.

### O quadro completo

| Camada | Sabe o que é 12x36? | Calcula hora extra? |
|---|---|---|
| Secullum (`/Calcular`) | ✅ sim, é a fonte da escala | ✅ sim |
| Código (`secullum_ponto.py`) | ✅ sim, com tratamento explícito | ❌ não |
| Airtable (fórmula `Horas Extras`) | ❌ **não — assume 8h fixas** | ✅ sim |

🔴 **A única camada que calcula hora extra é a única que não sabe que a
escala existe.** Este é o enunciado exato do risco AT-01, e ele é pior do
que "uma constante mal escolhida": é uma camada operando com um modelo de
mundo que as outras duas já abandonaram.

### Impacto — declarado como possibilidade, não como fato medido

| Frente | Impacto se a fórmula estiver em uso para 12x36 |
|---|---|
| Hora extra | Um plantão de 12h gera 4h de "extra" que podem não ser extra |
| Ponto | O fato bruto está certo; a derivação é que diverge |
| Folha | Propaga para valor pago |
| Competência | Se estiver errado, está errado **retroativamente**, por competência |

⚠️ **Não medi quantos funcionários 12x36 passam por essa fórmula.** Medir
exigiria ler registros reais. O risco é estrutural e comprovado; a
extensão é desconhecida e **precisa ser medida por quem pode ver o dado**.

### Recomendação arquitetural

**Fonte correta da jornada: a escala resolvida pela Secullum**, que já é
a fonte de verdade em `secullum_ponto.py` e já resolve 12x36 sozinha.
Jornada deve ser **atributo do vínculo/alocação com vigência**
(`BANCO_PROPRIO_MODELO.md` §5.1), nunca constante — porque jornada muda
no tempo e a fórmula atual não tem como saber disso.

**Ordem sugerida, cada passo um gate:**

1. **Medir** quantos vínculos 12x36 atravessam a fórmula. Sem isso,
   qualquer correção é chute sobre o tamanho do problema.
2. **Confirmar com a Direção** se a fórmula está mesmo em uso para
   cálculo, ou se virou vestígio.
3. Só então decidir entre corrigir a fórmula, movê-la para o código com
   a escala como entrada, ou aposentá-la.

❌ **Não transformo isto em implementação.** É regra trabalhista com
efeito retroativo em folha — decisão de negócio, não técnica.

## B.6 Make.com — estado real vs. decisão documentada

**As duas afirmações são verdadeiras ao mesmo tempo, e não se anulam:**

| | |
|---|---|
| **ESTADO REAL** | Make.com está **ativo em produção**, via `PROCESSAR ARQUIVOS`, disparando a cada registro criado |
| **DECISÃO DOCUMENTADA** | O plano do PR #22 registra *"não construir nada novo no Make.com"* |

**Classificação: divergência histórica/arquitetural.** A decisão fala de
*construir novo*; o que existe é *pré-existente*. O plano foi escrito sem
saber que a integração já existia — a falha foi de **inventário**, não de
decisão. Nenhuma das duas frases significa *"remover o Make.com agora"*.

### Decisão futura — quatro opções, com impacto

| Opção | O que significa | Impacto | Risco |
|---|---|---|---|
| **MANTER TEMPORARIAMENTE** | Nada muda; a dependência fica registrada | Zero imediato. Convive com AT-12 (falha silenciosa) | 🟡 O risco continua, mas **conhecido** |
| **INSTRUMENTAR** *(recomendada como primeiro passo)* | Manter o fluxo, acrescentar `try/catch`, checagem de status e registro de falha | Baixo — não muda o caminho feliz | 🟢 Mata AT-12 sem tocar no fluxo |
| **MIGRAR / SUBSTITUIR** | O cenário do Make vira código no Magnata OS | Alto — exige saber **o que o cenário faz**, hoje desconhecido | 🟠 Migrar o que não se entende é reescrever um bug |
| **DESCOMISSIONAR** | Desligar o Make | Desconhecido — pode parar um fluxo em produção | 🔴 Sem saber o que o cenário faz, é aposta |

**Recomendação:** **INSTRUMENTAR primeiro, decidir depois.** Falha
silenciosa é o problema urgente (`CLAUDE.md` §4); dependência de
fornecedor é o problema importante. Não são o mesmo problema e não
precisam da mesma decisão.

**Pré-requisito de qualquer opção além de MANTER:** abrir o cenário no
Make.com e documentar o que ele faz. É a lacuna que bloqueia as outras
três — e não é acessível por nenhuma ferramenta desta sessão.

## B.7 Riscos acrescentados

| ID | Risco | Severidade |
|---|---|---|
| AT-17 | `Automation 1` publicada com nó vazio sobre `Holerites` | 🟠 |
| AT-18 | Input rotulado `Cliente` carregando ID de registro | 🟡 |
| AT-19 | View `MES ATIVO copy` — cópia esquecida, gatilho acidental em potencial | 🟡 |
| AT-20 | Cenário do Make.com de conteúdo desconhecido — bloqueia migrar/descomissionar | 🟠 |
| AT-21 | Única camada que calcula hora extra é a única que ignora a escala | 🔴 |
