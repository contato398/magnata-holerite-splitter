# Magnata AI Engineering Powerpack — Inventário

**Status:** levantamento objetivo, sem nenhuma instalação/configuração
realizada. Nada foi conectado a serviços reais. Nenhum `CLAUDE.md`,
skill, agente, hook ou plugin foi criado nesta etapa — só observação do
que já existe.

**Branch:** `feat/magnata-os-claude-powerpack`, criada a partir da
`main` já atualizada (`f1c0edc`).

---

## 1. Claude Code

### Descoberta importante: qual runtime está de fato em uso

Não existe um binário `claude` (o CLI standalone `@anthropic-ai/claude-code`
via npm) no `PATH` deste ambiente — `claude --version` e `which claude`
não encontram nada. O `PATH` do shell, porém, contém entradas como
`AppData\Roaming\Claude\local-agent-mode-sessions\...\rpm\plugin_*\bin`
e `...\skills-plugin\...`, e `~/.claude.json` tem chaves como
`pluginUsage`, `skillUsage`, `oauthAccount`, `groveConfigCache`,
`penguinModeOrgEnabled`, `machineID` — **não é o formato do CLI OSS**
(que teria `mcpServers`, `theme`, etc. no topo). Conclusão: esta sessão
roda dentro do **cliente Claude Desktop / modo agente da Anthropic**
(nomes de ferramenta internos como `mcp__ccd_session__*` sugerem "Claude
Code Desktop"), que **embute o mesmo motor de agente** (skills,
subagentes, memória, tarefas, MCP) sem exigir a instalação separada do
pacote npm. Isso muda o que "instalar o Powerpack" significa na
prática — ver seção 5.

### Versão instalada
Não determinável via CLI nesta sessão (binário `claude` ausente do
`PATH`). O cliente desktop tem seu próprio ciclo de atualização,
opaco a partir daqui.

### Diagnóstico disponível
`claude doctor` (comando de terminal interativo) não está disponível
nesta sessão não-interativa — comandos de diálogo de terminal como
`/doctor`, `/config`, `/permissions`, `/hooks`, `/agents` abrem um
painel interativo que este modo de execução não suporta.

