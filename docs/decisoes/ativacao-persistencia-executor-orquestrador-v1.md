# Ativação da persistência do executor do Orquestrador — V1 (sem transporte)

Registro de execução da fase autorizada pelo usuário em 2026-09-08, a
partir da "PROPOSTA DE AUTORIZAÇÃO DE FASE — ATIVAÇÃO DA PERSISTÊNCIA
DO EXECUTOR V1". Autorização recebida em mensagem distinta da proposta
(confirmação explícita, escopo exato, hard gates reafirmados — ver
`CLAUDE.md §6`).

## Objetivo autorizado

Conectar o `PlanoDisparo` já autorizado à persistência real em
`magnata_orquestrador.acoes_execucao_plano`, reutilizando
`RepositorioAcoesExecucaoPlanoPostgres` (claim/checkpoint/retry já
existentes, sem alteração de comportamento), sem ativar qualquer
transporte ou efeito externo.

## Gap identificado na auditoria

`materializar_prestacao_orquestrador_shadow` (e sua variante
`_postgres_shadow`) já encadeava intenção → gate → `PlanoDisparo`, mas
nunca chamava `RepositorioAcoesExecucaoPlanoPostgres.materializar_plano`.
Esse repositório já estava completo e testado isoladamente, mas nunca
exercitado a partir do caminho real de composição.

## O que foi implementado

Extensão **aditiva** de
`magnata_os/orquestrador/wiring_prestacao_orquestrador_postgres_shadow.py`
— nenhuma função existente foi alterada:

- `ResultadoPrestacaoOrquestradorPersistenteShadow` (dataclass): agrega
  o resultado da composição já existente + a tupla de
  `RegistroAcaoExecucaoPlano` persistidos.
- `materializar_prestacao_orquestrador_persistente_shadow`: reutiliza
  `materializar_prestacao_orquestrador_shadow` sem reescrevê-la, e
  encadeia `RepositorioAcoesExecucaoPlanoPostgres.materializar_plano`
  com o mesmo instante usado no resto da composição. Não chama
  `reivindicar_proxima`, `marcar_sucesso` nem `marcar_falha` — só
  materializa.
- `materializar_prestacao_orquestrador_persistente_postgres_shadow`:
  compõe os três adapters Postgres (`RepositorioExecucoesPostgres`,
  `RepositorioAutorizacoesGatePostgres`,
  `RepositorioAcoesExecucaoPlanoPostgres`) sobre a mesma conexão
  DB-API injetada.

Mantido o sufixo `_shadow` em todos os nomes novos, por decisão
explícita da autorização, enquanto não houver transporte.

## Testes

- `test_wiring_prestacao_orquestrador_persistente_shadow.py` (novo,
  unitário, conexão fake): persistência de uma ação por notificação;
  reaplicação idempotente do mesmo evento/autorização não duplica;
  nenhum dado sensível em claro nos registros persistidos; verificação
  estrutural por AST de que nenhuma chamada (`.reivindicar_proxima(`,
  `.marcar_sucesso(`, `.marcar_falha(`) nem import de transporte
  existe no módulo alterado.
- `test_wiring_prestacao_orquestrador_persistente_shadow_real.py`
  (novo, E2E contra Postgres real/efêmero, `MAGNATA_TEST_POSTGRES_REAL`):
  aplica 0001/0002/0003 se ausentes, materializa duas vezes o mesmo
  evento (idempotência real), confirma exatamente uma linha na tabela,
  e prova que a linha nascida do caminho real de composição é
  utilizável pelo `RepositorioAcoesExecucaoPlanoPostgres` já testado
  isoladamente (`reivindicar_proxima` → `marcar_sucesso`) — sem
  reimplementar essa lógica, só provando a integração ponta a ponta.
- `.github/workflows/magnata-testes.yml`: uma linha adicionada à lista
  de testes do job `postgres-real`, incluindo o novo `_real`.

## Evidência dos testes (rodados localmente, Postgres 16 efêmero)

