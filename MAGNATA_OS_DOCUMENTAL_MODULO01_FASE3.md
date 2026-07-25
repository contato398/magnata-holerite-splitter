# Magnata OS Documental — Módulo 01, Fase 3 (Lotes e Esteira Operacional)

**Status:** modelo operacional da esteira documental, sem interface web
completa. **Não integrado ao fluxo legado.** `app.py` inalterado.
Nenhum acesso a banco, S3 ou Airtable reais nesta fase — todos os
serviços são testados com repositórios em memória.

## Objetivo

As Fases 1 e 2 resolveram **o que é um Documento** (entidade, máquina de
estados técnica, idempotência) e **onde ele fica gravado** (Postgres +
armazenamento de arquivo). Esta fase resolve uma pergunta diferente:
**em que ponto do processo operacional este documento está, agora?** —
e como agrupar N arquivos recebidos juntos num lote rastreável.

## Princípio central: status técnico ≠ etapa operacional

`StatusDocumento` (`dominio.py`, Fase 1: `RECEBIDO` → `REGISTRADO` →
...) responde **"o registro deste Documento é válido?"** — um dado
técnico sobre a integridade do próprio registro, que não muda depois
que o documento está `REGISTRADO` (a menos de re-processamento/erro
técnico).

`EtapaEsteira` + `SituacaoEsteira` (`dominio_esteira.py`, Fase 3)
respondem **"em que ponto do processo operacional este documento está,
e como está indo?"** — evoluem continuamente enquanto o documento
percorre a esteira (classificação, separação, identificação,
validação, montagem, distribuição, confirmação, auditoria), totalmente
**independente** de `StatusDocumento`. Um `Documento` com
`status=REGISTRADO` pode estar em qualquer etapa da esteira, de
`ENTRADA` a `AUDITORIA` — o status técnico não diz nada sobre isso, de
propósito.

Essas duas dimensões nunca se misturam no código: `EstadoEsteiraDocumento`
é uma entidade própria, com seu próprio repositório
(`repositorio_esteira.py`) e seu próprio serviço de transição
(`servico_avanco_esteira.py`) — nenhuma função desta fase muta
`Documento.status`, e nenhuma função da Fase 1/2 sabe que
`EstadoEsteiraDocumento` existe.

## Arquitetura

```
magnata_os/documental/modulo01/
├── dominio.py                     # Fase 1 — inalterado
├── repositorio.py                 # Fase 1 — inalterado
├── servico_entrada.py             # Fase 1 — inalterado, reaproveitado por servico_lote.py
├── armazenamento.py               # Fase 2 — inalterado
├── servico_entrada_persistente.py # Fase 2 — inalterado
├── adapters/                      # Fase 2 — inalterado
├── dominio_esteira.py             # NOVO — LoteDocumental, EstadoEsteiraDocumento,
│                                   #        EtapaEsteira, SituacaoEsteira, maquina de etapas
├── repositorio_esteira.py         # NOVO — Protocols + em-memoria (lotes e estados)
├── dtos_esteira.py                # NOVO — DTOs de saida (ResumoLote, ItemEsteiraDocumento, ...)
├── servico_avanco_esteira.py      # NOVO — transicoes de etapa, bloqueio, resolucao
├── servico_lote.py                # NOVO — criacao de lote (orquestra Fase 1 + esteira)
├── consultas_esteira.py           # NOVO — leituras (por etapa, situacao, bloqueio, parados...)
└── migrations/
    ├── 0001-0004                  # Fase 2 — inalteradas
    ├── 0005_criar_tabela_lotes_documentais.sql
    ├── 0006_criar_tabela_estados_esteira_documental.sql
    ├── 0007_vinculo_documentos_lote.sql
    └── 0008_indices_esteira.sql
```

Nenhum adapter Postgres é construído nesta fase — só o schema (migrations
0005-0008) que um adapter futuro vai preencher, seguindo o mesmo padrão
duck-typed contra DB-API 2.0 já usado em `adapters/postgres_repositorio.py`
(Fase 2). Persistência desta fase é só em memória, mesma disciplina de
fundação da Fase 1.

## Modelo de dados

### `LoteDocumental`

Agrupa N arquivos recebidos numa mesma operação de entrada, compartilhando
`origem` e `correlation_id`. Não é um `Documento` nem o substitui — é a
unidade de acompanhamento operacional de "uma entrada em lote" (ex.: um
e-mail com 5 anexos). Campos: `lote_id`, `origem`, `recebido_em`,
`quantidade_arquivos`, `situacao`, `correlation_id`, `criado_em`,
`atualizado_em`, `metadados`.

### `EstadoEsteiraDocumento`

