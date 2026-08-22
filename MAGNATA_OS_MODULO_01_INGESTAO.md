<!-- PROVENIÊNCIA (Etapa 3 da Central Command, 2026-08-22) — resgate documental.
Origem: branch `feat/magnata-os-claude-powerpack`, HEAD `053acada09dfc70bda71d2293aacbf2bca9ed43e`,
PR #12, FECHADO SEM MERGE em 2026-08-03T17:16:01Z. Texto original preservado;
as únicas alterações são a NOTA DE RECONCILIAÇÃO abaixo (quando existe) e a
de-identificação exigida por `CLAUDE.md` §6/LGPD, ambas declaradas.
Nenhuma decisão aprovada pela Direção foi alterada. -->

# Magnata OS — Módulo 01: Ingestão Documental Canônica

> **NOTA DE RECONCILIAÇÃO — Etapa 3, 2026-08-22.** Este é o **plano** do
> módulo, escrito antes da implementação. As Fases 1 a 4 já foram
> implementadas e mescladas em `main` (`magnata_os/documental/modulo01/`),
> e divergem deste plano em detalhe. Pela precedência de
> `docs/magnata-os/README.md` (item 1), **o código implementado prevalece
> sobre o plano** — e a divergência fica registrada, não corrigida em
> silêncio em nenhum dos dois lados. Fonte da verdade sobre o que existe:
> `MAGNATA_OS_DOCUMENTAL_MODULO01.md` e suas fases.

**Versão:** 1.0 (plano)
**Status:** PLANEJAMENTO — nenhuma linha de código implementada
**Data:** 2026-07-22
**Fontes:** `MAGNATA_OS_MANIFESTO.md`, `MAGNATA_OS_ARQUITETURA.md`,
`MAGNATA_OS_ENTIDADES.md`, `MAGNATA_OS_DECISOES_ENTIDADES.md`,
`MAGNATA_OS_EVENTOS.md`, `MAGNATA_OS_CONTRATOS.md`, `MAGNATA_OS_ESTADOS.md`,
mais evidência de código lida diretamente nesta sessão (`app.py`,
`apps_script_email_intake.gs`, `ENTREGA_FASES_A_B_C_D.md`,
`FASE_D_DECLARACOES_STATUS.md`).

