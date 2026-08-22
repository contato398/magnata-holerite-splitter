<!-- PROVENIÊNCIA (Etapa 3 da Central Command, 2026-08-22) — resgate documental.
Origem: branch `feat/magnata-os-claude-powerpack`, HEAD `053acada09dfc70bda71d2293aacbf2bca9ed43e`,
PR #12, FECHADO SEM MERGE em 2026-08-03T17:16:01Z. Texto original preservado;
as únicas alterações são a NOTA DE RECONCILIAÇÃO abaixo (quando existe) e a
de-identificação exigida por `CLAUDE.md` §6/LGPD, ambas declaradas.
Nenhuma decisão aprovada pela Direção foi alterada. -->

# Magnata OS — Catálogo Canônico de Eventos

**Versão:** 1.0
**Status:** CANÔNICO INICIAL
**Data:** 2026-07-22
**Fontes:** `MAGNATA_OS_MANIFESTO.md`, `MAGNATA_OS_ARQUITETURA.md`,
`MAGNATA_OS_ENTIDADES.md`, `MAGNATA_OS_DECISOES_ENTIDADES.md`, e evidências
de código já citadas nos documentos anteriores (não relidas do zero nesta
etapa — reaproveitadas por referência).

**Nota de escopo deste documento** (decisão editorial, registrada aqui para
não ser confundida com corte silencioso): a §2 abaixo define o **template
completo de 15 campos** para um evento. Aplicar esse template completo aos
~96 nomes avaliados neste catálogo produziria um documento
desproporcional ao problema. Por isso:

- Os eventos do **núcleo mínimo da primeira migração** (§12) recebem o
  **template completo**, em §4.
- Os demais eventos `CANÔNICO` e `CANDIDATO` recebem um **registro
  condensado** (mesma informação essencial, formato de tabela) dentro de
  cada categoria de §4.
- **Nenhum nome foi avaliado com menos rigor por causa disso** — a tabela
  consolidada de §5 cobre os 96 nomes sem exceção, com classificação e
  justificativa individuais.

Nenhum código, tabela do Airtable, configuração, memória ou outro documento
foi alterado para produzir este catálogo.

---

## 0. Princípio central

**Um evento representa um fato de negócio que já aconteceu.** Passado,
imutável, com timestamp.

**Exemplos corretos:** `ItemIngestaoRecebido`, `DocumentoClassificado`,
`EnvioAceitoPeloProvedor`, `AssinaturaRealizada`.

**O que não é evento:**

| Exemplo | O que é de fato |
|---|---|
| `ProcessarDocumento` | Comando — uma intenção que pode falhar |
| `EnviarMensagem` | Ação — um verbo, não um fato consumado |
| `TentarNovamente` | Comando de retry, não o resultado dele |
| `Pendente` | Estado — situação atual, não fato ocorrido |
| `Processando` | Estado |
| `HTTP200` | Resposta técnica de transporte — não prova fato de negócio |
| `ExecutarFatiamento` | Operação interna — implementação, não vocabulário de negócio |

A fronteira entre essas cinco categorias (comando, ação, estado, resposta
técnica, operação interna) e um evento genuíno é aplicada a cada um dos
~96 nomes avaliados neste documento — não é só uma explicação teórica na
abertura.

---

## 1. Regras de nomeação

Nome conceitual em português: **Substantivo + Verbo no particípio (fato
concluído)**.

**Corretos:** `DocumentoCriado`, `ArquivoClassificado`, `EnvioFalhou`,
`SolicitacaoAssinaturaExpirada`.

**Evitar nomes genéricos** que não dizem qual entidade nem qual fato:
`Processado`, `Atualizado`, `Concluido`, `Erro`, `Sucesso`. Essa regra é
aplicada de forma estrita neste catálogo — nomes propostos nas fontes deste
comando que caem nessa armadilha (ex.: `DocumentoAtualizado`,
`AlocacaoAlterada`, `AlertaPontoAtualizado`) são rejeitados explicitamente em
§5, não silenciosamente ignorados.

O nome deve sempre deixar claro **qual entidade** e **qual fato**, sem
depender de contexto externo para ser entendido.

---

## 2. Estrutura obrigatória de cada evento (template completo)

```text
### NomeDoEvento

**Definição:** fato de negócio representado.
**Entidade principal:** entidade que sofreu ou originou o fato.
**Momento de emissão:** condição exata do registro.
**Não emitir quando:** situações semelhantes que não justificam o evento.
**Dados mínimos:** campos conceituais obrigatórios (além do envelope, §3).
**Dados opcionais:** informações complementares.
**Estado anterior esperado:** quando aplicável.
**Estado resultante:** quando aplicável.
**Módulo produtor:** módulo responsável por emitir.
**Módulos consumidores potenciais:** módulos que podem reagir.
**Efeito esperado:** consequências possíveis, sem acoplamento direto
obrigatório.
**Idempotência:** como evitar duplicidade lógica.
**Auditoria:** informação obrigatória para rastreabilidade.
**Correspondência no legado:** funções/rotas/tabelas/estados/logs atuais.
**Riscos de migração:** falhas ou ambiguidades esperadas.
**Decisões e entidades relacionadas:** `DEC-ENT-*` e entidades canônicas.
```

Usado integralmente só para os eventos do núcleo mínimo (§4, marcados
`[TEMPLATE COMPLETO]`); os demais usam o registro condensado (mesma seção,
formato de tabela).

---

## 3. Envelope Canônico de Evento

Estrutura conceitual comum a **todo** evento deste catálogo — nenhum campo
abaixo é específico de um tipo de evento:

| Campo | Papel |
|---|---|
| `event_id` | identifica **esta ocorrência** do evento (não o tipo) |
| `event_name` | nome canônico do evento (ex.: `DocumentoCriado`) |
| `event_version` | versão do **formato do evento** — diferente da versão da entidade afetada |
| `occurred_at` | quando o fato de negócio ocorreu |
| `recorded_at` | quando o evento foi registrado pelo sistema (pode divergir de `occurred_at` — ex.: confirmação de entrega chegando atrasada) |
| `entity_type` | tipo da entidade canônica afetada (ex.: `Documento`) |
| `entity_id` | identificador canônico da entidade afetada |
| `correlation_id` | agrupa todo o fluxo de negócio relacionado (ex.: um Item de Ingestão até seus Envios) |
| `causation_id` | identifica o comando ou evento que causou diretamente este fato |
| `actor_type` | tipo de ator que causou o fato (sistema, usuário, integração externa) |
| `actor_id` | identificador do ator |
| `source_module` | módulo do Magnata OS que emitiu o evento |
| `source_system` | sistema de origem, quando externo (Secullum, Evolution API, Gmail) |
| `tenant_or_company_id` | quando aplicável — hoje irrelevante (Magnata é mono-tenant), reservado para o caso de expansão futura |
| `payload` | dados mínimos específicos do evento (§2, "Dados mínimos") |
| `metadata` | dados técnicos auxiliares (não de negócio) |

Registrado explicitamente:

- `event_id` identifica a ocorrência; `entity_id` identifica a entidade —
  não são o mesmo conceito, e um evento nunca deve confundir os dois.
- `correlation_id` agrupa o fluxo completo (ex.: todos os Envios gerados por
  uma Distribuição); `causation_id` aponta o passo imediatamente anterior
  que gerou este evento — a diferença importa para reconstituir a cadeia
  causal, não só o agrupamento.
- Versão do evento (`event_version`) é diferente da versão/vigência de
  Arquivo (DEC-ENT-017) — são dois conceitos de versionamento distintos que
  não devem ser confundidos.
- Airtable Record ID pode existir **apenas como referência externa** dentro
  de `metadata` ou como parte de `entity_id` transitoriamente — nunca como o
  próprio `entity_id` canônico (§8, Identidade e Chaves, de
  `MAGNATA_OS_ENTIDADES.md`).
- O **payload final** (nomes de campo, tipos, formato) será definido em
  contratos de dados posteriores — este documento não cria JSON Schema nem
  código.

---

## 4. Catálogo por Categoria

### A. Ingestão

O canal de entrada (Gmail, Apps Script, upload manual, API, navegador ou
outra integração) **não altera o significado do evento de negócio** — um
`ItemIngestaoRecebido` é o mesmo fato conceitual venha de onde vier;
`source_module`/`source_system` no envelope (§3) carregam essa diferença, não
o nome do evento.

#### ItemIngestaoRecebido `[TEMPLATE COMPLETO]`

**Definição:** um item de origem (hoje, tipicamente um e-mail de remetente
confiável) chegou ao Magnata OS, antes de qualquer classificação.
**Entidade principal:** Item de Ingestão.
**Momento de emissão:** no instante em que o item é recebido e persistido
como registro de Item de Ingestão — não no instante em que o canal de
origem (Gmail, upload, API) apenas o entregou à borda do sistema.
**Não emitir quando:** o item chega mas falha a validação básica antes de
virar um registro persistido (nesse caso, ver `ItemIngestaoRejeitado`); um
Arquivo chega solto sem um Item de Ingestão que o origine (caso hoje raro,
mas não impossível — upload manual direto).
**Dados mínimos:** identificador do Item de Ingestão, canal de origem,
Message ID (quando aplicável), Assunto, timestamp de chegada.
**Dados opcionais:** Conteúdo do e-mail, remetente.
**Estado anterior esperado:** não aplicável (é a origem do ciclo de vida).
**Estado resultante:** não aplicável — Item de Ingestão não tem vocabulário
de estado formalmente aprovado (`MAGNATA_OS_ENTIDADES.md` §5).
**Módulo produtor:** Ingestão.
**Módulos consumidores potenciais:** Classificação.
**Efeito esperado:** dispara a tentativa de classificação do(s) Arquivo(s)
anexado(s) — sem acoplamento obrigatório: Classificação decide quando reagir.
**Idempotência:** chave natural = Message ID (ou hash do payload de entrada,
quando o canal não fornecer Message ID) — reentrega do mesmo item não deve
gerar um segundo `ItemIngestaoRecebido` com `event_id` novo representando o
mesmo fato; deve ser reconhecida como reentrega técnica, não fato novo.
**Auditoria:** canal de origem, remetente (quando aplicável), timestamp de
chegada, resultado da validação básica.
**Correspondência no legado:** criação de registro em `Emails Savian`
(`apps_script_email_intake.gs`, função `processarEmails`).
**Riscos de migração:** as funções de backfill histórico do Apps Script
(`fatiarFGTS_Maio`, etc. — `MAGNATA_OS_ENTIDADES.md` §10, item 8) não passam
por um fluxo único de ingestão — qualquer emissão retroativa deste evento
para dados históricos precisa reconhecer que a ingestão real não seguiu este
vocabulário.
**Decisões e entidades relacionadas:** Item de Ingestão (Modelo Conceitual
Documental, `MAGNATA_OS_DECISOES_ENTIDADES.md`).

**Demais eventos da categoria (registro condensado):**

| Nome | Status | Definição | Entidade | Momento de emissão | Não emitir quando |
|---|---|---|---|---|---|
| `ItemIngestaoValidado` | CANDIDATO | item passou validação básica (remetente confiável, formato reconhecível) | Item de Ingestão | após checagem de remetente/formato, antes da classificação | quando a validação é trivial/instantânea a ponto de não haver fato distinto de `ItemIngestaoRecebido` a registrar — decisão de manter como evento separado depende de a validação ter lógica não trivial |
| `ItemIngestaoRejeitado` | CANÔNICO | item chegou mas foi recusado (remetente não confiável, formato inválido) | Item de Ingestão | no momento da rejeição, antes de persistir como Item de Ingestão pleno | quando o item só está incompleto mas ainda em processamento (não é rejeição, é estado intermediário) |
| `ArquivoExtraido` | CANÔNICO | um Arquivo foi extraído/anexado a partir de um Item de Ingestão | Arquivo | quando o anexo físico é persistido e vinculado ao Item de Ingestão | quando o "Arquivo" ainda é só um ponteiro/URL não baixado com sucesso |
| `LoteIngestaoIdentificado` | CANDIDATO | heurística de janela de tempo (±20s, Kit de Admissão) identificou que vários Arquivos recebidos pertencem ao mesmo lote | (transversal — Item de Ingestão/Documento) | quando a heurística de agrupamento conclui, antes da criação dos Documentos | quando só 1 Arquivo chegou (não há "lote" de fato) |
| `IngestaoFalhou` | CANÔNICO | a ingestão de um item falhou por erro técnico (não por rejeição de regra de negócio) | Item de Ingestão | no momento em que o pipeline de ingestão lança erro não tratável | quando o "erro" é, na verdade, uma rejeição de regra de negócio (`ItemIngestaoRejeitado`) — as duas causas não devem compartilhar o mesmo evento |

### B. Classificação e processamento documental

**Avaliação crítica prévia** (pedida explicitamente pelo comando): nomes
terminados em "Solicitada" só viram evento quando representam a criação de
uma entidade própria (ex.: uma Solicitação de Assinatura nascendo — §I), não
quando são só o registro de uma intenção técnica. Por isso
`ArquivoClassificacaoSolicitada` é **rejeitado** abaixo — duplica o comando
`ClassificarArquivo` (§7) sem representar um fato novo.

#### ArquivoClassificado `[TEMPLATE COMPLETO]`

