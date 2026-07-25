# Magnata OS Documental — Módulo 01, Fase 2 (Persistência)

**Status:** preparação de persistência durável e armazenamento físico.
**Não integrado ao fluxo legado.** `app.py` inalterado. Nenhum acesso a
banco ou S3 reais nesta fase — todos os adapters são testados com duplos
de teste (fakes), nunca contra infraestrutura real.

## Objetivo

A Fase 1 (`MAGNATA_OS_DOCUMENTAL_MODULO01.md`) construiu o domínio
(`Documento`, `EventoHistorico`, máquina de estados) e um serviço de
entrada com repositórios **em memória** — corretos, mas que perdem tudo
ao reiniciar o processo. Esta fase prepara os adapters de persistência
durável (PostgreSQL) e armazenamento físico (compatível com S3), **sem
ligar nada disso ao fluxo real ainda**. O domínio continua desacoplado:
nada em `dominio.py` ou `servico_entrada.py` (Fase 1) muda.

## Arquitetura

```
magnata_os/documental/modulo01/
├── dominio.py                    # Fase 1 — inalterado
├── repositorio.py                # Fase 1 — inalterado (Protocols + em-memoria)
├── servico_entrada.py            # Fase 1 — inalterado
├── armazenamento.py              # NOVO — porta ArmazenamentoArquivos + em-memoria
├── servico_entrada_persistente.py # NOVO — orquestra storage + Fase 1
├── adapters/
│   ├── postgres_repositorio.py   # NOVO — Documento/Historico via DB-API 2.0
│   └── s3_armazenamento.py       # NOVO — arquivo via cliente S3-like
└── migrations/
    ├── 0001_criar_tabela_documentos.sql
    ├── 0002_criar_tabela_eventos_documentais.sql
    ├── 0003_trigger_eventos_append_only.sql
    └── 0004_indices_adicionais.sql
```

### Por que nenhum adapter importa `psycopg2`/`psycopg`/`boto3`

Os adapters são escritos contra **interfaces**, não bibliotecas
específicas:

- `RepositorioDocumentosPostgres`/`RepositorioHistoricoPostgres` recebem
  uma `conexao` no construtor e só usam o subconjunto padronizado da
  DB-API 2.0 (PEP 249): `.cursor()`, `.execute()`, `.fetchone()`,
  `.fetchall()`, `.commit()`, `.rollback()`, e a convenção de nome de
  classe `IntegrityError` para violação de constraint. **Importante:**
  o SQL usa placeholders `%s` (estilo pyformat), específico da família
  psycopg (`psycopg2`, `psycopg` v3) — **não** é genérico para qualquer
  driver DB-API 2.0. `sqlite3` (stdlib), por exemplo, usa `?` e **não**
  é compatível sem adaptação — a menção anterior a `sqlite3` nesta
  seção estava incorreta e foi removida.
- `ArmazenamentoArquivosS3` recebe um `cliente_s3` no construtor e só
  usa os métodos que o cliente S3 da `boto3` já expõe:
  `put_object`, `get_object`, `head_object`, `delete_object`.

**Consequência prática:** nenhuma dependência nova foi adicionada a
`requirements.txt` nesta fase. Em produção, quem instanciar esses
adapters passa um `psycopg2.connect(...)` real e um `boto3.client('s3',
...)` real — mas isso é decisão de um momento de integração futuro, fora
do escopo desta fase. Os testes usam duplos de teste (fakes) que
implementam a mesma interface mínima, sem precisar da biblioteca real
instalada.

## Sequência transacional escolhida (registrada antes de codificar)

Objetivo: **nunca criar um `Documento` sem arquivo físico
correspondente, e nunca perder a referência de um arquivo já
armazenado.**

Ordem de operações em `registrar_entrada_com_armazenamento()`:

1. Calcular `hash_sha256` do conteúdo recebido.
2. **Armazenar o arquivo primeiro**, via `ArmazenamentoArquivos.armazenar()`
   — operação idempotente por hash: se um objeto para esse hash já
   existe, não reenvia, só confirma (comparando tamanho) que é o mesmo
   conteúdo, e retorna a referência já existente.