**Achado novo desta etapa, não registrado nos documentos anteriores:**
existe uma **terceira via de entrada real**, via **Make.com**, além de
Gmail→Apps Script e upload/API direta — confirmada por evidência textual
concreta (`ENTREGA_FASES_A_B_C_D.md:150-152`: diagrama "MAKE.COM SCENARIO →
POST /separar"; `FASE_D_DECLARACOES_STATUS.md:443`: "Testar com PDF real via
Make.com scenario"). Isso corrige, para este documento, a suposição anterior
de que só existiam os canais Gmail/Apps Script/upload/API — **não foi
assumida sem evidência**, foi encontrada e é tratada como parte real do
levantamento (§2).

**Natureza deste documento:** planejamento de implementação. Nenhum
código, endpoint, classe, adaptador, tabela ou campo foi criado. Este
documento não deve ser lido como implementação concluída em nenhuma
circunstância.

---

## 1. Missão do Módulo

**Qual problema resolve:** hoje, receber um documento de origens diferentes
(e-mail, upload, Make.com) e prepará-lo para classificação é feito de forma
fragmentada — cada rota (`/email/webhook`, `/separar`, `/processar-fila`,
`/processar-doc-cliente`) implementa sua própria validação, seu próprio
hash, sua própria gravação em Airtable, com pequenas divergências entre
elas. O Módulo 01 concentra essa responsabilidade num único ponto,
canônico, e produz Item de Ingestão + Arquivo de forma consistente,
independente da origem.

**Responsabilidades do módulo:**
- Receber uma solicitação de ingestão.
- Validar metadados mínimos.
- Receber ou referenciar o Arquivo original.
- Calcular ou validar hash.
- Impedir duplicidade técnica indevida.
- Criar Item de Ingestão.
- Registrar Arquivo original.
- Preservar origem.
- Registrar auditoria.
- Gerar correlação (`correlation_id`).
- Disponibilizar o item para classificação.

**Responsabilidades que o módulo NÃO possui:**
- Decidir destinatários.
- Distribuir documentos.
- Colher assinatura.
- Cadastrar colaboradores.
- Decidir Cliente definitivo sem classificação.
- Executar regras de folha.
- Alterar documentos já classificados.
- Resolver pendências de ponto.

**Entradas aceitas:** ver §2 (portas de entrada).

**Saídas produzidas:** um Item de Ingestão (`MAGNATA_OS_CONTRATOS.md` §4) e
um ou mais Arquivos (§5) em estado `VALIDADO`/`PROCESSADO` (conforme a
máquina mínima, §8), disponibilizados para o módulo de Classificação via o
contrato de saída (§14) — nunca um Documento, nunca uma decisão de Tipo
Documental.

**Como preserva a operação atual:** o Módulo 01 **não substitui** nenhuma
rota existente nesta fase — ele nasce ao lado do legado (`app.py`) e só
assume o papel de porta principal na Fase 2 da estratégia strangler (§16),
depois de comprovado em modo sombra (Fase 1). Nenhuma rota atual
(`/email/webhook`, `/separar`, `/processar-fila`, `/processar-doc-cliente`)
é desligada por este plano.

**Como se integra temporariamente ao legado:** por um adaptador de saída
(§15) que converte o Item de Ingestão/Arquivo canônicos para o formato que
`Processar Arquivos`/`Arquivos`/`Emails Savian` ainda esperam, enquanto o
legado continuar sendo a fonte de classificação/processamento.

---

## 2. Portas de Entrada

**Fluxo confirmado por evidência direta (Gmail):**

```text
Gmail
→ Google Apps Script (processarEmails, gatilho horário)
→ POST /email/webhook (Render, protegido por X-API-KEY)
→ Airtable (Emails Savian + Arquivos + Processar Arquivos)
```

Confirmado em `apps_script_email_intake.gs` (função `processarEmails`,
gatilho `criarGatilhoHorario`) e `app.py:5028-5205` (`email_webhook`).
**Não há Make.com nesta via específica** — o e-mail vai direto do Apps
Script para o Render.

**Fluxo confirmado por evidência direta (Make.com):**

```text
Make.com scenario
→ POST /separar (multipart: processar_arquivo_record_id + arquivo pdf)
→ Airtable (upload do PDF ao registro Processar Arquivos já existente)
→ Celery (fatiamento assíncrono)
```

Confirmado em `app.py:3877-3936` (`separar`) e nos dois arquivos de fase
citados no cabeçalho. **Achado importante para a fronteira do módulo:** o
registro `Processar Arquivos` já existe **antes** de `/separar` ser
chamado — isso sugere que o Make.com scenario cria esse registro
diretamente via seu próprio conector Airtable, **fora** de qualquer rota do
`app.py`. Ou seja, parte do que hoje conta como "ingestão" acontece **fora
do código que o Módulo 01 vai substituir** — o módulo novo precisa decidir
explicitamente se absorve esse padrão (Make.com passa a chamar um endpoint
de ingestão canônico primeiro) ou se convive com ele por mais tempo (ver
decisão pendente em §22).

| Origem | Fluxo atual | Formato recebido | Identificadores disponíveis | Riscos | Adaptação necessária |
|---|---|---|---|---|---|
| **Gmail** | Apps Script lê e-mail, envia JSON para `/email/webhook` | JSON com `anexos[].conteudo_base64` | Gmail Message ID (`message_id`) | Apps Script é um sistema fora do controle direto do time (Google) — falha lá não gera evento no Magnata OS | adaptador precisa aceitar o mesmo payload JSON, sem mudar o contrato do lado do Apps Script nesta fase |
| **Google Apps Script** | mecanismo de transporte do Gmail para o Render (não é uma origem própria, é o "correio") | idem acima | idem acima | gatilho horário — atraso de até ~1h entre e-mail chegar e ser processado | nenhuma, é infraestrutura de transporte, não uma porta de entrada distinta |
| **Make.com** | scenario externo cria `Processar Arquivos` via Airtable, depois chama `/separar` com o PDF | multipart form (`processar_arquivo_record_id` + arquivo `pdf`) | Airtable Record ID (já existente antes da chamada) | scenario cria registro **fora** do fluxo de ingestão canônico — Item de Ingestão não existiria para esse caminho, a menos que o scenario seja adaptado | decisão pendente (§22): adaptar o scenario para chamar um endpoint de ingestão canônico primeiro, ou tratar isso como uma via legada separada por mais tempo |
| **Upload manual** | rotas como `/processar-fila`, `/processar-doc-cliente` recebem PDF via `request.files` ou payload JSON com URL | multipart ou JSON, variável por rota | nenhum ID externo — só o nome do arquivo | cada rota valida de um jeito diferente hoje (inconsistência já observada, ex. `/separar` verifica extensão e avisa sobre Content-Type sem bloquear) | unificar em um único ponto de validação canônico |
| **API do Render** | termo genérico para "qualquer rota HTTP do Flask" — não é uma origem à parte das listadas acima | — | — | — | não é uma porta de entrada distinta; é o mecanismo de transporte comum a todas |
| **Navegador** | **não evidenciado no código lido** — nenhuma automação de navegador (Playwright/Selenium/Puppeteer) encontrada em `app.py`; a única ocorrência da palavra "Navegador" é um rótulo de User-Agent em evidência de assinatura, sem relação com ingestão | — | — | — | **nenhuma adaptação necessária agora** — não criar suporte a uma origem sem evidência de uso real (Manifesto, princípio 9, API antes de navegador) |

**Confirmado, conforme pedido:** o fluxo real de Gmail é exatamente
`Gmail → Google Apps Script → Render → Airtable` — sem Make.com nesse
caminho específico. Make.com **existe**, mas atua num caminho paralelo
(`/separar`), não no caminho de e-mail.

---

## 3. Fronteira do Módulo

### Antes da Ingestão (fora do módulo)
- Obtenção do arquivo no sistema externo (Gmail, Make.com scenario).
- Autenticação no provedor externo (conta de e-mail, credencial do Make.com).
- Download por navegador — não aplicável hoje (§2).
- Leitura do e-mail (Apps Script).
- Seleção manual do arquivo (quem faz upload).

### Dentro da Ingestão (responsabilidade do módulo)
- Recebimento da solicitação (via qualquer porta de §2).
- Validação de metadados mínimos.
- Registro do Item de Ingestão.
- Cálculo/validação de hash.
- Verificação de idempotência (§9).
- Identificação de origem.
- Criação ou registro do Arquivo original.
- Auditoria (§13).
- Disponibilização para Classificação (§14).

### Depois da Ingestão (fora do módulo)
- Classificação (Tipo Documental, Competência, titularidade).
- Identificação documental (Cliente/Colaborador).
- Fatiamento (separar um PDF mestre em páginas por CPF).
- Criação do Documento.
- Distribuição.
- Assinatura.

**Nota sobre o legado atual:** hoje, `email_webhook` (`app.py:5028-5205`)
**mistura** ingestão e classificação na mesma função — extrai texto do PDF
e chama `classificar_documento(texto)` antes de sequer criar o registro
`Processar Arquivos`. O Módulo 01, como planejado, **não replica essa
mistura** — a fronteira acima é o alvo; a primeira implementação pode, por
pragmatismo, ainda invocar a Classificação como chamada de função direta
dentro do mesmo processo (monólito modular, `MAGNATA_OS_ARQUITETURA.md`
§3), mas o **contrato** entre os dois módulos (§14) já força a separação
lógica desde o início.

---

## 4. Entidades Utilizadas

- **Item de Ingestão** — entidade central deste módulo. Existe **antes**
  da classificação (`MAGNATA_OS_ENTIDADES.md` §5).
- **Arquivo** — o Arquivo original pode existir sem Documento relacionado
  (`documento_id` ausente até a classificação, DEC-ENT-015).
- **Empresa** — sempre a Magnata; usada só como `empresa_id` de referência,
  sem lógica própria neste módulo.
- **Documento** — **apenas como entidade futura resultante**. O Módulo 01
  nunca cria um Documento — isso é responsabilidade da Classificação.
- **Evento de auditoria** — tratado conceitualmente via o Envelope de
  Evento (`MAGNATA_OS_CONTRATOS.md` §14); não existe uma entidade formal de
  "Evento de Auditoria" implementada — é lacuna conhecida, registrada em
  `MAGNATA_OS_ENTIDADES.md` §10 (achado #9), fora do escopo resolver aqui.
- **Erro** — usado conforme `MAGNATA_OS_CONTRATOS.md` §15, para toda falha
  do módulo (§12).

**Explicado expressamente:**
- Item de Ingestão existe antes da classificação — o Módulo 01 termina
  onde a Classificação começa (§3).
- Arquivo original pode existir sem Documento relacionado — é o estado
  normal de um Arquivo recém-criado por este módulo.
- Um Item de Ingestão pode originar vários Documentos (ex.: um e-mail com
  múltiplos anexos de tipos diferentes) — o Módulo 01 não decide quantos
  Documentos nascerão, só disponibiliza os Arquivos.
- Um Documento pode receber Arquivos de mais de um Item de Ingestão (ex.:
  uma correção que chega por um e-mail diferente do original) — isso
  ocorre depois da fronteira deste módulo, mas o Item de Ingestão criado
  aqui precisa preservar identidade suficiente para essa relação futura
  ser rastreável.
- **Ingestão não decide automaticamente o Tipo Documental** — mesmo
  quando o texto já permitiria inferir isso (como o legado faz hoje), o
  Módulo 01, por contrato, não grava essa decisão.

---

## 5. Contratos Utilizados

Contratos canônicos aplicáveis (`MAGNATA_OS_CONTRATOS.md` §4, §5, §14,
§15) — nenhum campo novo é criado aqui, é uso do que já foi definido.

### Item de Ingestão

| Campo canônico | Obrigatório | Origem possível | Validação | Correspondência no legado |
|---|---:|---|---|---|
| `item_ingestao_id` | Sim | gerado pelo módulo | identificador único | (não existe hoje — seria o Record ID de `Emails Savian`) |
| `empresa_id` | Sim | fixo (Magnata) | — | — |
| `origem` | Sim | Gmail/Make.com/Upload Manual/API | deve ser um dos valores do enum (§2) | inferido implicitamente pela rota chamada |
| `origem_externa_id` | Não | Gmail Message ID, quando `origem = EMAIL` | obrigatório se `origem = EMAIL` | `Emails Savian.MESSAGE ID` |
| `recebido_em` | Sim | timestamp da chamada | ISO 8601 com fuso | `Emails Savian.Created`/timestamp implícito |
| `hash_sha256` | Sim | calculado a partir do conteúdo recebido | SHA-256 válido | `Arquivos.Hash do Anexo` (já calculado hoje, `hashlib.sha256`) |
| `correlation_id` | Sim | gerado pelo módulo | identificador único | não existe hoje |
| `status_ingestao` | Sim | máquina de estados (§8) | um dos valores do vocabulário | `Emails Savian.Status` (`F_EMAIL_STATUS`, hoje só `'Recebido'` confirmado) |
| `nome_original` | Não | nome do anexo | — | `anexo.nome_arquivo` |
| `mime_type` | Não | detectado ou informado | — | não validado de forma robusta hoje (§11) |
| `tamanho_bytes` | Não | calculado | ≤ limite (§11) | `len(conteudo)` (já calculado hoje) |
| `remetente` | Não | só quando `origem = EMAIL` | — | `data.get('remetente')` |
| `assunto` | Não | só quando `origem = EMAIL` | — | `Emails Savian.Assunto` |

### Arquivo

| Campo canônico | Obrigatório | Origem possível | Validação | Correspondência no legado |
|---|---:|---|---|---|
| `arquivo_id` | Sim | gerado pelo módulo | identificador único | Record ID de `Arquivos` |
| `item_ingestao_id` | Sim | relação com o Item de Ingestão | deve existir | `Arquivos.Emails Savian` (`F_ARQ_EMAILS`) |
| `nome` | Sim | nome recebido | — | `F_ARQ_NOME`/`F_ARQ_NOME_ARQ` |
| `mime_type` | Sim | detectado | deve corresponder ao conteúdo real (§11) | não validado hoje além da extensão `.pdf` |
| `tamanho_bytes` | Sim | calculado | ≤ limite (§11 — hoje 50 MB via `MAX_CONTENT_LENGTH`) | `len(conteudo)` |
| `hash_sha256` | Sim | calculado | usado para deduplicação | `F_ARQ_HASH` (já em uso, checado antes de criar) |
| `versao` | Sim | `1` para todo Arquivo criado pela Ingestão | — | não existe hoje (DEC-ENT-017, novo) |
| `papel_arquivo` | Sim | sempre `ORIGINAL` para Arquivo criado por este módulo | — | não existe hoje |
| `criado_em` | Sim | timestamp | ISO 8601 com fuso | `F_ARQ_DATA` |
| `vigente` | Sim | sempre `true` para Arquivo recém-criado | — | não existe hoje |

**Não foi criado JSON Schema. Não foram definidas classes Python** — as
tabelas acima são a especificação conceitual, consistente com
`MAGNATA_OS_CONTRATOS.md` §4-§5.

---

## 6. Comandos Conceituais

### `ReceberItemIngestao`

**Finalidade:** registrar uma nova entrada documental.
**Pré-condições:** origem reconhecida (§2); payload sintaticamente válido
para aquela origem.
**Dados de entrada:** conforme a origem — JSON (Gmail/Make.com) ou
multipart (upload manual); no mínimo, o conteúdo do Arquivo e um
identificador de origem, quando existir.
**Resultado esperado:** um Item de Ingestão em estado `RECEBIDO`.
**Eventos de sucesso:** `ItemIngestaoRecebido`.
**Eventos de falha:** `IngestaoFalhou` (payload inválido, origem não
autorizada).
**Regra de idempotência:** chave = `origem_externa_id` (quando existir) ou
`hash_sha256` do conteúdo — reentrega não cria um segundo Item de
Ingestão (§9).
**Ator autorizado:** sistemas de origem autenticados (Apps Script via
`X-API-KEY`, Make.com via mecanismo equivalente a definir, upload manual
via sessão/autenticação da aplicação).

### `ValidarItemIngestao`

**Finalidade:** verificar integridade e metadados mínimos.
**Pré-condições:** Item de Ingestão em `RECEBIDO`.
**Dados de entrada:** o próprio Item de Ingestão e seu(s) Arquivo(s)
associado(s).
**Resultado esperado:** transição para `VALIDADO` ou `REJEITADO`.
**Eventos de sucesso:** `ItemIngestaoValidado`.
**Eventos de falha:** `ItemIngestaoRejeitado` (regra de negócio — remetente
não confiável, tipo não permitido) ou `IngestaoFalhou` (erro técnico).
**Regra de idempotência:** validar o mesmo Item duas vezes produz o mesmo
resultado, sem duplicar o registro.
**Ator autorizado:** o próprio módulo (processo automático), sem
intervenção humana nesta etapa.

### `RegistrarArquivoOriginal`

**Finalidade:** registrar a representação digital recebida.
**Pré-condições:** Item de Ingestão em `VALIDADO`; conteúdo do Arquivo
disponível.
**Dados de entrada:** bytes do Arquivo, nome, MIME.
**Resultado esperado:** um Arquivo com `papel_arquivo = ORIGINAL`,
`vigente = true`, vinculado ao Item de Ingestão.
**Eventos de sucesso:** `ArquivoExtraido`.
**Eventos de falha:** `IngestaoFalhou` (falha de armazenamento, hash não
calculável).
**Regra de idempotência:** mesmo `hash_sha256` para o mesmo
`item_ingestao_id` não cria um segundo Arquivo (§9) — reconhece o
existente.
**Ator autorizado:** o próprio módulo.

### `DisponibilizarParaClassificacao`

**Finalidade:** tornar o item elegível para o módulo seguinte.
**Pré-condições:** ao menos 1 Arquivo registrado com sucesso para o Item de
Ingestão.
**Dados de entrada:** `item_ingestao_id`, lista de `arquivo_id`.
**Resultado esperado:** transição para `PROCESSADO` (ou o nome equivalente
do subconjunto de estados, §8) — item consumido pela Ingestão, pronto para
o próximo módulo.
**Eventos de sucesso:** nenhum evento próprio adicional — a disponibilização
é o efeito agregado de `ArquivoExtraido` já ter ocorrido para todos os
Arquivos esperados; ver nota crítica em §7 sobre se isso merece evento
próprio.
**Eventos de falha:** não aplicável diretamente — falhas anteriores já
teriam impedido chegar aqui.
**Regra de idempotência:** disponibilizar o mesmo item mais de uma vez não
gera efeito duplicado no módulo de Classificação (a chamada/mensagem para
Classificação carrega o mesmo `correlation_id`).
**Ator autorizado:** o próprio módulo.

---

## 7. Eventos Mínimos do Módulo

Só os necessários — nenhum evento novo além do catálogo já aprovado
(`MAGNATA_OS_EVENTOS.md`):

- `ItemIngestaoRecebido`
- `ItemIngestaoValidado`
- `ItemIngestaoRejeitado`
- `ArquivoExtraido` (avaliação abaixo)
- `IngestaoFalhou`

**Avaliação pedida — `ArquivoExtraido` pertence à Ingestão ou à
Transformação?** Pertence à **Ingestão**. A definição em
`MAGNATA_OS_EVENTOS.md` §A é "um Arquivo foi extraído/anexado a partir de
um Item de Ingestão" — isto é, o anexo foi **desanexado do e-mail/payload
de origem e persistido como Arquivo próprio**, não "o texto foi extraído do
PDF para fins de classificação". Essa segunda operação (extração de texto
para classificar) é responsabilidade da Classificação, mesmo que o legado
hoje a execute na mesma função (`pdfplumber` dentro de `email_webhook`,
§3). O nome do evento é ambíguo o suficiente para justificar esta nota
explícita — **nenhum outro módulo deve reaproveitar `ArquivoExtraido` para
significar "texto extraído"**.

**Nenhum evento novo foi criado** — `ArquivoExtraido`,
`ItemIngestaoRecebido`, `ItemIngestaoValidado`, `ItemIngestaoRejeitado` e
`IngestaoFalhou` já existiam no catálogo aprovado.

---

## 8. Máquina Mínima de Estados

Subconjunto da máquina de Item de Ingestão (`MAGNATA_OS_ESTADOS.md` §3):

`RECEBIDO`, `EM_VALIDACAO`, `VALIDADO`, `REJEITADO`, `FALHA_TEMPORARIA`,
`FALHA_DEFINITIVA`, `CANCELADO` — **7 estados**.

**`EM_PROCESSAMENTO` e `PROCESSADO` ficam para a etapa de Classificação/
Transformação** — não porque a máquina completa de Item de Ingestão
(`MAGNATA_OS_ESTADOS.md` §3, 9 estados) esteja errada, mas porque o **valor
que este módulo específico entrega** é ir até `VALIDADO`, mais o registro
do Arquivo. A transição para `EM_PROCESSAMENTO`/`PROCESSADO` representa,
na prática, "a Classificação começou a trabalhar em cima disto" — que é o
próximo módulo, não este. Manter essas duas transições fora do Módulo 01
evita que ele precise saber quando a Classificação "termina", o que
violaria a fronteira de §3.

**Tabela de transições da primeira implantação:**

| Estado atual | Comando ou condição | Evento obrigatório | Novo estado | Evidência necessária | Transição automática? | Observações |
|---|---|---|---|---|---|---|
| (nenhum) | `ReceberItemIngestao` | `ItemIngestaoRecebido` | `RECEBIDO` | payload aceito de origem reconhecida | Não | — |
| `RECEBIDO` | início da validação | — | `EM_VALIDACAO` | — | Sim | — |
| `EM_VALIDACAO` | `ValidarItemIngestao` aprovado | `ItemIngestaoValidado` | `VALIDADO` | metadados mínimos + origem confiável | Sim | — |
| `EM_VALIDACAO` | `ValidarItemIngestao` reprovado | `ItemIngestaoRejeitado` | `REJEITADO` | motivo de rejeição registrado | Sim | terminal do Módulo 01 |
| `VALIDADO` | `RegistrarArquivoOriginal` + `DisponibilizarParaClassificacao` | `ArquivoExtraido` | (entrega ao próximo módulo — fora do vocabulário de 7 estados, ver nota) | Arquivo(s) persistido(s) | Sim | o Item "sai" da responsabilidade do Módulo 01 aqui |
| `RECEBIDO`/`EM_VALIDACAO` | erro técnico recuperável | `IngestaoFalhou` (`retryable=true`) | `FALHA_TEMPORARIA` | erro contextualizado (§12) | Sim | — |
| `FALHA_TEMPORARIA` | retry dentro do limite | — | `EM_VALIDACAO` (ou `RECEBIDO`, conforme onde falhou) | — | Sim | — |
| `FALHA_TEMPORARIA` | limite esgotado | `IngestaoFalhou` (`retryable=false`) | `FALHA_DEFINITIVA` | — | Sim | terminal |
| qualquer estado não-terminal | cancelamento operacional | — | `CANCELADO` | decisão registrada | Não | terminal |

**Nota sobre a transição a partir de `VALIDADO`:** como este módulo não
possui `EM_PROCESSAMENTO`/`PROCESSADO` no seu próprio vocabulário, a
transição de `VALIDADO` para "disponível para Classificação" é modelada
como a **saída** do Item de Ingestão da responsabilidade do Módulo 01, não
como um estado adicional dentro dele — a máquina completa de
`MAGNATA_OS_ESTADOS.md` §3 continua sendo a referência de longo prazo; este
módulo implementa só a parte que lhe cabe.

---

## 9. Idempotência e Duplicidade

Sete situações distintas, tratadas separadamente:

| Situação | Como é tratada |
|---|---|
| **Repetição da mesma chamada** (retry técnico do cliente/provedor) | reconhecida pela chave de idempotência da chamada (§ abaixo) — não cria novo Item de Ingestão |
| **Recebimento duplicado do mesmo anexo** (ex.: Apps Script reenvia o mesmo e-mail) | reconhecida por `origem_externa_id` (Gmail Message ID) já existente — já implementado no legado (`_buscar_por_campo(TABLE_EMAILS, 'MESSAGE ID', ...)`, `app.py:5084`) |
| **Mesmo Arquivo enviado por origens diferentes** (ex.: mesmo PDF chega por e-mail e por upload manual) | reconhecido por `hash_sha256` do conteúdo — já implementado no legado para Arquivo (`_buscar_por_campo(TABLE_ARQUIVOS, 'Hash do Anexo', ...)`, `app.py:5124`); **decisão de negócio pendente** (§22): dois Itens de Ingestão distintos podem apontar para o mesmo Arquivo (é permitido, N:1), mas isso não é o mesmo que "mesmo Documento" |
| **Mesmo conteúdo relacionado a processos diferentes** (ex.: o mesmo comprovante enviado para dois clientes distintos por engano, ou legitimamente comum a vários) | **não é duplicidade técnica** — hash igual não implica mesmo Documento (DEC-ENT-006, documento comum); a decisão de mesclar ou não pertence à Classificação, não à Ingestão |
| **Novo Arquivo com mesmo nome** (nome igual, conteúdo diferente) | **não é duplicidade** — `hash_sha256` diferente identifica como Arquivo novo; o nome nunca é usado como chave |
| **Novo Arquivo com hash diferente** | tratado como Arquivo genuinamente novo, sempre |
| **Reprocessamento deliberado** (alguém pede para reingerir algo de propósito) | precisa de um sinalizador explícito de intenção (equivalente ao `motivo_nova_solicitacao` de outros contratos) — **decisão pendente** (§22) sobre como esse sinalizador é expresso na chamada |

**Definido conceitualmente:**
- **Chave de idempotência da chamada:** combinação de origem +
  `origem_externa_id` (quando existir) — evita que uma reentrega técnica
  da mesma chamada HTTP crie dois Itens de Ingestão.
- **Hash do Arquivo:** SHA-256 do conteúdo — já em uso real no legado,
  reaproveitado como está.
- **ID externo da origem:** Gmail Message ID (hoje); Airtable Record ID
  pré-existente, no caso do Make.com (`processar_arquivo_record_id`) — este
  último é um caso especial que **não é** um ID de origem no sentido usual,
  é uma referência a um registro já criado fora do módulo (§2, achado sobre
  Make.com).
- **Janela de deduplicação:** **decisão pendente** (§22) — hoje o legado
  não expira a checagem de hash (é permanente, contra toda a tabela
  `Arquivos`); manter esse comportamento ou limitar a uma janela de tempo é
  uma escolha ainda em aberto.
- **Regra para duplicidade legítima:** quando um hash idêntico é
  legitimamente esperado (ex.: reenvio intencional do mesmo documento por
  outro canal), o módulo reconhece o Arquivo existente e **não** cria um
  segundo — mas registra o novo Item de Ingestão como a origem adicional,
  se a relação N:1 Item→Arquivo permitir isso (ver `MAGNATA_OS_ENTIDADES.md`
  §5, "um Documento pode receber Arquivos de mais de um Item de Ingestão").
- **Comportamento quando o resultado anterior estiver incompleto:** se o
  Item de Ingestão anterior com o mesmo `origem_externa_id`/`hash_sha256`
  ficou em `FALHA_TEMPORARIA` ou não chegou a `VALIDADO`, a nova chamada
  **retoma** esse Item (nova Tentativa dentro do mesmo Item), em vez de
  criar um segundo — consistente com o princípio de "retry técnico não
  reinicia silenciosamente o ciclo" (`MAGNATA_OS_ESTADOS.md` §1).

**Registrado expressamente:** **mesmo hash não significa necessariamente
mesmo Documento** — a Ingestão só garante que o mesmo **Arquivo** (bytes
idênticos) não é duplicado; a decisão de que dois Arquivos idênticos
pertencem ao mesmo Documento, a Documentos diferentes, ou a um Documento
comum (DEC-ENT-006) é inteiramente da Classificação.

---

## 10. Armazenamento do Arquivo

**Situação atual:** todo Arquivo hoje é armazenado como **anexo do
Airtable** (`multipleAttachments`), via `_anexar_attachment` (`app.py`) —
não há storage externo de objetos em uso. Arquivos temporários passam por
`/tmp` durante o processamento (ex.: `f'/tmp/email_{uuid}.pdf'`) e são
apagados logo depois (`os.unlink`, boa prática já presente).

**Opções conceituais (nenhuma implementada aqui):**

| Opção | Descrição |
|---|---|
| Airtable attachment | mantém o padrão atual — simples, mas sujeito a limites de tamanho/plano do Airtable e sem controle fino de acesso |
| Armazenamento externo de objetos (S3-compatível, GCS) | desacopla o binário do Airtable, permite políticas de retenção/acesso próprias, mas exige nova infraestrutura |
| Google Drive | possível, dado que o ecossistema já usa Google (Gmail, Apps Script) — mas introduz mais uma integração e mais uma superfície de autenticação |
| Storage do provedor de hospedagem (Render) | Render não oferece storage de objetos persistente nativo hoje conhecido — não avaliado em detalhe por falta de necessidade imediata |
| Referência temporária (sem persistência própria do módulo) | delega toda persistência ao Airtable, com o módulo só processando em memória/`/tmp` — é, na prática, o que o legado já faz |
| Combinação temporária durante a migração | Módulo 01 grava no Airtable (compatibilidade) e, em paralelo, num storage externo (preparação para o futuro) — maior custo operacional imediato |

**Riscos da situação atual:** limite de tamanho de anexo e de armazenamento
total por base do Airtable (não quantificado nesta sessão); ausência de
controle de acesso granular por Arquivo (quem pode baixar o quê depende do
controle de acesso do Airtable como um todo); ausência de trilha de
auditoria própria sobre acesso ao binário (o Airtable não expõe isso ao
Magnata OS hoje).

**Limite operacional confirmado:** `MAX_CONTENT_LENGTH = 50 * 1024 * 1024`
(50 MB) já configurado em `app.py:62` — limite real de upload por
requisição, independente de onde o Arquivo acabe armazenado.

**Recomendação para a primeira fase:** manter Airtable attachment — é o que
já funciona, evita risco de migração de dado desnecessário nesta etapa, e
está alinhado ao princípio de operação preservada (Manifesto, princípio 1).

**Recomendação de longo prazo:** avaliar armazenamento externo de objetos
quando o volume ou o custo do Airtable se tornarem um limitador real —
**não avaliado como necessário agora**, sem evidência de que o limite atual
já foi atingido.

**Nenhuma compra ou alteração de infraestrutura foi realizada ou
recomendada como ação imediata.**

---

## 11. Segurança

| Controle | Situação atual | Gap identificado |
|---|---|---|
| Tamanho máximo | `MAX_CONTENT_LENGTH = 50 MB` (`app.py:62`) | nenhum — já implementado |
| Tipos MIME permitidos | checagem de extensão `.pdf` em algumas rotas (`app.py:3920`, `app.py:5135`) | **inconsistente entre rotas** — nem toda rota valida |
| Extensão versus MIME real | `/separar` checa `content_type` mas **só avisa (log), não bloqueia** quando diverge (`app.py:3930-3933`, comentário explícito "Permitir se não foi fornecido, mas avisar se foi e está errado") | **gap real de segurança** — um arquivo com extensão `.pdf` e Content-Type divergente passa hoje |
| PDF protegido por senha | sem tratamento dedicado — `pdfplumber` provavelmente falha ao extrair texto, caindo em "PDF ilegível" | tratado como falha de extração, não como caso de segurança a sinalizar separadamente |
| Arquivos corrompidos | mesma via de falha de extração acima | idem — não há distinção entre corrompido e apenas protegido |
| Malware | **nenhuma varredura encontrada** | gap real — nenhum antivírus/scanner integrado hoje |
| Nomes de arquivo inseguros | sem sanitização explícita encontrada (path traversal, caracteres de controle) | gap a fechar antes de qualquer gravação em disco/storage externo |
| Conteúdo executável | não hoje possível via `.pdf` obrigatório em algumas rotas, mas outras rotas (Gmail) aceitam qualquer `nome_arquivo` do payload | gap — o e-mail não valida extensão do anexo antes de processar |
| Arquivos excessivamente grandes | coberto por `MAX_CONTENT_LENGTH`, mas só no nível HTTP — o payload JSON do e-mail (base64) não tem limite próprio verificado nesta leitura | gap potencial — base64 infla ~33% o tamanho, pode escapar do limite intencionado |
| Metadados sensíveis | não avaliado nesta sessão | fora do escopo desta leitura |
| Credenciais e tokens | `X-API-KEY` já usado para proteger `/email/webhook` (`app.py:5052`) | manter — nunca logar a chave (§13) |
| Acesso ao Arquivo | controlado pela API Key do Airtable, indiretamente | sem controle granular por Arquivo (ver §10) |
| Retenção temporária | `/tmp` já limpo após uso (`os.unlink`, `finally`) | boa prática já presente — manter |

**Não implementar antivírus nesta etapa** — registrado como necessidade
real (linha "Malware" acima), com ponto de integração recomendado: entre
`RegistrarArquivoOriginal` e a persistência final do Arquivo, antes de
disponibilizar para Classificação.

---

## 12. Erros

| Código | Categoria | Retry possível | Estado resultante | Mensagem segura | Evidência necessária | Ação operacional |
|---|---|---|---|---|---|---|
| `INGESTAO_PAYLOAD_INVALIDO` | Validação | Não | `REJEITADO` | "Payload de ingestão inválido" | payload bruto (protegido) | corrigir na origem |
| `INGESTAO_ARQUIVO_AUSENTE` | Validação | Não | `REJEITADO` | "Arquivo não encontrado na solicitação" | metadados da chamada | verificar origem |
| `INGESTAO_TIPO_NAO_PERMITIDO` | Negócio | Não | `REJEITADO` | "Tipo de arquivo não permitido" | MIME/extensão detectados | revisar política de tipos permitidos |
| `INGESTAO_ARQUIVO_CORROMPIDO` | Técnica | Sim (1x) | `FALHA_TEMPORARIA` → `FALHA_DEFINITIVA` | "Não foi possível ler o arquivo" | erro de parsing | solicitar reenvio na origem |
| `INGESTAO_DUPLICIDADE_TECNICA` | Negócio (não é falha) | Não aplicável | mantém o Item/Arquivo existente | "Conteúdo já registrado" | hash coincidente | nenhuma — comportamento esperado |
| `INGESTAO_ORIGEM_NAO_AUTORIZADA` | Segurança | Não | `REJEITADO` | "Origem não autorizada" | credencial/chave apresentada (protegida) | investigar tentativa de acesso |
| `INGESTAO_ARMAZENAMENTO_INDISPONIVEL` | Integração externa | Sim | `FALHA_TEMPORARIA` → `FALHA_DEFINITIVA` | "Armazenamento temporariamente indisponível" | erro do provedor de storage | acompanhar disponibilidade do Airtable |
| `INGESTAO_HASH_FALHOU` | Técnica | Sim | `FALHA_TEMPORARIA` | "Falha ao processar o arquivo" | erro de cálculo de hash | investigar biblioteca/ambiente |
| `INGESTAO_REGISTRO_FALHOU` | Técnica | Sim | `FALHA_TEMPORARIA` → `FALHA_DEFINITIVA` | "Falha ao registrar a entrada" | erro de gravação no Airtable | acompanhar disponibilidade do Airtable |
| `INGESTAO_RESULTADO_INCERTO` | Técnica | Sim, com cautela | permanece no estado anterior + marcador de reconciliação (`MAGNATA_OS_ESTADOS.md` §14) | "Resultado da operação não confirmado" | timeout sem resposta definitiva | reconciliar manualmente antes de assumir sucesso ou falha |

---

## 13. Auditoria e Observabilidade

**Registros mínimos por Item de Ingestão processado:**

origem; ator ou sistema; horário recebido; horário registrado; hash;
tamanho; MIME; nome original; ID externo (quando existir); Item de
Ingestão criado (`item_ingestao_id`); Arquivo criado (`arquivo_id`);
`correlation_id`; `request_id`; resultado; erro (quando houver); duração da
operação; número da tentativa.

**Logs estruturados nunca expõem:**
- token (ex.: `X-API-KEY`, credenciais de Make.com/Apps Script);
- conteúdo integral do arquivo ou do e-mail (hoje o legado já loga um
  resumo — `assunto`, contagem de anexos — não o corpo completo,
  `app.py:5071-5074` — manter esse padrão, não regredir);
- senha;
- dados pessoais desnecessários (CPF/CNPJ só quando estritamente
  necessário à operação, nunca "porque apareceu no texto");
- URL sensível completa (ex.: uma URL de armazenamento com token de acesso
  embutido).

---

## 14. Integração com Classificação

**Contrato de saída do módulo** — o que a Classificação recebe:

- `item_ingestao_id`
- `arquivo_id` (um ou mais)
- `correlation_id`
- contexto mínimo autorizado (ex.: `remetente`, `assunto`, quando
  existirem — os mesmos sinais que hoje ajudam a classificar documentos
  coletivos sem CNPJ legível, `MAGNATA_OS_ENTIDADES.md` §5)
- `origem`
- metadados úteis (`mime_type`, `tamanho_bytes`)

**Não deve depender de:**
- nomes de campos do Airtable (`F_PROC_TIPO_DOC`, `F_ARQ_HASH`, etc.);
- a tabela `Processar Arquivos` diretamente;
- a distinção `Arquivos` versus `Arquivos 2` (é um detalhe de
  implementação do legado, nunca do contrato);
- `Status` legado (o contrato usa `status_ingestao` conceitual,
  `MAGNATA_OS_CONTRATOS.md` §4);
- rota específica de entrada (o contrato é o mesmo, venha o Item de
  Ingestão de Gmail, Make.com ou upload manual).

Este contrato é exatamente o já definido em `MAGNATA_OS_CONTRATOS.md` §4
(`ItemIngestao`) — o Módulo 01 não cria um contrato novo, implementa o que
já foi aprovado.

---

## 15. Adaptador para o Legado

**Planejado, não implementado.**

**Objetivos:**
- manter o fluxo atual funcionando sem interrupção;
- converter o contrato canônico (Item de Ingestão + Arquivo) na estrutura
  que o legado espera (`Emails Savian` + `Arquivos` + `Processar
  Arquivos`);
- impedir que nomes legados (`F_PROC_TIPO_DOC`, `F_ARQ_HASH`, etc.) vazem
  para dentro do núcleo novo — só o adaptador os conhece;
- registrar o que foi convertido, para auditoria da própria migração;
- medir dependência do legado (quais consumidores ainda leem os campos
  antigos);
- permitir retirada futura, quando a telemetria confirmar que não há mais
  consumidor do caminho legado.

**Mapeamento a planejar (não implementado):**

| Conceito legado | Fonte | Nota |
|---|---|---|
| `Tipo` | campo de `Processar Arquivos` | pertence à Classificação, não à Ingestão — o adaptador de Ingestão não escreve este campo |
| `Tipo de Documento` | idem | idem — e carrega o débito conhecido de mistura com erro técnico (`MAGNATA_OS_ARQUITETURA.md` §8), que o Módulo 01 não deve herdar |
| `Arquivos` | tabela `Arquivos` | corresponde diretamente ao Contrato de Arquivo (§5) |
| `Arquivos 2` | campo de link em `Processar Arquivos` | é a relação Documento↔Arquivo — fora do escopo do Módulo 01 (essa relação só existe depois da Classificação) |
| `Status` | `Emails Savian`/`Arquivos`/`Processar Arquivos` | o adaptador traduz `status_ingestao` canônico para o valor de `Status` que cada tabela legada espera (hoje confirmado: `'Recebido'`) |
| IDs do Airtable | Record ID de cada tabela | tratados só como `identificadores_legados`/referência externa (§2.1 de `MAGNATA_OS_CONTRATOS.md`), nunca como `item_ingestao_id`/`arquivo_id` |
| Origem do formulário | rota chamada (`/email/webhook`, `/separar`, etc.) | vira o campo `origem` do contrato canônico |
| Payload do Apps Script | JSON com `message_id`/`anexos[].conteudo_base64` | mapeado diretamente para `origem_externa_id`/Arquivo(s) |

**O adaptador não foi implementado nesta etapa.**

---

## 16. Estratégia Strangler

**Sem datas definidas — só a sequência de fases.**

### Fase 0 — Observação
- Mapear tráfego atual (volume por rota: `/email/webhook`, `/separar`,
  `/processar-fila`, `/processar-doc-cliente`).
- Registrar volumes por origem (Gmail, Make.com, upload manual).
- Identificar origens não mapeadas, se houver.
- Medir falhas atuais (taxa de `Erro` por rota).
- **Não altera comportamento algum.**

### Fase 1 — Shadow Mode
- O Módulo 01 recebe uma **cópia** das entradas atuais (ou dos eventos que
  as representam), em paralelo ao legado.
- Valida e registra Item de Ingestão/Arquivo **sem** assumir a operação
  real.
- Compara resultado (hash calculado, decisão de validação) com o que o
  legado produziu para a mesma entrada.
- **Não gera efeito externo** — nenhuma gravação que o legado não faria de
  qualquer forma.

### Fase 2 — Ingestão Canônica como Porta Principal
- Entradas passam a ser recebidas pelo Módulo 01 primeiro.
- O adaptador de saída (§15) alimenta o legado a partir do resultado do
  Módulo 01.
- O legado continua responsável por classificação e processamento —
  inalterado.

### Fase 3 — Classificação Canônica
- Fora do escopo deste módulo, mas citada para contexto: a Classificação
  nova passa a consumir o Item de Ingestão diretamente (contrato de §14),
  com o legado permanecendo como fallback controlado.

### Fase 4 — Retirada das Portas Paralelas
- Desligamento gradual das rotas legadas de ingestão, guiado por
  telemetria (uso real medido, não suposição).
- Plano de rollback disponível a cada etapa.
- Documentação operacional atualizada antes de cada desligamento.

---

## 17. Critérios de Entrada para Implementação

O módulo só pode começar a ser implementado quando estiver definido:

1. Responsável técnico.
2. Repositório ou pacote onde o módulo viverá.
3. Estratégia de armazenamento (§10) confirmada para a primeira fase.
4. Contrato v1 aprovado (`MAGNATA_OS_CONTRATOS.md` §4-§5 — já aprovado;
   confirmar que nenhuma mudança foi necessária neste plano).
5. Máquina mínima aprovada (§8).
6. Política de idempotência definida (§9) — incluindo as decisões
   pendentes de §22.
7. Fontes de entrada prioritárias definidas (qual origem migra primeiro —
   decisão pendente, §22).
8. Estratégia de shadow mode (§16, Fase 1) detalhada operacionalmente.
9. Métricas (§19) instrumentadas antes do primeiro tráfego real.
10. Rollback definido para cada fase da estratégia strangler.
11. Dados de teste preparados (§20).
12. Tratamento de PDFs (senha, corrompido) decidido — hoje é só uma via de
    falha de extração (§11); decidir se merece tratamento diferenciado.
13. Política de erros (§12) validada operacionalmente.

---

## 18. Critérios de Pronto

**O módulo não está pronto apenas porque recebe arquivo.** Exige:

- Contrato validado (uso real do Contrato de Item de Ingestão/Arquivo sem
  necessidade de exceção).
- Testes unitários.
- Testes de integração.
- Teste de duplicidade (§20).
- Teste de retry (§20).
- Teste com arquivo corrompido (§20).
- Teste com MIME incorreto (§20).
- Teste com origem desconhecida (§20).
- Logs estruturados (§13) implementados e revisados.
- `correlation_id` presente em toda operação.
- Auditoria (§13) funcional.
- Documentação operacional (runbook).
- Monitoramento (métricas de §19 visíveis em dashboard).
- Rollback testado, não só documentado.
- Adaptador legado (§15) testado contra dados reais do legado.
- Shadow mode (§16, Fase 1) comparado e sem divergência inexplicada.
- **Nenhuma interrupção da operação atual** durante todo o processo.

---

## 19. Métricas Iniciais

- Itens recebidos (total e por origem).
- Itens validados.
- Itens rejeitados (com motivo).
- Duplicidades técnicas detectadas.
- Falhas temporárias.
- Falhas definitivas.
- Tempo médio de ingestão (do recebimento à disponibilização).
- Tamanho médio do Arquivo.
- Volume por origem (Gmail, Make.com, upload manual, API).
- Divergência entre shadow mode e legado (Fase 1).
- Itens sem classificação posterior dentro de um prazo esperado (sinal de
  item "perdido" entre módulos).
- Reprocessamentos (quantos, por qual motivo).

---

## 20. Testes Mínimos

1. PDF válido por Gmail.
2. PDF válido por upload manual.
3. Mesmo request repetido (retry técnico).
4. Mesmo anexo recebido duas vezes (Message ID repetido).
5. Arquivos com mesmo nome e conteúdo diferente.
6. Arquivos com nomes diferentes e mesmo hash.
7. PDF corrompido.
8. PDF protegido por senha.
9. MIME falso (extensão `.pdf`, conteúdo não-PDF).
10. Arquivo vazio.
11. Arquivo acima do limite (> 50 MB).
12. Origem sem autorização (chave inválida/ausente).
13. Airtable indisponível.
14. Armazenamento indisponível.
15. Timeout após gravação (resultado incerto).
16. Retry após resultado incerto.
17. Dois processamentos simultâneos do mesmo Item.
18. Caracteres especiais no nome do arquivo.
19. Múltiplos anexos no mesmo e-mail.

---

## 21. Riscos

| Risco | Criticidade |
|---|---|
| Perda de Arquivo (falha entre recebimento e persistência, sem retry) | **Crítica** |
| Duplicidade (mesmo conteúdo virando dois Itens/Arquivos por falha de idempotência) | **Alta** |
| Processamento duplo (mesmo Item disparando Classificação duas vezes) | **Alta** |
| Inconsistência entre storage e registro (Arquivo referenciado sem binário correspondente, ou vice-versa) | **Alta** |
| Dependência do Airtable como único armazenamento (§10) | **Média** |
| Indisponibilidade do Apps Script (atraso de até ~1h no gatilho horário) | **Baixa** — já é o comportamento aceito hoje |
| Timeout do Render em uploads grandes | **Média** |
| Arquivo grande demais para o fluxo síncrono | **Média** |
| Exposição de dados em log (violação de §13) | **Alta** |
| Incompatibilidade com o legado (adaptador de saída malformado) | **Crítica** durante a Fase 2 da estratégia strangler |
| Shadow mode incompleto (comparação não cobre todos os casos reais) | **Alta** — mascara divergência antes da Fase 2 |
| Falsa conclusão (módulo reporta sucesso sem persistência real confirmada) | **Crítica** — viola Manifesto, princípio 10 (Erros Explícitos) |

---

## 22. Decisões Necessárias Antes do Código

Somente o que ainda não foi decidido — **nenhuma decisão já aprovada é
reaberta aqui**:

- Armazenamento inicial (§10) — confirmar formalmente "manter Airtable
  attachment" como decisão, não só recomendação.
- Primeira origem a migrar (Gmail, Make.com, ou upload manual) — qual
  entra primeiro na Fase 2 da estratégia strangler.
- Limite de tamanho definitivo (manter 50 MB ou revisar).
- Tipos permitidos além de PDF (hoje só PDF é tratado com robustez —
  existe necessidade real de outros tipos na Ingestão?).
- Duração do shadow mode (Fase 1) antes de promover para Fase 2.
- Fonte oficial do Item de Ingestão durante a transição — quem escreve
  primeiro, o legado ou o módulo novo, enquanto os dois coexistirem.
- Estratégia de IDs — como `item_ingestao_id`/`arquivo_id` coexistem com
  Airtable Record ID durante a migração (referência externa vs. campo
  próprio).
- Comportamento para mesmo hash vindo de origens diferentes — permitir
  sempre, ou exigir confirmação humana em algum caso (ex.: hash igual mas
  remetentes muito diferentes)?
- Política de retenção temporária de Arquivos rejeitados/cancelados.
- Destino de itens rejeitados — ficam arquivados para auditoria, ou são
  descartados após um prazo?
- **Adaptação do scenario do Make.com** (achado de §2) — passa a chamar um
  endpoint de ingestão canônico antes de criar o registro em
  `Processar Arquivos`, ou continua criando o registro diretamente por mais
  tempo?

---

## 23. Plano de Implementação (futuro, não executado)

1. Observabilidade do fluxo atual (Fase 0, §16).
2. Contrato v1 implementável (formalização final de §5, sem mudança de
   conteúdo).
3. Estrutura interna do módulo (organização de código, dentro do monólito
   modular, `MAGNATA_OS_ARQUITETURA.md` §3).
4. Armazenamento (decisão de §22 implementada).
5. Endpoint ou adaptador de entrada (recebendo as origens de §2).
6. Idempotência (§9 implementada).
7. Criação de Item de Ingestão e Arquivo.
8. Eventos (§7 emitidos de fato).
9. Logs e métricas (§13, §19).
10. Shadow mode (Fase 1, §16).
11. Testes comparativos (shadow vs. legado).
12. Porta principal (Fase 2, §16).
13. Adaptador legado (§15 implementado).
14. Rollout progressivo, por origem.
15. Retirada controlada das portas paralelas (Fase 4, §16).

**Nada desta lista foi executado.**

---

## 24. Entregas da Implementação Futura

- Módulo ou pacote de Ingestão.
- Contratos implementados (Item de Ingestão, Arquivo, Envelope de Evento,
  Erro).
- Endpoint(s) de ingestão canônica.
- Adaptadores (entrada legado→canônico, saída canônico→legado).
- Testes (unitários, integração, comparativos de shadow mode).
- Migrações de dado, se necessárias (ex.: retroalimentar `versao`/
  `papel_arquivo` em Arquivos já existentes).
- Dashboards de métricas (§19).
- Alertas (falha definitiva, divergência de shadow mode acima de limiar).
- Runbook operacional.
- Plano de rollback documentado e testado.
- Documentação de uso do módulo para os módulos consumidores
  (Classificação).

---

## 25. Fora de Escopo do Módulo 01

Registrado expressamente — nenhum dos itens abaixo é tocado por este
módulo:

Classificação final; fatiamento; reconhecimento de colaborador;
determinação definitiva de Cliente; distribuição; envio; assinatura;
ponto; RH; financeiro; alteração imediata de Airtable; substituição
completa do legado.

---

## 26. Conclusão

- **Objetivo:** concentrar a ingestão documental de todas as origens reais
  (Gmail, Make.com, upload manual) num único ponto canônico, produzindo
  Item de Ingestão + Arquivo consistentes, sem decidir Tipo Documental,
  destinatário ou qualquer coisa além da própria ingestão.
- **Fronteira:** começa no recebimento da solicitação, termina na
  disponibilização para Classificação — nunca cruza para dentro da
  classificação, mesmo que o legado hoje misture as duas coisas na mesma
  função (§3).
- **Contratos:** reaproveita integralmente `MAGNATA_OS_CONTRATOS.md` §4
  (Item de Ingestão) e §5 (Arquivo), sem necessidade de campo novo.
- **Estados:** subconjunto de 7 estados da máquina completa de Item de
  Ingestão (`MAGNATA_OS_ESTADOS.md` §3) — `EM_PROCESSAMENTO`/`PROCESSADO`
  ficam para a Classificação.
- **Eventos:** 5 eventos, todos já existentes no catálogo aprovado —
  nenhum evento novo foi criado; a ambiguidade de `ArquivoExtraido` foi
  resolvida explicitamente (§7).
- **Erros:** 10 códigos conceituais, cada um com categoria, retry,
  estado resultante e evidência definidos (§12).
- **Estratégia de coexistência:** strangler pattern em 4 fases relevantes
  a este módulo (Observação → Shadow Mode → Porta Principal →
  Retirada), sem datas, sem interrupção do legado em nenhuma fase.
- **Decisões restantes:** 10 decisões de negócio/técnicas listadas em
  §22, nenhuma delas reabrindo decisão já aprovada (`DEC-ENT-*`).
- **Condições para autorizar implementação:** as 13 listadas em §17 —
  nenhuma foi satisfeita nesta etapa; este documento é o insumo para que
  elas comecem a ser endereçadas, não a autorização em si.

---

## Confirmação de Escopo

Nenhum arquivo existente foi alterado para produzir este documento — apenas
`MAGNATA_OS_MODULO_01_INGESTAO.md` foi criado. Nenhum código, tabela do
Airtable, configuração, memória, endpoint, classe, adaptador ou dependência
foi criado, alterado ou instalado. Nenhum deploy foi iniciado. Nenhum fluxo
existente (`/email/webhook`, `/separar`, `/processar-fila`,
`/processar-doc-cliente`, o scenario do Make.com, o Apps Script) foi
interrompido ou modificado. Este plano não deve ser considerado
implementação concluída.
