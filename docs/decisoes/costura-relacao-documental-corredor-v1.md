# Costura Automática de Relação Documento↔Documento no Corredor — V1

Documento de decisão da missão macro "CORRIGIR METADADOS + MERGE PR
#106 + COSTURA AUTOMÁTICA DE RELAÇÃO DOCUMENTO↔DOCUMENTO NO CORREDOR
V1". Fecha o gap explicitamente registrado no PR #106
(`docs/decisoes/evidencia-relacional-vinculo-unidade-v1.md`, seção 4
"PENDÊNCIA REGISTRADA"): a capacidade de RESOLVER uma relação já
existia; agora o corredor sabe, sozinho, "quais documentos considerar
como candidatos" e o que fazer quando a relação resolve.

## 1. Auditoria prévia

Antes de criar qualquer contrato novo, auditados:

- **`vinculos_prestacao.FonteVinculosPrestacao`** /
  **`vinculo_unidade_prestacao.FonteUnidadePostoPrestacao`/
  `FonteVinculoPrestacao`**: confirmam o padrão já estabelecido de
  Protocol substituível + wrapper `resolver_*_validado` (validação só
  de invariantes estruturais) — reaproveitado literalmente para
  `FonteCandidatosRelacaoDocumental`.
- **`fonte_inventario_composta.FonteInventarioPrestacaoComposta`**:
  padrão de agregação (união deduplicada de N fontes do mesmo
  Protocol) — reaproveitado para
  `FonteCandidatosRelacaoDocumentalComposta` (§12 da missão: "esgotar
  fontes já autorizadas antes de humano").
- **`inventario_prestacao_memoria.InventarioPrestacaoEmMemoria`**: sink
  já existente, já idempotente por `identidade_logica` — reaproveitado
  sem nenhuma alteração; a costura só ALIMENTA este mesmo sink.
- **`adaptador_inventario_prestacao.itens_para_clientes_broadcast`**:
  avaliado, mas NÃO reaproveitado diretamente para gerar os itens da
  costura — exigiria forjar um `ResultadoResolucaoSemantico` completo
  só para reusar a função, uma indireção artificial. `ItemInventario
  Prestacao` (o CONTRATO em si, já existente) é construído diretamente
  — reuso do dado, não de uma função mal-encaixada.
- **`estrategia_aquisicao_documental.py`**: modela "próxima fonte a
  consultar" para um documento FALTANTE (Gmail/Airtable/storage) — um
  conceito adjacente, mas DIFERENTE de "candidatos para uma relação
  entre documentos já conhecidos". Não reaproveitado diretamente (a
  composição de fontes locais já resolve §12 desta missão); citado
  aqui como o mecanismo correto para quando um candidato exigir uma
  fonte LIVE nova — fora do escopo desta missão (§26).
- **`estrategia_aquisicao_documental`/tabelas de esteira
  (`servico_lote.py`, migrations)**: nenhuma tabela de "relação entre
  documentos" existe hoje na esteira — confirmado, nenhuma reutilização
  possível além do que já foi auditado na missão anterior.

## 2. Contrato Fonte de Candidatos — `fonte_candidatos_relacao_documental.py`

`FonteCandidatosRelacaoDocumental` (Protocol) — **source-neutral**:
entrada = `documento_id_atual`, `tipo_documental_atual`,
`tipo_documental_candidato`, `competencia`, `tipo_relacao`; saída =
`CandidatoRelacaoDocumental` sanitizado (`documento_id`,
`tipo_documental`, `dados_correlacao` já extraídos, `referencias_
logicas` já resolvidas do próprio candidato, `proveniencia`
sanitizada) — nunca PDF/texto bruto, CPF, nome ou segredo.

**PROIBIDO, confirmado não criado**: nenhuma classe
`FonteComprovanteIfood`/`FontePedidosVR`/`RepositorioFGTSComprovantes`
existe — 1 única porta genérica para qualquer par de tipos.

`resolver_candidatos_validado` valida invariantes estruturais (nunca o
próprio documento como candidato, nunca tipo fora do pedido, nunca
competência divergente) — mesmo padrão de todo `resolver_*_validado`
já existente no repositório.

## 3. Candidato não é relação (§3)

Confirmado por construção: `FonteCandidatosRelacaoDocumental` NUNCA
importa nem chama `relacao_documental.resolver_relacao_documental_*` —
só devolve candidatos. A decisão continua exclusivamente em
`resolver_relacao_documental_dentre_candidatos`, chamado pelo
orquestrador DEPOIS.

