# Corredor operacional da Prestação de Contas (v1)

**Data:** 2026-08-30
**Branch:** `fix/corredor-operacional-prestacao-v1`
**Base:** `main @ 525fae9c314db9e875e3a49775ec2468934ba71b` (PR #96 mesclado)
**Status:** ✅ Implementado, testado (shadow), pronto para revisão

## Resumo executivo

Os PRs #93–#96 construíram o motor de RECONHECIMENTO. Esta missão
transforma isso num CORREDOR OPERACIONAL: dado um lote heterogêneo de
documentos de vários clientes, o sistema agora separa, identifica,
vincula, valida competência, inventaria, avalia readiness e monta um
PACOTE LÓGICO por cliente — indicando com precisão o que está completo
e o que falta — tudo pelo MESMO motor, sem corredor especial por tipo.

## Auditoria curta (Fase 2) — o que já existia

A auditoria revelou que boa parte da infraestrutura operacional JÁ
EXISTIA em shadow mode, criada em fases anteriores não documentadas
nesta cadeia de PRs recentes:

| Peça | Onde | Estado antes |
|---|---|---|
| `FonteInventarioPrestacao` (Protocol) | `inventario_prestacao.py` | pronta, genérica |
| `FonteInventarioPrestacaoResultadosShadow` | `inventario_prestacao_resultados.py` | específica — `if/elif` por `TipoDocumental` (Família B) |
| `PoliticaRequisitosPrestacao`/`REQUISITOS_BASE_PRESTACAO` | `politica_requisitos_prestacao.py` | pronta, mas vocabulário Família B (`extrato_cliente`) |
| `avaliar_prestacao_readiness`/`avaliar_prestacao_shadow` | `prestacao_readiness.py`/`prestacao_shadow.py` | prontos, genéricos |
| `ponte_prestacao_holerite.py` | `documental/modulo01/` | específica — só Holerite, opera sobre `HoleriteConfirmadoDTO` |
| Pacote lógico por cliente | — | **não existia** |
| Adaptador genérico `ResultadoResolucaoSemantico -> ItemInventarioPrestacao` | — | **não existia** |

Conclusão da auditoria: faltavam exatamente 2 peças (adaptador
genérico + pacote lógico) para o corredor operacional se fechar — o
resto já estava pronto e só precisava ser ORQUESTRADO, não recriado.

## O que foi criado

### 1. `adaptador_inventario_prestacao.py` (Fase 3) — o 3º caminho, genérico

`resultado_semantico_para_item_inventario(documento_id, resolucao,
cliente_broadcast=None) -> Optional[ItemInventarioPrestacao]`. Lê
TIPO_DOCUMENTAL/COMPETENCIA/CLIENTE de um `ResultadoResolucaoSemantico`
JÁ COMPOSTO — nunca reavalia, nunca conhece nenhum tipo por nome (prova
AST). Suporta as 3 granularidades (Fase 4):
- **por colaborador** (Holerite, Ponto): CLIENTE já vem resolvido via
  vínculo (`resolver_clientes_validado`) ANTES da composição — o
  adaptador só lê o resultado, nunca calcula vínculo;
- **por cliente** (Extrato, FGTS, Certidão, comprovantes): CLIENTE
  resolvido diretamente;
- **global/broadcast** (DCTFWeb): CLIENTE `NAO_APLICAVEL` no perfil +
  `cliente_broadcast` injetado por quem orquestra.

`itens_para_clientes_broadcast(documento_id, resolucao, clientes)` gera
N itens lógicos com o MESMO `documento_id` — nunca duplica identidade
documental (Fase 11), provado em teste.

**Nunca substitui** `FonteInventarioPrestacaoResultadosShadow` nem
`ponte_prestacao_holerite.py` — ambos preservados, migração progressiva
(cláusula pétrea #14).

### 2. `pacote_prestacao.py` (Fase 10)

`EstadoPacotePrestacao` (PRONTO/INCOMPLETO/EM_REVISAO/BLOQUEADO) —
mapeado 1:1 a partir do `EstadoPrestacaoReadiness` já existente
(PRONTO/FALTANDO/REVISAR/DIVERGENTE), nunca uma decisão nova.
`PacotePrestacaoCliente` (cliente, competência, estado, itens
incluídos, obrigatórios, faltantes, motivos) — nunca gera ZIP/PDF.
`avaliar_e_montar_pacote` orquestra política + inventário + readiness
+ pacote numa função só, reaproveitando `avaliar_prestacao_readiness`
sem alteração.

### 3. `PoliticaRequisitosPrestacao.requisitos_base` (extensão aditiva)

Campo novo, opcional, com default EXATAMENTE `REQUISITOS_BASE_PRESTACAO`
(zero mudança de comportamento para quem já usa a classe). Permite que
o corredor NOVO (vocabulário do motor geral: `'Holerite'`, `'Extrato da
Folha de Pagamento'`, etc.) construa sua própria base sem editar a
constante histórica (que serve o corredor Família B/Airtable-shadow já
em produção-sombra, testado por 5+ arquivos de teste estáveis).

**Decisão registrada:** `REQUISITOS_BASE_PRESTACAO` continua com
`'extrato_cliente'` (valor de `TipoDocumental.EXTRATO_CLIENTE`,
vocabulário Família B) — DIFERENTE de `'Extrato da Folha de Pagamento'`
(motor geral). Os 2 vocabulários NÃO foram unificados (mesma decisão já
registrada no PR #96 para fiscal↔finalidade) — editar a constante
histórica quebraria testes estáveis do corredor em produção-sombra.

## Corredor E2E (Fases 8/9/13) — `test_corredor_operacional_prestacao_e2e.py`

Um único cenário integrado, 4 "clientes" (A completo, B incompleto, C
em revisão, SKY com competência deslocada), 11 documentos/situações:

1. Master Extrato Mensal (A+B) → separado → 2 filhos → inventário.
2. Holerite avulso do colaborador de A (vínculo real).
3. Folha de Ponto estrutural do mesmo colaborador (sem frase literal).
4. FGTS (A) — B nunca recebe, de propósito (fica faltando).
5. DCTFWeb - Declaração — BROADCAST para A, B, C (1 identidade, 3 itens
   lógicos, provado sem duplicação).
6. Comprovante de pagamento com finalidade Salário (A).
7. Certidão (A).
8. Benefício VR/VA via abreviação+estrutura reforçando (A).
9. Documento desconhecido e documento ambíguo — nunca viram item.
10. Documento com CLIENTE ambíguo (C) — ancora o pacote em EM_REVISAO.
11. SKY Tatuí — competência esperada calculada pela política existente
    (base − 1 mês = 2026-06), validada, pacote próprio PRONTO na
    competência CORRETA (nunca a base).

Resultado determinístico: pacote A = PRONTO; pacote B = INCOMPLETO
(faltam exatamente `Holerite` e `FGTS`); pacote C = EM_REVISAO; pacote
SKY = PRONTO em `2026-06`. Broadcast confirmado sem duplicação física
(mesmo `documento_id` nos 3 pacotes).

## Cobertura documental — corredor completo (Fase 15)

| Família | Reconhecimento | Separação | Identificação/Vínculo | Competência | Cliente | Colaborador | Inventário | Readiness | Pacote | Gap |
|---|---|---|---|---|---|---|---|---|---|---|
| Holerite | ROBUSTO | por CPF pronta | vínculo real | pronta | via vínculo | resolvido | ✅ | ✅ | ✅ | fallback por nome do colaborador |
| Folha de Ponto | ROBUSTO (estrutural) | por CPF pronta | vínculo real | pronta | via vínculo | resolvido | ✅ | ✅ | ✅ | extração completa de dias/horários |
| Extrato Mensal | PARCIAL | CNPJ+nome | direta | pronta | direto | n/a | ✅ | ✅ | ✅ | separação por nome ainda arriscada em ambiguidade |
| FGTS (guia) | ROBUSTO | n/a | direta | pronta | direto | n/a | ✅ | ✅ | ✅ | — |
| DCTFWeb Declaração/Recibo, Guia DCTFWeb/DARF | ROBUSTO | n/a | broadcast | pronta | broadcast (injetado) | n/a | ✅ | ✅ | ✅ | lista de clientes do ciclo ainda injetada manualmente (sem cadastro real) |
| Comprovante de pagamento (finalidade) | PARCIAL | n/a | direta | pronta | direto | n/a | ✅ | ✅ | ✅ | integração fiscal↔finalidade (gap do PR #96, não bloqueia corredor) |
| Certidão | PARCIAL | n/a | direta | pronta | direto | n/a | ✅ | ✅ | ✅ | vínculo formal a competência específica ainda simples |
| VR/VA (benefício) | PARCIAL | n/a | direta | pronta | direto | n/a | ✅ (provado) | ✅ (provado) | ✅ (provado) | vínculo benefício→pessoa não modelado |
| Assiduidade/Diárias/Horas Extras | PARCIAL | n/a | direta | pronta | direto | n/a | capaz (não exercitado no E2E) | capaz | capaz | mesmo padrão de VR/VA, não testado nesta missão |
| Certidões-vínculo, benefícios-pessoa, assinatura digital externa | NECESSITA REGRA DE NEGÓCIO | — | — | — | — | — | bloqueado | bloqueado | bloqueado | decisão de negócio pendente, não inventada |
| Desconhecido/Ambíguo/Conflito | por design nunca "resolvido" | — | — | — | — | — | nunca vira item | nunca finge PRONTO | nunca finge PRONTO | correto por design, não é gap |

Nenhuma família saiu do mapa.

## Decisões arquiteturais registradas

1. **`PoliticaRequisitosPrestacao.requisitos_base` é aditivo, nunca
   substitui `REQUISITOS_BASE_PRESTACAO`** — ver acima.
2. **Broadcast nunca descobre sua própria lista de clientes** —
   `itens_para_clientes_broadcast` exige a lista injetada por quem
   orquestra (hoje, um teste; amanhã, um cadastro real de clientes
   ativos no ciclo). O motor documental nunca sabe "quantos clientes
   existem" — cláusula pétrea #10.
3. **Cliente "em revisão" é modelado via CLIENTE ambíguo na resolução-
   âncora**, não via um novo estado de pacote — reaproveita a mesma
   regra de readiness (`necessita_revisao_humana`/`estados_revisao`)
   já existente, nunca uma lógica de revisão paralela.
4. **Gap fiscal↔finalidade (PR #96) não foi fechado nesta missão** —
   confirmado que não bloqueia o corredor (FGTS/DCTF resolvem via
   produtor textual, que já é suficiente para o E2E); fica registrado
   como prioridade para a próxima missão, não tratado como bloqueio.

## O que NÃO foi feito (registrado, não escondido)

- Distribuição real (e-mail/WhatsApp/Airtable/Render) — fora de escopo,
  nunca implementada.
- Geração física de pacote (ZIP/PDF) — o pacote é só LÓGICO, conforme
  pedido.
- Unificação fiscal↔finalidade de pagamento — gap conhecido, não
  bloqueia o corredor, registrado para próxima missão.
- Vínculo formal benefício→pessoa/cliente — capacidade de
  RECONHECER benefício existe (Fase 8 do E2E prova), mas o vínculo
  automático a um colaborador/cliente específico ainda depende de
  composição manual (como no E2E), não de uma regra genérica nova.
- Busca complementar de faltantes (Gmail/Airtable/armazenamento) — o
  contrato de pacote já expõe `tipos_faltantes`, pronto para uma etapa
  futura de busca, mas nenhuma busca foi implementada aqui.

## Documentação relacionada

- `docs/decisoes/fechamento-cobertura-documental-fase2e3-v1.md` —
  produtores fiscal/ponto/temporal reaproveitados sem alteração.
- `docs/decisoes/capacidades-transversais-motor-documental-v1.md` —
  separação e master, base da granularidade usada aqui.
- `docs/decisoes/motor-geral-compreensao-documental-v1.md` — motor de
  TIPO_DOCUMENTAL.
- `docs/decisoes/resolucao-semantica-fase2e-v1.md` — compositor geral.
