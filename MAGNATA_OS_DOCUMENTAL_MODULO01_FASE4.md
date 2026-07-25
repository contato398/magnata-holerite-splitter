# Magnata OS Documental — Módulo 01, Fase 4 (API de Consulta da Esteira)

**Status:** camada de aplicação/API de consulta, desacoplada do legado.
**Não integrado ao fluxo legado.** `app.py` inalterado. Nenhum acesso a
banco, S3 ou Airtable reais nesta fase — todos os handlers são testados
contra repositórios em memória, chamados diretamente como funções
Python (sem servidor HTTP real).

## Objetivo

As Fases 1-3 construíram o domínio, a persistência e a esteira
operacional. Esta fase constrói **a API que vai servir o futuro painel
visual do Magnata OS** — uma camada de consulta que responde, para
qualquer documento ou para a esteira como um todo: o que chegou, onde
cada documento está, o que está parado, por que parou, quem precisa
agir, qual é a próxima ação. Nenhuma tela é construída aqui — só os
handlers/contratos que uma tela (ou qualquer outro cliente HTTP) vai
consumir.

## Princípio: desacoplada do legado, desacoplada de framework

Nada em `magnata_os/documental/modulo01/api/` importa `flask`, `app`,
nem qualquer estrutura interna de repositório além dos Protocols já
definidos nas fases anteriores (`RepositorioDocumentos`,
`RepositorioHistorico`, `RepositorioLotes`, `RepositorioEstadosEsteira`).
Os handlers (`handlers.py`) são funções Python puras do ponto de vista
de I/O externo: recebem um `ContextoApi` (repositórios), um `Sujeito`
(perfil de quem chama) e parâmetros simples (filtros, paginação,
ordenação — todos tipos de `filtros.py`), e devolvem sempre um contrato
estável de `contratos.py` — nunca uma entidade de domínio
(`Documento`, `EstadoEsteiraDocumento`, ...) nem um DTO interno
(`ItemEsteiraDocumento` da Fase 3) diretamente. **Um adapter web futuro
(fora do escopo desta fase) é quem conecta HTTP a estes handlers** —
traduzindo query string/JSON de entrada para os tipos de `filtros.py` e
a resposta dos handlers para JSON via `serializacao.para_json()`.

## Arquitetura

```
magnata_os/documental/modulo01/
├── dominio.py / repositorio.py / servico_entrada.py           # Fase 1 — inalterados
├── armazenamento.py / servico_entrada_persistente.py / adapters/  # Fase 2 — inalterados
├── dominio_esteira.py / repositorio_esteira.py / dtos_esteira.py
├── servico_avanco_esteira.py / servico_lote.py / consultas_esteira.py  # Fase 3 — inalterados
└── api/                            # NOVO (Fase 4)
    ├── contratos.py                 # Response DTOs estáveis, JSON-primitivos
    ├── erros.py                     # Hierarquia ApiError + conversão sem vazamento
    ├── autorizacao.py               # Perfil / Sujeito / exigir_perfil
    ├── filtros.py                   # FiltroDocumentos/FiltroLotes/Paginacao/Ordenacao + validação
    ├── handlers.py                  # Um handler por endpoint conceitual
    └── serializacao.py              # para_json() — contrato -> primitivos JSON
```

Nenhum arquivo das Fases 1-3 foi alterado. `api/` só **lê** dos
repositórios já existentes (`RepositorioDocumentos`,
`RepositorioHistorico`, `RepositorioLotes`, `RepositorioEstadosEsteira`)
e reaproveita `dtos_esteira.montar_item_esteira()` (Fase 3) como a
lógica de junção Documento×EstadoEsteira — a mesma que já resolve
compatibilidade com documentos legados.

## Endpoints conceituais e handlers correspondentes

