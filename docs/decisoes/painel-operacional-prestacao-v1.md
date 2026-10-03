# Painel Operacional de Diagnóstico — Prestação de Contas, V1 (somente leitura)

## Objetivo

Dar visibilidade humana ao resultado de `diagnosticar_prestacao`
(`magnata_os/classificacao/composicao_ciclo_persistente_prestacao.py`)
sem depender de olhar log ou JSON cru — referência explícita do PR #195
("painel próprio como interface operacional futura", até aqui nunca
implementado).

## Estado encontrado antes desta mudança (registrado explicitamente)

`diagnosticar_prestacao` já existe, mesclada em `main`, e já produz
`DiagnosticoPrestacao` com `DiagnosticoCliente`/`DiagnosticoNecessidade`
e o rastro de localização (`ResultadoLocalizacao.como_evidencia()`).
A própria docstring de `DiagnosticoPrestacao.como_dict()` já dizia
"consumível pelo futuro painel" — o painel em si nunca existiu.
Nenhum outro código do repositório renderiza esse diagnóstico para
humano; o único consumidor encontrado
(`magnata_os/orquestrador/prestacao_cliente_competencia_v1.py`) só usa
o diagnóstico internamente, sem expor nada legível.

## Decisão arquitetural

- **Função pura de renderização, não uma rota Flask nova.** Módulo
  novo `magnata_os/classificacao/painel_diagnostico_prestacao.py`,
  função `renderizar_diagnostico_prestacao_markdown(diagnostico: dict)
  -> str`. Recebe exatamente o dict que `DiagnosticoPrestacao.
  como_dict()` já produz (o contrato que o próprio módulo de
  diagnóstico já documentava como destinado a um painel) e devolve
  Markdown legível — cabeçalho por cliente, tabela de necessidades por
  tipo documental/colaborador com situação, contagem de avaliados vs.
  elegíveis, seção de rastro de localização (decisão, motivo, cada
  fonte consultada com status) para toda necessidade que não seja
  `PRONTO`, e uma legenda com o significado de cada `SituacaoNecessidade`.
  `renderizar_diagnostico_prestacao_objeto(diagnostico)` é a
  conveniência para quem já tem o dataclass em mãos (chama
  `.como_dict()` e delega, sem lógica própria).
- **Por que uma função pura e não uma rota Flask agora**: `app.py` é
  legado protegido (`/CLAUDE.md` §7) e não pode ser tocado fora de uma
  branch dedicada a ele; não há hoje nenhum blueprint de módulo novo já
  registrado em produção para pendurar uma rota nele sem inventar esse
  mecanismo de registro como decisão paralela desta tarefa. Uma função
  pura de Markdown é reaproveitável por **qualquer** interface futura
  (rota GET, notebook, CLI, worker que grava artefato) sem acoplamento
  prévio a nenhuma delas — decisão que evita comprometer a forma da
  futura rota antes que ela seja, ela própria, uma tarefa aprovada.
- **CLI de leitura incluída nesta mesma mudança**
  (`scripts/painel_diagnostico_prestacao_cli.py`): lê um JSON no
  formato de `.como_dict()` (de arquivo ou stdin) e imprime o Markdown
  renderizado — nenhuma chamada a `diagnosticar_prestacao` dentro do
  script, porque montar o `ContextoComposicaoPrestacao` completo (
  inventário, fontes de localização, repositórios) é uma decisão de
  wiring de infraestrutura própria, fora do escopo de um painel de
  leitura. Um caminho futuro que já produza esse JSON (execução
  agendada, endpoint, notebook operacional) usa a mesma CLI ou a mesma
  função de renderização sem duplicar formatação.
- **Zero escrita, zero ação, zero botão.** Nenhuma linha deste
  incremento cria Ordem, chama corredor de aquisição, grava
  repositório, dispara distribuição ou toca Airtable/Postgres/S3 real
  — só leitura de um dict já calculado e formatação de texto.
- **Legenda mantida sincronizada por teste, não por acoplamento de
  import.** O painel opera sobre o dict (contrato deliberadamente
  desacoplado do dataclass — ver acima), então a legenda de
  `SituacaoNecessidade` é texto estático no módulo do painel; o teste
  `test_legenda_cobre_todas_as_situacoes_do_enum_real` importa o Enum
  real e garante que a legenda nunca fica desatualizada em relação a
  ele, sem forçar o módulo do painel a depender do dataclass para
  funcionar a partir de um JSON puro.