### Diretórios de configuração encontrados
- `C:\Users\Lenovo\.claude\` (perfil do usuário) — contém `backups/`,
  `projects/` (histórico de sessões por repositório, incluindo
  transcrições `.jsonl` de subagentes já executados — não definições de
  agentes), `session-env/`, `sessions/`, `shell-snapshots/`, `tasks/`,
  e um arquivo `.credentials.json` (ver Segurança).
- `C:\Users\Lenovo\.claude.json` (39 KB) — cache/estado do cliente
  desktop (ver acima), não um arquivo de configuração de MCP no formato
  tradicional do CLI.
- `C:\Users\Lenovo\magnata-holerite-splitter\.claude\` (projeto) —
  contém só `settings.local.json` (e, na branch da Fase 5, também
  `launch.json`, usado para o preview do painel — não presente na
  `main`/nesta branch).

### Arquivos `CLAUDE.md` existentes
**Nenhum.** Busca em `~` (nível superior) e em toda a árvore do
repositório não encontrou nenhum `CLAUDE.md`, em nenhum nível
hierárquico.

### Configurações locais e de projeto
- `settings.local.json` (projeto) existe e contém **só uma allowlist de
  permissões** (`permissions.allow`) — cerca de 100 padrões de comando
  `Bash(...)`/`PowerShell(...)` aprovados ao longo de sessões anteriores
  (ex.: `git push *`, `gh pr *`, comandos `pytest` específicos). Não há
  chave `hooks`, `mcpServers` nem `env` nesse arquivo.
- Não existe `settings.json` (nível de projeto, versionável e
  compartilhável pela equipe) — só o `settings.local.json` (pessoal,
  não versionado por convenção do próprio Claude Code, embora este
  repositório não tenha `.claude/` no `.gitignore` — ver Segurança).
- Não existe `settings.json` de usuário (`~/.claude/settings.json`).

### Permissões configuradas
Só a allowlist descrita acima — nenhuma política de `deny`, nenhuma
categoria ampla liberada (ex.: não há `Bash(*)` genérico), tudo por
comando específico.

### Hooks existentes
**Nenhum.** Nenhuma chave `hooks` em `settings.local.json`, nenhum
diretório de hooks em `~/.claude/` ou no projeto.

### MCPs configurados
Nenhum arquivo `.mcp.json` (nem no projeto, nem em `~`). Ainda assim,
**esta sessão já tem várias ferramentas MCP conectadas** pelo cliente
desktop/organização, fora do fluxo de arquivo de config tradicional:

- **Já autenticados e ativos nesta sessão** (evidência direta: as
  ferramentas aparecem na lista de ferramentas disponíveis):
  - Um MCP de **Airtable** (`mcp__b78cb0ae-...`) — leitura/escrita de
    bases, tabelas, registros, automações.
  - Um MCP tipo **Gmail/Workspace** (`mcp__88f67136-...`) — rascunhos,
    labels, busca de threads.
  - `mcp__Claude_Browser__*` — navegador sandboxed embutido no cliente.
  - `mcp__claude-in-chrome__*` — automação do Chrome real do usuário
    (ferramentas "deferidas", carregadas sob demanda).
  - `mcp__visualize__*` — widgets/gráficos inline.
  - `mcp__mcp-registry__*` — busca/sugestão de conectores MCP
    disponíveis para instalar.
  - `mcp__scheduled-tasks__*` — agentes agendados (cron).
  - `mcp__ccd_session__*`, `mcp__ccd_directory__*`,
    `mcp__ccd_session_mgmt__*` — gestão de sessão/tarefas do próprio
    cliente (infraestrutura interna, não um serviço externo).
- **Listados, mas exigindo autorização OAuth antes de uso** (plugins de
  marketing/operações, não autenticados nesta sessão): `ahrefs`,
  `amplitude`, `amplitude-eu`, `canva`, `figma`, `hubspot`, `klaviyo`,
  `similarweb`, `supermetrics`, `asana`, `atlassian`, `notion`, `slack`.
- **Ausente: MCP do GitHub.** Toda interação com PRs nesta sessão até
  aqui foi feita via `curl` direto à API REST do GitHub, usando
  credencial extraída de `git credential fill` — porque não há `gh` CLI
  nem MCP do GitHub disponíveis (ver Ambiente e Compatibilidade).

### Plugins instalados
Não há um comando não-interativo para listar plugins nesta sessão, mas
há evidência indireta forte: a chave `pluginUsage` em `~/.claude.json`,
e a existência de **agentes e skills com prefixo de plugin** (ex.:
`searchfit-seo:*`, `cowork-plugin-management:*`) — confirmando que pelo
menos dois pacotes de plugin (um de SEO, um de gestão de plugins) estão
instalados a nível de organização/cliente.

### Skills existentes
Uma lista grande e variada já está disponível **a nível de
organização/cliente**, cobrindo marketing, operações, documentos
Office, visualização de dados e utilidades do próprio Claude Code
(`update-config`, `fewer-permission-prompts`, `keybindings-help`,
`skill-creator`, `loop`, `schedule`, `claude-api`, `simplify`,
`dataviz`, `artifact-design`/`artifact-capabilities`,
`consolidate-memory`, `docx`/`pdf`/`pptx`/`xlsx`, `morning`,
`setup-cowork`). **Nenhuma skill específica deste repositório** (nada
em `.claude/skills/` no projeto — o diretório nem existe).

### Agentes/subagentes existentes
Disponíveis nativamente nesta sessão: `claude` (genérico), `Explore`
(busca read-only), `general-purpose`, `Plan`, `claude-code-guide`,
`statusline-setup`, mais 3 agentes do plugin `searchfit-seo`. **Nenhum
subagente customizado para este repositório** — não há
`.claude/agents/` no projeto.

### Comandos personalizados existentes
**Nenhum.** Não há `.claude/commands/` no projeto nem evidência de
slash commands customizados — só os skills invocáveis via `/nome`
listados acima (que são um mecanismo diferente de comandos puros).

---

## 2. Ambiente

| Item | Resultado |
|---|---|
| Sistema operacional | Windows 10 Pro (build 19045), acessado via MINGW64/Git Bash (`MINGW64_NT-10.0-19045`) |
| Shell | Git Bash (`bash 5.3.9`) como padrão desta ferramenta; PowerShell 5.1 (Windows PowerShell, não PowerShell 7/Core) também disponível |
| Git | `2.54.0.windows.1` |
| Python | `3.12.10`, instalação global do sistema (`C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\`) — **sem virtualenv** (`sys.base_prefix == sys.prefix`) |
| Node.js/npm/npx | **Ausentes** — nenhum dos três no `PATH`, confirmado repetidamente durante a Fase 5 |
| Docker | **Ausente** — `docker --version` não encontrado |
| Navegador | Chrome instalado em `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe` (relevante para `claude-in-chrome`); além disso, um navegador sandboxed embutido no cliente (`Claude_Browser`) já funcional, sem depender de instalação local |
| Ferramentas de teste de interface | **Nenhuma instalada** — sem cache do Playwright (`~/AppData/Local/ms-playwright` não existe), sem `playwright`/`selenium` no `pip list` |
| GitHub CLI (`gh`) | **Ausente** — confirmado via `which`, `Get-Command` e `command -v`, nenhum encontra o binário |
| Variáveis de ambiente relevantes | `AIRTABLE_API_KEY` e `ANTHROPIC_BASE_URL` estão definidas no ambiente (nomes confirmados, **valores nunca lidos nem impressos**) |

### Pacotes Python relevantes já instalados globalmente
`pytest 9.1.1`, `pytest-mock 3.15.1`, `Flask 3.0.3`, `pymupdf 1.28.0`,
`CairoSVG 2.9.0` (os dois últimos instalados ad-hoc durante a Fase de
identidade visual — **não estão em `requirements.txt`**). Nenhuma
ferramenta de lint/type-check (`mypy`, `ruff`, `flake8`, `black`)
instalada.

---

## 3. Repositório

### Arquitetura documental atual
Módulo 01 (Documental) do "Magnata OS" já implementado em
`magnata_os/documental/modulo01/` através de 5 fases: domínio +
serviço de entrada (Fase 1), persistência Postgres/S3 (Fase 2), lotes e
esteira operacional (Fase 3), API de consulta (Fase 4), painel visual
mock (Fase 5, branch própria não mesclada). Convive lado a lado com o
sistema legado em `app.py` (Flask monolítico, ~455 mil bytes) sem
nenhum acoplamento — princípio "strangler pattern" documentado em
`MAGNATA_OS_MANIFESTO.md`.

### Documentação estruturante existente
**Tracked (versionada):** `MAGNATA_OS_DOCUMENTAL_MODULO01.md` (+
`_FASE2`/`_FASE3`/`_FASE4`), `MAGNATA_OS_IDENTIDADE_VISUAL.md`,
`MAGNATA_OS_MODULO_01_FASE_0_OBSERVABILIDADE.md`,
`MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1.md`.

**⚠️ Não versionada (existe só neste computador):**
`MAGNATA_OS_ARQUITETURA.md`, `MAGNATA_OS_CONTRATOS.md` (83 KB),
`MAGNATA_OS_DECISOES_ENTIDADES.md` (89 KB), `MAGNATA_OS_ENTIDADES.md`
(76 KB), `MAGNATA_OS_ESTADOS.md` (79 KB), `MAGNATA_OS_EVENTOS.md`
(95 KB), `MAGNATA_OS_MANIFESTO.md` (20 KB),
`MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO.md`,
`MAGNATA_OS_MODULO_01_INGESTAO.md` — **documentação fundacional volumosa
(centenas de KB) que nunca foi commitada.** Risco real de perda se esta
máquina falhar, e invisível para qualquer outra sessão/colaborador que
clone o repositório.

### Comandos oficiais de testes
Não há um comando "oficial" documentado em nenhum lugar do repositório
(sem `Makefile`, sem seção de testes no `README` — não existe
`README.md` na raiz). O padrão observado ao longo das últimas fases
(nos próprios `MAGNATA_OS_DOCUMENTAL_MODULO01_FASE*.md`) é:
```bash
pytest test_arquivo_especifico.py -v
pytest test_a.py test_b.py ... test_p.py -q   # suíte completa, 16 arquivos tracked
```
5 falhas pré-existentes e conhecidas (não relacionadas ao Módulo 01)
persistem nessa suíte desde antes da Fase 2 — documentadas em cada
relatório de fase, nunca "corrigidas silenciosamente".

### Ferramentas de lint/type-checking
**Nenhuma configurada.** Sem `pyproject.toml`, `setup.cfg`, `.flake8`,
`mypy.ini`, `tox.ini`, nem `.pre-commit-config.yaml` na raiz.

### GitHub Actions existentes
**Nenhuma.** Não existe diretório `.github/` no repositório — logo,
nenhum workflow de CI/CD automatizado hoje. Todo teste/verificação até
aqui foi manual, executado por mim (Claude) ou pelo usuário, em sessões
interativas.

### Arquivos sensíveis ou protegidos
- `.env` (167 bytes) e `.env.txt` (67 bytes) na raiz — **contêm
  segredos** (confirmado em sessões anteriores: chave de API do
  Airtable), corretamente listados em `.gitignore`, nunca commitados.
- `AIRTABLE_API_KEY` também presente como variável de ambiente do
  processo (ver Ambiente) — uma segunda cópia do mesmo segredo, fora do
  arquivo.
- `~/.claude/.credentials.json` (4,9 KB) — credenciais do próprio
  cliente Claude (ver Segurança).
- `render.yaml` e `Procfile` — configuração de deploy para Render.com
  (web + worker `celery`), sem segredo embutido, mas apontam o alvo de
  produção real (mencionado explicitamente como fora de escopo nesta
  tarefa).
- `_evolution_docker-compose.yml` (gitignored) — configuração local da
  Evolution API (gateway de WhatsApp), também fora de escopo aqui.

### Padrões atuais de branch, commit e PR
- **Branches:** prefixo `feat/`, `fix/` ou `chore/` +
  descrição-em-cadeia (ex.: `feat/magnata-os-documental-modulo01-fase4-api-esteira`).
  10 branches remotas além de `main` no momento deste inventário.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org)
  em português (`feat: ...`, `fix: ...`), assunto curto + corpo
  detalhado explicando o quê e o porquê, sempre com
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` quando a
  mudança é feita por mim.
