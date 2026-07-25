# Magnata OS — Contratos Canônicos de Dados

**Versão:** 1.0
**Status:** CANÔNICO INICIAL — conceitual, não implementado
**Data:** 2026-07-22
**Fontes:** `MAGNATA_OS_MANIFESTO.md`, `MAGNATA_OS_ARQUITETURA.md`,
`MAGNATA_OS_ENTIDADES.md`, `MAGNATA_OS_DECISOES_ENTIDADES.md`,
`MAGNATA_OS_EVENTOS.md`, e evidências de legado já documentadas nesses
arquivos (não relidas do zero nesta etapa).

**Natureza deste documento:** contratos **conceituais** — nomes de campo,
tipos conceituais e regras. **Não é** JSON Schema, não é classe Python, não
é schema de tabela do Airtable. Nenhum desses três será criado aqui. Toda
"implementação concluída" que alguém tentar declarar a partir deste
documento, sem passar por um trabalho de implementação real, é uma leitura
incorreta dele.

Nenhum código, tabela do Airtable, configuração, memória ou outro documento
foi alterado para produzir este catálogo.

---

## 1. Princípios dos Contratos

- **Um conceito tem um nome oficial.** Onde o legado usa dois nomes para o
  mesmo conceito (`Tipo` × `Tipo de Documento`), o contrato usa só um.
- **Nomes legados são aceitos apenas por adaptadores** — nunca vazam para
  dentro de um módulo novo como se fossem o vocabulário oficial.
- **Módulos internos usam somente contratos canônicos.** Se um módulo novo
  precisa ler o Airtable diretamente, ele o faz atrás de um adaptador que
  traduz para o contrato — o módulo em si nunca conhece `F_PROC_TIPO_DOC`.
- **Contratos são versionados** (§18) — nenhuma mudança de significado
  acontece "no mesmo v1".
- **Alteração incompatível exige nova versão.** Não se quebra um consumidor
  existente silenciosamente.
- **Campo não muda de significado silenciosamente.** Se `estado_documento`
  precisar passar a incluir um valor novo com semântica diferente da
  original, isso é uma mudança de contrato, documentada, não um `typecast`
  silencioso.
- **Campo desconhecido tem política definida:** por padrão, um consumidor
  ignora campos que não reconhece (tolerância a adição futura de campo
  opcional) — mas um **produtor** nunca omite um campo obrigatório do
  contrato da versão que declara usar.
- **Ausência, `null` e vazio são situações diferentes** (§2.4) — um contrato
  nunca trata os três como sinônimos.
- **Datas têm formato e fuso explícitos** (§2.2).
- **Valores monetários não usam ponto flutuante binário** — representados
  como inteiro em centavos, ou como string decimal de precisão fixa; nunca
  `float`/`double` (erro clássico de arredondamento).
- **Identificador interno e externo são separados** (§2.1) — um nunca
  substitui o outro silenciosamente.
- **Credencial nunca faz parte de payload comum.** Token, senha, chave de
  API não aparecem em nenhum contrato deste documento — nem mesmo em
  `metadata`.

---

## 2. Convenções Gerais

### 2.1 Identificadores

Sete conceitos diferentes, frequentemente confundidos no legado:

| Conceito | Papel | Confundido no legado com |
|---|---|---|
| **Identificador canônico interno** | identidade estável da entidade dentro do Magnata OS, independente de onde está persistida | Airtable Record ID (`MAGNATA_OS_ENTIDADES.md` §8) |
| **Airtable Record ID** | referência externa de persistência — pode mudar numa reimportação | usado hoje como se fosse identidade permanente |
| **Identificador externo** | referência a um sistema fora do Magnata OS (Gmail Message ID, ID do Secullum) | às vezes tratado como chave primária interna |
| **Hash** (ex.: SHA-256 de Arquivo) | identifica o **conteúdo** de um Arquivo, não a identidade do Documento | usado como identidade de Documento no legado (`MAGNATA_OS_ENTIDADES.md` §8) |
| **Chave de idempotência** | identifica uma **operação de criação**, evita duplicidade por retry | confundida com identificador canônico da entidade criada (DEC-ENT-029) |
| **`correlation_id`** | agrupa um fluxo de negócio inteiro | — |
| **`causation_id`** | aponta o fato/comando imediatamente anterior que causou este | às vezes confundido com `correlation_id` |
| **`request_id`** | identifica uma chamada técnica específica (HTTP, RPC) | às vezes usado como se fosse `correlation_id` |

Nenhum contrato deste documento usa Airtable Record ID, hash ou chave de
idempotência como identificador canônico de entidade — cada um aparece só
no seu papel próprio.

### 2.2 Datas e Horários

- Formato: **ISO 8601** (`AAAA-MM-DDTHH:MM:SS±HH:MM`).
- **Todo timestamp de instante tem fuso explícito** — nunca hora "solta" sem
  saber se é UTC ou horário de Brasília.
- **Data sem horário** (`AAAA-MM-DD`) é usada só quando o conceito é
  genuinamente um dia, não um instante (ex.: `periodo_inicio`/`periodo_fim`
  de Competência tipo `PERIODO`).
- **Competência mensal é separada de data** — `competencia_ano` +
  `competencia_mes` (inteiros) não são um timestamp; representam o período
  de referência de negócio (DEC-ENT-004), nunca derivados implicitamente de
  `criado_em`.

### 2.3 Valores Enumerados

- Todo valor controlado (enum conceitual) é representado, nos contratos
  técnicos futuros, em **maiúsculas sem acentuação** (ex.: `EMAIL`,
  `QUALQUER_UM`, `FALHA_DEFINITIVA`) — já é o padrão adotado em
  `MAGNATA_OS_DECISOES_ENTIDADES.md` e `MAGNATA_OS_EVENTOS.md`.
- **Rótulo amigável é separado do valor interno.** O contrato transporta o
  valor controlado (`FALHA_DEFINITIVA`); a tradução para "Falha definitiva"
  ou qualquer texto exibido ao usuário é responsabilidade de camada de
  apresentação, não do contrato de dados.

### 2.4 Ausência de Valor

Seis situações distintas, nenhuma tratada como sinônimo de outra:

| Situação | Significado |
|---|---|
| **Campo ausente** | o produtor não incluiu o campo no payload (diferente de tê-lo incluído como vazio) |
| **`null`** | o campo existe no contrato mas seu valor é explicitamente desconhecido/não coletado |
| **String vazia** (`""`) | o campo tem um valor, e esse valor é a ausência de texto — diferente de não saber o texto |
| **Lista vazia** (`[]`) | o campo é uma coleção, e a coleção de fato não tem itens — diferente de a coleção não ter sido calculada |
| **Valor desconhecido** | o produtor sabe que o dado existe mas não conseguiu obtê-lo (ex.: competência não extraída do texto — DEC-ENT-004, "não inventar competência") |
| **Não aplicável** | o campo genuinamente não se aplica a este caso (ex.: `competencia_tipo = NAO_APLICAVEL`) |

---

## 3. Estrutura Obrigatória de Cada Contrato (template)

```text
### NomeDoContrato — v1

**Finalidade:** o que transporta.
**Produtor:** módulo que produz.
**Consumidores:** módulos autorizados a consumir.
**Entidade principal:** entidade canônica relacionada.
**Evento ou comando relacionado:** referência a MAGNATA_OS_EVENTOS.md.
**Campos obrigatórios:** nome, tipo conceitual, significado.
**Campos opcionais:** nome, tipo, regra de presença.
**Regras de validação:** condições obrigatórias.
**Identificadores:** identidade canônica e referências externas.
**Idempotência:** quando aplicável.
**Erros possíveis:** falhas de validação ou processamento.
**Dados proibidos:** credenciais, dados excessivos, campos que não circulam.
**Correspondência no legado:** campos/tabelas/payloads atuais.
**Adaptação necessária:** como converter legado → canônico.
**Riscos de migração:** ambiguidades e perdas possíveis.
```

Aplicado integralmente aos 16 contratos deste documento (11 obrigatórios +
5 opcionais de assinatura, §19) — nenhum contrato recebe tratamento
condensado nesta etapa, ao contrário do catálogo de eventos, porque o
volume aqui é gerenciável (16, não 96).

---

## 4. Contrato de Item de Ingestão

### ItemIngestao — v1

**Finalidade:** transportar o registro de chegada de um item de origem,
antes de qualquer classificação.
**Produtor:** módulo de Ingestão.
**Consumidores:** módulo de Classificação.
**Entidade principal:** Item de Ingestão.
**Evento ou comando relacionado:** `ItemIngestaoRecebido`,
`ItemIngestaoRejeitado`, `IngestaoFalhou` (`MAGNATA_OS_EVENTOS.md` §A).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `item_ingestao_id` | identificador canônico interno | identidade do Item de Ingestão |
| `empresa_id` | referência (Empresa) | sempre a Magnata, hoje singular — reservado para eventual expansão |
| `origem` | enum: `EMAIL`/`UPLOAD_MANUAL`/`API`/`PORTAL`/`NAVEGADOR`/`OUTRO` | canal de entrada — não altera o significado de negócio do item (`MAGNATA_OS_EVENTOS.md` §A) |
| `recebido_em` | timestamp ISO 8601 com fuso | quando o item foi persistido |
| `hash_sha256` | string (hash) | hash do conteúdo recebido — chave de idempotência de fato |
| `correlation_id` | identificador de correlação | agrupa o fluxo de negócio originado por este item |
| `status_ingestao` | enum provisório: `RECEBIDO`/`REJEITADO`/`ERRO` | vocabulário provisório — Item de Ingestão não tem máquina de estados formalmente aprovada ainda (`MAGNATA_OS_ENTIDADES.md` §5) |

**Campos opcionais:**

| Campo | Tipo conceitual | Regra de presença |
|---|---|---|
| `origem_externa_id` | identificador externo | presente quando o canal fornece um (Gmail Message ID); ausente em upload manual sem equivalente |
| `nome_original` | string | nome do item/anexo como recebido |
| `mime_type` | string | tipo MIME, quando aplicável (item pode ser só metadado sem anexo) |
| `tamanho_bytes` | inteiro | tamanho do conteúdo, quando aplicável |
| `remetente` | string | só quando o canal for `EMAIL` |
| `assunto` | string | só quando o canal for `EMAIL` |
| `metadata_origem` | mapa chave-valor | dados técnicos auxiliares do canal, não de negócio |

**Nota sobre `arquivo_original`:** o comando original propôs este campo,
mas ele **não** carrega o binário embutido neste contrato — isso duplicaria
o Contrato de Arquivo (§5). `ItemIngestao` referencia os Arquivos que dele
se originaram por `arquivo_id` (relação 1:N, resolvida no lado do Contrato
de Arquivo via `item_ingestao_id`), nunca embute o payload físico.

**Regras de validação:**
- `hash_sha256` obrigatório mesmo quando o item é só um e-mail sem anexo
  (hash do conteúdo textual relevante, para permitir deduplicação).
