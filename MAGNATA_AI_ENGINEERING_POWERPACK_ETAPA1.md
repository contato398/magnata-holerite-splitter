<!-- PROVENIÊNCIA (Etapa 4 da Central Command, 2026-08-22) — resgate documental.
Origem: branch `feat/magnata-os-claude-powerpack`, HEAD `053acada09dfc70bda71d2293aacbf2bca9ed43e`,
PR #12, FECHADO SEM MERGE em 2026-08-03T17:16:01Z.
RELATÓRIO HISTÓRICO DE ETAPA — descreve o estado da época, não o estado atual.
Texto original inalterado, exceto remoção de espaço em branco à direita (exigência da VALIDAÇÃO 5 do pre-commit; conteúdo idêntico). Auditado: sem CPF, sem nome de funcionário real, sem segredo.
Nota adicional: duas citações de PADRÃO DE DETECÇÃO de segredo (o marcador de
início de chave privada) foram substituídas por descrição em texto, porque a
VALIDAÇÃO 4 do pre-commit as lê como segredo literal. Não havia segredo nenhum:
os relatórios descreviam o que a busca procurava. Sentido preservado. -->

# Magnata AI Engineering Powerpack — Etapa 1: Preservação e Governança da Documentação Fundacional

**Branch:** `feat/magnata-os-claude-powerpack`
**Status:** documentação versionada. Nenhum plugin, MCP, agente, skill
ou hook foi criado nesta etapa. Nenhum serviço real foi acessado.
`app.py` e código funcional inalterados.

---

## 1. Documentos encontrados

Busca por todo `.md` não versionado relacionado ao Magnata OS na raiz
do repositório, mais os 7 nomes-alvo listados no pedido
(`MAGNATA_OS_MANIFESTO.md`, `_ARQUITETURA`, `_CAPACIDADES`,
`_CONTRATOS`, `_ENTIDADES`, `_ESTADOS`, `_EVENTOS`, `_MODULOS`,
`_ROADMAP`) e equivalentes.

### 1.1 Núcleo fundacional (existem, não versionados)

| Documento | Tamanho | Modificado | Finalidade |
|---|---|---|---|
| `MAGNATA_OS_MANIFESTO.md` | 20 008 B | 2026-07-22 | Constituição do sistema — princípios não-negociáveis |
| `MAGNATA_OS_ARQUITETURA.md` | 17 723 B | 2026-07-22 | Estado real medido + arquitetura-alvo, com changelog |
| `MAGNATA_OS_ENTIDADES.md` | 76 010 B | 2026-07-22 | Modelo canônico de entidades do domínio |
| `MAGNATA_OS_DECISOES_ENTIDADES.md` | 89 264 B | 2026-07-22 | Pauta de decisões que fundamenta o modelo de entidades (26/29 `APROVADA`, 3 `PENDENTE`) |
| `MAGNATA_OS_EVENTOS.md` | 95 352 B | 2026-07-22 | Catálogo canônico de eventos de negócio (96 nomes avaliados) |
| `MAGNATA_OS_CONTRATOS.md` | 83 404 B | 2026-07-23 | Contratos canônicos de dados (forma dos campos) |
| `MAGNATA_OS_ESTADOS.md` | 79 119 B | 2026-07-23 | Máquinas de estado canônicas por entidade |
| `MAGNATA_OS_MODULO_01_INGESTAO.md` | 49 995 B | 2026-07-23 | Plano de implementação do Módulo 01 (ingestão) |
| `MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md` | 18 256 B | 2026-07-23 | 13 decisões que destravaram o código do Módulo 01 (12 `APROVADA`, 1 `APROVADA POR CONTINUIDADE OPERACIONAL`) |

**Nenhum destes 9 continha credencial, token, senha, cookie ou URL
secreta** (busca detalhada na §3). Todos contêm **IDs operacionais do
Airtable** (`tbl…`/`fld…`, ex.: `tblRsvhz8oOcUqhkv`, `fldJWy7givUDs1aCl`)
citados como evidência de mapeamento legado→canônico — não são
credenciais (não concedem acesso sem uma chave de API à parte), mas são
identificadores reais da base de produção; preservados porque fazem
parte do valor documental (rastreabilidade legado↔canônico) e o pedido
só exige sanitizar segredos, não identificadores estruturais.