- **PRs:** um PR por fase/entrega, título espelhando o commit
  principal, corpo estruturado em seções (objetivo, entregas, testes,
  escopo/limites) — mergeados via "Merge pull request" (merge commit
  preservado, não squash).

---

## 4. Segurança

**Nenhum segredo foi impresso, lido em texto puro, testado ou usado
nesta etapa.** Achados (só existência/local, nunca valor):

1. **`.env` / `.env.txt`** (raiz do repo) — arquivos de credenciais em
   texto puro no disco. Mitigado por estarem no `.gitignore` desde uma
   correção em sessão anterior; risco residual normal de qualquer
   `.env` local (quem tiver acesso ao disco tem acesso ao segredo).
2. **`AIRTABLE_API_KEY` como variável de ambiente do processo** —
   segunda cópia do mesmo tipo de segredo, fora de arquivo; visível a
   qualquer processo filho do shell atual (inclusive esta sessão).
3. **`~/.claude/.credentials.json`** — credenciais do próprio cliente
   Claude (provavelmente token OAuth de sessão). Gerenciado pelo
   cliente, fora do controle deste repositório — mencionado aqui só
   para registro de que existe em texto no disco do usuário.
4. **MCPs já autenticados e ativos nesta sessão** (Airtable, um serviço
   tipo Gmail) — **não são credenciais mal guardadas** (o fluxo OAuth do
   cliente é o esperado), mas representam **acesso real e imediato a
   serviços de produção disponível neste exato ambiente**, sem
   nenhuma barreira técnica adicional além da disciplina de instrução.
   Isso é o principal motivo para a seção "Itens que não devem receber
   acesso de produção" abaixo ser levada a sério — o acesso já existe,
   só não foi exercido.
