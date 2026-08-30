# Primeiro piloto real da Prestação de Contas — validação live read-only

**Data:** 2026-08-30
**Branch:** `fix/piloto-real-prestacao-readonly-v1`
**Base:** `main @ 83540e92edb04fa837f9d250cc8dcc86ed9fac33` (PR #100 mesclado)
**Autorização:** confirmada pelo humano numa resposta distinta e específica (AskUserQuestion), após aviso explícito do gate — antes de qualquer leitura live.

## Fase 0 — Merge do PR #100

HEAD citado (`a61ffe229f553e4f3a9f32b8c3d5e869c2999487`) confirmado idêntico ao HEAD real do PR aberto, base `main`, `mergeable_state: clean`, CI verde nos 2 checks. Mesclado. Merge commit: `83540e92edb04fa837f9d250cc8dcc86ed9fac33`.

## Leituras live realizadas (READ-ONLY, GET, zero escrita)

Via ferramenta MCP Airtable (mesma base `appaCpIVj7Q97VhFy` já referenciada em todo o código):
- `list_tables_for_base` — schema completo da base (só nomes/tipos de campo, nunca valor de registro).
- `get_table_schema` — detalhe dos campos `Status` (Clientes/Locais/Funcionários) e `Data de Admissão` (Funcionários).
- `list_records_for_table` — Clientes (`fld8bkTUma9T5BT6r` Status), Locais (`fldu9xd2vvoMQ2Iqb` Cliente, `fldmUQBeuZbtUFsVa` Status), Funcionários (`fldqpwuLJsZsavaEJ` Locais de trabalho, `fld5T04dlg1Yt6Xj8` Status) — nunca Nome/CPF/anexo.

**Nenhuma escrita, nenhuma automação, nenhum anexo/documento buscado.**

## Achado crítico — Clientes TEM um campo Status real

A auditoria anterior (`airtable_clientes_prestacao.py`, missão "POLÍTICA OPERACIONAL...") concluiu, sem leitura live, que nenhum campo "Ativo" existia em Clientes. **Essa conclusão estava errada** — confirmado por leitura live do schema: Clientes tem `Status` (singleSelect, `fld8bkTUma9T5BT6r`), opções `Ativo`/`Inativo`, exatamente o mesmo padrão já usado em Funcionários (`F_FUNC_STATUS`).

**Correção aplicada** (Fase 5 da missão — divergência técnica simples, autorizada sem retorno ao humano): `FonteClientesPrestacaoAirtable.listar_ativos()` agora consulta esse campo diretamente e filtra por `Status == 'Ativo'` — nunca mais devolve todos os clientes indiscriminadamente. `F_CLI_STATUS`/`STATUS_CLIENTE_ATIVO` adicionados a `airtable_clientes_prestacao.py`, mesma disciplina de duplicação de ID de campo (nunca importado de `app.py`). 5 testes atualizados/novos (`test_magnata_os_documental_airtable_clientes_prestacao.py`), todos com stub local, nenhum Airtable live no teste.

## Schema real confirmado (sanitizado — nunca nome/CPF)

- **Clientes** (`tbl0znyuCEzoCHtCV`): 31 registros. `Status`: 23 Ativo, 8 Inativo. Nenhum registro sem Status. Nenhuma duplicidade de `record id` observada.
- **Locais** (`tblZy1WfzmGIeR8ZP`): 49 registros. 25 com `Status` + `Cliente` preenchidos (22 Ativo, 3 Inativo); 2 com `Status` mas SEM `Cliente` vinculado (ambos Inativo — "local sem cliente", nunca contaminou nenhum cliente real); **22 registros (45%) completamente vazios** (nem Status nem Cliente) — achado de qualidade de dado, registrado, sem impacto no adapter (ausência de link já é tratada corretamente como "não contribui").
- **Funcionários** (`tblNd8G66kjwos3eP`): 178 registros. `Status`: 115 Ativo, 61 Inativo, 2 "Outro". 1 registro Ativo sem nenhum `Local de trabalho` vinculado ("colaborador sem local", tratado corretamente — contribui zero colaboradores esperados). Pelo menos 2 casos confirmados de funcionário vinculado a 2 Locais simultaneamente (`múltiplos locais`) — a lógica de união já existente (`_ids_vinculados`) cobre isso corretamente.

## Validação end-to-end de um cliente real conhecido — SKY Tatuí

`REFERENCIA_CLIENTE_SKY_TATUI` (`recrqv5NvbC37WfSl`, já hardcoded como exceção confirmada em `competencia_esperada_prestacao.py`) foi confirmado, pela cadeia real Cliente→Local→Funcionário:
- Cliente `recrqv5NvbC37WfSl`: Status = Ativo (confirmado).
- 1 Local vinculado (Status Ativo).
- **7 colaboradores esperados** (Status Ativo, vinculados a esse Local) — 2 outros vínculos ao mesmo Local corretamente EXCLUÍDOS por estarem Inativo.

Isso prova, com dado real (não fixture), que `FonteColaboradoresEsperadosPrestacaoAirtableShadow` (implementada na missão anterior, só testada com fakes até agora) produz o resultado esperado quando confrontada com a estrutura real — 7 `ReferenciaCanonica('COLABORADOR', id)`, nunca CPF/nome.

## Fase 4 — questão temporal (CRÍTICA, resposta definitiva)

**NÃO existe** nenhum campo de vigência/período (início/fim) no vínculo Funcionário↔Local nem Local↔Cliente — só um `Status` (snapshot ATUAL) e, em Funcionários, um único `Data de Admissão` (sem campo de desligamento correspondente diretamente na tabela; há uma tabela relacionada `Contratação/Recisão`, não explorada nesta missão — abrir essa tabela e interpretar sua semântica seria uma nova decisão de negócio, fora do escopo autorizado aqui).

**Conclusão, conforme exigido pela Fase 14:** `VINCULO_ATUAL ≠ VINCULO_HISTÓRICO`. Este piloto só pode confirmar composição de colaboradores esperados para a competência **atual/presente** com confiança; para qualquer competência passada, a composição real na época NÃO é garantida pela leitura de hoje — deve entrar como `EM_REVISAO`, nunca como certeza herdada do snapshot atual. Nenhum histórico foi inventado.

## Inventário real — NÃO conectado nesta rodada (registrado, não escondido)

Não existe, no repositório, nenhuma fonte read-only já pronta que leia Holerites/Extratos/FGTS reais do Airtable para alimentar `FonteInventarioPrestacao` do corredor novo (`ciclo_piloto_prestacao.py`) — os 2 caminhos específicos existentes (Família B shadow, ponte Holerite) usam vocabulário/fluxo próprios, não o Protocol genérico. Construir esse adapter agora seria infraestrutura nova, não validação (fora do escopo desta missão, que autorizou só leitura de Clientes/Locais/Funcionários). **Rodar o dry-run com inventário vazio para os 23 clientes reais ativos produziria só "tudo faltando" para todos — não informativo, registrado como não executado por não agregar valor real, não por limitação técnica.**

## Bloqueios classificados (Fase 13)

- **C — DADO TEMPORAL AUSENTE**: nenhum campo de vigência por competência (Fase 4, acima) — o mais crítico.
- **H — INVENTÁRIO AINDA NÃO CONSULTADO**: nenhuma fonte real de Holerites/Extratos/FGTS conectada ao corredor novo ainda.
- **E — ADAPTER/SCHEMA** (já corrigido nesta mesma missão): Clientes tinha campo Status não mapeado — corrigido.

## O que foi provado com dados reais

- O schema real bate exatamente com os 6 IDs de tabela/campo já duplicados no código (`TABLE_CLIENTES`, `TABLE_LOCAIS`, `TABLE_FUNC`, `F_LOCAL_CLIENTE`, `F_FUNC_LOCAIS`, `F_FUNC_STATUS`) — nenhuma divergência nesses 6.
- Um 7º campo (`Status` de Clientes) existia e não estava mapeado — corrigido.
- A cadeia Cliente→Local→Funcionário funciona exatamente como os adapters já modelam, inclusive para vínculo múltiplo e ausência de vínculo.
- Não há dado de vigência histórica — confirmado, não presumido.

## Maior bloqueio real encontrado

**Ausência de fonte real de inventário documental conectada ao corredor genérico** — sem isso, nenhum ciclo piloto real pode produzir um resultado de readiness diferente de "tudo faltando" para clientes reais.

## Próxima macro-missão recomendada

Construir um adapter read-only de inventário (Holerites/Extratos Mensais/FGTS Digital → `ItemInventarioPrestacao`, reaproveitando `resultado_semantico_para_item_inventario` ou equivalente) e rodar o primeiro ciclo piloto real COM inventário de verdade, para 1-2 clientes reais (ex.: SKY Tatuí, já mapeado) — ainda em dry-run, ainda sem nenhuma escrita.
