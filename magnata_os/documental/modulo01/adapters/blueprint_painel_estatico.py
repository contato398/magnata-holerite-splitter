"""Blueprint Flask que serve os arquivos ESTATICOS do painel operacional
(`frontend/`) sob o prefixo `/painel`.

Contexto: o painel (Fase 5, `frontend/src/`+`frontend/styles/`+
`frontend/index.html`, ja mesclado em `main`) so foi acessado
localmente (`python -m http.server --directory frontend`). Ele precisa
ser publicado de verdade, acessivel por qualquer dispositivo, no MESMO
dominio do backend -- `frontend/src/api/apiAdapter.js` ja chama
`/auth/me`, `/auth/login` e `/magnata-os/documental/...` com caminho
RELATIVO e a opcao `credentials` do `fetch` configurada para
same-origin (confirmado por leitura direta do arquivo), entao a sessao
de autenticacao (cookie) so funciona se o
painel for servido do mesmo dominio/origem do backend -- nunca um site
estatico separado. Ver docs/decisoes/painel-publicacao-estatico-mesmo-
dominio-v1.md para a decisao completa.

**Nenhuma logica de autenticacao nova aqui.** Este blueprint so serve
arquivo estatico (HTML/CSS/JS/SVG/PNG) de `frontend/` -- a autenticacao
continua inteiramente do lado de `auth_bp`/do proprio painel (que
checa `/auth/me` antes de montar qualquer tela, ja implementado, nao
alterado por esta missao). Servir um arquivo estatico sem sessao nao
expoe dado nenhum: o HTML/JS/CSS em si nao contem segredo (ver
`frontend/src/config.js`/`runtime-config.js`, `GOOGLE_OAUTH_CLIENT_ID:
null`, inalterados por esta missao -- configuracao real de producao e
pendencia declarada, fora de escopo).

Prefixo de rota escolhido: `/painel` -- curto, nao conflita com nenhum
prefixo ja registrado em app.py (`/auth`, `/secullum`, `/magnata-os/
documental`), e e o nome que o proprio usuario (dono do produto) usa
para se referir a esta tela.

SPA fallback: NAO implementado, de proposito. `frontend/src/nav.js`
(ROTAS) usa rotas client-side por HASH (`#/resumo`, `#/documentos`,
etc. -- confirmado por leitura direta do arquivo), que o navegador
nunca envia ao servidor; `app.js` troca de componente no mesmo
`index.html` sem nunca pedir uma URL de caminho novo ao servidor. Logo
nao ha rota profunda tipo `/painel/documentos` que precise cair em
`index.html` -- um caminho desconhecido sob `/painel/` e sempre um erro
real (arquivo que nao existe), nunca uma rota client-side disfarcada, e
por isso recebe 404 real, nunca `index.html`.

Seguranca: usa exclusivamente `flask.send_from_directory` (nunca
concatena path manualmente) -- e a propria funcao do Flask/Werkzeug que
rejeita tentativa de path traversal (`..`, path absoluto escapando do
diretorio base), levantando `NotFound` (404), nunca servindo arquivo
fora de `frontend/`. Testado explicitamente em
test_magnata_os_documental_modulo01_blueprint_painel_estatico.py.

Registrado em app.py com o MESMO padrao de 2 linhas (import +
`app.register_blueprint`) ja usado para auth_bp/secullum_bp/sync_bp/
ingestao_bp/esteira_bp -- essa mudanca em si NAO foi aplicada por esta
missao (app.py e legado protegido, `/CLAUDE.md` §7); o diff exato
proposto e o blob hash esperado estao documentados no ADR citado acima,
aguardando autorizacao humana especifica (`/CLAUDE.md` §6(e))."""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, send_from_directory

# Diretorio raiz do painel estatico: `frontend/`, irmao de `magnata_os/`
# na raiz do repositorio. Calculado a partir deste arquivo (nunca
# depende do diretorio de trabalho do processo) -- este arquivo vive em
# `magnata_os/documental/modulo01/adapters/`, 4 niveis abaixo da raiz
# do repositorio.
_RAIZ_REPOSITORIO = Path(__file__).resolve().parents[4]
DIRETORIO_FRONTEND = _RAIZ_REPOSITORIO / 'frontend'

painel_estatico_bp = Blueprint('magnata_os_painel_estatico', __name__, url_prefix='/painel')


@painel_estatico_bp.route('/', methods=['GET'])
def indice_painel():
    """Serve `frontend/index.html` na raiz do prefixo -- unico ponto de
    entrada do painel (SPA client-side, ver docstring do modulo)."""
    return send_from_directory(DIRETORIO_FRONTEND, 'index.html')


@painel_estatico_bp.route('/<path:caminho>', methods=['GET'])
def arquivo_estatico_painel(caminho: str):
    """Serve qualquer outro arquivo estatico de `frontend/` (src/, styles/,
    assets/, etc.) pelo MESMO caminho relativo usado em `index.html`
    (ver `<link>`/`<script src=...>` la, sempre relativo).

    `send_from_directory` resolve o Content-Type pela extensao e
    rejeita (404, `NotFound`) qualquer tentativa de escapar de
    `DIRETORIO_FRONTEND` -- nunca concatenamos path manualmente."""
    return send_from_directory(DIRETORIO_FRONTEND, caminho)
