# Auditoria — motor canônico de inventário/completude da Prestação de Contas já existe (v1)

**Data:** 2026-09-03
**Branch:** `docs/auditoria-inventario-completude-prestacao-v1`
**Base:** `origin/main @ da34f0143a34ce328bb6a981818c683d770c854d`
**Status:** ✅ Auditoria concluída — nenhum código novo nesta missão, por decisão explícita do humano após apresentação deste achado.

## Motivação desta missão

Foi solicitado o "primeiro motor canônico de inventário/completude da
prestação de contas" — somente leitura, capaz de responder por
CLIENTE + UNIDADE/POSTO + COMPETÊNCIA quais documentos são esperados,
encontrados, ausentes ou ambíguos, e se o pacote está
COMPLETO/INCOMPLETO/INDETERMINADO — com SKY Tatuí como caso
adversarial de validação, e regra pétrea explícita: **reutilizar antes
de criar, nunca duplicar motor documental/classificador/orquestrador
existente**.

A própria missão exigia, antes de qualquer implementação: auditar todo
código relacionado, procurar mecanismo existente de inventário/
completude/pacote mensal, e **documentar achados com caminhos/funções
reais antes de implementar**. Esta auditoria cumpre exatamente essa
exigência — e o resultado muda o escopo do trabalho.

## Achado central

**O motor canônico pedido já existe**, construído incrementalmente
entre 2026-08-29 e 2026-08-30 pelos PRs #93–#101 (mesclados em `main`),
com 7 ADRs já registrando cada fase, e **já validado ponta-a-ponta com
SKY Tatuí como piloto** — o mesmo caso adversarial que esta missão
pediu para usar. Implementar um motor novo neste momento duplicaria
esse trabalho e violaria a regra pétrea da própria missão.

## Mapeamento: conceito pedido → implementação real já existente

| Conceito pedido | Caminho real | Nome real |
|---|---|---|
| `EscopoPrestacao` (cliente + unidade + competência + colaboradores no período) | `magnata_os/classificacao/competencia_esperada_prestacao.py` | `ContextoCicloPrestacao`, `REFERENCIA_CLIENTE_SKY_TATUI` |
| `ItemEsperado` (requisitos por escopo, com origem de regra) | `magnata_os/classificacao/cadastro_requisitos_prestacao.py`, `politica_requisitos_prestacao.py` | `PoliticaRequisitosPrestacao`, `CADASTRO_REQUISITOS_PRESTACAO_V2`, `OverrideRequisitosPrestacao` |
| `ItemEncontrado` (documento + evidências + estado de resolução) | `magnata_os/classificacao/prestacao_readiness.py` | `ItemInventarioPrestacao` |
| Fonte de inventário substituível/composta (Airtable nunca é verdade semântica direta) | `magnata_os/classificacao/inventario_prestacao.py`, `fonte_inventario_composta.py` | `FonteInventarioPrestacao` (Protocol), `FonteInventarioPrestacaoComposta` |
| `ResultadoCompletude` (COMPLETO/INCOMPLETO/INDETERMINADO) | `prestacao_readiness.py`, `pacote_prestacao.py` | `EstadoPrestacaoReadiness` (PRONTO/FALTANDO/REVISAR/DIVERGENTE) mapeado 1:1 para `EstadoPacotePrestacao` (PRONTO/INCOMPLETO/EM_REVISAO/BLOQUEADO) |
| `PendenciaInventario` (AMBIGUO, COMPETENCIA_DIVERGENTE, DUPLICIDADE_CONFLITANTE, RELACAO_NAO_RESOLVIDA) | `resolucao_documento_prestacao.py`, `contratos.py` | `EstadoCorredorDocumentoPrestacao` (inclui `TIPO_AMBIGUO`), `EstadoResolucaoDimensao` |
| Colaborador → cliente/posto via vínculo **histórico** (nunca alocação atual reconstruindo o passado) | `magnata_os/documental/alocacao/` + `classificacao/vinculos_prestacao.py`, `vinculo_unidade_prestacao.py` | `resolver_clientes_validado`, `FonteVinculosPrestacaoAirtableShadow`, memória de vigência temporal (`temporal.py`) |
| Holerite obrigatório por **cardinalidade de colaborador** (nunca contagem simples) | `magnata_os/classificacao/holerite_obrigatorio_prestacao.py` | `avaliar_obrigatoriedade_holerite`, `combinar_pacote_com_holerite` |
| Orquestração ponta-a-ponta (clientes → requisitos → inventário → readiness → pacote → faltantes) | `magnata_os/classificacao/ciclo_prestacao.py` | `executar_ciclo_prestacao`, `NecessidadeDocumentoPrestacao` |
| Exceção de cliente como configuração versionável (nunca `if` espalhado) | `competencia_esperada_prestacao.py` | `REFERENCIA_CLIENTE_SKY_TATUI` + política de competência efetiva (regra "base − 1 mês" para SKY) |
| Piloto SKY ponta-a-ponta com dados sintéticos equivalentes ao schema real | `test_piloto_sky_inventario_real_local_e2e.py` | 7 colaboradores esperados, 6 Holerites presentes, 1 ausente → pacote INCOMPLETO |
| Prova de composição (documentos → relacionamento → competência → vínculo → inventário → completude) | `test_ciclo_prestacao_multicliente_e2e.py`, `test_corredor_operacional_prestacao_e2e.py`, `test_corredor_prestacao_holerite_e2e.py`, `test_ciclo_piloto_prestacao_readonly_e2e.py` | — |

