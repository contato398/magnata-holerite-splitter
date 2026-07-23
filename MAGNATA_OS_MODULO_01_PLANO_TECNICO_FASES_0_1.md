# Magnata OS — Módulo 01: Plano Técnico das Fases 0 e 1

**Versão:** 1.0 (plano técnico)
**Status:** PLANEJAMENTO TÉCNICO — não autoriza implementação
**Data:** 2026-07-22
**Fontes:** `MAGNATA_OS_MODULO_01_INGESTAO.md`,
`MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md` (v1.1, consolidada),
`MAGNATA_OS_CONTRATOS.md`, `MAGNATA_OS_ESTADOS.md`, `MAGNATA_OS_EVENTOS.md`,
mais evidência de código lida diretamente em `app.py`, `celery_app.py`,
`tarefas_processar_pdf.py`.

**Este documento ainda não autoriza implementação.** Nenhum código,
endpoint, classe, dependência, tabela ou configuração foi criado ou
alterado para produzi-lo.

---

## 1. Objetivo

Produzir o plano técnico executável para:

- **Fase 0 — Observabilidade do legado:** observar o fluxo atual de
  ingestão sem alterar seu comportamento.
- **Fase 1 — Upload manual em shadow mode:** executar o núcleo canônico em
  paralelo ao upload manual, sem assumir efeitos operacionais e sem
  substituir o legado.

Este plano parte das 13 decisões já fechadas em
`MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md` — nenhuma delas é reaberta
aqui.

---

## 2. Inventário Técnico do Fluxo Atual

**Rotas envolvidas (evidência: `app.py`):**

| Rota | Linha | Método de entrada | Retorno em falha |
|---|---|---|---|
| `/separar` | `app.py:3877` | `request.files['pdf']` + `request.form['processar_arquivo_record_id']` | **HTTP 200 mesmo em falha** (`success: False`, `app.py:3900-3927`) — achado crítico de observabilidade, ver abaixo |
| `/email/webhook` | `app.py:5028` | JSON com `anexos[].conteudo_base64` | HTTP 401 (chave inválida), 400 (`message_id` ausente), 500 (config ausente); demais casos retornam 200 com detalhe por anexo |
| `/processar-fila` | `app.py:5324` | não detalhado nesta leitura | não detalhado nesta leitura |
| `/processar-doc-cliente` | `app.py:6917` | não detalhado nesta leitura | não detalhado nesta leitura |

**Funções centrais:**
- `separar()` — `app.py:3877-3936+` — valida Record ID e PDF, lê em
  memória, enfileira via Celery, retorna HTTP 202 em caso de sucesso
  (assíncrono).
- `email_webhook()` — `app.py:5028-5205` — síncrono; decodifica base64,
  calcula hash, checa duplicidade, extrai texto (`pdfplumber`), classifica
  (`classificar_documento`) e grava em `Emails Savian`/`Arquivos`/
  `Processar Arquivos`, tudo na mesma requisição HTTP.

**Formulários:** `/separar` usa `multipart/form-data` (campo `pdf` +
campo de formulário `processar_arquivo_record_id`); `/email/webhook` usa
JSON puro.

**Tabelas envolvidas:** `Emails Savian` (`TABLE_EMAILS`), `Arquivos`
(`TABLE_ARQUIVOS`), `Processar Arquivos` (`TABLE_PROCESSAR`).

**Campos envolvidos:** `F_EMAIL_STATUS` (valor confirmado em uso:
`'Recebido'`), `F_EMAIL_MSGID`, `F_ARQ_HASH`, `F_ARQ_STATUS` (valor
confirmado: `'Recebido'`), `F_ARQ_EMAILS`, `F_PROC_STATUS` (valor
confirmado: `'Pendente'`), `F_PROC_TIPO_DOC`, `F_PROC_ARQUIVOS2`.

**Armazenamento:** anexo do Airtable (`multipleAttachments`), via
`_anexar_attachment` — nenhum storage externo de objetos em uso.

**Limites:** `MAX_CONTENT_LENGTH = 50 * 1024 * 1024` (`app.py:62`) — único
limite de tamanho confirmado, aplicado no nível HTTP/Flask, não por rota
individualmente.

**Hash:** SHA-256 do conteúdo (`hashlib.sha256(conteudo).hexdigest()`,
`app.py:5119`) — já em uso real para deduplicação de Arquivo.

**Idempotência:** checagem de `MESSAGE ID` duplicado antes de criar
`Emails Savian` (`app.py:5084`); checagem de `Hash do Anexo` duplicado
antes de criar `Arquivos` (`app.py:5124`) — ambas já funcionais.

**Logs:** `logger.info`/`logger.warning` dispersos (`app.py`, ex.: linha
5071-5074) — sem estrutura de campos fixos, sem `correlation_id`.

**Métricas:** **nenhuma métrica estruturada encontrada** — só logs de
texto livre.

**Filas:** Celery (`celery_app.py`), broker/backend Redis, tarefa
`processar_pdf_task` (`tarefas_processar_pdf.py`), `task_soft_time_limit=600`,
`task_time_limit=900`.

**Retries:** `task_acks_late=True`,
`broker_connection_retry_on_startup=True` (`celery_app.py:27-28`) — retry
de infraestrutura do Celery; não confirmado retry de negócio granular por
Tentativa individual.

**Retornos HTTP observados:** 200 (sucesso e, em `/separar`, também
falha), 202 (aceito, processamento assíncrono), 400, 401, 500.

**Pontos de entrada manual:** `/separar` (via Make.com hoje, mas
tecnicamente aceita qualquer chamador com o multipart correto) e rotas
como `/processar-fila`/`/processar-doc-cliente`.

**Dependências do Airtable:** todas as gravações de estado passam por
chamadas diretas à API do Airtable — não há camada de abstração de
persistência hoje.

**Pontos de escrita:** criação de registro (`_criar_registro`) e upload de
anexo (`_anexar_attachment`, `_fazer_upload_pdf_airtable`) — ambos síncronos
dentro da requisição HTTP, exceto quando delegados ao Celery.

**Achado crítico — erro retornando sucesso aparente:** `/separar` retorna
**HTTP 200** para `ATTACHMENT_NOT_FOUND`, `PDF_NO_FILENAME` e
`PDF_INVALID_EXTENSION` (`app.py:3900-3927`) — um chamador que só observa o
código de status HTTP (não o corpo `success: false`) leria isso como
sucesso. Isso é relevante tanto para a instrumentação da Fase 0 (medir
com base no corpo, não só no status HTTP) quanto como um risco a não
reproduzir no núcleo novo (Manifesto, princípio 10).