3. **Só depois de confirmar sucesso no armazenamento**, delega ao
   `ServicoEntradaDocumental` (Fase 1, inalterado) para persistir o
   `Documento` (com a referência já resolvida no passo 2) e o
   `EventoHistorico` — reaproveitando toda a lógica de idempotência,
   atomicidade e compensação já construída e testada na Fase 1.

### Por que essa ordem, e não a inversa

Se o `Documento` fosse criado **antes** do arquivo, uma falha no
armazenamento deixaria um `Documento` apontando para um arquivo que
nunca existiu — pior categoria de inconsistência (dado "confirmado" que
na verdade não está lá). Armazenando **primeiro**, essa situação é
estruturalmente impossível: o `Documento` só é criado depois que o
armazenamento já confirmou sucesso.

### O que acontece se o armazenamento tiver sucesso mas o registro do Documento falhar — estado `PENDENTE_DE_RECONCILIACAO`

Fica um arquivo fisicamente armazenado sem nenhum `Documento` apontando
para ele **no momento da falha**. Este módulo trata esse arquivo como
**`PENDENTE_DE_RECONCILIACAO`**: não é um erro definitivo nem um dado
perdido — é um estado transitório e **autocurável**, não uma entidade
com status próprio no banco (não existe tabela nem `StatusDocumento`
para isso; é uma classificação operacional do arquivo órfão, útil para
quem for auditar o bucket/prefixo de armazenamento diretamente). Um
arquivo `PENDENTE_DE_RECONCILIACAO` sai desse estado de uma de duas
formas:

- **Reconciliação automática** — uma nova tentativa de entrada com o
  mesmo conteúdo (mesmo `hash_sha256`) encontra o arquivo já armazenado
  no passo 2 e segue direto para persistir o `Documento` no passo 3; o
  arquivo passa a ter dono sem nunca ter sido reenviado.
- **Reconciliação manual/operacional** — se nenhuma nova tentativa
  ocorrer, o arquivo permanece `PENDENTE_DE_RECONCILIACAO`
  indefinidamente (este módulo não tem, ainda, nenhum processo de
  varredura/expurgo automático de arquivos órfãos — está fora do escopo
  desta fase). `ArmazenamentoArquivos.remover()` está disponível para
  quem precisar limpar isso manualmente, mas **nunca é chamado
  automaticamente** pelo fluxo de entrada.

Isso é aceito deliberadamente, por dois motivos:

1. **Idempotência do armazenamento por hash** — se a mesma entrada for
   tentada de novo (retry manual ou automático futuro), o passo 2
   encontra o arquivo já lá e não reenvia nada; o fluxo segue
   normalmente até persistir o `Documento` dessa vez. O arquivo nunca
   fica "perdido" — só temporariamente sem dono, e autocurável pela
   idempotência.
2. **Apagar automaticamente seria mais arriscado do que deixar** — se
   duas tentativas concorrentes usarem o mesmo conteúdo, apagar o
   arquivo assim que uma delas falhar no registro do `Documento`
   correria o risco de apagar um arquivo que a outra tentativa,
   bem-sucedida, já está referenciando. Por isso `ArmazenamentoArquivos.remover()`
   existe só para **compensação técnica deliberada** (uma ação humana ou
   de operação, não automática dentro do fluxo de entrada).

### Falha no armazenamento em si

Se `armazenamento.armazenar()` falhar, `registrar_entrada_com_armazenamento()`
levanta `FalhaArmazenamento` **antes** de tocar em qualquer repositório
de `Documento` — nenhum `Documento` é criado. Não há o que compensar:
nada foi persistido.

### Falha no registro do Documento/Histórico após o armazenamento ter sucesso

A Fase 1 já resolve isso — `ServicoEntradaDocumental` nunca remove um
`Documento` criado; marca `ERRO` (ou preserva intacto, no caso
específico de falha ao auditar uma tentativa duplicada) e propaga
`FalhaPersistencia`. Este módulo de Fase 2 não duplica essa lógica, só
garante que o armazenamento aconteceu antes de acioná-la.

