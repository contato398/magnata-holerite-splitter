# ADR — Magnata OS App Shell: manifesto PWA sobre o painel existente (V1)

- **Branch:** `fix/magnata-os-app-shell-manifest-pwa-v1`
- **Data:** 2026-10-03
- **Status:** implementado e testado; nenhuma alteração em `app.py`
  necessária (blueprint `painel_estatico_bp`, já registrado, serve
  qualquer arquivo novo em `frontend/` pelo mesmo mecanismo).

## 1. O que "App Shell" significa aqui

O pedido (item 9 da atualização de estado do Magnata, 2026-10-03) não
detalhou o termo — só disse "Magnata OS App Shell", "reutilizar o
frontend existente" e "não criar um segundo frontend". Não há nenhuma
especificação anterior de "App Shell" no repositório nem nos documentos
de `/mnt/project-files/magnata-os/`.

**Decisão registrada (default escolhido, não uma especificação
confirmada pelo Magnata):** interpretar "App Shell" no sentido técnico
padrão do termo — o invólucro persistente (navegação, cabeçalho, estado
de sessão, roteamento) que já existe em `frontend/src/app.js` (monta
`#app-shell` com sidebar/header/nav mobile/slot de conteúdo, troca só a
view interna por rota) — e torná-lo **instalável** (PWA: manifesto web,
ícone, cor de tema), que é a lacuna concreta e sem ambiguidade que dá
para fechar sem inventar escopo de produto novo. Não foi criada
nenhuma segunda aplicação, nenhum roteador novo, nenhuma duplicação do
shell já existente em `app.js`/`Sidebar.js`/`Header.js`.

Isto **não** resolve a pergunta maior "o App Shell deve deixar de ser
escopado só ao Módulo 01 (Documental) e virar o shell de toda a
plataforma (Ponto, Admissão, Assinatura, Distribuição)?" — ver §4.

## 2. O que já existia (mapeado, não um achado novo)

- `frontend/` é a única implementação de frontend do produto — SPA
  Vanilla JS sem framework/bundler, já servida em produção em
  `/painel/` pelo blueprint
  `magnata_os/documental/modulo01/adapters/blueprint_painel_estatico.py`
  (registrado em `app.py`, commit `8a28d9d`, autorização em
  `.magnata/app-py-authorizations/painel-publicacao-estatico-mesmo-dominio-v1.gitblob`).
- `frontend/src/app.js` já implementa o padrão de app shell: monta um
  contêiner fixo (`#app-shell` com `#slot-sidebar`/`#slot-header`/
  `#slot-nav-mobile`/`#app-main`) uma vez, e troca só a view do meio por
  rota hash (`nav.js`), sem recarregar a página — exatamente a mecânica
  que um "app shell" propõe.
- As 6 rotas atuais (`resumo`, `documentos`, `bloqueios`,
  `acoes-humanas`, `parados`, `ingestao-lote`) são todas do Módulo 01
  (Documental) — o texto fixo "Central Documental" aparece no
  `<title>`, no `Header.js` e no rodapé do `Sidebar.js`.
- Não havia `manifest.json`/`manifest.webmanifest`, nem
  `<meta name="theme-color">`, nem `apple-touch-icon` — o painel abria
  como aba de navegador comum, sem opção de "instalar"/"adicionar à
  tela inicial" em celular/tablet (o caso de uso que o próprio Magnata
  pediu no ADR anterior, `painel-publicacao-estatico-mesmo-dominio-v1.md`).
  Não havia service worker (nenhum cache offline) — fora de escopo
  desta missão (ver §3).

## 2.1. Achado incidental (documentado, não corrigido aqui)

O ADR `docs/decisoes/painel-publicacao-estatico-mesmo-dominio-v1.md`
(seção 5) descreve o registro do blueprint em `app.py` como "não
aplicado, aguardando autorização". Isso está **desatualizado**: o
registro já foi aplicado e mesclado (commit `8a28d9d`,
2026-10-03T02:49:17Z), com manifesto de autorização presente em
`.magnata/app-py-authorizations/`. Não é uma divergência de
arquitetura — é um documento histórico que não foi atualizado depois
do merge. Registrado aqui por `/CLAUDE.md` §2 ("nenhuma decisão
arquitetural é tomada em silêncio"); correção do ADR antigo é tarefa
separada, de menor risco, não incluída neste PR para não misturar
objetivos.

## 3. O que foi implementado nesta missão

- `frontend/manifest.webmanifest` — manifesto web padrão:
  `start_url`/`scope` = `/painel/` (onde o painel já é servido),
  `display: standalone`, cores institucionais já em uso
  (`--cor-marinho #041b36` / `--cor-fundo #f6f7f9`, de
  `frontend/styles/tokens.css`), ícones apontando para
  `assets/brand/magnata-symbol.png` (3220×3220, já existente) e
  `assets/brand/magnata-symbol.svg` — **nenhum asset de marca foi
  criado, editado, redesenhado ou recomprimido**, só referenciado pelo
  caminho que já existe.
- `frontend/index.html` — 3 linhas novas no `<head>`: `<link
  rel="manifest">`, `<link rel="apple-touch-icon">`,
  `<meta name="theme-color">`. Nenhuma mudança de comportamento da SPA
  em si.
- `test_magnata_os_documental_modulo01_blueprint_painel_estatico.py` —
  4 testes novos (mesmo padrão dos 6 já existentes, mesmo app de teste
  isolado, nunca o `app` real): manifesto servido com
  `Content-Type: application/manifest+json`, JSON válido, todo ícone
  referenciado existe de verdade em `frontend/` (nunca um ícone
  quebrado na instalação), e `index.html` referencia o manifesto e
  define `theme-color`. 10/10 testes passam.
- **Nenhuma linha de `app.py` alterada** — o blueprint já registrado
  serve `manifest.webmanifest` pelo mesmo mecanismo genérico
  (`send_from_directory` + `mimetypes`, que já reconhece
  `.webmanifest` → `application/manifest+json` na versão de Python do
  CI/produção, confirmado por teste).
- Nenhuma mudança em `frontend/assets/brand/` nem em `frontend/CLAUDE.md`
  (gate `protected_frontend` da governança roda verde).

## 4. O que não entra / pendência declarada para decisão humana

- **Escopo do shell além do Módulo 01.** Generalizar o título/rótulos
  (hoje "Central Documental") e a lista de rotas (`nav.js`) para
  incluir os módulos futuros (Ponto, Admissão, Assinatura,
  Distribuição) como o manifesto fundacional descreve é uma decisão de
  produto/arquitetura maior, não uma dedução segura de uma frase de uma
  linha ("App Shell"). Não decidido/implementado aqui — fica como gap
  explícito para o Magnata confirmar antes de qualquer PR que mexa em
  `nav.js`/títulos.
- **Service worker / cache offline** — parte comum do padrão "app
  shell" em contextos PWA, mas implica política de cache e
  invalidação (risco de servir versão velha do painel após deploy).
  Não implementado nesta missão; proponho como item separado, só
  depois de decidida a estratégia de invalidação de cache por deploy.
- **Ícones gerados em tamanhos fixos (192×192/512×512 PNG dedicados)**
  não foram criados — usei o PNG de marca já existente (3220×3220,
  escalável pelo navegador) para não "recomprimir/redesenhar" um asset
  de `assets/brand/` sem autorização (`/CLAUDE.md` §7). Gerar PNGs
  derivados em tamanho fixo, se desejado, é uma ação separada e exige
  a mesma autorização de ativo de marca.
- Nenhuma validação em produção real foi feita (depende de deploy, que
  é da Frente A/E).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
