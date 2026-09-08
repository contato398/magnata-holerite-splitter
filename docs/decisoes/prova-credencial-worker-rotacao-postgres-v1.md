# Prova de rotação de credencial do worker Postgres — V1

Documento de decisão sobre como comprovar que o `magnata-holerite-worker`
está usando a credencial correta (`magnata_worker_rot2`) contra o
Postgres real (`magnata_os`), no contexto do bloqueio operacional
identificado antes da aplicação da migration 0003
(`magnata_os/orquestrador/migrations/0003_acoes_execucao_plano.sql`) e
da ativação da persistência real do executor do Orquestrador.

## Contexto

O critério de aceite originalmente pedido era:

- `current_database() = magnata_os`
- `current_user = magnata_worker_rot2`
- `SELECT 1` = sucesso

Após corrigir a `DATABASE_URL` estática do worker no Render (ela estava
colada como texto solto, não vinculada ao banco, e por isso não
acompanhava a rotação de credencial), a investigação em produção
(sessão de Shell do próprio `magnata-holerite-worker`, somente leitura)
encontrou:

```
current_database() = magnata_os        -- confere
current_user       = magnata_os        -- NÃO confere com o pedido original
SELECT 1           = sucesso           -- confere
```

Achado com `SELECT rolname, rolconfig FROM pg_roles WHERE rolname =
'magnata_worker_rot2'`:

```
rolconfig = ['role=magnata_os']
```

E `magnata_worker_rot2` é membro do role `magnata_os` (além de
`pg_read_all_stats` e `pg_signal_backend`).

## Diagnóstico

O role `magnata_worker_rot2` tem `ALTER ROLE ... SET role = 'magnata_os'`
configurado — isto faz o Postgres executar automaticamente `SET ROLE
magnata_os` em toda sessão autenticada como `magnata_worker_rot2`. Por
isso:

- `session_user` (identidade de login/autenticação) = `magnata_worker_rot2`;
- `current_user` (identidade efetiva da sessão, após o `SET ROLE`
  automático) = `magnata_os`.

**Isto não é um bug de configuração do worker** — é o mecanismo (crido,
não confirmado formalmente com o suporte do Render) da própria rotação
de credencial do Render: o novo login herda a identidade efetiva do
role original, preservando ownership e GRANTs de todos os objetos
existentes (todos hoje pertencem a `magnata_os`) sem precisar
re-conceder privilégio nenhum. Verificado que a migration 0003 não
depende de `current_user`/`session_user`/`OWNER`/`GRANT` em nenhuma
parte do seu DDL — é apenas `CREATE TABLE` com `CHECK`/`FOREIGN
KEY`/`INDEX`. Rodar a migration sob esta sessão cria a tabela nova sob
o mesmo dono (`magnata_os`) que todo o resto do schema já tem hoje —
sem inconsistência de ownership.

## Decisão

**Opção A escolhida** (confirmada pelo usuário em 2026-09-07/08):
aceitar o alias de role como o desenho real da rotação de credencial do
Render, e **não alterar o role** `magnata_worker_rot2` em produção
(rejeitada a Opção B, que seria `ALTER ROLE magnata_worker_rot2 RESET
role;` — mudança de role/schema em produção, gate adicional, sem
necessidade real dado que a 0003 não depende de `current_user`).

A partir desta decisão, **a prova formal de rotação de credencial passa
a usar `session_user`, não `current_user`**:

- `current_database() = magnata_os`
- `session_user = magnata_worker_rot2` (substitui o antigo critério de
  `current_user`)
- `SELECT 1` = sucesso

`current_user = magnata_os` continua acontecendo por design nessa
sessão e é considerado **esperado e inofensivo**, não uma falha.

## O que isto NÃO decide

- Não confirma com certeza a intenção documentada do Render para esse
  comportamento — é uma inferência da investigação, não uma
  confirmação oficial do fornecedor. Se o suporte do Render confirmar
  ou contradizer essa leitura no futuro, este documento deve ser
  atualizado, não apagado.
- Não autoriza nenhuma alteração de role, schema ou credencial em
  produção — essa autorização, se algum dia for necessária, é uma nova
  decisão de fase própria (`CLAUDE.md §6`).
- Não altera o critério de aceite de nenhuma outra migration ou módulo
  além deste caso específico do `magnata-holerite-worker` contra
  `magnata_os`.

## Rastreabilidade

- Script de prova: `scripts/verificar_credencial_worker_postgres.py`
  (atualizado nesta mesma mudança para checar `session_user` em vez de
  `current_user` como critério principal, mantendo `current_user` só
  como campo informativo no relatório).
- Teste: `test_verificar_credencial_worker_postgres.py`.