---

## 3. Desenho Técnico Proposto

**Recomendação: módulo interno desacoplado dentro do backend existente —
não um microsserviço.** Nenhuma evidência nesta sessão justifica a
complexidade operacional de um serviço separado (deploy próprio, rede
própria, mais um ponto de falha) para o volume e a maturidade atuais do
Magnata OS — consistente com a recomendação de monólito modular já
registrada em `MAGNATA_OS_ARQUITETURA.md` §3.

Estrutura conceitual proposta (nomes ilustrativos, não arquivos criados):

```text
magnata_os/
└── ingestion/
    ├── application/      (comandos: ReceberItemIngestao, ValidarItemIngestao, ...)
    ├── domain/           (Item de Ingestão, Arquivo — modelos conceituais)
    ├── contracts/        (schemas conceituais de MAGNATA_OS_CONTRATOS.md §4-5)
    ├── adapters/
    │   ├── legacy/       (adaptador de saída para Airtable/Processar Arquivos)
    │   └── storage/      (adaptador de armazenamento — Airtable attachment hoje)
    ├── observability/    (logs estruturados, métricas, correlation_id)
    └── tests/
```

Esta estrutura vive **dentro** do repositório atual (`magnata-holerite-splitter`),
não num repositório novo — nenhuma decisão de separação de repositório foi
tomada ou é necessária nesta fase.

---

## 4. Componentes Mínimos

| Componente | Responsabilidade | Entrada | Saída | Dependências | Falhas | Testes | Observabilidade |
|---|---|---|---|---|---|---|---|
| Serviço de ingestão | orquestrar `ReceberItemIngestao`→`DisponibilizarParaClassificacao` | payload da origem | Item de Ingestão + Arquivo(s) | validador, gerador de ID, hash, idempotência, adaptadores | payload inválido, origem não autorizada | unitário + integração | log de início/fim, `correlation_id` |
| Validador | checar metadados mínimos, tipo, tamanho | Item de Ingestão em `RECEBIDO` | `VALIDADO`/`REJEITADO` | política de tipos/tamanho (DEC-MOD01-004/010) | tipo não permitido, tamanho excedido | unitário | motivo de rejeição logado |
| Gerador de UUIDv7 | gerar identificador canônico interno | — | UUIDv7 | biblioteca (`DECISÃO TÉCNICA DE IMPLEMENTAÇÃO`) | colisão (praticamente nula) | unitário | — |
| Cálculo de hash | SHA-256 do conteúdo | bytes do Arquivo | hash | — | falha de leitura do conteúdo | unitário | — |
| Política de idempotência | reconhecer repetição/duplicidade | chave de idempotência (§9) | decisão: novo/existente/retomar | armazenamento de chaves recentes | janela de deduplicação mal calibrada | unitário + concorrência | log de deduplicação |
| Registro de Item de Ingestão | persistir o Item de Ingestão | Item validado | Item persistido (canônico) | adaptador de persistência | falha de gravação | integração | evento `ItemIngestaoRecebido`/`Validado` |
| Registro de Arquivo | persistir o Arquivo | bytes + metadados | Arquivo persistido (canônico) | adaptador de armazenamento | falha de storage | integração | evento `ArquivoExtraido` |
| Publicador/registrador de eventos | emitir eventos do catálogo (§7 de `MAGNATA_OS_MODULO_01_INGESTAO.md`) | fato ocorrido | evento registrado | envelope canônico | evento perdido | unitário | correlação entre evento e operação |
| Adaptador de armazenamento | abstrair onde o binário vive | bytes | referência de armazenamento | Airtable attachment (hoje) | indisponibilidade do storage | integração | log de latência de upload |
| Adaptador Airtable legado | converter canônico→legado | Item/Arquivo canônicos | registro em `Emails Savian`/`Arquivos`/`Processar Arquivos` | API do Airtable | Airtable indisponível/rate limit | integração | log de conversão, contagem de uso |
| Repositório/interface de persistência | abstrair leitura/escrita do Item/Arquivo | operações CRUD conceituais | dado persistido/lido | adaptador concreto (Airtable hoje) | inconsistência de leitura | integração | — |
| Logs estruturados | registrar fatos com campos fixos (§13 do plano de ingestão) | evento/erro/operação | linha de log estruturada | — | log verboso demais/de menos | revisão manual | é a própria observabilidade |
| Métricas | contadores/tempos (§19 do plano de ingestão) | eventos/operações | série temporal | sistema de métricas (a definir) | cardinalidade explosiva | revisão manual | dashboards (§15) |
| Comparador shadow × legado | comparar resultado shadow com legado (§10) | dois resultados (shadow, legado) | classificação de divergência | ambos os resultados disponíveis | comparação incorreta | unitário | log de divergência |
| Mecanismo de feature flag | ligar/desligar partes do módulo (§8) | nome da flag | ativo/inativo | armazenamento de configuração | flag inconsistente entre instâncias | integração | log de mudança de flag |
| Rollback | reverter para o legado puro (DEC-MOD01-009) | acionamento explícito | módulo novo desativado | feature flag (kill switch) | rollback incompleto | teste dedicado (§17) | log de acionamento, com ator |

---

## 5. Fase 0 — Instrumentação

**O que deve ser medido no fluxo atual** (upload manual, via `/separar` e
rotas equivalentes), sem tocar no comportamento:

Quantidade de uploads; quantidade de arquivos; tamanho; MIME; origem;
duração da operação; resposta HTTP (código **e** corpo — corrigindo o
achado de §2, onde HTTP 200 não implica sucesso); falhas (por código de
erro); duplicidades (por hash); hashes calculados; IDs externos observados
(`processar_arquivo_record_id`); registros criados (contagem por tabela);
divergência entre arquivo recebido e attachment salvo (bytes enviados vs.
bytes confirmados no Airtable); tempo até classificação (do upload até
`Processar Arquivos` mudar de `Pendente`); itens sem processamento
posterior (uploads que nunca geraram classificação).

**A instrumentação NÃO deve:**
- Alterar a resposta (mesmo corpo, mesmo status HTTP retornado hoje).
- Criar novo registro operacional (nenhuma tabela/campo do Airtable
  ganha uma escrita nova nesta fase).
- Impedir upload (nenhuma validação nova bloqueia uma requisição que hoje
  passaria).
- Mudar estado (nenhum `Status` de `Processar Arquivos`/`Arquivos`/
  `Emails Savian` é alterado pela instrumentação).
- Alterar nome de campo.
- Alterar fluxo de negócio.

