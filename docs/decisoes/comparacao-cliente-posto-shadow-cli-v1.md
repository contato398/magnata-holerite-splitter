# CLI de comparação real Posto × Cliente (shadow × Airtable) — v1

**Frente G** ("saída progressiva do Airtable"), continuação do PR #240
(`comparar_cliente_do_posto_shadow_com_airtable`, já mesclado em main).
Branch: `fix/airtable-saida-progressiva-p4j06n`.

## Contexto

Em 2026-10-03T20:54Z o Magnata confirmou que a migration 0002
(`vigencia_cliente_por_posto`) já está aplicada no Postgres de produção.
O PR #240 implementou a comparação diagnóstica (shadow × Airtable), mas
só havia testes com mock/fakes — nenhuma forma de rodar a comparação de
verdade contra o ambiente real.

## O que este PR faz

1. `RepositorioAlocacaoPostgres.postos_com_vigencia_cliente_registrada`
   — novo método de leitura (reaproveita a tabela já migrada, nenhum
   schema novo) que lista os `posto_id` distintos já conhecidos pelo
   shadow.
2. `scripts/comparacao_cliente_posto_shadow_cli.py` — CLI que reaproveita
   100% a comparação já existente (`comparar_cliente_do_posto_shadow_
   com_airtable`) para rodar contra o ambiente real: `--todos` (usa o
   método novo acima) ou `--posto <id>` (repetível). Imprime um relatório
   JSON com o resumo por estado (`consistente`/`diferente`/
   `magnata_sem_dado`/`airtable_sem_vinculo`/`ambiguo`) e o detalhe por
   posto. 100% leitura — nunca escreve em nenhum dos dois lados, mesma
   disciplina de `comparacao_airtable.py`.
3. Testes novos (mock cursor DB-API 2.0 + fakes), mesma disciplina de
   PR #240 — nenhum acesso a Postgres/Airtable reais nos testes.

## O que este PR explicitamente não faz

- **Não roda a CLI contra o ambiente real.** Rodar contra
  Postgres/Airtable de produção é gate humano (`/CLAUDE.md` §6/§12-I —
  mesma disciplina já registrada em `prestacao_diagnostico_real_cli.py`
  e `verificar_credencial_worker_postgres.py`), não decidido por este
  PR. O script falha explicitamente (`BLOQUEADO`) sem `DATABASE_URL`/
  `AIRTABLE_API_KEY` no ambiente — testado localmente sem essas
  variáveis, confirmado o fail-closed.
- Não cria nenhuma tabela/migration nova (reaproveita `vigencia_cliente_
  por_posto`, já migrada e, segundo o Magnata, já aplicada em produção).
- Não altera `app.py`, não escreve no Airtable, não reconcilia nada
  automaticamente.
- `--todos` pode devolver lista vazia hoje (bootstrap populacional de
  `vigencia_cliente_por_posto` é fora de escopo desta missão e da
  migration 0002) — isso é um resultado válido, não um erro.

## Validação local

- Testes novos: 16/16 passando (mock/fakes, sem rede nem banco real).
- Suíte relacionada (`-k "alocacao or vigencia_cliente"`): 169 passed,
  14 skipped, 41 erros de coleção — mesmos erros pré-existentes de
  ambiente (dependências não instaladas: `boto3`, `flask`, `moto` etc.,
  confirmado idêntico sem minhas mudanças) já documentados no PR #240.
  Zero regressão nova.
- `git diff --check`: limpo. Busca por segredo no diff: nada encontrado.
- CLI rodada localmente sem `DATABASE_URL`/`AIRTABLE_API_KEY`: falha
  explícita (`BLOQUEADO`, exit 2) — nunca um default silencioso.

## Próximo passo (fora deste PR)

Rodar `--todos` contra o ambiente real é decisão de quem já tem acesso
autorizado a `DATABASE_URL`/`AIRTABLE_API_KEY` de produção — este PR só
entrega a ferramenta pronta para quando essa autorização existir.