| Endpoint conceitual | Handler (`handlers.py`) | Permissão |
|---|---|---|
| `GET /magnata-os/documental/esteira/resumo` | `obter_resumo_esteira` | leitura geral |
| `GET /magnata-os/documental/lotes` | `listar_lotes` | leitura geral |
| `GET /magnata-os/documental/lotes/{lote_id}` | `obter_lote` | leitura geral |
| `GET /magnata-os/documental/documentos` | `listar_documentos` | leitura geral |
| `GET /magnata-os/documental/documentos/{documento_id}` | `obter_documento` | leitura geral |
| `GET /magnata-os/documental/documentos/{documento_id}/historico` | `obter_historico_documento` | auditoria |
| `GET /magnata-os/documental/bloqueios` | `listar_bloqueios` | fila operacional |
| `GET /magnata-os/documental/acoes-humanas` | `listar_acoes_humanas` | fila operacional |
| `GET /magnata-os/documental/parados` | `listar_documentos_parados` | leitura geral |

Nenhuma rota HTTP de fato existe nesta fase — a coluna "Endpoint
conceitual" é o contrato que um adapter web futuro precisa respeitar,
não uma rota Flask registrada.

## Contratos de resposta (`contratos.py`)

Todos os campos são `str`/`int`/`float`/`bool`/`dict`/`tuple`/`None` —
nunca `Enum`, `datetime` ou `MappingProxyType` (esses tipos são
convertidos nos mapeadores de `handlers.py`, nunca vazam para o
contrato). Datas são sempre string ISO-8601 (UTC); enums de domínio
(etapa, situação, tipo de próxima ação) são sempre a string `.value`.

- **`DocumentoEsteiraResponse`** — resposta completa de um documento:
  `documento_id`, `nome_original`, `lote_id`, `origem`, `etapa_atual`,
  `situacao`, `motivo_bloqueio` (`MotivoBloqueioResponse` opcional),
  `proxima_acao` (`ProximaAcaoResponse` opcional, com `tipo`
  `'AUTOMATICA'`/`'HUMANA'`), `tempo_na_etapa_segundos`,
  `ultimo_evento` (`UltimoEventoResponse` opcional), `recebido_em`,
  `atualizado_em`, `rastreado_pela_esteira`. Responde de uma vez ao
  princípio obrigatório desta fase.
- **`LoteResponse`** — `lote_id`, `origem`, `recebido_em`,
  `quantidade_arquivos`, `situacao`, `correlation_id`, `criado_em`,
  `atualizado_em`, `metadados`.
- **`HistoricoResumidoResponse`** — `documento_id`, `total_eventos`,
  `eventos` (tupla de `HistoricoItemResponse`, ordenada
  cronologicamente).
- **`BloqueioResponse`** — visão focada em fila de trabalho:
  `documento_id`, `nome_original`, `lote_id`, `etapa_atual`,
  `motivo_bloqueio` (sempre presente aqui, nunca `None` — é a lista de
  quem está bloqueado), `proxima_acao`, `tempo_bloqueado_segundos`.
- **`ResumoEsteiraResponse`** — indicadores agregados (ver seção
  própria abaixo).
- **`PaginacaoResponse`** — envelope genérico (`pagina`,
  `tamanho_pagina`, `total_itens`, `total_paginas`, `itens`) usado por
  todo endpoint de listagem.
- **`ErroApiResponse`** — `codigo`, `mensagem`, `detalhes` opcional.

## Resumo da esteira (`obter_resumo_esteira`)

`ResumoEsteiraResponse` traz: `total_documentos` (todos os `Documento`,
incluindo legados sem esteira), `total_por_etapa`/`total_por_situacao`
(só documentos rastreados pela esteira — reaproveita a mesma agregação
de `consultas_esteira.montar_resumo_esteira`, Fase 3), `total_bloqueados`,
`total_com_acao_humana`, `total_em_erro`, `total_parados_acima_do_limite`
(configurável via `limite_parado_segundos`, padrão 24h),
`lotes_recebidos_hoje` (por `recebido_em.date()` no fuso do relógio do
`ContextoApi`, UTC por padrão), `tempo_medio_na_etapa_segundos` (média
do tempo na etapa atual entre todos os documentos rastreados),
`documento_mais_antigo_pendente` (o `DocumentoEsteiraResponse` completo
do documento com `entrou_na_etapa_em` mais antigo entre os que ainda não
chegaram a `AUDITORIA`+`CONCLUIDO`).

