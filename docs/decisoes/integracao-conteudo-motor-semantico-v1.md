# Integração real do conteúdo documental ao motor semântico + automação contínua da esteira V1

**Data:** 2026-08-30
**Branch:** `fix/integracao-conteudo-motor-semantico-v1`
**Base:** `main @ 320982db2b375cf42259c6024eb13a350155e72b` (PR #103 mesclado)
**Status:** ✅ Implementado, testado — corredor CLASSIFICACAO real conectado; encadeamento
automático além da CLASSIFICACAO (inventário/readiness/pacote lógico) é a maior lacuna real
restante, declarada abaixo, não escondida.

## Fase 0 — Merge do PR #103

HEAD citado (`07b4e399039ec4d692f41d2c7e808e9e22ef8bc4`) confirmado idêntico ao HEAD real, base
`main`, CI verde, governança verde, sem review bloqueante. Mesclado. Merge commit:
`320982db2b375cf42259c6024eb13a350155e72b`.

## Fase 1 — Auditoria do corredor existente (antes de criar qualquer coisa nova)

Achado central: **já existia uma ponte bytes→texto→classificação real** —
`roteamento_documental.py` (`extrair_texto_seguro` + `classificar_documento`) — e já existia uma
**política real de avanço de esteira** para o resultado dessa ponte — `politica_classificacao.py`
(`decidir_transicao_classificacao`), consumida por
`ServicoAvancoEsteira.aplicar_resultado_classificacao`. Nenhuma das duas foi refeita.

O gap genuíno: as duas só conhecem o classificador legado de 17 regras
(`EstadoClassificacao`, 4 estados) — nunca os produtores de evidência mais novos (fiscal, ponto,
temporal, rótulo alternativo de Extrato, finalidade de pagamento) nem o motor geral de 8 estados
(`EstadoResolucaoDimensao`/`resolver_tipo_documental`) construído nas missões anteriores. A
reconciliação origem×conteúdo e a competência esperada×observada (`resolucao_competencia_de_
validacao`, `extrair_competencia_de_texto`/`validar_competencia` em
`importacao_lote/dominio.py`) também já existiam como peças isoladas, mas nenhuma delas estava
conectada a uma decisão real de transição de etapa.

## O que foi construído

- **`ponte_conteudo_motor_semantico.py`** (novo): `resolver_tipo_documental_de_texto`/
  `resolver_tipo_documental_de_pdf` — agrega TODOS os produtores de evidência já existentes
  (textual/17-regras, fiscal, ponto, temporal, rótulo alternativo de Extrato, finalidade de
  pagamento) para o MESMO `resolver_tipo_documental`, produzindo uma `ResolucaoDimensao`
  (TIPO_DOCUMENTAL) real a partir de texto. Reaproveita `extrair_texto_seguro`
  (`roteamento_documental.py`) para o caminho por PDF — nunca uma segunda extração.
- **`politica_classificacao_semantica.py`** (novo, `magnata_os/documental/modulo01/`):
  `decidir_transicao_classificacao_semantica(texto, tipo_origem=None, competencia_esperada=None)`
  → o MESMO contrato `DecisaoTransicaoClassificacao` já consumido por
  `ServicoAvancoEsteira.aplicar_resultado_classificacao` — zero mudança nessa mecânica. Cobre:
  texto ausente (bloqueio técnico distinto de "desconhecido", Fase 3), RESOLVIDA sem/com
  reconciliação (auto-avanço ou CONFLITO), CONFLITO/AMBIGUA do próprio motor, NAO_ENCONTRADA
  (DESCONHECIDO, soft-flag `EM_REVISAO`), e competência esperada×observada (reaproveita
  `extrair_competencia_de_texto`/`validar_competencia`/`resolucao_competencia_de_validacao`
  já existentes — nunca uma segunda extração/validação).
- **`reconciliacao_origem_conteudo.py`** (refatorado, sem mudança de comportamento externo):
  extraído `reconciliar_origem_com_tipo_resolvido(tipo_origem, tipo_resolvido: Optional[str])` e
  `tipo_resolvido_da_dimensao(resolucao: ResolucaoDimensao)` — núcleos puros reaproveitados pela
  nova política, que só tem uma `ResolucaoDimensao` isolada em mãos (não um
  `ResultadoResolucaoSemantico` completo). `reconciliar_origem_com_resolucao_semantica` continua
  existindo, agora delegando a esses núcleos — os 7 testes existentes continuam passando sem
  alteração.
- **`automacao_por_confianca.py`** (refatorado, sem mudança de comportamento externo): extraído
  `decidir_por_estado_dimensao(estado: EstadoResolucaoDimensao)` de dentro de
  `decidir_proxima_acao` — mesma razão (reuso por quem só tem uma dimensão isolada). Os 10 testes
  existentes continuam passando sem alteração.
- **Teste arquitetural** (`test_magnata_os_classificacao_arquitetura_sem_dependencia_airtable.py`,
  novo): confirma via AST que nenhum dos 4 módulos do corredor (`ponte_conteudo_motor_semantico`,
  `reconciliacao_origem_conteudo`, `automacao_por_confianca`, `politica_classificacao_semantica`)
  importa Airtable, e que as assinaturas públicas só aceitam texto/strings genéricas — nunca um
  tipo de dado específico de uma fonte.
- **Corpus E2E heterogêneo** (`test_magnata_os_documental_modulo01_corpus_heterogeneo_
  classificacao_semantica.py`, novo, 10 casos parametrizados + teste de métricas): os 10 casos
  especificados pela missão, todos decididos pela MESMA função de política — nunca um caminho
  especial por caso.

## Dependência de Airtable — antes/depois

| | Antes | Depois |
|---|---|---|
| Ponte conteúdo→motor | Não existia uma ponte multi-evidência (só a de 17 regras) | `ponte_conteudo_motor_semantico.py` — zero import de Airtable (confirmado por teste AST) |
| Política de esteira | `politica_classificacao.py` só entendia o classificador de 17 regras | `politica_classificacao_semantica.py` — mesmo contrato, motor geral; zero import de Airtable |
| Reconciliação/automação | Já não dependiam de Airtable (missão anterior) | Continuam sem depender — núcleos extraídos tornam isso mais explícito, não menos |
| Substituição de fonte | `tipo_origem`/`texto` já eram parâmetros genéricos | Confirmado por teste de assinatura (`inspect.signature`) — Gmail/armazenamento/upload manual usam os MESMOS parâmetros, zero mudança de código |

## Corpus E2E — 10 casos (métricas Fase 20)

Todos os 10 casos da missão, decididos por `decidir_transicao_classificacao_semantica`:

| # | Caso | Resultado |
|---|---|---|
| 1 | Holerite sem a palavra "Holerite" (Recibo de Pagamento + Total de Vencimentos) | CONCLUIDO (auto-avança) |
| 2 | Folha de Ponto sem título, por estrutura | CONCLUIDO (auto-avança) |
| 3 | "Resumo da Folha" → Extrato | CONCLUIDO (auto-avança) |
| 4 | Origem "Holerite" × conteúdo FGTS | BLOQUEADO — `CLASSIFICACAO_ORIGEM_CONTEUDO_DIVERGENTES` |
| 5 | Guia DCTFWeb/DARF, origem neutra | CONCLUIDO (auto-avança) |
| 6 | Comprovante bancário, finalidade Salário | CONCLUIDO (auto-avança) |
| 7 | Comprovante ambíguo (Guia genérica × FGTS empatados) | BLOQUEADO — `CLASSIFICACAO_AMBIGUA_SEMANTICA` |
| 8 | PDF sem texto extraível | BLOQUEADO — `CLASSIFICACAO_TEXTO_NAO_EXTRAIVEL` (nunca confundido com desconhecido) |
| 9 | Documento totalmente desconhecido | EM_REVISAO (soft-flag, `deve_bloquear=False`) |
| 10 | Resolvido, mas competência observada diverge da esperada | BLOQUEADO — `CLASSIFICACAO_COMPETENCIA_DIVERGENTE` |

**Métricas do corpus**: TOTAL=10; AUTO_AVANCARAM=5 (casos 1,2,3,5,6); REVISAO=1 (caso 9);
BLOQUEADOS=4 (casos 4,7,8,10); PERCENTUAL_AUTOMACAO=50%.

Distinção Fase 20 (AUTO_RESOLVIDO ≠ AUTO_AVANCO_COMPLETO): as métricas acima medem só até a
decisão de transição da etapa CLASSIFICACAO — "auto-avança" aqui significa "sai da CLASSIFICACAO
sem bloqueio nem revisão", nunca "chegou à distribuição". Ver "Maior lacuna real restante" abaixo.

## Achado real registrado (nunca escondido): CONFLITO por sinais FORTES é hoje inalcançável via
## texto real com os produtores existentes

`resolver_tipo_documental` define CONFLITO como 2+ candidatos empatados em força FORTE. O
classificador textual legado (`classificar_documento`) só emite 1 hipótese vencedora por chamada
(nunca duas FORTE simultâneas), e nenhum outro produtor hoje agregado pela ponte emite evidência
FORTE isolada — o máximo alcançável por qualquer produtor novo é MODERADA (exceto o vencedor único
do classificador legado). Isso significa que, com o conjunto de produtores de HOJE, o branch de
CONFLITO da nova política (`CODIGO_BLOQUEIO_CONFLITO_TIPO`) está implementado e testado
(via monkeypatch isolando a resposta do resolvedor), mas não é alcançável por nenhum texto real
ainda — só ficará alcançável quando um produtor futuro também puder emitir FORTE. Não é um defeito
desta missão: o branch existe corretamente para quando isso acontecer, e o teste que o cobre
documenta essa limitação explicitamente, em vez de fabricar um texto artificial que não reflete
comportamento real algum.

## Maior lacuna real restante (Fase 7/10, declarada — próxima macro-missão)

Esta missão prova e conecta o corredor até a decisão de transição da etapa CLASSIFICACAO. A
esteira real (`servico_avanco_esteira.py`) ainda não tem nenhuma política de avanço automático
implementada para as etapas SEPARACAO/IDENTIFICACAO/VALIDACAO/MONTAGEM_PACOTE em diante
(`_DESCRICAO_PROXIMA_ACAO` documenta cada uma como "implementação em fase futura") — encadear um
documento RESOLVIDA+sem-conflito automaticamente até inventário/readiness/necessidades/pacote
lógico (Fase 7/19 da missão) exigiria: (a) decidir, por tipo documental já resolvido, um perfil de
aplicabilidade das outras 5 dimensões (CLIENTE/COMPETENCIA/COLABORADOR/UNIDADE_POSTO/VINCULO) —
hoje só existe fixo por caso de teste, nunca uma tabela tipo→perfil real; (b) uma política de
avanço automático real para SEPARACAO/IDENTIFICACAO/VALIDACAO em diante, que não existe ainda.
Implementar isso corretamente, por família (Fase 10: Holerite→colaborador→vínculo→cliente(s),
Extrato→cliente/competência, DCTF→broadcast, Comprovantes→finalidade+granularidade), é a próxima
macro-missão natural — não fabricado aqui como "concluído" para parecer mais completo do que é.

## Validação PLANO_VALIDACAO_LIVE_CONTEUDO (Fase 22)

Nenhuma leitura live de conteúdo/anexo real foi executada nesta missão (nem Airtable, nem
Gmail, nem armazenamento). Plano para quando estiver autorizado:

- **SISTEMA**: Airtable (tabelas de Holerites/Extratos/Guias já auditadas em missões anteriores).
- **FONTE**: anexos reais já vinculados a registros existentes (1 por tabela, já confirmados
  existentes na auditoria read-only anterior).
- **CLIENTE**: SKY Tatuí (`recrqv5NvbC37WfSl` — já validado em missão anterior).
- **COMPETÊNCIA**: base−1 mês (política já confirmada para SKY).
- **QUANTIDADE MÁXIMA**: 1 documento por família (Holerite, Extrato, Guia) — 3 no total.
- **TIPOS DE DOCUMENTOS**: Holerite, Extrato da Folha de Pagamento, Guia (FGTS ou DCTFWeb/DARF).
- **CAMPOS**: só o campo de anexo (binário) + o `tipo_origem`/nome de tabela já usados em leitura
  read-only anterior — nenhum campo de CPF/nome de colaborador é lido além do necessário para
  granularidade (e nunca logado).
- **DOWNLOADS**: 1 download por documento, direto para memória — nunca persistido em disco fora
  do fluxo de teste, nunca commitado.
- **LEITURA**: `extrair_texto_pdf` (mesma extração já usada em produção) + a nova ponte
  `resolver_tipo_documental_de_pdf`.
- **ESCRITAS**: ZERO — nenhuma escrita em nenhum sistema externo.
- **PII**: nenhum CPF/nome real logado; só `documento_id`/`tipo`/`estado`/`correlation_id`
  sanitizados.
- **STOP CRITERIA**: qualquer resultado inesperado (erro técnico não catalogado, CONFLITO em
  documento que deveria ser trivial, ou qualquer sinal de dado real vazando em log) interrompe
  imediatamente e é reportado antes de qualquer novo download.

`READY_FOR_LIVE_CONTENT_VALIDATION = TRUE` — o corredor técnico está pronto (ponte + política +
reconciliação + competência testados localmente); a leitura live em si não foi executada nesta
missão, por instrução explícita (Fase 22) — fica represada para confirmação humana explícita e
distinta antes do primeiro acesso real, conforme CLAUDE.md §6(e).
