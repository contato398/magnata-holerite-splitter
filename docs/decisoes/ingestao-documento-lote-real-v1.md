# Decisão — Ingestão de Documento em Lote Real V1

**Branch:** `fix/ingestao-documentos-lote-real-v1`
**Data:** 2026-10-02
**Status:** CLI construído e testado (fakes em memória, zero rede/
Postgres/S3 real nos testes). NENHUMA chamada contra o ambiente real
foi feita nesta missão — o disparo real é manual, feito pelo próprio
usuário, depois do merge.

## 1. Problema real que motivou

`scripts/prestacao_diagnostico_real_cli.py`, rodado pela primeira vez
contra Postgres real + R2/S3 real (bucket recém-configurado), encontrou
**133 registros de `Documento` já existentes no Postgres para um
cliente de teste, mas NENHUM com conteúdo real no armazenamento**.
Toda tentativa de `armazenamento.abrir_leitura(hash)`
(`FonteCandidatosPorConteudo._paginas`,
`magnata_os/classificacao/fonte_candidatos_por_conteudo.py`) falhava,
classificando os 133 como ilegíveis (`BuscaPorConteudoIncompleta`).
Causa: o bucket R2 foi criado no dia anterior (0 objetos antes disso)
— os 133 `Documento` são metadado órfão, sem binário correspondente.

**Nenhuma ferramenta existente no repositório ingeria conteúdo real de
documento no S3/R2.** Todos os CLIs reais já existentes
(`prestacao_diagnostico_real_cli.py`, `selecao_envio_operador_cli.py`,
`testar_conectividade_whatsapp_real_cli.py`) pressupõem que a entrada
já aconteceu — nenhum deles é, em si, um ponto de entrada.

## 2. Pedido do usuário (dono do produto), nas próprias palavras

- Disparo sempre manual (nunca cron/scheduler).
- Processamento em LOTE — uma invocação cobre todos os documentos de
  um cliente+competência, nunca documento por documento.
- Reaproveitar os contratos/domínio já existentes (Módulo 01, Prestação
  de Contas, Orquestrador) — nenhum caminho paralelo novo.

## 3. O que foi construído

- `magnata_os/documental/importacao_lote/ingestao_documentos_lote_real.py`
  — núcleo: `ingerir_documentos_lote(cliente_id, competencia_base, ...)`.
- `magnata_os/documental/importacao_lote/adapters/airtable_anexos_prestacao.py`
  — adapter GET-only: devolve os metadados de anexo (`url`, `filename`,
  `type`) de um conjunto de registros Airtable, por tabela/campo.
- `scripts/ingerir_documentos_lote_real_cli.py` — CLI, mesmo padrão de
  `prestacao_diagnostico_real_cli.py` (`--cliente`, `--competencia`,
  fail-closed sem os dois).
- `test_ingestao_documentos_lote_real.py` — 12 testes, zero rede real.

### 3.1 Reaproveitamento (nenhuma lógica nova reimplementada)

- **Descoberta de QUAIS documentos pertencem a 1 cliente+1 competência:**
  reaproveita `FonteInventarioHoleritesAirtableShadow`
  (Holerites, vínculo Funcionário→Local→Cliente) e
  `FonteInventarioPrestacaoAirtableShadow` (Extratos Mensais, FGTS
  Digital) — os MESMOS adapters já usados pelo inventário real da
  Prestação de Contas. A resolução de vínculo/Folha Mensal não é
  reimplementada em nenhuma linha nova.
- **Composição de dependências reais:** reaproveita
  `compor_dependencias_a_partir_do_ambiente`
  (`orquestrador/composicao_prestacao_real_v1.py`), que já compõe
  Postgres (`DATABASE_URL`), S3/R2 (`_compor_armazenamento_a_partir_do_
  ambiente`, já com suporte a endpoint customizado) e o leitor Airtable
  somente leitura (`AIRTABLE_API_KEY`) — nada disso é duplicado aqui.
- **Gravação do binário + metadado, idempotente por hash:** reaproveita
  `AdaptadorEntradaDuravel.registrar_entrada` (porta oficial de entrada
  durável, Fase 2) — armazena o blob ANTES do `Documento`, cria/reusa o
  `Documento` por hash via `ServicoEntradaDocumental`/
  `RepositorioDocumentosPostgres.salvar_se_ausente_por_hash`, e registra
  `EventoHistorico` (append-only). Nenhuma chamada direta a
  `armazenamento.armazenar()`/`repositorio.salvar()` foi escrita —
  tudo passa por essa porta já existente e já testada.

### 3.2 Schema Airtable confirmado (leitura, nunca escrita)

Confirmado via leitura read-only do schema real (`get_table_schema`,
2026-10-02) antes de escrever qualquer código de upload — nenhum campo
foi assumido sem conferência:

| Tabela | table_id | Campo de anexo | field_id |
|---|---|---|---|
| Holerites | `tblVaUgZeFfa5zRcH` | PDF do Holerite | `fldGXsgmuADtZIgtx` |
| Extratos Mensais | `tblJCUcFBVTH5W2kP` | PDF do Extrato | `fldznv1E24rfbZt34` |
| FGTS Digital | `tbl8ehgLa00cE1U3s` | Anexo FGTS | `fldYZS5KB9yKK4lMH` |

Todos `multipleAttachments`, confirmado real. IDs duplicados em
`ingestao_documentos_lote_real.py` — mesma disciplina já documentada em
`airtable_leitura.py`/`airtable_escrita.py` (módulo novo não importa
`app.py`, CLAUDE.md §7).

## 4. Quais tabelas Airtable foram incluídas, e por quê

O pedido citou "Holerites, Outros Documentos, Férias, etc." como
exemplos, não como lista fechada — a instrução explícita era investigar
quais tabelas são de fato relevantes olhando o que os compositores
reais da Prestação já usam. Essa investigação (ver
`airtable_inventario_prestacao.py`, já em produção-shadow) mostrou que
as tabelas com vínculo de CLIENTE real e inequívoco são exatamente
três: **Holerites** (via vínculo Funcionário→Local→Cliente), **Extratos
Mensais** e **FGTS Digital** (ambas com link direto a Cliente). Estas
três entraram no escopo desta v1.

**"Férias" não é uma tabela do Airtable** — é uma categoria de
classificação de conteúdo de PDF (`classificacao/classificador_
documental.py`), aplicada a documentos já ingeridos; não existe uma
tabela Airtable dedicada a ela hoje.

**Decisão de escopo reduzido, declarada (não silenciosa):**

- **Guias e Comprovantes** (`tbl6FT1YzK1yqI77l`, DCTFWeb/FGTS/ISS) ficou
  DE FORA desta v1. Essa tabela nunca carrega vínculo de cliente real no
  Airtable — é broadcast por desenho (mesmo documento aparece para
  qualquer cliente consultado, ver docstring de
  `FonteInventarioPrestacaoAirtableShadow`). Ingerir conteúdo sob uma
  atribuição de cliente inventada seria pior do que simplesmente não
  ingerir. Fica registrado como pendência para decisão futura explícita
  (não um "esquecimento").
- **"Arquivos"/"Outros Documentos" genérico** (`tblRsvhz8oOcUqhkv`, a
  caixa de entrada usada por `app.py`) também ficou DE FORA. Essa tabela
  não é filtrada por competência (Folha Mensal) do mesmo jeito que as
  três incluídas — teria exigido uma query/atribuição diferente, fora do
  padrão já estabelecido pelos inventários reais da Prestação, e
  arriscaria expandir escopo em silêncio (CLAUDE.md §8). Fica registrada
  como extensão possível de uma v2, não decidida aqui.

Isto é uma redução de escopo declarada em relação à lista ilustrativa
do pedido, não uma contradição escondida — CLAUDE.md §2 exige que
qualquer divergência entre pedido/código/documentação seja registrada
por escrito; é o que esta seção faz.

## 5. Desenho: manual, lote, idempotente, fail-closed

- **Manual:** o CLI só roda por invocação direta do operador
  (`--cliente`/`--competencia` obrigatórios). Nunca referenciado em
  `render.yaml`, cron ou scheduler algum (grep confirmado: nenhuma
  menção fora deste PR).
- **Lote:** UMA invocação descobre e processa TODOS os anexos de TODOS
  os documentos do cliente+competência pedidos — nunca
  documento-por-documento via chamada externa separada.
- **Idempotente por hash:** reingerir o mesmo conteúdo (mesmo hash)
  nunca duplica `Documento` nem reenvia o blob — comportamento herdado
  de `AdaptadorEntradaDuravel`/`salvar_se_ausente_por_hash`, não
  reimplementado. Os 133 registros órfãos pré-existentes, quando o hash
  do anexo baixado coincidir com o hash já gravado, passam a ter
  conteúdo real no armazenamento sem criar nenhum `Documento` duplicado
  — a mesma linha pré-existente passa a ser legível por
  `armazenamento.abrir_leitura(hash)`.
- **Fail-closed no escopo:** sem `--cliente`/`--competencia`, o CLI
  nunca roda sobre "tudo"; sem `AIRTABLE_API_KEY`/`DATABASE_URL`/bucket
  configurados, falha explícita (`CONFIGURACAO_AUSENTE`), nunca um
  default silencioso.
- **Falha isolada:** cada anexo é processado dentro de um `try/except`
  próprio — anexo sem URL, download que falha (rede, 404, timeout) ou
  qualquer outra exceção durante a ingestão produz uma
  `FalhaIngestaoAnexo` nomeada (registro Airtable + tabela + índice do
  anexo + motivo técnico) e NUNCA interrompe o processamento dos demais
  anexos/documentos do lote.
