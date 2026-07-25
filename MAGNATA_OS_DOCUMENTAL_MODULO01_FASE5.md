# Magnata OS Documental — Módulo 01, Fase 5 (Painel Visual)

**Status:** primeira interface visual profissional da esteira documental,
consumindo exclusivamente os contratos da API da Fase 4 via um adapter
mock local. **Não integrado ao fluxo legado.** `app.py` inalterado.
Nenhum acesso a PostgreSQL, S3, R2 ou Airtable reais — nenhuma conexão
HTTP real de nenhum tipo nesta fase.

## Objetivo

As Fases 1-4 construíram o domínio, a persistência, a esteira
operacional e a API de consulta. Esta fase constrói **a primeira tela**
que um humano de verdade vê — o painel operacional do Magnata OS,
usando a identidade visual oficial (Fase de identidade visual, já
incorporada à `main`) e falando com o mundo exclusivamente através dos
contratos definidos em `magnata_os/documental/modulo01/api/contratos.py`
(Fase 4), espelhados fielmente em JavaScript.

## Tecnologia escolhida

**HTML + CSS + JavaScript puro (módulos ES nativos, sem framework, sem
bundler, sem `package.json`).**

### Motivo da escolha

Antes de escolher qualquer tecnologia, o repositório foi inspecionado:

1. **Não existe frontend nenhum ainda.** `git grep`/busca de arquivos
   confirmou: nenhum `package.json`, nenhum `node_modules`, nenhum
   `templates/` do Flask, nenhuma pasta de frontend anterior a
   `frontend/assets/brand/` (só os assets de marca, sem nenhum código).
   `app.py` (`Flask(__name__)`) não usa `render_template` em nenhum
   lugar — o único uso de `static_folder` é servir um PDF avulso, não
   uma aplicação web. **Não existe padrão de interface a seguir nem a
   quebrar.**
2. **Não há Node.js/npm/npx instalados neste ambiente** (confirmado
   diretamente: `node`, `npm`, `npx` — nenhum dos três existe no PATH).
   Isso descarta, na prática, qualquer stack que dependa de build step
   (React/Vue/Angular + Vite/Webpack/CRA) — não seria possível instalar
   dependências, rodar o dev server, nem verificar que o build
   funciona, dentro desta sessão de trabalho.
3. **O pedido explicitamente exige** "a solução mais simples, moderna e
   isolada", proíbe "forçar integração com `app.py`" e proíbe "usar
   frameworks pesados sem justificativa" — um framework SPA completo
   seria dois desses três "não" ao mesmo tempo, sem trazer nenhum
   ganho real: o painel não precisa de roteamento complexo, SSR, nem
   gerenciamento de estado sofisticado para o volume de dados de uma
   esteira documental (dezenas/centenas de itens, não milhares).
4. **JavaScript moderno nativo (módulos ES2020+, `fetch`, CSS
   Grid/Flexbox/custom properties, `Intl.DateTimeFormat`) já cobre tudo
   que esta fase precisa** — componentes são só funções que devolvem
   `Node`s reais (`utils/dom.js`, um "hyperscript" de ~60 linhas),
   estado é um pub-sub de ~25 linhas (`state/store.js`), e não há
   nenhuma dependência externa para instalar, atualizar ou auditar.

**Consequência prática:** o painel roda em qualquer servidor de
arquivos estático (`python -m http.server`, Nginx, o próprio GitHub
Pages) — nenhum passo de build, nenhuma dependência de versão de Node.
Isolado de verdade: nada em `frontend/` importa `flask`, `app.py`, nem
qualquer módulo Python — confirmado automaticamente por
`tests/legado.test.js` (ver "Testes").

## Arquitetura

```
frontend/
├── index.html                  # shell da pagina, favicon = simbolo da marca
├── assets/brand/                # identidade visual (fase anterior -- inalterada)
├── styles/
│   ├── tokens.css                # cores institucionais + neutros + espacamento/forma
│   ├── base.css                  # reset + shell responsivo (sidebar/header/main)
│   └── components.css            # estilos de cada componente
├── src/
│   ├── app.js                    # bootstrap + roteador hash, sem biblioteca de rotas
│   ├── nav.js                    # unica fonte de verdade da navegacao (5 telas)
│   ├── api/
│   │   ├── contracts.js          # espelho fiel de contratos.py + dominio_esteira.py
│   │   ├── autorizacao.js        # espelho de autorizacao.py
│   │   ├── errors.js             # espelho de erros.py -- ApiError + tratarErroParaResposta
│   │   └── mockAdapter.js        # implementa os 9 "endpoints" contra mockData.js
│   ├── state/
│   │   ├── store.js               # pub-sub minimo (getState/setState/subscribe)
│   │   └── filtros.js             # validacao + aplicacao pura de filtro/ordenacao/paginacao
│   ├── data/mockData.js           # documentos/lotes/historico ficticios, ja no formato da API
│   ├── utils/                     # format, dom (hyperscript), icons, prioridade, responsive, debounce
│   ├── components/                # Sidebar, Header, ResumoCards, EsteiraBoard/Coluna, DocumentoCard,
│   │                               # Filtros, Paginacao, PainelDetalheDocumento/Lote, EstadosUI
│   └── views/                     # DashboardView, DocumentosView, BloqueiosView,
│                                   # AcoesHumanasView, ParadosView, viewHelpers
└── tests/                         # harness proprio + 10 suites (ver "Testes")
```