## Filtros, paginação e ordenação segura (`filtros.py`)

**Filtros de documentos** (`FiltroDocumentos`): `etapa`, `situacao`,
`lote_id`, `origem`, `bloqueado` (bool), `acao_humana` (bool),
`recebido_de`/`recebido_ate` (intervalo em `Documento.recebido_em`),
`tempo_minimo_parado_segundos`. Todos opcionais e combináveis — um
`listar_documentos()` com vários filtros preenchidos aplica todos em
conjunto (E lógico), nunca um só isoladamente.

**Filtros de lotes** (`FiltroLotes`): `origem`, `situacao`,
`recebido_de`/`recebido_ate`.

**Paginação** (`Paginacao`): `pagina` (>= 1), `tamanho_pagina` (1 a 200
— `TAMANHO_PAGINA_MAXIMO`). Pedir uma página além do total de itens
devolve uma lista vazia (`itens=()`), não é erro — só `pagina <= 0` ou
`tamanho_pagina` fora do intervalo levantam `PaginacaoInvalida`.

**Ordenação segura** (`Ordenacao`): `campo` + `direcao`
(`'asc'`/`'desc'`). "Segura" significa que `campo` é **sempre**
conferido contra um allowlist fixo por endpoint
(`CAMPOS_ORDENACAO_DOCUMENTOS`, `CAMPOS_ORDENACAO_LOTES`,
`CAMPOS_ORDENACAO_BLOQUEIOS`) antes de ser usado — nunca um
`getattr`/lookup dinâmico direto contra um nome vindo de fora, o que
poderia expor atributos internos não pensados para ordenação ou
levantar `AttributeError` revelando a forma interna dos objetos. Um
campo fora do allowlist, ou uma direção que não seja `asc`/`desc`,
levanta `OrdenacaoInvalida`. Itens sem valor no campo de ordenação
(ex.: `atualizado_em` de um documento legado não rastreado) sempre vão
para o fim da lista, em qualquer direção, sem quebrar o `sort` (que não
sabe comparar `None` com `datetime`/`float`).

## Autorização abstrata (`autorizacao.py`)

**Sem autenticação real nesta fase** — `Sujeito` carrega só um `Perfil`
declarado (`OPERACIONAL`, `GESTOR`, `AUDITOR`), não o resultado de
validar sessão/token/senha. Quando uma fase futura implementar
autenticação real, o único ponto de integração é onde `Sujeito` é
construído (no adapter web, fora deste módulo) — toda a lógica de "quem
pode consultar o quê" já vive aqui e não muda.

Cada handler **declara explicitamente** seu conjunto de perfis
permitidos (constantes em `handlers.py`) e chama `exigir_perfil()` como
a primeira coisa que faz:

- **`PERMISSAO_LEITURA_GERAL`** (`OPERACIONAL`, `GESTOR`, `AUDITOR`) —
  resumo, lotes, documentos, documento/lote individual, parados: visão
  geral do estado da esteira, todo perfil monitora.
- **`PERMISSAO_FILA_OPERACIONAL`** (`OPERACIONAL`, `GESTOR`) —
  bloqueios, ações humanas: filas de trabalho de quem efetivamente
  resolve essas pendências no dia a dia; auditor consulta o mesmo
  estado via documentos/histórico, não via a fila operacional.
- **`PERMISSAO_AUDITORIA`** (`GESTOR`, `AUDITOR`) — histórico completo
  de um documento: trilha de auditoria detalhada; operacional já tem a
  próxima ação resolvida nas outras consultas e não precisa do
  histórico bruto para o trabalho do dia a dia.

`exigir_perfil()` levanta `PermissaoNegada` (um `ApiError`,
`status_http=403`) quando o perfil do sujeito não está no conjunto
permitido — nunca aplica a regra em silêncio.

## Tratamento de erros (`erros.py`)