**Implicação técnica:** a instrumentação da Fase 0 é, por definição,
**só leitura/observação** em cima do fluxo existente — um wrapper de
medição em volta das chamadas já existentes (ex.: medir tempo antes/depois
de `separar()` rodar, sem alterar o que `separar()` faz).

---

## 6. Fase 1 — Shadow Mode

**Comportamento definido, na ordem:**

1. Usuário realiza upload pelo fluxo atual (`/separar` ou equivalente) —
   nada muda do ponto de vista de quem faz upload.
2. O legado continua sendo o **único responsável** pelo efeito
   operacional (gravação real em `Processar Arquivos`/`Arquivos`).
3. Uma **cópia controlada** dos dados autorizados (o mesmo PDF, os mesmos
   metadados) alimenta o núcleo canônico, em paralelo.
4. O núcleo cria uma **representação shadow** de Item de Ingestão e
   Arquivo — persistida separadamente (§7), nunca nas tabelas operacionais.
5. **Nenhuma representação shadow aciona** classificação, distribuição ou
   assinatura — a fronteira de `MAGNATA_OS_MODULO_01_INGESTAO.md` §3 vale
   também aqui, e a saída do shadow nunca ultrapassa "Item de Ingestão +
   Arquivo criados", nunca dispara o próximo módulo de verdade.
6. O **comparador** (§10) verifica legado versus canônico para a mesma
   entrada.
7. **Divergências são registradas** (não descartadas, não silenciadas).
8. **Falha do shadow nunca impede o legado** — se o núcleo novo lançar
   exceção, o fluxo legado continua e retorna sua resposta normalmente ao
   usuário.
9. **Falha do legado nunca é ocultada pelo shadow** — o shadow não
   "conserta" nem mascara um resultado ruim do legado; ele só registra o
   que observou.
10. **Nenhum usuário recebe resultado do shadow como se fosse
    operacional** — a resposta HTTP ao chamador é sempre a do legado,
    nunca influenciada pelo que o shadow calculou.

---

## 7. Persistência do Shadow

**Opções avaliadas:**

| Opção | Prós | Contras |
|---|---|---|
| Tabela shadow no Airtable | reaproveita infraestrutura já em uso | risco de contaminar a mesma base operacional; ainda sujeito aos limites do Airtable que o Módulo 01 tenta não herdar |
| Armazenamento interno separado (ex.: banco relacional simples dedicado) | isolamento total do operacional; consultável com SQL | nova peça de infraestrutura a manter, mesmo que pequena |
| Banco já disponível (se existir algum não usado hoje) | reaproveita o que já existe | não há evidência, nesta sessão, de um banco relacional já disponível e ocioso |
| Arquivo estruturado temporário (ex.: log estruturado em disco/objeto) | mais simples de implementar rapidamente | pouco consultável para comparação em volume, sem índice |
| Combinação (log estruturado + tabela leve para agregados) | equilíbrio entre simplicidade e consulta | mais peças para manter que uma opção única |

**Recomendação objetiva:** **armazenamento interno separado**, isolado do
Airtable operacional — mesmo que simples (uma tabela relacional leve ou
equivalente), desde que:
- não contamine nenhuma tabela operacional do Airtable;
- seja consultável (permita comparar volume, divergências, por origem e
  por período);
- os dados sejam elimináveis (retenção definida, §15) ou migráveis, sem
  virar uma segunda fonte de verdade permanente;
- não haja confusão possível entre um registro shadow e um registro de
  produção — nomenclatura e localização física devem deixar isso óbvio
  (ex.: nunca no mesmo schema/base que os dados operacionais).

**Airtable continua sendo a fonte operacional do legado durante toda a
Fase 1** (DEC-MOD01-006) — a recomendação acima não contradiz isso, ela
só define onde o **resultado do shadow** (não o dado operacional) é
guardado.

**Nenhuma tabela é criada nesta etapa.**

---

## 8. Feature Flags

Flags independentes planejadas (nomes ilustrativos — finais definidos na
implementação):

- Observabilidade ativada (liga/desliga a instrumentação da Fase 0).
- Shadow ativado (liga/desliga a execução do núcleo em modo sombra).
- Origem "upload manual" ativada (permite ativar/desativar por origem,
  já preparando a entrada futura de Make.com/Gmail sem retrabalho).
- Persistência shadow ativada (permite rodar o núcleo sem gravar nada,
  útil para teste).
- Comparação ativada (liga/desliga o comparador, independente de o
  shadow estar rodando).
- Eventos shadow ativados (liga/desliga a emissão de eventos do shadow,
  §14).
- Adaptador legado ativado/desativado (controla se o adaptador de saída
  está operante — relevante só a partir da Fase 2, mas a flag já nasce
  aqui por completude).
- **Kill switch geral** — desliga tudo de uma vez, incondicionalmente,
  independente do estado das demais flags.

**Nenhuma flag foi implementada nesta etapa.**

---

## 9. Idempotência Técnica

**Composição conceitual da chave de idempotência para upload manual:**
origem (`UPLOAD_MANUAL`) + identificador externo, quando existir (ex.:
`processar_arquivo_record_id`, no caso de `/separar`) + hash do conteúdo +
tamanho + janela temporal (para não acumular chaves indefinidamente) —
usuário e contexto operacional como metadados auxiliares, não como parte
obrigatória da chave (upload manual pode não ter um "usuário" identificado
de forma confiável hoje).

**Comportamento definido:**

| Situação | Comportamento |
|---|---|
| Mesma requisição repetida (retry técnico do cliente) | reconhecida pela chave — não cria novo Item de Ingestão |
| Retry após timeout | reconciliado: verifica se a operação anterior completou antes de assumir que não completou (§16) |
| Gravação concluída com resposta perdida | tratado como "resultado incerto" (§16) — nunca assumido como falha nem como sucesso sem verificação |
| Dois uploads simultâneos (mesmo conteúdo) | o segundo reconhece o primeiro em andamento/concluído — não cria duplicata; se ambos chegarem exatamente ao mesmo tempo, um mecanismo de trava (ex.: constraint de unicidade na chave) decide qual "vence" |
| Mesmo hash em contextos distintos | **não é duplicidade automática** (DEC-MOD01-005) — o hash é sinal forte, mas o módulo verifica origem/contexto antes de decidir |
| Reprocessamento deliberado | exige um sinalizador explícito de intenção (equivalente a "nova solicitação", não "retry") — mecanismo exato de sinalização é `DECISÃO TÉCNICA DE IMPLEMENTAÇÃO` |

---

## 10. Comparador Shadow × Legado

**Dimensões de comparação:**

