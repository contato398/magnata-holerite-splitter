# Corredor autônomo pós-classificação V1 — identificação → validação → inventário → readiness → pacote

**Data:** 2026-08-30
**Branch:** `fix/corredor-autonomo-pos-classificacao-v1`
**Base:** `main @ e9ecdc3cdfc6b83ff5baa0478d3d9a3690383d51` (PR #104 mesclado)
**Status:** ✅ Implementado, testado — o corredor completo (texto → tipo → perfil →
identificação → competência → cliente → inventário → readiness → pacote lógico) funciona
ponta a ponta e sem intervenção humana para as famílias com perfil cadastrado nesta missão.

## Fase 0 — Merge do PR #104

HEAD citado (`43f6f9ee1326b1c9668317edf3a9907d9e88e9e4`) confirmado idêntico ao HEAD real,
base `main`, mergeable_state=clean, CI verde (pytest + governança), 0 reviews, 1 commit.
Mesclado. Merge commit: `e9ecdc3cdfc6b83ff5baa0478d3d9a3690383d51`.

## Fase 3 — Auditoria (antes de criar qualquer coisa nova)

Achado central desta missão: quase toda a infraestrutura pedida **já existia**, espalhada em
módulos isolados de missões anteriores, só faltando a **composição**:

| Peça pedida pela missão | Já existia? | Onde |
|---|---|---|
| `PerfilAplicabilidadeResolucao`/dimensões | ✅ 100% | `contratos.py` |
| Compositor RESOLVIDA/PARCIAL/INCONCLUSIVA | ✅ 100% | `resolucao_semantica.compor_resolucao_semantica` |
| Tradução competência esperada×observada | ✅ 100% | `resolucao_semantica.resolucao_competencia_de_validacao` + `importacao_lote/dominio.py::extrair_competencia_de_texto`/`validar_competencia` |
| ResultadoResolucaoSemantico → item de inventário | ✅ 100% | `adaptador_inventario_prestacao.py` |
| Readiness + pacote lógico por cliente/competência | ✅ 100% | `prestacao_readiness.py` + `pacote_prestacao.py` |
| Necessidades + próxima fonte | ✅ 100% (missão anterior) | `ciclo_prestacao.py` + `estrategia_aquisicao_documental.py` |
| Vínculo colaborador→cliente | ✅ 100% (Protocol) | `vinculos_prestacao.py` |
| Detecção de granularidade (master) | ✅ 100% | `resolucao_master_documental.py` + `evidencia_estrutural_documental.py` |
| Engine de separação genérica | ✅ 100% | `separacao_documental.py` |
| Identificação de colaborador por texto | ✅ existia, mas nomeada/isolada para Holerite | `politica_identificacao_holerite.py` |
| **Cadastro tipo→perfil** | ❌ não existia | **construído nesta missão** |
| **Orquestrador que compõe tudo acima na ordem certa** | ❌ não existia | **construído nesta missão** |

Nenhuma dessas peças pré-existentes foi reimplementada. O trabalho real desta missão foi (1)
o cadastro declarativo tipo→perfil e (2) o fio que costura as peças já existentes.

## O que foi construído

- **`perfil_aplicabilidade_documental.py`** (novo): cadastro DECLARATIVO (dict, nunca um `if`
  gigante — Fase 6) `tipo_documental → PerfilAplicabilidadeResolucao`. Só consultado DEPOIS do
  tipo já resolvido pelo motor (Fase 2 — nunca o inverso). 15 tipos cadastrados nesta missão
  (ver matriz "Universo documental" abaixo); tipo sem perfil vira gate honesto
  (`PERFIL_NAO_CADASTRADO`), nunca um perfil inventado.
- **`identificacao_documental.py`** (novo): extrai o núcleo GENÉRICO de identificação de
  colaborador (CPF/nome → `ResolucaoDimensao` COLABORADOR) de dentro de
  `politica_identificacao_holerite.py` — que **continua existindo**, mesmo nome público, mesma
  classe (`MestreSuspeitoIdentificacaoHolerite` agora é um alias direto, não uma cópia),
  delegando 100% a este módulo novo. Confirmado por regressão: as 94 asserções específicas de
  Holerite (`test_politica_identificacao_holerite.py` + `test_gate_identificacao_holerite_
  esteira.py` + `test_resolucao_semantica_corredor_real.py`) continuam passando sem alteração
  de comportamento (1 teste ajustado: um monkeypatch que substituía `resolver_funcionario`
  precisou apontar para o novo módulo onde a função agora mora — mesma intenção do teste,
  local do patch corrigido).
- **`resolucao_documento_prestacao.py`** (novo): o orquestrador. `processar_documento_
  prestacao(texto, contexto)` compõe: ponte conteúdo→motor (PR #104) → perfil → competência
  (`resolucao_competencia_de_validacao`) → colaborador (`identificacao_documental`) → cliente
  (`vinculos_prestacao.resolver_clientes_validado`, derivado do vínculo, ou `cliente_direto`
  injetado para famílias de granularidade cliente) → `compor_resolucao_semantica`. Quando
  `pronto_para_routing_logico=True`, `avancar_para_inventario` usa o adaptador genérico já
  existente (`resultado_semantico_para_item_inventario`/`itens_para_multiplos_clientes_do_
  vinculo`/`itens_para_clientes_broadcast`, decidido só pelo ESTADO da dimensão CLIENTE, nunca
  um `if tipo ==`) para gerar o(s) item(ns) de inventário. `processar_documento_com_separacao_
  se_necessaria` fecha a Fase 7 (separação): detecta granularidade (`resolucao_master_
  documental`), separa por carry-forward (`separacao_documental`) quando uma estratégia de
  identificação de página é injetada, e REENTRA cada filho no MESMO `processar_documento_
  prestacao` — nunca uma segunda esteira, nunca um segundo motor.
- **`inventario_prestacao_memoria.py`** (novo): `InventarioPrestacaoEmMemoria`, implementação
  local/piloto de `FonteInventarioPrestacao` (Protocol já existente) com `adicionar`/
  `adicionar_muitos` idempotentes — dedup por `(documento_id, cliente)` (nunca só
  `documento_id`: um documento broadcast gera legitimamente N itens do mesmo documento_id, um
  por cliente — achado registrado abaixo).
- **Teste arquitetural estendido** (Fase 27): confirma que nenhum dos 4 módulos novos (+ os 4
  já existentes de missões anteriores) importa Airtable, e que o corredor inteiro funciona
  trocando `fonte_vinculos` por um objeto Python puro qualquer (duck-typed contra o Protocol).
- **Corpus E2E** (10 casos, A-J) + métricas distinguindo AUTO_CLASSIFICADOS de
  AUTO_AVANCOU_COMPLETO (Fase 23: "a segunda é a métrica mais importante").

## Achado real registrado, não corrigido (fora do escopo desta missão)

`fonte_inventario_composta.FonteInventarioPrestacaoComposta` (missão anterior) dedupa só por
`documento_id` — o mesmo problema que corrigi em `InventarioPrestacaoEmMemoria` (broadcast
gera N itens do mesmo `documento_id`) existiria lá se uma fonte real algum dia produzir
broadcast através dela. Não alterado aqui para não misturar uma correção não pedida com o
corredor novo desta missão — candidato a próxima macro-missão.

## Decisão registrada: UNIDADE_POSTO e VINCULO sempre NAO_APLICAVEL nesta missão

Nenhum perfil cadastrado marca UNIDADE_POSTO ou VINCULO como OBRIGATORIA/OPCIONAL, mesmo onde
a Fase 5 da missão sugeria ("Holerite: unidade_posto quando fonte/vínculo permitir"). Motivo:
`compor_resolucao_semantica` (já existente, nunca alterado aqui) trata QUALQUER dimensão
`NAO_AVALIADA` — inclusive uma marcada OPCIONAL sem produtor real — como impedimento a
`RESOLVIDA` consolidado/`pronto_para_routing_logico`. Nenhum produtor resolve UNIDADE_POSTO ou
VINCULO isoladamente hoje; marcá-las OPCIONAL sem produtor bloquearia PERMANENTEMENTE o
auto-avanço de toda família que as usasse. Mais seguro declarar NAO_APLICAVEL agora e promover
quando um produtor real existir — decisão registrada, não escondida.

## Universo documental — matriz de perfil cadastrado (Fase 16)

| Tipo documental | Perfil cadastrado? | Granularidade |
|---|---|---|
| Holerite | ✅ | Colaborador → vínculo → cliente(s) |
| Folha de Ponto | ✅ | Colaborador → vínculo → cliente(s) |
| Comprovante de Pagamento - Salário | ✅ | Colaborador → vínculo → cliente(s) |
| Comprovante de Pagamento - VR/VA | ✅ | Colaborador → vínculo → cliente(s) |
| Comprovante de Pagamento - Assiduidade | ✅ | Colaborador → vínculo → cliente(s) |
| Comprovante de Pagamento - Diárias | ✅ | Colaborador → vínculo → cliente(s) |
| Comprovante de Pagamento - Horas Extras | ✅ | Colaborador → vínculo → cliente(s) |
| Extrato da Folha de Pagamento | ✅ | Cliente direto |
| Guia DCTFWeb/DARF | ✅ | Broadcast |
| DCTFWeb - Declaração | ✅ | Broadcast |
| DCTFWeb - Recibo de Entrega | ✅ | Broadcast |
| FGTS (Guia) | ✅ | Broadcast |
| Guia (genérica) | ✅ | Broadcast |
| Comprovante de Pagamento - FGTS | ✅ | Broadcast |
| Comprovante de Pagamento - DCTF/DARF | ✅ | Broadcast |
| Certidão | ❌ SEM_REGRA | (produtor de tipo existe; perfil de aplicabilidade ainda não) |
| Rescisão | ❌ SEM_REGRA | (tipo legado; perfil ainda não avaliado) |
| EPI | ❌ SEM_REGRA | (tipo legado; perfil ainda não avaliado) |

Nenhuma família com perfil cadastrado ficou sem cobertura de auto-avanço nos testes. Famílias
sem perfil viram `PERFIL_NAO_CADASTRADO` — gate honesto, nunca um perfil inventado, nunca um
avanço silencioso.

## Corpus E2E (10 casos, Fase 24) — resultado

| Caso | Descrição | Resultado |
|---|---|---|
| A | Holerite completo | RESOLVIDO_E_AVANCOU → inventário → pacote PRONTO |
| B | Ponto sem título, estrutural | RESOLVIDO_E_AVANCOU → inventário |
| C | Extrato "master" (2 clientes) | separado em 2 filhos, cada um RESOLVIDO_E_AVANCOU, reentrando no mesmo motor |
| D | DCTF, broadcast | RESOLVIDO_E_AVANCOU → 2 itens (1 por cliente injetado) |
| E | Comprovante Salário | RESOLVIDO_E_AVANCOU → colaborador → cliente por vínculo |
| F | Conflito origem×conteúdo | ORIGEM_CONTEUDO_DIVERGENTE, para imediatamente |
| G | Ambiguidade | TIPO_AMBIGUO, revisão |
| H | PDF sem texto | TEXTO_NAO_EXTRAIVEL, nunca inventa classificação |
| I | Competência necessária não resolvida | REVISAO_NECESSARIA, nunca valida silenciosamente |
| J | Execução dupla | idempotente — sink permanece com 1 item após 3 processamentos |

**Métricas** (corpus de 10 documentos, teste dedicado): TOTAL=10; AUTO_CLASSIFICADOS=6;
**AUTO_AVANCOU_COMPLETO=4** (a métrica mais importante, Fase 23); REVISAO=1; AMBIGUOS=1;
CONFLITOS=1; ERROS_TECNICOS=1; DESCONHECIDOS=1; SEM_PERFIL=1;
PERCENTUAL_AUTO_CORREDOR_COMPLETO=40%.

## Dependência de Airtable — antes/depois

Nenhum módulo novo importa Airtable (confirmado por AST). `fonte_vinculos`/`candidatos_
colaborador`/`cliente_direto`/`tipo_origem` são todos parâmetros genéricos injetados —
provado por substituição: um objeto Python puro (duck-typed contra `FonteVinculosPrestacao`)
resolve o corredor inteiro sem o módulo saber que não é Airtable.

## PLANO_VALIDACAO_LIVE_CORREDOR (Fase 29) — para SKY Tatuí

- **SISTEMA**: Airtable (tabelas já auditadas em missões anteriores — Holerites, Extratos,
  Guias, Funcionários, Locais, Clientes).
- **FONTE**: registros já existentes, anexos já vinculados.
- **CLIENTE**: SKY Tatuí (`recrqv5NvbC37WfSl`).
- **COMPETÊNCIA**: Junho/2026 (conforme instrução desta missão).
- **QUANTIDADE MÁXIMA**: 3 documentos reais (1 Holerite, 1 Extrato, 1 Guia).
- **TIPOS DE DOCUMENTOS**: Holerite, Extrato da Folha de Pagamento, Guia (FGTS ou
  DCTFWeb/DARF).
- **CAMPOS**: só o campo de anexo (binário) + tipo de origem (nome de tabela) — nenhum campo
  de CPF/nome além do mínimo necessário para granularidade, nunca logado.
- **DOWNLOADS**: 1 por documento, direto para memória, nunca persistido em disco fora do
  fluxo de teste.
- **LEITURA**: `extrair_texto_pdf` (mesma extração já em produção) → `resolver_tipo_
  documental_de_pdf` → `processar_documento_prestacao`.
- **ESCRITAS**: ZERO em qualquer sistema externo.
- **PII**: nenhum CPF/nome real logado; só `documento_id`/`tipo`/`estado`/`correlation_id`
  sanitizados.
- **STOP CRITERIA**: qualquer erro técnico não catalogado, qualquer CONFLITO em documento que
  deveria ser trivial, ou qualquer sinal de dado real em log interrompe imediatamente e é
  reportado antes de qualquer novo download.

`READY_FOR_LIVE_CORRIDOR_VALIDATION = TRUE` — o corredor técnico completo está pronto e
testado localmente (10/10 casos do corpus, idempotência confirmada, readiness/pacote reais
alcançados para o caso feliz). A leitura live em si NÃO foi executada nesta missão (instrução
explícita, Fase 28) — fica represada para confirmação humana distinta antes do primeiro acesso
real, conforme CLAUDE.md §6(e).

---

## Adendo substitutivo (antes do merge do PR #105) — benefícios VR/VA/iFood + correção de
## granularidade FGTS/Guia + dedupe por identidade lógica

**Data:** 2026-08-30 (mesmo dia, antes do merge do PR original desta ADR).
**Motivo:** revisão humana identificou 2 erros de modelagem no PR #105 original (FGTS tratado
como broadcast estrutural; Guia genérica com perfil broadcast) e confirmou uma regra de
negócio nova (benefícios VR/VA processados num relatório único por colaborador; transição de
fornecedor VR Benefícios → iFood Benefícios a partir de set/2026).

### Regra canônica de benefícios (confirmada)

VR e VA são normalmente processados num MESMO relatório/pedido, por colaborador. O comprovante
de pagamento correspondente é um documento separado. Ambos entram na prestação de contas.

### O que foi construído

- **`produtores_evidencia_beneficios.py`** (novo): reconhece "Relatório/Pedido/Crédito de
  Benefícios" com força FORTE (frase deliberada e específica — precisa vencer, sem ambiguidade,
  a hipótese MODERADA já existente 'Comprovante de Pagamento - VR/VA' que qualquer menção solta
  de "vale-refeição"/"vale-alimentação" já produzia). Rubrica VR, rubrica VA, total do pedido,
  linhas de beneficiário e fornecedor conhecido (iFood Benefícios, VR Benefícios, Alelo, Sodexo,
  Ticket — lista aberta) são evidências ADICIONAIS na MESMA hipótese — nunca candidatos
  concorrentes 'VR'/'VA'/'iFood'. Um relatório com VR+VA nunca é forçado a escolher um dos dois.
  Fornecedor sozinho (sem a frase de relatório/pedido) nunca basta.