### ADRs que já documentam esta evolução (nenhum criado do zero por esta missão)

- `docs/decisoes/competencia-esperada-prestacao-v1.md` (2026-08-29)
- `docs/decisoes/corredor-prestacao-holerite-e2e-v1.md` (2026-08-29)
- `docs/decisoes/corredor-operacional-prestacao-v1.md` (2026-08-30, PR #96)
- `docs/decisoes/politica-operacional-prestacao-v1.md` (2026-08-30, PR #97)
- `docs/decisoes/cadastro-canonico-requisitos-prestacao-v1.md` (2026-08-30, PR #98)
- `docs/decisoes/piloto-real-prestacao-readonly-v1.md` (2026-08-30, PR #100)
- `docs/decisoes/inventario-real-prestacao-v1.md` (2026-08-30, PR #101)

## Gaps reais e já nomeados (não inventados nesta auditoria — extraídos de `inventario-real-prestacao-v1.md`, Fase 1)

| Família documental | Estado confirmado |
|---|---|
| Extrato Mensal | ✅ fonte existe (`FonteInventarioPrestacaoAirtableShadow`) |
| FGTS (Guia) | ✅ fonte existe (mesma classe acima) |
| DCTFWeb | ✅ fonte existe — broadcast por design (não é falha, é a regra) |
| Holerite | ✅ fonte existe, com resolução de vínculo e cardinalidade |
| **Folha/Cartão de Ponto** | ❌ **"NECESSITA EVIDÊNCIA — não construído"** (schema confirmado, adapter não) |
| **Certidões** | ❌ **"NECESSITA EVIDÊNCIA — não construído"** (schema confirmado, adapter não) |
| **Comprovantes de pagamento** (salário/assiduidade/VR/VA/horas extras/diárias) | ⚠️ reconhecimento textual já existe (`finalidade_comprovante_pagamento.py`); fonte read-only de presença por cliente/competência **não construída** |

Isto coincide exatamente com dois dos itens que esta missão pediu para
validar em SKY ("folhas/cartões de ponto" e "documentos fiscais/
tributários aplicáveis") — o segundo (DCTFWeb) já está coberto, o
primeiro (Ponto) é um gap conhecido e ainda aberto.

## Regras de prestação localizadas (fonte real, não memória do executor)

- Lista de documentos obrigatórios: `CADASTRO_REQUISITOS_PRESTACAO_V2`
  (`cadastro_requisitos_prestacao.py`) + overrides por cliente
  (`OverrideRequisitosPrestacao`, `politica_requisitos_prestacao.py`).
- Regra de competência efetiva do SKY (defasagem de 1 mês): política
  registrada em `competencia_esperada_prestacao.py`, documentada em
  `competencia-esperada-prestacao-v1.md` — **não** um `if` de nome de
  cliente espalhado pelo motor.
- Obrigatoriedade de Holerite por cardinalidade: `holerite_obrigatorio_prestacao.py`.

Nenhuma divergência entre fontes internas foi encontrada sobre esses
pontos — não há `REGRA_NAO_CONFIRMADA` a registrar nesta auditoria.

## Decisão

Apresentado este achado ao humano responsável, a decisão explícita foi:
**não implementar um motor novo nem fechar os gaps agora** — esta
missão se encerra como auditoria/consolidação por escrito. O fechamento
dos gaps de Folha de Ponto, Certidões e presença de comprovantes fica
registrado aqui como trabalho futuro possível, a ser aberto como missão
própria quando decidido — reaproveitando `FonteInventarioPrestacao` e
`FonteInventarioPrestacaoComposta`, sem novo motor/classificador/
orquestrador.

## Escopo desta entrega

- Nenhuma alteração de código.
- Nenhuma dependência nova de Airtable (nada foi tocado).
- Nenhum arquivo protegido (`app.py`) tocado.
- Nenhuma ação de produção, e-mail, WhatsApp ou Airtable executada.
- Único artefato: este documento.