Arquivo presente (sim/não em ambos os lados); tamanho; hash; MIME; nome;
quantidade de anexos; origem; horário; registro criado (existência e
correspondência); erro (presença e tipo); resultado (sucesso/falha);
duração da operação.

**Classificação de divergência:** `INFORMATIVA`, `BAIXA`, `MÉDIA`, `ALTA`,
`CRÍTICA`.

**Regra central:** **toda divergência `CRÍTICA` bloqueia a saída do
shadow mode** (reforço direto de DEC-MOD01-012/013 — "divergência crítica"
é uma das situações que prorrogam o shadow mode).

**Regra de não-simetria:** o comparador **não exige** que o núcleo novo
reproduza um erro do legado para ser considerado "igual" — se o legado
falha e o núcleo novo teria sucesso (ou o inverso, com justificativa), isso
é classificado e registrado, não tratado automaticamente como defeito de
quem divergiu.

---

## 11. Modelagem de Dados Provisória

Estruturas conceituais (sem tabela, classe ou schema criado):

- **Item de Ingestão shadow** — mesma forma conceitual de
  `MAGNATA_OS_CONTRATOS.md` §4, marcado como shadow (§14).
- **Arquivo shadow** — mesma forma de §5 daquele contrato, marcado como
  shadow.
- **Execução shadow** — registro de que uma tentativa de processamento
  shadow ocorreu, com timestamp, origem, resultado técnico.
- **Resultado da comparação** — o veredito do comparador (§10) para um par
  legado×shadow específico.
- **Divergência** — cada item individual de diferença encontrada, com sua
  classificação (`INFORMATIVA` a `CRÍTICA`).
- **Erro** — reaproveita o Contrato de Erro (`MAGNATA_OS_CONTRATOS.md`
  §15), sem campo novo.
- **Evento** — reaproveita o Envelope de Evento (§14 daquele contrato),
  com o marcador de shadow (§14 deste documento).

---

## 12. Segurança

Planejado para a Fase 1 (upload manual):

- Autenticação da origem (quem pode chamar o endpoint de upload — hoje
  não confirmado como robusto para `/separar`, que aceita qualquer
  chamador com o multipart correto).
- Autorização (o chamador autenticado tem permissão para este tipo de
  operação).
- Tamanho máximo de 50 MB (DEC-MOD01-010).
- PDF apenas (DEC-MOD01-004).
- Validação de MIME **real** (não só extensão) — corrigindo o gap já
  identificado em `MAGNATA_OS_MODULO_01_INGESTAO.md` §11 (`/separar` hoje
  só avisa, não bloqueia, quando `Content-Type` diverge).
- Arquivo vazio (rejeitado explicitamente).
- PDF corrompido (tratado como falha de leitura, não como sucesso parcial).
- PDF protegido por senha (mesma via de falha de leitura; sem tratamento
  distintivo nesta fase).
- Nome inseguro (sanitização contra path traversal e caracteres de
  controle antes de qualquer persistência).
- Logs sem conteúdo sensível (§15).
- Retenção (do binário e dos dados shadow — §15/§7).
- Acesso ao attachment (controlado pela mesma política do Airtable
  operacional, já que o attachment em si continua lá — DEC-MOD01-006).
- Sanitização geral de entrada antes de qualquer processamento.
- **Integração futura** com verificação de malware — **não implementada
  nesta fase**, só o ponto de integração é reservado (entre validação e
  persistência do Arquivo, mesma posição já indicada em
  `MAGNATA_OS_MODULO_01_INGESTAO.md` §11).

---

## 13. Estratégia de Armazenamento

**Detalhamento da decisão de manter Airtable attachment operacionalmente
na Fase 1** (DEC-MOD01-003, DEC-MOD01-006):

| Aspecto | Definição |
|---|---|
| Armazenamento usado pelo legado | Airtable attachment — inalterado |
| Armazenamento/referência usada pelo shadow | **decisão a tomar nesta seção** — ver recomendação abaixo |
| Risco de upload duplicado | se o shadow também fizesse upload físico do mesmo PDF para o Airtable, dobraria o consumo de anexo por item — risco real a evitar |
| Custo | upload duplicado físico dobraria o custo de armazenamento do Airtable sem benefício operacional |
| Integridade | referenciar o mesmo attachment do legado garante que shadow e legado falam do mesmo byte-a-byte, sem risco de divergência de conteúdo |
| Rollback | mais simples se o shadow nunca escreveu nada no Airtable — só desligar a flag |
| Indisponibilidade | se o shadow depende do attachment já gravado pelo legado, uma indisponibilidade do Airtable afeta os dois igualmente, sem criar um caminho de falha exclusivo do shadow |
| Consistência entre registro e attachment | referenciar (não duplicar) elimina o risco de o registro shadow apontar para um attachment que nunca existiu de fato |

**Avaliação pedida — o shadow deve referenciar o attachment legado, ou ter
cópia isolada?**

**Recomendação objetiva: referenciar, não duplicar.** O shadow calcula seu
próprio hash a partir dos mesmos bytes recebidos na requisição (antes de
qualquer upload), e guarda uma **referência** ao registro/attachment que o
legado já criou (quando aplicável) — nunca faz um segundo upload físico do
mesmo conteúdo para o Airtable. Isso elimina o risco de custo duplicado e
de divergência de conteúdo, ao preço de o shadow depender da gravação do
legado ter ocorrido — risco aceitável, já que o shadow por definição só
existe **depois** que o legado já processou (§6, item 2).

---

## 14. Eventos Shadow

**Marcação para não parecerem fatos operacionais oficiais:**

- **Namespace:** eventos shadow usam o mesmo `event_name` do catálogo
  canônico (`MAGNATA_OS_EVENTOS.md`), mas o envelope carrega um indicador
  explícito de que é shadow (ver abaixo) — não se inventa um segundo
  catálogo de nomes de evento só para o shadow.
- **Metadata:** campo dedicado (ex.: `metadata.shadow = true`) presente em
  todo evento shadow, ausente (ou `false`) em todo evento operacional real.
- **Ambiente:** o evento carrega identificação do ambiente de execução,
  consistente com a flag de shadow ativa no momento.
- **Indicador `shadow`:** o mais importante — deve estar num local do
  envelope que **nenhum consumidor legítimo ignoraria por acidente** (não
  enterrado em um campo opcional qualquer).
- **Origem:** preservada normalmente (§2 de `MAGNATA_OS_MODULO_01_INGESTAO.md`).
- **`correlation_id`:** o shadow usa um `correlation_id` **próprio**,
  nunca o mesmo do fluxo legado que originou a cópia — evita que uma
  consulta por `correlation_id` do legado acidentalmente traga resultado
  shadow misturado.