- **Perfil 'Relatório de Benefícios'**: granularidade colaborador (mesma forma de
  Holerite/Ponto) — fatiamento por colaborador via `estrategia_por_cpf_colaborador` (engine já
  existente, reentra cada filho no mesmo motor), cliente derivado do vínculo real do
  colaborador. Nunca uma dimensão nova de "categoria de benefício": VR/VA convivem como
  evidência dentro do MESMO tipo documental.
- **Correção FGTS** ('FGTS' e 'Comprovante de Pagamento - FGTS'): granularidade mudou de
  broadcast para **cliente** — exige `cliente_direto` (origem já resolvida) ou separação por
  CNPJ (`estrategia_por_cnpj_cliente`, já existente); sem cliente resolvido, fica
  `NAO_AVALIADA`/revisão, nunca se espalha.
- **Remoção de 'Guia' genérica do cadastro**: fallback GPS/DARF sem finalidade determinada
  nunca teve perfil suficiente — agora fica honestamente `PERFIL_NAO_CADASTRADO` em vez de
  broadcast automático.
- **DCTF** (Declaração/Recibo/Guia DCTFWeb-DARF/Comprovante DCTF-DARF): preservado broadcast —
  competência-level estruturalmente comprovado, regra NÃO generalizada para FGTS/benefícios.