## PostgreSQL — Documento e EventoHistorico

### Tabela `documentos`

Mapeia 1:1 os campos de `Documento` (Fase 1). `hash_sha256` tem
`UNIQUE` — é a base da atomicidade real sob concorrência **entre
processos** (diferente do `threading.Lock` do repositório em memória,
que só protege dentro de um processo). `status` tem `CHECK` restrito
aos 7 valores oficiais de `StatusDocumento`.

`salvar_se_ausente_por_hash()` usa `INSERT ... ON CONFLICT (hash_sha256)
DO NOTHING RETURNING documento_id`: se nenhuma linha retornar, outro
processo já inseriu esse hash — busca e devolve o existente. A
atomicidade vem inteiramente da constraint do banco, não de lock de
aplicação.

### Rollback explícito em toda falha

`salvar()`, `remover()` (documentos) e `registrar()` (histórico) sempre
executam dentro de `try/except Exception: self._conexao.rollback();
raise`. Isso não é cosmético: no PostgreSQL real, qualquer erro não
tratado numa conexão a deixa em estado de **transação abortada** —
toda operação seguinte na mesma conexão falha com `current transaction
is aborted...` até um `ROLLBACK` explícito. Sem esse rollback, uma
falha em `registrar()` (histórico) deixaria a conexão travada bem no
momento em que a Fase 1 tenta compensar (marcar o `Documento` como
`ERRO`, registrar `FALHA_REGISTRO_HISTORICO`) — mascarando a falha real
atrás de um segundo erro genérico de "transação abortada". Este era o
risco **BLOCKING** identificado na revisão arquitetural do commit
`a44bb10` e corrigido nesta rodada.

### Tabela `eventos_documentais`

Append-only: `documento_id` é `NOT NULL REFERENCES documentos
(documento_id)` (FK obrigatória — um evento nunca pode existir para um
`Documento` inexistente, imposto pelo próprio banco). Uma trigger
(`0003_trigger_eventos_append_only.sql`) bloqueia `UPDATE` e `DELETE`
comuns na tabela, levantando exceção — histórico é imutável a nível de
banco, não só de convenção de código. `detalhes` é `JSONB`. Ordenação
por `timestamp` (e `evento_id` como desempate) tanto em
`listar_por_documento` quanto em `listar_todos`.

## Armazenamento de arquivos (porta + S3)

`ArmazenamentoArquivos` (porta): `armazenar`, `existe`, `abrir_leitura`
(streaming — retorna um objeto tipo arquivo, nunca carrega tudo em
memória de propósito), `remover` (só compensação técnica), `referencia`
(gera a referência permanente sem precisar ler o conteúdo).

`ArmazenamentoArquivosS3`: chave do objeto é `<prefixo><hash_sha256>` —
a própria chave é o hash, então dois conteúdos diferentes nunca colidem
na mesma chave (a menos de colisão de SHA-256, praticamente impossível).

**Validação de hash contra o conteúdo real (nunca por confiança no
chamador):** todo `armazenar()` — tanto no adapter S3 quanto no
`ArmazenamentoArquivosEmMemoria` — recalcula
`hashlib.sha256(conteudo)` localmente e rejeita com `HashInconsistente`
se não bater com o `hash_sha256` informado, **antes** de tocar em
qualquer estado (S3 ou dicionário em memória). Isso fecha a brecha de
um chamador (com bug ou malicioso) informar um hash que não corresponde
ao conteúdo desta chamada.

**Detecção de corrupção do objeto já armazenado:** antes de um
`put_object`, confere se a chave já existe (`head_object`); se existir,
compara o `ETag` do objeto já armazenado (MD5 hex do conteúdo, válido
porque o upload aqui é sempre de parte única) contra o MD5 recalculado
do conteúdo desta chamada — não só o `ContentLength` como antes. Um
`ETag` divergente significa que o objeto já gravado não corresponde mais
ao seu próprio hash (corrupção ou adulteração pós-gravação) e levanta
`ConteudoDivergente`. Se o cliente S3 não expuser `ETag` por algum
motivo, cai de volta na comparação por `ContentLength` (mais fraca — ver
"Limitações dos fakes de teste" abaixo). Note que, com a validação de
hash acima sempre ativa, uma chamada **legítima** de `armazenar()` nunca
alcança mais o caminho de `ConteudoDivergente` — só é alcançável se o
objeto já armazenado foi corrompido depois do fato.