- `origem = EMAIL` exige `origem_externa_id` (Message ID) — sem ele, a
  deduplicação de reentrega de e-mail não é possível.
- `status_ingestao = REJEITADO` exige motivo em `metadata_origem` (campo
  técnico) — este contrato não formaliza um campo de negócio próprio para
  motivo de rejeição nesta versão.

**Identificadores:** `item_ingestao_id` (canônico) + `origem_externa_id`
(externo, quando existir) + `hash_sha256` (chave de idempotência de fato).

**Idempotência:** reentrega do mesmo item (mesmo `origem_externa_id` ou
mesmo `hash_sha256` quando não houver ID externo) não cria um segundo
`ItemIngestao` — é reconhecida como o mesmo fato.

**Erros possíveis:** `origem` desconhecida/não mapeada; ausência de
`hash_sha256`; falha ao persistir (ver Contrato de Erro, §15).

**Dados proibidos:** conteúdo completo do e-mail além do necessário para
classificação (evitar carregar corpo de e-mail extenso como obrigatório);
credenciais de acesso ao canal de origem.

**Correspondência no legado:** criação de registro em `Emails Savian`
(Message ID, Assunto, Conteúdo — `app.py:112`, `apps_script_email_intake.gs`).

**Adaptação necessária:** o adaptador de entrada precisa mapear `Emails
Savian.MESSAGE ID` → `origem_externa_id`, `Assunto` → `assunto`,
calcular/reaproveitar `hash_sha256` (hoje vive em `Arquivos.Hash do Anexo`,
não em `Emails Savian` — o adaptador precisa decidir se o hash do Item de
Ingestão é o do e-mail ou herdado do primeiro Arquivo, já que o legado não
distingue os dois).

**Riscos de migração:** as funções de backfill histórico do Apps Script
(`fatiarFGTS_Maio`, etc.) não produzem um `ItemIngestao` real — qualquer
emissão retroativa deste contrato para dados históricos precisa reconhecer
essa lacuna (já registrada em `MAGNATA_OS_EVENTOS.md` §A).

---

## 5. Contrato de Arquivo

### Arquivo — v1

**Finalidade:** transportar a manifestação física/digital de um Documento,
com versão e vigência.
**Produtor:** módulo de Ingestão (Arquivo original) ou módulo de Assinatura
(Arquivo Assinado — ver nota abaixo).
**Consumidores:** Classificação, Distribuição, Assinatura.
**Entidade principal:** Arquivo.
**Evento ou comando relacionado:** `ArquivoExtraido`, `ArquivoVersaoCriada`,
`ArquivoMarcadoComoVigente`, `ArquivoAssinadoGerado`
(`MAGNATA_OS_EVENTOS.md` §A, §B, §J).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `arquivo_id` | identificador canônico interno | identidade do Arquivo |
| `item_ingestao_id` | referência (Item de Ingestão) | origem do Arquivo |
| `nome` | string | nome do arquivo |
| `mime_type` | string | tipo MIME |
| `tamanho_bytes` | inteiro | tamanho do conteúdo |
| `hash_sha256` | string (hash) | identifica o conteúdo — **não é identidade do Documento** (`MAGNATA_OS_ENTIDADES.md` §8) |
| `versao` | inteiro ou identificador de versão | ordem/versão dentro do histórico do Documento (DEC-ENT-017) |
| `papel_arquivo` | enum: `ORIGINAL`/`EXTRAIDO`/`PROCESSADO`/`DERIVADO`/`CORRIGIDO`/`ASSINADO` | papel do Arquivo no ciclo de vida do Documento |
| `criado_em` | timestamp ISO 8601 com fuso | quando esta versão do Arquivo foi criada |
| `vigente` | booleano | se esta é a versão vigente do Documento (DEC-ENT-017) |

**Campos opcionais:**

| Campo | Tipo conceitual | Regra de presença |
|---|---|---|
| `documento_id` | referência (Documento) | ausente enquanto o Arquivo não foi classificado — permanece só em `item_ingestao_id` até então (DEC-ENT-015) |
| `arquivo_origem_id` | referência (Arquivo) | presente quando `papel_arquivo` é `DERIVADO`/`CORRIGIDO`/`ASSINADO` |
| `criado_por` | referência (ator/sistema) | quando o mecanismo gerador for identificável |
| `localizacao_referencia` | string (referência de armazenamento) | ponteiro para onde o binário está persistido — nunca o binário embutido no contrato |
| `identificadores_externos` | mapa chave-valor | ex.: Airtable Record ID, como referência externa (§2.1) |

**Nota sobre Arquivo Assinado:** `papel_arquivo = ASSINADO` **não** é um
tipo diferente de entidade — é um Arquivo como qualquer outro, só com esse
papel e `arquivo_origem_id` preenchido (DEC-ENT-026). Nenhum campo deste
contrato existe exclusivamente para "Arquivo Assinado" fora dessa
convenção.

**Regras de validação:**
- Um Arquivo com `papel_arquivo` em (`DERIVADO`, `CORRIGIDO`, `ASSINADO`)
  exige `arquivo_origem_id` preenchido.
- Um Arquivo novo marcado `vigente = true` para um Documento implica que o
  Arquivo anteriormente vigente do mesmo Documento passa a `vigente =
  false` **no mesmo instante lógico** — nunca os dois vigentes ao mesmo
  tempo para o mesmo Documento.
- `hash_sha256` nunca é usado, por si, como `documento_id`.

**Identificadores:** `arquivo_id` (canônico); `hash_sha256` (identidade de
conteúdo, usada para idempotência); `identificadores_externos` (Airtable
Record ID como referência, nunca como identidade).

**Idempotência:** reenvio do mesmo conteúdo (mesmo `hash_sha256`) para o
mesmo `item_ingestao_id` não cria um segundo Arquivo representando o mesmo
fato.

**Erros possíveis:** hash não calculável; `papel_arquivo` inconsistente com
presença/ausência de `arquivo_origem_id`; violação da regra de vigência
única.

**Dados proibidos:** o binário do arquivo não é o foco deste contrato de
metadados — quando precisar transportar o conteúdo, isso é feito por
`localizacao_referencia`, nunca embutindo dados sensíveis (ex.: dados
bancários de holerite) em `metadata`.

**Correspondência no legado:** tabela `Arquivos` (`tblRsvhz8oOcUqhkv`,
`Hash do Anexo` = `F_ARQ_HASH`); campo `Arquivos 2`
(`F_PROC_ARQUIVOS2`) como link de `Processar Arquivos` para `Arquivos`.

**Adaptação necessária:** o legado não tem `versao`, `papel_arquivo` nem
`vigente` — o adaptador precisa inferir `papel_arquivo = ORIGINAL` e
`vigente = true` para todo Arquivo existente hoje, como estado inicial de
migração (todo Arquivo legado é, por definição, o único e vigente até que
o novo modelo comece a operar).

**Riscos de migração:** o nome de campo "Arquivos 2" sugere um segundo
conjunto de anexos — já documentado como problema de nomenclatura, não de
dado (`MAGNATA_OS_ENTIDADES.md` §3); o adaptador precisa tratar isso como
uma única relação Documento↔Arquivo, não duas.

---

## 6. Contrato de Documento

### Documento — v1

**Finalidade:** transportar a unidade lógica de negócio classificada,
independente de quantos Arquivos a compõem.
**Produtor:** módulo de Classificação.
**Consumidores:** Distribuição, Assinatura, Auditoria.
**Entidade principal:** Documento.
**Evento ou comando relacionado:** `DocumentoCriado`,
`DocumentoDerivadoCriado`, `DocumentoProcessamentoConcluido`,
`DocumentoProcessamentoFalhou` (`MAGNATA_OS_EVENTOS.md` §B).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `documento_id` | identificador canônico interno | identidade do Documento |
| `empresa_id` | referência (Empresa) | sempre a Magnata |
| `tipo_documental` | enum (Tipo Documental — estrutura de valor, `MAGNATA_OS_ENTIDADES.md` §5) | categoria de negócio |
| `titularidade_tipo` | enum: `COLABORADOR`/`VINCULO`/`CLIENTE`/`NAO_APLICAVEL` | a quem o Documento pertence prioritariamente |
| `titularidade_id` | referência (conforme `titularidade_tipo`) | ex.: holerite → `titularidade_tipo = VINCULO` (DEC-ENT-005) |
| `competencia_tipo` | enum: `MENSAL`/`PERIODO`/`NAO_APLICAVEL` | estrutura de referência temporal (DEC-ENT-004) |
| `estado_documento` | enum: `PENDENTE`/`PROCESSANDO`/`CONCLUIDO`/`REVISAO_MANUAL`/`ERRO` | **nunca inclui `ASSINADO`** — reforço direto de DEC-ENT-022 |
| `criado_em` | timestamp ISO 8601 com fuso | criação do registro — **diferente** de `competencia_ano`/`competencia_mes` |
| `origem` | referência (Item de Ingestão) | Item de Ingestão que originou o Documento |
| `arquivo_vigente_id` | referência (Arquivo) | qual Arquivo é a versão vigente hoje |

**Campos opcionais:**

| Campo | Tipo conceitual | Regra de presença |
|---|---|---|
| `titulo` | string | quando aplicável para exibição |
| `descricao` | string | quando aplicável |
| `cliente_ids` | lista de referências (Cliente) | pode ter mais de um, quando Documento é comum a vários Clientes (DEC-ENT-006) — lista vazia é diferente de "não aplicável" (§2.4) |
| `colaborador_id` | referência (Colaborador) | ausente quando o Documento é coletivo |
| `vinculo_id` | referência (Vínculo Trabalhista) | titularidade preferencial para Holerite (DEC-ENT-005); pode coexistir com `colaborador_id` como referência operacional transitória enquanto Vínculo não estiver separado tecnicamente (DEC-ENT-002) |
| `posto_id` | referência (Posto de Trabalho) | quando relevante para rateio/distribuição |
| `competencia_ano` | inteiro | obrigatório **quando** `competencia_tipo = MENSAL` |
| `competencia_mes` | inteiro (1-12) | idem |
| `periodo_inicio` | data (sem horário) | obrigatório **quando** `competencia_tipo = PERIODO` |
| `periodo_fim` | data (sem horário) | idem |
| `identificadores_legados` | mapa chave-valor | Airtable Record ID de `Processar Arquivos`, como referência externa |

**Regras de validação:**
- `competencia_tipo = MENSAL` exige `competencia_ano` e `competencia_mes`;
  `competencia_tipo = PERIODO` exige `periodo_inicio`; `NAO_APLICAVEL` não
  aceita nenhum dos quatro campos de competência preenchidos (DEC-ENT-004 —
  "não inventar competência").
- `estado_documento` nunca aceita o valor `ASSINADO` ou qualquer sinônimo —
  validação **rejeita** esse valor explicitamente, não apenas o omite do
  vocabulário.
- `cliente_ids` com mais de um item exige que o Documento seja de um tipo
  documental compatível com "documento comum" (regra de negócio a refinar
  fora deste contrato).
