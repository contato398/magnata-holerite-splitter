# Aplicação da migration 0003 (acoes_execucao_plano) — V1

Registro de execução da migration
`magnata_os/orquestrador/migrations/0003_acoes_execucao_plano.sql` no
Postgres real de produção (`magnata_os`), sob a autorização já
registrada em
`.magnata/migration-authorizations/ativacao-orquestrador-postgres-0003-v1.gitblob`.

Depende do documento de decisão
`docs/decisoes/prova-credencial-worker-rotacao-postgres-v1.md`, que
resolveu o bloqueio operacional de credencial do
`magnata-holerite-worker` (pré-requisito para esta execução).

## Checklist da autorização — todos cumpridos antes do DDL

1. **Main canônica**: `origin/main @ 380013b` confirmado; migration
   presente em `main` desde o merge do PR #142
   (`0ec4eed Merge pull request #142`).
2. **Blob Git exato**: `git hash-object` do arquivo em `origin/main` =
   `7fa098725637eaa9dfb27c586c7163a424f123a1` — confere com o blob
   autorizado. SHA-256 documental
   `188b99f2d653b27dc06511d3ac2be4555d58e3474e6267b0144db1f21a24cb4f`
   confirmado **duas vezes** independentemente: uma vez com
   `sha256sum` no disco do worker antes da execução, e uma segunda vez
   computado a partir do conteúdo lido em memória no momento exato da
   execução (não apenas do arquivo em disco antes de abrir).
3. **Recovery/PITR disponível**: confirmado no painel do Render
   (`magnata-os-postgres` → Recovery) — Point-in-Time Recovery com
   janela de 3 dias, `Restore database` disponível; export lógico
   também disponível sob demanda.
4. **Preflight somente leitura**: confirmado, no Postgres real, antes
   do DDL —
   - schema `magnata_orquestrador` existe;
   - `execucoes` (dependência da migration 0001) existe;
   - `autorizacoes_gate` (dependência da migration 0002) existe;
   - `acoes_execucao_plano` **não** existia ainda (idempotência
     preservada — nenhuma reaplicação).

## Execução

- Tentativa inicial via `psql "$DATABASE_URL" -f ...` falhou por erro
  de ambiente do shell do Render (a variável, expandida por `"$VAR"`
  no bash daquele shell, não foi aceita pelo parser de conninfo do
  `psql` — mesma classe de problema, já observada antes com o parser
  do `psycopg`, de espaço/quebra de linha na variável de ambiente).
  Nenhuma tentativa de DDL chegou a ser executada nessa etapa —
  reportado como falha, não escondido.
- Aplicação efetiva feita via `psycopg` (o mesmo cliente já usado, com
  sucesso, na prova de credencial), lendo o arquivo do disco do
  próprio worker e executando seu conteúdo **exatamente como está**
  (`conexao.autocommit = True`, já que o arquivo tem seu próprio
  `BEGIN;`/`COMMIT;`) — nenhuma edição, nenhum SQL adicional, nenhum
  rollback executado.
- Confirmação: `MIGRATION_0003_APLICADA` sem exceção.

## Validação pós-aplicação (somente leitura)

- 21 colunas confirmadas, com os tipos esperados (`text`, `integer`,
  `timestamp with time zone`), batendo exatamente com o DDL do
  arquivo autorizado.
- 3 índices: `acoes_execucao_plano_pkey`,
  `acoes_execucao_plano_identidade_unica`,
  `acoes_execucao_plano_elegiveis_idx`.
- Todas as `CHECK`/`FOREIGN KEY`/`NOT NULL` constraints do arquivo
  presentes (incluindo `acoes_execucao_plano_gate_exato`, a FK
  composta para `autorizacoes_gate`, e
  `acoes_execucao_terminal_coerente`, o `CHECK` de coerência entre
  `estado` e `concluido_em`).
- `SELECT count(*)` = 0 — tabela nova, vazia, como esperado.

## O que isto NÃO fez (fora de escopo, por desenho da autorização)

- Não tocou `app.py`, Evolution, WhatsApp, Airtable, credencial ou
  deploy.
- Não executou rollback (`0003_acoes_execucao_plano_rollback.sql`)
  automaticamente nem manualmente — segue guardado só como plano de
  recuperação, se algum dia necessário, sob novo gate humano.
- Não ativou a persistência real do executor do Orquestrador — essa é
  a próxima etapa, ainda pendente de escopo/autorização própria.
- Não enviou nenhuma comunicação real (WhatsApp/transporte).

## Rastreabilidade

- Autorização: `.magnata/migration-authorizations/ativacao-orquestrador-postgres-0003-v1.gitblob`.
- Migration aplicada: `magnata_os/orquestrador/migrations/0003_acoes_execucao_plano.sql`.
- Rollback conhecido (não executado): `magnata_os/orquestrador/migrations/0003_acoes_execucao_plano_rollback.sql`.
- Decisão de credencial que desbloqueou esta execução:
  `docs/decisoes/prova-credencial-worker-rotacao-postgres-v1.md`.
