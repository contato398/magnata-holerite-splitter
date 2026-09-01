# Entrada Operacional + Postgres Próprio — V1

Documento de decisão da missão "ENTRADA OPERACIONAL + POSTGRES PRÓPRIO
V1". Baseline: `main @ c91028ceb0bb5dab9b491a50d30dbabe3b3c5905` (PR
#116 mergeado). Branch: `fix/entrada-alocacao-postgres-v1`.

Regra pétrea reafirmada: Airtable continua em uso durante a transição,
mas toda evolução nova reduz — nunca aumenta — a dependência estrutural
dele.

## FASE 0 — Preflight

- `main @ c91028ceb0bb5dab9b491a50d30dbabe3b3c5905` confirmado.
- PR #116 mergeado (`gh pr view 116` → `MERGED`).
- Worktree limpa.
- `confirmacao.py`, `comparacao_airtable.py`, adapters SQLite/Postgres,
  migration `0001_criar_vinculo_trabalhista_e_alocacao.sql` — todos já
  existentes, auditados, reaproveitados.
- Infra/deploy: `render.yaml` e `Procfile` auditados (ver FASE 4).
- Variáveis de ambiente: padrão já estabelecido é `DATABASE_URL`
  (única), lido por `magnata_os/documental/modulo01/adapters/conexao.py`
  — nunca uma variável nova.
- Conexão SQL já prevista: `conexao.py` (Postgres, DB-API 2.0,
  sanitiza credencial em erro) + `magnata_os/orquestrador/
  fabrica_repositorio_execucoes.py` (fábrica explícita, sem fallback
  silencioso) — ambos auditados e reaproveitados nesta missão.

## FASE 1 — Arqueologia da superfície humana

Auditado: as 38 rotas de `app.py` (nenhuma auth), ausência de CLI
administrativa em `magnata_os/`, e — achado novo desta missão — os 3
Flask Blueprints já existentes fora de `app.py`
(`src/ingestao_secullum.py::ingestao_bp`,
`src/services/secullum_ponto.py::secullum_bp`,
`src/sync_new_employees.py::sync_bp`), todos registrados em `app.py`
com exatamente 2 linhas cada (`from ... import xxx_bp` +
`app.register_blueprint(xxx_bp)`) — nenhuma lógica de negócio in-line
em `app.py` para eles. Também achado: `magnata_os/documental/modulo01/
api/` já é uma camada de handlers framework-agnóstica (Perfil/Sujeito/
exigir_perfil, contratos, handlers) construída numa fase anterior e
**deliberadamente nunca wireada a uma rota HTTP real** — mesmo gate que
esta missão encontra de novo, independentemente, para alocação.

```text
SUPERFICIE_REUTILIZAVEL=Padrão de Blueprint isolado (2 linhas em app.py para registrar) -- ja usado 3x fora de app.py; NENHUMA tela/form/CLI administrativa reutilizavel para colaborador<->posto especificamente
AUTENTICACAO_EXISTENTE=Nenhuma -- app.py nao tem login_required, SECRET_KEY de sessao, Basic Auth nem qualquer verificacao de identidade de ENTRADA (so Bearer tokens de SAIDA para Airtable/Resend). modulo01/api/autorizacao.py ja documenta o MESMO gate, sem resolve-lo, desde uma missao anterior
PONTO_MINIMO_DE_WIRING=Um Blueprint Flask novo, registrado com o mesmo padrao de 2 linhas em app.py -- NAO implementado nesta missao (ver FASE 6, gate de autenticacao)
APP_PY_PRECISA_SER_MODIFICADO=Sim, no futuro -- só 2 linhas (import + register_blueprint), quando a autenticacao real existir; NAO modificado nesta missao
NOVO_SERVICO_SEPARADO_NECESSARIO=Nao -- nenhuma aplicacao Flask paralela foi criada nem é necessária; o padrão de Blueprint dentro do MESMO processo app.py já resolve isso quando o gate de autenticação for fechado
```

## FASE 2/3 — Desenho da tela mínima + pré-visualização

