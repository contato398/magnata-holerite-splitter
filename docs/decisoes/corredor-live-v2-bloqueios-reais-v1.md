# Corredor Live V2 — Fechamento de Bloqueios Reais — V1

Documento de decisão da missão macro "MERGE PR #108 + FECHAR BLOQUEIOS
REAIS DO CORREDOR LIVE V2 + REVISÃO ADVERSARIAL PRÉ-ENTREGA". Sobre o
PR #108 (mesclado a `main`, HEAD `6ac9a7d8fbd1fe14f0daf951928657114a671bbb`).
Branch: `fix/corredor-live-v2-bloqueios-reais`.

## 0. Objetivo e método

Atacar de forma integrada os 5 bloqueios nomeados que mantêm
`READY_FOR_LIVE_CORRIDOR_V2 = FALSE` (docs/decisoes/adapters-reais-
unidade-posto-candidatos-relacao-v1.md §6): (1) `cliente_direto` de
produção para Extrato; (2) idem para FGTS Guia; (3) fonte/persistência
real de `DadosCorrelacaoDocumental`; (4) escopo temporal real para
candidatos históricos; (5) wiring entre essas capacidades e o corredor
real.

Método: auditar a FAMÍLIA inteira do problema antes de tocar código
(§1 da missão) — os resultados da auditoria estão na seção 1; as
decisões de implementação (o que foi CONSTRUÍDO com evidência real vs.
o que foi honestamente registrado como bloqueado por gate
constitucional) estão nas seções 2-5.

## 1. Auditoria

### 1.1 `cliente_direto` — mapa completo (§3 da missão)

Busca completa (`grep -rn cliente_direto`) confirma:

- `ContextoResolucaoDocumentoPrestacao.cliente_direto` (`resolucao_
  documento_prestacao.py`) é um VALOR pré-resolvido, injetado por quem
  orquestra — nunca uma fonte consultada durante a resolução de
  dimensões (mesmo padrão de `fonte_vinculos`/`fonte_unidade_posto`,
  mas estes SÃO fontes; `cliente_direto` é intencionalmente um valor
  já pronto).
- `perfil_aplicabilidade_documental.py` usa `cliente_direto` só para
  granularidade cliente (Extrato, FGTS Guia — `_perfil_granularidade_
  cliente`); nunca para granularidade colaborador (cliente é DERIVADO
  do vínculo) nem broadcast (`NAO_APLICAVEL`).
- **O único preenchimento real hoje** é via `separacao_documental.
  estrategia_por_cnpj_cliente`, através do hook `personalizar_
  contexto_do_grupo` de `processar_documento_com_separacao_se_
  necessaria` — usado quando um documento MASTER é separado por CNPJ
  (identidade derivada da ESTRUTURA do próprio documento, real,
  correta). **Confirmado por busca: `personalizar_contexto_do_grupo`
  só é chamado em arquivos de teste** — nenhum wiring de produção o
  invoca hoje.
