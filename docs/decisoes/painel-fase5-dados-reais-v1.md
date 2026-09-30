# Painel Operacional (Fase 5) — Recuperação com Dados Reais, V1

## Objetivo

Trazer de volta o painel operacional da esteira documental do Módulo
01 (Fase 5, `docs/magnata-os/central-command/FASE5_AUDITORIA.md`) e
concluí-lo: em vez de deixá-lo mockado indefinidamente ou reescrevê-lo
do zero, esta missão (1) recupera o código Vanilla JS já pronto de
`origin/feat/magnata-os-documental-modulo01-fase5-painel`, (2) expõe
pela primeira vez a API HTTP do Módulo 01 (Fase 4, até agora Python
puro sem rota nenhuma) e (3) troca o adapter do painel de mock para o
HTTP real, sem tocar nenhum arquivo protegido além do mínimo
explicitamente autorizado.

## Estado encontrado (registrado explicitamente, `/CLAUDE.md` §2)

- `FASE5_AUDITORIA.md` (2026-08-22) já tinha investigado e classificado
  o painel: nenhum bloco "REFAZER", stack sem dependência (sem
  `package.json`, sem build), 4.868 linhas prontas, parado só por 2
  bloqueios reais — governança (`ALLOWED_PATHS` não cobria
  `frontend/`) e a API nunca exposta por HTTP.
- `magnata_os/documental/modulo01/api/` (Fase 4) já existia,
  Python puro, testado (`test_magnata_os_documental_modulo01_fase4.py`),
  mas sem nenhuma rota Flask.