5. **Nenhuma credencial foi testada, nenhuma chamada real foi feita**
   a Airtable, Render, Gmail, PostgreSQL, S3/R2 ou Evolution API durante
   este levantamento.
6. **Nenhuma permissão foi alterada** — `settings.local.json` foi só
   lido, não editado.

---

## 5. Compatibilidade (avaliação, nada instalado)

| Recurso pedido | Compatível? | Observação |
|---|---|---|
| `CLAUDE.md` hierárquico | ✅ Sim | Mecanismo nativo do runtime em uso (evidenciado pelas instruções de sistema desta própria sessão, que descrevem suporte a hierarquia de `CLAUDE.md`); só precisa ser criado — nenhum pré-requisito de instalação. |
| Skills locais (`.claude/skills/`) | ✅ Sim | O cliente já executa skills de organização; skills de projeto usam o mesmo mecanismo, só exigem criar os arquivos no repositório. |
| Subagentes (`.claude/agents/`) | ✅ Sim | Mesma lógica das skills — o mecanismo de subagente já está ativo (uso da ferramenta `Agent` nesta própria sessão), falta só a definição local. |
| Hooks | ⚠️ Parcial/a confirmar | O conceito é suportado pelo runtime (referenciado nas instruções de sistema e existe uma skill dedicada, `update-config`, para configurá-los via `settings.json`), mas **nunca foi testado neste ambiente** — like todo hook dispara um processo externo (ex.: `git`, um linter), a viabilidade real depende de cada comando individual estar disponível (ex.: um hook de lint falharia hoje, pois não há `ruff`/`mypy` instalados). |
| GitHub MCP | ❌ Ausente | Não conectado nesta sessão. `mcp-registry` (já disponível) pode descobrir um conector, mas a instalação/autenticação em si não foi feita — ver "exige instalação adicional". Sem ele, qualquer automação de PR precisa continuar via `curl` + credencial do `git credential fill` (funcional, mas manual). |
| Navegador controlado | ✅ Sim (2 modos) | `Claude_Browser` (sandboxed, já funcional, usado extensivamente na Fase 5) não exige nada instalado. `claude-in-chrome` (Chrome real do usuário) também disponível — Chrome 32-bit confirmado instalado no sistema. |
| Playwright ou alternativa | ❌ Ausente | Nenhum cache do Playwright, nenhum pacote Python de teste de UI instalado. Já existe alternativa funcional (`Claude_Browser`) que cobriu toda a verificação de UI da Fase 5 sem precisar de Playwright — **pode não ser necessário instalar**, dependendo do que o Powerpack pretende automatizar (ex.: testes E2E versionados rodando fora de uma sessão de agente precisariam de algo como Playwright de verdade). |
| Execução não interativa | ✅ Sim, com limite conhecido | Esta própria sessão já roda de forma não-interativa (sem prompts de terminal); a limitação conhecida é que comandos de diálogo (`/doctor`, `/config`, `/permissions`, `/hooks`, `/agents`) não funcionam neste modo — qualquer automação que dependa deles precisa de um caminho alternativo (edição direta de `settings.json`, por exemplo). |
| GitHub Actions | ⚠️ Possível, mas não existe hoje | Nenhum workflow no repositório atualmente — criar um do zero é viável tecnicamente, mas é trabalho novo, não "ativar algo que já existe". |
| Execução agendada futura de agentes | ✅ Mecanismo já existe | `mcp__scheduled-tasks__*` (cron de agentes) já está disponível nesta sessão — não testado, mas presente e pronto para avaliação futura. |