**Proibição absoluta:** eventos shadow **nunca** são consumidos por
classificação operacional, distribuição, envio ou assinatura, nem geram
atualização do Airtable operacional — essas quatro proibições são a
tradução direta de §6, itens 5 e 9-10.

---

## 15. Logs e Métricas

**Campos obrigatórios de log** (todo log estruturado do módulo):
timestamp; nível; `correlation_id`; indicador shadow (sim/não); origem;
operação; resultado; duração; identificador da entidade afetada (quando
aplicável); erro (categoria/código, quando aplicável) — nunca o conteúdo
do arquivo, nunca token.

**Níveis:** `DEBUG` (detalhe técnico interno), `INFO` (fato de negócio —
eventos), `WARNING` (situação anômala não bloqueante), `ERROR` (falha).

**Métricas (contadores/tempos):** itens recebidos/validados/rejeitados;
duplicidades; falhas temporárias/definitivas; tempo médio de ingestão;
tamanho médio; volume por origem; divergência shadow×legado (por
categoria de §10); itens sem classificação posterior; reprocessamentos —
todas já listadas em `MAGNATA_OS_MODULO_01_INGESTAO.md` §19, reaproveitadas
aqui sem alteração.

**Correlação:** toda métrica e todo log devem poder ser cruzados por
`correlation_id`.

**Identificação shadow:** toda métrica tem uma dimensão "shadow: sim/não"
— nunca dados shadow e operacionais somados na mesma série sem
possibilidade de segregação.

**Alertas mínimos:** divergência crítica detectada; falha definitiva acima
de um limiar; ausência de métricas (o próprio pipeline de métricas
parando de reportar); Airtable indisponível.

**Dashboards mínimos:** volume por origem e por dia; taxa de falha
(temporária/definitiva); divergência shadow×legado por categoria;
progresso em relação aos critérios de saída de DEC-MOD01-012 (dias
decorridos, itens processados, divergências críticas abertas).

**Limite de cardinalidade:** dimensões de métrica devem evitar valores de
alta cardinalidade sem agregação (ex.: não usar `item_ingestao_id`
individual como dimensão de métrica — isso é log, não métrica).

**Retenção:** a definir junto com a política de retenção geral do shadow
(§7) — não fixada nesta etapa como número.

---

## 16. Tratamento de Resultado Incerto

| Caso | Tratamento |
|---|---|
| Attachment salvo, registro não criado | reconciliação: ao detectar o attachment órfão, verificar se o registro deveria existir e criá-lo (ou marcar para revisão), sem apagar o attachment |
| Registro criado, resposta perdida | reconciliação: cliente que não recebeu resposta pode reconsultar pela chave de idempotência (§9) — o registro já existente é retornado, não duplicado |
| Hash calculado, upload falhou | o hash isolado não vira Arquivo — a operação é tratada como incompleta, retomável (§8 de `MAGNATA_OS_MODULO_01_INGESTAO.md`, `FALHA_TEMPORARIA`) |
| Timeout do Airtable | tratado como falha técnica recuperável (`INGESTAO_ARMAZENAMENTO_INDISPONIVEL`), nunca como sucesso silencioso |
| Execução shadow interrompida | não afeta o legado (§6, item 8) — a execução shadow incompleta é descartada ou marcada como incompleta, sem gerar comparação com dado parcial |
| Comparação não executada | registrado como lacuna de cobertura (não conta como "sem divergência" — ausência de comparação não é evidência de paridade) |
| Resposta HTTP desconhecida (timeout de rede, conexão perdida) | tratado como resultado incerto — reconciliação necessária antes de assumir sucesso ou falha (reforço do achado de §2 sobre HTTP 200 não confiável isoladamente) |

**Princípio geral:** reconciliação **nunca apaga histórico** — um estado
incerto é resolvido adicionando o fato descoberto na reconciliação, não
substituindo o que já estava registrado (`MAGNATA_OS_ESTADOS.md` §13).

---

## 17. Rollback e Kill Switch

- **Desativar instrumentação (Fase 0):** flag "observabilidade ativada"
  desligada — o wrapper de medição para de rodar, o fluxo legado
  permanece 100% inalterado (já que a instrumentação nunca o alterou).
- **Desativar shadow (Fase 1):** flag "shadow ativado" desligada — o
  núcleo novo para de processar cópias, o legado continua sozinho.
- **Preservar dados já produzidos:** desligar uma flag **nunca apaga**
  dados shadow/métricas já gravados — rollback é sobre parar de gerar
  efeito novo, não sobre destruir histórico.
- **Impedir novos eventos shadow:** consequência direta de desligar a
  flag de shadow — sem execução, sem evento.
- **Garantir que o legado continue sozinho:** por construção (§6, itens
  2 e 8) — o legado nunca depende do shadow para funcionar, então
  desligar o shadow não exige nenhuma ação adicional sobre o legado.
- **Responsáveis:** o responsável técnico do módulo (a definir,
  `MAGNATA_OS_MODULO_01_INGESTAO.md` §17) aciona e confirma o rollback;
  a Direção da Magnata é informada.
- **Evidências de rollback:** log do acionamento (quem, quando, motivo),
  preservado como qualquer outro log estruturado.
- **Teste obrigatório do kill switch:** antes de qualquer ativação real em
  produção, o kill switch precisa ser exercitado em ambiente de teste,
  confirmando que ele de fato interrompe toda atividade do módulo novo
  sem exceção.

---

## 18. Testes Técnicos

**Unitários:** validação (tipo/tamanho); hash; geração de UUIDv7;
idempotência (reconhecimento de chave repetida); comparação (lógica do
comparador); classificação de divergência (mapeamento correto para
`INFORMATIVA`-`CRÍTICA`).

**Integração:** Airtable (leitura/escrita real em ambiente de teste);
attachment (upload/download real); endpoint legado (`/separar` chamado de
ponta a ponta); timeout; retry; persistência shadow.

**Concorrência:** dois uploads iguais simultâneos; gravação simultânea do
mesmo Item; retry concorrente (duas tentativas de retry disputando o
mesmo recurso).

**Segurança:** MIME falso; arquivo vazio; nome malicioso (path traversal,
caracteres de controle); PDF protegido; tamanho acima do limite.

**Shadow (combinações legado × shadow):** legado sucesso / shadow
sucesso; legado sucesso / shadow falha; legado falha / shadow sucesso;
ambos falham; divergência de hash; resposta perdida.

---

## 19. Dados de Teste

Conjunto controlado: PDF pequeno; PDF próximo de 50 MB; PDF corrompido;
PDF protegido por senha; mesmo PDF com nomes diferentes; PDFs diferentes
com mesmo nome; arquivo não-PDF; arquivo vazio; múltiplos uploads (mesmo
lote); caracteres especiais no nome.

