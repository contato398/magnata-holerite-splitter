# Fonte automática de competência esperada da Prestação de Contas

**Data:** 2026-08-29
**Branch:** `fix/competencia-esperada-prestacao`
**Status:** ✅ Implementado, testado (shadow), pronto para revisão

## Resumo executivo

O corredor Holerite → Readiness (PR #90) recebia a competência esperada
como um parâmetro solto `Optional[Tuple[int, int]]`, correto
arquiteturalmente mas ainda manual: alguém precisava informá-la a cada
execução. Este trabalho substitui esse parâmetro solto por uma
**política pura e versionada** (`PoliticaCompetenciaPrestacao`,
`magnata_os/classificacao/competencia_esperada_prestacao.py`) que
resolve a competência esperada automaticamente a partir de:

1. um **contexto de ciclo** (`ContextoCicloPrestacao.competencia_base`)
   — fornecido UMA VEZ por execução, nunca por documento;
2. **deslocamentos por cliente**, opcionalmente restritos a um tipo
   documental — mecanismo de exceção, vazio por padrão.

## Auditoria — fontes de competência já existentes

Buscados no repositório: `mes_cont_id`, `mes_referencia`, `periodo`,
`ciclo`, `fechamento`, `folha_mensal`, `previous_month`/`mes_anterior`,
em `app.py`, `scripts/`, `ConfiguracaoExecucao`, ADRs e testes.

**Achados:**

- `ConfiguracaoExecucao.ano`/`.mes` (Família B, `importacao_lote/
  contratos.py`) — competência esperada da execução, mas NUNCA
  instanciado em código de produção; só em testes. Não é uma fonte
  automática hoje, é só o formato do parâmetro.
- `scripts/prestacao_readiness_shadow_real.py --competencia` — mesmo
  padrão: parâmetro de execução explícito, obrigatório, fornecido uma
  vez por chamada do script. Nenhuma automação por trás; é a origem do
  padrão "parâmetro por execução" que este trabalho preserva e
  formaliza em `ContextoCicloPrestacao`.
- **`app.py` (legado) — achado crítico:** `mes_anterior_info()` calcula
  a competência default a partir de `datetime.now()` ("mês anterior");
  `buscar_mes_contabilidade_atual()` consulta uma tabela REAL do
  Airtable (`Mês - Contabilidade`) pelo mês corrente. Isso seria uma
  fonte automática genuína — MAS o próprio `app.py` (linha ~2021,
  comentário `"Competência manda"`) deixa a competência **extraída do
  próprio PDF do Holerite** SOBRESCREVER esse valor quando diverge.
  Isso é exatamente `esperada = observada` de forma indireta — a
  validação circular que esta missão proíbe. **Não foi reaproveitado.**
- Nenhuma regra de deslocamento de competência POR CLIENTE foi
  encontrada em nenhum lugar do repositório (código, ADR ou
  documentação) — nenhuma ocorrência de "cliente X usa mês Y" ou
  equivalente. **Não existe hoje nenhuma exceção real a preservar.**
- `avaliar_prestacao_shadow`/`avaliar_prestacao_readiness` — a própria
  assinatura (`cliente`, `competencia` como parâmetros de nível
  superior, separados) já pressupõe que competência pode ser avaliada
  por cliente individualmente — compatível com deslocamento por
  cliente sem qualquer alteração desses contratos.

## Fonte canônica escolhida

`PoliticaCompetenciaPrestacao` — mesmo padrão de
`PoliticaRequisitosPrestacao`/`OverrideRequisitosPrestacao`
(`politica_requisitos_prestacao.py`, já existente): política pura e
versionada, com uma lista de exceções (aqui, `DeslocamentoCompetenciaCliente`)
vazia por padrão. **Por que é independente do documento:** o módulo
inteiro (`competencia_esperada_prestacao.py`) nunca importa
`datetime`/`time`/`calendar` (garantido por teste estático AST) e nunca
recebe o texto do documento — só `ContextoCicloPrestacao` (fornecido de
fora) e `cliente`/`tipo_documental` (já resolvidos antes de chegar
aqui).

## Competência base

`ContextoCicloPrestacao.competencia_base: Tuple[int, int]` — fornecida
uma única vez por execução por quem orquestra o corredor (config
operacional, parâmetro do runner, ou o próprio ciclo de fechamento já
em uso hoje via `--competencia`). Este trabalho NÃO decide de onde essa
config virá em produção (script novo, variável de ambiente, tabela
"Mês - Contabilidade" lida via `LeitorAirtableSomenteLeitura` já
existente) — isso é bootstrap operacional, fora de escopo, mesmo
princípio já registrado em `composition-root-modulo01-v1.md`.

## Regras por cliente (deslocamento)

`DeslocamentoCompetenciaCliente(cliente, competencia, tipo_documental=None)`.
`tipo_documental=None` aplica a qualquer tipo documental daquele
cliente; um valor explícito restringe a esse tipo só. Lista vazia por
padrão — reflete o estado real hoje (nenhuma exceção comprovada).

## Precedência

1. deslocamento específico (`cliente` + `tipo_documental` exatos);
2. deslocamento geral do cliente (`tipo_documental=None`);
3. `ContextoCicloPrestacao.competencia_base`;
4. `None` quando nenhum contexto foi fornecido.

Determinística e auditável — `PoliticaCompetenciaPrestacao.__post_init__`
rejeita, na CONSTRUÇÃO (nunca em tempo de resolução), dois deslocamentos
para a mesma chave `(cliente, tipo_documental)` — uma política ambígua
nunca chega a existir para ser consultada.

## Ordem cliente × competência (ajuste na ponte)

Auditoria confirmou que, se a competência esperada pode depender do
cliente, o cliente precisa estar resolvido ANTES de perguntar "qual é a
competência esperada". `ponte_prestacao_holerite.
confirmar_holerite_para_inventario` foi reordenada:

1. exige competência OBSERVADA com valor único (`ENCONTRADA`);
2. resolve CLIENTE via `FonteVinculosPrestacao`, usando a competência
   **OBSERVADA** como referência temporal do vínculo (nunca a esperada,
   que ainda não existe neste ponto — é uma pergunta organizacional
   "a qual cliente este colaborador pertencia no período que o
   documento diz ser o dele", não uma validação de competência);
3. com o cliente já resolvido, obtém a competência ESPERADA via
   `PoliticaCompetenciaPrestacao.competencia_esperada_para`;
4. valida observada contra esperada (`validar_competencia`, sem
   alteração).

Cliente continua fora de CLASSIFICACAO/IDENTIFICACAO (nenhuma mudança
nesses gates) — a reordenação é inteira dentro da ponte.

## Ausência de contexto — nunca inventa

Quando `ContextoCicloPrestacao` é `None` e nenhum deslocamento se
aplica, `competencia_esperada_para` devolve `None` — a ponte para ali,
sem inventar. Nunca usa `datetime.now()`, nunca um "mês anterior"
genérico.

## Proibição de circularidade

A competência OBSERVADA nunca determina a ESPERADA — a esperada vem
sempre de `ContextoCicloPrestacao`/`PoliticaCompetenciaPrestacao`,
nunca do documento. A observada é usada em dois papéis DIFERENTES e
nunca confundidos: (a) referência temporal para resolver o vínculo
colaborador→cliente (papel organizacional); (b) o valor comparado
contra a esperada (papel de validação). Nenhum dos dois papéis deriva a
esperada a partir da observada.

## Documentação relacionada

- `docs/decisoes/corredor-prestacao-holerite-e2e-v1.md` — corredor
  original (PR #90), agora com a competência esperada automatizada.
- `magnata_os/classificacao/politica_requisitos_prestacao.py` — padrão
  de política pura + exceções reaproveitado.
- `CLAUDE.md` §4 — separação de dimensões, princípio preservado
  (competência observada/esperada nunca fundidas num único campo).
