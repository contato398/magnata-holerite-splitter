# Fechamento da base canônica + preparação do primeiro ciclo piloto real (read-only)

**Data:** 2026-08-30
**Branch:** `fix/ciclo-piloto-prestacao-readonly-v1`
**Base:** `main @ edea4fc749db7d98186ab8572d547891a14c0faa` (PR #99 mesclado)
**Status:** ✅ Implementado, testado, pronto para revisão (inclui correção via ADENDO DE CONTINUIDADE, mesma missão, mesmo dia)

## Fase 0 — Merge do PR #99

A missão original citou `HEAD AUTORIZADO: 0a1f490e11772a177d127ee83fb05fc49040c3e6`
para o PR #99. No momento do merge, o HEAD real do PR já era
`3be0df7f5c9c9be26ad3d5cf8b117e41ceeb0c14` — 1 commit à frente,
contendo o "Adendo de Regra de Negócio — Holerite" que o próprio humano
pediu, numa mensagem distinta, imediatamente antes desta missão. PR #99
foi mesclado nesse HEAD real, com CI verde nos dois checks (`pytest`,
`Validação de Governança e Conformidade`) e `mergeable_state: clean`
confirmados antes do merge. Merge commit:
`edea4fc749db7d98186ab8572d547891a14c0faa`. Um "ADENDO DE CONTINUIDADE"
posterior (ver seção dedicada abaixo) confirmou explicitamente este
mesmo SHA (`3be0df7f...`) como o HEAD correto — a divergência inicial
já estava corretamente resolvida antes dessa confirmação chegar.

## HISTÓRICO COMPLETO DA REGRA DE HOLERITE — 3 decisões, mesmo humano, mesmo dia, mensagens distintas

Transparência total (cláusula constitucional "nenhuma decisão
arquitetural em silêncio") — nenhuma das 3 chegou a ser mesclada em
`main` como comportamento definitivo antes da seguinte a corrigir; toda
a sequência aconteceu dentro desta mesma branch/PR (#100), antes do
merge:

1. **Adendo original** (PR #99, vigente em V1): *"HOLERITE É
   OBRIGATÓRIO EM TODA PRESTAÇÃO DE CONTAS"* — universal, avaliado por
   CARDINALIDADE colaborador, nunca contagem plana.
2. **Esta missão** ("FECHAMENTO DA BASE CANÔNICA") instruiu
   inicialmente **reverter** (1): *"Holerite é documento
   individualizado por colaborador/cliente e deve ser exigido conforme
   aplicabilidade/política do cliente/ciclo. Ausência de configuração
   específica NÃO significa automaticamente que todo cliente exige
   Holerite."* — implementado como gate por
   `ConfiguracaoCondicionalCliente(..., CONFIGURADO_EXIGE)`.
3. **"ADENDO DE CONTINUIDADE"**, do mesmo humano, no mesmo dia,
   **revogou explicitamente (2)** antes deste PR ser mesclado:
   *"QUALQUER trecho do comando anterior que trate Holerite como
   condicional [...] ESTÁ REVOGADO."* — restaura (1) integralmente.

**Decisão efetiva (resultado de 1→2→3, prevalece (3)):** Holerite é
universal, avaliado por CARDINALIDADE colaborador
(`holerite_obrigatorio_prestacao.avaliar_obrigatoriedade_holerite`)
para TODO cliente sempre que `fonte_colaboradores_esperados` estiver
disponível em `ciclo_prestacao.executar_ciclo_prestacao` — nunca
contagem plana, nunca gateado por configuração condicional. O código e
os testes deste PR refletem (3); o texto de (1) e a instrução
intermediária (2) permanecem registrados aqui e nos comentários do
código, nunca apagados.

## Decisão de negócio #1 (mantida, nunca revertida): Guia DCTFWeb/DARF é documento comum/base

Reverte, só para este tipo, a cautela original da Fase 3 do PR #99
("só interseção das 2 fontes vira base universal"). Sai de
`REQUISITOS_DIVERGENTES_ENTRE_FONTES` (V1) e entra em
`REQUISITOS_BASE_CANONICOS_V2`, com `evidencia` citando esta decisão
explícita — nunca inferido automaticamente pela reconciliação de
fontes.

## O que foi criado/alterado (estado final, pós-ADENDO DE CONTINUIDADE)

- **`cadastro_requisitos_prestacao.py`**: `REQUISITOS_BASE_CANONICOS_V2`
  (V1 + Guia DCTFWeb/DARF), `REQUISITOS_DIVERGENTES_ENTRE_FONTES_V2`
  (vazia — a única divergência conhecida foi resolvida acima),
  `CADASTRO_REQUISITOS_PRESTACAO_V2` (zero condicionais configurados,
  mesma disciplina de V1; Holerite NUNCA é um candidato a condicional
  aqui — é universal). **V1 permanece intacto, byte a byte** — nenhuma
  constante de V1 foi alterada ou removida.
- **`ciclo_prestacao.py`**: `executar_ciclo_prestacao` aciona a
  avaliação de Holerite por cardinalidade SEMPRE que
  `fonte_colaboradores_esperados` estiver disponível, para TODO
  cliente — sem gate por configuração condicional (comportamento
  idêntico ao Adendo original de V1; a versão intermediária com gate,
  criada e depois revogada dentro desta mesma missão, nunca chegou a
  ser mesclada).
- **`ciclo_piloto_prestacao.py`** (novo): runner READ-ONLY do ciclo
  piloto — `executar_ciclo_piloto_readonly` (mesma assinatura de
  `executar_ciclo_prestacao`, reaproveitada sem duplicar orquestração)
  + `LinhaDryRunCicloPiloto`/`gerar_linhas_dry_run` (saída SANITIZADA:
  só `cliente_id`/`competencia_efetiva`/`estado`/`presentes`/
  `faltantes`/`nao_configurados`/`em_revisao` — nunca CPF, nunca nome,
  nunca texto de PDF, nunca token, nunca payload Airtable cru).
- **`airtable_colaboradores_esperados_prestacao.py`** (novo, ADENDO DE
  CONTINUIDADE item 3): `FonteColaboradoresEsperadosPrestacaoAirtableShadow`
  — adapter read-only, direção INVERSA de
  `FonteVinculosPrestacaoAirtableShadow` já existente (que resolve
  COLABORADOR→CLIENTE; este resolve CLIENTE→COLABORADORES esperados),
  reaproveitando as MESMAS 2 tabelas/campos já auditados
  (`TABLE_LOCAIS`/`F_LOCAL_CLIENTE`, `TABLE_FUNC`/`F_FUNC_LOCAIS`) +
  `F_FUNC_STATUS`/`STATUS_FUNCIONARIO_ATIVO` (duplicado de `app.py`,
  nunca importado do legado) para restringir a colaboradores ATIVOS.
  Ver seção dedicada abaixo.
- **Testes**: `test_magnata_os_classificacao_cadastro_requisitos_prestacao.py`
  (testes de V2 corrigidos para "Holerite universal, nunca condicional"),
  `test_magnata_os_classificacao_holerite_obrigatorio_prestacao.py`
  (E2E revertido para incondicional + 2 testes novos de 4
  colaboradores esperados — ver ADENDO DE CONTINUIDADE item 5),
  `test_magnata_os_classificacao_ciclo_prestacao.py` (docstring do
  teste AST de genericidade corrigido), `test_ciclo_piloto_prestacao_readonly_e2e.py`
  (E2E do runner corrigido — Holerite universal, avaliado por
  cardinalidade sem gate), `test_airtable_colaboradores_esperados_prestacao.py`
  (novo — 11 testes do adapter, só com `LeitorAirtableSomenteLeitura`
  fake, nunca Airtable live).

## Colaboradores esperados por cliente — auditoria e implementação (ADENDO DE CONTINUIDADE, item 3)

**Pergunta:** a composição de colaboradores esperados por cliente pode
ser derivada de estruturas/vínculos já conhecidos, sem parar para pedir
uma fonte nova?

**Resposta: SIM.** Auditoria confirmou que `FonteVinculosPrestacaoAirtableShadow`
(`airtable_vinculos_prestacao.py`, já existente desde antes desta
missão) já resolve COLABORADOR/FUNCIONARIO/UNIDADE_POSTO → CLIENTE lendo
`TABLE_LOCAIS` (campo `F_LOCAL_CLIENTE`) e `TABLE_FUNC` (campo
`F_FUNC_LOCAIS`). A direção INVERSA (CLIENTE → COLABORADORES) é
derivável das MESMAS 2 tabelas — só troca qual lado é conhecido e qual
é buscado. Adicionalmente, `app.py` já documenta um campo de Status do
Funcionário (`F_FUNC_STATUS`, valores conhecidos incluindo `'Ativo'`)
que permite restringir a colaboradores efetivamente ativos.

**Implementado:** `FonteColaboradoresEsperadosPrestacaoAirtableShadow`
— lê TODOS os registros de `TABLE_LOCAIS`/`TABLE_FUNC` (sem
`filterByFormula`, já que este pacote nunca duplica NOMES de campo, só
IDs — uma fórmula do Airtable exige o nome) e filtra em Python:
locais cujo `F_LOCAL_CLIENTE` contém o cliente pedido → funcionários
cujo `F_FUNC_LOCAIS` intersecta esses locais E `F_FUNC_STATUS ==
'Ativo'`. Nunca solicita `Nome Completo`/`CPF` — identidade sempre
`ReferenciaCanonica('COLABORADOR', func_id)`.

**GAP registrado, não escondido:** não existe, no schema auditado até
agora, nenhum campo de vínculo com validade/período (início/fim)
distinto do Status atual — "esperado NESTA competência" é aproximado
por "vinculado a um Local do cliente E Status atual = Ativo" (a mesma
aproximação implícita que já vale para toda leitura de vínculo deste
módulo). Se isso se mostrar insuficiente para um cliente real, é uma
decisão humana nova, não uma inferência a fazer aqui.

**NUNCA acessado com Airtable live nesta missão** — testado só com
`LeitorAirtableSomenteLeitura` fake (11 testes,
`test_airtable_colaboradores_esperados_prestacao.py`), mesma disciplina
de `test_airtable_vinculos_prestacao.py`.

## Matriz canônica atualizada (V2, pós-ADENDO DE CONTINUIDADE)

| Família | Base universal? | Condicional? | Granularidade | Origem da regra | Configurada? | Necessita decisão? | Competência | Broadcast? | Readiness | Gap |
|---|---|---|---|---|---|---|---|---|---|---|
| FGTS | ✅ | — | cliente | V1 (2 fontes concordam) | — | não | base (ou SKY se aplicável) | não | contagem plana | — |
| DCTFWeb - Declaração | ✅ | — | global | V1 (2 fontes concordam) | — | não | base | sim | contagem plana | lista de clientes do ciclo ainda injetada externamente |
| DCTFWeb - Recibo de Entrega | ✅ | — | global | V1 (2 fontes concordam) | — | não | base | sim | contagem plana | idem |
| Extrato da Folha de Pagamento | ✅ | — | cliente | V1 (2 fontes, tradução de vocabulário) | — | não | base | não | contagem plana | separação por nome cautelosa |
| **Guia DCTFWeb/DARF** | **✅ (V2, decisão de negócio #1)** | — | global | decisão explícita 2026-08-30 (era divergente em V1) | — | não | base | disponível (não usado no E2E) | contagem plana | nenhum outro |
| **Holerite** | **✅ (universal, Adendo original — confirmado por ADENDO DE CONTINUIDADE)** | — | colaborador (cardinalidade, nunca contagem plana) | Adendo original + ADENDO DE CONTINUIDADE (revogou tentativa intermediária de tornar condicional) | todos (obrigatório por colaborador esperado) | não | base | não (multi-cliente via vínculo genuíno já suportado) | cardinalidade (`avaliar_obrigatoriedade_holerite`), sempre que houver fonte de colaboradores esperados | fonte de colaboradores esperados agora tem adapter Airtable-shadow (não live) — falta validação live |
| Horas Extras/Assiduidade/VR/VA/Diárias/Almoço-Janta | ❌ | ✅ (disponível, mesmo mecanismo de configuração condicional) | cliente/colaborador | reconhecimento provado; obrigatoriedade NÃO comprovada (`CAPACIDADES_BENEFICIOS` só reconhece) | 0 clientes reais configurados | sim, por cliente | base | não | contagem plana (flat, quando configurado) | NECESSITA CONFIRMAÇÃO HUMANA por cliente |
| Assinatura | — | ✅ (quando realmente exigida) | — | Opção B confirmada (PR #96) | 0 configurados | sim, quando o cliente exigir | — | — | — | caso externo real não modelado |
| Certidão | ❌ | ✅ (mecanismo já provado, E2E do PR #99) | cliente | nenhuma fonte real | 0 no cadastro real | sim | base | não | contagem plana | nenhuma fonte real de Certidão ainda |
| SKY (regra de competência) | — | — | — | `DESLOCAMENTO_SKY_TATUI` (inalterado) | já confirmado | não | base − 1 mês | — | — | — |

Nenhuma família saiu do mapa; nenhuma nova foi inventada sem evidência.

## Primeiro ciclo piloto (read-only) — o que foi provado (corrigido pelo ADENDO DE CONTINUIDADE)

`test_ciclo_piloto_prestacao_readonly_e2e.py`, via
`executar_ciclo_piloto_readonly`, com 5 clientes sintéticos (nenhum
cliente real ainda) e o cadastro canônico V2 real:

- **Cliente comum**: base V2 inteira presente, zero colaboradores
  esperados (Holerite vacuamente satisfeito) → `PRONTO`; Horas Extras
  aparece em `nao_configurados` (nunca em `faltantes`) — prova
  "ausência de configuração de benefício nunca vira obrigação".
- **Cliente Holerite incompleto**: 3 colaboradores esperados / 2
  Holerites presentes / 1 ausente → `INCOMPLETO` por cardinalidade
  (nunca contagem plana, nunca gateado por configuração condicional —
  Holerite nunca aparece em `nao_configurados`, pois não passa por
  `ConfiguracaoCondicionalCliente`).
- **Cliente sem Guia DCTFWeb/DARF**: zero colaboradores esperados
  (Holerite vacuamente OK) → `INCOMPLETO` **só** por `Guia
  DCTFWeb/DARF`.
- **Cliente com benefício condicional (Horas Extras)**:
  `CONFIGURADO_EXIGE`, documento presente → `PRONTO`; nunca aparece em
  `nao_configurados`.
- **SKY**: competência efetiva = base − 1 mês (regra inalterada),
  base completa na competência deslocada → `PRONTO`.
- **Restrição de segurança do dry-run**: testado por asserção — nenhuma
  linha de saída contém padrão de CPF, a palavra "token", a chave
  "fields" (payload Airtable cru), espaço em `cliente_id`, ou qualquer
  string fora do vocabulário fixo de `tipo_documental` do motor.

## Teste E2E adicional obrigatório (ADENDO DE CONTINUIDADE, item 5)

Em `test_magnata_os_classificacao_holerite_obrigatorio_prestacao.py`:
cliente com 4 colaboradores esperados — 4 Holerites presentes →
`avaliar_obrigatoriedade_holerite(...).completo is True`; 3 presentes →
pacote `INCOMPLETO` via `executar_ciclo_prestacao`, com EXATAMENTE 1
necessidade sanitizada (nunca CPF/nome). O caso "1 colaborador
vinculado a 2 clientes → 1 identidade documental válida nos 2 pacotes"
já estava coberto por `test_colaborador_vinculado_a_2_clientes_gera_mesmo_holerite_para_ambos`
(sem alteração necessária).

## Fonte real de clientes (Airtable) — reconfirmado, não alterado

`FonteClientesPrestacaoAirtable` (adapter já existente, PR #98) segue
`LeitorAirtableSomenteLeitura` (GET-only). O teste já existente
(`test_magnata_os_documental_airtable_clientes_prestacao.py`) já prova
que `listar_ativos` nunca transporta nome como identidade — reafirmado
nesta missão, nenhuma alteração necessária.

## Mapeamento de condicionais — contrato pronto, nenhum campo Airtable criado

`ConfiguracaoCondicionalCliente.tipo_documental` já aceita qualquer
valor de `TIPOS_DOCUMENTAIS_CANONICOS` — Horas Extras, Assiduidade,
VR/VA, Diárias, Assinatura já são valores válidos hoje, sem nenhuma
alteração de contrato necessária (Holerite NÃO é candidato a este
mecanismo — é universal). Esta missão **não criou nenhum campo novo no
Airtable** — só confirmou, por teste, que o contrato canônico já
suporta receber essa configuração no futuro, quando um humano
confirmar a fonte real.

## PLANO_DE_VALIDACAO_LIVE (NÃO EXECUTADO)

```
OBJETIVO:
  1) validar FonteClientesPrestacaoAirtable.listar_ativos() contra a
     base real (contagem, formato de ID);
  2) validar FonteColaboradoresEsperadosPrestacaoAirtableShadow contra
     a base real (contagem de colaboradores ativos por cliente,
     formato de ID) -- read-only, mesmas tabelas já lidas por
     FonteVinculosPrestacaoAirtableShadow;
  3) confirmar que nenhum campo Airtable hoje carrega semântica de
     "benefício obrigatório" que esta missão já não tenha classificado
     corretamente como NAO_CONFIGURADO;
  4) confirmar ausência de qualquer campo "Guia DCTFWeb/DARF exigido"
     que contradiga a nova base universal V2;
  5) NÃO alterar, NÃO configurar nenhum condicional real nesta
     validação -- só ler e confirmar schema.

SISTEMA: Airtable Magnata.
MODO: READ-ONLY.
ESCRITAS: ZERO.
TABELAS: TABLE_CLIENTES, TABLE_LOCAIS, TABLE_FUNC (campos já usados
  pelos adapters existentes) -- nenhuma tabela nova lida sem
  necessidade comprovada.
SAÍDA: sanitizada -- contagens, IDs de registro, nomes de campo (nunca
  valor de campo com CPF/nome), nunca payload bruto.
PROIBIDO: create/update/delete/schema change/webhook/automação/upload de
  attachment/mutação de status; qualquer leitura além das 3 tabelas
  acima para este plano específico; qualquer inferência automática de
  obrigatoriedade a partir de um campo não confirmado por um humano.
STOP CRITERIA: schema divergente do esperado; campo ambíguo cujo
  significado não é óbvio; falha de autenticação; necessidade de
  escrita para completar a validação; volume de registros fora do
  esperado; qualquer exposição de PII desnecessária.
ROLLBACK: nenhum necessário (read-only, sem mutação).
QUANDO EXECUTAR: só mediante confirmação humana específica e separada
  desta missão -- nenhuma leitura live foi realizada nesta missão.
```

## READY_FOR_LIVE_READONLY_VALIDATION = **FALSE**

Motivo: nenhuma leitura live foi executada nesta missão (fora de
escopo, por instrução explícita da missão). O plano acima está pronto,
mas falta a confirmação humana específica e separada exigida por
`/CLAUDE.md` §6 (autorização por fase) antes do primeiro acesso real ao
Airtable — mesmo sendo read-only.

## O que NÃO foi feito (registrado, não escondido)

- Nenhum cliente real configurado no cadastro condicional V2 (começa
  vazio, mesma disciplina de V1).
- Nenhuma leitura live do Airtable foi executada.
- Nenhum campo novo foi criado no Airtable (nem proposto para criação
  automática) — só o contrato canônico já pronto para recebê-lo no
  futuro.
- `FonteColaboradoresEsperadosPrestacaoAirtableShadow` foi implementada
  e testada (fakes) nesta missão — mas nunca validada contra o
  Airtable real; a aproximação "vinculado a um Local ativo do cliente"
  para "esperado nesta competência" (sem campo de período/validade)
  é um gap explícito, não uma garantia definitiva.
- Nenhuma auditoria nova de obrigatoriedade de benefícios por cliente
  real foi feita (seria inventar regra sem evidência).

## Documentação relacionada

- `docs/decisoes/cadastro-canonico-requisitos-prestacao-v1.md` — Adendo
  original de Holerite (confirmado como decisão efetiva por esta
  missão, após uma tentativa intermediária de reversão ter sido
  revogada — texto original preservado).
- `docs/decisoes/politica-operacional-prestacao-v1.md` — fontes/
  Protocols (PR #98).
- `docs/decisoes/corredor-operacional-prestacao-v1.md` — corredor
  operacional (PR #97).