**Todos sintéticos.** Nenhum documento real com dado pessoal é necessário
para nenhum destes casos — não usar holerite/documento real de
colaborador quando um PDF sintético já comprova o comportamento.

---

## 20. Plano de Implantação Futura

1. Adicionar observabilidade (Fase 0).
2. Validar sem mudar comportamento (confirmar que a instrumentação é
   inerte).
3. Adicionar feature flags (todas desligadas por padrão).
4. Implementar contratos internos (Item de Ingestão, Arquivo — conceituais
   viram estrutura de código).
5. Implementar núcleo shadow (lógica de validação, hash, idempotência).
6. Criar persistência shadow (armazenamento isolado, §7).
7. Implementar comparador.
8. Testar localmente.
9. Testar em ambiente isolado (staging, se existir; ou ambiente dedicado).
10. Ativar observabilidade em produção (Fase 0 real).
11. Ativar shadow para uploads internos/controlados primeiro (não todo
    tráfego de upload manual de uma vez).
12. Ampliar gradualmente até cobrir todo o tráfego de upload manual.
13. Medir critérios de saída (DEC-MOD01-012/013) continuamente.
14. Decidir Fase 2 — com aprovação formal (DEC-MOD01-012, último item).

**Cada passo possui rollback próprio** — nenhum passo avança sem que o
anterior possa ser revertido independentemente.

---

## 21. Critérios de Autorização para Codificação

Antes de escrever código, exigir aprovação explícita de: estrutura modular
(§3); persistência shadow (§7 — armazenamento interno separado); estratégia
de referência do attachment (§13 — referenciar, não duplicar); geração de
UUIDv7 (DEC-MOD01-011); chave de idempotência (§9); feature flags (§8);
métricas (§15); política de retenção (a fixar); plano de testes (§18-19);
rollback (§17); responsáveis; ambiente de teste.

---

## 22. Critérios de Saída do Shadow Mode

**Reproduzidos integralmente de `MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md`
DEC-MOD01-012 e DEC-MOD01-013 — nenhum número alterado.**

### Volume mínimo (cumulativo)
- Pelo menos 14 dias consecutivos de observação.
- Pelo menos 100 itens reais processados em shadow mode.
- Representação das origens que participarão da fase seguinte.
- Presença de casos com múltiplos anexos, repetição, falha e arquivo
  inválido, quando ocorrerem naturalmente ou por teste controlado.

### Critérios obrigatórios (cumulativo)
Zero perda de Arquivo; zero interrupção do fluxo legado; zero duplicidade
crítica produzida pelo núcleo novo; 100% dos itens com `correlation_id`;
100% dos itens com hash calculado ou erro explícito; 100% das falhas
registradas sem falso sucesso; todas as divergências classificadas;
nenhuma divergência crítica sem explicação; adaptador legado validado em
teste; rollback testado; métricas e logs disponíveis; aprovação formal da
Direção da Magnata e do responsável técnico.

### Critério de comparação
Paridade de recebimento; paridade de Arquivo; paridade de metadados;
divergência de hash; divergência de quantidade de anexos; divergência de
origem; divergência de resultado; falhas exclusivas do legado; falhas
exclusivas do shadow. **Não se exige que o núcleo novo reproduza um erro
do legado para atingir "paridade".**

### Situações que prorrogam o shadow mode (mesmo com critérios acima
nominalmente satisfeitos)
Perda de Arquivo; duplicidade não explicada; divergência crítica; falha de
correlação; erro silencioso; impossibilidade de rollback; ausência de
métricas; diferença estrutural ainda não tratada pelo adaptador; volume
insuficiente; origem prioritária não representada.

---

## 23. Arquivos que Poderão Ser Criados Futuramente

| Arquivo (ilustrativo) | Finalidade | Responsabilidade | Dependências | Testes associados |
|---|---|---|---|---|
| `ingestion/domain/item_ingestao.py` | modelo conceitual do Item de Ingestão | representar o Item e seu estado | contratos | unitário |
| `ingestion/domain/arquivo.py` | modelo conceitual do Arquivo | representar o Arquivo, versão, vigência | contratos | unitário |
| `ingestion/application/comandos.py` | os 4 comandos conceituais (§6 de `MAGNATA_OS_MODULO_01_INGESTAO.md`) | orquestrar a máquina de estados mínima | domain, contracts | unitário + integração |
| `ingestion/contracts/envelope.py` | envelope canônico de evento | estrutura comum a todo evento | — | unitário |
| `ingestion/adapters/legacy_adapter.py` | conversão canônico↔legado | isolar nomes de campo do Airtable | Airtable API | integração |
| `ingestion/adapters/storage_adapter.py` | abstração de armazenamento | hoje, delega ao attachment do Airtable | Airtable API | integração |
| `ingestion/observability/logging.py` | logs estruturados | campos fixos, `correlation_id` | — | revisão manual |
| `ingestion/observability/metrics.py` | métricas | contadores/tempos (§15) | sistema de métricas a definir | revisão manual |
| `ingestion/shadow/comparador.py` | comparador shadow×legado | classificar divergências (§10) | resultado shadow + legado | unitário |
| `ingestion/shadow/persistencia.py` | persistência isolada do shadow | armazenamento separado (§7) | storage a definir | integração |
| `ingestion/flags.py` | feature flags (§8) | ligar/desligar componentes | armazenamento de config | integração |
| `tests/ingestion/*` | suíte de testes (§18) | cobrir todos os cenários listados | — | — |

**Nenhum destes arquivos foi criado.**

---

## 24. Alterações Futuras no Legado

Menores alterações que **poderão** ser necessárias (não executadas agora):

- Espelhar o upload — capturar uma cópia dos bytes recebidos por
  `/separar` (ou equivalente) para alimentar o shadow, sem alterar o que
  a rota retorna.
- Gerar `request_id` — se a rota legada ainda não tiver um identificador
  técnico por requisição, adicionar isso é o menor passo possível sem
  mudar comportamento.
- Enviar dados ao núcleo shadow — um ponto de chamada adicional
  (síncrono ou assíncrono, a decidir na implementação) que não afeta o
  retorno da rota legada.
- Capturar resultado para comparação — armazenar o que o legado produziu
  (hash, registro criado, erro) de forma acessível ao comparador.
- Adicionar `correlation_id` — se ainda não existir, é pré-requisito para
  toda a observabilidade deste plano.
