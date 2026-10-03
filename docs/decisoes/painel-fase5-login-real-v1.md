# Painel Operacional (Fase 5) — Tela de Login Real, V1

## Objetivo

Substituir a tela mínima "sessão ausente" do painel
(`frontend/src/app.js`) por uma tela de login funcional, usando
**exatamente** o mecanismo de autenticação já existente no backend
(`magnata_os/autenticacao/adapters/blueprint_login.py::auth_bp`, já
registrado em `app.py` — commit `89c9c45`) — nenhum mecanismo de
autenticação novo foi criado nesta missão.

Branch: `fix/magnata-os-painel-fase5-login-real-v1`. Baseline: `main`
com `aeeea2a` (PR #204 mesclada). `app.py` **não foi tocado** — não
precisou: `/auth/login`, `/auth/logout`, `/auth/me` já existem e já
estão registradas.

## O que o backend já espera (confirmado lendo o código, não assumido)

- **Mecanismo:** Google Identity Services ("Sign in with Google"),
  delegado — nunca senha própria (ver
  `docs/decisoes/autenticacao-administrativa-compartilhada-v1.md`,
  FASE 1).
- `POST /auth/login`: corpo `{"id_token": "<ID token do Google>"}`.
  Nunca aceita `email`/`perfil` autodeclarado — `email` só depois de
  verificado pelo Google, `perfil` só depois de resolvido pela
  allowlist (`magnata_os/autenticacao/allowlist.py`).
  Respostas: `200 {email, perfil, csrf_token}` em sucesso; `400
  {erro:"id_token_ausente"}`; `401 {erro:"identidade_invalida"}`; `403
  {erro:"nao_autorizado"}`; `503 {erro:"provedor_indisponivel"}`.
- `GET /auth/me`: `200 {autenticado:false}` sem sessão válida, `200
  {autenticado:true, email, perfil, csrf_token}` com sessão válida —
  já consumido por `verificarSessaoAtual()` em `apiAdapter.js` desde a
  missão anterior.
- Variáveis de ambiente lidas pelo backend (nomes confirmados no
  código, nunca inventados):
  - `GOOGLE_OAUTH_CLIENT_ID` (`provedor_google_oidc.py`) — Client ID
    público do OAuth (não é segredo — é enviado ao navegador de
    qualquer forma para renderizar o botão de login).
  - `MAGNATA_ADMIN_ALLOWLIST` (`allowlist.py`) — formato
    `email:PERFIL,email:PERFIL`.
  - `MAGNATA_SESSION_SECRET_KEY` (`adapters/sessao.py`) — segredo da
    sessão Flask assinada; falha explícita (`SegredoSessaoAusente`) se
    ausente.

**Nenhuma das três está configurada neste ambiente de
desenvolvimento** (confirmado via variável de ambiente vazia, sem
imprimir nenhum valor). Isso não é uma regressão desta missão — o
próprio `docs/decisoes/autenticacao-administrativa-compartilhada-v1.md`
(FASE 9) já registrava isso como gate externo pendente.

## O que foi construído (frontend, sem tocar `app.py`)

- `frontend/src/components/TelaLogin.js` (novo) — tela de login real:
  título, texto explicativo, container do botão "Entrar com o Google"
  e área de estado (reaproveita `estadoErro`/`estadoCarregando` de
  `EstadosUI.js`, mesmo componente usado no resto do painel — nenhum
  design paralelo). Toda integração com SDK/rede (`carregarGis`/
  `renderizarBotao`) e com o backend (`autenticar`) é injetável —
  mesmo padrão de dependência injetável já usado no backend
  (`verificador` em `provedor_google_oidc.py`).
- `frontend/src/auth/googleIdentity.js` (novo) — carrega o script
  oficial do Google (`accounts.google.com/gsi/client`) só quando a
  tela de login precisa, e inicializa/renderiza o botão do SDK. Única
  parte do frontend que toca o SDK real do Google.
- `frontend/src/config.js` + `frontend/src/runtime-config.js` (novos)
  — mecanismo de configuração pública em tempo de deploy. O painel é
  estático (sem servidor de template — ver
  `docs/decisoes/painel-fase5-frontend-v1.md`), então o
  `GOOGLE_OAUTH_CLIENT_ID` (público, nunca segredo) precisa vir de um
  arquivo que cada ambiente sobrescreve no deploy —
  `frontend/src/runtime-config.js` é esse arquivo (script clássico,
  carregado por `index.html` antes do módulo `app.js`), commitado com
  `GOOGLE_OAUTH_CLIENT_ID: null`. `config.js` só lê
  `window.MAGNATA_CONFIG` e nunca lança, mesmo se o script não
  carregar.
- `frontend/src/api/apiAdapter.js` — adicionadas `autenticarComIdToken`
  (POST `/auth/login`) e a classe `ErroLogin` (mapeia os 4 códigos de
  erro que `auth_bp::login()` devolve). Mesmo padrão de
  `verificarSessaoAtual` (já existente): nunca finge sucesso.
- `frontend/src/app.js` — `iniciarApp` refeito para: sem sessão,
  montar `TelaLogin` e só resolver (com o `store` do painel) depois de
  um login bem-sucedido — nunca antes disso. Lógica de montagem do
  shell/rotas extraída para `montarPainel(...)`, reaproveitada tanto
  no caminho "sessão já válida" quanto no caminho "login concluído
  agora".
- `frontend/index.html` — inclui `<script src="src/runtime-config.js">`
  antes do módulo `app.js`.
- `frontend/styles/components.css` — 2 regras pequenas (`.gis-botao-login`,
  ocultar `#area-estado-login` vazio) — reaproveita os tokens/estados
  já existentes, nenhum estilo paralelo.

## Sem configuração — comportamento garantido (item 4 do pedido)

Sem `GOOGLE_OAUTH_CLIENT_ID` (caso deste ambiente), `TelaLogin`
renderiza normalmente e mostra o estado estrutural "Login indisponível:
configuração ausente…" (via `estadoErro`) — nunca tenta carregar o SDK
do Google, nunca finge sessão autenticada. Confirmado manualmente
(Playwright headless contra `frontend/index.html` servido localmente)
e coberto por teste automatizado.

## Testes

`frontend/tests/telaLogin.test.js` (novo) e `frontend/tests/app.test.js`
(novo) cobrem os 4 cenários pedidos:
- tela de login renderiza corretamente (título, texto, container do
  botão do Google);
- submissão bem-sucedida atualiza o estado de sessão e monta o painel
  (perfil/e-mail vindos da resposta real de `/auth/login`, header
  mostra o e-mail autenticado);
- submissão com erro mostra a mensagem certa, para os 4 códigos de
  erro que o backend pode devolver (`nao_autorizado`,
  `identidade_invalida`, `provedor_indisponivel`, `id_token_ausente`),
  nunca chama `aoAutenticar`;
- sem configuração, mostra o erro estrutural certo, nunca quebra.

`frontend/tests/legado.test.js` (item 12, "ausência de dependência do
legado") estendido para cobrir os 3 arquivos novos que não chamam
`fetch()`/SDK real (`TelaLogin.js`, `googleIdentity.js`, `config.js`,
`runtime-config.js`) — a mesma regra "nenhum `fetch()` fora de
`apiAdapter.js`" continua valendo.

Nenhum e-mail/allowlist real é usado em nenhum teste — só sintéticos
(`@exemplo.com`, `@teste.*`), nenhum id_token real do Google, nenhuma
chamada de rede real ao Google nem ao backend (toda integração
injetada/mockada, mesmo padrão de `apiAdapter.test.js`).

**Resultado local (Playwright headless, `frontend/tests/index.html`):
145/145 testes passaram (134 pré-existentes + 11 novos), 0 falhas.**
Suíte Python completa (baseline, nenhuma mudança Python nesta missão):
2979 passed, 103 skipped, 0 failed — idêntico ao estado de `main`
antes desta branch. Governança local: 15/15 gates (script) / 14/14
validações (`pre-commit`).

## O que não entra / pendências declaradas

- **Nenhuma variável de ambiente real configurada** neste ambiente de
  desenvolvimento (`GOOGLE_OAUTH_CLIENT_ID`/`MAGNATA_ADMIN_ALLOWLIST`/
  `MAGNATA_SESSION_SECRET_KEY`) — sem elas, o login real não funciona
  em lugar nenhum ainda, só a estrutura está pronta. Configurá-las é
  decisão/ação humana fora da capacidade desta sessão (registrar
  Client ID no Google Cloud Console, decidir a allowlist real,
  provisionar o segredo de sessão no Render) — mesmo gate já registrado
  em `autenticacao-administrativa-compartilhada-v1.md`, FASE 9.
- **Nenhum mecanismo automatizado de deploy do
  `frontend/src/runtime-config.js` por ambiente foi construído** —
  hoje é um arquivo estático commitado com valor `null`; cada deploy
  real precisaria sobrescrevê-lo (ou um mecanismo equivalente) com o
  Client ID real daquele ambiente antes de servir o painel. Isso não
  foi implementado porque built-in de deploy está fora do escopo desta
  missão (poderia exigir tocar `app.py` para servir o frontend, ou
  infraestrutura de build — nenhum dos dois autorizado aqui) — registrado
  como pendência, não escondido.
- **Nenhuma tela de logout foi adicionada.** A missão pediu
  especificamente "deixar a pessoa entrar" — logout (`POST
  /auth/logout`, já existe no backend) fica fora de escopo desta
  entrega, não foi incluído para não expandir o pedido em silêncio.
  Sugestão separada para uma próxima missão.
- **`frontend/` continua servido só localmente**
  (`python -m http.server --directory frontend`) — nenhuma exposição
  pública, nenhum deploy real, conforme já declarado em
  `painel-fase5-frontend-v1.md`.
- Nenhuma ação externa real (Google Cloud Console, Airtable, Postgres,
  e-mail/WhatsApp, deploy) foi executada nesta missão.
