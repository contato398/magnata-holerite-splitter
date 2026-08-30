# Política operacional real de clientes/requisitos (v1)

**Data:** 2026-08-30
**Branch:** `fix/politica-operacional-prestacao-v1`
**Base:** `main @ 9a69b727c6d9282a2ac1dae6715bdfed23ccdd17` (PR #97 mesclado)
**Status:** ✅ Implementado, testado (shadow), pronto para revisão

## Resumo executivo

Substitui o cenário artificial "clientes A/B/C injetados manualmente"
(PR #97) por uma arquitetura que obtém clientes ativos e requisitos por
cliente de fontes canônicas SUBSTITUÍVEIS — preparando o Magnata OS
para um ciclo real sem hardcode, sem ainda acessar nada ao vivo.

## Auditoria curta (Fase 1)

| Item | O que já existe | Estado |
|---|---|---|
| Clientes | `LeitorAirtableSomenteLeitura.listar_clientes()` (`airtable_leitura.py`) | CANÔNICO, já usado por `FonteVinculosPrestacaoAirtableShadow`/matching de Extrato |
| Vínculo posto→cliente | `FonteVinculosPrestacaoAirtableShadow` (`airtable_vinculos_prestacao.py`) — Funcionário→Local→Cliente | CANÔNICO, read-only, já testado |
| `PoliticaRequisitosPrestacao` | `politica_requisitos_prestacao.py` | CANÔNICO (estendido no PR #97 com `requisitos_base`) |
| `ContextoCicloPrestacao`/SKY | `competencia_esperada_prestacao.py` | CANÔNICO, autoridade de competência |
| `FonteInventarioPrestacao`/`FonteInventarioPrestacaoAirtableShadow` | `inventario_prestacao.py` / `airtable_inventario_prestacao.py` | CANÔNICO, read-only, já em shadow |
| Campo "cliente ativo" | **procurado, não encontrado** | **NÃO EXISTE** — ver decisão registrada abaixo |
| Campo "requisito obrigatório da prestação" por cliente | **procurado, não encontrado** | **NÃO EXISTE** — só existem campos de ANEXO por benefício (ver Fase 4) |

## Decisões arquiteturais registradas

### 1. "Cliente ativo" = todos os clientes cadastrados (gap registrado)

Auditoria de `app.py` (`TABLE_CLIENTES`, todos os `F_CLI_*`) não
encontrou nenhum campo "Ativo"/"Status". `FonteClientesPrestacaoAirtable.
listar_ativos` devolve TODOS os clientes de `listar_clientes()` — nunca
um subconjunto inventado. Se um campo de vigência real existir e não
foi mapeado, é uma **NECESSITA REVISÃO** explícita, não resolvida por
suposição aqui (cláusula pétrea #15).

### 2. Campos de benefício (`F_CLI_HORAS_EXTRAS`/`F_CLI_ASSIDUIDADE`/`F_CLI_VRVA`/`F_CLI_ALMOCO_JANTA`/`F_CLI_DIARIAS`) NÃO viram requisito (Fase 4)

Auditoria confirmou (`app.py:7543-7705`, `_processar_lote_sicoob`,
`CAPACIDADES_BENEFICIOS`): estes 5 campos são onde o PDF já processado
é ANEXADO (`_anexar_attachment(TABLE_CLIENTES, cliente_id, F_CLI_VRVA,
...)`) — armazenamento de OUTPUT, nunca uma flag "este cliente exige
este benefício". Interpretar presença de anexo passado como
"obrigatoriedade futura" seria inventar semântica (cláusula pétrea #14)
e confundir reconhecimento passado com requisito (cláusula pétrea #7).
**Nenhum adapter Airtable de requisitos foi construído** — só o
Protocol + normalização (Fases 3/7), testados com fixture. Este é o
GAP mais relevante desta missão, registrado explicitamente, não
escondido.

### 3. `FonteRequisitosPrestacao` fornece dados brutos; a política interpreta

`registros_para` devolve `RegistroRequisitoExterno` (tipo + quantidade,
forma neutra) — nunca `RequisitoDocumentalPrestacao` direto. A
normalização (`normalizacao_requisitos_prestacao.py`) valida contra o
universo documental canônico ANTES de virar `OverrideRequisitosPrestacao`
— tipo desconhecido nunca vira requisito silenciosamente (`TIPO_
DESCONHECIDO`, explícito).

### 4. Competência entra uma vez, na borda

`executar_ciclo_prestacao` recebe `competencias_por_cliente` já
resolvido por quem chama (via `PoliticaCompetenciaPrestacao`,
existente, reaproveitada sem alteração) — o orquestrador nunca lê o
relógio nem recalcula deslocamento. SKY continua exceção de POLÍTICA
(`DESLOCAMENTO_SKY_TATUI`, `offset_meses=-1`), nunca um pipeline
próprio — provado no E2E (competência base julho/2026 → SKY junho/2026).

## O que foi criado

- **`fonte_clientes_prestacao.py`** — `FonteClientesPrestacao` (Protocol).
- **`fonte_requisitos_prestacao.py`** — `FonteRequisitosPrestacao` (Protocol).
- **`normalizacao_requisitos_prestacao.py`** — `RegistroRequisitoExterno`,
  `normalizar_requisito(s)`, `TIPOS_DOCUMENTAIS_CANONICOS`.
- **`documental/importacao_lote/adapters/airtable_clientes_prestacao.py`**
  — `FonteClientesPrestacaoAirtable`, reaproveita `LeitorAirtableSomenteLeitura.
  listar_clientes()` sem nenhum cliente HTTP novo.
- **`ciclo_prestacao.py`** — `executar_ciclo_prestacao`,
  `ResultadoCicloPrestacao` (prontos/incompletos/em_revisao/bloqueados),
  `ResultadoClientePrestacao`, `NecessidadeDocumentoPrestacao` (Fase 12).

## Matriz de requisitos (Fase 13)

| Requisito | Origem da regra | Escopo | Base ou condicional | Representação no core | Fonte externa futura | Validado? | Gap |
|---|---|---|---|---|---|---|---|
| Holerite | universo canônico (motor geral) | colaborador→cliente | base (demonstrada) | `RequisitoDocumentalPrestacao('Holerite')` | Airtable Funcionários (via vínculo) | ✅ | — |
| Extrato da Folha de Pagamento | universo canônico | cliente | base (demonstrada) | idem | Airtable Extrato | ✅ | separação por nome ainda cautelosa |
| FGTS | universo canônico | cliente | base (demonstrada) | idem | Airtable FGTS | ✅ | — |
| DCTFWeb (3 variantes) | universo canônico | global/broadcast | base (demonstrada) | idem, via `itens_para_clientes_broadcast` | Airtable Guias | ✅ | lista de clientes do broadcast ainda injetada por quem chama |
| Certidão | universo canônico | cliente | **condicional** (provado no E2E) | idem | **nenhuma fonte real** — auditoria anterior confirmou só Airtable | ✅ (mecanismo) | fonte real de Certidão não existe ainda |
| Horas Extras/Assiduidade/VR/VA/Diárias/Almoço-Janta | campos de ANEXO em `Clientes` (app.py) | cliente | **NÃO CONFIRMADO como requisito** | `finalidade_comprovante_pagamento.py` reconhece o TIPO; nenhuma política os declara obrigatórios | **decisão de negócio pendente** | ❌ | **GAP CENTRAL** — ver decisão #2 |
| "Cliente ativo" | — | — | — | `FonteClientesPrestacaoAirtable.listar_ativos` = todos cadastrados | campo de status, se existir | ❌ | **GAP** — ver decisão #1 |

Nenhum item do universo documental canônico desapareceu do mapa (ver
matrizes anteriores em `docs/decisoes/fechamento-cobertura-documental-
fase2e3-v1.md` e `corredor-operacional-prestacao-v1.md`, ainda válidas).

## E2E sem hardcode (Fases 8/14)

`test_ciclo_prestacao_multicliente_e2e.py`: 5 clientes (completo,
incompleto, em revisão, com requisito condicional — Certidão —, e SKY),
obtidos via `FonteClientesPrestacaoAirtable`-compatible fake (mesma
interface que o adapter real), requisitos via `FonteRequisitosPrestacao`-
compatible fake. Inclui 1 master (Extrato) separado e 1 broadcast
(DCTFWeb) para 4 clientes sem duplicação. Resultado determinístico:
PRONTOS={completo, condicional, SKY}; INCOMPLETOS={incompleto};
EM_REVISAO={revisão}; BLOQUEADOS=∅. `ciclo_prestacao.py` provado, por
AST, livre de qualquer nome de cliente/tipo hardcoded em código
executável.

## PLANO_DE_VALIDACAO_LIVE (Fase 15 — NÃO EXECUTADO nesta missão)

```
OBJETIVO:
  Validar que FonteClientesPrestacaoAirtable.listar_ativos() devolve os
  clientes reais esperados, comparando contra o cadastro Airtable real
  (contagem e amostra de IDs, nunca payload completo).

SISTEMA:
  Airtable Magnata (BASE_ID já em airtable_leitura.py).

MODO:
  READ-ONLY -- LeitorAirtableSomenteLeitura já não tem nenhum método de
  escrita (superfície inteira é GET).

ESCRITAS:
  ZERO. Nenhum método de escrita será chamado, nenhum token de escrita
  será usado.

LIMITES:
  Só a tabela TABLE_CLIENTES (tbl0znyuCEzoCHtCV), só os campos já
  usados por listar_clientes() (Nome, CNPJ) -- nenhum campo novo lido
  sem necessidade comprovada.

DADOS:
  Não imprimir payload bruto. Não imprimir nome/CNPJ (PII/dado
  comercial sensível) -- só contagem de registros e, no máximo, os
  primeiros caracteres de um ID de registro para conferência de
  formato. Nenhum segredo (API key) impresso, nem parcialmente.

STOP CRITERIA:
  - schema divergente (campo Nome/CNPJ ausente ou renomeado);
  - autenticação falhar (401/403);
  - quantidade de registros fora de uma faixa razoável esperada
    (definir faixa com o humano antes de rodar);
  - qualquer necessidade de escrita aparecer durante a validação.

ROLLBACK:
  Nenhum necessário -- operação inteiramente read-only, sem mutação de
  estado em nenhum sistema.

PROIBIDO:
  update/create/delete em qualquer tabela; qualquer automação/webhook;
  qualquer mudança de schema; qualquer leitura de tabela além de
  TABLE_CLIENTES para este plano específico.

QUANDO EXECUTAR:
  Só mediante confirmação humana específica e separada desta missão --
  esta seção é o PLANO, não a execução (cláusula pétrea #12 desta
  missão: "nenhum acesso live à produção nesta missão sem gate humano
  específico posterior").
```

## O que NÃO foi feito (registrado, não escondido)

- `FonteRequisitosPrestacaoAirtable` (adapter real de requisitos) —
  não construído; nenhuma evidência de campo real no cadastro (decisão
  #2). Só o Protocol + normalização + fixture de teste existem.
- Campo "cliente ativo" real — não mapeado (decisão #1).
- Nenhum acesso live ao Airtable — plano produzido, não executado.
- Distribuição/envio/montagem física — fora de escopo, como sempre.

## Documentação relacionada

- `docs/decisoes/corredor-operacional-prestacao-v1.md` — corredor
  operacional (PR #97), base direta desta missão.
- `docs/decisoes/fechamento-cobertura-documental-fase2e3-v1.md` —
  matriz de cobertura documental (ainda válida).
