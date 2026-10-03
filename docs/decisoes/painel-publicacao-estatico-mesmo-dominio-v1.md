# ADR — Publicação do painel estático no mesmo domínio do backend (V1)

- **Branch:** `fix/painel-publicacao-estatico-mesmo-dominio-v1`
- **Data:** 2026-10-03
- **Status:** blueprint novo construído e testado; registro em `app.py`
  **NÃO aplicado** — aguarda autorização humana específica, numa
  mensagem distinta (ver `/CLAUDE.md` §6(e)).

## 1. Objetivo

O dono do produto nunca acessou o painel operacional da Fase 5
(`frontend/`) em produção — só o rodou localmente
(`python -m http.server --directory frontend`). Ele quer o painel
publicado de verdade, acessível por computador, celular ou tablet.

## 2. Por que mesmo domínio (não um site estático separado)

Confirmado por leitura direta de `frontend/src/api/apiAdapter.js`:
todas as chamadas de API usam caminho **relativo**, à raiz do domínio
— `/auth/me`, `/auth/login`, `/magnata-os/documental/...` — e a opção
`credentials` de cada `fetch` configurada para same-origin. Isso significa que o
cookie de sessão (ver `magnata_os/autenticacao/adapters/sessao.py`)
só é enviado pelo navegador quando o painel é servido da MESMA origem
(protocolo + domínio + porta) do backend Flask. Um site estático
hospedado em outro domínio nunca receberia esse cookie — o painel
mostraria permanentemente a tela de login sem conseguir autenticar, ou
exigiria reconstruir toda a autenticação em torno de CORS
cross-origin com credenciais, o que é mais risco de segurança, não
menos. Por isso o painel precisa ser servido pelo mesmo processo
Flask/domínio que já serve `/auth`, `/magnata-os/documental` etc.

## 3. O que foi construído nesta missão

- `magnata_os/documental/modulo01/adapters/blueprint_painel_estatico.py`
  — blueprint novo, isolado, que serve `frontend/` (HTML/CSS/JS/
  assets) sob o prefixo `/painel`, usando exclusivamente
  `flask.send_from_directory` (nunca concatenação manual de path —
  é a própria função do Flask/Werkzeug que rejeita tentativa de path
  traversal, levantando `NotFound`/404).
  - `GET /painel/` → serve `frontend/index.html`.
  - `GET /painel/<qualquer-caminho>` → serve o arquivo correspondente
    de `frontend/` (ex.: `/painel/src/nav.js`, `/painel/styles/
    tokens.css`), com `Content-Type` resolvido pela extensão.
  - Caminho inexistente → 404 real.
- `test_magnata_os_documental_modulo01_blueprint_painel_estatico.py`
  — 7 testes: `index.html` na raiz, arquivo `.js` com Content-Type
  JavaScript, arquivo `.css` com Content-Type correto, 404 real para
  caminho inexistente, e 3 testes explícitos de path traversal
  (`../app.py`, `%2e%2e/app.py`, `..%2f..%2f..%2f..%2fapp.py`) — todos
  bloqueados.
- Este documento.

**Nenhuma linha de `app.py` foi alterada.** `frontend/` não foi
tocado — nenhum arquivo do painel foi criado, removido ou editado.

## 4. Decisões registradas no caminho

- **Prefixo de rota: `/painel`.** Curto, não colide com nenhum
  prefixo já registrado em `app.py` (`/auth`, `/secullum`,
  `/magnata-os/documental`), e é o nome que o próprio usuário usa para
  se referir à tela.
- **Nenhum SPA fallback.** Lido `frontend/src/nav.js`: todas as rotas
  são client-side por **hash** (`#/resumo`, `#/documentos`,
  `#/ingestao-lote` etc.), nunca enviadas ao servidor pelo navegador;
  `frontend/src/app.js` troca de componente dentro do mesmo
  `index.html`, sem nunca pedir ao servidor uma URL de caminho novo.
  Logo não existe rota profunda tipo `/painel/documentos` que
  precisasse cair em `index.html` — todo caminho sob `/painel/` que
  não corresponde a um arquivo real é um erro real (404), nunca uma
  rota client-side disfarçada.
- **Nenhuma lógica de autenticação nova.** O blueprint só serve
  arquivo estático; a autenticação continua inteiramente do lado de
  `auth_bp`/do próprio painel (que já checa `/auth/me` antes de montar
  qualquer tela — implementado, não alterado aqui).
- **`config.js`/`runtime-config.js` continuam exatamente como estão**
  (`GOOGLE_OAUTH_CLIENT_ID: null`) — configuração real de produção do
  Google OAuth Client ID é **pendência declarada**, fora do escopo
  desta missão.

## 5. Próximo passo pendente — diff exato proposto para `app.py`

Mudança de **2 linhas funcionais** (import + `register_blueprint`,
mesmo padrão exato já usado para `auth_bp`/`secullum_bp`/`sync_bp`/
`ingestao_bp`/`esteira_bp`), com o mesmo estilo de comentário curto já
usado em cada um dos registros anteriores em `app.py`:

```diff
--- a/app.py
+++ b/app.py
@@ -88,6 +88,13 @@
 from magnata_os.documental.modulo01.adapters.blueprint_esteira import esteira_bp
 app.register_blueprint(esteira_bp)

+# ── Módulo 01 (Ingestão) — painel estático (frontend/), mesmo domínio ──────────
+# Wiring mínimo: só o registro. Toda lógica vive em
+# magnata_os/documental/modulo01/adapters/blueprint_painel_estatico.py --
+# nenhuma autenticação nova; só serve arquivo estático de frontend/.
+from magnata_os.documental.modulo01.adapters.blueprint_painel_estatico import painel_estatico_bp
+app.register_blueprint(painel_estatico_bp)
+
 # ── Módulo 01 (Ingestão) — Fase 0: observabilidade, sem efeito operacional ──────
 from src.observability import observar_ingestao
```

- **Blob hash de `app.py` ANTES desta mudança** (estado atual em
  `main`, confirmado por `git hash-object app.py` nesta sessão):
  `e4bd4e4cdf3db8e9029cca8ac66fa1417e3976be`
- **Blob hash de `app.py` SE esta mudança fosse aplicada** (calculado
  nesta sessão sobre uma cópia local em scratchpad, fora do
  repositório, descartada após o cálculo — nunca commitada):
  `03975a1643ceb7588363abedaa4ebb1417817800`

Esta mudança **não foi aplicada**. Ela aguarda:
1. autorização humana específica, confirmada numa mensagem distinta
   da que apresentou este diff (`/CLAUDE.md` §6(e)) — e, antes disso,
2. o manifesto de autorização em
   `.magnata/app-py-authorizations/*.gitblob` (mesmo padrão de
   `painel-fase5-backend-v1.gitblob`), que **não foi criado** nesta
   missão — só é criado depois da confirmação do usuário, fora desta
   missão.

## 6. Pendências declaradas (não resolvidas aqui)

- Configuração real do `GOOGLE_OAUTH_CLIENT_ID` de produção — fora de
  escopo, painel continua com `null` até decisão/execução separada.
- O registro do blueprint em `app.py` (seção 5 acima) — aguarda
  autorização humana específica numa mensagem distinta.
- Nenhuma validação foi feita contra um ambiente de produção real
  (Render ou outro) — este trabalho cobre só o blueprint, seus testes
  locais, e a proposta de wiring; o comportamento em produção real só
  pode ser confirmado depois do registro em `app.py` ser autorizado e
  aplicado, e de um deploy real (fora de escopo e de autonomia desta
  missão — `/CLAUDE.md` §6/§9).