Metadados (`mime_type`, nome original, tamanho) vão no `Metadata` do
objeto S3. Como `Metadata` do S3 é enviado como headers HTTP, precisa
ser ASCII-safe — `nome_original` (que frequentemente tem acentos neste
projeto) é codificado com `urllib.parse.quote()` antes de ir para o
`Metadata`, e precisa de `urllib.parse.unquote()` para ser lido de
volta. Leitura (`abrir_leitura`) devolve o `Body` da resposta do
`get_object` — já é um stream no `boto3` real.

## Migrations — idempotência e ordem obrigatória

As 4 migrations em `magnata_os/documental/modulo01/migrations/` **não
são aplicadas automaticamente por nenhuma ferramenta nesta fase** —
aplicação é manual (ou via ferramenta de migração apropriada), fora do
escopo desta fase de fundação. Duas garantias importantes sobre elas:

- **Idempotentes** — cada uma pode ser reaplicada sem erro contra um
  banco onde já foi aplicada antes: `0001` e `0002` usam `CREATE TABLE
  IF NOT EXISTS`; `0003` usa `CREATE OR REPLACE FUNCTION` e `DROP
  TRIGGER IF EXISTS` antes de recriar cada trigger; `0004` usa `CREATE
  INDEX IF NOT EXISTS`. Isso significa que rodar a mesma migration duas
  vezes (por engano, ou como parte de uma reconciliação de ambiente) é
  seguro — não é o mesmo que dizer que a *sequência completa* pode ser
  aplicada fora de ordem.
- **Ordem numérica obrigatória (0001 → 0002 → 0003 → 0004)** — `0002`
  cria uma `FOREIGN KEY` para a tabela que `0001` cria; `0003` cria uma
  trigger sobre a tabela que `0002` cria. Aplicar fora de ordem falha
  (referência a uma tabela que ainda não existe), mesmo que cada
  migration individualmente seja idempotente.

## Limitações dos fakes de teste (não são substitutos de teste real)

Os duplos de teste em `test_magnata_os_documental_modulo01_fase2.py`
(`_ConexaoFalsa`/`_CursorFalso`/`_BancoFalso` para Postgres,
`_ClienteS3Falso` para S3) reproduzem a **interface** de um driver real
o suficiente para testar a lógica dos adapters, mas têm limitações
conhecidas e deliberadas:

- **Não simulam transações reais.** `_CursorFalso.execute()` muta
  `_BancoFalso` diretamente, na hora — não existe um buffer de
  transação que só se torna visível após `commit()` nem que é
  descartado após `rollback()`. Isso significa que, no fake, uma falha
  **depois** de um `execute()` bem-sucedido mas **antes** do `commit()`
  (ex.: `falhar_no_proximo_commit`) deixa a mutação aplicada mesmo
  chamando `rollback()` — diferente de um Postgres real, onde o
  `ROLLBACK` desfaria a mudança. Os testes desta fase focam em provar
  que o **adapter chama rollback() e propaga a exceção corretamente**,
  não em provar atomicidade real de transação — isso só um banco real
  garante.
- **O estado "transação abortada" (`_abortada`) só é simulado para as
  falhas injetadas explicitamente** (`falhar_no_proximo_execute`,
  `falhar_no_proximo_commit`), não para todo `IntegrityError` levantado
  organicamente pelas outras ramificações do fake (ex.: violação de
  UNIQUE, FK obrigatória, trigger append-only). Um Postgres real
  abortaria a transação em qualquer um desses casos também — o fake
  simplifica aqui porque os adapters já chamam `rollback()` em
  qualquer exceção (não só nas injetadas), então essa simplificação não
  esconde nenhum bug do adapter, só reduz a fidelidade do fake fora do
  que os testes desta fase precisam verificar.