## 4. Política de consequência — `politica_consequencia_relacao_documental.py`

Cadastro declarativo (`RegraConsequenciaRelacao`, tupla — nunca um
`if tipo ==`), 3 regras comprovadas (cada uma com caso E2E
correspondente):

| Relatante | Comprovante | Deriva referências? | Preserva broadcast? |
|---|---|---|---|
| Relatório de Benefícios | Comprovante de Pagamento - VR/VA | Sim | Não |
| FGTS | Comprovante de Pagamento - FGTS | Sim | Não |
| Guia DCTFWeb/DARF | Comprovante de Pagamento - DCTF/DARF | Não | Sim |

Regra estrutural: `pode_derivar_referencias_do_relatante` e
`preserva_broadcast` são mutuamente exclusivos (validado no
`__post_init__` — nunca as duas ao mesmo tempo).

`derivar_referencias_herdadas` é a ÚNICA regra de herança —
generalização de `produtores_evidencia_beneficios.derivar_clientes_
logicos_do_comprovante_global`, que agora DELEGA para cá (fonte única
de verdade, nunca uma segunda engine por família).

## 5. Orquestrador — `corredor_relacao_documental.py`

`resolver_relacao_e_avancar(contexto, sink)` — ponto de entrada único:

```
documento atual (tipo já resolvido)
  -> política (tipo é lado COMPROVANTE de alguma regra?)
  -> fonte de candidatos (união de fontes locais autorizadas)
  -> evidências de correlação (produzir_evidencias_correlacao)
  -> resolver_relacao_documental_dentre_candidatos
  -> se RESOLVIDA e regra permite: deriva referências, gera
     ItemInventarioPrestacao, alimenta o MESMO sink
  -> devolve resultado
```

Sem regra cadastrada para o tipo, ou sem fonte injetada:
`regra_aplicavel=False`, nada avaliado (nunca fabricado).

Idempotente por construção: o sink já dedupe por `identidade_logica` —
chamar a função 2x com o mesmo contexto nunca duplica itens (Caso
E2E-H).

Puramente ADITIVO: nunca recebe, nunca devolve, nunca toca em
classificação/`tipo_documental` — ausência de relação nunca desfaz o
que o motor semântico já resolveu (Caso E2E-I).

## 6. E2E obrigatório (§23) — todos os 10 casos provados

`test_magnata_os_classificacao_corredor_relacao_documental.py`:

- **A**: candidato correto encontrado, relação resolve, clientes
  corretos, itens no inventário.
- **B**: 2 candidatos fortes → `AMBIGUA`, zero itens gerados.
- **C**: só valor igual → `NAO_ENCONTRADA`.
- **D**: candidato contraditório + candidato correto → correto
  resolve (prova a correção do PR #106 na prática, dentro do
  orquestrador real).
- **E**: nenhum candidato → `NAO_ENCONTRADA`.
- **F**: FGTS guia+comprovante cliente A → só cliente A, nunca vaza.
- **G**: DCTF guia+comprovante → relação resolve como EVIDÊNCIA/
  auditoria, mas zero item gerado (broadcast intocado, decidido em
  outro lugar).
- **H**: execução dupla → nunca duplica.
- **I**: relação não encontrada → resultado só afeta a própria função,
  nunca a classificação.
- **J**: fornecedor de benefício desconhecido → relação resolve por
  outras evidências (identificador + valor), fornecedor nunca exigido.

