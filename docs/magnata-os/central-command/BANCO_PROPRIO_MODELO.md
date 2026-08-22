# BANCO PRÓPRIO — modelo alvo

**Etapa 8 da Central Command, 2026-08-22.**
**Modelo, não migração. Nada foi provisionado, migrado ou alterado.**
Schema do Airtable lido em read-only: nomes de tabela, campo e tipo.
**Zero registros, zero PII.**

> ⚠️ **O objetivo não é eliminar o Airtable.** Ele continua sendo
> ferramenta operacional importante. O objetivo é eliminar **dependência
> crítica e lock-in** — que são coisas diferentes.

---

## 1. O problema que o modelo alvo precisa resolver

O modelo atual responde **"onde trabalha?"**. Não responde **"onde
trabalhava na competência de julho?"**.

Evidência no schema: `Funcionários` liga-se a `Locais de trabalho` por
`multipleRecordLinks` **sem nenhuma dimensão temporal**. Quando um
colaborador muda de posto, o vínculo anterior **é sobrescrito**. O
holerite de julho passa a apontar para o posto de agosto.

Isso não é hipótese: é consequência direta de um link sem vigência. E é
exatamente o que o Modelo Conceitual aprovado pela Direção em 2026-07-22
já previu ao introduzir **`Alocação`** como entidade própria, distinta de
`Vínculo Trabalhista`.

**O modelo alvo existe, antes de tudo, para tornar `Alocação` temporal.**

---

## 2. Densidade de lógica derivada — o que não migra sozinho

| Tabela | Campos | Derivados (fórmula/rollup/lookup/count) | % |
|---|---|---|---|
| `Folha de Ponto` | 50 | **36** | **72%** |
| `Funcionários` | 66 | 25 | 38% |
| `Envios de Documentos` | 46 | 17 | 37% |
| `Clientes` | 36 | 15 | 42% |
| `Locais` | 22 | 8 | 36% |
| `Holerites` | 25 | 6 | 24% |

🔴 **Em `Folha de Ponto`, quase três quartos dos campos são calculados
dentro do Airtable.** Isso é regra de negócio que não está em nenhum
arquivo do repositório, não passa por PR, não tem teste e não aparece em
auditoria de código (RSK-014).

**Consequência para a migração:** copiar dados **não** migra o sistema.
Cada campo derivado precisa virar consulta, view ou coluna calculada — e
a regra precisa ser lida do Airtable antes, porque não existe em outro
lugar.

---

## 3. Entidades do núcleo — aprovadas em 2026-07-22

Do Modelo Conceitual oficial. **Não invento nem renomeio nada.**

```text
Empresa Magnata
└── Cliente
    └── Contrato Comercial
        └── Posto de Trabalho

Colaborador
└── Vínculo Trabalhista
    └── Alocação
        └── Posto de Trabalho
```

| Entidade | Existe no Airtable hoje? | Observação |
|---|---|---|
| `Empresa` | ❌ implícita | O CNPJ da Magnata aparece como constante no código |
| `Cliente` | ✅ `Clientes` (36 campos) | 7 links de saída |
| `Contrato Comercial` | ❌ **não existe** | Aprovado como vocabulário, sem implementação |
| `Posto de Trabalho` | 🟡 `Locais` (22 campos) | Nome diferente; a equivalência é **decisão pendente**, não conclusão minha |
| `Colaborador` | ✅ `Funcionários` (66 campos) | A maior tabela |
| `Vínculo Trabalhista` | 🟡 disperso | `Status`, `Data de Admissão`, `Contratação/Recisão` — **não é entidade** |
| `Alocação` | 🔴 **não existe** | Hoje é o link `Funcionários ↔ Locais`, sem temporalidade |

---

## 4. Entidades adicionais — só as justificadas por evidência

Nenhuma inventada. Cada uma tem tabela correspondente no Airtable:

| Entidade | Origem | Por que é entidade própria |
|---|---|---|
| `Competência` | `Mês Contabilidade`, `Contabilidade Mensal` | Já é chave de ligação de Holerite, Folha e Envio. Hoje é texto e nome de tabela |
| `Documento` | `Holerites`, `Folha de Ponto`, `Certidões`, `Guias`, `Extratos` | Já tem contrato canônico e máquina de estado definidos |
| `Envio` | `Envios de Documentos` (46 campos, 12 links) | Já tem `DEC-ENT-013/018/019/020/021` aprovadas |
| `Assinatura` | `Assinaturas Digitais` | `DEC-ENT-014/022–029` aprovadas |
| `Registro de Ponto` | `Batidas de ponto` | Fato bruto, distinto da Folha calculada |
| `Lançamento Financeiro` | `Pagamentos`, `Recebimentos`, `Despesas` | Núcleo Financeiro — existe, **sem contrato canônico** |

---

## 5. Temporalidade — o ponto central

Três padrões, escolhidos por natureza do dado. Não é preferência
estética: usar o padrão errado é o que produz o bug de "onde trabalhava
em julho".

### 5.1 Vigência por intervalo — para relação que muda no tempo

