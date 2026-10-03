# Shadow Cliente × Posto — Airtable V1

Documento de decisão da missão "SHADOW CLIENTE X POSTO AIRTABLE V1".
Frente 7 ("Postgres e redução do Airtable") da execução paralela
autônoma iniciada por Magnata em 2026-10-03. Branch:
`fix/shadow-cliente-posto-airtable-v1`.

Regra pétrea reafirmada (mesma de
[`entrada-alocacao-postgres-v1.md`](entrada-alocacao-postgres-v1.md)):
Airtable continua em uso durante a transição, mas toda evolução nova
reduz — nunca aumenta — a dependência estrutural dele.

## Contexto

O mapa de dependências desta frente
(`/mnt/project-files/magnata-os/airtable-postgres.md`) identificou que
a migration `vigencia_cliente_por_posto`
(`magnata_os/documental/alocacao/migrations/0002_criar_vigencia_
cliente_por_posto.sql`) já existe, com a própria migration registrando
explicitamente que "a população inicial desta tabela será feita em
missão separada, apenas com snapshot Airtable como evidência" — ou
seja, o próximo passo já estava previsto e documentado, só não feito
ainda. O padrão de como fazer isso sem risco já existe e está validado
em produção de decisão: `comparacao_airtable.py` (comparação shadow
read-only de Alocação, missão "CONFIRMAÇÃO DE ALOCAÇÃO SHADOW V1").

## Escopo desta missão

Estender exatamente o mesmo padrão — shadow, read-only, nunca
reconciliação automática — para a relação Posto↔Cliente:

1. `FonteVinculosPrestacaoAirtableShadow.clientes_atuais_do_posto`
   (novo método, `airtable_vinculos_prestacao.py`) — reaproveita o
   helper privado `_resolver_por_locais` já existente (mesmo link
   Local→Cliente já lido por `resolver_clientes`); nenhuma leitura
   nova, nenhum campo novo do Airtable.
2. `RepositorioAlocacaoPostgres.cliente_vigente_do_posto` (novo método
   de leitura, `postgres_alocacao.py`) — consulta
   `vigencia_cliente_por_posto` já migrada; `LIMIT 1` seguro porque a
   invariante de 1-cliente-por-posto-por-período já é garantida pela
   constraint `EXCLUDE` da própria migration 0002.
3. `comparar_cliente_do_posto_shadow_com_airtable`
   (`comparacao_airtable.py`) — reaproveita 100% a função `comparar_
   postos` já existente (os 5 estados diagnósticos já definidos:
   `consistente`/`diferente`/`magnata_sem_dado`/`airtable_sem_
   vinculo`/`ambiguo`), tratando "o cliente vigente de um posto" como
   um `FrozenSet` de 0 ou 1 elemento — nenhum estado novo, nenhuma
   lógica de comparação nova.

## O que esta missão explicitamente NÃO faz

- Não aplica a migration 0002 contra nenhum Postgres real (inerte,
  como já documentado na própria migration — aplicar é gate humano
  separado).
- Não escreve nenhuma linha em `vigencia_cliente_por_posto` (bootstrap
  populacional continua fora de escopo, como a migration já previa).
- Não toca `app.py` (legado protegido, `/CLAUDE.md` §7).
- Não decide qual lado (Postgres ou Airtable) está correto em caso de
  divergência — só relata o estado, nunca corrige.
- Não substitui o Airtable como fonte para o corredor semântico, que
  continua usando `resolver_clientes` normalmente.

## Testes

- `test_airtable_vinculos_prestacao.py` — 3 testes novos para
  `clientes_atuais_do_posto` (cliente único, sem vínculo, dado sujo
  com 2 clientes).
- `test_comparacao_cliente_posto_airtable_shadow_v1.py` (novo) — 3
  testes para `cliente_vigente_do_posto` (mock cursor DB-API 2.0,
  mesmo padrão de `test_vigencia_cliente_por_posto_v1.py`, nunca
  Postgres real) + 6 testes para os 5 estados de comparação (um deles
  cobrindo também o path de exceção → `AMBIGUO`).
- Suíte geral validada antes/depois (branch vs. `main`): mesmas 62
  falhas pré-existentes nos dois lados (ambiente sem `flask`/`moto`
  instalados — nada relacionado a esta mudança), +12 testes novos
  passando, zero regressão.

## Impacto no legado

Nenhum — só leitura adicional sobre adapters e tabelas já existentes.
Nenhuma rota, nenhum comportamento de produção muda.

## Rollback

Reverter o commit desta missão. Nenhuma migration foi aplicada, nenhum
dado foi escrito — rollback é só reverter código.

## Próximo passo (fora desta missão)

Com esta comparação disponível, o próximo passo natural (gate humano
separado, decisão de negócio) é decidir *quando* rodar essa comparação
em produção (CLI de diagnóstico, ou rotina) e *se/quando* popular
`vigencia_cliente_por_posto` a partir do snapshot Airtable como
evidência inicial — ambos fora do escopo desta missão, que só
construiu a capacidade de comparar.
