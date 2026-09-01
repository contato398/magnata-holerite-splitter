# Alocação com Vigência Histórica — V1

Documento de decisão da missão "IMPLEMENTAÇÃO ESTRUTURAL DA ENTIDADE
`alocacao` COM VIGÊNCIA HISTÓRICA". Contexto: o segundo live real SKY
Tatuí Junho/2026 provou 7/7 Holerites semanticamente resolvidos, mas
todos bloqueados por `UNIDADE_POSTO=NAO_ENCONTRADA` -- gap de vigência
já confirmado, antes desta missão, por auditoria de fontes atuais
(`VIGENCIA_FONTE_REAL_ENCONTRADA=FALSE`) e por arqueologia do legado
(nenhum dado histórico existe). Branch:
`fix/alocacao-vigencia-historica-v1`.

## Autorização

Schema/migration autorizado explicitamente, em mensagem distinta, para
a entidade `alocacao`. Durante a Fase 1 (auditoria de domínio), um
conflito real entre o desenho aprovado
(`BANCO_PROPRIO_MODELO.md` §5.1: FK `vinculo_trabalhista_id`) e o
schema/código real (`vinculo_trabalhista` também não existe) foi
encontrado e reportado -- a missão foi PARADA até decisão humana.
Decisão registrada: **Opção A** -- criar `vinculo_trabalhista` como
dependência estrutural MÍNIMA de `alocacao`, preservando a cadeia
canônica `colaborador -> vinculo_trabalhista -> alocacao -> posto`,
nunca um atalho por `colaborador_id` direto.

## Correções da revisão independente (PR #112) — 2 blockers, ambos fechados

A revisão humana independente do PR #112 (HEAD `57e54246`, antes desta
correção) encontrou 2 blockers reais e bloqueou o merge até ambos
serem corrigidos. Registrados aqui explicitamente, não escondidos:

**Blocker 1 — conflito de regra de negócio resolvido sem parar para
decisão humana.** A primeira versão desta migration encontrou o mesmo
tipo de conflito que já havia pausado esta missão uma vez (FK de
`alocacao`, ver "Autorização" abaixo) -- só que desta vez o agente
**não parou**: "reconciliou" sozinho a contradição entre
`BANCO_PROPRIO_MODELO.md` (impede QUALQUER sobreposição) e
`MAGNATA_OS_ENTIDADES.md` (permite rateio simultâneo), tratando como
uma leitura mais cuidadosa do que como o conflito arquitetural real que
era. Isso violou a mesma regra que a própria missão já havia aplicado
uma vez -- inconsistência real, corrigida, não minimizada.

**Correção:** decisão humana explícita, na revisão do PR (mensagem
distinta desta migration): **adotada como regra canônica V1** -- um
mesmo vínculo trabalhista PODE ter múltiplas alocações simultâneas em
POSTOS DIFERENTES (rateio legítimo), mas NÃO pode ter duas alocações
temporalmente sobrepostas para o MESMO posto. O comportamento
implementado (constraint, adapters, testes) **não mudou** -- já
implementava exatamente essa regra; o que mudou foi a governança:
a decisão agora está corretamente atribuída ao humano, registrada como
tal na migration (§ "Regra canônica V1 de sobreposição") e neste ADR,
nunca mais apresentada como autoescolha do agente.