- **`ContextoResolucaoDocumentoPrestacao(` só é construído em arquivos
  de teste, em TODO o repositório.** Achado maior desta auditoria: não
  existe, hoje, NENHUM orquestrador de produção real que chame
  `processar_documento_prestacao`/`processar_documento_com_separacao_
  se_necessaria` com dados reais — o corredor inteiro de `classificacao/`
  é, até esta missão, um motor completo na INTERFACE, nunca ligado a
  uma execução real ponta-a-ponta. Isso é maior que "falta 1 adapter" —
  é a causa raiz honesta por trás de "wiring" (bloqueio #5).

### 1.2 Descoberta paralela: pipeline de importação em lote JÁ resolve cliente real

`magnata_os/documental/importacao_lote/` (módulo DIFERENTE, mais
antigo, com orquestrador real — `orquestrador.processar_extrato`) já
tem, em produção, exatamente a capacidade que faltava:

- `LeitorAirtableSomenteLeitura.listar_clientes()` (`adapters/
  airtable_leitura.py`) lê CNPJ + Nome reais de `TABLE_CLIENTES` —
  já usado por `processar_extrato`.
- `dominio.resolver_cliente(linha_bruta, nome_manifesto, candidatos)`
  (função PURA, já testada): CNPJ extraído do texto SEMPRE tentado
  primeiro; `EXACT`/`AMBIGUOUS`/`CONFLICT`/`NOT_FOUND` explícitos,
  nunca decide por nome quando há CNPJ candidato.

Isso já é precedente estabelecido nesta sessão: `classificacao/
separacao_documental.py` já importa funções puras de `importacao_lote.
dominio` (`extrair_cnpjs_de_texto`, `extrair_cpfs_distintos_de_texto`).
Reaproveitar `resolver_cliente` da mesma forma NÃO é uma decisão
arquitetural nova — é aplicação consistente de uma já feita.

### 1.3 Escopo histórico real (§13 da missão)

`FonteInventarioPrestacaoAirtableShadow.listar()` (`adapters/airtable_
inventario_prestacao.py`) já busca TODOS os registros de Extrato/FGTS
de uma "Folha Mensal" (competência) via Airtable, e só DEPOIS filtra
por 1 cliente, em Python (`filter_by_formula` usa só a folha; o filtro
de cliente acontece no `for registro in registros if cliente.entidade_
id in ...`). Isso significa que a MESMA leitura real já em produção
permite agregar "todo cliente com QUALQUER registro nesta competência"
— evidência real, nunca "ativos hoje" (`Status`), nunca uma tabela
nova.

Guias/DCTFWeb fica de fora dessa agregação: essa tabela nunca carrega
vínculo de cliente no Airtable (é broadcast por desenho, `perfil_
aplicabilidade_documental.py`) — incluir um cliente aí seria inventar
evidência que a tabela não tem.

### 1.4 `dados_correlacao` — persistência (§9/§10/§12 da missão)

Auditoria completa de armazenamento existente:

- `magnata_os/documental/modulo01/` tem um schema Postgres REAL e já
  desenhado (`documentos`, `eventos_documentais` append-only,
  `lotes_documentais`, `estados_esteira_documental`, `itens_
  importacao_lote`) — mas seu próprio `migrations/CLAUDE.md` afirma
  explicitamente: **"Nenhuma migration é aplicada por este projeto
  ainda — são definição de schema para um adapter futuro, não
  executadas automaticamente por nenhum código hoje."**
- `magnata_os/orquestrador/migrations/0001_repositorio_execucoes.sql`
  tem, no próprio cabeçalho: **"INERTE: nenhum módulo aplica esta
  migration automaticamente. Provisionar banco, fornecer secret e
  aplicar schema exigem gates humanos separados."**
- Nenhum dos dois schemas modela `DadosCorrelacaoDocumental` por
  `documento_id` hoje — mesmo se estivessem live, precisariam de uma
  tabela/coluna NOVA.
- `app.py` não referencia nenhum desses módulos — confirmando que
  também não há acoplamento com o legado.

**Conclusão de auditoria**: não existe hoje NENHUM lugar já conectado
para persistir `DadosCorrelacaoDocumental`. Criar um exigiria uma
migration nova — e tanto `/CLAUDE.md` §12-I ("migration/schema
relevante" é gate humano que "§12 nunca dispensa") quanto a própria
convenção deste repositório ("se já foi commitado, trate como
aplicado") tratam a CRIAÇÃO de uma migration nova como uma decisão que
cruza um gate humano, não uma decisão técnica local. **Registrado como
BLOCKED, não implementado nesta missão** — ver seção 3.

## 2. Implementado — evidência real, sem gate cruzado

### 2.1 `FonteEscopoClientesPorInventarioAirtableShadow` (fecha bloqueio #4)

`magnata_os/documental/importacao_lote/adapters/airtable_inventario_
prestacao.py`. Implementa `FonteEscopoClientesPrestacao.escopo_para_
competencia` sobre os MESMOS 2 vínculos de cliente já lidos em
produção (Extrato/`F_EXT_CLIENTE`, FGTS/`F_FGTS_CLIENTE`) — nenhuma
tabela nova, nenhum campo novo. Agrega o conjunto de clientes que
aparecem em QUALQUER registro da folha pedida, nunca "ativos hoje".
Nunca consulta `Status`. Guias/DCTFWeb fica de fora (sem vínculo de
cliente no Airtable, ver 1.3).

Testado (`test_airtable_inventario_prestacao.py`, 5 casos novos): 2
tabelas reais consultadas na ordem certa; dedup de cliente com registro
em Extrato E FGTS; competência sem nenhum registro devolve vazio;
rejeita referência que não é COMPETENCIA; cliente hoje inativo mas com
registro histórico é encontrado (a fonte nem lê `Status`).

### 2.2 `FonteClienteDiretoDocumento` + adapter real (fecha bloqueios #1 e #2)

Capacidade COMPARTILHADA (§7 da missão) — um Protocol só, um adapter
só, para Extrato E FGTS Guia (as 2 famílias hoje cadastradas em
`_perfil_granularidade_cliente`):

- `magnata_os/classificacao/fonte_cliente_direto_documento.py` —
  Protocol puro, `resolver_cliente_direto(texto_documento) ->
  Optional[ReferenciaCanonica]`.
- `magnata_os/documental/importacao_lote/adapters/airtable_cliente_
  direto_documento.py` — `FonteClienteDiretoDocumentoAirtableShadow`,
  reaproveita (nunca reimplementa) `LeitorAirtableSomenteLeitura.
  listar_clientes()` + `dominio.resolver_cliente` (ver 1.2).

Regra pétrea aplicada (§4 da missão): só CNPJ extraído do PRÓPRIO
TEXTO do documento, batendo EXATAMENTE 1 cliente cadastrado, resolve —
checagem EXPLÍCITA (`criterio_usado == 'cnpj_exato'`), nunca implícita
via `nome_manifesto=''`. Nome de cliente NUNCA é evidência aqui (risco
de falso positivo por substring contra texto integral de PDF — ao
contrário de um campo de manifesto estruturado). CNPJ ausente, CNPJ
desconhecido, ou 2+ CNPJs de clientes DIFERENTES no mesmo texto — os 3
casos devolvem `None`, nunca um palpite.

Testado (`test_airtable_cliente_direto_documento.py`, 11 casos —
casos A-H dos §17/§18 da missão, para Extrato E para FGTS Guia com o
MESMO adapter): CNPJ comprovado resolve; sem CNPJ nunca resolve;
resolve igual para competência histórica (nenhum acoplamento
temporal); rótulo/tipo sozinho nunca resolve; 2 CNPJs de clientes
diferentes nunca resolve; CNPJ desconhecido nunca resolve; retorno é
estruturalmente `Optional[1 cliente]`, nunca coleção (broadcast
estruturalmente impossível); reusa só `listar_clientes()`, nenhuma
tabela nova; blindagem explícita contra aceitar um match por nome
mesmo que a função reaproveitada algum dia devolvesse isso.

### 2.3 Wiring real (fecha bloqueio #5 no nível seguro desta missão)

`test_magnata_os_classificacao_e2e_bloqueios_corredor_live_v2.py` (5
casos): prova que os 2 adapters acima compõem, SEM AJUSTE, com o
corredor já existente — texto de Extrato/FGTS Guia com CNPJ real →
`cliente_direto` resolvido → `processar_documento_prestacao` avança
automaticamente; sem CNPJ, nunca inventa, nunca avança; escopo
histórico real → `FonteCandidatosRelacaoDocumentalDoInventario` →
`resolver_relacao_e_avancar`, candidato real encontrado só pela
evidência real do Airtable.

**Isso NÃO é um orquestrador de produção novo.** Dado o achado de 1.1
(nenhum orquestrador real existe hoje para todo o corredor
`classificacao/`), construir um entrypoint de produção real (lendo PDF
real, chamando Airtable real, ponta-a-ponta) seria uma peça
arquitetural nova e material, fora do que esta missão especificou
(capacidades/adapters, não um novo orquestrador) — **registrado como
pendência, não fabricado sem gate humano separado** (ver seção 4).

## 3. Bloqueado — gate constitucional, não implementado

### `dados_correlacao` — persistência (bloqueio #3, permanece BLOCKED)

Ver auditoria 1.4: nenhum lugar já conectado existe. A menor extensão
coerente seria uma tabela nova (`documentos_correlacao_prestacao` ou
equivalente), com colunas exatamente pelo §10 da missão (`documento_id`
PK, `competencia`, `identificador_pedido`, `valor_total_normalizado`,
`data_relevante`, `fornecedor`, `correlation_id`) — nunca PDF bruto,
texto integral, CPF, nome de colaborador, payload bancário ou segredo.

**Proposta, NÃO aplicada** (nenhum arquivo `.sql` criado nesta missão):
uma migration nova em `magnata_os/documental/modulo01/migrations/`
(ou schema próprio do corredor de prestação, a decidir), seguindo a
mesma disciplina já usada (`CREATE TABLE IF NOT EXISTS`, comentários
`COMMENT ON`, sem edição de migration existente). Isso cruza,
explicitamente, o gate de `/CLAUDE.md` §12-I ("migration/schema
relevante" — nunca dispensado por autonomia) e a própria convenção
deste repositório de tratar migration commitada como aplicada — por
isso não foi criada nesta missão sem confirmação humana separada e
específica sobre ela.

`FonteDadosCorrelacaoDocumental` (Protocol) e `FonteDadosCorrelacaoEm
Memoria` (referência local) permanecem exatamente como estavam —
`Optional[...] = None` no construtor de `FonteCandidatosRelacaoDocumental
DoInventario`, nunca exigindo um fake obrigatório. Sem uma
implementação real, candidatos continuam sendo descobertos com
identidade real, mas a relação correspondente cai honestamente em
`NAO_ENCONTRADA` — comportamento intocado.

## 4. Wiring de produção — pendência nomeada (não fabricada)

Achado de 1.1: não existe, em nenhum lugar do repositório, um
orquestrador real que construa `ContextoResolucaoDocumentoPrestacao`
fora de teste. Fechar isso de verdade significa: ler um PDF real
(hoje: `_extrair_texto_pdf`, já usado por `importacao_lote/
orquestrador.py`), montar o contexto com os adapters reais (UNIDADE_
POSTO, cliente_direto, escopo de candidatos — todos já reais após esta
missão), e chamar `processar_documento_prestacao`/`resolver_relacao_e_
avancar` de verdade, uma vez por documento processado.

Isso é uma peça de integração NOVA e MATERIAL — decisão de onde ela
mora (dentro de `importacao_lote/orquestrador.py`? um orquestrador novo
específico do corredor `classificacao/`? uma extensão do "Grande
Orquestrador" já desenhado em `magnata_os/orquestrador/`?) não foi
tomada aqui, unilateralmente — fica registrada como pendência para uma
missão futura com esse escopo explícito.

## 5. Holerite — reavaliação (§14/§15/§16 da missão)

`pacote_prestacao.py` já mapeia `EstadoPrestacaoReadiness.FALTANDO ->
EstadoPacotePrestacao.INCOMPLETO` (nunca `PRONTO`) — confirmado por
leitura direta do código, não é uma suposição. Isso significa que a
distinção pedida pela missão já é estrutural, sem precisar de nenhuma
mudança de código: **VALIDAR CLASSIFICAÇÃO/COMPETÊNCIA/INVENTÁRIO
nunca depende de VALIDAR RELAÇÃO HISTÓRICA (UNIDADE_POSTO) para
produzir um resultado honesto** — um documento sem vigência comprovada
de UNIDADE_POSTO cai em `NAO_ENCONTRADA`/`INCOMPLETO`, nunca crasha,
nunca finge `PRONTO`.

**Nenhuma métrica/flag nova criada** (§15 da missão: "não criar
métrica nova se contrato existente já representa isso") — a distinção
LAB / LIVE_READONLY_VALIDATION / AUTOMATED_PRESTACAO é só DOCUMENTADA
aqui e no relatório final, nunca um enum/campo novo no código: os
estados que já existem (`RESOLVIDA`/`NAO_ENCONTRADA`/`INCOMPLETO`/
`EM_REVISAO`) já bastam para representar "validação read-only honesta"
sem qualquer alteração.

## 6. `READY_FOR_LIVE_CORRIDOR_V2` — reavaliado por família e por propósito

| Família | LAB | LIVE_READONLY_VALIDATION | AUTOMATED_PRESTACAO |
|---|---|---|---|
| Holerite | READY | READY — corredor roda contra dados reais, UNIDADE_POSTO honestamente `NAO_ENCONTRADA` sem prova de vigência | PARTIAL — política de vigência para ciclo corrente ainda não decidida (quem fornece `competencia_snapshot_comprovada` real e quando) |
| Extrato | READY | READY — `FonteClienteDiretoDocumentoAirtableShadow` real, nunca inventa | BLOCKED — sem orquestrador de produção (seção 4) |
| FGTS Guia | READY | READY — mesmo adapter compartilhado | BLOCKED — mesma causa |
| Relação documental | READY | READY — escopo histórico real (2.1); `dados_correlacao` ausente cai honestamente em `NAO_ENCONTRADA`, nunca crasha (§16 da missão: honesto é suficiente para validação) | BLOCKED — `dados_correlacao` sem persistência (seção 3) + sem orquestrador (seção 4) |

**`READY_FOR_LIVE_CORRIDOR_V2` permanece `FALSE`** — bloqueios reais e
comprovados restantes, nenhum deles dispensável por autonomia (todos
cruzam gate de `/CLAUDE.md` §12-I ou §6):

1. Nenhum orquestrador de produção real existe para o corredor
   `classificacao/` (achado maior desta auditoria, seção 1.1/4) —
   mudança arquitetural material, precisa de escopo próprio e decisão
   humana de onde morar.
2. `dados_correlacao` sem persistência real — exige migration/schema
   novo, gate humano permanente (§12-I), nunca dispensado.
3. Política de vigência do snapshot de UNIDADE_POSTO para o ciclo
   corrente (quem prova, quando) ainda não decidida.

Como consequência direta (§23 da missão: "se FALSE, nomear somente
bloqueios restantes; se TRUE, produzir plano de autorização live"),
**este documento não produz `PLANO_AUTORIZACAO_LIVE_SKY_V1`** — a
condição para produzi-lo (`READY_FOR_LIVE_CORRIDOR_V2 = TRUE`) não foi
alcançada. Dito isso, a tabela acima registra, honestamente, que
`LIVE_READONLY_VALIDATION` está em `READY` para as 4 famílias — um
patamar novo e real, que pode justificar uma missão futura com esse
escopo explícito (ver relatório final, "PRÓXIMA MACRO-MISSÃO").

## 7. Revisão adversarial (§2/§28 da missão)

Aplicada ao diff desta missão (2 arquivos novos de produção + 1 classe
nova num arquivo já real + 3 arquivos de teste):

- snapshot atual usado como prova histórica? Não — `FonteEscopoClientes
  PorInventarioAirtableShadow`/`FonteClienteDiretoDocumentoAirtableShadow`
  usam a competência PEDIDA (folha) ou CNPJ intrínseco ao texto, nunca
  "hoje".
- competência do runner confundida com vigência da fonte? Não — nenhuma
  das 2 classes novas recebe/usa `ContextoCicloPrestacao`.
- source label/tabela usada como identidade semântica? Não — CNPJ do
  texto/cadastro, nunca nome de tabela.
- contrato depende só de docstring? Não — `criterio_usado == 'cnpj_
  exato'` é checagem estrutural; exclusão de Guias/DCTFWeb do escopo é
  estrutural (a tabela nunca é consultada), não um comentário.
- outro arquivo repetindo a mesma falha conceitual? Varredura global
  (`ContextoCicloPrestacao`/`competencia_base`/`listar_ativos`/
  `snapshot`/`historico`/`vigencia`/`as_of`/`competencia_comprovada`/
  `competencia_snapshot` em todo `magnata_os/`) confirma: o único uso
  de `listar_ativos(contexto)` fora do já corrigido é `ciclo_prestacao.
  executar_ciclo_prestacao` — uso LEGÍTIMO (define "quem está sendo
  processado NESTE ciclo", nunca reivindica prova histórica para outra
  competência; `competencias_por_cliente` chega PRONTO de fora,
  "competência entra uma vez na borda"). Nenhuma nova ocorrência do
  mesmo erro encontrada.
- teste reproduzindo suposição errada do código? Não identificado —
  todos os testes novos verificam contra o comportamento REAL
  (`filter_by_formula` exato, ordem de chamadas, ausência de consulta a
  `Status`/Guias).
- adapter decidindo regra de negócio que deveria ficar no core? A
  checagem `criterio_usado == 'cnpj_exato'` é qualidade de EVIDÊNCIA
  (nunca aceitar nome como prova), não regra de elegibilidade de
  cliente — mesma disciplina já aplicada ao gate temporal de UNIDADE_
  POSTO (também no adapter).
- core passou a depender de Airtable? Não — os 2 adapters reais vivem
  em `importacao_lote/adapters/`; o novo Protocol em `classificacao/`
  é puro (confirmado por `test_magnata_os_classificacao_arquitetura_
  sem_dependencia_airtable.py`, 5/5 passando).
- first-match arbitrário? Não — CONFLICT (2+ CNPJs de clientes
  diferentes) tratado explicitamente, nunca "pega o primeiro".
- fallback que inventa cliente/competência/vínculo? Não.
- campo Optional mascarado? `fonte_dados_correlacao` continua
  `Optional[...] = None`, comportamento intocado.
- duplicação de capacidade já no legado? `app.py::construir_mapa_
  cliente` resolve cliente por PÁGINA de um documento MASTER
  (separação); o adapter novo resolve cliente de um documento ÚNICO,
  já separado — escopo diferente, zero duplicação, e a função pura
  reaproveitada (`resolver_cliente`) é a MESMA usada pelo pipeline real
  de Extrato, nunca uma reimplementação.

Nenhum achado exigiu correção adicional.

## 8. Preservado (confirmado, nenhum arquivo tocado além do listado)

`EscopoClientesFixo`/`EscopoClientesAtivosDoCiclo`/`competencia_
snapshot_comprovada` (UNIDADE_POSTO) intocados; `FonteCandidatosRelacao
DocumentalDoInventario` intocada (só ganhou um novo consumidor real de
`fonte_escopo_clientes`); `VINCULO` `NAO_APLICAVEL`; Extrato/FGTS
Guia/relação documental continuam sem escrita real em nenhum lugar;
`app.py` intocado; zero Airtable no core; zero migration aplicada.

## 9. Regressão

1336 passed (era 1315 no HEAD pós-merge do PR #108), 34 falhas/17 erros
pré-existentes idênticos ao baseline (pdfplumber/cryptography do
sandbox — nada relacionado), 6 skipped. `test_magnata_os_classificacao_
arquitetura_sem_dependencia_airtable.py`: 5/5.