- **Não validam SQL real.** O fake reconhece SQL por substring
  (`sql_norm.startswith(...)`, `in sql_norm`), não por um parser real —
  não pega erro de sintaxe, incompatibilidade de tipo de coluna, nem
  problema de binding de parâmetro `%s` que só um driver/servidor real
  detectaria.
- **`_ClienteS3Falso` só imita o formato de erro do `botocore` por
  `.response['Error']['Code']`**, não o comportamento real de rede,
  concorrência entre múltiplos clientes S3 verdadeiros, nem
  consistência eventual (que buckets S3 reais podem ter, dependendo do
  provedor).

**Testes de integração reais são um gate obrigatório antes de apontar
este código para infraestrutura de produção** — por exemplo, via
`testcontainers` (Postgres real em container) e um bucket S3/MinIO real
de staging. Nenhum teste desta fase, por mais completo que seja contra
os fakes, substitui essa verificação. Este módulo **não deve ser
conectado a Postgres/S3 reais em produção sem antes rodar essa suíte de
integração real**.

## Persistência ainda em memória (mantida)

`RepositorioDocumentosEmMemoria`, `RepositorioHistoricoEmMemoria` (Fase
1) e a nova `ArmazenamentoArquivosEmMemoria` continuam existindo e são
usadas pela maioria dos testes — rápidas, sem I/O, sem precisar de
nenhum duplo de teste mais elaborado.

## O que esta fase explicitamente NÃO faz

Classificação de documento; OCR; fatiamento/separação; vínculo com
funcionário; vínculo com cliente; agrupamento em pacotes; envio
(e-mail/WhatsApp); qualquer interface visual; qualquer acesso real a
Postgres, S3 ou Airtable; qualquer alteração em `app.py` ou nos fluxos
legados; deploy.

## Testes

```bash
pytest test_magnata_os_documental_modulo01_fase2.py -v
```

Cobrem: concorrência por hash (múltiplas threads contra o adapter em
memória e contra o adapter Postgres), violação de unique constraint
simulada no adapter Postgres (fake DB-API), arquivo já armazenado
(idempotência), falha simulada no armazenamento, falha simulada no
banco (genérica e por injeção de falha em `execute`/`commit`),
compensação (arquivo permanece após falha de registro, documento nunca
criado sem arquivo, reaproveitamento do arquivo órfão numa nova
tentativa), histórico append-only (trigger simulada rejeitando
UPDATE/DELETE), FK obrigatória (evento rejeitado para `documento_id`
inexistente), leitura por streaming, "reinicialização" simulada (nova
conexão/cliente apontando para o mesmo armazenamento de fundo,
confirmando que os dados sobrevivem — ao contrário dos repositórios em
memória, que perdem tudo), e, desta rodada de correção (revisão do
commit `a44bb10`):

- **Rollback explícito em `salvar()`, `remover()` e `registrar()`** —
  falha em `execute()` e falha em `commit()`, separadamente, cada uma
  provando que `rollback()` é chamado e a exceção original propaga.
- **Fidelidade do fake quanto a "conexão abortada"** — uma falha de
  `execute()` bloqueia a conexão (`.cursor()` levanta) até `rollback()`
  explícito; e, separadamente, que o rollback automático já feito
  *dentro* do adapter é suficiente para a próxima operação na mesma
  conexão funcionar sem nenhuma ação extra do chamador.
- **`HashInconsistente`** — hash informado que não corresponde ao
  conteúdo real desta chamada, rejeitado tanto no adapter em memória
  quanto no S3, antes de qualquer gravação.
- **`ConteudoDivergente` por corrupção pós-gravação** — conteúdos
  diferentes com o mesmo tamanho, alcançável agora só via adulteração
  direta do objeto já armazenado (memória e S3 via `ETag`), já que uma
  chamada legítima de `armazenar()` nunca mais alcança esse caminho por
  si só.
- **Nome original com acentos/caracteres especiais** — codificação
  ASCII-safe (`quote`/`unquote`) nos metadados S3.