---

## Síntese

### O que já existe
- Runtime de agente com skills/subagentes/memória/tarefas nativos,
  ativo nesta própria sessão, sem exigir instalação de CLI separada.
- MCPs já conectados e autenticados: Airtable, um serviço tipo Gmail,
  navegador sandboxed, navegador Chrome real, widgets, registry de
  conectores, agendador de tarefas.
- Dezenas de skills e alguns subagentes de organização/plugin
  (marketing, operações, SEO, utilidades) prontos para uso imediato.
- Git, Python 3.12 com pytest, e um histórico consistente de
  convenções de branch/commit/PR já em produção há várias fases.
- Um navegador real instalado no sistema (Chrome).

### O que está ausente
- `CLAUDE.md` (qualquer nível).
- Qualquer customização de projeto: `.claude/agents/`,
  `.claude/skills/`, `.claude/commands/`, hooks.
- MCP do GitHub (`gh` CLI também ausente).
- Node.js/npm/npx, Docker, Playwright (ou qualquer ferramenta dedicada
  de teste de UI fora do navegador do próprio cliente).
- GitHub Actions / qualquer CI automatizado.
- Ferramentas de lint/type-check (mypy, ruff, flake8, black).
- `requirements-dev.txt` ou equivalente (dependências de teste/dev não
  declaradas em lugar nenhum — `pytest` foi instalado manualmente).

### O que pode ser instalado/criado imediatamente (sem dependência externa)
- `CLAUDE.md` na raiz do projeto.
- Skills e subagentes locais em `.claude/skills/` e `.claude/agents/`.
- `settings.json` de projeto (versionável, distinto do
  `settings.local.json` atual).
- Hooks simples que só dependem de ferramentas já instaladas (git,
  python, pytest).
- `requirements-dev.txt` capturando `pytest`/`pytest-mock` já em uso.

