# Identidade temporal do PDF de Folha/Cartão de Ponto — auditoria e proposta arquitetural (v1)

**Data:** 2026-09-03
**Branch:** `fix/identidade-temporal-ponto-auditoria-v1`
**Base:** `main @ 8c278b9cc3343122b454cb2f7c7879cebd6ac6e0` (PR #125 mesclado)
**Status:** 📋 Auditoria + proposta arquitetural — **nenhuma implementação de produção**, conforme escopo da missão.

## Contexto

O PR #125 confirmou, por auditoria, que:
1. registros diários de ponto/batidas (Secullum) não são o documento;
2. o documento real (PDF "Cartão Ponto") existe hoje anexado no legado;
3. o campo legado (`PDF Folha Ponto`) não tem granularidade confiável de competência por anexo;
4. existe lógica de extração de período (`extrair_cartao_ponto`) não integrada ao fluxo canônico;
5. a solução não deve aumentar dependência do Airtable.

Esta missão responde: **qual é o menor lugar canônico no Magnata OS
onde a identidade temporal desse PDF deve morar?**

## Fase 0 — Auditoria (caminho + função/classe real)

| # | Item pedido | Caminho real | O que é |
|---|---|---|---|
| 1 | Extrator de período | `app.py:768` `extrair_cartao_ponto`; `app.py:759` `_LINHA_CARTAO_PONTO_RE`; `app.py:762` `_PERIODO_CARTAO_PONTO_RE` (regex `Período: dd/mm/aaaa até dd/mm/aaaa`) | Extrai período REAL do texto do PDF — **"ainda NÃO usada em produção"** (docstring literal do próprio `app.py`) |
| 2 | Classificador/produtor de evidência de Ponto | `magnata_os/classificacao/classificador_documental.py:192-197` (regex "Folha de Ponto"/"Cartão de Ponto"); `magnata_os/classificacao/produtores_evidencia_ponto.py` (`TIPO_FOLHA_DE_PONTO`, `hipoteses_estruturais_de_ponto`, `_PADRAO_PERIODO_PONTO`) | Já reconhece o tipo documental E tem evidência estrutural de período (fraca) — pronto, não precisa de novo classificador |
| 3 | `ResultadoResolucaoSemantico` | `magnata_os/classificacao/contratos.py` | Já existe — carrega `resolucoes: Tuple[ResolucaoDimensao]` por dimensão (CLIENTE/COMPETENCIA/TIPO_DOCUMENTAL/COLABORADOR), `estado_consolidado`, `necessita_revisao_humana` |
| 4 | `ItemInventarioPrestacao` | `magnata_os/classificacao/prestacao_readiness.py:41` | Já existe — `documento_id`, `tipo_documental`, `cliente`, `competencia`, `colaborador` opcional |
| 5 | Adaptador `ResultadoResolucaoSemantico -> ItemInventarioPrestacao` | `magnata_os/classificacao/adaptador_inventario_prestacao.py::resultado_semantico_para_item_inventario` | **Já pronto e genérico** — nunca conhece tipo por nome, já suporta Folha de Ponto sem alteração |
| 6 | Mecanismo canônico de competência documental | `magnata_os/classificacao/resolucao_semantica.py::resolucao_competencia_de_validacao` (traduz `validar_competencia`, `importacao_lote/dominio.py`, já pura) | Já existe, genérico a qualquer tipo — nunca assume Holerite |
| 7 | Vínculo/alocação histórica | `magnata_os/classificacao/vinculos_prestacao.py::resolver_clientes_validado` (Protocol, shadow/Airtable hoje) **+** `magnata_os/documental/alocacao/` (`vinculo_trabalhista`, `alocacao` — **Postgres real, com vigência histórica**, ainda não conectado a um banco real) | **Achado central**: já existe um modelo Postgres MADURO de vínculo histórico (`vigente_de`/`vigente_ate`, sem sobreposição, migration `0001_criar_vinculo_trabalhista_e_alocacao.sql`) — hoje não é a fonte usada por `FonteVinculosPrestacao` (que ainda lê Airtable-shadow), mas é exatamente o destino correto de longo prazo |
| 8 | Postgres próprio já existente | `magnata_os/documental/modulo01/adapters/postgres_repositorio.py` (`documentos`, `eventos_documentais`); `magnata_os/documental/alocacao/adapters/postgres_alocacao.py` (`vinculo_trabalhista`, `alocacao`) | Ambos reais, com migrations versionadas — nenhum conectado a um Postgres de produção ainda (gate humano separado, fora desta missão) |
| 9 | Modelo/repositório de documento já existente | `magnata_os/documental/modulo01/dominio.py::Documento` (`documento_id`, `hash_sha256` UNIQUE, `origem`, `status`, `lote_id`) + `EventoHistorico` (append-only, trigger de banco bloqueia UPDATE/DELETE) | **A entidade documental canônica do Magnata OS** — sem colaborador/cliente/competência/período hoje |
| 10 | Estruturas de documento/origem/hash/competência/colaborador/cliente/unidade/período/evidência/auditoria | Documento+EventoHistorico (9); `ReferenciaCanonica` (`classificacao/contratos.py`, tipo+id opaco, usado para COLABORADOR/CLIENTE/UNIDADE_POSTO/COMPETENCIA); `EvidenciaSanitizada` (`contratos.py`) | Todos os conceitos já têm um tipo Python puro correspondente — nenhum precisa ser inventado |
| 11 | Migration/modelo que suporte isso sem schema novo | Nenhuma migration existente tem colunas de competência/período/colaborador ligadas a `documento_id` | **Não existe hoje** — ver proposta abaixo |
| 12 | Caminho atual do PDF de Ponto no legado/Airtable | `app.py:119` `F_FUNC_PDF_FOLHA = 'fldgBhXpEFmy20yxd'` (campo "PDF Folha Ponto", tabela `Funcionários` `TABLE_FUNC = 'tblNd8G66kjwos3eP'`) | Confirmado na missão anterior — anexo no prontuário do Funcionário |
| 13 | Como os anexos são adicionados hoje | `app.py:3869`, `app.py:4933` `_anexar_attachment(TABLE_FUNC, func_id, F_FUNC_PDF_FOLHA, pdf_bytes, filename)` | Escrita real no Airtable (legado, fora de escopo alterar) |
| 14 | Hash/ID estável do anexo | Cada attachment do Airtable tem `url`/`filename` próprios, mas **nenhum SHA-256 de conteúdo é calculado hoje para este campo especificamente** (diferente de `documentos.hash_sha256`, que é canônico no Modulo 01) | Gap — mas resolvível: o PDF pode ser baixado (GET da `url` do attachment) e hasheado no momento da ingestão, sem escrever nada de volta no Airtable |
| 15 | Acesso read-only ao PDF sem alterar Airtable | `LeitorAirtableSomenteLeitura.listar_registros` (`documental/importacao_lote/adapters/airtable_leitura.py`) já expõe GET puro; a URL do attachment retornada pelo Airtable é, ela mesma, uma leitura — baixar o conteúdo dessa URL não escreve nada | Sim, viável sem qualquer escrita |

## Questão central — onde mora a identidade temporal

Avaliação das 4 opções, como pedido:

- **(D) Manter no Airtable — descartada.** O campo `PDF Folha Ponto` já
  demonstrou, na prática (auditoria do PR #125), que não tem
  granularidade de competência e não é confiável para essa semântica.
  Persistir competência ali seria exatamente o que a regra pétrea desta
  missão proíbe ("nenhuma solução nova deve colocar no Airtable a
  semântica canônica de competência/período/identidade documental").
  Não há impedimento técnico que justifique essa opção — é evitável.

- **(A) Reutilizar entidade documental já existente, sem metadado
  novo — não é suficiente sozinha.** `documentos` (Modulo 01) é o lugar
  certo para a IDENTIDADE do arquivo (hash, origem, status) — mas não
  tem nenhuma coluna para período/competência/colaborador. Usá-la
  sozinha, sem extensão, deixaria a identidade temporal sem lugar
  algum.

- **(C) Nova entidade documental mínima do zero — desnecessária e
  duplicativa.** Criar uma segunda tabela "documento" (paralela a
  `documentos`) reintroduziria exatamente a duplicação que a auditoria
  deveria evitar (`documento_id`/`hash_sha256`/`origem` já existem).

- **(B) Metadado/relacionamento novo sobre entidades já existentes —
  RECOMENDADA.** Uma tabela pequena e nova, mas que é uma
  **extensão relacional**, nunca uma nova entidade documental
  concorrente:
  - referencia `documentos.documento_id` (identidade do arquivo/hash —
    reaproveitada, nunca duplicada);
  - referencia (indiretamente, por `colaborador_id` opaco) o mesmo
    `vinculo_trabalhista`/`alocacao` já existentes para resolver
    cliente/posto **por data**, nunca por cadastro atual;
  - adiciona SÓ o que hoje não tem lugar nenhum: `tipo_documental`,
    `periodo_inicio`, `periodo_fim`, `competencia`, `estado_resolucao`,
    `evidencias`.

  Isto é uma extensão mínima e localizada — nenhum novo classificador,
  nenhuma nova entidade de "documento", nenhuma nova fonte de vínculo.

## Modelo conceitual recomendado (NÃO implementado nesta missão)

```
resolucao_documental_temporal
──────────────────────────────
resolucao_id          TEXT PRIMARY KEY
documento_id          TEXT NOT NULL REFERENCES documentos(documento_id)   -- reaproveita Modulo 01
tipo_documental        TEXT NOT NULL            -- ex.: 'Folha de Ponto' (vocabulário já existente)
colaborador_id          TEXT                     -- opaco, mesmo padrão de vinculo_trabalhista.colaborador_id
periodo_inicio          DATE                     -- extraído do PDF real, nunca do nome do arquivo/upload
periodo_fim             DATE
competencia             TEXT                     -- 'AAAA-MM', canônico (mesmo formato já usado em toda classificacao/)
estado_resolucao        TEXT NOT NULL            -- vocabulário de EstadoResolucaoDimensao (RESOLVIDA/AMBIGUA/NAO_ENCONTRADA/CONFLITO/...)
evidencias              JSONB NOT NULL DEFAULT '{}'  -- proveniência sanitizada (EvidenciaSanitizada), nunca CPF/nome
criado_em               TIMESTAMPTZ NOT NULL DEFAULT now()
```

Note que **cliente/posto NÃO é uma coluna aqui** — de propósito. O
cliente/posto correto para um `colaborador_id` numa `competencia` já é
respondido, de forma histórica e auditável, por `alocacao` (JOIN por
`colaborador_id` + intervalo de datas que contenha o `periodo_inicio`/
`periodo_fim` resolvido). Guardar o cliente como coluna aqui seria
denormalizar um fato derivado e arriscar ele ficar desatualizado se a
alocação histórica for corrigida depois — a mesma cautela que já rege
`vinculo_unidade_prestacao.py` hoje (nunca usar snapshot atual como
prova de passado).

Este modelo é deliberadamente MÍNIMO: não introduz `cargo`, `salário`,
`empresa`, nem duplica `Documento`/`EventoHistorico` — só acrescenta a
dimensão temporal que falta, ancorada nas duas entidades que já
existem.

## Período e competência

1. **Extrair** — reaproveitar a MESMA regex já validada contra PDF real
   em `app.py::extrair_cartao_ponto`/`_PERIODO_CARTAO_PONTO_RE`
   ("Período: dd/mm/aaaa até dd/mm/aaaa") — nunca reimplementar do
   zero; portar como função pura (sem I/O) para dentro de
   `classificacao/` ou `documental/`, mesma disciplina de portabilidade
   já usada por `produtores_evidencia_ponto.py` (que já porta o PADRÃO
   estrutural de `app.py::_LINHA_CARTAO_PONTO_RE` como regex de
   detecção, citando a origem).
2. **Validar formato** — reaproveitar `validar_competencia`
   (`importacao_lote/dominio.py`, já pura) e
   `resolucao_competencia_de_validacao` (`resolucao_semantica.py`, já
   genérica) — mesma tradução para `ResolucaoDimensao` que qualquer
   outro tipo documental já usa.
3. **Mapear período → competência** — se o período cobre um único mês
   civil, a competência é direta; se cruza um mês (ciclo deslocado), a
   competência é a do **fechamento do período** (mesma convenção já
   adotada — e corrigida — pela política de ciclo revertida no PR #125:
   ver docs/decisoes/inventario-ponto-prestacao-v1.md). Ciclos
   deslocados continuam representados como override explícito por
   cliente, nunca inferidos do documento.
4. **Nome de arquivo / data de upload / "último anexo"** — nenhum dos
   três entra na resolução (regra pétrea já estabelecida, reafirmada
   aqui): o `periodo_inicio`/`periodo_fim` SÓ vem do texto do PDF; na
   ausência ou ambiguidade desse texto, `estado_resolucao =
   NAO_ENCONTRADA`/`AMBIGUA` — nunca um fallback por data de upload.
5. **Dúvida → INDETERMINADO/REVISAR** — mesmo vocabulário de
   `EstadoResolucaoDimensao` já usado por toda `classificacao/`; a
   readiness a jusante (`prestacao_readiness.py`) já sabe tratar
   `AMBIGUA`/`CONFLITO`/`NAO_ENCONTRADA` como `REVISAR`, sem alteração.

## Vínculo histórico

`colaborador_id` resolvido por competência/período usa `alocacao`
(Postgres, `vigente_de`/`vigente_ate`) — nunca o cadastro atual do
colaborador. Hoje `FonteVinculosPrestacao` (Protocol já existente) é
implementado por um Airtable-shadow; migrar essa implementação para
consultar `alocacao` diretamente (quando um Postgres real existir) é
**só uma nova implementação do MESMO Protocol** — nenhuma mudança na
`classificacao/` que consome o Protocol.

### Correção (revisão independente) — transferência de posto/cliente DENTRO do período do documento

Um PDF de Folha de Ponto cobre um INTERVALO de dias (`periodo_inicio`..
`periodo_fim`), não um instante — e o colaborador pode ter tido MAIS DE
UMA alocação válida dentro desse intervalo (transferência de posto no
meio do ciclo). Exemplo sintético confirmado: ciclo 29/05/2026 a
28/06/2026, Cliente A vigente até 10/06/2026, Cliente B vigente a
partir de 11/06/2026 — as duas alocações são legítimas e cobrem partes
reais e distintas do mesmo documento.

**A resolução correta é por INTERSEÇÃO temporal**, nunca um ponto único
no tempo: toda alocação cujo intervalo `[vigente_de, vigente_ate ou
sem-fim]` intersecta `[periodo_inicio, periodo_fim]` do documento é uma
relação válida para este documento — nunca só a que cobre "a maior
parte" nem a "mais recente" (isso seria escolher arbitrariamente, regra
pétrea #8 proíbe).

**Reaproveitamento confirmado — nenhuma modelagem nova necessária**:
`ResolucaoDimensao` (`classificacao/contratos.py`, linha ~275) já
representa exatamente esta cardinalidade — `valores_confirmados:
Tuple[ReferenciaCanonica, ...]`, já **plural por design**, sem limite
de 1 valor. Este é o MESMO mecanismo que já resolve "vínculo múltiplo
genuíno" para Holerite (`adaptador_inventario_prestacao.py::
itens_para_multiplos_clientes_do_vinculo`, comentário: "quando a
dimensão CLIENTE resolveu RESOLVIDA com 2+ valores confirmados... gera
1 item por cliente, MESMO documento_id em todos"). A transferência
intra-período de Ponto é o MESMO padrão: 1 documento físico, N
resoluções lógicas legítimas — nunca uma segunda modelagem.

Mapeamento de cardinalidade (vocabulário já existente, sem novo
estado):
- **zero** alocações intersectam o período → `EstadoResolucaoDimensao.
  NAO_ENCONTRADA` (mesmo vocabulário já usado; a readiness a jusante já
  trata isso como `REVISAR`, sem alteração);
- **uma** alocação intersecta → `RESOLVIDA`, `valores_confirmados` com
  1 valor — caso inequívoco;
- **duas ou mais** alocações distintas intersectam (transferência
  dentro do período) → `RESOLVIDA`, `valores_confirmados` com **todos**
  os clientes distintos — nunca reduzido a 1; o documento contribui
  para a completude de CADA cliente envolvido, mesma semântica já usada
  por `itens_para_multiplos_clientes_do_vinculo` (mesmo `documento_id`
  em cada item lógico, nunca duplicado fisicamente).

**Decisão de modelo mantida**: cliente/posto continua **fora** de
`resolucao_documental_temporal` como coluna — a auditoria confirma que
isso seria não só desnecessário, mas ATIVAMENTE ERRADO no caso de
transferência intra-período (uma única coluna não poderia representar
2 clientes legítimos para o mesmo documento sem duplicar a linha ou
inventar uma escolha). A resolução por interseção, feita em tempo de
consulta contra `alocacao`, é estritamente necessária para este caso —
reforça, em vez de enfraquecer, a decisão original do ADR.

## Airtable — disciplina desta proposta

- Origem transitória/read-only apenas: o PDF é baixado da `url` do
  attachment já existente (GET puro, já suportado por
  `LeitorAirtableSomenteLeitura`).
- **Nenhum campo novo** seria criado no Airtable.
- **Nenhuma automação** dependeria de campo novo no Airtable.
- Competência/período/identidade **nunca** seriam escritos de volta no
  Airtable — moram exclusivamente em `resolucao_documental_temporal`
  (Postgres, Magnata OS).
- Nenhuma lógica semântica no adapter Airtable — ele só devolveria
  bytes do PDF e metadados brutos do attachment (nome, tamanho), a
  MESMA disciplina já seguida por `FonteRegistrosPontoAirtableShadow`
  (revertido no PR #125, mas cujo princípio de "adapter burro" continua
  correto).

**Dependência do Airtable NÃO aumenta**: hoje o PDF já é lido do
Airtable pelo legado; esta proposta troca "ler e nunca resolver
competência" por "ler e resolver competência fora do Airtable" — é uma
REDUÇÃO da superfície semântica que o Airtable carrega, não um aumento.

## Postgres

`documentos`/`eventos_documentais` (Modulo 01) e
`vinculo_trabalhista`/`alocacao` (Alocação) já cobrem identidade de
arquivo, histórico append-only e vínculo histórico — **reutilizáveis
sem alteração**. O único schema novo necessário é a tabela de resolução
acima (`resolucao_documental_temporal`), FK para `documentos`, nenhuma
FK própria para colaborador/posto (mesma disciplina de "identidade
opaca sem FK própria" já usada em `vinculo_trabalhista.colaborador_id`
e `alocacao.posto_id`, pelo mesmo motivo: as tabelas alvo ainda não
existem).

## Atomicidade / auditoria

O gate já conhecido (persistência + auditoria atômicas na mesma
transação, ou ambas falham) já tem um padrão de referência pronto para
reaproveitar: `RepositorioDocumentosPostgres.salvar`/
`salvar_se_ausente_por_hash` (`postgres_repositorio.py`) — uma única
conexão, `commit()`/`rollback()` explícitos, idempotência garantida por
constraint UNIQUE do banco (nunca lock de aplicação). Uma futura
implementação de escrita para `resolucao_documental_temporal` deveria:
inserir a linha de resolução E o evento de auditoria correspondente
(`eventos_documentais`, já append-only e protegido por trigger) **na
mesma transação/conexão**, com rollback conjunto em caso de falha —
mesmo padrão, nenhum mecanismo novo de atomicidade. Nada disto foi
implementado nesta missão (só descrito).

## `app.py` — o que mudaria, e a alternativa sem tocá-lo

Se algum dia for necessário fechar o gap de fato:

- **Trecho:** `app.py::extrair_cartao_ponto` (linha 768) precisaria
  passar a ser CHAMADA em produção (hoje só existe, isolada,
  explicitamente marcada como não usada) — e o período extraído
  precisaria ser persistido em algum lugar além do attachment (que não
  tem campo de competência).
- **Por quê:** é a única lógica já validada contra PDF real capaz de
  extrair o período do Cartão de Ponto — reescrevê-la seria duplicar
  trabalho já feito e testado.
- **Mudança mínima:** nenhuma mudança de COMPORTAMENTO em `app.py`
  seria estritamente necessária — bastaria que ALGO FORA de `app.py`
  (um novo serviço/ingestão em `magnata_os/`) baixasse o mesmo PDF pela
  `url` do attachment (leitura, já possível) e reimplementasse (ou
  importasse, se um dia deixasse de ser legado) a mesma extração de
  período.
- **Alternativa sem tocar `app.py` — SIM, existe e é preferível:**
  portar a lógica de `extrair_cartao_ponto`/`_PERIODO_CARTAO_PONTO_RE`
  como uma função PURA nova dentro de `magnata_os/classificacao/` ou
  `magnata_os/documental/` (mesmo padrão já usado por
  `produtores_evidencia_ponto.py`, que já porta o padrão estrutural de
  `_LINHA_CARTAO_PONTO_RE` sem importar `app.py`) — nenhuma alteração
  em `app.py` é necessária para isso. `app.py` continuaria como está,
  sem nunca ser tocado.

**Conclusão desta seção: `app.py` NÃO precisa ser alterado.** A
alternativa (portar a extração como função nova em `magnata_os/`) é
estritamente melhor e já seria a recomendação mesmo sem a restrição de
não tocar em legado protegido.

## Prova de viabilidade (read-only, sintética)

`test_prova_identidade_temporal_ponto_conceitual.py` (nesta branch)
demonstra, com dados 100% sintéticos e sem nenhuma dependência de rede/
Airtable/Postgres real:

1. um texto de PDF sintético com "Período: 29/05/2026 até 28/06/2026";
2. extração pura do período (função nova, mesma regex-padrão de
   `app.py::_PERIODO_CARTAO_PONTO_RE`, reimplementada localmente para a
   prova — nunca importa `app.py`);
3. resolução de competência a partir do período (fechamento do
   período → `2026-06`);
4. montagem do objeto canônico em memória (equivalente a
   `resolucao_documental_temporal`, como `dataclass` puro, só para a
   prova);
5. resolução de colaborador→cliente(s) via alocação histórica SINTÉTICA
   (tupla em memória simulando `vinculo_trabalhista`/`alocacao`),
   **por INTERSEÇÃO com o intervalo `[periodo_inicio, periodo_fim]` do
   documento** — nunca um único ponto no tempo, nunca cadastro atual;
   inclui o caso de transferência intra-período (2 clientes distintos,
   ambos retornados, nenhum descartado);
6. confirmação, por teste AST, de que nenhum import de Airtable/
   `requests`/`app.py` existe no arquivo de prova.

## Revisão adversarial

| Risco procurado | Resultado |
|---|---|
| Aumento de dependência do Airtable | Não — Airtable seguiria só como origem de leitura do PDF, nunca destino de competência (redução de escopo semântico) |
| Duplicação de entidade documental existente | Não — proposta referencia `documentos.documento_id`, nunca recria a tabela |
| Nova verdade semântica no adapter | Não — adapter proposto (futuro) só devolveria bytes/metadado bruto |
| Competência por filename | Não — só por texto do PDF real |
| Competência por data de upload | Não — mesma proibição explícita |
| Uso de cadastro atual para passado | Não — `alocacao` (vigência histórica) é o mecanismo de resolução |
| Criação prematura de nova tabela | Uma tabela nova é proposta, mas é a extensão mínima comprovadamente necessária (nenhuma coluna de competência/período existe hoje ligada a `documento_id`) — não implementada nesta missão |
| Necessidade desnecessária de `app.py` | Não — `app.py` não precisa ser alterado (ver seção acima) |
| Violação do gate de atomicidade/auditoria | Não — proposta reaproveita o padrão já existente de `postgres_repositorio.py` |
| Solução que só funciona para SKY | Não — nenhuma referência a cliente específico em nenhuma parte do modelo proposto |

## Governança

- Nenhuma alteração em `app.py` (só leitura para a auditoria).
- Nenhuma migration aplicada nesta missão (só descrita/proposta).
- Nenhuma escrita no Airtable, nenhum e-mail, nenhum WhatsApp, nenhum deploy.
- Único código novo: 1 arquivo de teste/prova isolado, sintético, sem
  integração real.

## Próxima missão recomendada (decisão humana)

Autorizar, em missão própria e com escopo explícito:
1. criar a migration de `resolucao_documental_temporal` (schema acima);
2. portar `extrair_cartao_ponto`/`_PERIODO_CARTAO_PONTO_RE` como função
   pura em `magnata_os/` (sem tocar `app.py`);
3. implementar o adapter read-only que baixa o PDF pela `url` do
   attachment já existente e calcula o hash;
4. implementar a escrita atômica (persistência + evento) reaproveitando
   o padrão de `postgres_repositorio.py`;
5. só então avaliar cardinalidade (1 documento por colaborador esperado,
   como Holerite) sobre uma fonte real.

Nenhum desses 5 itens foi implementado nesta missão.