- **Registro sem anexo nenhum** é listado separado
  (`registros_sem_anexo`), nunca contado como falha — é um fato
  operacional distinto (documento sem PDF anexado no Airtable), não um
  erro técnico.

## 6. LGPD — nenhum dado pessoal em log/print

O resumo final (`ResumoIngestaoLote.como_dict()`, única saída impressa
pelo CLI) contém só: contagens, hash SHA-256, id de registro Airtable
(identificador técnico, não dado pessoal) e nome de tabela/tipo
documental. `nome_original` (que pode conter nome de pessoa, ex.:
"João Silva - Holerite.pdf") nunca é impresso nem incluído no resumo —
só flui para o armazenamento (metadado S3) e para `Documento`/
`EventoHistorico` no Postgres, exatamente como já acontece hoje em todo
o resto do Módulo 01 (`ServicoEntradaDocumental`); isto não é log nem
print, é o mesmo comportamento já estabelecido e aceito no resto do
sistema.

`FalhaDownloadAnexo` nunca inclui a URL do anexo no seu texto — a URL
de anexo do Airtable frequentemente reproduz o nome do arquivo (e,
portanto, o nome da pessoa) na própria URL. Testado explicitamente
(`test_anexo_inacessivel_falha_isolada_nunca_derruba_o_lote`,
`test_resumo_nunca_contem_nome_do_arquivo_nem_dado_pessoal`).

## 7. O que continua fora de escopo

- Nenhuma automação/cron/scheduler — só invocação manual.
- Nenhum gatilho por e-mail novo.
- Nenhuma tabela além de Holerites/Extratos Mensais/FGTS Digital (ver
  §4) — Guias/Comprovantes e a caixa "Arquivos" genérica ficam para
  decisão futura explícita.
- Nenhuma alteração em `app.py`, `autorizacao_transporte_real.py`,
  migration existente ou credencial real.
- Nenhuma chamada de rede real nesta missão — os 12 testes usam sempre
  um leitor Airtable fake e um downloader de anexo injetado
  (`baixar_anexo`); `armazenamento`/`repositorio_documentos`/
  `repositorio_historico` usam as implementações em memória já
  existentes (`ArmazenamentoArquivosEmMemoria`,
  `RepositorioDocumentosEmMemoria`, `RepositorioHistoricoEmMemoria`).

## 8. Validação técnica

- 12/12 testes novos verdes (`test_ingestao_documentos_lote_real.py`):
  documento novo ingerido; idempotência por hash (reingestão não
  duplica); lote com Holerite+Extrato+FGTS numa única execução;
  múltiplos anexos no mesmo registro; falha isolada de 1 anexo nunca
  derruba o lote; anexo sem URL; registro sem nenhum anexo (nunca
  contado como falha); cliente sem vínculo não ingere nada
  (fail-closed); `cliente_id` vazio rejeitado; validação de
  `competencia`; e confirmação de que nenhum nome de arquivo/dado
  pessoal aparece no resumo.
- Suíte geral: `python -m pytest -q` — 3162 passed, 112 skipped (todos
  os skips já pré-existiam, nenhuma regressão nova).
- `git diff --check`: limpo.
- Busca por segredo no diff: nenhum encontrado.

## 9. Riscos declarados

- As três tabelas incluídas cobrem Holerite/Extrato/FGTS; qualquer
  outro tipo documental (Guias, Admissionais, Rescisão, "Arquivos"
  genérico) continua sem caminho de ingestão real em lote — precisa de
  decisão/desenho próprios (ver §4).
- O downloader padrão (`_baixar_anexo_padrao`) usa a URL de anexo que o
  Airtable devolve na mesma chamada de leitura; essa URL é assinada e
  expira — uma execução muito longa entre "listar anexos" e "baixar
  bytes" poderia, em tese, encontrar uma URL expirada. Não observado
  nos testes (sempre mockados); fica registrado como risco operacional
  a observar na primeira execução real.
- Idempotência por hash depende de `UNIQUE(hash_sha256)` no Postgres
  (`RepositorioDocumentosPostgres`, já existente) — nenhuma mudança de
  schema nesta fase.

## 10. Próxima etapa

Após merge: o usuário, no seu próprio ambiente, com
`AIRTABLE_API_KEY`/`DATABASE_URL`/`ORQUESTRADOR_S3_*` já configurados,
roda manualmente:

```
python scripts/ingerir_documentos_lote_real_cli.py \
    --cliente <rec_do_cliente_de_teste> --competencia <AAAA-MM>
```

e confirma, pelo resumo impresso, quantos dos 133 registros órfãos
passam a ter conteúdo real. Nenhuma execução contra o ambiente real foi
feita a partir desta sessão.