- Testes unitários novos: 4/4 `PASSED`.
- Teste `_real` novo + os dois `_real` de Orquestrador já existentes,
  na ordem exata do CI: 5/5 `PASSED`.
- Suíte geral completa (sem `MAGNATA_TEST_POSTGRES_REAL`): **2204
  passed, 57 skipped, 0 failed** — sem regressão.
- Suíte geral completa (com `MAGNATA_TEST_POSTGRES_REAL`, banco
  efêmero recriado do zero, arquivos `_real` na mesma ordem do CI):
  **2258 passed, 2 skipped, 0 failed** — sem regressão.
- Achado adversarial durante a validação, **não relacionado a esta
  mudança**: rodar a suíte `_real` fora da ordem exata do CI (ex.:
  ordem alfabética simples, sem os arquivos explícitos na ordem do
  workflow) expõe uma fragilidade pré-existente em
  `test_wiring_prestacao_orquestrador_postgres_shadow_real.py::_aplicar_migrations`,
  que recria as migrations 0001/0002 sem checar `to_regclass` antes
  (diferente dos outros dois arquivos `_real` do Orquestrador, que já
  checam). Isso só se manifesta reordenando os testes; na ordem exata
  do workflow (a que roda de fato em CI, e que o novo teste também
  segue) não há colisão. Reportado como risco pré-existente, não
  corrigido nesta fase — corrigi-lo seria tocar um teste fora do
  escopo autorizado (`_aplicar_migrations` pertence a um arquivo que
  esta fase não deveria alterar).

## Confirmação de zero transporte

- `grep` no diff completo desta fase por `transporte_comunicacao`,
  `evolution`, `airtable`, `whatsapp`, `import requests`: nenhuma
  ocorrência de import ou chamada real — as únicas ocorrências da
  palavra são docstring (mencionando o que o módulo **não** faz) e o
  valor default pré-existente `canal_preferencial: str = 'WHATSAPP'`
  (uma string de preferência operacional, não uma chamada).
- Verificação estrutural por AST no teste unitário novo confirma
  ausência de chamada aos métodos de claim/finalização no módulo
  alterado.
- `app.py` sem diff (`git diff --stat -- app.py` vazio).

## O que NÃO foi feito, por desenho da autorização

- Nenhuma alteração em `transporte_comunicacao.py`.
- Nenhuma chamada real de `reivindicar_proxima`/`marcar_sucesso`/
  `marcar_falha` a partir de código de produção — só nos testes
  (unitário com fake, e `_real` provando a integração, ambos sem
  transporte).
- Nenhuma migration nova, nenhuma alteração da 0003.
- Nenhuma credencial, nenhum Render/deploy.
- Rotação/revogação de credencial expostas mantida como frente
  separada, por decisão explícita do usuário — não auditada nem
  tocada nesta fase.

## Próximo hard gate real para a etapa seguinte

Qualquer executor que de fato chame `reivindicar_proxima` +
`marcar_sucesso`/`marcar_falha` a partir de um caminho de produção
(mesmo sem transporte real, ex.: um laço de teste/dry-run) é uma nova
fase, com autorização própria — esta fase entrega só a persistência do
plano, não o consumo das ações persistidas. Ativar transporte real
(Evolution/WhatsApp) é uma fase distinta e maior, com seus próprios
hard gates, ainda mais distante.

## Rastreabilidade

- Arquivos alterados: `magnata_os/orquestrador/wiring_prestacao_orquestrador_postgres_shadow.py`,
  `.github/workflows/magnata-testes.yml`.
- Arquivos novos: `test_wiring_prestacao_orquestrador_persistente_shadow.py`,
  `test_wiring_prestacao_orquestrador_persistente_shadow_real.py`.
- Proposta original: registrada na conversa que precedeu esta decisão
  (não versionada separadamente — a autorização e a proposta ficam
  registradas aqui, no ponto de execução).
- Decisões anteriores da mesma cadeia: `docs/decisoes/prova-credencial-worker-rotacao-postgres-v1.md`,
  `docs/decisoes/aplicacao-migration-0003-acoes-execucao-plano-v1.md`.