### 1.2 Documentos-alvo do pedido que **não existem**

`MAGNATA_OS_CAPACIDADES.md`, `MAGNATA_OS_MODULOS.md` e
`MAGNATA_OS_ROADMAP.md` **não foram encontrados em nenhum lugar do
disco** — nem versionados, nem como rascunho. `MAGNATA_OS_ENTIDADES.md`
(linha 17) já cita `MAGNATA_OS_CAPACIDADES.md` como "ainda não criado"
em 2026-07-22; segue não criado até hoje. Ver §6 (pendências).

### 1.3 Documentos já versionados (contexto, não tocados nesta etapa)

Já em `main`, servem de contexto para a ordem de leitura e para o
índice: `MAGNATA_OS_DOCUMENTAL_MODULO01.md` (+ `_FASE2`/`_FASE3`/`_FASE4`),
`MAGNATA_OS_IDENTIDADE_VISUAL.md`,
`MAGNATA_OS_MODULO_01_FASE_0_OBSERVABILIDADE.md`,
`MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1.md`.

**Achado relevante:** `MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1.md`
— já em `main` — referencia por nome de arquivo exato 7 dos 9 documentos
do §1.1, que até este commit **não existiam no repositório para
ninguém além desta máquina**. Ou seja, a documentação já mesclada tinha
links quebrados de fato, silenciosamente, desde que foi mesclada — esta
etapa corrige isso.

### 1.4 Outros arquivos identificados — fora do escopo desta etapa

| Documento | Tamanho | O que é | Por que fica de fora |
|---|---|---|---|
| `ARQUITETURA_FASE_2_DECISAO_FINAL.md` | 13 463 B | Decisão de arquitetura pontual (2026-07-20, pré-Manifesto) sobre classificação de documentos | Citado por `MAGNATA_OS_ARQUITETURA.md` §0 como exemplo do padrão antigo que a fundação substitui — histórico, não fundação vigente. **Incluído no commit** (categoria "histórico"), pois o novo `docs/magnata-os/README.md` passou a referenciá-lo — deixá-lo de fora criaria um link quebrado por conta própria desta etapa. |
| `ENTREGA_FASES_A_B_C_D.md`, `FASE_A_FIELD_ID_DISCOVERY.md`, `FASE_B_AUDITORIA_CODIGO.md`, `FASE_C_TESTES_RESULTADO.md`, `FASE_D_DECLARACOES_STATUS.md` | 4,6–17,8 KB cada | Relatório de entrega de uma feature legada **não relacionada** (processamento assíncrono do `/separar` via Celery+Redis, 2026-07-20) | Não é documentação do Magnata OS — é registro de entrega de outra iniciativa. **Não incluído.** |
| `RELATORIO_SCHEMA_AIRTABLE_COMPLETO.md` | 28 379 B | Levantamento read-only, exaustivo, de todas as tabelas/campos da base Airtable de produção (`appaCpIVj7Q97VhFy`, citada explicitamente na linha 2) | Não é um documento de decisão/arquitetura — é um dump bruto de schema com densidade muito maior de IDs operacionais de produção que qualquer documento do §1.1 (todo campo de toda tabela). Excluído por precaução desta rodada — ver §3 e §6. **Não incluído.** |

---

## 2. Documentos incluídos nesta etapa (versionados)

Todos os 9 de §1.1, mais `ARQUITETURA_FASE_2_DECISAO_FINAL.md`
(histórico, citado pelo novo índice), mais os dois arquivos novos desta
etapa: `docs/magnata-os/README.md` e este próprio relatório.

**Nenhum foi movido ou renomeado** — todos permanecem na raiz do
repositório, com o nome atual. Motivo detalhado em
`docs/magnata-os/README.md`, seção "Por que os arquivos não foram
movidos para cá": os 9 documentos se citam mutuamente pelo nome exato
de arquivo **294 vezes** ao todo (contagem física, ver comando abaixo),
e pelo menos um arquivo **já em `main`** também os cita assim. Mover ou
renomear sem reescrever cada citação quebraria links em silêncio — o
próprio risco que este pedido instruiu a evitar. A reorganização em
`docs/magnata-os/00-manifesto.md` … `08-roadmap.md` fica documentada
como intenção futura, não executada.