- **Identidade lógica canônica**: `ItemInventarioPrestacao.identidade_logica` (propriedade nova,
  `documento_id`+`cliente`+`colaborador`) — reaproveitada por `FonteInventarioPrestacaoComposta`
  (corrigida: dedupava só por `documento_id`, perdendo itens legítimos de vínculo múltiplo ou
  fatiamento por colaborador) e por `InventarioPrestacaoEmMemoria` (já usava uma tupla ad-hoc
  `(documento_id, cliente)`, agora usa a mesma identidade canônica do contrato).
- **VINCULO/UNIDADE_POSTO**: docstrings corrigidas para deixar explícito que `NAO_APLICAVEL` é
  uma **limitação técnica temporária** (nenhum produtor resolve essas dimensões isoladamente
  ainda), nunca uma afirmação de que a dimensão não importa ao domínio.

### Limitação registrada, não escondida: comprovante de benefícios "global" sem decomposição

O adendo (§5) pede: um comprovante bancário que paga um LOTE inteiro (múltiplos colaboradores/
clientes) sem trazer, ele mesmo, nenhuma identificação de colaborador — relacionado ao pedido
correspondente — deveria gerar "relações lógicas somente para os clientes do pedido". Isso
exigiria uma capacidade de LIGAR o comprovante ao documento de pedido correspondente (por
competência, valor total, ou outro critério) que não existe hoje e que este adendo não
implementa: inventar esse vínculo sem evidência real violaria a proibição explícita do próprio
adendo (§20, "não inventar vínculos"). O que FOI implementado e testado (§16.E) é o caso real e
comum: um comprovante que TRAZ identificação de colaborador (CPF) segue a mesma granularidade
colaborador→vínculo→cliente já existente, sem inventar nada. O caso "comprovante zero-evidência
+ ligação externa ao pedido" fica como capacidade futura, candidata a próxima macro-missão.

### Regressão

583 → 616+ testes locais (classificação/documental), todos verdes; nenhuma quebra nos 94 testes
específicos de identificação de Holerite nem nos testes de inventário/readiness/pacote já
existentes.