- Preservar a resposta atual — nenhuma das alterações acima pode mudar o
  corpo ou o código HTTP que o legado já retorna hoje, incluindo o
  comportamento hoje existente de `/separar` retornar HTTP 200 mesmo em
  erro (§2) — mudar isso é uma decisão à parte, fora deste plano.

**Nenhuma alteração foi executada.**

---

## 25. Riscos Técnicos

| Risco | Criticidade |
|---|---|
| Perda (Arquivo recebido sem persistência confirmada) | **Crítica** |
| Duplicidade (Item/Arquivo duplicado por falha de idempotência) | **Alta** |
| Inconsistência (registro shadow sem attachment correspondente, ou vice-versa) | **Alta** |
| Sobrecarga (shadow competindo por recursos com o legado no mesmo processo/servidor) | **Média** |
| Timeout (shadow atrasando ou sendo atrasado pelo legado) | **Média** |
| Custo do attachment (se, por engano, o shadow duplicar upload físico) | **Média** — mitigado pela recomendação de §13 (referenciar, não duplicar) |
| Impacto da instrumentação (Fase 0 introduzindo latência perceptível) | **Média** |
| Vazamento de dados (log/métrica expondo conteúdo sensível) | **Alta** |
| Shadow acionando efeito real por erro de implementação (violação de §6, item 5) | **Crítica** |
| Comparação incorreta (comparador classificando divergência errada, mascarando problema real) | **Alta** |
| Feature flag falhando (estado inconsistente entre instâncias) | **Média** |
| Rollback incompleto (parte do módulo continua ativa após acionamento) | **Crítica** |

---

## 26. Decisões Técnicas Ainda Necessárias

**Estado desta seção:** as 5 decisões abaixo, que permaneciam em aberto na
versão anterior deste plano, foram **fechadas pela Direção da Magnata em
2026-07-23**. Nenhuma decisão técnica bloqueia o início da codificação da
Fase 0. A tabela original é preservada abaixo, seguida do registro formal
de cada decisão.

| Decisão | Opções | Recomendação | Impacto | Bloqueava codificação? | Responsável |
|---|---|---|---|---|---|
| Biblioteca de geração de UUIDv7 | biblioteca padrão da linguagem, se disponível; biblioteca de terceiros | usar a opção mais madura/mantida disponível no ecossistema Python já em uso | baixo — troca de biblioteca não afeta o contrato | Fechada — ver DEC-MOD01-014 | Direção da Magnata |
| Mecanismo de configuração por ambiente do limite de tamanho | variável de ambiente; arquivo de configuração | variável de ambiente, consistente com `REDIS_URL`/outras já usadas no projeto (`celery_app.py:10`) | baixo | Fechada — ver DEC-MOD01-015 | Direção da Magnata |
| Armazenamento shadow concreto | banco relacional leve; outra opção de §7 | banco relacional leve dedicado, isolado do Airtable | médio — afeta o comparador e a consulta de métricas | Fechada — ver DEC-MOD01-016 | Direção da Magnata |
| Ponto exato de captura no legado (síncrono vs. assíncrono) para alimentar o shadow | chamada síncrona adicional dentro de `separar()`; captura assíncrona via fila | assíncrona, para não introduzir latência perceptível no fluxo legado (risco "Sobrecarga"/"Timeout" de §25) | médio | Fechada — ver DEC-MOD01-017 | Direção da Magnata |
| Sinalização de reprocessamento deliberado (§9) | campo explícito no payload; endpoint separado | campo explícito no payload, mais simples de auditar | baixo | Fechada — ver DEC-MOD01-018 | Direção da Magnata |

**Nenhuma decisão funcional já aprovada (`MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md`)
foi reaberta por esta lista.**

---

## DEC-MOD01-014 — Biblioteca de Geração de UUIDv7

**Decisão:** a geração de UUIDv7 fica **encapsulada atrás de uma função
única**, `generate_canonical_id()`, ainda a ser criada num módulo futuro de
identidade canônica. Nenhum ponto do código chama uma biblioteca de UUIDv7
diretamente — todos passam por essa função. A escolha da biblioteca
concreta por trás dela é um detalhe de implementação trocável sem impacto
em quem a consome.

**Escopo desta Fase:** **não é obrigatório implementar `generate_canonical_id()`
na Fase 0.** Esta decisão apenas remove o bloqueio para quando a primeira
entidade canônica (§ estratégia de identificadores, DEC-MOD01-011) precisar
gerar um ID — a Fase 0 de observabilidade não gera identidade canônica
(usa `secrets.token_hex`, observacional apenas, ver
`MAGNATA_OS_MODULO_01_FASE_0_OBSERVABILIDADE.md`).

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-23
**Documentos impactados:** nenhum arquivo de código nesta fase; relevante
para a futura criação do módulo de identidade canônica.

---

## DEC-MOD01-015 — Configuração do Limite de Tamanho por Ambiente

**Decisão:** o limite de tamanho (DEC-MOD01-010) será configurável através
da variável de ambiente **`MAGNATA_INGESTION_MAX_FILE_SIZE_MB`**, com
**valor padrão de 50** (mantendo o valor atual de `MAX_CONTENT_LENGTH`,
`app.py:62`, por continuidade operacional). Configuração ausente usa o
padrão; configuração presente e **inválida** (não numérica, negativa ou
zero) deve **falhar de forma explícita** na inicialização — nunca cair
silenciosamente para o padrão nem para um valor calculado.

**Escopo desta Fase:** esta decisão registra o mecanismo de configuração.
**Não altera o limite hoje em produção** (`app.py:62` permanece 50 MB) e
**não é implementada como código na Fase 0** (a Fase 0 é só observabilidade
— não mexe em validação de tamanho, que é comportamento de negócio já
existente e fora do escopo autorizado desta etapa).

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-23
**Documentos impactados:** nenhuma alteração de código nesta fase; relevante
quando a validação de tamanho for de fato migrada para leitura de ambiente.

---

## DEC-MOD01-016 — Armazenamento Shadow Concreto (Fase 1)

**Decisão:** a persistência shadow da Fase 1 usará **PostgreSQL**,
descartando explicitamente SQLite, armazenamento em arquivo JSON, e
tabelas adicionais dentro do próprio Airtable como opções concretas.
PostgreSQL foi escolhido por suportar concorrência real (múltiplos
workers Celery escrevendo shadow ao mesmo tempo), tipos de dado
apropriados para comparação estruturada, e por ser a opção mais madura
para uma futura migração de dado shadow para dado canônico.