Toda `ApiError` carrega um `codigo` estável (para o cliente decidir
programaticamente, sem parsear mensagem) e um `status_http` sugerido:

| Exceção | `codigo` | `status_http` |
|---|---|---|
| `DocumentoNaoEncontrado` | `DOCUMENTO_NAO_ENCONTRADO` | 404 |
| `LoteNaoEncontrado` | `LOTE_NAO_ENCONTRADO` | 404 |
| `FiltroInvalido` | `FILTRO_INVALIDO` | 400 |
| `OrdenacaoInvalida` | `ORDENACAO_INVALIDA` | 400 |
| `PaginacaoInvalida` | `PAGINACAO_INVALIDA` | 400 |
| `PermissaoNegada` | `PERMISSAO_NEGADA` | 403 |
| `ErroInternoNaoExposto` | `ERRO_INTERNO` | 500 |

**Nenhum detalhe técnico sensível escapa para o cliente da API.** Todo
handler é decorado com `@proteger_erros`: qualquer exceção que não seja
`ApiError` (bug, repositório indisponível, erro de infraestrutura com
credenciais na mensagem, etc.) é convertida em `ErroInternoNaoExposto`
com a **mesma mensagem genérica sempre**
(`"Erro interno ao processar a consulta. Tente novamente mais tarde."`)
— nunca `str(excecao_original)`. A causa original fica encadeada via
`raise ... from exc` (visível em stacktrace/logs de processo para quem
for investigar), nunca na resposta exposta. `tratar_erro_para_resposta()`
é o único ponto que converte qualquer exceção em `ErroApiResponse`,
seguindo a mesma regra.

## Serialização JSON (`serializacao.py`)

`para_json(resposta)` converte qualquer contrato (ou estrutura aninhada
de contratos, tuplas, dicts e primitivos) para algo diretamente aceito
por `json.dumps()`. Como os contratos já armazenam só tipos
JSON-primitivos *dentro* de cada campo (nunca `Enum`/`datetime`), a
única conversão necessária é de **estrutura** — dataclass aninhado vira
`dict`, tupla vira `list` — recursivamente.

## O que esta fase explicitamente NÃO faz

Tela web; autenticação real (senha, token, sessão); OCR; IA;
fatiamento; vínculo com cliente; vínculo com funcionário; montagem de
pacote; envio (e-mail/WhatsApp); qualquer acesso real a PostgreSQL, S3
ou Airtable; qualquer alteração em `app.py` ou nos fluxos legados;
deploy; qualquer rota HTTP de fato registrada (Flask ou outro
framework) — os handlers desta fase são funções Python puras, prontas
para serem conectadas por um adapter web futuro.

## Testes

```bash
pytest test_magnata_os_documental_modulo01_fase4.py -v
```

33 testes cobrindo os 14 cenários exigidos por esta fase: resumo da
esteira (indicadores agregados e validação de `limite_parado_segundos`),
filtros combinados (etapa+situação+origem+bloqueado+ação-humana, lote+
tempo-parado, intervalo de recebimento), paginação (página cheia, última
página parcial, página além do fim), ordenação segura (ascendente/
descendente, campo fora do allowlist, direção inválida), documento
individual (rastreado e legado sem esteira), lote individual, histórico
(ordenado cronologicamente), bloqueios (com e sem bloqueio ativo), ações
humanas, documentos parados (com relógio controlável e validação de
tempo negativo), autorização (histórico exige gestor/auditor, filas
operacionais excluem auditor, leitura geral permite todos os perfis,
mensagem de negação lista os perfis permitidos), erros (documento/lote
não encontrado, paginação inválida, filtro inválido, mapeamento de
`tratar_erro_para_resposta`), serialização JSON (todos os 9 tipos de
resposta + erro, incluindo valores aninhados), e ausência de vazamento
de detalhes internos (um repositório fake que sempre falha com uma
mensagem contendo um segredo, provando que o segredo nunca aparece na
exceção exposta, na `ErroApiResponse` nem no JSON serializado).