Estado operacional **atual** de um `Documento` na esteira — uma linha por
`documento_id`, não um histórico (o histórico de transições vai para
`RepositorioHistorico`, ver "Histórico da esteira" abaixo). Campos:
`documento_id`, `lote_id` (opcional), `etapa_atual`, `situacao`,
`motivo_bloqueio` (opcional), `proxima_acao` (opcional),
`entrou_na_etapa_em`, `atualizado_em`, `correlation_id`.

### `MotivoBloqueio` (opcional, estruturado)

`codigo`, `descricao`, `detalhe_tecnico` (opcional),
`resolvivel_automaticamente` (bool) — nunca um texto livre solto.
`resolvivel_automaticamente` alimenta diretamente o tipo da próxima ação
calculada (`AUTOMATICA` ou `HUMANA`, ver abaixo).

### `ProximaAcao` (opcional)

`acao` (descrição), `tipo` (`AUTOMATICA`/`HUMANA`), `prazo` (opcional),
`responsavel` (opcional). Sempre **calculada**, nunca definida à mão pelo
chamador — ver `calcular_proxima_acao()` em `servico_avanco_esteira.py`.

## Etapas e transições

```
ENTRADA → REGISTRO → CLASSIFICACAO → SEPARACAO → IDENTIFICACAO →
VALIDACAO → MONTAGEM_PACOTE → DISTRIBUICAO → CONFIRMACAO → AUDITORIA
```

Sequência **linear e estrita**: cada etapa só avança para a *próxima* da
lista (`TRANSICOES_ETAPA_PERMITIDAS`, `dominio_esteira.py`) — nunca pula
etapas, nunca retrocede, nunca fica na mesma etapa. `AUDITORIA` é
terminal (nenhuma transição permitida a partir dela). Uma transição fora
dessa maquina levanta `TransicaoEtapaInvalida`, nunca aplicada em
silêncio.

**Retroceder/revisar não é modelado como retrocesso de etapa.** Um
documento que precisa de revisão manual numa etapa qualquer tem sua
`situacao` marcada `EM_REVISAO` — a etapa em si nunca anda para trás.
Isso mantém as duas dimensões (etapa x situação) genuinamente
independentes: a etapa é sempre monotônica; a situação é o que varia
livremente dentro dela.

**Bloqueio impede qualquer avanço de etapa.** Enquanto
`situacao == BLOQUEADO`, `avancar_etapa()` levanta
`AvancoBloqueadoPorPendencia` — o bloqueio precisa ser resolvido primeiro
via `resolver_bloqueio()` (que nunca avança etapa por si só; um
`avancar_etapa()` separado continua sendo necessário depois, se for o
caso).

## Cálculo de próxima ação

`calcular_proxima_acao(etapa_atual, situacao, motivo_bloqueio=None)` é
uma função pura (sem I/O, sem acesso a repositório), com estas regras,
em ordem de prioridade:

1. **`BLOQUEADO`** — a próxima ação é sempre resolver o bloqueio;
   `AUTOMATICA` se `motivo_bloqueio.resolvivel_automaticamente`,
   `HUMANA` caso contrário.
2. **`EM_REVISAO`** — sempre `HUMANA` (revisão manual), independente da
   etapa.
3. **`AUDITORIA` + `CONCLUIDO`** — etapa terminal, não há próxima ação
   (`None`).