Mais: tipo sem regra cadastrada nunca avalia; sem fonte injetada nunca
avalia; teste arquitetural confirma zero Airtable nos 4 módulos novos
(`fonte_candidatos_relacao_documental`,
`politica_consequencia_relacao_documental`,
`corredor_relacao_documental`, e `relacao_documental`/`vinculo_
unidade_prestacao` do PR #106) + Protocol-substituível puro-Python.

## 7. Métricas relacionais (§22)

`corredor_relacao_documental.MetricasRelacaoDocumental` +
`medir_relacoes` — capacidade permanente (nunca um cálculo ad hoc só
de teste): `total_relacoes_avaliadas`, `auto_relacoes_resolvidas`,
`relacoes_ambiguas`, `relacoes_conflito`, `relacoes_nao_encontradas`,
`auto_relacoes_aplicadas_a_inventario`, `percentual_auto_relacao`
(`None` quando nada foi avaliado — nunca `0.0` disfarçado).

## 8. Persistência / auditabilidade (§14/§15)

Nenhum banco paralelo criado. `ResolucaoRelacaoDocumental` (já
existente, PR #106) já É o registro auditável — `documento_a_id`,
`documento_b_id`/`candidatos_documento_b_id`, `tipo_relacao`, `estado`,
`motivos`, `evidencias` (cada uma com `tipo_evidencia`/`forca`/`motivo_
sanitizado`) — nenhum texto bruto, CPF, nome ou valor bancário bruto em
nenhum campo. `correlation_id` explícito não é carregado ainda (nenhum
candidato do sink em memória expõe um hoje) — quando uma fonte real
expuser, `CandidatoRelacaoDocumental.proveniencia` já é o campo
preparado para carregá-lo sanitizado, sem mudança de contrato.
Persistência DURÁVEL da relação (fora do sink em memória) seria um
banco novo — não criado nesta missão (nenhuma necessidade comprovada
além do que os testes já provam localmente).

## 9. Universo Documental — matriz atualizada

| Família | Estado (antes → depois desta missão) |
|---|---|
| Relatório de Benefícios | PARCIAL → **PARCIAL, capacidade de relação FECHADA em teste** (regra cadastrada, E2E A-D/J provam a costura completa; falta só o adapter real de candidatos para produção) |
| Comprovante de Pagamento - VR/VA | PARCIAL, SEM_EVIDENCIA_RELACIONAL → **PARCIAL, evidência relacional RESOLVÍVEL automaticamente em teste** (Caso A/D/J) — `SEM_EVIDENCIA_RELACIONAL` deixa de ser o estado permanente da família; passa a ser o estado só quando a relação de fato não resolve (Caso C/E), nunca por falta de mecanismo |
| FGTS (Comprovante de Pagamento) | AUTOMATIZADO p/ classificação/cliente, SEM_EVIDENCIA_RELACIONAL p/ vínculo Guia↔Comprovante → **mesma costura genérica fecha o vínculo em teste** (Caso F) — adapter real de candidatos ainda pendente para produção |
| DCTF (Comprovante de Pagamento) | AUTOMATIZADO (broadcast) → **inalterado estruturalmente**; relação Guia↔Comprovante agora pode ser registrada como evidência/auditoria adicional (Caso G), broadcast continua sendo a única fonte de clientes |

Nenhum estado maquiado: a costura fecha a CAPACIDADE (provada em
teste, com fontes fake); a produção real ainda depende de um adapter
real de candidatos (seção 10) que não foi construído nesta missão —
fora do escopo autorizado (nenhum acesso live, §26).

## 10. Pendência restante — adapters reais (honesto, não escondido)

Dois adapters de PRODUÇÃO ainda não existem, e nenhum dos dois foi
construído nesta missão (fora de escopo — exigiria decidir contra qual
fonte real consultar, uma decisão de infraestrutura não pedida aqui):

1. **`FonteUnidadePostoPrestacao` real** (já pendente desde a missão
   anterior — Holerite depende dela para UNIDADE_POSTO em produção).
2. **`FonteCandidatosRelacaoDocumental` real** (nova pendência desta
   missão) — precisaria consultar, por exemplo, o inventário real
   (Postgres/Airtable já existentes) por `tipo_documental`+
   `competencia`, devolvendo `CandidatoRelacaoDocumental` já
   sanitizado. `InventarioPrestacaoEmMemoria` já usada em teste PROVA
   o mecanismo, mas não é a fonte de registro de produção.

## 11. `PLANO_VALIDACAO_LIVE_CORREDOR_V2` — reavaliação

Plano original preservado (`docs/decisoes/evidencia-relacional-
vinculo-unidade-v1.md`, §8: cliente EDIFICIO SKY TATUI, competência
JUNHO/2026, só leitura, zero escrita, limite baixo de documentos).

**`READY_FOR_LIVE_CORRIDOR_V2 = FALSE`** — a pendência original
("costura de orquestração ausente") está FECHADA por esta missão, mas
uma pendência JÁ EXISTENTE e distinta segue de pé: nenhum dos 2
adapters reais da seção 10 existe. Autorizar a validação live hoje
significaria rodar contra um corredor cuja UNIDADE_POSTO (Holerite) e
cuja costura relacional (comprovantes) não têm fonte real nenhuma —
ficariam sempre `NAO_AVALIADA`/sem candidato, mesmo com dado real
disponível no Airtable. Recomendação: construir o adapter real de
UNIDADE_POSTO (bloqueio mais antigo, mais simples — reaproveitaria os
mesmos `local_id` já lidos por `FonteVinculosPrestacaoAirtableShadow`)
antes de reavaliar de novo.
