# Cadastro canônico real de requisitos da Prestação (v1)

**Data:** 2026-08-30
**Branch:** `fix/cadastro-canonico-requisitos-prestacao-v1`
**Base:** `main @ 6a443b9640c5a8076d03ce025b88d0c73e0c61dd` (PR #98 mesclado)
**Status:** ✅ Implementado, testado (shadow), pronto para revisão

## ADENDO DE REGRA DE NEGÓCIO — HOLERITE (2026-08-30)

Correção canônica autorizada pelo negócio, numa mensagem distinta desta
mesma sessão: **"HOLERITE É OBRIGATÓRIO EM TODA PRESTAÇÃO DE CONTAS"**
— substitui integralmente o registro original desta missão, que tratava
Holerite como item divergente/`NAO_CONFIGURADO` (interseção insuficiente
entre `CAPACIDADES_DOCUMENTO` e `REQUISITOS_BASE_PRESTACAO`).

**O que muda:**
- Holerite é **base universal** — nunca mais condicional/NAO_CONFIGURADO.
- Mas NUNCA avaliado pela contagem plana (`RequisitoDocumentalPrestacao`/
  `avaliar_prestacao_readiness`) — o próprio adendo declara isso
  insuficiente ("não basta verificar presença do tipo Holerite no
  inventário"). Avaliado por **cardinalidade colaborador**: cliente →
  colaboradores esperados → 1 Holerite por colaborador aplicável.
- Um colaborador vinculado a mais de 1 cliente na competência pode ter
  o MESMO Holerite (1 identidade documental) válido logicamente em mais
  de 1 pacote — nunca duplicado fisicamente.

**Peças novas (aditivas, retrocompatíveis):**
- `ItemInventarioPrestacao.colaborador` (`Optional[ReferenciaCanonica]`,
  default `None`) — identidade sanitizada do colaborador dono do item.
- `fonte_colaboradores_esperados_prestacao.py` — `FonteColaboradoresEsperadosPrestacao`
  (Protocol, mesma família de `FonteClientesPrestacao`/`FonteRequisitosPrestacao`).
- `holerite_obrigatorio_prestacao.py` — `avaliar_obrigatoriedade_holerite`
  (pura: cliente + competência + colaboradores esperados + inventário →
  presentes/faltantes, nunca CPF/nome, só `ReferenciaCanonica('COLABORADOR', id)`).
- `adaptador_inventario_prestacao.itens_para_multiplos_clientes_do_vinculo`
  — generaliza o broadcast para vínculo múltiplo GENUÍNO (resolvido pela
  própria `ResolucaoDimensao(CLIENTE)`, nunca injetado de fora como o
  broadcast, nunca confundido com ele).
- `pacote_prestacao.combinar_pacote_com_holerite` — nunca upgrada um
  pacote já problemático; só rebaixa PRONTO→INCOMPLETO quando falta
  Holerite de algum colaborador esperado.
- `ciclo_prestacao.executar_ciclo_prestacao(..., fonte_colaboradores_
  esperados=None)` — parâmetro opcional; `None` preserva 100% o
  comportamento anterior (Holerite, se presente na base efetiva de
  quem chama, continua avaliado pela contagem plana antiga — nunca uma
  regressão silenciosa para quem já usava esta função).
- `cadastro_requisitos_prestacao.py`: `HOLERITE_TIPO_DOCUMENTAL`/
  `HOLERITE_EVIDENCIA` (citando o adendo); removido de `REQUISITOS_
  DIVERGENTES_ENTRE_FONTES` (agora só `Guia DCTFWeb/DARF`).

**Testes obrigatórios do adendo** (`test_magnata_os_classificacao_holerite_
obrigatorio_prestacao.py`): cliente com 3 colaboradores esperados/2
Holerites presentes/1 ausente → pacote INCOMPLETO com necessidade
sanitizada (nunca CPF/nome); colaborador vinculado a 2 clientes → mesmo
Holerite, 1 identidade documental, válido em ambos os pacotes; E2E
completo via `executar_ciclo_prestacao`. Todos os 9 testes passam.

**Decisão de genericidade registrada:** `ciclo_prestacao.py` antes
provava, por AST, nunca mencionar "holerite" em código executável (uma
garantia de "nenhum tipo especial"). Esse teste foi ATUALIZADO — não
enfraquecido — para refletir que Holerite agora é, por decisão de
negócio explícita, a ÚNICA exceção legítima a essa genericidade; os
demais termos proibidos (`sky`, `extrato`, `fgts`, `dctfweb`) continuam
bloqueados sem exceção.

## Resumo executivo (missão original, antes do adendo)

Resolve o maior bloqueio identificado no PR #98 — "requisitos por
cliente sem fonte com semântica de obrigatoriedade comprovada" — SEM
inventar regra de negócio: cria um cadastro canônico versionado,
declarativo, cuja base universal é a INTERSEÇÃO de 2 fontes canônicas
já existentes que concordam entre si, e cuja parte condicional começa
vazia (zero clientes configurados) até confirmação humana real.

## Fase 1 — Inventário das regras de negócio comprovadas

| Regra | Evidência | Origem | Confiança | Pode ser canônica? |
|---|---|---|---|---|
| FGTS é base universal | `app.py::CAPACIDADES_DOCUMENTO['FGTS']` + `REQUISITOS_BASE_PRESTACAO` | legado + classificacao | ALTA (2 fontes concordam) | ✅ |
| DCTFWeb-Declaração é base, broadcast | idem | idem | ALTA | ✅ |
| DCTFWeb-Recibo é base, broadcast | idem | idem | ALTA | ✅ |
| Extrato é base (por cliente) | `CAPACIDADES_DOCUMENTO['Extrato da Folha de Pagamento']` + `REQUISITOS_BASE_PRESTACAO['extrato_cliente']` (tradução) | idem | ALTA | ✅ |
| Holerite é base universal, granularidade colaborador | `CAPACIDADES_DOCUMENTO` + **Adendo de Regra de Negócio (2026-08-30, confirmação humana explícita)** | legado + negócio | ALTA (confirmado pelo negócio) | ✅ (ver ADENDO acima) |
| Guia DCTFWeb/DARF é base | só `REQUISITOS_BASE_PRESTACAO` | classificacao | MÉDIA (1 fonte só) | ❌ divergente, registrado |
| Horas Extras/Assiduidade/VR/VA/Diárias/Almoço-Janta são obrigatórios por cliente | `CAPACIDADES_BENEFICIOS` — mas só descreve RECONHECIMENTO (keyword/fuzzy), nunca obrigatoriedade | legado | NENHUMA (campos são anexo de output, não flag) | ❌ NAO_CONFIGURADO |
| SKY = competência base − 1 mês | `DESLOCAMENTO_SKY_TATUI`, `POLITICA_COMPETENCIA_PRESTACAO_V1` | classificacao, já provado em produção-sombra | ALTA | ✅ (já canônica desde PR #91/#92) |

Nenhuma investigação histórica nova foi refeita — reaproveitada a
auditoria já registrada nos ADRs dos PRs #96/#97/#98.

## Fase 3 — Reconciliação de divergência

`REQUISITOS_BASE_PRESTACAO` (Família B) e `CAPACIDADES_DOCUMENTO`
(legado) divergem em 2 pontos (Holerite, Guia DCTFWeb/DARF). Regra
aplicada: **interseção vira base universal; divergência vira registro
explícito, nunca obrigação inventada** (`REQUISITOS_DIVERGENTES_ENTRE_
FONTES`, disponível para `ConfiguracaoCondicionalCliente` explícita
quando confirmado por um humano).

## O que foi criado

- **`cadastro_requisitos_prestacao.py`**: `RequisitoCanonico` (exige
  `evidencia` não vazia — nunca uma linha sem proveniência),
  `ConfiguracaoCondicionalCliente` (`NAO_CONFIGURADO` nunca é entrada
  explícita — é a AUSÊNCIA de entrada), `CadastroRequisitosPrestacao`,
  `FonteRequisitosPrestacaoCanonica` (satisfaz o Protocol do PR #98
  sem alteração), `REQUISITOS_BASE_CANONICOS_V1` (4 itens, interseção),
  `REQUISITOS_DIVERGENTES_ENTRE_FONTES` (2 itens, registrados),
  `CADASTRO_REQUISITOS_PRESTACAO_V1` (zero condicionais configurados).
- **`normalizacao_requisitos_prestacao.py`** (ampliado): `TRADUCAO_
  FAMILIA_B_PARA_MOTOR_GERAL` (Fase 9 — único par de vocabulário
  divergente encontrado: `extrato_cliente` ↔ `Extrato da Folha de
  Pagamento`; DCTFWeb/FGTS já usam a mesma grafia nos dois lados).
- **`finalidade_comprovante_pagamento.py`** (ampliado): novo sinal
  `REFORCO_FISCAL_ESTRUTURAL` (sempre FRACA).
- **`produtores_evidencia_fiscal.py`** (ampliado): `reconciliar_
  evidencia_fiscal_com_finalidade` (Fase 10) — fecha o gap fiscal↔
  finalidade: só reforça uma finalidade (FGTS/DCTF-DARF) JÁ identificada
  por descrição, nunca infere sozinho.
- **`ciclo_prestacao.py`** (ampliado): `ResultadoClientePrestacao.
  requisitos_nao_configurados` (Fase 13) + parâmetro opcional
  `tipos_condicionais_para_auditoria` — extensão 100% retrocompatível
  (default vazio, Protocol nunca quebrado, duck-typed).

## Fase 10 — Fiscal ↔ Finalidade: antes/depois

**Antes:** `produtores_evidencia_fiscal.py` alimentava só o tipo
genérico `'Guia'`; `finalidade_comprovante_pagamento.py` nunca recebia
reforço de sinais fiscais — um comprovante de FGTS com código de
receita mas sem a frase "recolhimento do FGTS" ficava INCONCLUSIVO.

**Depois:** `reconciliar_evidencia_fiscal_com_finalidade` combina os 2
vocabulários pelo MESMO resolvedor — testado end-to-end (`Guia do FGTS
-- Código de Receita: 0561` → RESOLVIDA, `Comprovante de Pagamento -
FGTS`). Nunca um segundo motor: a função só traduz sinal fiscal em
`OcorrenciaSinalFinalidade`, o mesmo tipo já consumido por `resolver_
tipo_documental`.

## Fase 11 — Vínculo de benefícios: resultado e limitações

**Resultado:** benefícios individuais (VR/VA avulso, Horas Extras,
Assiduidade) já são resolvidos, no legado, por "CPF→Local→Cliente" —
exatamente o caminho que `FonteVinculosPrestacao`/`resolver_clientes_
validado` já implementam (`_ORIGENS_SUPORTADAS` já inclui COLABORADOR/
FUNCIONARIO/UNIDADE_POSTO). Nenhuma peça nova foi necessária — provado
por teste (`test_magnata_os_classificacao_vinculo_beneficio_prestacao.py`).

**Limitações:** nenhuma granularidade específica (individual vs.
agregado por cliente) foi confirmada para nenhum cliente REAL — a
estrutura suporta ambas, mas nenhuma foi "ligada" a um cliente real
sem evidência.

## Fase 13 — Política incompleta ≠ documento faltando

`ResultadoClientePrestacao` agora carrega DOIS campos nunca confundidos:
`pacote.tipos_faltantes` (requisito CONFIGURADO e ausente do
inventário) e `requisitos_nao_configurados` (tipo do universo canônico
sem NENHUMA configuração de obrigatoriedade para este cliente — nem
exige, nem não exige). Provado por teste que os dois conjuntos nunca
se sobrepõem.

## Matriz canônica (Fase 14)

| Família | Granularidade | Base? | Condicional? | Regra comprovada? | Origem | Clientes configurados | Broadcast? | Gap |
|---|---|---|---|---|---|---|---|---|
| FGTS (Guia) | cliente | ✅ | — | ✅ (2 fontes) | legado + classificacao | todos (base universal) | não | — |
| DCTFWeb - Declaração | global | ✅ | — | ✅ (2 fontes) | idem | todos (broadcast) | sim | lista de clientes do ciclo ainda injetada externamente |
| DCTFWeb - Recibo de Entrega | global | ✅ | — | ✅ (2 fontes) | idem | todos (broadcast) | sim | idem |
| Extrato da Folha de Pagamento | cliente | ✅ | — | ✅ (2 fontes, tradução de vocabulário) | idem | todos (base universal) | não | separação por nome cautelosa |
| Holerite | colaborador (cardinalidade, nunca contagem plana) | ✅ (universal, Adendo de Regra de Negócio) | — | ✅ (decisão de negócio explícita) | Adendo 2026-08-30 | todos (obrigatório por colaborador esperado) | não (multi-cliente via vínculo genuíno, `itens_para_multiplos_clientes_do_vinculo`) | fonte real de `FonteColaboradoresEsperadosPrestacao` ainda não implementada (só Protocol + fixture) |
| Guia DCTFWeb/DARF | global | ❌ (divergente) | disponível | ⚠️ (1 fonte só) | classificacao | **0 configurados** | broadcast possível | NECESSITA CONFIRMAÇÃO HUMANA |
| Certidão | cliente | ❌ | disponível | mecanismo provado (E2E) | nenhuma fonte real | 0 no cadastro real (E2E usa cliente sintético) | não | nenhuma fonte real de Certidão ainda |
| Comprovante de Pagamento - FGTS | cliente | ❌ | não modelado como requisito | reconhecimento robusto (fiscal+finalidade) | classificacao | — | não | não é requisito, é finalidade de um documento já contado como FGTS/outro |
| Comprovante de Pagamento - DCTF/DARF | cliente | ❌ | idem | idem | classificacao | — | não | idem |
| VR/VA, Assiduidade, Horas Extras, Diárias | colaborador/cliente | ❌ | disponível | reconhecimento provado; obrigatoriedade **NÃO comprovada** | app.py `CAPACIDADES_BENEFICIOS` (só reconhecimento) | **0 configurados** | não | NECESSITA CONFIRMAÇÃO HUMANA (qual cliente exige o quê) |
| Folha de Ponto | colaborador | ❌ | disponível | reconhecimento robusto; obrigatoriedade não auditada nesta missão | classificacao | 0 | não | não avaliado nesta missão |
| Assinatura digital | — | — | — | Opção B confirmada (PR #96) | app.py | — | — | caso externo real não modelado |
| Boleto/Nota Fiscal/Guia genérica/desconhecido | — | ❌ | — | fallback, nunca requisito | classificacao | — | — | não é gap — comportamento correto |

Nenhuma família saiu do mapa.

## Fase 15 — Preparar futura edição externa (registrado, não executado)

Precedência futura recomendada (quando um adapter Airtable de
requisitos REAL existir, com semântica confirmada por um humano):

```
1. Configuração canônica versionada (este cadastro, no repo) é a
   BASE — nunca substituída silenciosamente.
2. Um override externo validado (Airtable, quando existir com campo
   confirmado) pode ADICIONAR configuração condicional por cliente —
   nunca contradizer a base universal sem uma nova versão do cadastro
   revisada por humano.
3. Toda leitura externa passa por normalização (`normalizacao_
   requisitos_prestacao.py`) antes de virar override — nunca direto.
```

Não implementado nesta missão — só desenhado e registrado.

## PLANO_DE_VALIDACAO_LIVE_ATUALIZADO (Fase 17 — NÃO EXECUTADO)

```
OBJETIVO:
  1) validar FonteClientesPrestacaoAirtable.listar_ativos() contra o
     cadastro real (contagem, formato de ID);
  2) confirmar que NENHUM campo Airtable hoje tem semântica de
     "requisito obrigatório" que a normalização desta missão já não
     tenha classificado corretamente como NAO_CONFIGURADO.

SISTEMA: Airtable Magnata.
MODO: READ-ONLY.
ESCRITAS: ZERO.
LIMITES: TABLE_CLIENTES (campos Nome/CNPJ já usados); nenhuma tabela
  nova lida sem necessidade comprovada.
DADOS: nunca payload bruto, nunca nome/CNPJ impresso, nunca segredo.
STOP CRITERIA: schema divergente; autenticação falhar; contagem fora
  do esperado; qualquer sinal de que um campo de obrigatoriedade real
  existe e precisa ser mapeado (nesse caso, PARAR e levar a decisão a
  um humano antes de normalizar).
ROLLBACK: nenhum necessário (read-only).
PROIBIDO: update/create/delete; qualquer leitura além de TABLE_CLIENTES
  para este plano específico; qualquer inferência automática de
  obrigatoriedade a partir de um campo não confirmado.
QUANDO EXECUTAR: só mediante confirmação humana específica e separada.
```

## O que NÃO foi feito (registrado, não escondido)

- Nenhum cliente real configurado no cadastro condicional (v1 começa
  vazio — correto, sem evidência).
- Guia DCTFWeb/DARF permanece fora da base universal — aguardando
  confirmação humana explícita, não uma escolha técnica (Holerite JÁ
  foi confirmado pelo Adendo de Regra de Negócio acima).
- Nenhuma auditoria de obrigatoriedade de Folha de Ponto foi feita
  nesta missão (fora do escopo declarado nas fases).
- `FonteColaboradoresEsperadosPrestacao` real (Airtable ou outra fonte)
  ainda não implementada — só o Protocol + fixture de teste existem
  (mesmo padrão do PR #98 para clientes/requisitos: Protocol primeiro,
  adapter real quando houver evidência de onde ler "colaboradores
  esperados por cliente").
- Validação live não executada — plano pronto, aguardando gate humano.

## Documentação relacionada

- `docs/decisoes/politica-operacional-prestacao-v1.md` — fontes/
  Protocols (PR #98), base direta desta missão.
- `docs/decisoes/corredor-operacional-prestacao-v1.md` — corredor
  operacional (PR #97).
- `docs/decisoes/fechamento-cobertura-documental-fase2e3-v1.md` —
  matriz de cobertura documental (produtores fiscal/ponto/temporal).