Mapeamento direto para os itens pedidos: **componentes** =
`src/components/`; **páginas** = `src/views/`; **serviços de
consulta** = `src/api/` (contrato + mock); **tipos/contratos** =
`src/api/contracts.js`; **estado** = `src/state/store.js`; **filtros**
= `src/state/filtros.js`; **tratamento de erros** = `src/api/errors.js`
+ `src/views/viewHelpers.js`; **dados mockados** = `src/data/mockData.js`;
**testes** = `frontend/tests/`.

### Por que um "adapter mock" e não dados soltos

`mockAdapter.js` implementa a **mesma assinatura de método, a mesma
validação de filtro/paginação/ordenação, e a mesma política de
permissão** que os handlers Python da Fase 4 (`handlers.py`) — a única
diferença é que lê de `data/mockData.js` (arrays em memória) em vez de
um banco real. Toda view (`src/views/*.js`) só conhece a interface
`apiClient.<metodo>(sujeito, opções)` — trocar `mockAdapter.js` por um
`client.js` real (fetch contra a API HTTP futura) é a única mudança
necessária para conectar o painel a dados de verdade; nenhum
componente, view ou teste de UI precisa mudar.

## Componentes

| Componente | Responsabilidade |
|---|---|
| `Sidebar` / `NavMobile` | Menu lateral (desktop) e barra de navegação horizontal (celular) — símbolo da marca, 5 telas |
| `Header` | Identidade (logo horizontal + "Magnata OS" / "Central Documental"), perfil atual (mock), botão atualizar, selo de última atualização |
| `ResumoCards` | Os 9 cartões operacionais (item 3) |
| `EsteiraBoard` / `EsteiraColuna` | As 10 colunas da esteira (item 4), com troca de layout responsiva |
| `DocumentoCard` | Cartão de documento (item 5), em dois layouts (`coluna`/`linha`) |
| `Filtros` | Barra de filtros completa (item 6) |
| `Paginacao` | Controles de paginação, reaproveitados por toda lista |
| `PainelDetalheDocumento` | Painel sobreposto com todos os campos do documento + histórico resumido (item 7) |
| `PainelDetalheLote` | Painel sobreposto com os dados do lote + documentos daquele lote (item 7) |
| `EstadosUI` | Os 8 estados de interface do item 8 (carregando, vazio, nenhuma ocorrência, erro, serviço indisponível, sem permissão, faixa de dados parciais, selo de atualização recente) |

## Telas (`src/views/`)

- **Resumo** (`DashboardView`) — home: `ResumoCards` + `EsteiraBoard` completo.
- **Documentos** (`DocumentosView`) — busca, todos os filtros, lista paginada.
- **Bloqueios** (`BloqueiosView`) — fila de documentos bloqueados, ordenada pelos mais antigos.
- **Ações humanas** (`AcoesHumanasView`) — fila de documentos com `proxima_acao.tipo === 'HUMANA'`.
- **Parados** (`ParadosView`) — documentos acima de um tempo mínimo configurável na etapa atual.

Todas as 5 telas abrem `PainelDetalheDocumento` ao clicar num cartão, e
esse painel abre `PainelDetalheLote` ao clicar no lote — nenhuma tela
duplica essa lógica; ela vive uma vez em cada view, seguindo o mesmo
padrão.

## Fluxo de dados

```
usuário interage (clique, filtro, paginação, troca de perfil)
        │
        ▼
   view (src/views/*.js) monta estado local (filtro/paginação/ordenação)
        │
        ▼
   apiClient.<metodo>(sujeito, opções)   -- state/filtros.js valida antes
        │                                   de qualquer chamada
        ▼
   mockAdapter.js: exigirPerfil() → valida filtro/paginação/ordenação →
   aplica filtro/ordenação/paginação puros sobre data/mockData.js →
   devolve exatamente a forma de contracts.js
        │
        ▼
   view recebe o resultado (ou um ApiError) e re-renderiza o container
   via utils/dom.js `mount()` -- nenhum diffing, o container inteiro é
   reconstruído a cada mudança (aceitável no volume de dados desta fase)
```