`magnata_os/documental/alocacao/preview_confirmacao.py` (novo, puro):
`PreviewConfirmacaoAlocacao` com exatamente os 8 campos pedidos
(Colaborador, Ação, De, Para, Data efetiva, Estado atual Magnata OS,
Snapshot atual Airtable, Consequência temporal) + `montar_preview`
(nunca escreve nada). **Achado de auto-revisão, corrigido nesta
rodada:** a primeira versão lia "estado atual" na data_efetiva da
solicitação pendente (podendo ser passada ou futura) em vez de agora —
corrigido para um parâmetro `hoje` explícito (`date.today()` por
padrão, injetável para teste) — "estado atual" significa **agora**,
nunca a data da mudança pendente. Isso não fere "nunca inferir
data_efetiva automaticamente": `hoje` é só o ponto de leitura de uma
consulta read-only, `data_efetiva` (o fato confirmado) continua 100%
humano, intocado.

Contrato de entrada continua sendo `SolicitacaoConfirmacaoAlocacao`
(`confirmacao.py`, já existente) — nenhum contrato paralelo novo. O
operador nunca digita IDs técnicos NO DESENHO (a borda resolveria
nome→id via `ResolverIdentidadeAlocacaoAirtableShadow`, já existente) —
mas a UI real que faria essa tradução segue fora do escopo (gate de
autenticação, FASE 6).

## FASE 4 — Postgres próprio

**Achado central: a decisão já existe, documentada, e não foi
tomada nesta missão** — `render.yaml` já declara um banco
`databases: magnata-os-db` (Postgres 16, gerenciado no Render, MESMO
ambiente dos serviços `web`/`worker` já existentes), com `DATABASE_URL`
já wireada via `fromDatabase` a ambos os serviços (bloco declarativo,
nunca aplicado — nenhum Blueprint Render rodado). O runbook
`docs/magnata-os/MAGNATA_OS_HANDOFF_ATIVACAO_JULHO2026.md` §5 já
detalha o passo a passo de provisionamento deste MESMO banco para o
Módulo 01 (`documentos`, `eventos_documentais`, etc. — migrations
`0001`-`0009`), incluindo a decisão explícita de **não** injetar
`DATABASE_URL` nos serviços Render "nesta fase" (evitar redeploy fora
do escopo autorizado) e de usar `conexao.abrir_conexao(database_url=...)`
diretamente numa sessão de execução segura, quando ativado.

**Esta missão reafirma essa mesma decisão para `alocacao`/
`vinculo_trabalhista`, em vez de propor um banco separado** — exatamente
o erro que a regra pétrea pede para evitar. `alocacao` passa a ser mais
um schema no MESMO `magnata-os-db`, migrado com sua própria migration
(`0001_criar_vinculo_trabalhista_e_alocacao.sql`, já validada contra
Postgres real em CI), nunca um banco à parte.

```text
POSTGRES_RECOMENDADO=magnata-os-db (Render, ja declarado em render.yaml) -- reaproveitado, nao um banco novo
MOTIVO=Decisao arquitetural ja em vigor (render.yaml + runbook de ativacao ja existente para modulo01); mesma DATABASE_URL/conexao.py ja usados por outro modulo; capaz de crescer progressivamente para servir outros modulos do Magnata OS (exigencia explicita desta missao); nenhuma vantagem real identificada em separar um banco so para alocacao (so custo/superficie operacional a mais)
CUSTO_APROXIMADO_SE_IDENTIFICAVEL=Nao identificavel com seguranca nesta sessao -- render.yaml usa plan:free só como placeholder (explicitamente marcado como NAO recomendação de producao, pois o tier free expira); a escolha do plano pago real é decisão financeira pendente, já registrada como tal no próprio render.yaml e no runbook (gate financeiro real, CLAUDE.md §6-b)
CONEXAO_PROPOSTA=Mesma DATABASE_URL ja wireada a web+worker (fromDatabase) + magnata_os/documental/modulo01/adapters/conexao.py::abrir_conexao/ler_database_url (reaproveitado nesta missao via fabrica_repositorio_alocacao.py, nunca reimplementado)
BACKUP=Depende do plano Render (planos pagos incluem PITR; free nao tem backup duravel) -- mesmo gate financeiro acima
MIGRATION_PATH=magnata_os/documental/alocacao/migrations/0001_criar_vinculo_trabalhista_e_alocacao.sql ja existe e ja foi validada contra Postgres real (job postgres-real de CI); falta so aplica-la ao banco real quando provisionado, como mais uma migration na mesma sequencia do runbook existente (nunca editar migration ja aplicada)
VARIAVEIS_DE_AMBIENTE_NECESSARIAS=So DATABASE_URL (ja declarada no render.yaml para os 2 servicos) -- nenhuma variavel nova
IMPACTO_RENDER=Nenhum nesta missao -- render.yaml ja preparado (bloco databases: declarativo, nao aplicado). Ativacao futura (fora desta missao) exige: 1) provisionar o banco no painel/Blueprint Render, 2) aplicar a migration da alocacao contra ele, 3) so entao decidir SE/QUANDO injetar DATABASE_URL nos servicos -- o runbook ja registra que isso NAO deve acontecer "nesta fase" para modulo01; mesma cautela se estende a alocacao
```