4. **Caso geral** — descrição fixa por etapa; `AUTOMATICA` para
   `ENTRADA`/`REGISTRO` (etapas já totalmente automatizadas pela
   plataforma via `ServicoEntradaDocumental` + `ServicoCriacaoLote`),
   `HUMANA` para as demais (`CLASSIFICACAO` em diante ainda não têm
   nenhuma automação implementada — ver "O que esta fase explicitamente
   NÃO faz").

## Serviço de criação de lote (`servico_lote.py`)

`ServicoCriacaoLote.criar_lote(origem, arquivos, correlation_id=None)`:

1. Cria o `LoteDocumental` (situação `EM_PROCESSAMENTO`).
2. Para **cada arquivo, isoladamente**:
   - Delega a `ServicoEntradaDocumental.registrar_entrada()` (Fase 1,
     reaproveitado sem alteração) — calcula hash, garante idempotência,
     persiste `Documento` + histórico técnico.
   - Cria o `EstadoEsteiraDocumento` inicial via
     `ServicoAvancoEsteira.criar_estado_inicial()` — **atômico** por
     `documento_id`: se já existir um estado (mesmo hash já processado
     antes, neste lote ou em qualquer lote anterior), o arquivo é
     marcado `duplicado=True` no resumo e **nada é alterado** no estado
     existente (nem o `lote_id`, que permanece apontando para o lote
     *original*).
   - Se for a primeira vez, avança automaticamente `ENTRADA → REGISTRO`
     (situação `CONCLUÍDO`) — porque, a essa altura, `registrar_entrada()`
     já persistiu o `Documento` com `status=REGISTRADO`; as duas etapas
     já aconteceram de fato.
   - **Qualquer exceção neste arquivo é capturada e vira um item de erro
     no resumo — nunca aborta o processamento dos demais arquivos.**
3. Calcula a situação final do lote: `CONCLUIDO` se nenhum arquivo
   falhou; `ERRO` se todos falharam; `EM_REVISAO` se foi parcial
   (alguns sucesso, alguns erro) — sinalizando que um humano precisa
   olhar o lote.
4. Retorna um `ResumoLote` completo, sempre — mesmo quando todos os
   arquivos falharam.

### Por que a duplicidade é detectada pela existência de `EstadoEsteiraDocumento`, não por `StatusDocumento`

`ServicoEntradaDocumental.registrar_entrada()` (Fase 1) sempre retorna um
`Documento` válido, seja ele novo ou já existente — sem expor se foi
"criado agora" ou não. Em vez de mudar a assinatura da Fase 1 (já
mergeada e revisada), a Fase 3 usa
`RepositorioEstadosEsteira.criar_se_ausente()` (atômico, mesmo padrão de
`salvar_se_ausente_por_hash` da Fase 1) como a fonte de verdade: se um
estado já existe para aquele `documento_id`, é duplicidade — do mesmo
lote ou de qualquer lote anterior, não importa.

## Serviço de avanço da esteira (`servico_avanco_esteira.py`)

`ServicoAvancoEsteira` é o único lugar que muta `EstadoEsteiraDocumento`:

- `criar_estado_inicial(documento_id, lote_id, correlation_id, ...)` —
  cria o primeiro estado (atômico via `criar_se_ausente`), retorna
  `(estado, criado)`.
- `avancar_etapa(documento_id, nova_etapa, correlation_id, ...)` —
  valida a transição, impede avanço se `BLOQUEADO`, registra saída da
  etapa anterior e entrada na nova.
- `registrar_bloqueio(documento_id, motivo, correlation_id)` — marca
  `BLOQUEADO` **na etapa atual** (a etapa não muda), com o motivo
  estruturado.
- `resolver_bloqueio(documento_id, correlation_id, ...)` — limpa o
  bloqueio, devolve a uma situação normal na mesma etapa; levanta
  `NenhumBloqueioAtivo` se não havia bloqueio.

### Histórico da esteira

Toda transição (`ESTEIRA_ESTADO_INICIAL_CRIADO`, `ESTEIRA_ETAPA_AVANCADA`,
`ESTEIRA_BLOQUEIO_REGISTRADO`, `ESTEIRA_BLOQUEIO_RESOLVIDO`) gera um
`EventoHistorico` no **mesmo** `RepositorioHistorico` da Fase 1 —
reaproveitamento deliberado da infraestrutura de auditoria já
construída, em vez de criar uma segunda tabela de eventos só para a
esteira (não existe `eventos_esteira` nas migrations desta fase, de
propósito). `status_anterior`/`status_novo` desses eventos são sempre
`None`: eles nunca representam uma transição de `StatusDocumento`, só de
`EtapaEsteira`/`SituacaoEsteira`. O registro do evento é *best-effort* —
uma falha ao registrar não desfaz a mutação de `EstadoEsteiraDocumento`
já salva (mesma filosofia de "o dado principal nunca é perdido por causa
de uma falha de auditoria" da Fase 1).

## Documentos legados (compatibilidade)

Documentos criados **antes** da Fase 3 (ou por qualquer fluxo que não
passe por `ServicoCriacaoLote`) nunca têm `EstadoEsteiraDocumento` — não
existe linha para eles em `estados_esteira_documental`, e
`lote_id` no próprio `Documento` (campo já existente desde a Fase 1)
continua `None`.

Isso **não é tratado como erro**: `dtos_esteira.montar_item_esteira()`
responde explicitamente `rastreado_pela_esteira=False` com todos os
campos de esteira (`etapa_atual`, `situacao`, `motivo_bloqueio`,
`proxima_acao`, `tempo_na_etapa_segundos`) em `None`, em vez de inventar
um estado que nunca existiu de verdade ou levantar exceção. Consultas por
etapa/situação (`documentos_por_etapa`, `documentos_por_situacao`, etc.)
simplesmente não incluem documentos legados — elas leem
`estados_esteira_documental`, não `documentos`.

**Estratégia de migração:** nenhum backfill retroativo é feito nesta
fase (não há como reconstruir com confiança em que etapa um documento
legado "estaria" — o conceito de etapa não existia quando ele foi
criado). Um documento legado só passa a ser rastreado pela esteira se
for reprocessado através de `ServicoCriacaoLote` no futuro (o que criaria
um novo `Documento`, já que a idempotência por hash é por conteúdo, não
por identidade) — ou por uma migração de dados explícita e deliberada,
fora do escopo desta fase.

**Enforcement de "toda entrada nova deve possuir lote":** é uma
convenção desta fase, não uma restrição de código na Fase 1.
`ServicoEntradaDocumental.registrar_entrada()` continua aceitando
`lote_id=None` (Fase 1/2 não foram alteradas, para não quebrar contratos
já revisados e mergeados) — mas `ServicoCriacaoLote` é o único ponto de
entrada **sancionado** a partir desta fase, e ele sempre gera um
`lote_id` real. Ver "Riscos restantes" no relatório de entrega desta
fase para o risco associado a essa escolha.

## Migrations

- **0005** `lotes_documentais` — tabela nova, idempotente
  (`CREATE TABLE IF NOT EXISTS`).
- **0006** `estados_esteira_documental` — tabela nova, uma linha por
  `documento_id` (`PRIMARY KEY`), FK obrigatória para `documentos`, FK
  opcional para `lotes_documentais`. Inclui uma `CHECK` garantindo
  consistência entre `situacao` e presença de `motivo_bloqueio_codigo`
  (bloqueado ⟺ motivo presente).
- **0007** vínculo formal `documentos.lote_id → lotes_documentais.lote_id`
  — a coluna já existia desde a migration 0001 (Fase 2) sem FK; esta
  migration adiciona a constraint, `NULL` continua permitido (FK padrão
  do Postgres não exige `NOT NULL`) — é exatamente isso que preserva
  compatibilidade com documentos anteriores à Fase 3. Idempotente via
  bloco `DO` + checagem em `pg_constraint` (`ALTER TABLE ADD CONSTRAINT`
  não aceita `IF NOT EXISTS` nativamente).
- **0008** índices — por `lote_id`, por `etapa_atual`, por `situacao`,
  índice parcial para `BLOQUEADO`, por `entrou_na_etapa_em` (suporta
  "documentos parados"), e por `lotes_documentais.criado_em DESC`
  (suporta "lotes recentes”). `CREATE INDEX IF NOT EXISTS` já é
  idempotente nativamente.

**Ordem obrigatória:** 0005 → 0006 → 0007 → 0008 (mesma disciplina das
migrations 0001-0004 da Fase 2 — 0006 referencia 0005, 0007 referencia
0005 e a coluna já criada por 0001).

## Consultas (`consultas_esteira.py`)

Respondem diretamente ao princípio obrigatório desta fase — para
qualquer documento: onde está, como está, por que parou, qual a próxima
ação, há quanto tempo:

- `lotes_recentes` / `lote_por_id`
- `documentos_por_etapa` / `documentos_por_situacao`
- `documentos_bloqueados`
- `documentos_parados_a_partir_de(limite_segundos)` — compara
  `entrou_na_etapa_em` contra o relógio, ordenado do mais parado para o
  menos parado.
- `documentos_com_acao_humana_pendente`
- `ultimo_evento_e_proxima_acao` — combina o último `EventoHistorico`
  (Fase 1, inclui eventos técnicos e `ESTEIRA_*`) com a `proxima_acao`
  atual da esteira (Fase 3) numa única resposta.
- `montar_resumo_esteira` — visão agregada (contagens por etapa,
  situação, bloqueados, ação humana pendente) para painéis futuros.

## O que esta fase explicitamente NÃO faz

OCR; IA/classificação automática de conteúdo; fatiamento/separação real
de PDF; vínculo com cliente; vínculo com funcionário; montagem real de
pacotes de envio; envio (e-mail/WhatsApp); interface web completa;
qualquer acesso real a PostgreSQL, S3 ou Airtable; qualquer alteração em
`app.py` ou nos fluxos legados; deploy. As etapas `CLASSIFICACAO` em
diante existem no vocabulário (`EtapaEsteira`) e na máquina de transições
para que módulos futuros tenham onde encaixar essas automações — nenhuma
delas é implementada aqui.

## Testes

```bash
pytest test_magnata_os_documental_modulo01_fase3.py -v
```

25 testes, cobrindo os 13 cenários exigidos por esta fase: lote com
vários arquivos, duplicidade no mesmo lote, duplicidade em lote
anterior, falha isolada (parcial e total), transição de etapa válida e
inválida (incluindo documento sem estado), bloqueio impedindo avanço,
resolução de bloqueio (incluindo tentativa sem bloqueio ativo), cálculo
de documentos parados (via relógio controlável), próxima ação automática
e humana (incluindo bloqueio resolvível automaticamente e etapa
terminal), compatibilidade com documento legado, e concorrência na
criação de lotes (15 threads, mesmo conteúdo, `threading.Barrier`) —
mais cobertura complementar das consultas (`documentos_bloqueados`,
`documentos_com_acao_humana_pendente`, `ultimo_evento_e_proxima_acao`,
`lotes_recentes`, `lote_por_id`, `documentos_por_situacao`,
`montar_resumo_esteira`).
