# Fechamento da base canônica + preparação do primeiro ciclo piloto real (read-only)

**Data:** 2026-08-30
**Branch:** `fix/ciclo-piloto-prestacao-readonly-v1`
**Base:** `main @ edea4fc749db7d98186ab8572d547891a14c0faa` (PR #99 mesclado)
**Status:** ✅ Implementado, testado, pronto para revisão

## Fase 0 — Merge do PR #99: divergência de HEAD registrada

A missão citou `HEAD AUTORIZADO: 0a1f490e11772a177d127ee83fb05fc49040c3e6`
para o PR #99. No momento do merge, o HEAD real do PR já era
`3be0df7f5c9c9be26ad3d5cf8b117e41ceeb0c14` — 1 commit à frente,
contendo o "Adendo de Regra de Negócio — Holerite" que o próprio humano
pediu, numa mensagem distinta, imediatamente antes desta missão (já
implementado e relatado antes desta missão começar). Não é uma mudança
não autorizada nem inexplicada: é o resultado direto do pedido anterior
do mesmo humano. PR #99 foi mesclado no HEAD real (`3be0df7f...`), com
CI verde nos dois checks (`pytest`, `Validação de Governança e
Conformidade`) e `mergeable_state: clean` confirmados antes do merge.
Merge commit: `edea4fc749db7d98186ab8572d547891a14c0faa`.

## Decisões de negócio desta missão (ambas confirmadas pelo humano numa mensagem distinta)

### 1) Guia DCTFWeb/DARF é documento comum/base

Reverte, só para este tipo, a cautela original da Fase 3 do PR #99
("só interseção das 2 fontes vira base universal"). Sai de
`REQUISITOS_DIVERGENTES_ENTRE_FONTES` (V1) e entra em
`REQUISITOS_BASE_CANONICOS_V2`, com `evidencia` citando esta decisão
explícita — nunca inferido automaticamente pela reconciliação de
fontes.

### 2) Holerite NÃO é promovido a requisito universal — reversão do Adendo anterior

O "Adendo de Regra de Negócio — Holerite" (confirmado pelo humano numa
mensagem distinta, registrado em
`docs/decisoes/cadastro-canonico-requisitos-prestacao-v1.md`, vigente
no cadastro V1) foi **revertido** por uma nova decisão de negócio,
também confirmada numa mensagem distinta desta mesma sessão:

> "Holerite é documento individualizado por colaborador/cliente e deve
> ser exigido conforme aplicabilidade/política do cliente/ciclo.
> Ausência de configuração específica NÃO significa automaticamente que
> todo cliente exige Holerite."

**O que NÃO muda:** Holerite nunca esteve em
`REQUISITOS_BASE_CANONICOS_V1`/`V2` (a contagem plana nunca avaliou
Holerite, isso é anterior ao Adendo e continua assim); o MECANISMO de
avaliação por cardinalidade colaborador
(`holerite_obrigatorio_prestacao.avaliar_obrigatoriedade_holerite`,
`pacote_prestacao.combinar_pacote_com_holerite`) não foi descartado —
continua sendo o único jeito correto de avaliar Holerite quando ele
estiver configurado.

**O que muda:** `ciclo_prestacao.executar_ciclo_prestacao` deixa de
acionar essa avaliação incondicionalmente sempre que
`fonte_colaboradores_esperados` é informada. A partir desta missão, só
aciona quando a política efetiva do cliente (montada a partir de
`fonte_requisitos`) já contém um registro **válido** de tipo
'Holerite' — ou seja, o cliente está `CONFIGURADO_EXIGE` para Holerite
via `ConfiguracaoCondicionalCliente`. Sem essa configuração, Holerite
fica `NAO_CONFIGURADO`, como qualquer outro tipo condicional — nunca
aparece em `pacote.tipos_faltantes`.

**Registro de transparência (cláusula constitucional "nenhuma decisão
arquitetural em silêncio"):** o texto original do Adendo
(`HOLERITE_EVIDENCIA` em `cadastro_requisitos_prestacao.py`) foi
preservado tal como redigido — não foi apagado nem "corrigido"
silenciosamente. A reversão é uma decisão NOVA, registrada aqui, e
tanto o cadastro V1 quanto o texto do Adendo original continuam
intactos no código como registro histórico do que foi decidido em cada
momento.

## O que foi criado/alterado

- **`cadastro_requisitos_prestacao.py`**: `REQUISITOS_BASE_CANONICOS_V2`
  (V1 + Guia DCTFWeb/DARF), `REQUISITOS_DIVERGENTES_ENTRE_FONTES_V2`
  (vazia — a única divergência conhecida foi resolvida acima),
  `CADASTRO_REQUISITOS_PRESTACAO_V2` (zero condicionais configurados,
  mesma disciplina de V1). **V1 permanece intacto, byte a byte** —
  nenhuma constante de V1 foi alterada ou removida.
- **`ciclo_prestacao.py`**: `executar_ciclo_prestacao` agora só aciona
  a avaliação de Holerite por cardinalidade quando o cliente estiver
  `CONFIGURADO_EXIGE` para 'Holerite' (verificado a partir dos
  registros já normalizados da política efetiva) **E**
  `fonte_colaboradores_esperados` estiver disponível. Sem qualquer uma
  das duas condições, comportamento idêntico ao de um cliente sem
  Holerite configurado (nenhuma necessidade gerada, `pacote.holerite is
  None`).
- **`ciclo_piloto_prestacao.py`** (novo): runner READ-ONLY do ciclo
  piloto — `executar_ciclo_piloto_readonly` (mesma assinatura de
  `executar_ciclo_prestacao`, reaproveitada sem duplicar orquestração)
  + `LinhaDryRunCicloPiloto`/`gerar_linhas_dry_run` (saída SANITIZADA:
  só `cliente_id`/`competencia_efetiva`/`estado`/`presentes`/
  `faltantes`/`nao_configurados`/`em_revisao` — nunca CPF, nunca nome,
  nunca texto de PDF, nunca token, nunca payload Airtable cru).
- **Testes**: `test_magnata_os_classificacao_cadastro_requisitos_prestacao.py`
  (6 testes novos de V2), `test_magnata_os_classificacao_holerite_obrigatorio_prestacao.py`
  (E2E atualizado para configurar Holerite explicitamente + 1 teste
  novo provando o caso "sem configuração"), `test_magnata_os_classificacao_ciclo_prestacao.py`
  (docstring do teste AST de genericidade atualizado — a exceção
  'holerite' continua válida, agora por outro motivo), `test_ciclo_piloto_prestacao_readonly_e2e.py`
  (novo — E2E completo do runner, 5 clientes sintéticos).

## Matriz canônica atualizada (V2)

| Família | Base universal? | Condicional? | Granularidade | Origem da regra | Configurada? | Necessita decisão? | Competência | Broadcast? | Readiness | Gap |
|---|---|---|---|---|---|---|---|---|---|---|
| FGTS | ✅ | — | cliente | V1 (2 fontes concordam) | — | não | base (ou SKY se aplicável) | não | contagem plana | — |
| DCTFWeb - Declaração | ✅ | — | global | V1 (2 fontes concordam) | — | não | base | sim | contagem plana | lista de clientes do ciclo ainda injetada externamente |
| DCTFWeb - Recibo de Entrega | ✅ | — | global | V1 (2 fontes concordam) | — | não | base | sim | contagem plana | idem |
| Extrato da Folha de Pagamento | ✅ | — | cliente | V1 (2 fontes, tradução de vocabulário) | — | não | base | não | contagem plana | separação por nome cautelosa |
| **Guia DCTFWeb/DARF** | **✅ (V2, decisão de negócio #1)** | — | global | **decisão explícita 2026-08-30 (era divergente em V1)** | — | não | base | disponível (não usado no E2E) | contagem plana | nenhum outro |
| **Holerite** | **❌ NÃO é base universal (reversão, decisão de negócio #2)** | **✅** | colaborador (cardinalidade, nunca contagem plana) | Adendo original revertido; agora condicional como qualquer outro | 0 clientes reais configurados | sim, por cliente (fonte externa ainda não implementada) | base | não (multi-cliente via vínculo genuíno já suportado) | cardinalidade (`avaliar_obrigatoriedade_holerite`), só quando configurado | fonte real de `FonteColaboradoresEsperadosPrestacao` ainda não implementada |
| Horas Extras/Assiduidade/VR/VA/Diárias/Almoço-Janta | ❌ | ✅ (disponível, mesmo mecanismo de Holerite) | cliente/colaborador | reconhecimento provado; obrigatoriedade NÃO comprovada (`CAPACIDADES_BENEFICIOS` só reconhece) | 0 clientes reais configurados | sim, por cliente | base | não | contagem plana (flat, quando configurado) | NECESSITA CONFIRMAÇÃO HUMANA por cliente |
| Assinatura | — | ✅ (quando realmente exigida) | — | Opção B confirmada (PR #96) | 0 configurados | sim, quando o cliente exigir | — | — | — | caso externo real não modelado |
| Certidão | ❌ | ✅ (mecanismo já provado, E2E do PR #99) | cliente | nenhuma fonte real | 0 no cadastro real | sim | base | não | contagem plana | nenhuma fonte real de Certidão ainda |
| SKY (regra de competência) | — | — | — | `DESLOCAMENTO_SKY_TATUI` (inalterado) | já confirmado | não | base − 1 mês | — | — | — |

Nenhuma família saiu do mapa; nenhuma nova foi inventada sem evidência.

## Primeiro ciclo piloto (read-only) — o que foi provado

`test_ciclo_piloto_prestacao_readonly_e2e.py`, via
`executar_ciclo_piloto_readonly`, com 5 clientes sintéticos (nenhum
cliente real ainda) e o cadastro canônico V2 real:

- **Cliente comum** (zero condicionais): base V2 inteira presente →
  `PRONTO`; Holerite e Horas Extras aparecem em `nao_configurados`
  (nunca em `faltantes`) — prova "ausência de configuração nunca vira
  obrigação universal", tanto para Holerite quanto para benefício.
- **Cliente com Holerite configurado**: `CONFIGURADO_EXIGE`, 3
  colaboradores esperados / 2 Holerites presentes / 1 ausente →
  `INCOMPLETO` por cardinalidade (nunca contagem plana); Holerite
  nunca aparece em `nao_configurados` (foi configurado).
- **Cliente sem Guia DCTFWeb/DARF, sem configuração de Holerite**:
  `INCOMPLETO` **só** por `Guia DCTFWeb/DARF` — Holerite continua
  `NAO_CONFIGURADO`, nunca junto em `faltantes` (os dois conjuntos são
  sempre disjuntos, provado por asserção explícita).
- **Cliente com benefício condicional (Horas Extras)**:
  `CONFIGURADO_EXIGE`, documento presente → `PRONTO`; nunca aparece em
  `nao_configurados`.
- **SKY**: competência efetiva = base − 1 mês (regra inalterada),
  base completa na competência deslocada → `PRONTO`.
- **Restrição de segurança do dry-run**: testado por asserção — nenhuma
  linha de saída contém padrão de CPF, a palavra "token", a chave
  "fields" (payload Airtable cru), espaço em `cliente_id`, ou qualquer
  string fora do vocabulário fixo de `tipo_documental` do motor.

## Fonte real de clientes (Airtable) — reconfirmado, não alterado

`FonteClientesPrestacaoAirtable` (adapter já existente, PR #98) segue
`LeitorAirtableSomenteLeitura` (GET-only). O teste já existente
(`test_magnata_os_documental_airtable_clientes_prestacao.py`) já prova
que `listar_ativos` nunca transporta nome como identidade — reafirmado
nesta missão, nenhuma alteração necessária.

## Mapeamento de condicionais — contrato pronto, nenhum campo Airtable criado

`ConfiguracaoCondicionalCliente.tipo_documental` já aceita qualquer
valor de `TIPOS_DOCUMENTAIS_CANONICOS` — Holerite, Horas Extras,
Assiduidade, VR/VA, Diárias, Assinatura já são valores válidos hoje,
sem nenhuma alteração de contrato necessária. Esta missão **não criou
nenhum campo novo no Airtable** — só confirmou, por teste, que o
contrato canônico já suporta receber essa configuração no futuro,
quando um humano confirmar a fonte real.

## PLANO_DE_VALIDACAO_LIVE (Fase final — NÃO EXECUTADO)

```
OBJETIVO:
  1) validar FonteClientesPrestacaoAirtable.listar_ativos() contra a
     base real (contagem, formato de ID);
  2) confirmar que nenhum campo Airtable hoje carrega semântica de
     "Holerite obrigatório" ou "benefício obrigatório" que esta missão
     já não tenha classificado corretamente como NAO_CONFIGURADO;
  3) confirmar ausência de qualquer campo "Guia DCTFWeb/DARF exigido"
     que contradiga a nova base universal V2;
  4) confirmar que a leitura de clientes continua devolvendo apenas
     record id (nunca nome/CNPJ como identidade transportada);
  5) NÃO alterar, NÃO configurar nenhum condicional real nesta
     validação -- só ler e confirmar schema.

SISTEMA: Airtable Magnata.
MODO: READ-ONLY.
ESCRITAS: ZERO.
TABELAS: só TABLE_CLIENTES (campos já usados por
  FonteClientesPrestacaoAirtable/LeitorAirtableSomenteLeitura) -- nenhuma
  tabela nova lida sem necessidade comprovada.
SAÍDA: sanitizada -- contagens, IDs de registro, nomes de campo (nunca
  valor de campo com CPF/nome), nunca payload bruto.
PROIBIDO: create/update/delete/schema change/webhook/automação/upload de
  attachment/mutação de status; qualquer leitura além de TABLE_CLIENTES
  para este plano específico; qualquer inferência automática de
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
- `FonteColaboradoresEsperadosPrestacao` real ainda não implementada —
  só o Protocol + fixtures de teste (mesmo estado desde o PR #99).
- Nenhuma auditoria nova de obrigatoriedade de benefícios por cliente
  real foi feita (seria inventar regra sem evidência).

## Documentação relacionada

- `docs/decisoes/cadastro-canonico-requisitos-prestacao-v1.md` — Adendo
  original de Holerite (agora revertido por esta missão, texto
  preservado).
- `docs/decisoes/politica-operacional-prestacao-v1.md` — fontes/
  Protocols (PR #98).
- `docs/decisoes/corredor-operacional-prestacao-v1.md` — corredor
  operacional (PR #97).