- Documento não é o Arquivo — este contrato nunca embute o binário
  (reforço de `MAGNATA_OS_ENTIDADES.md` §9).

**Identificadores:** `documento_id` (canônico); `identificadores_legados`
(Airtable Record ID, referência externa apenas).

**Idempotência:** reclassificação do mesmo Arquivo (mesmo `hash_sha256`)
não cria um segundo Documento — a chave de idempotência da operação de
classificação é distinta do `documento_id` resultante.

**Erros possíveis:** competência inconsistente com o tipo declarado;
titularidade ambígua (nem Colaborador/Vínculo nem Cliente identificados,
sem cair explicitamente em `NAO_APLICAVEL`); tentativa de gravar
`estado_documento = ASSINADO`.

**Dados proibidos:** dados financeiros sensíveis do conteúdo do Documento
não pertencem a este contrato de metadados — ficam no Arquivo referenciado,
sob controle de acesso próprio.

**Correspondência no legado:** tabela `Processar Arquivos`
(`tblXaLXvGJMyFOayc`) — hoje mistura ingestão e classificação num só
registro, e `Status` recebe `'Assinado'` (achado crítico #1, `app.py:9896`).

**Adaptação necessária:** o adaptador precisa (1) separar, de um único
registro `Processar Arquivos`, o que vira `ItemIngestao` do que vira
`Documento`; (2) mapear qualquer `Status = 'Assinado'` encontrado no legado
para `estado_documento = CONCLUIDO` **mais** um evento
`AssinaturaRealizada`/estado próprio de Solicitação de Assinatura — nunca
para `estado_documento = ASSINADO` (que este contrato proíbe).

**Riscos de migração:** dado histórico com `Status = 'Assinado'` é o caso
mais delicado da migração — perder a informação de que o documento foi
assinado (só porque o valor não é mais um `estado_documento` válido) seria
uma regressão; o adaptador precisa **preservar** esse fato como evidência
de Assinatura, não descartá-lo.

---

## 7. Contrato de Classificação

### ClassificacaoEntrada — v1

**Finalidade:** transportar a solicitação de classificação de um Arquivo.
**Produtor:** módulo de Ingestão.
**Consumidores:** módulo de Classificação.
**Entidade principal:** Documento (resultado), Arquivo (insumo).
**Evento ou comando relacionado:** comando `ClassificarArquivo`
(não é evento — `MAGNATA_OS_EVENTOS.md` §B, nota sobre
`ArquivoClassificacaoSolicitada` rejeitado).

**Campos obrigatórios:** `item_ingestao_id`, `arquivo_id`, `correlation_id`.

**Campos opcionais:** `contexto_disponivel` (mapa chave-valor — sinais já
conhecidos no momento da chamada, ex.: remetente do e-mail, se relevante
para a heurística de classificação).

**Regras de validação:** `arquivo_id` deve existir e pertencer ao
`item_ingestao_id` informado.

**Identificadores:** não introduz identidade própria — é uma solicitação,
não uma entidade persistente.

**Idempotência:** não aplicável como conceito de entidade — mas a
**operação** de classificar o mesmo `arquivo_id` duas vezes deve produzir o
mesmo `ClassificacaoResultado` (ou reconhecer que já foi classificado),
não dois Documentos.

**Erros possíveis:** `arquivo_id` inexistente; Arquivo sem conteúdo
extraível.

**Dados proibidos:** nenhum específico além dos gerais (§1).

**Correspondência no legado:** chamada interna às funções de classificação
em `app.py` (não é uma rota HTTP separada hoje).

**Adaptação necessária:** nenhuma migração de dado — é uma solicitação
interna, não um registro persistido no legado.

**Riscos de migração:** baixo.

### ClassificacaoResultado — v1

**Finalidade:** transportar o resultado de uma tentativa de classificação.
**Produtor:** módulo de Classificação.
**Consumidores:** módulo que criou/atualiza o Documento; Distribuição
(indiretamente, após o Documento existir); Auditoria.
**Entidade principal:** Documento.
**Evento ou comando relacionado:** `ArquivoClassificado`,
`ArquivoClassificacaoInconclusiva` (`MAGNATA_OS_EVENTOS.md` §B).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `resultado_classificacao` | enum: `CLASSIFICADO`/`INCONCLUSIVO`/`REJEITADO`/`ERRO` | resultado da tentativa |
| `tipo_documental` | enum (Tipo Documental) | presente mesmo quando `INCONCLUSIVO` (melhor palpite), ausente só quando `ERRO` |
| `confianca` | enum: `ALTO`/`MEDIO`/`BAIXO` | nível de confiança do resultado |
| `necessita_revisao` | booleano | deriva de `confianca`/`resultado_classificacao`, mas é explícito, não implícito |
| `classificador` | string (identificador do mecanismo) | qual lógica/versão de classificador produziu o resultado |
| `versao_classificador` | string | versão do classificador — **diferente** de `event_version` do evento associado |

**Campos opcionais:** `dados_extraidos` (mapa chave-valor — CPF/CNPJ/nome
encontrados no texto), `titularidade_sugerida`, `competencia_sugerida`,
`motivos` (lista de strings — por que `INCONCLUSIVO`/`REJEITADO`, quando
aplicável).

**Regras de validação:** `resultado_classificacao = INCONCLUSIVO` ou
`REJEITADO` exige `motivos` não vazio; `resultado_classificacao =
CLASSIFICADO` com `confianca = BAIXO` implica `necessita_revisao = true`.

**Identificadores:** referencia `arquivo_id`/`documento_id` (não introduz
identidade própria além disso).

**Idempotência:** ver Contrato de `ClassificacaoEntrada` acima.

**Erros possíveis:** `resultado_classificacao = ERRO` sem `motivos`
associado a um Contrato de Erro (§15).

**Dados proibidos:** nenhum específico.

**Correspondência no legado:** gravação de `F_PROC_TIPO_DOC`, `Status` e
campos de cliente/funcionário em `Processar Arquivos`, ao fim das funções
de classificação (`app.py`).

**Adaptação necessária:** hoje o legado não separa "classificação
concluiu" de "documento criado" — são a mesma gravação; o adaptador precisa
decidir a ordem de emissão (`DocumentoCriado` antes ou simultâneo a
`ArquivoClassificado`).

**Riscos de migração:** o campo `F_PROC_TIPO_DOC` hoje também recebe
códigos de erro técnico (`UPLOAD_FAILED`, débito conhecido #3) — o
adaptador **não** deve mapear esses valores para `tipo_documental`; eles
pertencem ao Contrato de Erro (§15), nunca a este.

---

## 8. Contrato de Distribuição

### Distribuicao — v1

**Finalidade:** transportar a decisão/obrigação de entregar Documentos e
Arquivos a destinatários.
**Produtor:** módulo de Distribuição.
**Consumidores:** módulo de Envio.
**Entidade principal:** Distribuição.
**Evento ou comando relacionado:** `DistribuicaoCriada`,
`DistribuicaoConcluida`, `DistribuicaoFalhou`, `DistribuicaoCancelada`
(`MAGNATA_OS_EVENTOS.md` §D).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `distribuicao_id` | identificador canônico interno | identidade da Distribuição |
| `empresa_id` | referência (Empresa) | sempre a Magnata |
| `finalidade` | enum (a definir em contrato futuro — ex.: `INFORMACAO`/`PRESTACAO_CONTAS`/`EXIGE_CONFIRMACAO`/`EXIGE_ASSINATURA`) | determina condições de conclusão e se ativa o núcleo de assinatura (DEC-ENT-022) |
| `documento_ids` | lista de referências (Documento) | Documento(s) a distribuir — lista com 1+ item |
| `destinatarios` | lista de referências (Destinatário, §9) | quem deve receber |
| `canais_permitidos` | lista de enum (Canal — estrutura de valor) | canais aceitáveis para esta Distribuição |
| `politica_conclusao` | estrutura (referencia os níveis de evidência de `MAGNATA_OS_DECISOES_ENTIDADES.md` DEC-ENT-009) | qual nível de evidência conclui esta Distribuição |
| `criada_em` | timestamp ISO 8601 com fuso | criação |
| `solicitada_por` | referência (ator/sistema) | quem/o que solicitou |
| `correlation_id` | identificador de correlação | agrupa todos os Envios gerados |
| `estado_distribuicao` | enum (vocabulário próprio, ainda não formalizado em `MAGNATA_OS_ENTIDADES.md` §5 — provisório: `CRIADA`/`EM_ANDAMENTO`/`CONCLUIDA`/`FALHOU`/`CANCELADA`) | estado atual |

**Campos opcionais:** `arquivo_ids` (quando a Distribuição referencia
Arquivos específicos além dos vigentes dos Documentos), `competencia_referencia`
(quando a Distribuição é organizada por competência, ex.: "todos os
holerites de Junho/2026").

**Regras de validação:**
- `documento_ids` não pode ser vazio.
- `destinatarios` não pode ser vazio.
- Conclusão da Distribuição só ocorre quando `politica_conclusao` é
  satisfeita por **todos** os Envios relevantes — nunca por 1 Envio isolado
  (DEC-ENT-013).
- Documento comum a vários Clientes (`cliente_ids` com múltiplos itens no
  Contrato de Documento) **não exige** `documento_ids` duplicado por
  Cliente — a mesma referência de Documento é usada para todos os
  destinatários relevantes (DEC-ENT-006).

**Identificadores:** `distribuicao_id` (canônico).

**Idempotência:** criar a mesma Distribuição (mesmo Documento, finalidade e
conjunto de destinatários) por retry técnico não gera Distribuições
duplicadas.

**Erros possíveis:** `documento_ids` ou `destinatarios` vazios;
`politica_conclusao` referenciando nível de evidência que o `canal`
escolhido não suporta (DEC-ENT-009 — "canais que não fornecem determinado
nível de evidência não devem inventá-lo").

**Dados proibidos:** nenhum específico além dos gerais.

**Correspondência no legado:** hoje inexistente como registro separado —
embutido na criação de `Envios de Documentos` pelas rotas
`gerar-fila-envios*`.

**Adaptação necessária:** os 4 fluxos de fila+disparo por canal precisam
convergir para produzir uma Distribuição antes de gerar Envios — hoje cada
um cria o Envio diretamente, sem essa camada intermediária.

**Riscos de migração:** alto — é a mudança estrutural mais profunda do
núcleo de Distribuição/Envio; qualquer relatório legado que conta "envios"
pode estar, na prática, contando o que deveria ser uma única Distribuição
multiplicada por destinatário/canal.

---

## 9. Contrato de Destinatário

### Destinatario — v1

**Finalidade:** transportar a identidade de quem é autorizado a receber uma
comunicação — separada do endereço usado em cada Envio.
**Produtor:** módulo de Cadastro (referenciando Colaborador/Cliente) ou
Distribuição (quando o destinatário é criado ad-hoc).
**Consumidores:** Distribuição, Envio.
**Entidade principal:** Destinatário.
**Evento ou comando relacionado:** não tem evento de criação próprio
formalizado em `MAGNATA_OS_EVENTOS.md` — é referenciado, não emite
(`MAGNATA_OS_EVENTOS.md` §13).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `destinatario_id` | identificador canônico interno | identidade do Destinatário |
| `tipo_destinatario` | enum: `COLABORADOR`/`RESPONSAVEL_CLIENTE`/`SINDICO`/`ADMINISTRADORA`/`CONTADOR`/`SIGNATARIO`/`OUTRO_CONTATO` | papel do destinatário (DEC-ENT-018) |
| `entidade_relacionada_tipo` | enum (tipo de entidade canônica) | a que entidade este Destinatário se relaciona, quando aplicável |
| `entidade_relacionada_id` | referência (conforme `entidade_relacionada_tipo`) | ex.: Colaborador específico |
| `nome_exibicao` | string | nome para fins de exibição/log — **não é identidade** |
| `ativo` | booleano | se o Destinatário está atualmente ativo para receber comunicações |

**Campos opcionais:**

| Campo | Tipo conceitual | Regra de presença |
|---|---|---|
| `enderecos_disponiveis` | lista de estruturas (canal + endereço) | endereços cadastrados atualmente — **não confundir** com `endereco_utilizado` do Contrato de Envio (§10), que é o endereço efetivamente usado num Envio específico e não muda retroativamente |
| `autorizacoes` | lista de enum | escopos do que este Destinatário está autorizado a receber |
| `identificadores_externos` | mapa chave-valor | Airtable Record ID, quando aplicável |

**Regras de validação:** telefone e e-mail **nunca** aparecem como
`destinatario_id` — só dentro de `enderecos_disponiveis`, como dado
descritivo (DEC-ENT-018).

**Identificadores:** `destinatario_id` (canônico) — imutável mesmo que o
cadastro de endereço mude.

**Idempotência:** não aplicável como operação recorrente — Destinatário é
majoritariamente um cadastro de referência, não um fluxo transacional.

**Erros possíveis:** `entidade_relacionada_id` inexistente;
`tipo_destinatario` incompatível com a entidade relacionada informada.

**Dados proibidos:** nenhum específico além dos gerais.

**Correspondência no legado:** campo `Destinatário` como **texto livre**
(WhatsApp ou e-mail) em `Envios de Documentos` — não existe cadastro de
Destinatário separado hoje.

**Adaptação necessária:** o adaptador precisa inferir `Destinatario` a
partir do texto livre legado, tipicamente casando com Colaborador (por
telefone/e-mail cadastrado) — quando não houver casamento possível, cria-se
um Destinatário `tipo_destinatario = OUTRO_CONTATO` com o endereço bruto
preservado só em `enderecos_disponiveis`.

**Riscos de migração:** alto — não há garantia de que todo texto livre
legado tenha um Destinatário canônico correspondente hoje; o histórico de
para quem um documento foi enviado no passado pode ficar com
`entidade_relacionada_id` ausente, preservando só o endereço bruto.

---

## 10. Contrato de Envio

### Envio — v1

**Finalidade:** transportar cada entrega concreta, tentada ou realizada,
por um canal, a um destinatário.
**Produtor:** módulo de Distribuição/Envio.
**Consumidores:** módulo de Envio (execução), Auditoria, Distribuição
(avaliação de conclusão).
**Entidade principal:** Envio.
**Evento ou comando relacionado:** `EnvioCriado` até
`EnvioConfirmadoPeloDestinatario`, `EnvioCancelado`, `ReenvioCriado`
(`MAGNATA_OS_EVENTOS.md` §E).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `envio_id` | identificador canônico interno | identidade do Envio |
| `distribuicao_id` | referência (Distribuição) | Distribuição de origem |
| `destinatario_id` | referência (Destinatário) | quem recebe |
| `canal` | enum (Canal — estrutura de valor) | meio de negócio |
| `endereco_utilizado` | string | endereço efetivamente usado **neste** Envio — imutável mesmo que o cadastro do Destinatário mude depois (DEC-ENT-018) |
| `documento_ids` | lista de referências (Documento) | Documento(s) sendo entregues |
| `estado_envio` | enum: `PLANEJADO`/`EM_FILA`/`EM_PROCESSAMENTO`/`ACEITO_PELO_PROVEDOR`/`ENVIADO`/`ENTREGUE`/`LIDO`/`CONFIRMADO`/`FALHA_TEMPORARIA`/`FALHA_DEFINITIVA`/`CANCELADO` (DEC-ENT-020) | estado atual — vocabulário conceitual, não nomes finais de campo |
| `criado_em` | timestamp ISO 8601 com fuso | criação |
| `correlation_id` | identificador de correlação | herdado da Distribuição de origem |

**Campos opcionais:**

| Campo | Tipo conceitual | Regra de presença |
|---|---|---|
| `arquivo_ids` | lista de referências (Arquivo) | quando o Envio referencia Arquivos específicos além dos vigentes |
| `provedor_tecnico` | string | Evolution API, SMTP, etc. — **separado** de `canal` (DEC-ENT-019) |
| `condicao_conclusao` | referência à política da Distribuição | herdada, presente para consulta local sem nova busca à Distribuição |
| `envio_anterior_id` | referência (Envio) | presente **somente** quando este Envio é um Reenvio deliberado (DEC-ENT-007) — nunca presente para mera Tentativa |
| `motivo_reenvio` | string | obrigatório **quando** `envio_anterior_id` está presente |
| `identificador_externo` | identificador externo | ID retornado pelo provedor, quando existir |
| `colocado_fila_em` | timestamp ISO 8601 com fuso | quando aplicável |
| `processado_em` | timestamp ISO 8601 com fuso | quando o processamento técnico concluiu |

**Regras de validação:**
- `envio_anterior_id` presente exige `motivo_reenvio` presente — nunca um
  sem o outro.
- `estado_envio` nunca avança para um valor cuja evidência correspondente
  não existe (ex.: não pode ir para `ENTREGUE` sem um sinal de entrega real
  — DEC-ENT-009, DEC-ENT-020).
- HTTP 200/201 de transporte **não** é, por si só, evidência suficiente
  para `estado_envio = ACEITO_PELO_PROVEDOR` — a validação exige checar o
  conteúdo semântico da resposta do provedor.
- Retry técnico da mesma tentativa **nunca** cria um novo `Envio` — isso é
  Tentativa de Envio (§11); só Reenvio deliberado cria novo `envio_id`.

**Identificadores:** `envio_id` (canônico); `identificador_externo`
(referência ao provedor, nunca substitui `envio_id`).

**Idempotência:** criação do mesmo Envio (mesma Distribuição + mesmo
Destinatário + mesmo Canal) por retry técnico não duplica o registro.

**Erros possíveis:** ver Contrato de Erro (§15) e Contrato de Tentativa de
Envio (§11) para a granularidade de falha técnica.

**Dados proibidos:** conteúdo do Documento não pertence a este contrato —
só a referência (`documento_ids`/`arquivo_ids`).

**Correspondência no legado:** tabela `Envios de Documentos`
(`tblAu4wgdfTgLOoa4`) — `Status` hoje mistura `Preparando`/`Enviado`/
`Concluído`/`Lido`, mais `Erro` usado no código sem estar no vocabulário
documentado (`app.py:123, 10330`).

**Adaptação necessária:** mapear o vocabulário de `Status` legado para
`estado_envio` conceitual — `Lido` deixa de ser um valor do mesmo campo e
vira evidência em camada própria (Contrato de Evidência de Entrega, §12).

**Riscos de migração:** os 4 fluxos de fila+disparo por canal (WhatsApp,
e-mail, combinado, ponto) gravam esse registro de formas ligeiramente
diferentes — convergir para este contrato único exige uniformizar os 4
antes de qualquer consumidor novo depender dele.

---

## 11. Contrato de Tentativa de Envio

### TentativaEnvio — v1

**Finalidade:** transportar cada execução técnica dentro de um Envio.
**Produtor:** módulo de Envio (execução/integração com provedor).
**Consumidores:** mecanismo de retry (Celery), Auditoria.
**Entidade principal:** Tentativa de Envio.
**Evento ou comando relacionado:** `TentativaEnvioFalhou`
(`MAGNATA_OS_EVENTOS.md` §F).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `tentativa_envio_id` | identificador canônico interno | identidade da Tentativa |
| `envio_id` | referência (Envio) | Envio ao qual pertence |
| `numero_tentativa` | inteiro | ordem da tentativa dentro do Envio |
| `iniciada_em` | timestamp ISO 8601 com fuso | início da execução técnica |
| `resultado` | enum: `SUCESSO`/`FALHA_TEMPORARIA`/`FALHA_DEFINITIVA` | resultado da tentativa |
| `retry_permitido` | booleano | se uma nova tentativa automática pode ocorrer |

**Campos opcionais:**

| Campo | Tipo conceitual | Regra de presença |
|---|---|---|
| `finalizada_em` | timestamp ISO 8601 com fuso | ausente enquanto em execução |
| `provedor` | string | provedor técnico usado nesta tentativa |
| `request_id` | identificador de requisição técnica | quando a chamada tem um ID técnico próprio |
| `codigo_resposta` | string | código retornado pelo provedor |
| `identificador_externo` | identificador externo | quando o provedor retorna um ID de mensagem |
| `erro_categoria` | enum | quando `resultado` ≠ `SUCESSO` — ver Contrato de Erro (§15) |
| `erro_codigo` | string | idem |
| `erro_mensagem_segura` | string | mensagem segura, nunca stack trace bruto (§15) |
| `metadata_tecnica_protegida` | mapa chave-valor, acesso restrito | payload/resposta bruta do provedor — **nunca** exposta a consumidores comuns |

**Regras de validação:** `resultado ≠ SUCESSO` exige `erro_categoria` e
`erro_codigo` presentes; `metadata_tecnica_protegida` nunca aparece fora de
um contexto de acesso restrito (auditoria técnica), mesmo quando o restante
do contrato circula livremente entre módulos.

**Identificadores:** `tentativa_envio_id` (canônico) — cada execução
técnica tem seu próprio, mesmo quando o resultado se repete.

**Idempotência:** não há duplicidade a evitar entre Tentativas — cada
execução técnica é, por definição, um fato novo (`MAGNATA_OS_EVENTOS.md`
§F). A idempotência relevante aqui é a de **não confundir** uma nova
Tentativa com um Reenvio (essa distinção vive no Contrato de Envio, §10).

**Erros possíveis:** ver campos `erro_*` acima e Contrato de Erro (§15).

**Dados proibidos:** tokens de autenticação do provedor; payload de
requisição/resposta sem proteção (deve ficar em
`metadata_tecnica_protegida`, com acesso restrito, nunca em campo comum).

**Correspondência no legado:** contador `Tentativa` (campo numérico) em
`Envios de Documentos` — sem registro individual por tentativa hoje.

**Adaptação necessária:** criar o registro individual que hoje não existe;
o valor atual do contador vira, na migração, `numero_tentativa` da última
tentativa conhecida, sem histórico anterior recuperável.

**Riscos de migração:** perda de granularidade histórica — tentativas
passadas do legado não têm registro individual para reconstruir
retroativamente; a migração só garante granularidade completa a partir do
ponto em que o novo contrato entrar em vigor.

---

## 12. Contrato de Evidência de Entrega

**Nota de forma técnica em aberto** (DEC-ENT-009, DEC-ENT-021): este
contrato é escrito para funcionar **tanto** como entidade própria **quanto**
como registro imutável associado ao Envio — a decisão técnica final não é
antecipada aqui.

### EvidenciaEntrega — v1

**Finalidade:** transportar um sinal de evidência recebido sobre um Envio.
**Produtor:** módulo de Envio (integração — recepção de webhook/callback).
**Consumidores:** Distribuição (avaliação de conclusão), Auditoria.
**Entidade principal:** Evidência de Entrega (candidata) / Envio.
**Evento ou comando relacionado:** `EvidenciaEntregaRegistrada`
(candidato, `MAGNATA_OS_EVENTOS.md` §G).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `evidencia_id` | identificador canônico interno | identidade da ocorrência de evidência |
| `envio_id` | referência (Envio) | Envio ao qual se refere |
| `tipo_evidencia` | enum: `ACEITE_PROVEDOR`/`DESPACHO_PROVEDOR`/`ENTREGA`/`LEITURA`/`CONFIRMACAO_DESTINATARIO`/`ACESSO_AUTENTICADO` | nível de evidência (DEC-ENT-009) |
| `ocorrida_em` | timestamp ISO 8601 com fuso | quando o fato ocorreu, segundo o provedor |
| `registrada_em` | timestamp ISO 8601 com fuso | quando o Magnata OS registrou — pode ser posterior a `ocorrida_em` (§10 de `MAGNATA_OS_EVENTOS.md`, confirmação atrasada) |
| `confiabilidade` | enum: `ALTA`/`MEDIA`/`BAIXA` | quão confiável é o sinal (ex.: confirmação ativa do destinatário é mais confiável que aceite de provedor) |
| `correlation_id` | identificador de correlação | herdado do Envio |

**Campos opcionais:** `provedor` (string), `identificador_externo`
(referência ao evento do provedor), `dados_comprovantes` (mapa chave-valor
— metadado bruto do sinal recebido).

**Regras de validação:**
- `tipo_evidencia` só pode ser registrado se o `canal`/`provedor` do Envio
  realmente suportar aquele nível — nunca inventado (DEC-ENT-009).
- Uma nova Evidência **não** apaga uma anterior — mesmo quando o sinal mais
  recente parece contradizer o anterior (ex.: uma confirmação de entrega
  atrasada chegando depois de uma falha definitiva já registrada) — ambas
  permanecem (`MAGNATA_OS_EVENTOS.md` §10).

**Identificadores:** `evidencia_id` (canônico).

**Idempotência:** reentrega do mesmo webhook de confirmação não deve gerar
duas Evidências representando o mesmo fato — chave: `envio_id` +
`tipo_evidencia` + `identificador_externo`, quando existir.

**Erros possíveis:** sinal de evidência para um `envio_id` inexistente;
`tipo_evidencia` incompatível com o canal do Envio.

**Dados proibidos:** payload bruto do webhook sem proteção — deve ficar
em `dados_comprovantes` com o mesmo tratamento de acesso restrito de
`metadata_tecnica_protegida` (§11).

**Correspondência no legado:** hoje inferida do próprio `Status` do Envio
(`Enviado`/`Lido`) — não há registro de evidência separado.

**Adaptação necessária:** cada transição de `Status` legado precisa ser
reclassificada em um `tipo_evidencia` — `Lido` vira `LEITURA`, por exemplo.

**Riscos de migração:** o legado não distingue, para todo canal, aceite de
entrega real — nesses casos o adaptador não deve inventar uma Evidência de
nível mais alto do que o dado real sustenta.

---

## 13. Contratos Opcionais de Assinatura

**Só entram em jogo quando DEC-ENT-022 determina exigência de assinatura**
para o Tipo Documental/finalidade do Documento. Nenhum dos 5 contratos
abaixo é produzido para um Documento que não exige assinatura — sua
ausência não é erro nem pendência (DEC-ENT-022).

### SolicitacaoAssinatura — v1

**Finalidade:** transportar o processo de obter uma ou mais assinaturas
sobre um Documento e Arquivo específicos.
**Produtor:** módulo de Assinatura.
**Consumidores:** Distribuição (para entregar o Link via Envio), Auditoria.
**Entidade principal:** Solicitação de Assinatura.
**Evento ou comando relacionado:** `SolicitacaoAssinaturaCriada` até
`SolicitacaoAssinaturaFalhou` (`MAGNATA_OS_EVENTOS.md` §I).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `solicitacao_assinatura_id` | identificador canônico interno | identidade da Solicitação |
| `documento_id` | referência (Documento) | **link canônico**, nunca texto solto (corrige achado crítico #4) |
| `arquivo_apresentado_id` | referência (Arquivo) | versão exata apresentada para assinatura |
| `politica_conclusao` | enum: `TODOS`/`QUALQUER_UM`/`QUANTIDADE_MINIMA`/`SEQUENCIAL` (DEC-ENT-008) | como a conclusão é determinada |
| `estado_solicitacao` | enum: `RASCUNHO`/`PREPARADA`/`ENVIADA`/`EM_ASSINATURA`/`PARCIALMENTE_ASSINADA`/`CONCLUIDA`/`RECUSADA`/`EXPIRADA`/`CANCELADA`/`ERRO` (DEC-ENT-027) | estado atual |
| `criada_em` | timestamp ISO 8601 com fuso | criação |
| `solicitada_por` | referência (ator/sistema) | quem/o que disparou a criação |
| `correlation_id` | identificador de correlação | agrupa Signatários, Links, Assinaturas relacionados |

**Campos opcionais:**

| Campo | Tipo conceitual | Regra de presença |
|---|---|---|
| `expira_em` | timestamp ISO 8601 com fuso | quando a Solicitação tem prazo |
| `solicitacao_anterior_id` | referência (Solicitação de Assinatura) | presente **somente** quando esta é uma nova Solicitação deliberada para o mesmo Documento (ex.: versão corrigida) |
| `motivo_nova_solicitacao` | string | obrigatório **quando** `solicitacao_anterior_id` está presente |

**Regras de validação:**
- `documento_id` e `arquivo_apresentado_id` são obrigatoriamente
  referências canônicas — **nunca** texto livre (corrige
  `F_ASS_PROCESSAR_ID` do legado).
- Retry técnico da criação **não** gera nova Solicitação — a chave de
  idempotência da operação é distinta de `solicitacao_assinatura_id`
  (DEC-ENT-029); `solicitacao_anterior_id` só é usado para uma nova
  Solicitação **deliberada**, nunca para reconhecer retry.
- `estado_solicitacao = CONCLUIDA` só é válido quando `politica_conclusao`
  foi de fato satisfeita — nunca por uma única Assinatura isolada sob
  política que exige mais.

**Identificadores:** `solicitacao_assinatura_id` (canônico).

**Idempotência:** ver DEC-ENT-029 — chave de idempotência da criação é
conceito distinto da identidade da Solicitação.

**Erros possíveis:** `documento_id`/`arquivo_apresentado_id` inexistentes;
`politica_conclusao` sem Signatários suficientes para ser satisfeita (ex.:
`QUANTIDADE_MINIMA` maior que o total de Signatários informados).

**Dados proibidos:** conteúdo do Documento — só a referência ao Arquivo
apresentado.

**Correspondência no legado:** tabela `Assinaturas` (`tbl6xgW45637YJISv`),
`F_ASS_PROCESSAR_ID` (texto solto, `app.py:167`); bloco de campos
placeholder nunca criados no Airtable (`F_ASS_FINALIDADE`,
`F_ASS_STATUS_ENVIO`, etc., `app.py:183-192`).

**Adaptação necessária:** substituir a referência textual por link
canônico; os campos placeholder já desenhados no legado (nunca
implementados) mapeiam parcialmente para `estado_solicitacao` e para o
Contrato de Tentativa de Envio do Link (não modelado como contrato próprio
nesta versão — ver Link de Assinatura abaixo).

**Riscos de migração:** achado crítico #4 e #5 (`MAGNATA_OS_ENTIDADES.md`
§10) — corrigir a referência textual é pré-requisito para este contrato
funcionar de forma confiável em produção.

### Signatario — v1

**Finalidade:** transportar o papel de uma pessoa/parte dentro de uma
Solicitação específica.
**Produtor:** módulo de Assinatura.
**Consumidores:** Assinatura, Auditoria.
**Entidade principal:** Signatário.
**Evento ou comando relacionado:** `SignatarioAdicionado`,
`LinkAssinaturaAcessado` (`MAGNATA_OS_EVENTOS.md` §J).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `signatario_id` | identificador canônico interno | identidade do Signatário **dentro desta Solicitação** |
| `solicitacao_assinatura_id` | referência (Solicitação de Assinatura) | Solicitação à qual pertence |
| `nome_registrado` | string | nome utilizado **no momento** da Solicitação — não atualizado retroativamente se o cadastro da pessoa mudar (DEC-ENT-023) |
| `papel` | enum (ex.: `COLABORADOR`/`REPRESENTANTE_CLIENTE`/`RESPONSAVEL_LEGAL`/`TESTEMUNHA`/`GESTOR`/`OUTRO`) | papel deste Signatário |
| `estado_assinatura` | enum: `PENDENTE`/`ACESSADA`/`ASSINADA`/`RECUSADA`/`EXPIRADA`/`INVALIDADA` (DEC-ENT-028) | estado individual — **nunca reutilizado como estado de Documento** |

**Campos opcionais:**

| Campo | Tipo conceitual | Regra de presença |
|---|---|---|
| `entidade_relacionada_tipo` | enum (tipo de entidade canônica) | quando o Signatário se relaciona a uma entidade cadastrada (Colaborador, etc.) |
| `entidade_relacionada_id` | referência | idem — **não é sinônimo automático** de Signatário (DEC-ENT-023) |
| `identificador_registrado` | string (CPF ou outro) | quando juridicamente necessário, capturado no momento |
| `contato_utilizado` | string | contato usado para esta Solicitação especificamente |
| `ordem` | inteiro | relevante sob `politica_conclusao = SEQUENCIAL` |
| `autenticacao_exigida` | enum | método de autenticação exigido deste Signatário |

**Regras de validação:** alterações futuras no cadastro da pessoa
relacionada **não** propagam para `nome_registrado`/`identificador_registrado`
já gravados — esses campos são imutáveis após a criação do Signatário
(DEC-ENT-023).

**Identificadores:** `signatario_id` (canônico, escopo dentro da
Solicitação).

**Idempotência:** adicionar o mesmo Signatário (mesma
`entidade_relacionada_id`) duas vezes à mesma Solicitação, por retry
técnico, não duplica o papel.

**Erros possíveis:** `papel`/`ordem` inconsistentes com `politica_conclusao`
da Solicitação (ex.: `SEQUENCIAL` sem `ordem` definida para todos).

**Dados proibidos:** nenhum específico além dos gerais.

**Correspondência no legado:** `F_ASS_FUNCIONARIO` (link direto e único a
Funcionários) — não comporta Signatário sem vínculo de Colaborador.

**Adaptação necessária:** todo Signatário legado é inferido como
`papel = COLABORADOR`, `entidade_relacionada_tipo = Colaborador`; novos
papéis (testemunha, representante de Cliente) não têm equivalente legado a
adaptar — nascem só no contrato novo.

**Riscos de migração:** nenhum registro legado de Signatário sem
Colaborador existe hoje — não há dado histórico a perder nesse ponto
específico.

### LinkAssinatura — v1

**Finalidade:** transportar a credencial temporária de acesso a uma
Solicitação de Assinatura.
**Produtor:** módulo de Assinatura.
**Consumidores:** Distribuição (para entrega via Envio), Auditoria.
**Entidade principal:** Link de Assinatura.
**Evento ou comando relacionado:** `LinkAssinaturaCriado`,
`LinkAssinaturaRevogado`, `LinkAssinaturaExpirado`, `LinkAssinaturaAcessado`
(`MAGNATA_OS_EVENTOS.md` §J).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `link_assinatura_id` | identificador canônico interno | identidade do Link |
| `solicitacao_assinatura_id` | referência (Solicitação de Assinatura) | Solicitação relacionada |
| `token_hash` | string (hash) | hash do token — **nunca** o token em texto puro neste contrato |
| `criado_em` | timestamp ISO 8601 com fuso | geração |
| `estado_link` | enum: `VALIDO`/`EXPIRADO`/`REVOGADO` | situação atual |

**Campos opcionais:**

| Campo | Tipo conceitual | Regra de presença |
|---|---|---|
| `signatario_id` | referência (Signatário) | quando o Link é específico a um Signatário (não compartilhado) |
| `expira_em` | timestamp ISO 8601 com fuso | validade planejada |
| `revogado_em` | timestamp ISO 8601 com fuso | presente **quando** `estado_link = REVOGADO` |
| `motivo_revogacao` | string | obrigatório **quando** `revogado_em` está presente |
| `limite_acessos` | inteiro | quando há limite de uso |
| `quantidade_acessos` | inteiro | contador de uso até o momento |

**Regras de validação:**
- `estado_link = REVOGADO` exige `revogado_em` e `motivo_revogacao`.
- Um Link `EXPIRADO` ou `REVOGADO` nunca permite nova assinatura — a
  validação de acesso é feita contra este estado antes de qualquer
  operação de Assinatura.
- Gerar um novo Link **não** apaga o anterior — ambos permanecem no
  histórico, só o `estado_link` do anterior muda, se aplicável.

**Identificadores:** `link_assinatura_id` (canônico); `token_hash` (não é
identidade, é a credencial hasheada).

**Idempotência:** não aplicável como conceito recorrente — cada geração de
Link é um fato novo por definição (DEC-ENT-024).

**Erros possíveis:** tentativa de acesso a Link já `EXPIRADO`/`REVOGADO`;
`token_hash` inválido.

**Dados proibidos:** **o token completo nunca aparece neste contrato nem em
nenhum contrato de auditoria** — só o hash. Esta é uma restrição absoluta,
reforçada tanto pelo comando quanto por DEC-ENT-024 e pelo princípio 14 do
Manifesto.

**Correspondência no legado:** campo `Hash Token` (`F_ASS_HASH`) dentro do
registro único de `Assinaturas` — sem histórico de gerações/revogações.

**Adaptação necessária:** o `Hash Token` atual vira o primeiro
`LinkAssinatura` de cada Solicitação migrada, com `estado_link` inferido do
`Status` da Assinatura correspondente (`Pendente` → `VALIDO`; `Expirado` →
`EXPIRADO`).

**Riscos de migração:** sem histórico de múltiplos Links por Solicitação no
legado, a migração só reconstrói o Link mais recente conhecido.

### Assinatura — v1

**Finalidade:** transportar o ato individual de um Signatário.
**Produtor:** módulo de Assinatura.
**Consumidores:** Solicitação de Assinatura (avaliação de política),
Auditoria.
**Entidade principal:** Assinatura.
**Evento ou comando relacionado:** `AssinaturaRealizada`,
`AssinaturaRecusada`, `AssinaturaExpirada`, `AssinaturaInvalidada`
(`MAGNATA_OS_EVENTOS.md` §J).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `assinatura_id` | identificador canônico interno | identidade da Assinatura |
| `solicitacao_assinatura_id` | referência (Solicitação de Assinatura) | Solicitação relacionada |
| `signatario_id` | referência (Signatário) | quem assinou |
| `arquivo_apresentado_id` | referência (Arquivo) | versão apresentada no momento da assinatura |
| `estado_assinatura` | enum: `PENDENTE`/`ACESSADA`/`ASSINADA`/`RECUSADA`/`EXPIRADA`/`INVALIDADA` | espelha o estado do Signatário (DEC-ENT-028) — **nunca propagado como estado de Documento** |
| `correlation_id` | identificador de correlação | herdado da Solicitação |

**Campos opcionais:**

| Campo | Tipo conceitual | Regra de presença |
|---|---|---|
| `realizada_em` | timestamp ISO 8601 com fuso | presente **quando** `estado_assinatura = ASSINADA` |
| `metodo_autenticacao` | enum | método usado na autenticação do Signatário |
| `arquivo_assinado_id` | referência (Arquivo, `papel_arquivo = ASSINADO`) | presente após a geração do Arquivo Assinado (DEC-ENT-026) |
| `evidencia_id` | referência (Evidência da Assinatura, abaixo) | evidência associada |

**Regras de validação:**
- `estado_assinatura = ASSINADA` exige `realizada_em` e evidência mínima
  associada (§ Evidência da Assinatura abaixo) — nunca gravado só pela
  aparência de uma tela de sucesso (DEC-ENT-025).
- Este contrato **nunca** popula um campo de estado de Documento — essa é
  a regra mais crítica de todo o conjunto de contratos de assinatura,
  correspondendo diretamente à correção do achado crítico #1.

**Identificadores:** `assinatura_id` (canônico).

**Idempotência:** uma Assinatura por Signatário por Solicitação — dupla
submissão do mesmo formulário não gera duas Assinaturas.

**Erros possíveis:** tentativa de assinar com Link
`EXPIRADO`/`REVOGADO`; evidência insuficiente para o método declarado.

**Dados proibidos:** dados de evidência sensíveis (IP, biometria, se algum
dia aplicável) só circulam dentro do Contrato de Evidência da Assinatura,
com proteção equivalente à de dados de auditoria.

**Correspondência no legado:** conclusão em `/assinatura/<hash_token>`
(POST), `F_ASS_STATUS: 'Assinado'` em `Assinaturas`, **e hoje também**
`Status = 'Assinado'` em Processar Arquivos (achado crítico #1).

**Adaptação necessária:** o adaptador de saída (canônico → legado, §17)
precisa decidir se ainda escreve o campo de compatibilidade em Processar
Arquivos durante o período de transição — e, se escrever, isso é uma
adaptação documentada e temporária, não o contrato em si aceitando esse
comportamento como correto.

**Riscos de migração:** é o ponto de maior risco jurídico/de auditoria de
todo este documento — qualquer falha em preservar a Assinatura como fato
imutável, distinto do estado do Documento, reproduz o achado crítico #1.

### EvidenciaAssinatura — v1

**Nota de forma técnica em aberto** (DEC-ENT-025): entidade própria ou
registro imutável vinculado à Assinatura — não decidido aqui.

**Finalidade:** transportar os fatos e artefatos que sustentam uma
Assinatura.
**Produtor:** módulo de Assinatura.
**Consumidores:** Auditoria (acesso restrito).
**Entidade principal:** Evidência da Assinatura (candidata).
**Evento ou comando relacionado:** `EvidenciaAssinaturaRegistrada`
(candidato, `MAGNATA_OS_EVENTOS.md` §J).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `evidencia_assinatura_id` | identificador canônico interno | identidade da ocorrência |
| `assinatura_id` | referência (Assinatura) | Assinatura relacionada |
| `ocorrida_em` | timestamp ISO 8601 com fuso | quando o fato de evidência ocorreu |
| `metodo_autenticacao` | enum | método usado |
| `resultado` | enum: `SUFICIENTE`/`INSUFICIENTE`/`INCONCLUSIVO` | avaliação da evidência coletada frente ao método declarado |
| `correlation_id` | identificador de correlação | herdado da Assinatura |

**Campos opcionais (acesso restrito — nunca em log comum):**

| Campo | Tipo conceitual | Regra de presença |
|---|---|---|
| `hash_antes` | string (hash) | hash do Arquivo antes da assinatura |
| `hash_depois` | string (hash) | hash do Arquivo resultante |
| `sessao_id` | identificador técnico | quando aplicável |
| `ip_protegido` | string, acesso restrito | só quando juridicamente permitido e necessário (DEC-ENT-025) |
| `agente_dispositivo` | string | User-Agent ou equivalente |
| `termos_versao` | string | versão dos termos apresentados |
| `aceite_registrado` | booleano | se houve aceite explícito capturado |

**Regras de validação:**
- **Tela de sucesso, isoladamente, nunca produz `resultado = SUFICIENTE`.**
- Imagem isolada de assinatura, sem os demais campos de evidência
  correlatos, não comprova autoria/integridade/validade por si só
  (DEC-ENT-025).
- O Magnata OS **nunca declara validade jurídica absoluta** neste contrato
  — só registra fatos; a suficiência jurídica depende do Tipo Documental,
  método e requisitos aplicáveis, avaliados fora deste contrato.

**Identificadores:** `evidencia_assinatura_id` (canônico).

**Idempotência:** cada evidência capturada é um fato novo — não há
duplicidade a evitar entre evidências distintas do mesmo tipo.

**Erros possíveis:** `resultado = INSUFICIENTE` para o método declarado.

**Dados proibidos:** `ip_protegido` e demais campos sensíveis nunca
circulam fora de contexto de acesso restrito — nunca em log comum, nunca
em resposta HTTP padrão.

**Correspondência no legado:** IP, User-Agent, CPF Informado, Data/Hora
Assinatura já existem em `Assinaturas` (achado positivo do legado).

**Adaptação necessária:** os campos já existentes migram diretamente;
`hash_antes`/`hash_depois`, `termos_versao` e `correlation_id` não têm
equivalente legado e nascem vazios/inferidos para dados históricos.

**Riscos de migração:** dados históricos não terão `hash_antes`/`hash_depois`
reconstruíveis — essa lacuna deve ser reconhecida explicitamente, não
preenchida com valor inventado.

**Reforço final:** nem todo Documento usa os 5 contratos desta seção — sua
ausência para um Documento sem exigência de assinatura é o caminho normal,
não uma lacuna (DEC-ENT-022).

---

## 14. Contrato do Envelope de Evento

### EnvelopeEvento — v1

**Finalidade:** transportar o envelope comum a todo evento do catálogo
(`MAGNATA_OS_EVENTOS.md` §3) — este contrato não substitui aquele
documento, formaliza-o como contrato de dados.
**Produtor:** todo módulo que emite evento.
**Consumidores:** todo módulo que consome evento; Auditoria.
**Entidade principal:** transversal — não pertence a uma entidade única.
**Evento ou comando relacionado:** todos os 54 eventos canônicos
(`MAGNATA_OS_EVENTOS.md` §5).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `event_id` | identificador canônico interno | identidade **desta ocorrência** do evento |
| `event_name` | string (enum aberto — vocabulário de `MAGNATA_OS_EVENTOS.md` §5) | nome canônico do evento |
| `event_version` | string (versão semântica do formato) | versão do formato do evento — **diferente** da versão da entidade afetada |
| `occurred_at` | timestamp ISO 8601 com fuso | quando o fato ocorreu |
| `recorded_at` | timestamp ISO 8601 com fuso | quando foi registrado — pode divergir de `occurred_at` |
| `entity_type` | enum (tipo de entidade canônica) | tipo da entidade afetada |
| `entity_id` | referência (conforme `entity_type`) | identidade da entidade afetada |
| `correlation_id` | identificador de correlação | agrupa o fluxo de negócio completo |
| `source_module` | string | módulo emissor |
| `payload` | estrutura (específica de cada `event_name`) | dados mínimos do evento, definidos em `MAGNATA_OS_EVENTOS.md` §4 |

**Campos opcionais:**

| Campo | Tipo conceitual | Regra de presença |
|---|---|---|
| `causation_id` | identificador de correlação | presente quando há um comando/evento causador identificável |
| `actor_type` | enum: `SISTEMA`/`USUARIO`/`INTEGRACAO_EXTERNA` | quando relevante distinguir |
| `actor_id` | identificador (conforme `actor_type`) | idem |
| `source_system` | string | presente quando a origem é externa (Secullum, Evolution API, Gmail) |
| `tenant_or_company_id` | referência (Empresa) | reservado para expansão futura — hoje sempre a Magnata |
| `metadata` | mapa chave-valor | dados técnicos auxiliares, não de negócio |

**Regras de validação:**
- `event_id` é sempre único por ocorrência — mesmo quando `event_name` e
  `entity_id` se repetem (ex.: duas `TentativaEnvioFalhou` do mesmo Envio).
- `entity_id` nunca é confundido com `event_id` (§2.1).
- `payload` segue o "Dados mínimos" definido para o `event_name`
  específico em `MAGNATA_OS_EVENTOS.md` §4 — este contrato não repete
  aqueles 54 formatos individualmente, referencia-os.

**Identificadores:** `event_id` (canônico da ocorrência); `entity_id`
(canônico da entidade afetada) — dois conceitos, nunca fundidos.

**Idempotência:** consumidores identificam eventos já processados por
`event_id` — reentrega de publicação não deve ser reprocessada como fato
novo.

**Erros possíveis:** `event_name` não reconhecido; `payload` incompatível
com o `event_name` declarado; `entity_type`/`entity_id` inconsistentes.

**Dados proibidos:** credenciais, tokens completos (ex.: nunca em
`metadata` de um evento relacionado a Link de Assinatura — só o hash, se
necessário).

**Correspondência no legado:** não existe conceito de envelope de evento
hoje — o legado opera por efeito colateral direto (gravação de campo),
sem um formato de evento publicado.

**Adaptação necessária:** qualquer publicação retroativa de eventos a
partir de dados históricos do legado precisa reconstruir `occurred_at` a
partir do melhor dado disponível (ex.: `Created` do Airtable), reconhecendo
que pode não refletir o instante exato do fato original.

**Riscos de migração:** nenhum event bus existe hoje — a adoção deste
envelope não pressupõe, por si só, infraestrutura de mensageria; pode
começar como registro interno consultável antes de virar transporte entre
processos.

---

## 15. Contrato de Erro

### Erro — v1

**Finalidade:** transportar, de forma comum, qualquer falha de validação ou
processamento em qualquer contrato deste documento.
**Produtor:** qualquer módulo.
**Consumidores:** todo módulo; Auditoria.
**Entidade principal:** transversal.
**Evento ou comando relacionado:** todos os eventos de falha
(`MAGNATA_OS_EVENTOS.md` §8).

**Campos obrigatórios:**

| Campo | Tipo conceitual | Significado |
|---|---|---|
| `error_id` | identificador canônico interno | identidade da ocorrência de erro |
| `category` | enum: `VALIDACAO`/`NEGOCIO`/`TECNICA`/`INTEGRACAO_EXTERNA` | categoria do erro |
| `code` | string | código específico, estável entre versões compatíveis |
| `safe_message` | string | mensagem segura para exibição/log comum — **nunca** stack trace ou dado sensível |
| `retryable` | booleano | se uma nova tentativa automática é sensata |
| `occurred_at` | timestamp ISO 8601 com fuso | quando o erro ocorreu |
| `operation` | string | operação que falhou (ex.: "criar Documento", "despachar Envio") |
| `correlation_id` | identificador de correlação | agrupa com o fluxo de negócio afetado |

**Campos opcionais:**

| Campo | Tipo conceitual | Regra de presença |
|---|---|---|
| `entity_type` | enum | quando o erro está associado a uma entidade específica |
| `entity_id` | referência | idem |
| `provider` | string | quando o erro vem de integração externa |
| `request_id` | identificador técnico | quando há uma chamada técnica específica associada |
| `causation_id` | identificador de correlação | quando há um evento/comando causador identificável |
| `detail_reference` | referência (a um registro protegido) | ponteiro para o detalhe técnico completo, armazenado separadamente |

**Regras de validação:**
- **Resposta de erro nunca retorna sucesso.** Nenhum contrato deste
  documento permite que um `Erro` seja transportado dentro de uma resposta
  que também sinaliza sucesso (violaria o princípio 10 do Manifesto,
  Erros Explícitos).
- `safe_message` e o detalhe técnico protegido (via `detail_reference`)
  são **sempre** campos diferentes — nunca a mesma string reaproveitada.
- Stack trace **nunca** circula em `safe_message` nem em nenhum campo deste
  contrato — só no armazenamento protegido referenciado por
  `detail_reference`, se necessário.

**Identificadores:** `error_id` (canônico da ocorrência).

**Idempotência:** não aplicável como conceito recorrente — cada ocorrência
de erro é um fato técnico distinto, mesmo quando a causa se repete
(consistente com Tentativa de Envio, §11).

**Erros possíveis:** não aplicável (é o próprio contrato de erro).

**Dados proibidos:** credenciais; conteúdo de Documento; stack trace bruto;
qualquer dado que violaria o princípio 14 do Manifesto (segurança por
padrão) se exposto num log comum.

**Correspondência no legado:** mensagens de exceção capturadas em
`logger.warning`/`logger.error` (`app.py`, disperso); códigos técnicos
gravados em `F_PROC_TIPO_DOC` (`UPLOAD_FAILED`, `PROCESSING_ERROR` —
débito conhecido #3, misturado com Tipo Documental).

**Adaptação necessária:** separar, definitivamente, o que hoje vive
misturado em `F_PROC_TIPO_DOC` — códigos técnicos migram para este
Contrato de Erro, nunca para `tipo_documental` no Contrato de Documento
(§6).

**Riscos de migração:** dado histórico onde erro técnico e categoria
documental estão fundidos exige decisão de reprocessamento, não só de
mapeamento — alguns registros podem não ser distinguíveis
retroativamente sem reanálise.

---

## 16. Contratos versus Campos Legados

| Conceito canônico | Campo legado | Tabela/fluxo | Problema | Regra de adaptação |
|---|---|---|---|---|
| `tipo_documental` (Documento) | `Tipo` **e** `Tipo de Documento` | `Processar Arquivos` | dois campos competindo, um contaminado com erro técnico | usar `Tipo` (`fldJWy7givUDs1aCl`) como fonte; nunca `Tipo de Documento` quando o valor for um código técnico |
| Arquivo (referência) | `Arquivos` | tabela `Arquivos` | nenhum no dado — só no nome | adaptador direto, sem transformação de significado |
| relação Documento↔Arquivo | `Arquivos 2` | `Processar Arquivos` | nome sugere segundo conjunto de anexos | tratar como referência relacional única, não duplicar |
| `estado_documento`/`estado_envio`/`estado_solicitacao` | `Status` (múltiplas tabelas, vocabulários distintos) | `Processar Arquivos`, `Envios de Documentos`, `Assinaturas` | um nome de campo, três vocabulários diferentes, sem namespace | cada adaptador de tabela usa o vocabulário conceitual do contrato correspondente — nunca um vocabulário genérico "Status" compartilhado |
| (proibido) `estado_documento = ASSINADO` | `Status = 'Assinado'` em `Processar Arquivos` | `app.py:9896` | achado crítico #1 | mapear para `estado_documento = CONCLUIDO` + Assinatura associada — nunca para um valor `ASSINADO` no Contrato de Documento |
| identificador canônico | Airtable Record ID | todas as tabelas | usado como identidade permanente | tratar sempre como referência externa (`identificadores_legados`/`identificadores_externos`), nunca como `*_id` canônico |
| `Colaborador`/`destinatario_id` | casamento por nome completo | `app.py:1421-1465` | nome não é identificador confiável (incidente real: Eduardo Caetano rotulado como Milton) | usar CPF como chave primária de casamento; nome só como sinal auxiliar de baixa confiança |
| `endereco_utilizado` (Envio) | telefone/e-mail em texto livre | `Envios de Documentos.Destinatário` | endereço e identidade confundidos | separar Destinatário (identidade) de `endereco_utilizado` (valor daquele Envio específico) |
| `numero_tentativa` (Tentativa de Envio) | contador `Tentativa` | `Envios de Documentos` | só o número final, sem histórico | criar registro individual retroativamente só a partir da migração; histórico anterior não é recuperável |
| campos de Solicitação de Assinatura | bloco `fldXXXXXXXXXXXXXX` × 6, nunca criados | `app.py:183-192` | campos já desenhados, nunca implementados | usar o desenho existente como ponto de partida do contrato, não reinventar nomenclatura |
| resposta de provedor | HTTP 200/201 tratado como sucesso | rotas `disparar-fila*` | ausência de erro de transporte confundida com aceite de negócio | Contrato de Erro e de Tentativa de Envio exigem checar o corpo da resposta, não só o código HTTP |
| `estado_envio`/`estado_documento` | `Enviar`, `Pendente`, `Processando`, `Concluído` | múltiplas tabelas | vocabulário informal, sem namespace por entidade | cada contrato usa seu próprio enum, mesmo quando o nome textual coincide entre legado e canônico |
| (não decidido) | `Finalizado`, `Pronto` | não confirmados no código | DEC-ENT-012 `PENDENTE` | **nenhum contrato deste documento assume a existência ou o significado** desses valores — nenhuma adaptação é definida até confirmação direta no schema do Airtable |

Regra aplicada de forma consistente: **uma alteração de campo no Airtable
não vira, automaticamente, um valor de contrato.** Cada linha acima é uma
correspondência já verificada por evidência, não uma tradução mecânica.

---

## 17. Regras de Compatibilidade

- **Adaptador de entrada** (legado → canônico): traduz um registro/campo
  legado para o contrato correspondente no momento da leitura — nunca
  altera o dado de origem.
- **Adaptador de saída** (canônico → legado): traduz um contrato canônico
  para o formato que o legado ainda espera, durante o período de
  transição — necessário enquanto rotas/consumidores antigos não migraram.
- **Período de dupla leitura, quando necessário:** um módulo em transição
  pode precisar ler tanto o formato legado quanto o canônico, até que o
  produtor migre por completo — isso é uma fase explícita, com prazo, não
  um estado permanente.
- **Escrita única na fonte oficial:** mesmo durante dupla leitura, existe
  sempre **uma** fonte de escrita autoritativa por dado — nunca dois
  produtores escrevendo o "mesmo" campo por caminhos diferentes sem
  reconciliação.
- **Telemetria de uso dos campos antigos:** antes de desligar um caminho
  legado, medir se ele ainda é lido/escrito por algo — decisão de retirada
  não deve ser feita às cegas.
- **Plano de retirada:** todo adaptador tem uma condição de encerramento
  registrada (quando o último consumidor legado migrar), não vida útil
  indefinida.
- **Proibição de espalhar aliases legados em módulos novos:** um módulo
  novo nunca importa `F_PROC_TIPO_DOC` ou qualquer nome de campo legado
  diretamente — só through o adaptador, e só o adaptador conhece o nome
  legado.

**Nenhum adaptador é implementado nesta etapa** — esta seção define a
regra, não o código.

---

## 18. Versionamento dos Contratos

- **Versão inicial: `v1`**, para todos os 16 contratos deste documento.
- **Mudança compatível** (não exige nova versão): adição de campo
  **opcional** novo; adição de valor novo a um enum, quando os consumidores
  existentes já tolerarem valores desconhecidos (§1); relaxamento de uma
  regra de validação (aceitar mais casos, não menos).
- **Mudança incompatível** (exige nova versão, ex. `v2`): remoção de campo;
  renomeação de campo; alteração de significado de um campo existente;
  alteração de um campo de opcional para obrigatório; remoção de um valor
  de enum já em uso; qualquer mudança que quebre um consumidor que segue a
  `v1` sem alteração.
- **Adição de campo:** só é compatível se **opcional**; campo obrigatório
  novo é, por definição, mudança incompatível (consumidores antigos não o
  produziam).
- **Remoção de campo:** sempre incompatível — mesmo que o campo pareça não
  usado, um consumidor pode depender dele silenciosamente.
- **Renomeação:** tratada como remoção do nome antigo + adição do novo —
  sempre incompatível, nunca "só um apelido".
- **Alteração de significado:** proibida dentro da mesma versão, sob
  qualquer circunstância (princípio 1, "campo não muda de significado
  silenciosamente") — exige nova versão, mesmo que o nome do campo não
  mude.
- **Período de depreciação:** uma versão antiga permanece aceita por um
  prazo definido e comunicado após a nova versão existir — nunca
  desligada da noite para o dia sem aviso aos consumidores conhecidos.

**Nenhum sistema complexo de governança é criado aqui** — versionamento
simples por número inteiro crescente (`v1`, `v2`, ...) é suficiente para o
estágio atual do Magnata OS.

---

## 19. Contratos Mínimos da Primeira Migração

### Obrigatórios (11)

Item de Ingestão, Arquivo, Documento, Classificação (Entrada + Resultado),
Distribuição, Destinatário, Envio, Tentativa de Envio, Evidência de
Entrega, Envelope de Evento, Erro.

### Opcionais de assinatura (5)

Solicitação de Assinatura, Signatário, Link de Assinatura, Assinatura,
Evidência da Assinatura — só produzidos quando DEC-ENT-022 determina
exigência.

### Futuros (fora desta versão)

Cliente completo (com Tipo de Cliente, DEC-ENT-001), Contrato Comercial,
Vínculo Trabalhista, Alocação, contratos de Folha/Holerite detalhados,
contratos de Ponto/Alerta (aguardando DEC-ENT-010/011), contratos
financeiros.

**Total: 16 contratos definidos nesta versão** (11 obrigatórios + 5
opcionais — Classificação contada como 1 contrato com duas partes,
Entrada e Resultado, consistente com §7).

---

## 20. Validações Cruzadas

1. **Cada evento mínimo (17, `MAGNATA_OS_EVENTOS.md` §12) possui dados
   suficientes em algum contrato** — verificado: `ItemIngestaoRecebido` →
   Contrato de Item de Ingestão; `ArquivoClassificado` → Contrato de
   Classificação/Documento; `DocumentoCriado` → Contrato de Documento;
   `ArquivoVinculadoAoDocumento` → Contrato de Arquivo;
   `DocumentoProcessamentoFalhou` → Contrato de Documento + Erro;
   `DistribuicaoCriada` → Contrato de Distribuição; `EnvioCriado`/
   `EnvioColocadoNaFila`/`EnvioAceitoPeloProvedor`/`EnvioEntregue` →
   Contrato de Envio; `TentativaEnvioFalhou` → Contrato de Tentativa de
   Envio; `EnvioFalhaDefinitivaRegistrada` → Contrato de Envio + Erro;
   `SolicitacaoAssinaturaCriada`/`SolicitacaoAssinaturaConcluida` →
   Contrato de Solicitação de Assinatura; `LinkAssinaturaCriado` → Contrato
   de Link de Assinatura; `AssinaturaRealizada` → Contrato de Assinatura;
   `ArquivoAssinadoGerado` → Contrato de Arquivo (papel `ASSINADO`).
2. **Cada entidade mínima (9 do núcleo documental, `MAGNATA_OS_ENTIDADES.md`
   §11) possui contrato ou justificativa** — Cliente e Posto de Trabalho
   **não** têm contrato próprio nesta versão (ficam em "Futuros", §19) —
   justificativa: são referenciados por `documento_id`/`destinatario_id`
   sem exigir contrato completo para o núcleo mínimo funcionar; Colaborador
   idem, referenciado via `titularidade_id`/`entidade_relacionada_id`.
3. **Documento e Arquivo não estão misturados** — confirmado: Contrato de
   Documento (§6) nunca embute binário; Contrato de Arquivo (§5) nunca
   carrega campos de classificação/titularidade.
4. **Distribuição, Envio e Tentativa estão separados** — confirmado: três
   contratos distintos (§8, §10, §11), cada um com `*_id` próprio e relação
   explícita ao outro, nunca campos fundidos.
5. **Assinatura permanece opcional** — confirmado: §13 abre com a condição
   explícita de que os 5 contratos só existem quando DEC-ENT-022 determina
   exigência; nenhum campo obrigatório de Documento (§6) referencia
   Solicitação de Assinatura.
6. **Nenhum estado de Assinatura aparece como estado de Documento** —
   confirmado: `estado_documento` (§6) lista explicitamente que
   `ASSINADO` é valor proibido, com validação própria; `estado_assinatura`
   vive só nos contratos de Signatário/Assinatura (§13).
7. **Canal e provedor estão separados** — confirmado: Contrato de Envio
   (§10) tem `canal` (enum de negócio) e `provedor_tecnico` (string
   técnica) como campos distintos.
8. **IDs internos e externos estão separados** — confirmado em todo
   contrato: cada um distingue `*_id` canônico de `identificadores_legados`/
   `identificadores_externos`/`identificador_externo` (§2.1 aplicado
   uniformemente).
9. **HTTP 200/201 não é prova de entrega** — confirmado: regra de
   validação explícita no Contrato de Envio (§10) e no Contrato de
   Tentativa de Envio (§11), reforçada no Contrato de Evidência de Entrega
   (§12).
10. **Retry e reenvio estão separados** — confirmado: Contrato de Envio
    (§10) trata `envio_anterior_id`/`motivo_reenvio` como exclusivos de
    Reenvio deliberado; Contrato de Tentativa de Envio (§11) é o único
    lugar onde retry técnico vive, sem gerar novo `envio_id`.

---

## 21. Conclusão

**Quantidade de contratos definidos:** 16 (11 obrigatórios + 5 opcionais de
assinatura), mais o Envelope de Evento (§14) e o Contrato de Erro (§15) já
contados dentro dos 11 obrigatórios.

**Contratos obrigatórios:** Item de Ingestão, Arquivo, Documento,
Classificação, Distribuição, Destinatário, Envio, Tentativa de Envio,
Evidência de Entrega, Envelope de Evento, Erro.

**Contratos opcionais de assinatura:** Solicitação de Assinatura,
Signatário, Link de Assinatura, Assinatura, Evidência da Assinatura.

**Maiores incompatibilidades com o legado:** (1) `Tipo`/`Tipo de
Documento` competindo e um contaminado com erro técnico; (2) `Status =
'Assinado'` em Processar Arquivos, que o Contrato de Documento agora
proíbe explicitamente; (3) referência textual solta Assinatura→Documento,
que o Contrato de Solicitação de Assinatura exige ser link canônico; (4)
ausência de registro individual de Tentativa de Envio; (5) Destinatário
inexistente como cadastro separado, hoje só texto livre em Envio.

**Decisões ainda pendentes que afetam contratos:** DEC-ENT-010, 011, 012
(nenhum contrato deste documento assume resposta a elas); forma técnica
final de Evidência de Entrega e Evidência da Assinatura (entidade própria
× registro imutável); nomes finais de campo além dos conceituais aqui
definidos (isso é, propositalmente, trabalho de uma revisão de
implementação, não deste documento).

**Condições para criar as máquinas de estados:** os vocabulários de estado
já estão fixados por contrato nesta versão (`estado_documento`,
`estado_envio`, `estado_solicitacao`, `estado_assinatura`, `estado_link`) —
a máquina de estados formal (transições permitidas, guardas, efeitos
colaterais por transição) pode ser desenhada a partir daqui sem
pré-requisito bloqueante adicional, desde que respeite as proibições já
registradas (nenhuma transição para `ASSINADO` em Documento; nenhum avanço
de `estado_envio` sem evidência correspondente).

---

## Confirmação de Escopo

Nenhum arquivo existente foi alterado para produzir este documento — apenas
`MAGNATA_OS_CONTRATOS.md` foi criado. Nenhum código, tabela do Airtable,
configuração, memória, classe, JSON Schema, tabela de banco ou adaptador foi
criado ou implementado. Nenhum nome de campo em produção foi alterado.
Nenhum contrato conceitual foi tratado como implementação concluída.
