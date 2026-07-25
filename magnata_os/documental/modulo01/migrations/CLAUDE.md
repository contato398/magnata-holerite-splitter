# migrations/ — Regras específicas

Complementa `/CLAUDE.md` (raiz). Vale só para os arquivos `.sql` deste
diretório.

- **Append-only.** Uma mudança de schema é sempre um arquivo novo,
  numerado na sequência (`000N_descricao.sql`) — nunca uma edição de
  arquivo já existente aqui, mesmo que ainda não tenha sido aplicado em
  nenhum ambiente real (se já foi commitado, trate como aplicado).
- **Nunca editar uma migration já aplicada.** Corrigir um erro de uma
  migration anterior é uma migration nova que corrige, não um `git
  commit --amend` nem uma edição do arquivo antigo.
- **Idempotência por instrução:** preferir `CREATE TABLE IF NOT
  EXISTS`, `CREATE INDEX IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`,
  e um bloco `DO $$ ... $$` com checagem em `pg_constraint` para
  `ADD CONSTRAINT` (que não aceita `IF NOT EXISTS` nativamente) — ver
  `0007_vinculo_documentos_lote.sql` como referência já implementada.
- **Rollback explícito.** Uma migration que precisa ser desfeita ganha
  sua própria migration de reversão — não existe "desfazer" implícito.
- **Índices e integridade referencial são parte da migration, não um
  ajuste posterior** — `FOREIGN KEY`, `UNIQUE`, `CHECK` entram na
  mesma migration que cria a coluna/tabela que os precisa, salvo
  quando a ordem de dependência entre migrations exigir separação
  (documentar por quê, se acontecer).
- **Compatibilidade estrita com PostgreSQL** — sem extensão
  específica de outro banco, sem sintaxe que só funcione numa versão
  não confirmada do Postgres.
- **Nenhuma migration é aplicada por este projeto ainda** — são
  definição de schema para um adapter futuro, não executadas
  automaticamente por nenhum código hoje. Não adicionar um mecanismo de
  aplicação automática aqui sem decisão explícita separada.