- `magnata_os/autenticacao/adapters/blueprint_login.py` já continha
  `exigir_sessao_com_perfil`, decorator desenhado exatamente para este
  caso ("rotas de domínio FUTURAS", conforme seu próprio docstring) —
  nunca usado antes desta missão. `auth_bp` já estava registrado em
  `app.py` (missão anterior, "Autenticação Administrativa Compartilhada
  V1").
- `magnata_os/documental/modulo01/adapters/postgres_repositorio.py` e
  `postgres_repositorio_esteira.py` (Fases 2/3) já existiam,
  implementando os 4 repositórios reais que `ContextoApi` (handlers.py)
  precisa — nunca antes montados juntos numa única fábrica.

## O que foi religado

1. **`magnata_os/documental/modulo01/adapters/api_contexto.py`** (novo)
   — monta um `ContextoApi` real a partir de uma conexão Postgres
   aberta via `conexao.abrir_conexao()` (lê `DATABASE_URL` do
   ambiente). Sem `DATABASE_URL`, levanta `ConfiguracaoBancoAusente` —
   nunca cai para dado em memória/mockado em silêncio (`/CLAUDE.md`
   §4, "falha nunca é silenciosa").
2. **`magnata_os/documental/modulo01/adapters/blueprint_esteira.py`**
   (novo) — blueprint Flask com os 9 endpoints conceituais de
   `handlers.py` (resumo, lotes, lote, documentos, documento,
   histórico, bloqueios, ações humanas, parados), traduzindo
   querystring → `filtros.py` e contrato → JSON (via
   `serializacao.para_json`). Toda rota é decorada com
   `exigir_sessao_com_perfil` (auth reaproveitada, nenhuma nova) e cada
   handler continua aplicando sua própria regra fina de perfil
   (`PERMISSAO_LEITURA_GERAL`/`PERMISSAO_FILA_OPERACIONAL`/
   `PERMISSAO_AUDITORIA`) — a borda HTTP nunca duplica essa lógica, só
   verifica "sessão válida". Sem `DATABASE_URL` configurada, toda rota
   devolve `503 BANCO_NAO_CONFIGURADO`, nunca `200` com dado
   inventado.
3. **`app.py`**: 2 linhas adicionadas (import + `register_blueprint`),
   mesmo padrão já usado para `auth_bp`/`secullum_bp`/`sync_bp`/
   `ingestao_bp` — nenhuma outra linha tocada. Autorizado por blob
   exato em `.magnata/app-py-authorizations/painel-fase5-dados-reais-v1.gitblob`
   (ver esse arquivo para o texto de autorização e seu escopo nominal).
4. **Frontend recuperado** de `origin/feat/magnata-os-documental-modulo01-fase5-painel`
   (`frontend/index.html`, `src/`, `styles/`, `tests/`) — sem alteração
   de conteúdo, exceto:
   - **`frontend/src/api/apiAdapter.js`** (novo) — client HTTP real,
     mesma forma de entrada/saída que `mockAdapter.js` (drop-in), fala
     só com `/magnata-os/documental/*` (o blueprint novo) e `/auth/me`
     — nunca com `app.py`/rota legada/Airtable diretamente
     (`frontend/CLAUDE.md`). Erros HTTP (`codigo` do contrato) são
     traduzidos para a mesma hierarquia de `errors.js`; `401` vira
     `AutenticacaoAusente` (erro próprio do adapter, não um `ApiError`
     do contrato Python).
   - **`frontend/src/app.js`** — `iniciarApp` agora é assíncrono: por
     padrão chama `verificarSessaoAtual()` (`GET /auth/me`) antes de
     montar qualquer tela; sem sessão válida, mostra uma tela de login
     mínima e **nunca monta o painel nem chama nenhum endpoint de
     dado**. `?mock=1` na URL liga o modo demonstração antigo
     (`mockAdapter.js`), sem sessão, só para desenvolvimento local do
     próprio painel sem o servidor da API rodando.
   - **`frontend/src/components/Header.js`** — o seletor de perfil
     (que o próprio `FASE5_AUDITORIA.md` marcou como risco crítico se
     publicado como se fosse autenticação real) só aparece **editável**
     em modo mock. Com sessão real, o perfil é mostrado como
     somente-leitura, vindo da sessão autenticada (`/auth/me`) — nunca
     mais escolhível pelo usuário do painel.
   - Testes novos: `test_magnata_os_documental_modulo01_blueprint_esteira.py`
     (Python, blueprint) e `frontend/tests/apiAdapter.test.js`
     (transporte HTTP, com `fetch` sempre substituído por um duplo —
     nenhum teste toca rede real).

## O que continua mockado / pendência declarada

- **Não há tela de login funcional (botão "Entrar com Google").**
  `auth_bp`/`/auth/login` já aceita um `id_token` do Google, mas
  nenhuma página deste repositório jamais renderizou o botão de sign-in
  do Google Identity Services, nem existe hoje `GOOGLE_OAUTH_CLIENT_ID`/
  `MAGNATA_ADMIN_ALLOWLIST`/`MAGNATA_SESSION_SECRET_KEY` configurados
  neste ambiente. A tela de login deste painel (`app.js::TelaLogin`)
  hoje só informa que a sessão está ausente e oferece recarregar a
  página — **não constrói um mecanismo de autenticação novo** (proibido
  pela missão); constrói só o *gate* de leitura de sessão, que é o que
  foi pedido. Login de fato depende de uma fase própria de frontend
  (botão Google Identity Services) e das 3 variáveis de ambiente reais
  — nenhuma delas foi criada, setada ou solicitada aqui.
- **`?mock=1` continua existindo de propósito** — modo de
  desenvolvimento local do painel sem precisar do servidor Flask nem de
  Postgres rodando. Documentado explicitamente na própria UI (rótulo
  "Perfil (simulação — dado mockado)" no seletor) e nos comentários de
  `app.js`.
- **Sem `DATABASE_URL` configurada neste ambiente**, a API real
  devolve `503` para toda consulta — testado explicitamente
  (`test_sem_database_url_devolve_503_nunca_dado_mockado`). Não foi
  aplicada nenhuma migration nem aberta nenhuma conexão Postgres real
  como parte desta missão.
- **Nenhum deploy, nenhuma exposição pública.** Tudo roda só
  localmente: `python -m http.server --directory frontend` (painel) +
  o servidor Flask de desenvolvimento local para a API (nunca Render/
  produção).

## Como rodar localmente

```bash
# 1. API (num terminal) -- precisa de DATABASE_URL, MAGNATA_SESSION_SECRET_KEY,
#    GOOGLE_OAUTH_CLIENT_ID e MAGNATA_ADMIN_ALLOWLIST reais para autenticar de
#    verdade; sem elas, sobe mas toda rota de dado responde 401/503.
python app.py

# 2. Painel (noutro terminal)
python -m http.server 8000 --directory frontend
# abrir http://localhost:8000/ -- pede sessão (/auth/me) antes de mostrar
# qualquer dado. http://localhost:8000/?mock=1 -- modo demonstração, sem
# servidor/sessão, dado simulado.

# 3. Testes
python -m pytest test_magnata_os_documental_modulo01_blueprint_esteira.py -q
python -m pytest -q                       # suíte Python completa
# Testes JS (harness próprio, sem Node/browser em produção, mas
# executável aqui via qualquer navegador ou Playwright headless):
python -m http.server 8099 --directory frontend &
# abrir http://127.0.0.1:8099/tests/index.html
```

## Riscos remanescentes

- Autenticação de fato (botão de login + variáveis de ambiente reais)
  continua pendência — sem ela, o painel em qualquer ambiente real fica
  preso na tela "sessão não autenticada", por design (fail-closed).
- `DATABASE_URL`/Postgres real para o Módulo 01 não foi provisionado
  nem testado contra dado de produção — só testado contra repositórios
  em memória (sintéticos) e contra a ausência de configuração (503).
- `.magnata/app-py-authorizations/painel-fase5-dados-reais-v1.gitblob`
  autoriza só o blob exato do `app.py` resultante deste diff — qualquer
  mudança posterior (inclusive comentário) invalida essa autorização e
  exige um blob novo.

## Governança

- `.magnata/patterns.sh` (`ALLOWED_PATHS`) ganhou entradas exatas para
  os 2 arquivos Python novos, o teste novo, este documento, e para
  `frontend/index.html`/`frontend/src/`/`frontend/styles/`/
  `frontend/tests/` — nenhuma entrada nova libera `frontend/CLAUDE.md`
  nem `frontend/assets/brand/`, que continuam protegidos e intocados.
- Nenhuma migration nova, nenhuma alteração de schema.
- Nenhuma ação externa real (Airtable, e-mail, WhatsApp, deploy) foi
  executada como parte desta missão.
