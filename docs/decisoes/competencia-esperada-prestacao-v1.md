# Fonte automática de competência esperada da Prestação de Contas

**Data:** 2026-08-29
**Branch:** `fix/competencia-esperada-prestacao`
**Status:** ✅ Implementado, testado (shadow), pronto para revisão

**Correção registrada em 2026-08-29 (mesma branch, missão corretiva):**
a auditoria original desta ADR descrevia a ausência de deslocamento
codificado como "nenhuma exceção real hoje" — formulação imprecisa,
corrigida abaixo.

**Ativação registrada em 2026-08-30 (branch
`fix/competencia-sky-relativa`, missão corretiva curta):** a referência
canônica do cliente SKY Tatuí foi confirmada por leitura somente-GET no
Airtable e a regra foi ATIVADA — ver "Exceção operacional — SKY Tatuí"
abaixo (não é mais "pendente").

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
- Nenhuma regra de deslocamento de competência POR CLIENTE estava
  CODIFICADA em nenhum lugar do repositório (código, ADR ou
  documentação) — nenhuma ocorrência de "cliente X usa mês Y" ou
  equivalente no momento desta auditoria. **Isso não significa que
  nenhuma exceção real existe** — uma correção posterior (ver seção
  "Exceção operacional — SKY Tatuí" abaixo) identificou e, em seguida,
  confirmou e ativou uma regra operacional real.
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
vazia por padrão para quem não tem exceção nenhuma — a exceção real do
SKY Tatuí (ver "Exceção operacional — SKY Tatuí" abaixo) já vem
composta em `POLITICA_COMPETENCIA_PRESTACAO_V1`. **Por que é
independente do documento:** o módulo
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

`DeslocamentoCompetenciaCliente(cliente, competencia=None, tipo_documental=None,
offset_meses=None)` — exatamente UM entre `competencia` (absoluta, forma
preservada por compatibilidade) e `offset_meses` (relativa, aplicada sobre
`ContextoCicloPrestacao.competencia_base` no momento da resolução,
nunca hardcoded como valor fixo). `tipo_documental=None` aplica o
deslocamento a qualquer tipo documental daquele cliente; um valor
explícito restringe a esse tipo só. `PoliticaCompetenciaPrestacao(version="1")`
(sem argumentos) continua com `deslocamentos=()` — o default seguro
para quem não tem exceção; a exceção real do SKY Tatuí vem pronta em
`POLITICA_COMPETENCIA_PRESTACAO_V1` (ver "Exceção operacional — SKY
Tatuí" abaixo), para quem compõe o corredor real reaproveitar sem
duplicar a regra.

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

## Exceção operacional — SKY Tatuí (ATIVADA em 2026-08-30)

**Referência canônica confirmada** por leitura somente-GET no Airtable
(base `appaCpIVj7Q97VhFy`, tabela Clientes `tbl0znyuCEzoCHtCV`, cliente
"EDIFICIO SKY TATUI"):

```
cliente_ref = recrqv5NvbC37WfSl
regra       = competência base − 1 mês (RELATIVA, não fixa)
```

Exportada em `magnata_os/classificacao/competencia_esperada_prestacao.py`
como `REFERENCIA_CLIENTE_SKY_TATUI` (a identidade é SEMPRE este record
id — nunca o nome livre "SKY Tatuí"/"Edifício Sky Tatuí", que só existe
em comentário para rastreabilidade humana) e `DESLOCAMENTO_SKY_TATUI`
(`offset_meses=-1`, nunca uma competência absoluta hardcoded — funciona
para qualquer competência base, inclusive virada de ano: base
JANEIRO/2027 → esperada DEZEMBRO/2026). Ambas compostas em
`POLITICA_COMPETENCIA_PRESTACAO_V1`, a política real pronta para quem
compuser o corredor reaproveitar — nenhuma duplicação da regra em mais
de um lugar.

**Histórico da auditoria de identidade** (branch anterior,
`fix/competencia-esperada-prestacao`): busca por "SKY"/"Tatuí" em todo
o repositório havia encontrado só `recSKY` em
`test_fila_envios_v2_23.py` — um ID sintético local a esse teste,
inventado para uma funcionalidade não relacionada (fila de envios
legada), nunca reaproveitado. A referência real acima veio de uma
consulta de leitura nova e específica ao Airtable, autorizada e
executada nesta correção — não do `recSKY` de teste.

**Suporte a deslocamento relativo** (`DeslocamentoCompetenciaCliente.
offset_meses`, `_aplicar_offset_meses`): menor ajuste ao mecanismo já
existente — a forma absoluta (`competencia: Tuple[int,int]`) foi
preservada por compatibilidade (nenhum uso real dela foi encontrado que
justificasse removê-la); as duas formas são mutuamente exclusivas em
cada `DeslocamentoCompetenciaCliente` (validado em `__post_init__`).
Aritmética pura de meses (nunca `datetime`/`calendar`), continua
coberta pelo mesmo teste estático que garante que o módulo nunca
importa relógio.

## Documentação relacionada

- `docs/decisoes/corredor-prestacao-holerite-e2e-v1.md` — corredor
  original (PR #90), agora com a competência esperada automatizada.
- `magnata_os/classificacao/politica_requisitos_prestacao.py` — padrão
  de política pura + exceções reaproveitado.
- `CLAUDE.md` §4 — separação de dimensões, princípio preservado
  (competência observada/esperada nunca fundidas num único campo).