```bash
grep -rho "MAGNATA_OS_[A-Z0-9_]*\.md" MAGNATA_OS_*.md | sort | uniq -c | sort -rn
```

---

## 3. Itens sanitizados

**Nenhuma sanitização de texto foi necessária.** Busca dedicada por
padrões de credencial/token/senha/cookie/URL-com-segredo (ver comandos
abaixo) não encontrou nenhum valor real — só menções conceituais (ex.:
"nunca logar a chave", "token nunca aparece neste contrato") e IDs
estruturais do Airtable (tabela/campo, não credenciais).

Comandos executados (documentados para reprodutibilidade, sem expor
nenhum resultado sensível porque não houve nenhum):

```bash
# valores de credencial/token/chave/segredo
grep -rniE '(api[_-]?key|password|senha|secret|token|bearer|authorization:|AKIA[0-9A-Z]{16}|key[a-zA-Z0-9]{14}|pat[A-Za-z0-9]{14}\.[a-f0-9]{40,}|<marcador-de-inicio-de-chave-privada>)' MAGNATA_OS_*.md

# tokens/chaves de API embutidos em query string
grep -rniE '[?&](token|api_key|apikey|access_token)=[^&"\x27)]{6,}' MAGNATA_OS_*.md

# e-mails e URLs externas
grep -rniE '[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}' MAGNATA_OS_*.md
grep -rniE 'https?://[a-zA-Z0-9.-]+\.[a-z]{2,}' MAGNATA_OS_*.md
```

**Decisão preventiva, não uma sanitização de segredo:**
`RELATORIO_SCHEMA_AIRTABLE_COMPLETO.md` foi excluído desta rodada (não
commitado) por concentrar um volume muito maior de IDs operacionais de
produção (o Base ID `appaCpIVj7Q97VhFy` e o ID de toda tabela/campo da
base real) do que qualquer documento de decisão — ver §1.4. Isso não é
o mesmo que "conter um segredo"; é uma escolha conservadora sobre
densidade de identificadores operacionais, registrada aqui de forma
genérica, sem reproduzir nenhum valor.

---

## 4. Conflitos arquiteturais detectados

### 4.1 "Item de Ingestão" (canônico) vs. "Documento" (implementado)

- **`MAGNATA_OS_ESTADOS.md`** (linhas 115-138, 921-1105) define a
  máquina de estados da entidade **"Item de Ingestão"**:
  `RECEBIDO → EM_VALIDACAO → VALIDADO → EM_PROCESSAMENTO → PROCESSADO`
  (mais `CANCELADO` como terminal alternativo).
- **`MAGNATA_OS_MODULO_01_INGESTAO.md`** e
  **`MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md`** (ex.:
  `DEC-MOD01-001`) também usam **"Item de Ingestão"** como o nome da
  entidade a implementar.
- **O código de fato implementado e já mesclado em `main`**
  (`magnata_os/documental/modulo01/dominio.py`, entidade `Documento`,
  enum `StatusDocumento`) usa **"Documento"**, com estados
  `RECEBIDO → REGISTRADO → (DUPLICADO | AGUARDANDO_PROCESSAMENTO) → EM_PROCESSAMENTO → EM_REVISAO/ERRO`
  — mesmo estado inicial, vocabulário e estrutura diferentes depois
  dele.
- **`MAGNATA_OS_DOCUMENTAL_MODULO01.md`** (já em `main`, é a entrega
  real) não cita nem uma vez os documentos fundacionais nem explica a
  troca de nome — a entidade simplesmente aparece como `Documento`, sem
  reconciliação registrada em lugar nenhum.

**Isso não foi resolvido nesta etapa** (não é permitido alterar decisão
de negócio em silêncio). Fica registrado como pendência (§6) para uma
decisão explícita: renomear os documentos fundacionais para
`Documento`, ou documentar `Documento` como uma especialização/apelido
de `Item de Ingestão` restrito ao Módulo 01.

### 4.2 Nenhum outro conflito de implementação encontrado

O modelo conceitual aprovado em `MAGNATA_OS_DECISOES_ENTIDADES.md`
("Modelo Conceitual Aprovado", `Cliente`/`Contrato Comercial`/
`Colaborador`/`Vínculo Trabalhista`/`Alocação`/`Posto de Trabalho`) não
tem, ainda, nenhuma contrapartida implementada — o Módulo 01 trata só
de `Documento`/`Lote`/`EstadoEsteiraDocumento`, então não há conflito
possível ainda, só ausência de implementação (esperado e já declarado
pelo próprio documento).