**Escopo desta Fase:** esta é uma decisão de **arquitetura para a Fase 1**.
**Nenhum provisionamento de banco, nenhuma dependência nova, nenhuma
tabela é criada na Fase 0** — a Fase 0 não persiste shadow algum (ver
proibições explícitas em `MAGNATA_OS_MODULO_01_FASE_0_OBSERVABILIDADE.md`).

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata (custo/infra) + Responsável técnico
**Data:** 2026-07-23
**Documentos impactados:** nenhum nesta fase; referência obrigatória
quando a Fase 1 (shadow mode) for autorizada para codificação.

---

## DEC-MOD01-017 — Ponto de Captura para o Shadow (Fase 1)

**Decisão:** a futura captura de dado para o shadow (Fase 1) será
**assíncrona**, nunca uma chamada síncrona adicional dentro de `separar()`
ou equivalente. O byte do arquivo precisa ser capturado **antes** de
qualquer exclusão de arquivo temporário no fluxo legado, e repassado à
captura assíncrona por um mecanismo que não dependa da persistência do
arquivo temporário além do tempo de vida da requisição original. Em
nenhuma hipótese a captura shadow pode alterar o tempo de resposta nem o
corpo de resposta observado hoje pelo chamador de `/separar`.

**Escopo desta Fase:** esta decisão **não é implementada na Fase 0** — não
há shadow, não há captura de bytes para shadow, não há fila nova nesta
etapa. Fica registrada para orientar a Fase 1.

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-23
**Documentos impactados:** nenhum nesta fase; referência obrigatória para
o desenho de código da Fase 1 (§24 deste plano).

---

## DEC-MOD01-018 — Sinalização de Reprocessamento Deliberado

**Decisão:** reprocessamento **deliberado** (decidido por uma pessoa, ex.:
reenviar um documento que já foi processado antes por decisão operacional)
é sinalizado por um campo explícito no payload — **`reprocess_requested =
true`** — acompanhado de metadados de auditoria: **ator** (quem pediu),
**motivo**, **data**, e **referência** ao item original. Isso é
deliberadamente distinto de **retry técnico** (nova tentativa automática
após falha de rede/timeout/erro transitório), que não passa por este
campo e não exige os mesmos metadados de auditoria — são conceitos
diferentes e não devem ser confundidos no mesmo mecanismo.

**Escopo desta Fase:** esta decisão **não bloqueia nem é implementada na
Fase 0** (upload manual comum não depende disso imediatamente, conforme já
indicado na tabela original desta seção). Fica registrada para quando o
fluxo de reprocessamento deliberado for de fato desenhado.

**Decisão da Magnata:** `APROVADA`
**Responsável:** Direção da Magnata
**Data:** 2026-07-23
**Documentos impactados:** nenhum nesta fase; referência obrigatória
quando o mecanismo de reprocessamento deliberado (§9 do plano de
ingestão) for implementado.

---

**Conclusão desta seção:** com o fechamento de DEC-MOD01-014 a
DEC-MOD01-018, **nenhuma decisão técnica pendente bloqueia a codificação
da Fase 0 (Observabilidade)**. As 5 decisões acima são todas de escopo
Fase 1 ou de infraestrutura futura — a Fase 0, por ser puramente
observacional (sem UUIDv7, sem limite de tamanho novo, sem shadow, sem
reprocessamento), não depende de nenhuma delas para ser codificada.

---

## 27. Sequência para o Claude Code Implementar

Roteiro futuro de execução em pequenos commits — **não executado**:

1. Instrumentação read-only da Fase 0 (sem flag ainda, ou com flag
   sempre-ligada trivial) + testes.
2. Feature flags (todas desligadas por padrão) + testes.
3. Contratos internos (Item de Ingestão, Arquivo) como estruturas de
   código, sem persistência ainda + testes.
4. Gerador de UUIDv7 + testes unitários.
5. Cálculo de hash + testes unitários.
6. Política de idempotência (em memória/local, antes de persistência
   real) + testes de concorrência.
7. Persistência shadow (armazenamento isolado) + testes de integração.
8. Adaptador de armazenamento (referência ao attachment legado) + testes.
9. Publicador de eventos (com marcador shadow) + testes.
10. Comparador shadow×legado + testes unitários com casos fixos.
11. Logs estruturados + revisão manual de campos.
12. Métricas + revisão manual de dashboards mínimos.
13. Integração ponta a ponta em ambiente isolado (todos os componentes
    juntos, ainda sem tráfego real).
14. Ativação para upload manual controlado (Fase 1 real), com flag.
15. Kill switch testado explicitamente, isoladamente, antes de qualquer
    ampliação de tráfego.

**Cada commit futuro deve:**
- ter escopo único (um componente ou uma correção por commit);
- incluir testes no mesmo commit da funcionalidade;
- não misturar refatoração geral do legado com a construção do módulo
  novo;
- manter compatibilidade — nenhum commit desta sequência altera o
  comportamento observável do legado antes do passo 14, e mesmo a partir
  daí só sob a flag de shadow;
- permitir reversão individual (reverter um commit não deveria exigir
  reverter os anteriores).

**Nada desta sequência foi executado.**

---

## 28. Conclusão

- **Arquitetura proposta:** módulo interno desacoplado
  (`magnata_os/ingestion/`), dentro do monólito modular existente — não um
  microsserviço (§3).
- **Escopo da Fase 0:** instrumentação read-only do fluxo de upload manual
  atual, sem alterar resposta, estado, campo ou fluxo de negócio (§5).
- **Escopo da Fase 1:** núcleo shadow processando uma cópia do upload
  manual, sem efeito operacional, comparado ao legado, sem nunca impedir
  ou mascarar o legado (§6).
- **Decisões fechadas:** as 13 de
  `MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md` (v1.1) — nenhuma
  reaberta aqui.
- **Decisões abertas:** 5 decisões técnicas de implementação (§26), todas
  bloqueando codificação mas nenhuma bloqueando o planejamento em si.
- **Riscos:** 12 classificados (§25), com 4 críticos (perda de Arquivo,
  shadow acionando efeito real, comparação incorreta mascarando problema,
  rollback incompleto).
- **Critérios para autorizar código:** os 12 itens de §21.
- **Critério de saída do shadow:** reproduzido integralmente de
  DEC-MOD01-012/013 em §22, sem alteração de número.

---

## Confirmação de Escopo

Nenhum arquivo além dos dois autorizados
(`MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md` e
`MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1.md`) foi criado ou alterado.
Nenhum código, tabela do Airtable, configuração, memória, endpoint, classe
ou dependência foi criado, alterado ou instalado. Nenhuma flag, UUID ou
dashboard foi implementado. Nenhum commit foi feito. O shadow mode não foi
iniciado. A produção não foi alterada. Este plano não deve ser tratado como
execução concluída.

---