**Definição:** um Arquivo foi analisado e recebeu Categoria Documental,
Competência e (quando aplicável) vínculo com Cliente/Colaborador, com
confiança suficiente para seguir o fluxo automático.
**Entidade principal:** Documento (o Arquivo é classificado, mas o fato
relevante de negócio é a existência/atualização do Documento resultante).
**Momento de emissão:** quando a classificação conclui com Confiança
suficiente para não exigir Revisão Manual.
**Não emitir quando:** a classificação conclui com confiança insuficiente
(ver `ArquivoClassificacaoInconclusiva`); a classificação ainda não rodou.
**Dados mínimos:** identificador do Arquivo, Tipo Documental, Competência
(estrutura `MENSAL`/`PERIODO`/`NAO_APLICAVEL`), Cliente (se identificado),
Colaborador/Vínculo (se identificado), nível de confiança.
**Dados opcionais:** sinais usados na classificação (CNPJ encontrado, CPF
encontrado, assunto do e-mail).
**Estado anterior esperado:** `Processando` (Documento).
**Estado resultante:** `Concluído` (Documento) — ou o Documento é criado
neste mesmo fluxo, ver `DocumentoCriado`.
**Módulo produtor:** Classificação.
**Módulos consumidores potenciais:** Distribuição, Assinatura (para avaliar
DEC-ENT-022), Auditoria.
**Efeito esperado:** pode disparar avaliação de exigência de assinatura
(Tipo Documental) e elegibilidade para Distribuição — sem acoplamento
obrigatório.
**Idempotência:** reclassificar o mesmo Arquivo (hash idêntico) não deve
gerar um novo Documento — deve ser reconhecido como o mesmo fato, com
`causation_id` apontando para a tentativa original quando for reprocessamento
técnico.
**Auditoria:** sinais de classificação usados, nível de confiança, ator
(sistema).
**Correspondência no legado:** gravação de `Processar Arquivos` com `Status
= Concluído` e `F_PROC_TIPO_DOC` preenchido (`app.py`, funções de
classificação via `pdfplumber`/`pypdf`).
**Riscos de migração:** o legado mistura este fato com a criação do
registro de ingestão (`Processar Arquivos` cobre as duas fases,
`MAGNATA_OS_ENTIDADES.md` achado crítico #1 do diagnóstico original) — migrar
exige separar os dois eventos (`DocumentoCriado` × `ArquivoClassificado`) de
um único registro técnico hoje.
**Decisões e entidades relacionadas:** DEC-ENT-004, DEC-ENT-022; entidades
Documento, Tipo Documental.

#### DocumentoCriado `[TEMPLATE COMPLETO]`

**Definição:** um novo Documento passou a existir como unidade lógica de
negócio.
**Entidade principal:** Documento.
**Momento de emissão:** no instante em que o Documento é persistido pela
primeira vez — tipicamente junto com (ou imediatamente após) a
classificação bem-sucedida do Arquivo que o originou.
**Não emitir quando:** um Arquivo novo é vinculado a um Documento **já
existente** (ver `ArquivoVinculadoAoDocumento` — isso não cria um novo
Documento); um Documento é só derivado de outro por regra de negócio (ver
`DocumentoDerivadoCriado`, que é mais específico).
**Dados mínimos:** identificador do Documento, Tipo Documental, Competência,
Item de Ingestão de origem.
**Dados opcionais:** Cliente, Colaborador/Vínculo, se já identificados neste
momento.
**Estado anterior esperado:** não aplicável.
**Estado resultante:** `Pendente` ou `Processando` (a depender de o
Documento nascer já classificado ou não).
**Módulo produtor:** Classificação.
**Módulos consumidores potenciais:** Distribuição, Assinatura, Auditoria.
**Efeito esperado:** nenhum efeito colateral obrigatório — é o fato de
existência que outros módulos podem escolher observar.
**Idempotência:** um Item de Ingestão que gera múltiplos Documentos (Kit de
Admissão) emite um `DocumentoCriado` por Documento resultante, não um só;
reprocessamento do mesmo Item de Ingestão não deve duplicar Documentos já
criados (chave: hash do Arquivo de origem + Tipo Documental).
**Auditoria:** Item de Ingestão de origem, ator (sistema).
**Correspondência no legado:** criação de registro em `Processar Arquivos`.
**Riscos de migração:** mesmo risco de `ArquivoClassificado` — hoje é o
mesmo registro técnico que cobre ingestão e classificação.
**Decisões e entidades relacionadas:** DEC-ENT-004, DEC-ENT-006,
DEC-ENT-015, Modelo Conceitual Documental.

#### ArquivoVinculadoAoDocumento `[TEMPLATE COMPLETO]`

**Definição:** um Arquivo (original, derivado, corrigido ou assinado) foi
associado a um Documento.
**Entidade principal:** Arquivo.
**Momento de emissão:** no instante em que o vínculo Arquivo→Documento é
persistido.
**Não emitir quando:** o Arquivo ainda está solto num Item de Ingestão, sem
Documento identificado (`MAGNATA_OS_DECISOES_ENTIDADES.md`, DEC-ENT-015 —
Arquivo não classificado permanece em Item de Ingestão).
**Dados mínimos:** identificador do Arquivo, identificador do Documento,
papel do Arquivo (original/derivado/corrigido/assinado).
**Dados opcionais:** Arquivo de origem, quando derivado.
**Estado anterior esperado:** não aplicável (Arquivo não tem vocabulário de
estado formal além de vigência).
**Estado resultante:** o Arquivo passa a ter `situação de vigência`
definida (ver `ArquivoMarcadoComoVigente`).
**Módulo produtor:** Classificação (vínculo inicial) ou Assinatura (Arquivo
Assinado — ver `ArquivoAssinadoGerado`, mais específico).
**Módulos consumidores potenciais:** Distribuição, Auditoria.
**Efeito esperado:** nenhum obrigatório.
**Idempotência:** vincular o mesmo Arquivo (mesmo hash) ao mesmo Documento
mais de uma vez não deve gerar vínculos duplicados.
**Auditoria:** ator/mecanismo que gerou o vínculo.
**Correspondência no legado:** campo `Arquivos 2` (`F_PROC_ARQUIVOS2`) em
`Processar Arquivos`, e vínculo direto em `Arquivos.Emails Savian`.
**Riscos de migração:** o legado não tem conceito de "papel do Arquivo"
(original/derivado/corrigido/assinado) — é uma dimensão nova introduzida por
DEC-ENT-017.
**Decisões e entidades relacionadas:** DEC-ENT-015, DEC-ENT-017.

#### DocumentoProcessamentoFalhou `[TEMPLATE COMPLETO]`

**Definição:** o processamento de um Documento (extração, classificação ou
etapa correlata) falhou de forma não recuperável automaticamente.
**Entidade principal:** Documento.
**Momento de emissão:** quando o pipeline de processamento lança um erro que
não é uma decisão de negócio (Revisão Manual é decisão de negócio, não
falha).
**Não emitir quando:** o resultado é Confiança Baixa levando a Revisão
Manual — isso é `ArquivoClassificacaoInconclusiva` ou `PendenciaDocumentalCriada`,
não uma falha técnica.
**Dados mínimos:** ver §8 (Eventos de falha) — categoria, código, mensagem
seguranda, etapa, possibilidade de retry, entidade afetada, tentativa,
correlation ID.
**Dados opcionais:** stack trace interno (nunca exposto fora de log técnico
protegido).
**Estado anterior esperado:** `Processando`.
**Estado resultante:** `Erro`.
**Módulo produtor:** Classificação (ou o módulo específico da etapa que
falhou).
**Módulos consumidores potenciais:** Auditoria, operação humana (retomada
manual).
**Efeito esperado:** nenhum automático obrigatório — decisão de retry ou
intervenção manual não é automática por definição de negócio.
**Idempotência:** falhas repetidas da mesma tentativa técnica não geram um
novo fato de negócio a cada re-tentativa dentro da mesma operação — ver §9.
**Auditoria:** obrigatória por definição — este é, por natureza, um evento
de auditoria de falha.
**Correspondência no legado:** `_atualizar_status_processar(proc_id, 'Erro')`
(`app.py`, múltiplas ocorrências), e o hotfix que grava códigos técnicos em
`F_PROC_TIPO_DOC` (`UPLOAD_FAILED`, `PROCESSING_ERROR` — achado crítico #3
do diagnóstico de entidades).
**Riscos de migração:** o legado mistura erro técnico com Tipo Documental —
migrar exige separar os dois campos, não só criar o evento.
**Decisões e entidades relacionadas:** débito conhecido #3
(`MAGNATA_OS_ARQUITETURA.md` §8); Documento.

**Demais eventos da categoria (registro condensado):**

| Nome | Status | Definição | Entidade | Momento de emissão | Não emitir quando |
|---|---|---|---|---|---|
| `ArquivoClassificacaoSolicitada` | **REJEITADO** | — | — | — | Duplica o comando `ClassificarArquivo` — "solicitada" aqui é intenção, não fato; não representa criação de entidade própria |
| `ArquivoClassificacaoInconclusiva` | CANÔNICO | classificação concluiu com Confiança Baixa, sem Cliente/Colaborador identificado com segurança | Documento | ao fim da tentativa de classificação, quando o resultado não atinge o piso de confiança | quando a classificação simplesmente ainda não rodou |
| `DocumentoIdentificado` | CANDIDATO | Cliente e/ou Colaborador do Documento foram determinados (pode ocorrer depois da criação/classificação inicial) | Documento | quando a resolução de Cliente/Colaborador conclui, se distinta no tempo da classificação de Tipo Documental | quando identificação e classificação ocorrem no mesmo instante — nesse caso é redundante com `ArquivoClassificado`, avaliar fusão futura |
| `DocumentoAtualizado` | **REJEITADO** | — | — | — | Nome genérico proibido pela regra de nomenclatura (§1) — qualquer fato de atualização precisa de nome específico (`ArquivoVinculadoAoDocumento`, `ArquivoVersaoCriada`, etc.) |
| `DocumentoDerivadoCriado` | CANÔNICO | um novo Documento foi criado a partir de outro por mudança material de conteúdo/titularidade/competência | Documento | quando a regra de derivação (DEC-ENT-006/DEC-ENT-015) determina que o caso exige novo Documento, não só novo Arquivo | quando a mudança preserva o mesmo significado de negócio — nesse caso é só `ArquivoVersaoCriada` |
| `ArquivoVersaoCriada` | CANÔNICO | uma nova versão de Arquivo foi criada dentro do mesmo Documento (correção, por exemplo) | Arquivo | na criação do novo Arquivo vinculado ao anterior | quando é o primeiro Arquivo do Documento (não há "nova versão" sem uma anterior) |
| `ArquivoMarcadoComoVigente` | CANÔNICO | um Arquivo passou a ser a versão vigente do Documento, superando o anterior | Arquivo | quando a vigência é reatribuída | quando é a primeira vigência (coincide com a criação do Arquivo — nesse caso não há transição a marcar) |
| `DocumentoProcessamentoIniciado` | CANDIDATO | processamento do Documento começou (extração de texto, classificação) | Documento | ao iniciar o processamento assíncrono | quando o processamento é síncrono e instantâneo demais para justificar dois eventos (Iniciado + Concluído) separados |
| `DocumentoProcessamentoConcluido` | CANÔNICO | processamento do Documento terminou com sucesso, independente do nível de confiança atingido | Documento | ao fim do pipeline de processamento, sucesso técnico (não é sinônimo de "sem necessidade de revisão") | quando o processamento falhou tecnicamente (`DocumentoProcessamentoFalhou`) |
| `PendenciaDocumentalCriada` | CANÔNICO | uma Pendência Documental foi aberta para um Documento | Pendência Documental | quando Confiança Baixa ou ausência de Cliente/Colaborador leva a Revisão Manual | quando a pendência é, na verdade, um Alerta de Ponto (tabela compartilhada hoje, mas fato de negócio distinto — `MAGNATA_OS_ENTIDADES.md` achado crítico #2) |
| `PendenciaDocumentalResolvida` | CANÔNICO | uma Pendência Documental foi resolvida por intervenção humana | Pendência Documental | quando o Status muda de `Pendente` para resolvido | quando a pendência é cancelada sem resolução real (avaliar se merece nome próprio, ex. `PendenciaDocumentalCancelada`, ainda não decidido) |

### C. Colaborador, Vínculo e Alocação

**Vocabulário único aplicado** (pedido explícito do comando): eventos que
duplicariam o mesmo fato com nome alternativo são rejeitados aqui, não
mantidos como "sinônimos aceitáveis".

| Nome | Status | Definição | Entidade | Momento de emissão | Não emitir quando |
|---|---|---|---|---|---|
| `ColaboradorCadastrado` | CANÔNICO | uma nova identidade de Colaborador foi criada | Colaborador | na primeira persistência do registro de Colaborador | quando é só um novo Vínculo para um Colaborador já existente (`VinculoTrabalhistaCriado`) |
| `ColaboradorIdentificado` | CANDIDATO | um Colaborador foi reconhecido (por CPF ou, em fallback frágil, por nome) durante classificação de um Documento | Colaborador | no momento do casamento CPF↔Colaborador | quando o casamento falha e cai em Pendência — possível sobreposição com `DocumentoIdentificado` (§B), resolver na revisão de contratos de dados |
| `VinculoTrabalhistaCriado` | CANÔNICO | um novo Vínculo Trabalhista foi aberto para um Colaborador (admissão ou readmissão) | Vínculo Trabalhista | na admissão | quando é só uma correção cadastral do Colaborador, sem novo vínculo |
| `VinculoTrabalhistaEncerrado` | CANÔNICO | um Vínculo Trabalhista foi encerrado (desligamento) | Vínculo Trabalhista | no desligamento | quando é só uma Alocação que termina, sem encerrar o Vínculo |
| `AlocacaoCriada` | CANÔNICO | uma Alocação foi criada, ligando um Vínculo a um Posto de Trabalho por um período | Alocação | no início da alocação | quando é só continuidade da mesma alocação já vigente |
| `AlocacaoAlterada` | **REJEITADO** | — | — | — | Nome genérico proibido (§1, "Alterada" ≈ "Atualizado"); qualquer alteração real deve ser modelada como `AlocacaoEncerrada` + nova `AlocacaoCriada`, preservando histórico |
| `AlocacaoEncerrada` | CANÔNICO | uma Alocação terminou (fim de período, transferência, fim de cobertura) | Alocação | no fim do período de alocação | quando é o Vínculo inteiro que encerra (`VinculoTrabalhistaEncerrado`, que é o fato mais amplo) |
| `ColaboradorAlocadoAoPosto` | **REJEITADO** | — | — | — | Duplica `AlocacaoCriada` com outro nome — vocabulário único escolhido: `AlocacaoCriada` |
| `ColaboradorRemovidoDoPosto` | **REJEITADO** | — | — | — | Duplica `AlocacaoEncerrada` — mesma razão acima |

### D. Distribuição

#### DistribuicaoCriada `[TEMPLATE COMPLETO]`

**Definição:** uma Distribuição foi criada, definindo a intenção de entregar
um ou mais Documentos/Arquivos a um ou mais destinatários.
**Entidade principal:** Distribuição.
**Momento de emissão:** quando finalidade, Documentos/Arquivos, destinatários
e condições de conclusão estão definidos e a Distribuição é persistida.
**Não emitir quando:** só um Envio individual está sendo criado dentro de
uma Distribuição já existente (`EnvioCriado`).
**Dados mínimos:** identificador da Distribuição, finalidade, Documento(s)/
Arquivo(s), destinatário(s), canais permitidos, condições de conclusão.
**Dados opcionais:** competência, regras de agrupamento.
**Estado anterior esperado:** não aplicável.
**Estado resultante:** Distribuição pronta para gerar Envios.
**Módulo produtor:** Distribuição.
**Módulos consumidores potenciais:** Envio (para gerar os Envios
correspondentes).
**Efeito esperado:** tipicamente segue-se a criação de N Envios — mas isso é
efeito, não parte do mesmo fato.
**Idempotência:** criar a mesma Distribuição duas vezes (mesmo Documento,
mesma finalidade, mesmo conjunto de destinatários) por retry técnico não
deve gerar Distribuições duplicadas.
**Auditoria:** ator/sistema solicitante, Documentos envolvidos.
**Correspondência no legado:** hoje inexistente como fato isolado — está
embutido na criação de registros em `Envios de Documentos` (rotas
`gerar-fila-envios*`).
**Riscos de migração:** migrar exige separar, de um único fluxo hoje, o que
é "decisão de distribuir" do que é "cada entrega individual" — os 4 pares de
rota fila+disparo por canal precisam convergir para este modelo.
**Decisões e entidades relacionadas:** DEC-ENT-013 (Modelo Conceitual de
Distribuição e Entrega).

**Demais eventos da categoria (registro condensado):**

| Nome | Status | Definição | Entidade | Momento de emissão | Não emitir quando |
|---|---|---|---|---|---|
| `DocumentoAdicionadoADistribuicao` | CANDIDATO | um Documento adicional foi incluído numa Distribuição já criada | Distribuição | quando a Distribuição é construída incrementalmente, não atomicamente | quando todos os Documentos já são definidos no momento de `DistribuicaoCriada` — nesse caso este evento é redundante |
| `DestinatarioAdicionadoADistribuicao` | CANDIDATO | um destinatário adicional foi incluído | Distribuição | idem acima, para destinatários | mesma ressalva acima |
| `DistribuicaoPronta` | CANDIDATO | todos os elementos necessários (Documentos, destinatários, canais) estão definidos e a Distribuição pode gerar Envios | Distribuição | quando a construção incremental conclui | quando a Distribuição já nasce completa em `DistribuicaoCriada` (torna este evento redundante) |
| `DistribuicaoIniciada` | CANDIDATO | a geração de Envios a partir da Distribuição começou | Distribuição | ao iniciar o disparo dos Envios | quando "iniciada" e "criada" coincidem no tempo |
| `DistribuicaoConcluida` | CANÔNICO | as condições de conclusão definidas pela própria Distribuição foram satisfeitas | Distribuição | quando a política de conclusão (definida na criação) é atendida por todos os Envios relevantes — **nunca** apenas porque um Envio concluiu (DEC-ENT-013) | quando só 1 de N Envios concluiu, sob política que exige todos |
| `DistribuicaoFalhou` | CANÔNICO | a Distribuição não pôde ser concluída dentro das condições esperadas (ex.: todos os Envios falharam definitivamente) | Distribuição | quando a política de conclusão se torna impossível de satisfazer | quando só parte dos Envios falhou mas ainda há caminho para conclusão |
| `DistribuicaoCancelada` | CANÔNICO | a Distribuição foi cancelada antes de concluir, por decisão operacional | Distribuição | no cancelamento explícito | quando é falha, não cancelamento deliberado (`DistribuicaoFalhou`) |

### E. Envio

**Nota explícita pedida pelo comando:** `EnvioConcluido` **não é criado**
neste catálogo. Não há uma única condição de "concluído" para Envio — o que
conta como conclusão depende do nível de evidência exigido pela Distribuição
de origem (DEC-ENT-009). Em vez de um evento ambíguo, o catálogo usa os
eventos específicos por nível de evidência (`EnvioEntregue`, `EnvioLido`,
`EnvioConfirmadoPeloDestinatario`) — quem precisar saber "este Envio está
concluído para os fins da minha Distribuição" consulta qual desses eventos
já ocorreu, à luz da política daquela Distribuição especificamente.

#### EnvioCriado `[TEMPLATE COMPLETO]`

**Definição:** um Envio foi criado, representando a intenção concreta de
entregar por um canal a um destinatário específico.
**Entidade principal:** Envio.
**Momento de emissão:** quando o par Destinatário+Canal é definido dentro de
uma Distribuição e o registro de Envio é persistido.
**Não emitir quando:** é uma nova Tentativa dentro do mesmo Envio (não um
Envio novo); é um Reenvio (ver `ReenvioCriado`, que é mais específico e
sempre acompanhado de `EnvioCriado` também, com `causation_id` apontando
para o Envio anterior).
**Dados mínimos:** identificador do Envio, Distribuição de origem,
Destinatário, endereço a utilizar, Canal.
**Dados opcionais:** provedor técnico já definido neste momento.
**Estado anterior esperado:** não aplicável.
**Estado resultante:** `PLANEJADO`.
**Módulo produtor:** Distribuição.
**Módulos consumidores potenciais:** Envio (execução), Auditoria.
**Efeito esperado:** tipicamente segue-se `EnvioColocadoNaFila`.
**Idempotência:** mesma Distribuição + mesmo Destinatário + mesmo Canal não
deve gerar dois Envios por retry técnico da criação.
**Auditoria:** Distribuição de origem, Destinatário, Canal, ator solicitante.
**Correspondência no legado:** criação de registro em `Envios de
Documentos` com `Status = Preparando`.
**Riscos de migração:** os 4 fluxos de fila+disparo por canal criam esse
registro de formas ligeiramente diferentes hoje — convergir para um único
evento exige uniformizar os 4.
**Decisões e entidades relacionadas:** DEC-ENT-013, DEC-ENT-018, DEC-ENT-019.

#### EnvioColocadoNaFila `[TEMPLATE COMPLETO]`

**Definição:** um Envio está pronto e aguardando processamento/despacho.
**Entidade principal:** Envio.
**Momento de emissão:** quando o Envio entra na fila de processamento
(síncrono ou assíncrono).
**Não emitir quando:** o Envio é processado de forma síncrona e imediata a
ponto de não haver fila real distinguível de `EnvioCriado`.
**Dados mínimos:** identificador do Envio, timestamp de entrada na fila.
**Dados opcionais:** posição/prioridade na fila, se relevante.
**Estado anterior esperado:** `PLANEJADO`.
**Estado resultante:** `EM_FILA`.
**Módulo produtor:** Distribuição/Envio.
**Módulos consumidores potenciais:** o próprio worker de disparo (Celery, no
legado).
**Efeito esperado:** processamento assíncrono subsequente.
**Idempotência:** reentrada na fila por retry técnico não deve ser
confundida com uma nova tentativa deliberada — ver Tentativa de Envio (§F).
**Auditoria:** timestamp de entrada na fila.
**Correspondência no legado:** enfileiramento via Celery
(`tarefas_processar_pdf.py`, `celery_app.py`).
**Riscos de migração:** baixo — já existe mecanismo de fila real (Celery/
Redis) no legado.
**Decisões e entidades relacionadas:** DEC-ENT-020 (estado `EM_FILA`).

#### EnvioAceitoPeloProvedor `[TEMPLATE COMPLETO]`

**Definição:** o provedor técnico (Evolution API, SMTP, etc.) aceitou a
solicitação de envio sem erro imediato.
**Entidade principal:** Envio.
**Momento de emissão:** na resposta de aceitação do provedor — **nunca**
apenas por causa de um HTTP 200/201 de infraestrutura (§9, princípio de
evidência, DEC-ENT-009) sem que o corpo da resposta confirme aceitação real.
**Não emitir quando:** o provedor retorna erro, mesmo com HTTP 200 (alguns
provedores retornam erro de negócio dentro de um 200); a chamada ainda não
retornou.
**Dados mínimos:** identificador do Envio, identificador externo do
provedor (quando existente), timestamp.
**Dados opcionais:** metadado bruto da resposta do provedor.
**Estado anterior esperado:** `EM_PROCESSAMENTO`.
**Estado resultante:** `ACEITO_PELO_PROVEDOR`.
**Módulo produtor:** Envio (integração com o provedor).
**Módulos consumidores potenciais:** Auditoria, Distribuição (avaliação de
conclusão, se a política exigir só este nível).
**Efeito esperado:** nenhum obrigatório.
**Idempotência:** uma única aceitação por Tentativa — aceitação duplicada
por retry de leitura de resposta não deve gerar dois eventos representando
o mesmo fato.
**Auditoria:** identificador externo, provedor, timestamp.
**Correspondência no legado:** resposta HTTP da Evolution API/SMTP dentro
das rotas `disparar-fila*`.
**Riscos de migração:** o legado hoje tende a tratar "chamada não lançou
exceção" como sinônimo de sucesso — esse evento exige checar o conteúdo da
resposta, não só a ausência de erro de transporte.
**Decisões e entidades relacionadas:** DEC-ENT-009 (nível
`ACEITO_PELO_PROVEDOR`), DEC-ENT-019 (Canal × provedor).

#### EnvioEntregue `[TEMPLATE COMPLETO]`

**Definição:** existe confirmação de entrega ao servidor, dispositivo ou
conta destinatária — não apenas aceitação do provedor.
**Entidade principal:** Envio.
**Momento de emissão:** quando o provedor (ou canal) confirma entrega
efetiva — ex.: webhook de confirmação de entrega do WhatsApp.
**Não emitir quando:** só há aceitação do provedor, sem confirmação de
entrega (`EnvioAceitoPeloProvedor`); a "entrega" é, na verdade, leitura
(`EnvioLido`, nível mais alto — não emitir os dois como se fossem o mesmo
fato quando só a leitura foi confirmada e a entrega não foi observada à
parte).
**Dados mínimos:** identificador do Envio, timestamp de entrega, origem do
sinal de confirmação.
**Dados opcionais:** metadado bruto do webhook de confirmação.
**Estado anterior esperado:** `ENVIADO`.
**Estado resultante:** `ENTREGUE`.
**Módulo produtor:** Envio (integração — recepção de webhook/callback).
**Módulos consumidores potenciais:** Distribuição (avaliação de conclusão),
Auditoria.
**Efeito esperado:** pode satisfazer a condição de conclusão de uma
Distribuição cuja finalidade exige só entrega (não leitura).
**Idempotência:** confirmações de entrega duplicadas (reentrega de webhook)
não devem gerar dois fatos de negócio distintos.
**Auditoria:** origem do sinal, timestamp.
**Correspondência no legado:** hoje não há distinção clara entre "Enviado"
e "Entregue" no vocabulário de `Status` do Envio (`app.py:123` — só
`Preparando/Enviado/Concluído/Lido`).
**Riscos de migração:** o legado pode não ter, para todo canal, um sinal
técnico real de "entregue" distinto de "aceito pelo provedor" — nesse caso o
evento simplesmente não deve ser inventado (DEC-ENT-009: "canais que não
fornecem determinado nível de evidência não devem inventá-lo").
**Decisões e entidades relacionadas:** DEC-ENT-009 (nível `ENTREGUE`).

#### EnvioFalhaDefinitivaRegistrada `[TEMPLATE COMPLETO]`

**Definição:** o Envio falhou de forma definitiva — não há mais tentativa
técnica automática a fazer.
**Entidade principal:** Envio.
**Momento de emissão:** quando o número máximo de Tentativas é atingido, ou
o provedor retorna um erro reconhecido como não-recuperável (ex.: número de
WhatsApp inválido).
**Não emitir quando:** a falha é temporária e ainda há Tentativas
disponíveis (`EnvioFalhaTemporariaRegistrada`, mais adequado).
**Dados mínimos:** ver §8 — categoria, código, mensagem segura, entidade
afetada, tentativa final, correlation ID.
**Dados opcionais:** sugestão de ação corretiva (ex.: "verificar número de
telefone cadastrado").
**Estado anterior esperado:** `FALHA_TEMPORARIA` (após esgotar tentativas)
ou diretamente `EM_PROCESSAMENTO`/`ACEITO_PELO_PROVEDOR` (falha
não-recuperável imediata).
**Estado resultante:** `FALHA_DEFINITIVA`.
**Módulo produtor:** Envio.
**Módulos consumidores potenciais:** Distribuição (avaliação de conclusão —
DEC-ENT-013 diz que falha de 1 Envio pode ou não impedir conclusão, conforme
política), Auditoria, operação humana (correção de cadastro + Reenvio).
**Efeito esperado:** nenhum automático — Reenvio é decisão operacional
(DEC-ENT-007), não consequência automática.
**Idempotência:** uma falha definitiva é um fato terminal — não deve ser
reemitida para o mesmo Envio.
**Auditoria:** obrigatória por natureza (é evento de falha).
**Correspondência no legado:** `_marcar_envio_status(rec['id'], 'Erro',
erro=str(exc))` (`app.py`, múltiplas ocorrências).
**Riscos de migração:** o legado não distingue falha temporária de
definitiva no vocabulário atual (`'Erro'` é único) — migrar exige essa
distinção antes de mapear o evento.
**Decisões e entidades relacionadas:** DEC-ENT-007, DEC-ENT-020 (estado
`FALHA_DEFINITIVA`).

**Demais eventos da categoria (registro condensado):**

| Nome | Status | Definição | Entidade | Momento de emissão | Não emitir quando |
|---|---|---|---|---|---|
| `EnvioProcessamentoIniciado` | CANDIDATO | o processamento técnico do Envio (chamada ao provedor) começou | Envio | ao sair da fila e iniciar a chamada | quando a fila e o processamento são o mesmo instante técnico |
| `EnvioDespachadoPeloProvedor` | CANÔNICO | o provedor informou que despachou/processou a mensagem (nível intermediário entre aceitar e entregar) | Envio | quando o provedor sinaliza despacho, distinto de mera aceitação | quando o provedor não distingue "aceitou" de "despachou" (nesse caso, usar só `EnvioAceitoPeloProvedor`) |
| `EnvioLido` | CANÔNICO | existe evidência de leitura/abertura pelo destinatário | Envio | na confirmação de leitura (ex.: link de recibo acessado) | quando só há entrega confirmada, sem sinal de leitura |
| `EnvioConfirmadoPeloDestinatario` | CANÔNICO | houve ação inequívoca do destinatário (resposta, confirmação, download autenticado) | Envio | na confirmação ativa do destinatário | quando é só leitura passiva (abrir o link), sem ação adicional — isso é `EnvioLido` |
| `EnvioFalhaTemporariaRegistrada` | CANÔNICO | uma falha ocorreu mas ainda há Tentativas disponíveis | Envio | ao falhar uma Tentativa, com Tentativas restantes | quando é a última tentativa disponível (`EnvioFalhaDefinitivaRegistrada`) |
| `EnvioCancelado` | CANÔNICO | o Envio foi cancelado por decisão operacional antes de concluir | Envio | no cancelamento explícito | quando é falha, não cancelamento deliberado |
| `ReenvioCriado` | CANÔNICO | uma nova decisão operacional de reenviar gerou um novo Envio, referenciando o anterior | Envio | na criação do novo Envio motivado por reenvio deliberado | quando é retry técnico da mesma tentativa (`TentativaEnvio*`, §F) — nunca confundir os dois (DEC-ENT-007) |

### F. Tentativa de Envio

**Distinção pedida pelo comando** entre evento de domínio, evento de
integração e log técnico: dos 4 nomes propostos, só um justifica tratamento
de evento de domínio pleno — os demais são eventos de integração (relevantes
para causalidade/auditoria técnica, mas não fatos de negócio que outros
módulos de negócio devam consumir).

#### TentativaEnvioFalhou `[TEMPLATE COMPLETO]`

**Definição:** uma execução técnica específica (dentro de um Envio) falhou.
**Entidade principal:** Tentativa de Envio.
**Momento de emissão:** ao falhar uma chamada técnica ao provedor, dentro de
um Envio já existente.
**Não emitir quando:** é a criação de um novo Envio (Reenvio) — isso não é
falha de Tentativa, é decisão operacional nova (DEC-ENT-007).
**Dados mínimos:** identificador da Tentativa, Envio (relação), timestamp,
erro técnico (categoria/código).
**Dados opcionais:** payload/resposta bruta do provedor (protegida, sem
dado sensível).
**Estado anterior esperado:** não aplicável (Tentativa não tem estado
próprio que transiciona — §2, `MAGNATA_OS_ENTIDADES.md`).
**Estado resultante:** não aplicável a Tentativa; pode levar o Envio a
`FALHA_TEMPORARIA` ou `FALHA_DEFINITIVA`, conforme tentativas restantes.
**Módulo produtor:** Envio (execução técnica).
**Módulos consumidores potenciais:** o próprio mecanismo de retry (Celery);
Auditoria.
**Efeito esperado:** pode disparar nova Tentativa automática (se dentro do
limite) ou `EnvioFalhaDefinitivaRegistrada` (se esgotado).
**Idempotência:** cada Tentativa tem seu próprio `event_id` — não há
duplicidade a evitar aqui, cada execução técnica é, por definição, um fato
novo (mesmo que o resultado se repita).
**Auditoria:** erro técnico, provedor, tentativa número N.
**Correspondência no legado:** contador `Tentativa` incrementado em
`Envios de Documentos`, sem registro individual por tentativa hoje.
**Riscos de migração:** o legado só guarda o número final, não o histórico
por tentativa — migrar exige criar o registro individual que hoje não
existe.
**Decisões e entidades relacionadas:** DEC-ENT-007, DEC-ENT-021.

**Demais eventos da categoria (registro condensado):**

| Nome | Classificação | Status | Definição | Não emitir quando |
|---|---|---|---|---|
| `TentativaEnvioIniciada` | EVENTO DE INTEGRAÇÃO | CANDIDATO | início de uma execução técnica específica | quando não há valor de auditoria distinto de simplesmente observar `EnvioProcessamentoIniciado` |
| `TentativaEnvioAceitaPeloProvedor` | EVENTO DE INTEGRAÇÃO | CANDIDATO | a Tentativa específica foi aceita — nível técnico que causa `EnvioAceitoPeloProvedor` | quando não há mais de uma Tentativa em jogo (nesse caso é redundante com o evento do Envio) |
| `TentativaEnvioFinalizada` | EVENTO DE INTEGRAÇÃO | CANDIDATO | a execução técnica terminou (sucesso ou falha), fechando o registro da Tentativa | quando o resultado já é coberto por `TentativaEnvioFalhou` ou pelo evento de sucesso do Envio |

### G. Evidências de Entrega

**Explicação exigida pelo comando:** dos 4 nomes propostos, 3 duplicam
eventos já definidos na categoria E (Envio) — pertencem ao ciclo de vida do
**Envio**, não precisam de vocabulário próprio. Só 1 nome tem valor
diferencial: o registro do próprio fato de "uma evidência chegou", que
pertence à futura entidade/registro **Evidência de Entrega** (candidata,
`MAGNATA_OS_ENTIDADES.md` §5), não ao Envio em si.

| Nome | Status | Definição | Pertence a | Justificativa |
|---|---|---|---|---|
| `EvidenciaEntregaRegistrada` | CANDIDATO | um sinal de evidência (de qualquer nível, DEC-ENT-009) foi recebido e registrado | Evidência de Entrega (candidata) | é o evento "meta" de registrar a chegada de qualquer evidência — distinto de qual nível especificamente foi atingido |
| `EntregaConfirmada` | **REJEITADO** | — | Envio | duplica `EnvioEntregue` (§E) — vocabulário único escolhido: `EnvioEntregue` |
| `LeituraConfirmada` | **REJEITADO** | — | Envio | duplica `EnvioLido` (§E) |
| `ConfirmacaoDestinatarioRegistrada` | **REJEITADO** | — | Envio | duplica `EnvioConfirmadoPeloDestinatario` (§E) |

### H. Aplicabilidade da Assinatura

**Avaliação crítica exigida pelo comando:** os 3 nomes propostos são
**resultado de uma regra aplicada** (Tipo Documental determinando exigência
de assinatura, DEC-ENT-022), não fatos de negócio independentes que
justifiquem emissão própria de evento. `MAGNATA_OS_ENTIDADES.md` §5 já
registra Tipo Documental como **estrutura de valor**, sem ciclo de eventos
próprio (§13 deste documento reforça isso) — é coerente que a avaliação de
exigência de assinatura também não gere evento à parte.

| Nome | Status | Justificativa |
|---|---|---|
| `AssinaturaExigida` | **REJEITADO** | é a avaliação de um atributo (Tipo Documental/finalidade) sobre um Documento — o fato de negócio observável é a própria criação da Solicitação (`SolicitacaoAssinaturaCriada`, §I), que só ocorre quando a exigência existe |
| `AssinaturaDispensada` | **REJEITADO** | DEC-ENT-022 é explícito: "a ausência de necessidade de assinatura não representa pendência ou falha do Documento" — não há fato positivo a registrar quando nada acontece; a ausência de `SolicitacaoAssinaturaCriada` já é a informação |
| `PoliticaAssinaturaDeterminada` | **REJEITADO** | é configuração de Tipo Documental (estrutura de valor), não evento de instância — mudar a política de um Tipo Documental é uma alteração de configuração do sistema, não um fato de negócio por Documento |

### I. Solicitação de Assinatura

#### SolicitacaoAssinaturaCriada `[TEMPLATE COMPLETO]`

**Definição:** uma Solicitação de Assinatura foi criada para um Documento e
Arquivo específicos.
**Entidade principal:** Solicitação de Assinatura.
**Momento de emissão:** quando a exigência de assinatura (Tipo Documental/
finalidade/regra/obrigação contratual/decisão operacional — DEC-ENT-022) é
confirmada e a Solicitação é persistida, com Documento e Arquivo
referenciados por identificador canônico.
**Não emitir quando:** o Documento simplesmente foi enviado (envio nunca
cria Solicitação automaticamente, DEC-ENT-022); é uma nova Tentativa técnica
da mesma criação (idempotência, DEC-ENT-029) — nesse caso não há fato novo,
é a mesma Solicitação.
**Dados mínimos:** identificador da Solicitação, Documento (relação
canônica), Arquivo apresentado (relação canônica), política de conclusão
(`TODOS`/`QUALQUER_UM`/`QUANTIDADE_MINIMA`/`SEQUENCIAL`), lista de
Signatários previstos.
**Dados opcionais:** motivo/gatilho específico da exigência.
**Estado anterior esperado:** não aplicável.
**Estado resultante:** `RASCUNHO` ou `PREPARADA`.
**Módulo produtor:** Assinatura.
**Módulos consumidores potenciais:** Distribuição (para entregar o Link),
Auditoria.
**Efeito esperado:** tipicamente segue-se a criação de Signatários e Links —
sem acoplamento obrigatório.
**Idempotência:** retry técnico da criação não deve gerar uma segunda
Solicitação para o mesmo Documento — a chave de idempotência pertence à
operação de criação, não é o identificador canônico da Solicitação
(DEC-ENT-029). Uma nova Solicitação **deliberada** (ex.: documento
corrigido) é um fato novo, com `causation_id` referenciando a anterior e o
motivo — nunca tratada como "retry".
**Auditoria:** Documento, Arquivo, política de conclusão, ator solicitante.
**Correspondência no legado:** criação de registro em `Assinaturas`, rotas
`/assinatura/gerar`, `/assinatura/gerar-lote` — hoje com referência ao
Documento por **texto solto** (`F_ASS_PROCESSAR_ID`), não link canônico.
**Riscos de migração:** corrigir a referência textual solta é pré-requisito
para este evento carregar `entity_id` de Documento de forma confiável —
sem isso, o evento herdaria a fragilidade já identificada como achado
crítico #4.
**Decisões e entidades relacionadas:** DEC-ENT-008, DEC-ENT-014,
DEC-ENT-022, DEC-ENT-029.

#### SolicitacaoAssinaturaConcluida `[TEMPLATE COMPLETO]`

**Definição:** a política de conclusão da Solicitação foi satisfeita.
**Entidade principal:** Solicitação de Assinatura.
**Momento de emissão:** quando a condição definida pela política (`TODOS`
assinaram, `QUALQUER_UM` assinou, quantidade mínima atingida, ou sequência
completa) é satisfeita — **nunca** apenas porque uma Assinatura individual
ocorreu, se a política exige mais.
**Não emitir quando:** apenas uma Assinatura individual concluiu mas a
política ainda não foi satisfeita (`SolicitacaoAssinaturaParcialmenteAssinada`,
condensado abaixo); a Solicitação foi recusada ou expirou antes de a
política ser satisfeita.
**Dados mínimos:** identificador da Solicitação, lista de Assinaturas que
satisfizeram a política, timestamp.
**Dados opcionais:** Arquivo Assinado resultante, se já gerado neste
momento.
**Estado anterior esperado:** `EM_ASSINATURA` ou `PARCIALMENTE_ASSINADA`.
**Estado resultante:** `CONCLUIDA`.
**Módulo produtor:** Assinatura.
**Módulos consumidores potenciais:** Distribuição (se a finalidade da
Distribuição de origem exigia assinatura para concluir — DEC-ENT-022),
Auditoria.
**Efeito esperado:** pode disparar `ArquivoAssinadoGerado`, se ainda não
gerado.
**Idempotência:** a satisfação da política é um fato terminal — não deve
ser reemitida para a mesma Solicitação.
**Auditoria:** Assinaturas que satisfizeram a política, ator/sistema.
**Correspondência no legado:** hoje, conclusão de Assinatura atualiza
`Status` de **Processar Arquivos** para `'Assinado'` (`app.py:9896`) — este
é o achado crítico #1, que DEC-ENT-022 resolve como regra de negócio: este
evento afeta o estado da **Solicitação**, nunca do Documento.
**Riscos de migração:** qualquer consumidor legado que hoje espera
`Assinado` como estado de Documento precisa migrar para observar este
evento (ou o estado da Solicitação) em vez disso.
**Decisões e entidades relacionadas:** DEC-ENT-008, DEC-ENT-022,
DEC-ENT-027.

**Demais eventos da categoria (registro condensado):**

| Nome | Status | Definição | Momento de emissão | Não emitir quando |
|---|---|---|---|---|
| `SolicitacaoAssinaturaPreparada` | CANDIDATO | Solicitação estruturada (Signatários, política) mas ainda não enviada | quando a preparação conclui, antes do envio de Links | quando criação e preparação coincidem no tempo |
| `SolicitacaoAssinaturaEnviada` | CANÔNICO | o(s) Link(s)/convite(s) foram disponibilizados aos Signatários | quando o(s) Envio(s) do Link são criados — **não** significa que houve assinatura | quando ainda não há Link disponibilizado a nenhum Signatário |
| `SolicitacaoAssinaturaIniciada` | CANDIDATO | um Signatário começou a interagir (acessou o Link) | no primeiro acesso de qualquer Signatário | possível sobreposição com `LinkAssinaturaAcessado` (§J) — avaliar fusão na revisão de contratos |
| `SolicitacaoAssinaturaParcialmenteAssinada` | CANÔNICO | ao menos uma Assinatura válida existe, mas a política ainda não foi satisfeita | a cada Assinatura individual que não completa a política | quando a Assinatura completa a política (`SolicitacaoAssinaturaConcluida`) |
| `SolicitacaoAssinaturaRecusada` | CANÔNICO | um Signatário obrigatório recusou, inviabilizando a política | na recusa que torna a política impossível de satisfazer | quando a recusa não impede a política (ex.: `QUALQUER_UM` com outros Signatários ainda disponíveis) |
| `SolicitacaoAssinaturaExpirada` | CANÔNICO | a Solicitação expirou sem satisfazer a política | na expiração | quando é recusa ativa, não expiração passiva |
| `SolicitacaoAssinaturaCancelada` | CANÔNICO | a Solicitação foi cancelada por decisão operacional | no cancelamento explícito | quando é falha técnica (`SolicitacaoAssinaturaFalhou`) |
| `SolicitacaoAssinaturaFalhou` | CANÔNICO | falha técnica no processo de Solicitação (não recusa nem expiração de negócio) | ver §8 | quando é recusa/expiração de negócio, não falha técnica |
| `NovaSolicitacaoAssinaturaCriada` | **REJEITADO** | — | — | duplica `SolicitacaoAssinaturaCriada` — a distinção "nova vs. retry" é resolvida por `causation_id`/idempotência (DEC-ENT-029), não por um segundo nome de evento |

### J. Signatário e Assinatura Individual

#### LinkAssinaturaCriado `[TEMPLATE COMPLETO]`

**Definição:** um Link de Assinatura (credencial temporária) foi gerado
para um Signatário acessar a Solicitação.
**Entidade principal:** Link de Assinatura.
**Momento de emissão:** na geração do token e persistência do Link.
**Não emitir quando:** é um acesso a um Link já existente
(`LinkAssinaturaAcessado`); é apenas a Solicitação sendo preparada, sem Link
ainda gerado.
**Dados mínimos:** identificador do Link, Solicitação (relação), Signatário
(quando específico a um), validade/expiração.
**Dados opcionais:** limite de acessos, regras de uso.
**Estado anterior esperado:** não aplicável.
**Estado resultante:** Link válido.
**Módulo produtor:** Assinatura.
**Módulos consumidores potenciais:** Distribuição (para entregá-lo via
Envio).
**Efeito esperado:** tipicamente segue-se `SolicitacaoAssinaturaEnviada`
(via Envio do Link).
**Idempotência:** gerar um novo Link não apaga o histórico do anterior
(DEC-ENT-024) — cada geração é um fato novo, mesmo que o Link antigo ainda
não tenha expirado.
**Auditoria:** Solicitação, Signatário, validade — **nunca o token completo
em log comum** (DEC-ENT-024, princípio 14 do Manifesto).
**Correspondência no legado:** geração de `Hash Token` (`F_ASS_HASH`) dentro
do registro de `Assinaturas`.
**Riscos de migração:** o legado não tem histórico de Links — hoje um novo
Hash Token provavelmente substitui o campo, sem preservar o anterior;
migrar exige criar o histórico que não existe.
**Decisões e entidades relacionadas:** DEC-ENT-024.

#### AssinaturaRealizada `[TEMPLATE COMPLETO]`

**Definição:** um Signatário concluiu o ato de assinar.
**Entidade principal:** Assinatura.
**Momento de emissão:** quando o Signatário confirma a assinatura e a
evidência mínima exigida é capturada.
**Não emitir quando:** o Signatário apenas acessou o Link
(`LinkAssinaturaAcessado`); a tela de sucesso apareceu sem que a evidência
correspondente tenha sido de fato capturada (DEC-ENT-025 — tela de sucesso
não é evidência suficiente por si só, o evento representa o fato validado,
não a UI).
**Dados mínimos:** identificador da Assinatura, Solicitação (relação),
Signatário (relação), Arquivo apresentado, timestamp.
**Dados opcionais:** ver lista completa de evidências em DEC-ENT-025 (IP,
User-Agent, hash antes/depois, etc.) — carregadas via Evidência da
Assinatura, referenciada por este evento, não duplicadas no payload.
**Estado anterior esperado:** `ACESSADA` (Signatário).
**Estado resultante:** `ASSINADA` (Signatário) — **nunca** um estado de
Documento (reforço de DEC-ENT-022/DEC-ENT-028).
**Módulo produtor:** Assinatura.
**Módulos consumidores potenciais:** Solicitação de Assinatura (avaliação de
política de conclusão), Auditoria.
**Efeito esperado:** pode disparar `SolicitacaoAssinaturaParcialmenteAssinada`
ou `SolicitacaoAssinaturaConcluida`, conforme a política.
**Idempotência:** uma Assinatura, por Signatário, por Solicitação — dupla
submissão do mesmo formulário não deve gerar duas Assinaturas.
**Auditoria:** obrigatória por natureza — este é o fato jurídico mais
sensível do catálogo.
**Correspondência no legado:** conclusão em `/assinatura/<hash_token>`
(POST), gravação de `F_ASS_STATUS: 'Assinado'` em `Assinaturas` — e, hoje,
também `Status = 'Assinado'` em **Processar Arquivos** (achado crítico #1,
corrigido como regra por DEC-ENT-022, ainda não tecnicamente).
**Riscos de migração:** enquanto a correção técnica do achado crítico #1 não
for aplicada, este evento e o comportamento legado coexistem de forma
inconsistente — qualquer leitor que consuma `Status` de Documento
continuará vendo `Assinado` até a migração ocorrer.
**Decisões e entidades relacionadas:** DEC-ENT-014, DEC-ENT-022,
DEC-ENT-025, DEC-ENT-028.

#### ArquivoAssinadoGerado `[TEMPLATE COMPLETO]`

**Definição:** um novo Arquivo, resultante da incorporação de uma ou mais
Assinaturas, foi criado.
**Entidade principal:** Arquivo (caso concreto: Arquivo Assinado).
**Momento de emissão:** quando o PDF assinado é gerado e persistido como
**novo** Arquivo, referenciando o Arquivo de origem.
**Não emitir quando:** a assinatura ocorreu mas o Arquivo resultante ainda
não foi gerado (efeito assíncrono, se aplicável); o Arquivo apresentado for
sobrescrito em vez de um novo ser criado — isso seria uma violação de
DEC-ENT-026, não um caso válido de não-emissão, mas de erro de
implementação a evitar.
**Dados mínimos:** identificador do novo Arquivo, Arquivo de origem,
Solicitação de origem, Assinaturas incorporadas, hash.
**Dados opcionais:** ator/mecanismo gerador.
**Estado anterior esperado:** não aplicável ao novo Arquivo; o Arquivo de
origem passa de `vigente` a `superado`.
**Estado resultante:** o novo Arquivo nasce com situação `assinado` e,
tipicamente, `vigente` (ver `ArquivoMarcadoComoVigente`, §B).
**Módulo produtor:** Assinatura.
**Módulos consumidores potenciais:** Distribuição (se o Arquivo assinado
precisar ser redistribuído), Auditoria.
**Efeito esperado:** o Documento continua o mesmo quando a assinatura só
formaliza o mesmo conteúdo (DEC-ENT-026); alteração material exigiria avaliar
Documento derivado, fora do escopo deste evento.
**Idempotência:** gerar o Arquivo Assinado mais de uma vez para a mesma
Solicitação/conjunto de Assinaturas não deve criar Arquivos duplicados
representando o mesmo fato.
**Auditoria:** Arquivo de origem, Solicitação, Assinaturas incorporadas,
hash antes/depois.
**Correspondência no legado:** hoje não há Arquivo Assinado separado
formalmente documentado como versão — o PDF resultante da assinatura nativa
é referenciado dentro do próprio fluxo de `Assinaturas`
(`F_ASS_DOCUMENTO_PDF`).
**Riscos de migração:** confirmar que o legado nunca sobrescreve o PDF
original ao gerar a versão assinada — se sobrescrever, é uma violação
retroativa da política de versão que precisa ser corrigida antes de
confiar neste evento como fonte de verdade.
**Decisões e entidades relacionadas:** DEC-ENT-015, DEC-ENT-017,
DEC-ENT-026.

**Demais eventos da categoria (registro condensado):**

| Nome | Status | Definição | Momento de emissão | Não emitir quando |
|---|---|---|---|---|
| `SignatarioAdicionado` | CANÔNICO | um Signatário foi incluído numa Solicitação | na criação do papel de Signatário | quando é o próprio Signatário sendo notificado (`SignatarioConvocado`, fato distinto) |
| `SignatarioConvocado` | CANDIDATO | o Signatário foi notificado/convidado a assinar | no envio da convocação | quando convocação e criação do Link são o mesmo instante técnico — avaliar fusão |
| `LinkAssinaturaRevogado` | CANÔNICO | um Link foi invalidado antes de expirar naturalmente | na revogação explícita, com motivo | quando é expiração natural por tempo (`LinkAssinaturaExpirado`) |
| `LinkAssinaturaExpirado` | CANÔNICO | um Link atingiu sua validade sem ser usado (ou sem completar o uso) | na expiração natural | quando é revogação ativa |
| `LinkAssinaturaAcessado` | CANÔNICO | o Signatário acessou o Link — **não significa assinatura** (DEC-ENT-024, DEC-ENT-028) | no primeiro (ou cada) acesso registrável | quando o acesso já é seguido imediatamente pela assinatura no mesmo fluxo — mesmo assim, ambos os eventos devem ser emitidos, pois são fatos distintos |
| `AssinaturaRecusada` | CANÔNICO | o Signatário recusou explicitamente assinar | na recusa ativa | quando é expiração passiva (`AssinaturaExpirada`) |
| `AssinaturaExpirada` | CANÔNICO | a janela de assinatura do Signatário expirou sem ação | na expiração | quando é recusa ativa |
| `AssinaturaInvalidada` | CANÔNICO | uma Assinatura previamente válida foi invalidada (ex.: fraude identificada) — **não apaga o histórico anterior** | na invalidação | quando é simplesmente uma expiração ou recusa (estados distintos) |
| `EvidenciaAssinaturaRegistrada` | CANDIDATO | uma evidência (IP, hash, aceite, etc.) foi capturada e registrada | a cada evidência relevante capturada, podendo ser mais de uma por Assinatura | quando o dado já está coberto pelo próprio `AssinaturaRealizada` sem necessidade de registro em separado — decisão técnica final pendente (DEC-ENT-025) |

### K. Auditoria

**Avaliação crítica exigida pelo comando:** auditoria, neste catálogo,
**não é uma categoria própria de eventos de negócio** — é uma capacidade
transversal (Manifesto, princípio 12) que **consome** os envelopes dos
eventos de domínio já definidos acima. Três dos cinco nomes propostos são
redundantes com essa premissa: criar um evento "sobre" outro evento de
domínio duplicaria o registro, não agregaria valor. Dois têm valor
diferencial real e ficam como candidatos.

| Nome | Status | Justificativa |
|---|---|---|
| `OperacaoAuditada` | **REJEITADO** | todo evento de domínio já é, por definição, auditável via seu envelope (§3) — um evento "em cima" de outro duplicaria o registro |
| `MudancaEstadoRegistrada` | **REJEITADO** | mudança de estado já é o campo "Estado resultante" de cada evento de domínio — não precisa de evento próprio |
| `FalhaRegistrada` | **REJEITADO** | cada evento de falha já é contextualizado (`TentativaEnvioFalhou`, `DocumentoProcessamentoFalhou`, etc., §8) — um genérico duplicaria e violaria a própria regra de "evitar `ProcessamentoFalhou` único" |
| `DecisaoAutomaticaRegistrada` | CANDIDATO | quando o sistema toma uma decisão automática de negócio não coberta por outro evento específico (ex.: aplicar uma política de desempate não óbvia) — sobreposição parcial com `ArquivoClassificacaoInconclusiva`, avaliar se se justifica como evento à parte |
| `IntervencaoManualRegistrada` | CANDIDATO | quando um humano intervém manualmente fora do fluxo automático — tem valor de auditoria distinto, mas não é obrigatório nesta fase |

### L. Ponto e Alertas

**Restrição aplicada por causa de DEC-ENT-010/DEC-ENT-011 (`PENDENTE`):**
nenhum evento abaixo afirma que Alerta de Ponto é (ou não é) Pendência
Documental, e nenhum define o significado de `Fechamento`/`SBJ` — todos os
que dependem dessas respostas ficam marcados `PENDENTE DE DECISÃO`, não
`CANDIDATO` (a diferença: candidato é modelagem em aberto; pendente de
decisão é modelagem que **não pode avançar** sem resposta de negócio
externa a este catálogo).

| Nome | Status | Definição | Momento de emissão | Não emitir quando |
|---|---|---|---|---|
| `AlertaPontoCriado` | CANDIDATO | um Alerta de Ponto foi identificado a partir dos dados do Secullum | ao detectar o desvio | quando o desvio já tem alerta aberto para o mesmo Colaborador/data/tipo (idempotência, `_alerta_existe` no legado) |
| `AlertaPontoAtualizado` | **REJEITADO** | — | — | nome genérico proibido pela regra de nomenclatura (§1) |
| `AlertaPontoResolvido` | CANDIDATO | o Alerta foi tratado/resolvido | na resolução | quando ainda está em aberto |
| `InconsistenciaPontoIdentificada` | CANDIDATO | possível sinônimo de `AlertaPontoCriado` | — | avaliar sobreposição antes de manter os dois nomes — não decidir agora qual prevalece |
| `FechamentoPontoIniciado` | **PENDENTE DE DECISÃO** | depende do significado de `Fechamento` (DEC-ENT-011, ainda não confirmado) | — | não modelar em detalhe até DEC-ENT-011 ser respondida |
| `FechamentoPontoConcluido` | **PENDENTE DE DECISÃO** | idem | — | idem |
| `FechamentoPontoFalhou` | **PENDENTE DE DECISÃO** | idem | — | idem |

---

## 5. Classificação Consolidada — os 96 Nomes Avaliados

**Resumo da contagem** (reconciliado por soma direta das categorias A-L
acima, sem arredondamento): **96 nomes analisados** — **54 CANÔNICO**, **23
CANDIDATO**, **16 REJEITADO**, **3 PENDENTE DE DECISÃO** (54+23+16+3=96).

| # | Nome analisado | Classificação | Entidade principal | Status | Justificativa (curta — detalhe completo em §4) |
|---|---|---|---|---|---|
| 1 | `ItemIngestaoRecebido` | EVENTO DE DOMÍNIO | Item de Ingestão | CANÔNICO | fato de chegada, núcleo mínimo |
| 2 | `ItemIngestaoValidado` | EVENTO DE DOMÍNIO | Item de Ingestão | CANDIDATO | só se validação tiver lógica não trivial |
| 3 | `ItemIngestaoRejeitado` | EVENTO DE DOMÍNIO | Item de Ingestão | CANÔNICO | fato negativo real, distinto de falha técnica |
| 4 | `ArquivoExtraido` | EVENTO DE DOMÍNIO | Arquivo | CANÔNICO | anexo persistido e vinculado |
| 5 | `LoteIngestaoIdentificado` | EVENTO DE DOMÍNIO | Item de Ingestão/Documento | CANDIDATO | heurística de janela, não determinística |
| 6 | `IngestaoFalhou` | EVENTO DE DOMÍNIO | Item de Ingestão | CANÔNICO | falha contextualizada, distinta de rejeição de regra |
| 7 | `ArquivoClassificacaoSolicitada` | NÃO É EVENTO — COMANDO | — | REJEITADO | duplica comando `ClassificarArquivo` |
| 8 | `ArquivoClassificado` | EVENTO DE DOMÍNIO | Documento | CANÔNICO | núcleo mínimo |
| 9 | `ArquivoClassificacaoInconclusiva` | EVENTO DE DOMÍNIO | Documento | CANÔNICO | confiança baixa, fato distinto de sucesso |
| 10 | `DocumentoCriado` | EVENTO DE DOMÍNIO | Documento | CANÔNICO | núcleo mínimo |
| 11 | `DocumentoIdentificado` | EVENTO DE DOMÍNIO | Documento | CANDIDATO | possível sobreposição com `ArquivoClassificado` |
| 12 | `DocumentoAtualizado` | NÃO É EVENTO — ESTADO/nome genérico | — | REJEITADO | viola regra de nomenclatura (§1) |
| 13 | `DocumentoDerivadoCriado` | EVENTO DE DOMÍNIO | Documento | CANÔNICO | DEC-ENT-006/015, mudança material de conteúdo |
| 14 | `ArquivoVinculadoAoDocumento` | EVENTO DE DOMÍNIO | Arquivo | CANÔNICO | núcleo mínimo |
| 15 | `ArquivoVersaoCriada` | EVENTO DE DOMÍNIO | Arquivo | CANÔNICO | DEC-ENT-017 |
| 16 | `ArquivoMarcadoComoVigente` | EVENTO DE DOMÍNIO | Arquivo | CANÔNICO | DEC-ENT-017 |
| 17 | `DocumentoProcessamentoIniciado` | EVENTO DE DOMÍNIO | Documento | CANDIDATO | só se processamento não for síncrono/instantâneo |
| 18 | `DocumentoProcessamentoConcluido` | EVENTO DE DOMÍNIO | Documento | CANÔNICO | sucesso técnico, distinto de confiança atingida |
| 19 | `DocumentoProcessamentoFalhou` | EVENTO DE DOMÍNIO | Documento | CANÔNICO | núcleo mínimo |
| 20 | `PendenciaDocumentalCriada` | EVENTO DE DOMÍNIO | Pendência Documental | CANÔNICO | distinto de Alerta de Ponto (achado crítico #2) |
| 21 | `PendenciaDocumentalResolvida` | EVENTO DE DOMÍNIO | Pendência Documental | CANÔNICO | resolução humana |
| 22 | `ColaboradorCadastrado` | EVENTO DE DOMÍNIO | Colaborador | CANÔNICO | criação de identidade |
| 23 | `ColaboradorIdentificado` | EVENTO DE DOMÍNIO | Colaborador | CANDIDATO | possível sobreposição com `DocumentoIdentificado` |
| 24 | `VinculoTrabalhistaCriado` | EVENTO DE DOMÍNIO | Vínculo Trabalhista | CANÔNICO | DEC-ENT-002/016 |
| 25 | `VinculoTrabalhistaEncerrado` | EVENTO DE DOMÍNIO | Vínculo Trabalhista | CANÔNICO | DEC-ENT-002 |
| 26 | `AlocacaoCriada` | EVENTO DE DOMÍNIO | Alocação | CANÔNICO | DEC-ENT-016 |
| 27 | `AlocacaoAlterada` | NÃO É EVENTO — nome genérico | — | REJEITADO | "Alterada" viola §1; usar Encerrada+Criada |
| 28 | `AlocacaoEncerrada` | EVENTO DE DOMÍNIO | Alocação | CANÔNICO | DEC-ENT-016 |
| 29 | `ColaboradorAlocadoAoPosto` | EVENTO DE DOMÍNIO (duplicado) | — | REJEITADO | duplica `AlocacaoCriada` |
| 30 | `ColaboradorRemovidoDoPosto` | EVENTO DE DOMÍNIO (duplicado) | — | REJEITADO | duplica `AlocacaoEncerrada` |
| 31 | `DistribuicaoCriada` | EVENTO DE DOMÍNIO | Distribuição | CANÔNICO | núcleo mínimo |
| 32 | `DocumentoAdicionadoADistribuicao` | EVENTO DE DOMÍNIO | Distribuição | CANDIDATO | só se construção incremental |
| 33 | `DestinatarioAdicionadoADistribuicao` | EVENTO DE DOMÍNIO | Distribuição | CANDIDATO | idem |
| 34 | `DistribuicaoPronta` | EVENTO DE DOMÍNIO | Distribuição | CANDIDATO | redundante se Distribuição nasce completa |
| 35 | `DistribuicaoIniciada` | EVENTO DE DOMÍNIO | Distribuição | CANDIDATO | possível coincidência temporal com Criada |
| 36 | `DistribuicaoConcluida` | EVENTO DE DOMÍNIO | Distribuição | CANÔNICO | DEC-ENT-013, política de conclusão própria |
| 37 | `DistribuicaoFalhou` | EVENTO DE DOMÍNIO | Distribuição | CANÔNICO | política de conclusão impossível |
| 38 | `DistribuicaoCancelada` | EVENTO DE DOMÍNIO | Distribuição | CANÔNICO | cancelamento deliberado |
| 39 | `EnvioCriado` | EVENTO DE DOMÍNIO | Envio | CANÔNICO | núcleo mínimo |
| 40 | `EnvioColocadoNaFila` | EVENTO DE DOMÍNIO | Envio | CANÔNICO | núcleo mínimo |
| 41 | `EnvioProcessamentoIniciado` | EVENTO DE DOMÍNIO | Envio | CANDIDATO | só se fila≠processamento distinguíveis |
| 42 | `EnvioAceitoPeloProvedor` | EVENTO DE DOMÍNIO | Envio | CANÔNICO | núcleo mínimo, DEC-ENT-009 |
| 43 | `EnvioDespachadoPeloProvedor` | EVENTO DE DOMÍNIO | Envio | CANÔNICO | nível intermediário DEC-ENT-009 |
| 44 | `EnvioEntregue` | EVENTO DE DOMÍNIO | Envio | CANÔNICO | núcleo mínimo, DEC-ENT-009 |
| 45 | `EnvioLido` | EVENTO DE DOMÍNIO | Envio | CANÔNICO | DEC-ENT-009 |
| 46 | `EnvioConfirmadoPeloDestinatario` | EVENTO DE DOMÍNIO | Envio | CANÔNICO | DEC-ENT-009, nível mais alto |
| 47 | `EnvioFalhaTemporariaRegistrada` | EVENTO DE DOMÍNIO | Envio | CANÔNICO | DEC-ENT-020 |
| 48 | `EnvioFalhaDefinitivaRegistrada` | EVENTO DE DOMÍNIO | Envio | CANÔNICO | núcleo mínimo |
| 49 | `EnvioCancelado` | EVENTO DE DOMÍNIO | Envio | CANÔNICO | cancelamento deliberado |
| 50 | `ReenvioCriado` | EVENTO DE DOMÍNIO | Envio | CANÔNICO | DEC-ENT-007, nunca confundir com retry |
| 51 | *(nota)* `EnvioConcluido` | NÃO É EVENTO — ambíguo | — | REJEITADO (não proposto pelo comando, evitado por decisão própria) | sem condição única de conclusão — ver nota de abertura da §E |
| 52 | `TentativaEnvioIniciada` | EVENTO DE INTEGRAÇÃO | Tentativa de Envio | CANDIDATO | valor de auditoria marginal |
| 53 | `TentativaEnvioAceitaPeloProvedor` | EVENTO DE INTEGRAÇÃO | Tentativa de Envio | CANDIDATO | redundante com `EnvioAceitoPeloProvedor` se 1 tentativa |
| 54 | `TentativaEnvioFalhou` | EVENTO DE DOMÍNIO | Tentativa de Envio | CANÔNICO | núcleo mínimo |
| 55 | `TentativaEnvioFinalizada` | EVENTO DE INTEGRAÇÃO | Tentativa de Envio | CANDIDATO | redundante com evento de resultado do Envio |
| 56 | `EvidenciaEntregaRegistrada` | EVENTO CANDIDATO | Evidência de Entrega (candidata) | CANDIDATO | meta-evento de registro de evidência |
| 57 | `EntregaConfirmada` | EVENTO DE DOMÍNIO (duplicado) | Envio | REJEITADO | duplica `EnvioEntregue` |
| 58 | `LeituraConfirmada` | EVENTO DE DOMÍNIO (duplicado) | Envio | REJEITADO | duplica `EnvioLido` |
| 59 | `ConfirmacaoDestinatarioRegistrada` | EVENTO DE DOMÍNIO (duplicado) | Envio | REJEITADO | duplica `EnvioConfirmadoPeloDestinatario` |
| 60 | `AssinaturaExigida` | NÃO É EVENTO — ESTADO (regra aplicada) | — | REJEITADO | resultado de atributo de Tipo Documental |
| 61 | `AssinaturaDispensada` | NÃO É EVENTO — ESTADO (regra aplicada) | — | REJEITADO | DEC-ENT-022: ausência não é fato a registrar |
| 62 | `PoliticaAssinaturaDeterminada` | NÃO É EVENTO — configuração | — | REJEITADO | configuração de Tipo Documental, não instância |
| 63 | `SolicitacaoAssinaturaCriada` | EVENTO DE DOMÍNIO | Solicitação de Assinatura | CANÔNICO | núcleo mínimo (assinatura opcional) |
| 64 | `SolicitacaoAssinaturaPreparada` | EVENTO DE DOMÍNIO | Solicitação de Assinatura | CANDIDATO | possível coincidência com Criada |
| 65 | `SolicitacaoAssinaturaEnviada` | EVENTO DE DOMÍNIO | Solicitação de Assinatura | CANÔNICO | Link disponibilizado ≠ assinatura |
| 66 | `SolicitacaoAssinaturaIniciada` | EVENTO DE DOMÍNIO | Solicitação de Assinatura | CANDIDATO | possível fusão com `LinkAssinaturaAcessado` |
| 67 | `SolicitacaoAssinaturaParcialmenteAssinada` | EVENTO DE DOMÍNIO | Solicitação de Assinatura | CANÔNICO | DEC-ENT-027 |
| 68 | `SolicitacaoAssinaturaConcluida` | EVENTO DE DOMÍNIO | Solicitação de Assinatura | CANÔNICO | núcleo mínimo (assinatura opcional) |
| 69 | `SolicitacaoAssinaturaRecusada` | EVENTO DE DOMÍNIO | Solicitação de Assinatura | CANÔNICO | política inviabilizada |
| 70 | `SolicitacaoAssinaturaExpirada` | EVENTO DE DOMÍNIO | Solicitação de Assinatura | CANÔNICO | expiração passiva |
| 71 | `SolicitacaoAssinaturaCancelada` | EVENTO DE DOMÍNIO | Solicitação de Assinatura | CANÔNICO | cancelamento deliberado |
| 72 | `SolicitacaoAssinaturaFalhou` | EVENTO DE DOMÍNIO | Solicitação de Assinatura | CANÔNICO | falha técnica contextualizada |
| 73 | `NovaSolicitacaoAssinaturaCriada` | EVENTO DE DOMÍNIO (duplicado) | — | REJEITADO | duplica `SolicitacaoAssinaturaCriada`, resolvido por `causation_id` |
| 74 | `SignatarioAdicionado` | EVENTO DE DOMÍNIO | Signatário | CANÔNICO | DEC-ENT-023 |
| 75 | `SignatarioConvocado` | EVENTO DE DOMÍNIO | Signatário | CANDIDATO | possível coincidência com criação do Link |
| 76 | `LinkAssinaturaCriado` | EVENTO DE DOMÍNIO | Link de Assinatura | CANÔNICO | núcleo mínimo (assinatura opcional) |
| 77 | `LinkAssinaturaRevogado` | EVENTO DE DOMÍNIO | Link de Assinatura | CANÔNICO | DEC-ENT-024 |
| 78 | `LinkAssinaturaExpirado` | EVENTO DE DOMÍNIO | Link de Assinatura | CANÔNICO | DEC-ENT-024 |
| 79 | `LinkAssinaturaAcessado` | EVENTO DE DOMÍNIO | Link de Assinatura | CANÔNICO | acesso ≠ assinatura |
| 80 | `AssinaturaRealizada` | EVENTO DE DOMÍNIO | Assinatura | CANÔNICO | núcleo mínimo (assinatura opcional) |
| 81 | `AssinaturaRecusada` | EVENTO DE DOMÍNIO | Assinatura | CANÔNICO | recusa ativa |
| 82 | `AssinaturaExpirada` | EVENTO DE DOMÍNIO | Assinatura | CANÔNICO | expiração passiva |
| 83 | `AssinaturaInvalidada` | EVENTO DE DOMÍNIO | Assinatura | CANÔNICO | preserva histórico anterior |
| 84 | `EvidenciaAssinaturaRegistrada` | EVENTO CANDIDATO | Evidência da Assinatura (candidata) | CANDIDATO | decisão técnica pendente DEC-ENT-025 |
| 85 | `ArquivoAssinadoGerado` | EVENTO DE DOMÍNIO | Arquivo (especialização) | CANÔNICO | núcleo mínimo (assinatura opcional) |
| 86 | `OperacaoAuditada` | EVENTO DE AUDITORIA | — | REJEITADO | redundante — todo evento já é auditável via envelope |
| 87 | `MudancaEstadoRegistrada` | EVENTO DE AUDITORIA | — | REJEITADO | redundante — já é campo "Estado resultante" |
| 88 | `FalhaRegistrada` | EVENTO DE AUDITORIA | — | REJEITADO | redundante — falhas já contextualizadas (§8) |
| 89 | `DecisaoAutomaticaRegistrada` | EVENTO DE AUDITORIA | (transversal) | CANDIDATO | sobreposição parcial com `ArquivoClassificacaoInconclusiva` |
| 90 | `IntervencaoManualRegistrada` | EVENTO DE AUDITORIA | (transversal) | CANDIDATO | valor de auditoria distinto, não obrigatório |
| 91 | `AlertaPontoCriado` | EVENTO DE DOMÍNIO | Alerta de Ponto | CANDIDATO | DEC-ENT-010 pendente para relação com Pendência |
| 92 | `AlertaPontoAtualizado` | NÃO É EVENTO — nome genérico | — | REJEITADO | viola §1 |
| 93 | `AlertaPontoResolvido` | EVENTO DE DOMÍNIO | Alerta de Ponto | CANDIDATO | idem 91 |
| 94 | `InconsistenciaPontoIdentificada` | EVENTO DE DOMÍNIO | Alerta de Ponto | CANDIDATO | possível sinônimo de `AlertaPontoCriado` |
| 95 | `FechamentoPontoIniciado` | EVENTO CANDIDATO | Fechamento (significado incerto) | PENDENTE DE DECISÃO | depende de DEC-ENT-011 |
| 96 | `FechamentoPontoConcluido` | EVENTO CANDIDATO | Fechamento (significado incerto) | PENDENTE DE DECISÃO | depende de DEC-ENT-011 |
| 97 | `FechamentoPontoFalhou` | EVENTO CANDIDATO | Fechamento (significado incerto) | PENDENTE DE DECISÃO | depende de DEC-ENT-011 |

**Nota sobre a numeração:** a linha 51 (`EnvioConcluido`) é uma nota de
decisão própria, não um nome proposto pelo comando original — por isso a
soma "96 nomes analisados" citada no resumo desconsidera essa linha; as
demais 96 linhas (1-50, 52-97) correspondem exatamente aos nomes citados no
comando.

---

## 6. Eventos versus Estados

| Estado (situação atual) | Evento (fato ocorrido) |
|---|---|
| `ENTREGUE` | `EnvioEntregue` |
| `ASSINADA` | `AssinaturaRealizada` |
| `CONCLUIDA` | `SolicitacaoAssinaturaConcluida` |

Registrado:

- **Estado representa a situação atual** de uma entidade — pode ser
  sobrescrito quando a entidade avança para o próximo estado.
- **Evento representa um fato ocorrido** — imutável, nunca sobrescrito.
- **Eventos não são apagados quando o estado muda.** Um Envio que passa de
  `ENTREGUE` para `LIDO` mantém o evento `EnvioEntregue` no histórico — o
  estado avança, o fato passado permanece registrado.
- **O estado atual pode ser reconstruído ou validado pelo histórico de
  eventos** — mas isso é uma capacidade que o histórico de eventos permite,
  não uma exigência de que o estado só possa existir dessa forma.
- **Não se implementa event sourcing obrigatório nesta fase.** O estado
  continua sendo lido diretamente de onde ele vive hoje (campo no registro).
  Preservar eventos para auditoria é uma decisão independente de adotar
  event sourcing como arquitetura — uma coisa não obriga a outra.

---

## 7. Eventos versus Comandos

| Comando (intenção, pode falhar) | Evento (fato, só existe se ocorreu) |
|---|---|
| `ReceberItemIngestao` | `ItemIngestaoRecebido` |
| `ClassificarArquivo` | `ArquivoClassificado` |
| `CriarDocumento` | `DocumentoCriado` |
| `CriarDistribuicao` | `DistribuicaoCriada` |
| `EnviarDocumento` | `EnvioAceitoPeloProvedor` |
| `RegistrarAssinatura` | `AssinaturaRealizada` |
| `CancelarEnvio` | `EnvioCancelado` |

Registrado:

- **Um comando pode falhar.** Um evento, por definição, só é emitido quando
  o fato correspondente de fato ocorreu — não existe "evento que falhou",
  existe um evento de falha **diferente** e contextualizado (§8).
- **Intenção não é registrada como sucesso.** `EnviarDocumento` (comando) não
  vira `EnvioRealizado` só porque foi chamado — o evento correspondente só
  nasce quando o provedor de fato aceitou/processou/entregou (ver os níveis
  de `EnvioAceitoPeloProvedor` em diante, DEC-ENT-009).
- **Comandos terão contratos próprios**, definidos posteriormente — este
  catálogo não define o formato de comando, só demonstra a fronteira
  conceitual entre os dois.

---

## 8. Eventos de Falha

**Nenhum `ProcessamentoFalhou` genérico.** Cada categoria tem seu próprio
evento de falha contextualizado, já definido em §4:
`IngestaoFalhou`, `DocumentoProcessamentoFalhou`, `TentativaEnvioFalhou`,
`EnvioFalhaDefinitivaRegistrada`, `SolicitacaoAssinaturaFalhou`. Um evento
adicional citado pelo comando — `GeracaoArquivoAssinadoFalhou` — não teve
entrada própria em §4 porque, nesta modelagem, uma falha na geração do
Arquivo Assinado é tratada como `SolicitacaoAssinaturaFalhou` com etapa
(`stage`) = "geração de Arquivo Assinado", não como um sexto evento de
falha — avaliar na revisão de contratos se o volume de casos justifica
separar.

**Todo evento de falha carrega, conceitualmente:**

- categoria (técnica, negócio, integração externa);
- código;
- mensagem segura (nunca credenciais nem conteúdo sensível — princípio 14
  do Manifesto);
- etapa (`stage`) em que ocorreu;
- possibilidade de retry (sim/não);
- entidade afetada e seu identificador;
- número da tentativa, quando aplicável;
- provedor ou integração envolvida, quando aplicável;
- `correlation_id`;
- referência ao erro original, protegida (não o erro bruto exposto em
  texto livre para qualquer consumidor);
- data e hora.

---

## 9. Idempotência de Eventos

- Uma **ocorrência** de evento tem `event_id` único — retries de
  **publicação** do mesmo fato não devem gerar dois fatos de negócio
  distintos.
- **Dois eventos do mesmo tipo podem ser legítimos**: duas
  `TentativaEnvioFalhou` para o mesmo Envio são dois fatos reais distintos
  (duas tentativas, dois momentos) — idempotência não significa "só um
  evento deste tipo por entidade", significa "o mesmo fato não é registrado
  duas vezes".
- **Idempotência do comando ≠ idempotência do evento.** A chave de
  idempotência de uma operação de criação (ex.: DEC-ENT-029, criação de
  Solicitação de Assinatura) evita que o **comando** repetido crie duas
  entidades — isso é anterior e distinto de garantir que o **evento**
  `SolicitacaoAssinaturaCriada` também não seja publicado duas vezes para a
  mesma criação.
- Consumidores devem poder identificar eventos já processados (via
  `event_id`) para não reagir duas vezes ao mesmo fato.
- Chaves finais de idempotência (formato, armazenamento) serão definidas
  nos contratos de dados posteriores.

---

## 10. Ordenação e Causalidade

- Todo evento tem `occurred_at` (quando o fato ocorreu) e `recorded_at`
  (quando foi registrado) — podem divergir.
- `correlation_id` agrupa o processo de negócio inteiro (ex.: um Item de
  Ingestão e todos os Documentos/Envios/Assinaturas que dele derivam).
- `causation_id` aponta o fato ou comando imediatamente anterior que causou
  este evento — permite reconstruir a cadeia causal passo a passo, não só o
  agrupamento geral.
- **Não confiar apenas na ordem física de chegada.** Eventos externos (
  confirmação de entrega, webhook de leitura) podem chegar atrasados —
  inclusive depois de um timeout já ter sido processado como falha.
- Quando isso acontece — ex.: `EnvioFalhaDefinitivaRegistrada` seguido, mais
  tarde, por uma confirmação de entrega atrasada chegando do provedor — o
  **conflito de evidências deve ser preservado e resolvido, não apagado**:
  ambos os eventos permanecem no histórico; a resolução (qual prevalece para
  fins de negócio) é uma regra a definir nos contratos, não uma decisão de
  descartar um dos dois fatos.

---

## 11. Compatibilidade com o Legado

| Evento canônico | Situação equivalente no legado | Evidência atual | Risco | Adaptação necessária |
|---|---|---|---|---|
| `DocumentoCriado` / `ArquivoClassificado` | criação de registro em `Processar Arquivos` com `Status`/`F_PROC_TIPO_DOC` preenchidos | `app.py:114`, funções de classificação | Alto | separar as duas fases hoje fundidas num único registro (`ARQUITETURA_FASE_2_DECISAO_FINAL.md`) |
| `DocumentoProcessamentoFalhou` | `_atualizar_status_processar(id, 'Erro')` + `F_PROC_TIPO_DOC` com código técnico | `app.py`, múltiplas ocorrências | Alto | separar erro técnico de Tipo Documental (débito #3) antes de confiar no payload do evento |
| `ArquivoVinculadoAoDocumento` | campo `Arquivos 2` (`F_PROC_ARQUIVOS2`) | `app.py:438` | Baixo | nenhuma — já é uma referência relacional real |
| `PendenciaDocumentalCriada` | criação de registro em `Pendências/Revisar` | `app.py:115` | Crítico | tabela compartilhada com Alerta de Ponto (achado crítico #2) — separar antes de confiar que o evento só representa Pendência Documental |
| `AssinaturaRealizada` | POST em `/assinatura/<hash_token>`, grava `F_ASS_STATUS: 'Assinado'` **e também** `Status` de Processar Arquivos = `'Assinado'` | `app.py:9896` | Crítico | achado crítico #1 — enquanto a correção técnica não ocorre, o legado seguirá contaminando o estado do Documento mesmo depois deste evento existir no catálogo |
| `EnvioCriado` / `EnvioColocadoNaFila` | criação de registro em `Envios de Documentos`, `Status = 'Preparando'` | rotas `gerar-fila-envios*` (4 variantes por canal) | Alto | unificar os 4 fluxos por canal antes de mapear 1:1 para este evento único |
| `EnvioAceitoPeloProvedor` | resposta HTTP da Evolution API/SMTP dentro de `disparar-fila*`, sem distinguir aceitação real de HTTP 200 de transporte | rotas `disparar-fila*` | Médio | checar o corpo da resposta, não só ausência de exceção |
| `EnvioFalhaDefinitivaRegistrada` | `_marcar_envio_status(id, 'Erro', erro=...)` | `app.py`, múltiplas ocorrências | Médio | legado não distingue falha temporária de definitiva (`'Erro'` único) |
| `TentativaEnvioFalhou` | incremento do contador `Tentativa`, sem registro por tentativa | `Envios de Documentos` | Alto | criar o registro individual por tentativa que hoje não existe |
| `ReenvioCriado` | reenvio manual hoje reaproveita o mesmo registro (`Tentativa` incrementada) — comportamento não confirmado como uniforme em todos os fluxos | `app.py`, rotas de reenvio | Médio | confirmar, fluxo a fluxo, se reenvio hoje cria novo registro ou reaproveita — DEC-ENT-007 já decidiu qual deve ser o alvo |
| `SolicitacaoAssinaturaCriada` | criação de registro em `Assinaturas`, Documento referenciado por texto solto | `F_ASS_PROCESSAR_ID`, `app.py:167` | Crítico | corrigir para link canônico antes de o evento poder confiar em `entity_id` de Documento |
| (estados `Enviar`, `Pendente`, `Processando`, `Concluído`, `Assinado`) | vocabulário de `Status` hoje misturado entre Documento/Envio/Assinatura | `app.py`, múltiplas tabelas | Alto | reconciliar com o vocabulário conceitual aprovado (DEC-ENT-020, DEC-ENT-027, DEC-ENT-028) |
| (possíveis `Finalizado`, `Pronto`) | não confirmados como literais no código; possivelmente só no Airtable | não verificado | Médio | DEC-ENT-012 segue `PENDENTE` — nenhum evento deste catálogo assume a existência ou o significado desses estados |

Regra aplicada consistentemente nesta matriz e em todo o documento: **uma
alteração de campo no Airtable não é, automaticamente, um evento canônico.**
Cada linha acima representa um fato de negócio já identificado — não uma
tradução mecânica de "todo `PATCH` vira um evento".

---

## 12. Eventos Mínimos da Primeira Migração

### Ingestão e documento

`ItemIngestaoRecebido`, `ArquivoClassificado`, `DocumentoCriado`,
`ArquivoVinculadoAoDocumento`, `DocumentoProcessamentoFalhou`.

### Distribuição e envio

`DistribuicaoCriada`, `EnvioCriado`, `EnvioColocadoNaFila`,
`EnvioAceitoPeloProvedor`, `EnvioEntregue`, `TentativaEnvioFalhou`,
`EnvioFalhaDefinitivaRegistrada`.

### Assinatura opcional (só quando o Tipo Documental exigir, DEC-ENT-022)

`SolicitacaoAssinaturaCriada`, `LinkAssinaturaCriado`, `AssinaturaRealizada`,
`SolicitacaoAssinaturaConcluida`, `ArquivoAssinadoGerado`.

**Avaliação de indispensabilidade** (pedida explicitamente pelo comando):
dos 17 eventos acima, todos passaram no teste de "o fato é observável e
distinto de qualquer outro evento do núcleo"? Um caso de atenção:
`EnvioColocadoNaFila` só se justifica separado de `EnvioCriado` se o
processamento for de fato assíncrono com fila real (o que já é verdade no
legado via Celery/Redis) — mantido. Os demais 16 não têm sobreposição entre
si dentro deste núcleo. Total: **17 eventos** no núcleo mínimo (12
obrigatórios + 5 de assinatura opcional).

---

## 13. Relação com Entidades Canônicas

| Entidade | Eventos que pode produzir | Eventos que pode consumir/sofrer |
|---|---|---|
| Empresa | nenhum específico (singular, estável) | nenhum |
| Cliente | `ClienteCadastrado` (candidato, fora deste catálogo — `MAGNATA_OS_ENTIDADES.md` §5) | `DocumentoCriado` (como destinatário coletivo), `DistribuicaoCriada` |
| Contrato Comercial | nenhum definido nesta versão (segunda fase) | — |
| Posto de Trabalho | nenhum definido nesta versão | `AlocacaoCriada`, `AlocacaoEncerrada` |
| Colaborador | `ColaboradorCadastrado` | `VinculoTrabalhistaCriado`, `AlertaPontoCriado` (candidato) |
| Vínculo Trabalhista | `VinculoTrabalhistaCriado`, `VinculoTrabalhistaEncerrado` | `AlocacaoCriada` |
| Alocação | `AlocacaoCriada`, `AlocacaoEncerrada` | — |
| Documento | `DocumentoCriado`, `DocumentoDerivadoCriado`, `DocumentoProcessamentoConcluido`, `DocumentoProcessamentoFalhou` | `ArquivoClassificado`, `ArquivoVinculadoAoDocumento`, `PendenciaDocumentalCriada`, `SolicitacaoAssinaturaCriada` (opcional) |
| Arquivo | `ArquivoExtraido`, `ArquivoVersaoCriada`, `ArquivoMarcadoComoVigente`, `ArquivoAssinadoGerado` | `ArquivoVinculadoAoDocumento` |
| Item de Ingestão | `ItemIngestaoRecebido`, `ItemIngestaoRejeitado` | `ArquivoExtraido`, `DocumentoCriado` |
| Distribuição | `DistribuicaoCriada`, `DistribuicaoConcluida`, `DistribuicaoFalhou`, `DistribuicaoCancelada` | `EnvioCriado` (N vezes) |
| Envio | `EnvioCriado` até `EnvioConfirmadoPeloDestinatario`, `EnvioCancelado`, `ReenvioCriado` | `TentativaEnvioFalhou`, `DistribuicaoCriada` (origem) |
| Tentativa de Envio | `TentativaEnvioFalhou` | `EnvioColocadoNaFila` (origem) |
| Destinatário | nenhum específico (é referenciado, não emite) | `EnvioCriado` |
| Solicitação de Assinatura | `SolicitacaoAssinaturaCriada` até `SolicitacaoAssinaturaFalhou` | `SignatarioAdicionado`, `AssinaturaRealizada` (via Signatário) |
| Signatário | `SignatarioAdicionado`, `LinkAssinaturaAcessado` | `SolicitacaoAssinaturaCriada` (origem) |
| Assinatura | `AssinaturaRealizada`, `AssinaturaRecusada`, `AssinaturaExpirada`, `AssinaturaInvalidada` | `LinkAssinaturaAcessado` (pré-requisito) |
| Link de Assinatura | `LinkAssinaturaCriado`, `LinkAssinaturaRevogado`, `LinkAssinaturaExpirado` | `SolicitacaoAssinaturaCriada` (origem) |
| Pendência Documental | `PendenciaDocumentalCriada`, `PendenciaDocumentalResolvida` | `DocumentoProcessamentoFalhou`/`ArquivoClassificacaoInconclusiva` (origem) |
| Alerta de Ponto | `AlertaPontoCriado` (candidato), `AlertaPontoResolvido` (candidato) | dados do Secullum (fora deste catálogo) |

**Estruturas de valor** (Tipo Documental, Competência, Canal): **não
possuem ciclo próprio de eventos nesta versão** — são atributos consultados
por eventos de outras entidades (ex.: Tipo Documental é lido por
`SolicitacaoAssinaturaCriada` para avaliar exigência, DEC-ENT-022), nunca a
origem ou o alvo direto de um evento.

**Evidência de Entrega e Evidência da Assinatura** (candidatas): produzem
`EvidenciaEntregaRegistrada` e `EvidenciaAssinaturaRegistrada`
respectivamente — ambos `CANDIDATO`, refletindo que a própria entidade
ainda não tem forma técnica definitiva (entidade própria × registro
imutável, DEC-ENT-009/021/025).

As 20 entidades canônicas definitivas estão cobertas na tabela acima.

---

## 14. Decisões Pendentes que Afetam Eventos

- **DEC-ENT-010** — ainda não decidido se Alerta de Ponto e Pendência
  Documental possuem relação ou permanecem totalmente independentes.
  Nenhum evento deste catálogo assume uma resposta — `AlertaPontoCriado` e
  `PendenciaDocumentalCriada` permanecem eventos de entidades **não
  relacionadas** até essa decisão.
- **DEC-ENT-011** — significado funcional definitivo de `Fechamento` e
  `SBJ` ainda não aprovado. Os três eventos candidatos de Fechamento (§L)
  ficam classificados `PENDENTE DE DECISÃO`, não modelados em detalhe.
- **DEC-ENT-012** — estados `Finalizado`/`Pronto` ainda precisam ser
  confirmados no Airtable. Nenhum evento deste catálogo pressupõe a
  existência ou o significado desses estados (ver nota na matriz de
  legado, §11).

**Estas três pendências não impedem o catálogo principal** de eventos
documentais, de distribuição e de assinatura — todos os 17 eventos do
núcleo mínimo (§12) são independentes delas.

---

## 15. Conclusão

- **Nomes analisados:** 96.
- **Eventos canônicos:** 54.
- **Eventos candidatos:** 23.
- **Nomes rejeitados** (comando, estado, log técnico, configuração ou
  duplicata): 16.
- **Pendentes de decisão** (aguardando DEC-ENT-011): 3.
- **Eventos mínimos da primeira migração:** 17 (12 obrigatórios + 5 de
  assinatura opcional, §12).
- **Eventos opcionais de assinatura:** `SolicitacaoAssinaturaCriada`,
  `LinkAssinaturaCriado`, `AssinaturaRealizada`,
  `SolicitacaoAssinaturaConcluida`, `ArquivoAssinadoGerado` — só emitidos
  quando DEC-ENT-022 determina exigência de assinatura para aquele Tipo
  Documental/finalidade.
- **Pendências:** DEC-ENT-010, DEC-ENT-011, DEC-ENT-012 (§14); mais os 23
  candidatos que dependem de refinamento em contratos de dados futuros
  (sobreposições sinalizadas: `DocumentoIdentificado`×`ColaboradorIdentificado`,
  `SolicitacaoAssinaturaIniciada`×`LinkAssinaturaAcessado`,
  `AlertaPontoCriado`×`InconsistenciaPontoIdentificada`).
- **Condições para iniciar contratos de dados:** o núcleo mínimo (§12) está
  suficientemente estável para servir de base a contratos de payload —
  desde que os contratos (1) corrijam a referência textual solta
  Assinatura→Documento antes de definir `entity_id` de
  `SolicitacaoAssinaturaCriada`, e (2) tratem as 3 sobreposições candidatas
  acima como perguntas abertas, não como sinônimos resolvidos por
  conveniência.

---

## Confirmação de escopo

Nenhum arquivo existente foi alterado para produzir este catálogo — apenas
`MAGNATA_OS_EVENTOS.md` foi criado. Nenhum código, tabela do Airtable,
configuração, memória, fila, event bus, classe Python, JSON Schema ou
endpoint foi criado ou alterado. Nenhuma decisão `PENDENTE`
(DEC-ENT-010/011/012) foi tratada como resolvida. Nenhum evento candidato foi
promovido a canônico sem justificativa registrada na tabela de §5. Event
sourcing não foi assumido como arquitetura obrigatória — §6 registra
explicitamente o contrário.