## FASE 5 — Configuração independente

`magnata_os/documental/alocacao/fabrica_repositorio_alocacao.py`
(novo) — `BackendAlocacao` (`SQLITE`/`POSTGRES`, só 2 valores — Airtable
nunca é um valor aceito, garantido pelo próprio tipo, não por
convenção) + `construir_repositorio_alocacao`, mesma disciplina de
`fabrica_repositorio_execucoes.py` (nenhum fallback silencioso).
Reaproveita `conexao.abrir_conexao`/`ler_database_url` para o backend
POSTGRES — nunca reimplementado.

**Decisão registrada:** isso cria uma dependência de import entre
`alocacao` e `modulo01` (exceção deliberada à regra geral de módulos
desacoplados) — `conexao.py` não tem nenhuma lógica específica de
Módulo 01, e duplicar a sanitização de credencial em 2 lugares seria um
risco de segurança maior do que o acoplamento. Ver docstring do módulo
para o raciocínio completo.

Nenhum fallback para Airtable em nenhum caminho — testado
estruturalmente (`BackendAlocacao('AIRTABLE')` levanta `ValueError`) e
comportamentalmente (falha de conexão Postgres propaga
`FalhaConexaoBanco`, nunca tenta Airtable).

## FASE 6 — Autorização e segurança da tela

**GATE real, reportado, não contornado.** Auditoria confirma: este
projeto não tem, hoje, nenhum mecanismo de autenticação administrativa
(`app.py` sem `login_required`/sessão/Basic Auth; Bearer tokens só de
saída para Airtable/Resend). `magnata_os/documental/modulo01/api/
autorizacao.py` já documentava o mesmo gate numa fase anterior, sem
resolvê-lo.

Construído: `magnata_os/documental/alocacao/autorizacao.py` (cópia
local deliberada do mesmo desenho — `Perfil`/`Sujeito`/`exigir_perfil`
— nunca importada de `modulo01` para preservar desacoplamento entre
módulos) + `magnata_os/documental/alocacao/api/handlers.py`
(framework-agnóstico, `exigir_perfil` sempre como a PRIMEIRA linha,
antes de qualquer acesso a `repo`/`resolver` — comprovado por teste
com espião). Pré-visualização exige `GESTOR` ou `OPERACIONAL`;
confirmação (escrita real, altera histórico canônico) exige só
`GESTOR`.

**Não implementado, e não deve ser, até o gate ser fechado:** nenhum
Blueprint Flask, nenhuma rota HTTP, nenhuma alteração em `app.py`.
Registrar uma rota real sem autenticação real por trás permitiria
qualquer chamador se autodeclarar `Sujeito(perfil=Perfil.GESTOR)` — pior
do que não ter rota nenhuma. `Sujeito` só pode ser construído, de
verdade, quando uma sessão/token validado existir — decisão fora do
escopo desta missão.

## FASE 7 — Auditoria da operação

**GATE real, reportado, não contornado.** Auditado: `eventos_documentais`
(Módulo 01) é o único log append-only genérico do repositório, mas
tem FK obrigatória para `documentos` — não reutilizável para
colaborador/posto sem uma migration nova. As tabelas `alocacao`/
`vinculo_trabalhista` não têm NENHUMA coluna de trilha (nem sequer
`origem_evidencia`/`origem_confirmacao`, que já é validado em
`eventos.py`/`confirmacao.py` mas nunca persistido — achado real desta
auditoria, pré-existente a esta missão, não introduzido por ela) —
muito menos identidade do operador, quando confirmou, ou resultado/erro.