---

## 5. Decisões preservadas (não alteradas)

- As **3 decisões `PENDENTE`** em `MAGNATA_OS_DECISOES_ENTIDADES.md`
  (`DEC-ENT-010`, `DEC-ENT-011`, `DEC-ENT-012`) continuam `PENDENTE`.
  Nenhuma foi marcada como aprovada para "destravar" esta etapa.
- As **26 decisões `APROVADA`** do mesmo documento e as **13 decisões**
  (12 `APROVADA` + 1 `APROVADA POR CONTINUIDADE OPERACIONAL`) de
  `MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md` foram preservadas
  exatamente como estavam — nenhum texto de decisão foi editado.
- O conflito §4.1 foi **registrado, não resolvido** — nenhum documento
  foi editado para fazer "Item de Ingestão" e "Documento" concordarem.

---

## 6. Pendências

1. **Reconciliar "Item de Ingestão" vs. "Documento"** (§4.1) — decisão
   explícita necessária: qual nome é o vigente, e se um documento
   precisa de nova versão para refletir isso.
2. **`MAGNATA_OS_CAPACIDADES.md`, `MAGNATA_OS_MODULOS.md`,
   `MAGNATA_OS_ROADMAP.md`** não existem — `MAGNATA_OS_ENTIDADES.md` já
   previa `_CAPACIDADES.md` desde 2026-07-22 e ele nunca foi criado.
   Criar esses três é trabalho novo de conteúdo/decisão, fora do escopo
   desta etapa (que é preservação, não autoria).
3. **As 3 decisões `PENDENTE`** de `MAGNATA_OS_DECISOES_ENTIDADES.md`
   seguem aguardando resposta da Direção da Magnata.
4. **`RELATORIO_SCHEMA_AIRTABLE_COMPLETO.md`** — decidir separadamente
   se/como versionar (ex.: redigido para manter só o essencial, ou
   movido para um local com controle de acesso diferente), dado o
   volume de IDs operacionais de produção que carrega.
5. **Reorganização física para `docs/magnata-os/00-manifesto.md` etc.**
   — documentada como intenção em `docs/magnata-os/README.md`, não
   executada; precisa de uma etapa própria que reescreva as 294+
   referências cruzadas.
6. **`ENTREGA_FASES_A_B_C_D.md` e o cluster `FASE_A..D`** — permanecem
   não versionados; se alguém decidir que valem a pena preservar,
   pertencem a uma governança diferente (feature legada, não Magnata
   OS), fora do escopo deste Powerpack.

---

## 7. Riscos remanescentes

- **Nenhum owner explícito das 3 decisões `PENDENTE`** — enquanto
  seguirem assim, qualquer módulo futuro que dependa de
  `Contrato Comercial`/`Vínculo Trabalhista`/`Alocação` não tem base
  aprovada para implementar.
- **O conflito §4.1 pode se repetir** em outros pares plano↔implementação
  se nenhuma sessão futura (humana ou agente) checar
  sistematicamente nomes de entidade/estado do plano contra o código
  antes de uma nova fase começar.
- **`RELATORIO_SCHEMA_AIRTABLE_COMPLETO.md` continua no disco local**,
  fora do controle de versão — não é um risco novo introduzido por esta
  etapa, mas também não foi mitigado por ela.
- **A reorganização física adiada (§6.5)** significa que a estrutura
  `docs/magnata-os/` proposta no pedido original existe só como índice
  por enquanto — quem esperar encontrar os arquivos numerados dentro
  dela vai encontrar só o `README.md` apontando de volta para a raiz.

---

## Parecer

**FUNDAÇÃO PROTEGIDA** — os 9 documentos fundacionais (mais o
histórico citado) estão prestes a ser commitados nesta branch, com
índice de navegação, regra de precedência e nenhum segredo exposto. O
risco de perda total por falha de máquina, que motivou esta etapa,
está eliminado a partir do commit abaixo. O conflito de nomenclatura
(§4.1) e os três documentos ainda inexistentes (§6.2) permanecem como
trabalho pendente, explicitamente registrado — não como fundação em
risco.