## O que NÃO foi feito nesta V1 (gate remanescente, fora de escopo)

- **Nenhuma rota Flask/HTTP nova.** Se o painel precisar virar página
  web, isso é uma decisão de produto (autenticação, quem acessa, onde
  fica o blueprint) fora do escopo desta tarefa — a função de
  renderização já está pronta para ser chamada por uma rota GET futura
  sem qualquer alteração.
- **Nenhum wiring real de `diagnosticar_prestacao` no script/CLI** —
  quem quiser rodar o diagnóstico de verdade (com inventário e fontes
  de localização reais) continua chamando `diagnosticar_prestacao`
  onde já é chamada hoje e passando o `.como_dict()` resultante (ou o
  próprio objeto, via `renderizar_diagnostico_prestacao_objeto`) para
  o renderizador.
- Nenhuma alteração em `app.py`, migration, schema, Airtable,
  Postgres, worker, Render, produção, env/secrets.

## Testes (`tests/test_painel_diagnostico_prestacao.py`)

- Cobertura de schema: legenda e marcadores cobrem exatamente os
  valores do Enum `SituacaoNecessidade` real (anti-drift).
- Estados principais renderizados corretamente com dados sintéticos:
  diagnóstico vazio, `PRONTO` sem necessidade de rastro, `CONFLITO`
  bloqueando a Ordem mesmo com documentos elegíveis, `AUSENTE` com
  rastro de localização detalhado (decisão, motivo, fontes
  consultadas), `EM_REVISAO`/`ERRO_DE_LEITURA`/`FONTE_INDISPONIVEL`/
  `SEM_FONTE`/`ENCONTRADO_NAO_ELEGIVEL`, necessidade a nível de cliente
  sem colaborador, resumo geral (contagem de prontos/bloqueados).
- Confirma que nenhum termo de dado pessoal (`.pdf`, `.jpg`, `CPF`,
  `@`) aparece no relatório quando não está no dado sintético de
  entrada — o painel não injeta nada além do que já veio no dict.
- CLI testada via subprocesso real: leitura por arquivo e por stdin.
- Todos os dados de teste são sintéticos (`cliente-sintetico-001`,
  `colaborador-sintetico-001`, `doc-001`) — nenhum CPF, nome ou
  documento real.

## Como usar/visualizar

```python
from magnata_os.classificacao.composicao_ciclo_persistente_prestacao import diagnosticar_prestacao
from magnata_os.classificacao.painel_diagnostico_prestacao import renderizar_diagnostico_prestacao_objeto

diagnostico = diagnosticar_prestacao(contexto)  # mesmo contexto já usado pelo ciclo real
print(renderizar_diagnostico_prestacao_objeto(diagnostico))
```

Ou, a partir de um JSON já salvo (`diagnostico.como_dict()` gravado em
arquivo por quem já chama `diagnosticar_prestacao` hoje):

```bash
python scripts/painel_diagnostico_prestacao_cli.py caminho/diagnostico.json
# ou
cat diagnostico.json | python scripts/painel_diagnostico_prestacao_cli.py
```

## Riscos e pendências declarados

- Sem rota HTTP, o painel exige que alguém já tenha o JSON do
  diagnóstico em mãos (rodando `diagnosticar_prestacao` em um shell,
  notebook ou script já existente) — não é ainda um painel "sempre
  disponível" sem ação manual. Uma rota GET somente-leitura é o
  próximo incremento natural, fora de escopo aqui por exigir decisão
  de onde registrar o blueprint sem tocar `app.py`.
- A legenda de situações é texto estático (sincronizada por teste, não
  por import) — se `SituacaoNecessidade` ganhar um novo valor, o teste
  `test_legenda_cobre_todas_as_situacoes_do_enum_real` falha e força
  atualização da legenda; isso é o comportamento desejado (fail-closed
  em vez de um valor silenciosamente sem legenda), mas exige lembrar de
  rodar a suíte ao alterar o Enum.

## Arquivos

Criados: `magnata_os/classificacao/painel_diagnostico_prestacao.py`,
`scripts/painel_diagnostico_prestacao_cli.py`,
`tests/test_painel_diagnostico_prestacao.py`, este documento.

Não tocados: `app.py`, todas as migrations, `frontend/assets/brand/`,
`composicao_ciclo_persistente_prestacao.py`, `central/localizacao.py`,
qualquer adapter de Airtable/Postgres/S3.