Nenhuma view importa `data/mockData.js` diretamente — sempre passa por
`apiClient`, mantendo a fronteira que permite trocar o adapter no
futuro sem tocar em nenhuma tela.

## Uso da identidade visual

- **Símbolo** (`assets/brand/magnata-symbol.svg`) — favicon (`index.html`)
  e topo do menu lateral (`Sidebar.js`).
- **Versão horizontal** (`assets/brand/magnata-logo-horizontal.svg`) —
  cabeçalho, em telas ≥ 640px; abaixo disso, o cabeçalho troca para o
  símbolo isolado (a lockup horizontal fica larga demais para uma tela
  de celular) — troca feita só por CSS (`@media`), o `Header.js`
  renderiza os dois e o CSS decide qual mostrar.
- **"Magnata OS" / "Central Documental"** — texto tipografado ao lado
  da marca no cabeçalho (`.produto-nome` / `.produto-subtitulo`),
  deliberadamente separado do lockup "GRUPO MAGNATA" da marca (ver
  `MAGNATA_OS_IDENTIDADE_VISUAL.md`, seção "Composição do lockup
  horizontal" — o nome do produto não é a marca da empresa, os dois
  convivem lado a lado).
- **Marinho institucional** (`--cor-marinho: #041b36`) — sidebar,
  cabeçalho, títulos de seção, texto de ênfase alta.
- **Dourado institucional** (`--cor-dourado: #fdc82a`) — usado **com
  moderação**, só em: item ativo do menu, botão "Atualizar", indicador
  de "ação humana", borda de destaque nos cartões de resumo de
  bloqueados/ação-humana/erro — nunca como cor de fundo de área grande.
- **Fundos neutros** — `--cor-fundo`/`--cor-superficie` são cinza
  muito claro/branco, cores propostas para esta fase (não fazem parte
  da marca — ver `MAGNATA_OS_IDENTIDADE_VISUAL.md`).
- **Nenhum arquivo em `assets/brand/` foi alterado** nesta fase —
  `tests/components.test.js` confere programaticamente que todo `<img>`
  de marca aponta para dentro de `assets/brand/`.

## Responsividade

Três comportamentos deliberadamente diferentes, não um único layout
"encolhido":

- **Desktop/notebook (≥ 1024px):** sidebar expandida com rótulos,
  esteira em 10 colunas kanban roláveis horizontalmente, grade de
  resumo em 5 colunas.
- **Tablet (768–1023px):** mesmo shell (sidebar + kanban), grade de
  resumo em 3 colunas.
- **Celular (< 768px):** sidebar desaparece, vira uma **barra de
  navegação horizontal rolável** no topo (`NavMobile`) — nunca some a
  navegação. A esteira **não comprime as 10 colunas** — troca para uma
  **lista única com um seletor de etapa** (`<select>` + lista de
  cartões em layout `linha`), decisão pura e testada isoladamente em
  `utils/responsive.js`/`tests/responsive.test.js`, verificada de
  verdade num viewport 375×812 via automação de navegador (ver
  "Testes").

## O que esta fase explicitamente NÃO faz

Autenticação real (o seletor de perfil no cabeçalho é só um mock
visual — ver `autorizacao.js`); alteração de documentos; resolução real
de bloqueios; upload real; OCR; IA; fatiamento; envio por e-mail;
envio por WhatsApp; conexão HTTP real de qualquer tipo (todo dado vem
de `data/mockData.js`); deploy.

## Testes

```bash
# servir a pasta frontend/ com qualquer servidor estatico, por exemplo:
python -m http.server 8934 --directory frontend
# depois abrir http://localhost:8934/tests/ no navegador
```

Harness próprio, sem dependência (`tests/test-harness.js` —
`describe`/`it`/`assert*`, ~120 linhas), porque não há Node.js
disponível para Jest/Vitest/Mocha neste ambiente. `tests/index.html`
carrega as 10 suítes e renderiza o resultado na própria página (✅/❌
por teste), verificável tanto a olho quanto por automação de
navegador.

**124 testes, 0 falhas**, distribuídos em 10 arquivos, cobrindo todos
os 17 cenários pedidos:

