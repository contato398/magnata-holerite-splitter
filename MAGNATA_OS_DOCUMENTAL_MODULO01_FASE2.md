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
  classe `IntegrityError` para violação de constraint. Isso é
  satisfeito por `psycopg2`, `psycopg` (v3) e até `sqlite3` (stdlib).
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

### O que acontece se o armazenamento tiver sucesso mas o registro do Documento falhar

Fica um arquivo fisicamente armazenado sem nenhum `Documento` apontando
para ele **no momento da falha**. Isso é aceito deliberadamente, por
dois motivos:

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
Antes de um `put_object`, confere se a chave já existe (`head_object`);
se existir, compara o tamanho armazenado com o tamanho da nova tentativa
— tamanhos diferentes para o mesmo hash levantam `ConteudoDivergente`
em vez de sobrescrever silenciosamente. Metadados (`mime_type`, nome
original, tamanho) vão no `Metadata` do objeto S3. Leitura
(`abrir_leitura`) devolve o `Body` da resposta do `get_object` — já é um
stream no `boto3` real.

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
memória), violação de unique constraint simulada no adapter Postgres
(fake DB-API), arquivo já armazenado (idempotência), falha simulada no
armazenamento, falha simulada no banco, compensação (arquivo permanece
após falha de registro, documento nunca criado sem arquivo), histórico
append-only (trigger simulada rejeitando UPDATE/DELETE), FK obrigatória
(evento rejeitado para `documento_id` inexistente), leitura por
streaming, conteúdo diferente com mesma chave rejeitado, e
"reinicialização" simulada (nova conexão/cliente apontando para o mesmo
armazenamento de fundo, confirmando que os dados sobrevivem — ao
contrário dos repositórios em memória, que perdem tudo).