```sql
-- Alocação: a entidade que hoje NÃO existe e resolve o problema
CREATE TABLE alocacao (
    id                    uuid PRIMARY KEY,
    vinculo_trabalhista_id uuid NOT NULL REFERENCES vinculo_trabalhista(id),
    posto_id              uuid NOT NULL REFERENCES posto_trabalho(id),
    vigente_de            date NOT NULL,
    vigente_ate           date,              -- NULL = vigente agora
    registrado_em         timestamptz NOT NULL DEFAULT now(),
    origem                text NOT NULL,     -- proveniência (CLAUDE.md §4)
    id_externo_airtable   text,              -- nunca chave canônica
    CONSTRAINT periodo_valido CHECK (vigente_ate IS NULL OR vigente_ate >= vigente_de)
);
-- Impede duas alocações sobrepostas para o mesmo vínculo:
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE alocacao ADD CONSTRAINT sem_sobreposicao
    EXCLUDE USING gist (vinculo_trabalhista_id WITH =,
                        daterange(vigente_de, vigente_ate, '[]') WITH &&);
```

Com isso, *"onde trabalhava na competência X?"* vira uma consulta:

```sql
SELECT p.* FROM alocacao a JOIN posto_trabalho p ON p.id = a.posto_id
WHERE a.vinculo_trabalhista_id = $1
  AND daterange(a.vigente_de, a.vigente_ate, '[]') @> $2::date;
```

O mesmo padrão vale para `vinculo_trabalhista` (admissão → rescisão) e
para `contrato_comercial`.

### 5.2 Competência como entidade — nunca como nome de tabela

`Sem_Batida_Julho_2026` e `Fechamento_Mai_Jun_2026` põem o mês **no nome
da tabela** (RSK-015). No modelo alvo, competência é coluna com
constraint, e cada documento a referencia. Uma competência nova não cria
tabela nova.

### 5.3 Fato imutável — append-only

`Registro de Ponto`, evento de esteira e evidência de assinatura **nunca
são atualizados**. `CLAUDE.md` §4 e a migration `0003` do Módulo 01 já
implementam isso por **trigger de banco**, não por disciplina de código.
É o padrão a repetir.

---

## 6. Identidade, proveniência e auditoria

Regras que **já foram decididas** — só aplicadas aqui:

1. **Record ID do Airtable nunca é chave canônica.** Vai em
   `id_externo_airtable`, como referência externa. Já é `DEC-ENT` e já
   está em `MAGNATA_OS_ENTIDADES.md` §8.
2. **Nome nunca é identificador.** Regra nascida de incidente real de
   colisão de identidade (`HISTORICO.md` §2.2), hoje em
   `MAGNATA_OS_CONTRATOS.md` §16.
3. **Toda linha carrega `origem` e `registrado_em`** — proveniência é
   coluna, não comentário.
4. **Histórico append-only por trigger**, não por convenção.
5. **`DATA ISO` / `DATA TXT` colapsam numa coluna `date`.** Hoje a mesma
   data existe duas vezes em formatos diferentes — duas fontes de verdade
   para o mesmo fato, com risco de divergirem.

---

## 7. Sincronização com o Airtable — quem manda em quê

O Airtable **permanece**. O que muda é a direção da escrita, por domínio,
uma de cada vez.

| Fase | Airtable | Banco próprio | Reconciliação |
|---|---|---|---|
| **A** *(hoje)* | 🥇 Fonte única | ❌ não existe | — |
| **B** | 🥇 Fonte | 👁 Espelho read-only | Por hash e chave canônica, **nunca por nome** |
| **C** | 🥇 Fonte | ✍️ Dual-write | Divergência é **incidente**, não warning |
| **D** | 👁 Espelho | 🥇 Fonte | Um domínio por vez, com rollback |
| **E** | 🖥 Painel opcional | 🥇 Fonte | Airtable segue útil como interface |

**Critério para avançar de fase:** divergência zero por N competências,
**medida** — não presumida. E cada avanço é gate humano.

**Ordem sugerida:** Documental e RH primeiro (têm contrato, estado e
evento definidos). **Financeiro por último** — hoje só existe no
Airtable, sem contrato canônico.

---

## 8. Pré-requisitos que bloqueiam a Fase B

1. 🔴 **Postgres real.** `render.yaml` declara `plan: free`, marcado como
   placeholder pelo próprio arquivo, que avisa que o tier gratuito expira
   e não serve para persistência durável. **Decisão financeira.**
2. 🔴 **Auditar as fórmulas do Airtable** (RSK-014). Sem isso, os 72% de
   `Folha de Ponto` viram perda silenciosa.
3. 🟠 **Decidir se `Locais` = `Posto de Trabalho`.** Se não for, falta uma
   entidade.
4. 🟠 **Contrato canônico para Financeiro/Fiscal** — não existe.
5. 🟡 **`DEC-ENT-010/011/012`** pendentes; `DEC-ENT-020` (estados do
   Envio) depende de `012`.

---

## 9. O que este documento NÃO faz

Não provisiona banco · não cria migration · não migra registro · não
altera schema do Airtable · não remove automação · não troca fonte de
verdade · não decide se `Locais` equivale a `Posto` · não define
retenção de dado pessoal.

Tudo isso é gate humano, e cada um está nomeado acima.
