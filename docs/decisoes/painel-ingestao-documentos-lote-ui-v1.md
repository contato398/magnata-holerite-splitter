# Painel Operacional — Ingestão de Documentos em Lote via UI, V1

## Objetivo

Decisão de produto já tomada desde o início da automação, reafirmada
explicitamente pelo dono do produto: **nunca precisar entrar no Shell
do Render ou digitar comando de terminal para operar o sistema**. O
PR #221 (`fix/ingestao-documentos-lote-real-v1`) construiu a lógica
real de ingestão em lote (Airtable → S3/R2 + Postgres) como CLI manual
(`scripts/ingerir_documentos_lote_real_cli.py`) — rápido para provar
que a lógica funciona, mas não a interface definitiva. Esta missão
expõe a MESMA lógica por um clique no painel operacional (Fase 5),
sem duplicar nada do núcleo de ingestão.

## Dependência declarada do PR #221

Esta branch (`fix/painel-ingestao-documentos-lote-ui-v1`) foi criada a
partir de `fix/ingestao-documentos-lote-real-v1` (PR #221), que ainda
não estava mesclado em `main` no momento em que esta missão começou —
instrução explícita do pedido. Todo o núcleo reaproveitado
(`magnata_os/documental/importacao_lote/ingestao_documentos_lote_real.py`,
`ingerir_documentos_lote`, `parse_competencia`, `CompetenciaInvalida`,
`ResumoIngestaoLote`) vem desse PR, sem alteração de conteúdo. **O PR
desta missão deve ser mesclado só depois (ou em conjunto, explicitado
no próprio PR) do PR #221** — se #221 mudar de forma incompatível
antes de ambos mesclarem, esta camada HTTP precisa ser revisada contra
a versão final.

## O que foi exposto

### Backend

- **`magnata_os/documental/importacao_lote/servico_ingestao_lote_http.py`**
  (novo) — fronteira HTTP/autorização da ingestão: valida perfil
  (`PERMISSAO_INGESTAO_LOTE = {OPERACIONAL, GESTOR}` — AUDITOR de fora
  de propósito, é ação de escrita, não consulta), valida `cliente`/
  `competencia`, compõe as dependências REAIS do ambiente (Airtable
  somente leitura + S3/R2 + Postgres) e chama `ingerir_documentos_lote`
  (núcleo do PR #221, sem alteração), devolvendo
  `ResumoIngestaoLote.como_dict()`. **Decisão de design**: a composição
  de dependências é feita de novo aqui (`compor_dependencias_ingestao_lote_a_partir_do_ambiente`),
  **não** reaproveitando `magnata_os.orquestrador.composicao_prestacao_real_v1.compor_dependencias_a_partir_do_ambiente`
  (o que o CLI do PR #221 usa) — `magnata_os/documental/` nunca pode
  importar `magnata_os.orquestrador` (regra de dependência acíclica já
  verificada em
  `tests/test_magnata_os_arquitetura_dependencias_aciclicas.py`:
  orquestrador coordena/compõe sobre documental, nunca o contrário;
  este módulo é parte de `documental/`). A composição duplicada usa as
  MESMAS variáveis de ambiente e os MESMOS adapters concretos
  (`LeitorAirtableSomenteLeitura`, `abrir_conexao`,
  `ArmazenamentoArquivosS3`) — nenhum provedor novo. Custo aceito e
  registrado (mesma disciplina já documentada em
  `importacao_lote/CLAUDE.md` para outras duplicações): os dois
  compositores precisam ser mantidos em sincronia manualmente se o
  ambiente mudar. Toda dependência de composição é injetável — nenhum
  teste deste módulo toca Airtable/S3/Postgres real
  (`test_servico_ingestao_lote_http.py`).
- **`magnata_os/documental/modulo01/adapters/blueprint_esteira.py`**
  (rota nova) — `POST /magnata-os/documental/ingestao-lote`, no MESMO
  blueprint já registrado em `app.py` (Fase 5, "dados reais") — decisão
  deliberada: um blueprint dedicado novo exigiria registrá-lo em
  `app.py`, arquivo legado protegido (`/CLAUDE.md` §7) que só pode ser
  alterado em branch própria, dedicada só a isso, com autorização
  explícita; reaproveitar `esteira_bp` (já registrado) evita precisar
  tocar `app.py` nesta missão. Protegida por
  `exigir_sessao_com_perfil` (MESMO mecanismo dos outros 9 endpoints,
  nenhuma autenticação nova) **e** por `exigir_csrf` — primeira rota de
  ESCRITA deste blueprint, por isso a primeira a usar esse decorator
  (já existia em `blueprint_login.py`, nunca antes aplicado a uma rota
  de domínio; GET continua sem CSRF, convenção padrão). Corpo:
  `{"cliente": "<id do registro Airtable>", "competencia": "AAAA-MM"}`.
- Resposta: exatamente `ResumoIngestaoLote.como_dict()` — contagens,
  ids de registro Airtable e hash (quando presente no núcleo), **nunca**
  CPF/nome (mesma garantia já documentada no núcleo e no CLI do PR
  #221; testado explicitamente em
  `test_servico_ingestao_lote_http.py::test_resposta_nunca_contem_dado_pessoal`
  e em `test_magnata_os_documental_modulo01_blueprint_esteira.py`).

### Frontend

- **`frontend/src/views/IngestaoLoteView.js`** (nova tela) — formulário
  (campo texto para `cliente`, `<input type="month">` para
  `competencia` — já devolve `AAAA-MM`, sem conversão manual) + botão
  "Ingerir documentos". Ao clicar: mostra indicador de carregamento
  (`estadoCarregando`, botão desabilitado e `aria-busy`), chama
  `apiClient.ingerirDocumentosLote`, e mostra o resumo em cartões
  (reaproveita o mesmo estilo visual de `ResumoCards.js`), nunca JSON
  cru. Erro (permissão, sessão expirada, CSRF, rede) passa por
  `renderErroApi` (mesmo helper já usado pelas outras telas) — nunca
  falha silenciosa.
- **`frontend/src/api/apiAdapter.js`** — `ingerirDocumentosLote` (POST
  real) + `requisitarPost` (helper nova, só para escrita): busca um
  token CSRF fresco via `GET /auth/me` antes de cada chamada (MESMO
  token que o login já devolve, nenhum mecanismo de CSRF novo) e o
  envia no header `X-CSRF-Token`. `FalhaSegurancaRequisicao` (erro novo,
  mesma forma de `AutenticacaoAusente`/`ErroLogin`, não um `ApiError`
  do contrato Python) cobre `{erro: "csrf_invalido"}`.
- **`frontend/src/api/mockAdapter.js`** — `ingerirDocumentosLote`
  simulado (modo `?mock=1`, demonstração local), para o botão nunca
  ficar morto nesse modo; nunca é o caminho usado contra dado real.
- **`frontend/src/nav.js`/`app.js`** — rota `#/ingestao-lote` nova, no
  mesmo padrão das demais (link na Sidebar/nav mobile, entrada em
  `VIEWS`).

## Limitações declaradas (V1)

- **Síncrono e bloqueante.** A requisição HTTP só responde quando TODOS
  os documentos do cliente+competência tiverem sido processados —
  igual ao CLI original, só que por HTTP. Para um lote grande, a aba
  do navegador fica esperando minutos nessa única requisição. Aceito
  para V1 (nenhum worker assíncrono/fila foi construído); risco
  registrado, não escondido. Mitigação futura possível: endpoint
  assíncrono (202 + polling/job id) — fora de escopo desta missão.
- **Seletor de cliente ainda é texto livre do id do registro Airtable**
  (`recXXXXXXXXXXXXXX`), não um seletor com nome do cliente. Melhoria
  futura explicitamente não bloqueante para esta entrega (mesmo
  raciocínio de "o que não entra" já usado em
  `docs/decisoes/ingestao-documento-lote-real-v1.md`).
- **Nenhuma alteração em `app.py`.** A rota nova entra no blueprint já
  registrado (`esteira_bp`); nenhuma linha de `app.py` foi tocada nesta
  missão.
- **Nenhuma migration, nenhum schema novo.** Reaproveita 100% dos
  repositórios/contratos já existentes.
- **Depende do PR #221 ainda não mesclado** (ver seção acima) — núcleo
  de ingestão em si não foi alterado nem revisado de novo aqui.

## Governança

- `.magnata/patterns.sh` (`ALLOWED_PATHS`) ganhou entradas exatas para
  `servico_ingestao_lote_http.py`, seu teste nominal
  (`test_servico_ingestao_lote_http.py`) e este documento.
  `blueprint_esteira.py` e seu teste
  (`test_magnata_os_documental_modulo01_blueprint_esteira.py`) já
  estavam liberados (missão anterior, "dados reais") — a rota nova
  entra nesse caminho já autorizado, sem precisar de entrada nova.
  `frontend/src/`/`frontend/tests/` já estavam liberados como
  prefixo (missão anterior, "frontend Fase 5") — os arquivos novos de
  frontend desta missão também não precisam de entrada nova.
- Nenhuma ação externa real (Airtable, S3/R2, Postgres, e-mail,
  WhatsApp, deploy) foi executada como parte desta missão — todo teste
  injeta dependências em memória/fakes.
- `app.py` permanece intocado.

## Resultado dos testes

- `test_servico_ingestao_lote_http.py`: 9/9 — permissão (GESTOR/
  OPERACIONAL podem, AUDITOR não pode e o núcleo nunca é chamado),
  parâmetros inválidos (cliente ausente, competência fora de
  AAAA-MM), ausência de configuração de ambiente (503, nunca finge
  sucesso), parâmetros corretos passados ao núcleo, resposta com
  falhas parciais preservada, nenhum dado pessoal na resposta.
- `test_magnata_os_documental_modulo01_blueprint_esteira.py`: 16/16
  (7 novos para a rota `/ingestao-lote` — sem sessão 401, sem CSRF 403,
  com sessão+CSRF 200 chamando o núcleo corretamente, erro de parâmetro
  propagado, perfil AUDITOR 403).
- Suíte Python completa (`python -m pytest -q`): ver resultado no PR —
  nenhuma regressão.
- Suíte de testes do frontend (`frontend/tests/index.html` via
  Playwright headless, mesmo padrão já usado nas missões anteriores do
  painel): 158/158 passando, incluindo os novos
  `ingestaoLoteView.test.js` e os casos novos em `apiAdapter.test.js`/
  `mockAdapter.test.js`.

🤖 Generated with [Claude Code](https://claude.ai/code/session_01WPVZTgsag3f25pYNVdsEnK)
