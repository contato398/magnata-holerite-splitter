# Inventário documental real da Prestação + primeiro piloto completo SKY (local)

**Data:** 2026-08-30
**Branch:** `fix/inventario-real-prestacao-v1`
**Base:** `main @ 6c9c0cf67352ca28433d0e54a42a1629a41b7078` (PR #101 mesclado)
**Status:** ✅ Implementado, testado localmente com fixtures do schema real — **nenhuma leitura live documental executada** (fora de escopo desta missão, por instrução explícita).

## Fase 0 — Merge do PR #101

HEAD citado (`c1b17b62e1d68180fb37cdfe80d9abae3ba1e0fb`) confirmado idêntico ao HEAD real do PR aberto, base `main`, `mergeable_state: clean`, CI verde. Mesclado. Merge commit: `6c9c0cf67352ca28433d0e54a42a1629a41b7078`.

## Fase 1 — Auditoria curta do inventário existente

| Família | Fonte existente | Adapter existente | Identidade | Cliente | Colaborador | Competência | Gap |
|---|---|---|---|---|---|---|---|
| Extrato | `TABLE_EXTRATO` | `FonteInventarioPrestacaoAirtableShadow` (já existia) | record id | via `F_EXT_CLIENTE` | não aplicável | `Folha Mensal` | — |
| FGTS (Guia) | `TABLE_FGTS` | idem | record id | via `F_FGTS_CLIENTE` | não aplicável | `Folha Mensal` | — |
| DCTFWeb (Declaração/Recibo/Guia) | `TABLE_GUIAS` | idem | record id | broadcast (parâmetro, nunca campo) | não aplicável | `Mês Contabilidade` | já é broadcast por design — nenhuma mudança |
| Holerite | `TABLE_HOL` | **novo**: `FonteInventarioHoleritesAirtableShadow` | record id | resolvido via `FonteVinculosPrestacaoAirtableShadow` (Holerite não linka Cliente diretamente) | `F_HOL_FUNC` → sanitizado | `Folha Mensal` | GAP fechado nesta missão |
| Folha de Ponto | `TABLE_GqOBHoG76EWEjK`/`tblmgV10s3dZiP8av` (schema confirmado, nunca lido em detalhe) | nenhum | — | — | — | **NECESSITA EVIDÊNCIA** — não construído |
| Pagamento salário/assiduidade/VR/VA/horas extras/diárias | `finalidade_comprovante_pagamento.py` já reconhece por TEXTO (motor geral) | nenhum adapter Airtable read-only dedicado | — | — | — | reconhecimento existe; fonte read-only de presença por cliente/competência não construída |
| Certidões | `tblKU2B8rSJyfpTBS` (schema confirmado) | nenhum | — | — | — | **NECESSITA EVIDÊNCIA** — não construído |

Nenhuma nova auditoria histórica extensa foi refeita — reaproveitada a auditoria já registrada nos ADRs anteriores + o schema já confirmado live na missão passada.

## Fase 2 — Adapter geral de inventário (fonte composta)

`magnata_os/classificacao/fonte_inventario_composta.py` — `FonteInventarioPrestacaoComposta(fontes)`, implementa `FonteInventarioPrestacao` agregando N fontes do MESMO Protocol. **Nunca** contém `if Holerite... elif Extrato...`: cada fonte específica já produz `ItemInventarioPrestacao`, esta classe só une, deduplica por `documento_id` (nunca filename) e traduz vocabulário Família B → motor geral via `TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL` (já existente, reaproveitado sem duplicar).

## Fase 3 — Proveniência

Todo item de inventário desta missão carrega: `documento_id` (sempre record id do Airtable, nunca filename), `fonte` (implícita pela classe do adapter, cada uma documentada), `cliente` (estrutural — via campo de link real ou resolvido por vínculo), `colaborador` (sanitizado, só quando aplicável — Holerite), `competencia` (derivada do parâmetro, nunca do relógio), `tipo_documental` (vocabulário canônico, traduzido quando necessário). Nunca CPF/nome — nenhum adapter novo solicita esses campos (provado por teste AST, mesma disciplina de `airtable_colaboradores_esperados_prestacao.py`).

## Fase 4 — Holerites (GAP fechado)

`magnata_os/documental/importacao_lote/adapters/airtable_holerites_prestacao.py` — `FonteInventarioHoleritesAirtableShadow`. `TABLE_HOL` só linka Funcionário (nunca Cliente) — reaproveita `FonteVinculosPrestacaoAirtableShadow` (já existente) para resolver a qual cliente cada Holerite pertence. Nunca contagem plana: a readiness/pacote continuam delegando a obrigatoriedade real de Holerite a `holerite_obrigatorio_prestacao.avaliar_obrigatoriedade_holerite` (cardinalidade colaborador, inalterado). Vínculo múltiplo genuíno (RESOLVIDA com 2+ clientes) → o mesmo Holerite aparece para cada cliente, 1 identidade documental, nunca duplicada fisicamente — testado.

## Fase 5 — Extrato Mensal

Nenhuma mudança — `FonteInventarioPrestacaoAirtableShadow` já existente já cobre Extrato lendo `F_EXT_CLIENTE` diretamente (o campo já resolve o cliente estruturalmente, sem necessidade de separação master/filho neste ponto — essa separação já acontece a montante, na importação, antes do registro existir na tabela Extratos Mensais).

## Fase 6 — FGTS

Nenhuma mudança — `FonteInventarioPrestacaoAirtableShadow` já separa `TABLE_FGTS` (Guia) de qualquer comprovante textual (`Comprovante de Pagamento - FGTS`, tratado à parte por `finalidade_comprovante_pagamento.py`/`produtores_evidencia_fiscal.py`) — nunca promove um ao outro.

## Fase 7 — DCTFWeb

Nenhuma mudança — `TABLE_GUIAS` já separa Declaração/Recibo/Guia DCTFWeb-DARF por `F_GUIA_TIPO` com valores exatos, já broadcast por design (o parâmetro `cliente` é atribuído a cada item, não lido de um campo de vínculo — mesma semântica de `itens_para_clientes_broadcast`).

## Fase 8 — Outras famílias

Folha de Ponto, pagamento salário, assiduidade, VR/VA, horas extras, diárias e certidões **não foram conectadas** — nenhuma fonte read-only pronta existe para nenhuma delas (só reconhecimento textual de finalidade, que não é o mesmo que "presença estruturada por cliente/competência no Airtable"). Registrado como gap explícito (Fase 1), nunca construído "para aumentar percentual" sem evidência.

## Fase 9 — Fonte composta: prova

`test_magnata_os_classificacao_fonte_inventario_composta.py` (6 testes) prova: agregação de múltiplas fontes, deduplicação por `documento_id` (primeira fonte prevalece, nunca merge), tradução de vocabulário Família B, preservação do campo `colaborador` sanitizado.

## Fase 10 — Piloto SKY completo, local, com fixtures do schema real

`test_piloto_sky_inventario_real_local_e2e.py` (2 testes) — usa os MESMOS IDs de tabela/campo já confirmados por leitura live na missão anterior (`TABLE_CLIENTES`, `TABLE_LOCAIS`, `TABLE_FUNC`, `TABLE_EXTRATO`, `TABLE_FGTS`, `TABLE_GUIAS`, `TABLE_HOL`) — nunca uma chamada de rede. Prova ponta-a-ponta: `FonteClientesPrestacaoAirtable` (corrigida na missão anterior) → `FonteColaboradoresEsperadosPrestacaoAirtableShadow` (7 colaboradores, mesma contagem já confirmada live) → competência efetiva SKY = base − 1 mês (regra inalterada) → `FonteInventarioPrestacaoComposta` (Extrato+FGTS+DCTF+Holerites) → `executar_ciclo_prestacao` → readiness → Holerite por cardinalidade (6/7 presentes → 1 necessidade sanitizada) → pacote `INCOMPLETO`. Variante com 7/7 Holerites → pacote `PRONTO`.

## Fase 11 — Risco temporal

Nenhum novo enum/contrato foi criado — `NivelConfianca`/`ConfiancaResolucao` (já existentes) já expressam força de uma resolução, e nada nesta missão ainda PRECISA ramificar programaticamente entre "vínculo atual" e "vínculo histórico" (o piloto local roda com o mesmo snapshot para as duas competências testadas, base e SKY-deslocada, porque nenhuma fonte de histórico existe — não porque a diferença foi ignorada). **Registrado explicitamente, não codificado ainda**: qualquer piloto real contra uma competência **passada** deve tratar a composição de colaboradores esperados como `EM_REVISAO`/confiança reduzida, nunca como certeza herdada do snapshot atual — a decisão de COMO representar isso no contrato (novo campo? novo estado?) fica para quando um piloto real de competência passada for de fato tentado, evitando inventar estrutura sem consumidor.

## Fase 12 — Gate para leitura documental live (PRODUZIDO, NÃO EXECUTADO)

```
PLANO_LEITURA_LIVE_INVENTARIO

OBJETIVO: validar o inventário real do SKY Tatuí na competência piloto
  (Junho/2026, competência efetiva) -- confirmar que os documentos
  esperados (Extrato, FGTS, DCTF Declaração/Recibo/Guia, Holerites)
  existem de fato e que os adapters desta missão os leem corretamente.

SISTEMA: Airtable Magnata (mesma base appaCpIVj7Q97VhFy).
MODO: READ-ONLY. ESCRITAS: ZERO.

TABELAS (nominal, só as necessárias):
  - tblJCUcFBVTH5W2kP (Extratos Mensais)
  - tbl8ehgLa00cE1U3s (FGTS Digital)
  - tbl6FT1YzK1yqI77l (Guias e Comprovantes)
  - tblVaUgZeFfa5zRcH (Holerites)

CAMPOS (nominal, só os necessários):
  - Extratos Mensais: F_EXT_CLIENTE (fldKtdZpZ4fd7XpAX)
  - FGTS Digital: F_FGTS_CLIENTE (fldGFwcySH5TXBjDB)
  - Guias e Comprovantes: F_GUIA_TIPO (fldZc4A6stiQPI8qt)
  - Holerites: F_HOL_FUNC (fldTXMjeHfgyDas9f)
  - Filtro em todas: campo "Folha Mensal"/"Mês Contabilidade" (nome,
    não ID -- já usado assim pelo adapter existente, confirmado
    funcional em produção-sombra)

CLIENTE: SKY Tatuí, recrqv5NvbC37WfSl (record id canônico já confirmado).
COMPETÊNCIA: Junho/2026 ("Folha Mensal"="Junho 2026") -- efetiva do
  SKY para a competência base Julho/2026.

LIMITES: só registros cuja Folha Mensal/Mês Contabilidade bate com a
  competência acima; para Extrato/FGTS, só os vinculados ao cliente
  SKY; para DCTFWeb, os da competência (broadcast, aplicável a todos).

SAÍDA: sanitizada -- contagens por tipo, record ids, nunca CPF/nome,
  nunca texto de PDF, nunca payload bruto de anexo.

PROIBIDO: create/update/delete/schema change/webhook/automação/upload
  de attachment/mutação de status; qualquer leitura de anexo/conteúdo
  de PDF; qualquer tabela fora da lista acima.

STOP CRITERIA: schema divergente do já confirmado; autenticação falhar;
  necessidade de escrita; volume anômalo; campo ambíguo; necessidade de
  baixar conteúdo de anexo não previamente autorizado; qualquer risco
  de exposição de PII.
```

**READY_FOR_LIVE_INVENTORY_VALIDATION = TRUE**

Motivo: adapters implementados e testados (localmente, com fixtures fiéis ao schema real), plano nominal completo com tabelas/campos exatos já conhecidos. **Esta missão NÃO executa essa leitura** — a autorização live anterior cobriu só Clientes/Locais/Funcionários e não se estende, em silêncio, a Holerites/Extratos/FGTS/DCTF. Aguarda confirmação humana específica e distinta antes da primeira chamada live documental.

## O que NÃO foi feito (registrado, não escondido)

- Nenhuma leitura live de Holerites/Extratos/FGTS/DCTF foi executada.
- Folha de Ponto, benefícios (VR/VA/horas extras/assiduidade/diárias) e Certidões não têm fonte read-only de inventário construída — nenhuma evidência suficiente para fazer isso sem inventar.
- O risco temporal (Fase 11) foi registrado, não resolvido em código novo — nenhum enum/contrato novo foi criado sem consumidor real.

## Documentação relacionada

- `docs/decisoes/piloto-real-prestacao-readonly-v1.md` — validação live de Clientes/Locais/Funcionários (schema, Status real de Clientes, 7 colaboradores esperados do SKY).
- `docs/decisoes/fechamento-base-canonica-ciclo-piloto-readonly-v1.md` — cadastro V2, Holerite universal por cardinalidade.