**Blocker 2 — migration não era realmente idempotente.**
`CREATE TABLE IF NOT EXISTS` era seguido de `ALTER TABLE ... ADD
CONSTRAINT` sem proteção -- reaplicar a migration depois das
constraints já criadas falharia (`constraint already exists`). O
projeto já tinha o padrão correto documentado e implementado
(`magnata_os/documental/modulo01/migrations/CLAUDE.md`, "bloco `DO $$
... $$` com checagem em `pg_constraint`", referência viva em
`0007_vinculo_documentos_lote.sql`) -- não foi seguido na primeira
versão desta migration.

**Correção:** as 2 constraints `EXCLUDE USING gist` agora são criadas
dentro de blocos `DO $$ ... IF NOT EXISTS (SELECT 1 FROM pg_constraint
WHERE conname = '...') THEN ... END IF; END $$;`, exatamente o padrão
já em uso em `0007`. A migration inteira agora é idempotente por
instrução, ponta a ponta -- reaplicá-la contra um banco onde ela já
rodou não falha em nenhuma linha. `CREATE EXTENSION IF NOT EXISTS
btree_gist` já era idempotente nativamente; documentado agora,
explicitamente, o requisito de privilégio (extensão "trusted" desde
PostgreSQL 13, instalável pelo dono do banco, sem exigir superusuário)
e o risco remanescente (nunca testado contra um provedor Postgres
real -- pode haver restrição de plano gerenciado não descoberta ainda).

Nenhuma mudança de comportamento de aplicação nos 2 adapters
(Postgres/SQLite) nem nos 24 testes -- ambos os blockers eram sobre a
migration `.sql` e sua governança/documentação, não sobre a lógica já
testada.

**Duas revisões adversariais da correção em si:**

*Primeira (a correção resolve exatamente os 2 blockers, nada além):*
a regra de sobreposição implementada não mudou -- só a atribuição da
decisão, agora corretamente humana e registrada como tal, em 2 lugares
(migration + este ADR); a idempotência foi corrigida só onde faltava
(as 2 `ADD CONSTRAINT`), sem tocar nenhuma outra instrução já
idempotente; nenhum campo, tabela ou regra nova foi introduzida na
correção.

*Segunda (nenhuma regressão introduzida pela correção):* suíte
completa re-executada -- **1745 passed, mesmos 5 failed/34 errors
pré-existentes, 2 skipped**, idêntico ao HEAD anterior à correção;
52/52 testes do escopo direto (alocação + corredor + Holerite
multicolaborador) re-confirmados verdes; nenhum código Python foi
alterado nesta correção (só `.sql` + `.md`), então a suíte permanecer
idêntica é o resultado esperado, não uma coincidência.

## FASE 0 — Pré-flight

```
MODELO_DOCUMENTADO_ENCONTRADO=Sim (BANCO_PROPRIO_MODELO.md §5.1, MAGNATA_OS_ENTIDADES.md §5)
MECANISMO_MIGRATION_EXISTENTE=Sim (magnata_os/{documental/modulo01,orquestrador}/migrations/,
  .sql numerado, nunca aplicado automaticamente, rollback em arquivo separado,
  IF NOT EXISTS, testado localmente via SQLite paralelo -- RepositorioExecucoesSQLite)
TABELA_ALOCACAO_EXISTE=Não (0 migrations, confirmado antes e nesta missão)
GAPS_ENTRE_DOC_E_SCHEMA=vinculo_trabalhista também ausente -- reportado, decisão A autorizada
```

## FASE 1 — Domínio e cardinalidade

FK canônica: **`vinculo_trabalhista_id`** (cadeia completa preservada,
nunca `colaborador_id` como atalho). `posto_id` e
`vinculo_trabalhista.colaborador_id` permanecem identidades opacas
(TEXT), sem FK própria -- `posto_trabalho`/`colaborador` como tabelas
Postgres não existem e criá-las está fora do escopo autorizado (só
`vinculo_trabalhista` foi autorizado como dependência mínima).

**Conflito real entre 2 documentos canônicos, corrigido por decisão
humana (ver seção "Correções da revisão independente" acima):**
`BANCO_PROPRIO_MODELO.md` §5.1 esboça `EXCLUDE` que impede QUALQUER
sobreposição para o mesmo vínculo; `MAGNATA_OS_ENTIDADES.md` §5
documenta que "pode haver mais de uma Alocação no mesmo período para o
mesmo Vínculo (rateio entre Clientes)". Este conflito foi originalmente
resolvido pelo agente sozinho ("reconciliação") -- achado da revisão
independente do PR #112, corrigido: agora é decisão humana explícita
que a constraint impede sobreposição só para o MESMO (vínculo, posto),
nunca para postos diferentes do mesmo vínculo.

## FASE 2 — Temporalidade canônica

`vigente_de`/`vigente_ate` (NULL = vigente agora), consulta sempre por
JANELA DO MÊS INTEIRO (nunca 1 dia-âncora) -- preserva transferência de
posto no meio da competência, retornando os 2 postos legitimamente
(cardinalidade múltipla, nunca uma escolha arbitrária de qual "vale
mais"). Ausência = `NAO_ENCONTRADA` honesta. "Conflito" (2 alocações do
mesmo vínculo+posto sobrepostas) é impedido ESTRUTURALMENTE pela
constraint -- nunca precisa de tratamento em runtime.

## FASE 3 — Schema/migration

`magnata_os/documental/alocacao/migrations/0001_criar_vinculo_trabalhista_e_alocacao.sql`
(+ rollback). `id TEXT PRIMARY KEY` (desvio deliberado do esboço `uuid`
de `BANCO_PROPRIO_MODELO.md` -- segue a convenção JÁ estabelecida em
TODAS as migrations reais do projeto, nunca uuid nativo). Campos
deliberadamente ausentes de `vinculo_trabalhista` (autorização
explícita): cargo, salário, regime, matrícula, empresa (constante),
situação (redundante com `data_desligamento IS NULL`).

**Idempotência (corrigida na revisão do PR #112, ver seção dedicada
acima):** toda instrução da migration é segura para reexecução --
`CREATE TABLE`/`CREATE INDEX`/`CREATE EXTENSION` via `IF NOT EXISTS`;
as 2 constraints `EXCLUDE USING gist` via bloco `DO $$` + checagem em
`pg_constraint`, mesmo padrão já em uso em
`modulo01/migrations/0007_vinculo_documentos_lote.sql`.

## FASE 4 — Contrato de leitura temporal

`magnata_os/documental/alocacao/resolucao.py::resolver_unidade_posto_via_alocacao`
-- função pura, injetada com as 2 consultas (`vinculos_vigentes_em`,
`postos_vigentes_em`), implementa o Protocol JÁ EXISTENTE
`FonteUnidadePostoPrestacao` (`vinculo_unidade_prestacao.py`) -- **zero
contrato novo**, zero duplicação. Core (`resolucao.py`) não importa
driver de banco.

## FASE 5 — Integração com UNIDADE_POSTO

`ExecucaoCorredorReadonly` ganhou 1 parâmetro opcional,
`fonte_unidade_posto_override` (default `None` = 100% comportamento
anterior preservado). `FonteUnidadePostoPrestacaoComPrioridadeHistorica`
(`magnata_os/classificacao/`) compõe histórica (prioridade) + corrente
(Airtable, fallback só quando histórica devolve `NAO_ENCONTRADA`) --
Airtable nunca mais é "verdade histórica" quando alocação existe,
continua bridge para o resto.

## FASE 6 — Backfill: nenhum realizado

```
BACKFILL_REALIZADO=Não
BACKFILL_ESTRATEGIA=Nenhum dado histórico foi inventado ou inferido.
  Schema pronto e testado; 0 linhas de dado real inseridas.
  Classificação de evidência para uso futuro: COMPROVADA (nenhuma
  encontrada nesta missão -- arqueologia do legado já confirmou isso
  antes desta missão), PARCIAL (nenhuma), INEXISTENTE (100% do
  histórico anterior a esta migration).
```

## FASE 7 — Captura futura automática (proposta, não implementada)

Auditado: `app.py::criar_registro_holerite` e o vínculo Funcionário->
Local do Airtable nunca escrevem em `alocacao`/`vinculo_trabalhista`
hoje -- ponto de integração mínimo proposto (nunca implementado, fora
do escopo desta missão): quando uma mudança de `Locais de trabalho` for
detectada (manual ou via automação futura), a aplicação deveria (a)
fechar `vigente_ate` da alocação aberta atual do vínculo/posto anterior,
(b) abrir uma nova linha com `vigente_de` = data da mudança. O contrato
já existe pronto para isso (`registrar_alocacao`/`registrar_vinculo`,
ambos adapters) -- só nunca chamado com escrita real nesta missão.

## FASE 8 — Testes (24 novos)

`test_magnata_os_documental_alocacao_vigencia_historica.py`: aritmética
pura (4), persistência real via SQLite -- casos 1-13 do checklist da
missão (13), composição de prioridade histórica/corrente (2), e a prova
central -- caso equivalente ao SKY Junho/2026 desbloqueado end-to-end
via `ExecucaoCorredorReadonly` real (2), mais 1 teste de não-regressão
do comportamento anterior sem override. Todos passam contra SQLite real
(nunca Postgres real -- não provisionado nesta sessão, ver Fase 10/11).

## FASE 9 — Duas revisões adversariais

**Primeira (domínio, schema, constraints, temporalidade,
cardinalidade, integridade, sobreposição, meio do mês, identidade,
dependência do Airtable):** nenhum campo de RH inventado; `posto_id`/
`colaborador_id` seguem a MESMA identidade opaca já usada em todo o
código existente, nunca um novo esquema de ID; rateio e transferência
no meio do mês comprovados por teste real (não hipotético); Airtable
nunca é consultado pela lógica de resolução histórica em si (só pelo
fallback, e só quando a histórica não tem dado).

**Segunda (integração com corredor, UNIDADE_POSTO, readiness, Holerite,
automação futura, fail-safe, backfill, migração segura, idempotência,
rollback):** zero regressão -- suíte completa idêntica ao baseline (5
failed/34 errors pré-existentes, iguais); `ExecucaoCorredorReadonly`
com `fonte_unidade_posto_override=None` (default) produz exatamente o
mesmo resultado do teste pré-existente
(`test_sky_ciclo_base_julho_snapshot_comprovado...`), provado por teste
novo dedicado; rollback existe e nunca toca tabela de outra fase;
idempotência de escrita não testada contra Postgres real (ver riscos).

## FASE 10 — Segurança da migration

```
MIGRATION_REVERSIVEL=Sim -- rollback simétrico, ordem inversa de dependência
MIGRATION_DESTRUTIVA=Não -- só CREATE TABLE/INDEX/CONSTRAINT, nenhum DROP/ALTER de tabela existente
TABELAS_NAO_RELACIONADAS_ALTERADAS=Nenhuma
CREDENCIAL_NO_CODIGO=Nenhuma -- adapters recebem `conexao` já pronta, nunca constroem a própria conexão
SEGREDO_INTRODUZIDO=Nenhum
EXECUTADA_CONTRA_PRODUCAO=Não -- nem contra Postgres real nenhum (não provisionado nesta sessão)
```

**Limite honesto, não escondido:** a migration Postgres canônica
(`.sql`) **nunca foi executada contra um Postgres real** nesta missão
-- nenhum Postgres está disponível nesta sessão (mesma limitação já
registrada em missões anteriores). A validação real aconteceu contra
`RepositorioAlocacaoSQLite` (DDL hand-traduzida, mesma disciplina já
estabelecida por `RepositorioExecucoesSQLite` do Orquestrador) -- prova
a LÓGICA temporal e o contrato, mas não prova que a sintaxe exata do
`.sql` (incl. `EXCLUDE USING gist`) roda sem erro num Postgres real.
Isso é um risco remanescente explícito, não uma alegação de teste que
não aconteceu.

## Preservado

`app.py` intocado; zero escrita Airtable; zero produção; zero Render;
zero Gmail/WhatsApp; nenhum contrato pré-existente alterado (só uma
property/parâmetro novo, aditivo, default preserva comportamento);
`vinculo_unidade_prestacao.py` reaproveitado, nunca duplicado.