Persistir "quem confirmou" (FASE 7 pede explicitamente essa trilha)
exigiria schema novo — migration em `alocacao`/`vinculo_trabalhista`
(nova coluna) ou uma tabela de auditoria própria. Isso é
`migration/schema relevante`, gate humano permanente (CLAUDE.md
§12-I), e esta missão **para aqui, sem criar a migration**, em vez de
decidir sozinha o formato dessa trilha.

## FASE 8 — Implementação permitida nesta missão

Implementado: view-model/DTO da tela (`PreviewConfirmacaoAlocacao`),
serviço de pré-visualização (`preview_confirmacao.py`), fábrica de
repositório (`fabrica_repositorio_alocacao.py`), camada de autorização
(`autorizacao.py`) + handlers framework-agnósticos (`api/handlers.py`),
testes, este ADR. `app.py` não foi tocado. Nenhum Blueprint Flask foi
criado (decisão explícita — ver FASE 6: um Blueprint só faria sentido
já registrável, e registrá-lo sem autenticação real seria pior do que
não tê-lo).

## FASE 9 — Testes adversariais

`test_magnata_os_documental_alocacao_entrada_operacional_v1.py` (22
testes) cobre: operador sem data (herdado de `confirmacao.py`,
reconfirmado via handler); colaborador/posto inexistente; transferência;
preview sem escrita; confirmação com perfil errado nunca toca
repo/resolver; Airtable indisponível (preview vira `AMBIGUO`, nunca
derruba); **Postgres indisponível** (fábrica propaga `FalhaConexaoBanco`,
nunca cai para Airtable); **falha entre preview e confirmação** (preview
válido, escrita real falha, nenhum estado parcial); **snapshot Airtable
mudou depois do preview** (TOCTOU — confirmação real re-lê o estado
atual, nunca confia no preview, recusa com segurança); tentativa de
usar ID arbitrário (mesmos testes de posto/colaborador inexistente);
nenhuma escrita Airtable (estrutural); nenhuma gravação antes da
confirmação. Idempotência/conflito/rateio/remoção parcial/evento fora
de ordem continuam cobertos pela suíte já existente de `confirmacao.py`
(não duplicados aqui).

## FASE 10 — Duas revisões adversariais (autocorrigidas nesta rodada)

**Revisão 1 (segurança/temporalidade/identidade/TOCTOU/idempotência/
atomicidade/autorização):** achado e corrigido — `montar_preview` lia
"estado atual" na `data_efetiva` da solicitação pendente em vez de
agora; corrigido com parâmetro `hoje` explícito + teste de regressão.
TOCTOU confirmado protegido por desenho (preview nunca é fonte de
verdade da escrita real). Autorização confirmada: `exigir_perfil`
sempre antes de qualquer I/O.

**Revisão 2 (independência do Airtable/risco de aplicação paralela/
acoplamento ao Render/portabilidade do Postgres/reutilização futura/
regressões/produção):** nenhum Blueprint/app paralelo criado;
`fabrica_repositorio_alocacao.py` não tem nenhuma especificidade de
Render (só `DATABASE_URL` + DB-API 2.0 — portável para qualquer
Postgres gerenciado); nenhuma regressão na suíte completa; zero
produção tocada. Único ponto de acoplamento não-trivial (import
`alocacao` → `modulo01/adapters/conexao`) registrado e justificado na
FASE 5, não escondido.

## FASE 11 — Testes/Governança

Suíte completa local: 1835 passed, 5 failed, 34 errors (mesma baseline
pré-existente de sandbox Windows, sem regressão nova). Governança
local: 15/15 gates. `git diff --check` limpo. Busca manual por padrão
de segredo no diff: nenhum encontrado. Nenhum Postgres real provisionado,
nenhuma migration aplicada em produção, nenhuma escrita Airtable,
nenhum dado real.

## Resultado

Ver relatório estruturado na entrega do PR.