### O que exige instalação adicional
- MCP do GitHub — requer descoberta via `mcp-registry` e autenticação.
- Qualquer hook que dependa de lint/type-check — requer instalar
  `ruff`/`mypy` (ou equivalente) primeiro.
- GitHub Actions — requer criar `.github/workflows/` do zero (não é
  "ativar", é construir).
- Testes E2E versionados e reprodutíveis fora de uma sessão de agente —
  requer Playwright (ou similar) instalado de verdade, já que
  `Claude_Browser` só existe dentro de uma sessão de agente ativa.

### Riscos
1. **Documentação fundacional não versionada** (9 arquivos, centenas de
   KB) — o maior risco concreto encontrado neste inventário; não é um
   risco de segurança, é risco de perda de conhecimento.
2. **Acesso real a Airtable/Gmail já disponível nesta sessão** — a
   barreira contra uso indevido é hoje só a instrução, não uma
   restrição técnica; qualquer automação futura (hooks, agentes
   agendados) precisa reforçar essa fronteira explicitamente.
3. **Ausência total de CI** — toda verificação depende de alguém (ou
   algum agente) lembrar de rodar a suíte manualmente; nada barra um
   PR com testes quebrados hoje.
4. **Sem lint/type-check** — bugs de tipo/estilo só aparecem em
   revisão humana ou em execução real.
5. **Sem venv** — dependências (incluindo as instaladas ad-hoc,
   `pymupdf`/`cairosvg`) vivem no Python global do sistema, não
   isoladas nem declaradas.
6. **`gh` CLI e MCP do GitHub ausentes** — todo fluxo de PR depende de
   `curl` manual com credencial extraída via `git credential fill`,
   um processo mais frágil e com mais superfície de erro humano do que
   uma ferramenta dedicada.

### Dependências entre os itens
`CLAUDE.md` e skills/agentes/hooks locais não dependem de nada externo
— podem vir primeiro. Hooks de lint dependem de instalar as ferramentas
de lint antes. MCP do GitHub deveria vir antes de qualquer automação de
PR via agente agendado (para não depender do fluxo `curl` manual em
execução não supervisionada). GitHub Actions depende de já existir uma
suíte de comandos confiável (`pytest ...`) documentada — que já existe,
então essa dependência está satisfeita.

### Ordem recomendada de implantação
1. **Commitar a documentação fundacional não versionada** (risco #1,
   sem custo técnico, só decisão).
2. `CLAUDE.md` na raiz (orienta qualquer sessão futura, humana ou
   agente).
3. `requirements-dev.txt` + (opcional) migrar para um venv declarado.
4. Skills/subagentes locais de projeto, começando pelos que já têm
   padrão comprovado nesta sessão (ex.: um skill de "rodar suíte de
   testes e reportar falhas preexistentes separadamente", que já é o
   que faço manualmente a cada fase).
5. Ferramentas de lint/type-check + hook de pre-commit local.
6. MCP do GitHub (substitui o fluxo `curl` manual).
7. GitHub Actions (CI mínimo: rodar a suíte de testes a cada PR).
8. Só depois, com tudo acima estável: execução agendada de agentes
   (`mcp__scheduled-tasks__*`) — porque agendar automação **antes** de
   ter CI e MCP do GitHub confiáveis aumenta o risco do item #2 da
   seção de riscos, não reduz.

### Itens que não devem receber acesso de produção
- **Airtable** (MCP já conectado, credencial de ambiente `AIRTABLE_API_KEY`,
  `.env`/`.env.txt` locais) — qualquer hook/agente agendado criado no
  Powerpack deve explicitamente não usar essas credenciais, a menos que
  uma tarefa peça uma escrita real, com a mesma disciplina de dry-run +
  autorização explícita já usada nas fases anteriores.
- **Render** (`render.yaml`/`Procfile` apontam o serviço real de
  produção) — nenhuma automação deve disparar deploy sozinha.
- **Gmail/Workspace** (MCP já conectado) — mesma cautela do Airtable.
- **PostgreSQL / S3 / R2** — ainda nem foram conectados a este projeto
  (Fases 2-4 só usam adapters em memória/duck-typed); nenhum Powerpack
  deveria ser o primeiro a criar essa conexão real sem uma decisão
  explícita separada.
- **Evolution API** (WhatsApp) — `_evolution_docker-compose.yml` local,
  gitignored, nunca deve ser subido por automação nenhuma.