| Arquivo | Cenários cobertos |
|---|---|
| `format.test.js` | Rótulos PT-BR, tempo relativo, duração, truncamento de nome |
| `contracts.test.js` | **Compatibilidade com os contratos da API** — enums e política de permissão idênticos à Fase 4 |
| `errors.test.js` | **Erro** / **sem permissão** — códigos de `ApiError`, nenhuma mensagem técnica vaza |
| `filtros.test.js` | **Filtros** / **busca** — validação, aplicação, ordenação segura, paginação, conversão UI→contrato |
| `prioridade.test.js` | Regra de documento prioritário |
| `responsive.test.js` | **Responsividade básica** — decisão pura kanban/lista por largura |
| `store.test.js` | Store pub-sub |
| `mockAdapter.test.js` | Os 9 endpoints — **bloqueios**, **ações humanas**, **vazio**, **erro** (falha simulada), **sem permissão** por perfil |
| `components.test.js` | **Renderização do resumo**, **identidade visual**, **colunas da esteira**, **cartões**, **filtros** (DOM), **detalhe do documento**, **detalhe do lote**, **carregando**, **vazio**, **erro**, **sem permissão** |
| `legado.test.js` | **Ausência de dependência do legado** — lê o próprio código-fonte via `fetch` e confere que nenhum arquivo menciona Flask/`app.py`, nem tem acoplamento real com Airtable (URL da API ou IDs de base/tabela/campo/registro como literal), nem chama `fetch()`/`XMLHttpRequest` contra qualquer coisa (só o próprio teste de legado usa `fetch`, para ler o código) |

Verificação funcional adicional (não persistida como teste automatizado,
feita por automação de navegador durante o desenvolvimento): abertura
do painel real (`index.html`) servido por HTTP, navegação entre as 5
telas, abertura do painel de detalhe de documento e de lote, aplicação
de filtros e busca, alternância de perfil com bloqueio de acesso
correto, simulação de falha de infraestrutura (estado "serviço
indisponível") e redimensionamento para 375×812 confirmando a troca
kanban→lista da esteira. Um bug real foi encontrado e corrigido nessa
verificação: `exigirPerfil` levantava um `Error` genérico em vez de um
`PermissaoNegada` de verdade, fazendo `mockAdapter.js` mascarar toda
negação de permissão como "serviço indisponível" — corrigido movendo
`exigirPerfil`/`Perfil`/`PERMISSAO_*` para `api/autorizacao.js`
(import de `PermissaoNegada` sem criar dependência circular com
`contracts.js`).

## Limitações

- **Sem persistência de estado entre recarregamentos** — perfil
  selecionado e rota atual não sobrevivem a um F5 (voltam ao padrão:
  perfil Gestor, tela Resumo). Aceitável para uma fase sem autenticação
  real; uma fase futura com login de verdade resolveria isso junto.
- **Re-render completo do shell a cada mudança de estado global** —
  `renderShell()` reconstrói sidebar/header inteiros a cada
  `store.setState()` (inclusive o intervalo de 30s que atualiza "há
  quanto tempo" no cabeçalho), o que reemite requisições `GET` para os
  SVGs de marca repetidamente (confirmado via inspeção de rede durante
  o desenvolvimento) — sem impacto perceptível no volume desta fase
  (arquivos pequenos, cache do navegador), mas seria a primeira coisa a
  otimizar (diffing seletivo, ou só re-renderizar o que mudou) se o
  painel crescer.
- **`EsteiraBoard` busca até 200 documentos de uma vez** para montar o
  quadro completo — funciona bem para o volume mockado; com milhares de
  documentos reais, precisaria de uma consulta agregada por etapa
  (contagem + top-N) em vez de carregar tudo.
- **Filtros de origem/lote são populados a partir da página de dados já
  carregada** (`DocumentosView`), não de uma lista canônica de valores
  possíveis — com poucos itens por página, o dropdown pode não mostrar
  toda origem/lote existente até o usuário navegar mais páginas.

## Próximos passos

1. Construir `api/client.js` (fetch real contra a API HTTP da Fase 4,
   quando ela for exposta por um framework web) implementando a MESMA
   interface de `mockAdapter.js` — nenhuma view muda.
2. Autenticação real, substituindo o seletor de perfil mock por sessão
   de verdade.
3. Ações reais (resolver bloqueio, reprocessar documento) — hoje o
   painel é só leitura, por decisão explícita desta fase.
4. Otimizar o re-render do shell (evitar refetch de assets de marca a
   cada atualização do relógio do cabeçalho).
5. Consultas agregadas por etapa para a esteira suportar volume real de
   produção sem carregar todos os documentos de uma vez.
