# Orquestrador Real Read-Only do Corredor V2 — V1

Documento de decisão da missão macro "CONSTRUIR ORQUESTRADOR REAL
READ-ONLY DO CORREDOR V2 + PREPARAR PRIMEIRO LIVE CONTROLADO SEM
EXECUTÁ-LO". Sobre o PR #109 (mesclado a `main`, HEAD
`b6ab40542735aaf9ad8dcadc1e507db5e6b20c74`). Branch:
`fix/orquestrador-readonly-corredor-v2`.

## 0. Objetivo

Eliminar o maior bloqueio real registrado em `docs/decisoes/corredor-
live-v2-bloqueios-reais-v1.md` §1.1: "nenhum orquestrador de produção
real existe hoje para o corredor `classificacao/`". Construir o MENOR
orquestrador real read-only capaz de compor as capacidades já reais
(cliente_direto, escopo histórico, UNIDADE_POSTO, relação documental,
inventário, readiness, pacote) sem escrever externamente, sem
migration, sem live.

## 1. Decisão de local — auditoria obrigatória

Auditados, antes de qualquer código:

- **A. `importacao_lote/orquestrador.py`**: `processar_holerite`/
  `processar_extrato` resolvem CORRESPONDÊNCIA de cliente/colaborador
  para o pipeline de IMPORTAÇÃO EM LOTE (manifesto → `ResultadoItem` →
  `escritor.py`) — um fluxo DIFERENTE, com contrato de saída diferente
  (`ResultadoItem`, não `ResultadoResolucaoSemantico`). Nunca chama
  `processar_documento_prestacao`. Reaproveitar ESTE arquivo para o
  papel pedido misturaria 2 responsabilidades distintas no mesmo
  módulo — descartado.
- **B. `magnata_os/classificacao/`**: tem o corredor PURO completo
  (`resolucao_documento_prestacao.py`, `corredor_relacao_documental.py`)
  mas NENHUM arquivo de composição/orquestração de execução — só
  Protocols e funções puras, nenhum entrypoint. Confirmado por busca:
  nenhum arquivo do tipo `orques*`/`composic*`/`runner*`/`pipeline*`
  existe neste diretório.
- **C. `magnata_os/orquestrador/`** ("Grande Orquestrador"): engine de
  eventos/execução GENÉRICA (`motor.py`, `eventos.py`, `autorrecuperacao.
  py`, `supervisor.py`) — nenhuma regra documental, por desenho.
  Colocar regra documental aqui violaria diretamente o §21 da missão
  ("se ele for de execução/eventos gerais: não colocar regra
  documental nele") — descartado.
- **D. Scripts/runners shadow**: busca confirma que não existe nenhum.
- **E. `magnata_os/documental/modulo01/`**: bounded context DIFERENTE
  (entidade `Documento`, schema Postgres próprio, conflito de
  nomenclatura "Item de Ingestão" vs "Documento" já registrado e não
  resolvido em `/CLAUDE.md` §5) — misturar a composição da Prestação
  de Contas aqui criaria acoplamento entre 2 domínios que o próprio
  `/CLAUDE.md` trata como separados.
- **F. `app.py`**: lido só para entendimento conceitual (legado
  protegido, nunca importado).

**DECISÃO**: nenhum orquestrador existente cumpre o papel — criados 2
módulos NOVOS e estreitos, na MESMA separação Protocol/adapter já
usada em toda a sessão (§19 da missão):

- `magnata_os/classificacao/orquestrador_corredor_readonly.py` —
  ORQUESTRADOR CANÔNICO/PURO (§19-A): só Protocols, zero Airtable/
  requests, `dataclasses`/tipo puro. Fica dentro de `classificacao/`
  porque é exatamente o mesmo tipo de composição que `resolucao_
  documento_prestacao.py`/`corredor_relacao_documental.py` já fazem —
  nunca um segundo motor, só a ORDEM de 2 decisões que precisavam ser
  tomadas ANTES do corredor já existente (ver §2).
- `magnata_os/documental/importacao_lote/composicao_corredor_readonly.py`
  — COMPOSIÇÃO DE BORDA (§19-B): instancia os adapters REAIS já
  construídos (nenhum adapter novo), extrai PDF via `extracao_texto.
  extrair_texto_pdf` (já promovida, neutra). Fica em `importacao_lote/`
  porque é o MESMO pacote que já hospeda todo adapter real Airtable-
  shadow construído nesta sessão (`adapters/`) — precedente direto,
  não uma escolha nova.

**Alternativas descartadas**: A (mistura 2 pipelines); C (proibido
explicitamente pela missão); E (bounded context errado); estender
`resolucao_documento_prestacao.py` com Airtable direto (quebraria o
teste arquitetural já existente).

## 2. O que é genuinamente novo (nunca um "GrandeOrquestrador2")

O orquestrador canônico só COSTURA peças já existentes, na ordem
certa — nenhuma reimplementada: `processar_documento_com_separacao_se_
necessaria` → `avancar_para_inventario` → `resolver_relacao_e_avancar`
→ `avaliar_e_montar_pacote` (as 4 já existiam). A única coisa nova é
resolver, ANTES de montar `ContextoResolucaoDocumentoPrestacao`
(que já exige esses 2 valores PRONTOS, nunca uma fonte a consultar
sozinho — por desenho, desde PR #106):

1. **`competencia_esperada`**: via `PoliticaCompetenciaPrestacao.
   competencia_esperada_para(ciclo, cliente_do_ciclo, tipo_provisorio)`
   — reaproveita a MESMA política pura já existente (`POLITICA_
   COMPETENCIA_PRESTACAO_V1`, regra SKY Tatuí já registrada), nunca
   uma segunda regra. `tipo_provisorio` vem de uma chamada SEM efeito
   colateral à MESMA ponte semântica que o corredor já usa
   internamente (`resolver_tipo_documental_de_texto`) — chamá-la aqui
   só para escolher a política de competência não duplica a decisão
   real de tipo (essa é tomada de novo, com autoridade, dentro do
   corredor). Só resolve com certeza (RESOLVIDA, 1 valor) — qualquer
   outro caso cai no fallback tipo-agnóstico já existente na própria
   política, nunca um erro nem uma competência inventada.
2. **`cliente_direto`**: via `FonteClienteDiretoDocumento.resolver_
   cliente_direto(texto)` — porque esse campo já é, estruturalmente,
   um VALOR pré-resolvido no contrato existente, nunca uma fonte
   consultada pelo corredor.

`cliente_do_ciclo`: mesmo tipo de conhecimento operacional que
`ContextoCicloPrestacao.competencia_base` já representa para
competência — "este run já sabe que processa 1 cliente específico"
(ex.: 1 pasta/manifesto por vez) — NUNCA inferido do documento. `None`
é seguro: cai no fallback sem deslocamento por cliente.

## 3. Reuso principal (nada reimplementado)

| Capacidade | Reaproveitada de |
|---|---|
| Extração de PDF | `documental/extracao_texto.extrair_texto_pdf` |
| Resolução de tipo/dimensões | `resolucao_documento_prestacao.processar_documento_com_separacao_se_necessaria` |
| Avanço para inventário | `resolucao_documento_prestacao.avancar_para_inventario` |
| Relação documental | `corredor_relacao_documental.resolver_relacao_e_avancar` |
| Pacote/readiness | `pacote_prestacao.avaliar_e_montar_pacote` |
| Extração de correlação | `relacao_documental.extrair_dados_correlacao_de_texto` |
| Política de competência | `competencia_esperada_prestacao.POLITICA_COMPETENCIA_PRESTACAO_V1` |
| CLIENTE via vínculo | `FonteVinculosPrestacaoAirtableShadow` (real, já existente) |
| UNIDADE_POSTO | `FonteUnidadePostoPrestacaoAirtableShadow` (real, já existente) |
| CLIENTE_DIRETO | `FonteClienteDiretoDocumentoAirtableShadow` (real, já existente) |
| Escopo/candidatos de relação | `FonteEscopoClientesPorInventarioAirtableShadow` + `FonteCandidatosRelacaoDocumentalDoInventario` (reais, já existentes) |
| Correlação transitória | `FonteDadosCorrelacaoEmMemoria` (já existente) |

Nenhuma linha de lógica de negócio foi reimplementada; o orquestrador
só decide EM QUE ORDEM chamar o que já existe.

## 4. Limitação honesta — extração por página

`extrair_texto_pdf` devolve 1 string já concatenada (todas as páginas
juntas), não uma lista por página. `processar_documento_com_separacao_
se_necessaria` precisa de páginas SEPARADAS para detectar documento
MASTER (múltiplos clientes/colaboradores no mesmo PDF). Consequência:
**separação master automática via PDF real não está disponível nesta
V1** — o orquestrador aceita `paginas: Tuple[str, ...]` (não só
`texto: str`) exatamente para não fechar essa porta: um chamador que já
tenha texto por página (teste, ou uma extração futura por página) usa
separação master normalmente; a composição de borda de HOJE, usando
`extrair_texto_pdf`, sempre produz `paginas=(texto_completo,)` (1
elemento) — nunca fabrica separação de página que a extração real não
suporta. Registrado como pendência nomeada, não fabricada.

## 5. Correlação transitória (§13/§14 da missão)

`FonteDadosCorrelacaoEmMemoria` (já existente, nunca alterada) é
instanciada UMA VEZ por `ExecucaoCorredorReadonly` (opcional,
`habilitar_correlacao_transitoria=False` por default). O orquestrador
canônico NUNCA decide sozinho se registra — só devolve `dados_
correlacao_extraidos` no resultado quando `registrar_dados_correlacao=
True` é pedido; quem compõe a borda decide registrar. Reiniciar o
processo (nova instância) apaga tudo — nunca chamado de persistência,
provado por teste (`test_relacao_documental_restart_da_fonte_dado_
nao_existe`).

## 6. Pacote/readiness (§17/§18 — achado da revisão adversarial)

A primeira versão desta missão deixou de fora a composição de pacote/
readiness por documento, apesar de a missão pedir explicitamente
(§17/§18). Corrigido na revisão adversarial (§33 da missão): campos
`fonte_inventario_pacote`/`politica_requisitos` (ambos opcionais,
`None` por default) — quando os 2 são informados E a dimensão CLIENTE
resolveu para EXATAMENTE 1 valor, `avaliar_e_montar_pacote` é chamado
(reaproveitado, nunca reimplementado). Documentos broadcast (DCTF,
N clientes) ou com vínculo múltiplo NUNCA geram pacote fabricado —
`pacote=None`, provado por teste
(`test_pacote_nunca_montado_para_broadcast_dctf`).
`fonte_inventario_pacote` é deliberadamente separada do `sink` (§16 da
missão: "distinguir inventário externo pré-existente vs gerado neste
run") — quem compõe decide se são a mesma fonte ou uma composta.

## 7. Revisão adversarial (§33 da missão) — achados e correções

Executada em 2 rodadas (a segunda, após as correções da primeira, sem
novos achados):

1. **Achado real, corrigido**: `dados_correlacao` do PRÓPRIO documento
   (usado para ele se resolver como comprovante) estava sendo extraído
   só quando `registrar_dados_correlacao=True` — um comprovante que não
   precisa registrar nada para o futuro, mas PRECISA da sua própria
   correlação para resolver contra candidatos, ficava com dados vazios
   e nunca resolvia. Corrigido: extração acontece 1 vez sempre que
   QUALQUER um dos 2 usos existir (registro transitório OU resolução
   imediata como comprovante); "registrar" e "usar agora" são
   decisões independentes.
2. **Achado real, corrigido**: pacote/readiness ausente (§6 acima).
3. Demais perguntas do checklist (§33 da missão) -- segundo pipeline?
   Não. Duplicou legado? Não. Airtable no core? Não (teste
   arquitetural, "positive control" novo). Título virou classificador?
   Não. Competência observada virou esperada? Não. Ciclo virou
   vigência? Não -- `competencia_snapshot_comprovada` continua
   totalmente desacoplado de `ContextoCicloPrestacao`, nunca derivado
   dele. First-match arbitrário? Não. CNPJ múltiplo? Não (reusa
   adapter já auditado). FGTS virou broadcast? Não, provado por teste.
   DCTF virou client-level? Não, preservado. Holerite ganhou cliente
   fake? Não. Cache transitório vendido como persistência? Não,
   docstring explícita + teste de restart. Live ready exige código
   novo? Sim, honestamente reconhecido -- ver §9.

## 8. Varredura de temporalidade (§32 da missão)

Busca por `ContextoCicloPrestacao`/`competencia_base`/`competencia_
esperada`/`snapshot`/`vigencia`/`historico`/`listar_ativos`/
`competencia_comprovada`/`competencia_snapshot` nos 2 arquivos novos:
`competencia_snapshot_comprovada` é repassada tal como está para
`FonteUnidadePostoPrestacaoAirtableShadow`, NUNCA derivada de `ciclo`
(parâmetro totalmente separado no construtor de `ExecucaoCorredorReadonly`).
`ciclo.competencia_base` só alimenta o FALLBACK de `competencia_
esperada` quando nenhuma política por cliente se aplica (`cliente_do_
ciclo=None`) -- mesmo fallback já existente dentro de `PoliticaCompetencia
Prestacao.competencia_esperada_para` para quando não há deslocamento
cadastrado, nunca uma "vigência" nova inventada. Nenhuma ocorrência do
erro já corrigido em missões anteriores (ciclo/snapshot tratado como
prova de outra coisa).

## 9. Checkpoint final pré-merge PR #110 — correção de inventário + reavaliação de READY

### 9.1 Achado funcional crítico, corrigido

`ExecucaoCorredorReadonly` injetava `FonteInventarioPrestacaoAirtableShadow`
(só Airtable) direto em `FonteCandidatosRelacaoDocumentalDoInventario` --
um documento processado NESTA execução (que entra em `self._sink`,
nunca escrito no Airtable, por desenho read-only) nunca seria
encontrado como candidato por um comprovante processado depois, no
MESMO run. Mesmo problema no ESCOPO de clientes: `FonteEscopoClientesPor
InventarioAirtableShadow` sozinha só enxerga clientes com registro NO
AIRTABLE -- um cliente cujo único rastro é o documento processado neste
run nunca apareceria no escopo, e a busca de candidatos nem chegaria a
olhar o inventário local dele.

Corrigido com o contrato já existente, nunca reimplementado:

- **Inventário**: `FonteInventarioPrestacaoComposta((FonteInventarioPrestacao
  AirtableShadow(leitor), self._sink))` -- externo + local, dedupe por
  `identidade_logica` já garantido pela classe composta.
- **Escopo**: `_EscopoClientesComCicloConhecido` (novo, pequeno --
  nunca reimplementa `FonteEscopoClientesPorInventarioAirtableShadow`,
  só aumenta o resultado dela com `cliente_do_ciclo` quando conhecido).
  `cliente_do_ciclo` migrou de parâmetro por-documento (`processar_
  documento`) para parâmetro da EXECUÇÃO (`ExecucaoCorredorReadonly.
  __init__`) -- reflete melhor o uso real (§15 do checkpoint: "1
  pasta/manifesto de 1 cliente por vez") e permite montar o escopo
  aumentado uma única vez, com o mesmo ciclo de vida do `sink`.
- **Pacote/readiness**: nova propriedade `fonte_inventario_completa`
  (a MESMA fonte composta usada para candidatos de relação) --
  fechando a mesma classe de bug também para quem monta pacote/
  readiness (§7 do checkpoint: "auditar também... alguma outra
  capacidade consulta apenas inventário externo?").

Teste anterior (`test_relacao_documental_correlacao_transitoria_
comprova`, no orquestrador PURO) usava uma `_FonteInventarioFake` que
JÁ continha o item do relatante -- provava o motor puro, nunca a
composição de borda real. Corrigido com 5 novos testes E2E pela BORDA
REAL (`ExecucaoCorredorReadonly`, `Mock()` de leitor, ZERO preload
externo): (A) relatório processado entra no sink + correlação
registrada; (B) comprovante processado depois, no MESMO run, encontra
o relatante só pelo inventário local -- núcleo do achado, agora
provado pela borda real; (C) nova execução não herda o cache da
anterior; (D) relatante em externo E local dedupa para 1 candidato;
(E) relatante só no externo continua encontrável.

### 9.2 Proteção de master (fail-safe)

`texto_filho = texto_completo` (linha já suspeita, nomeada no
checkpoint) -- corrigido: quando `resultado.documento_id !=
contexto.documento_id` (documento SEPARADO em filhos), `dados_
correlacao` NUNCA é extraído do texto MASTER inteiro para um filho --
fica no default vazio, nunca contamina. Documento unitário (o caso
real hoje, dado que `extrair_texto_pdf` não fatia por página) preserva
o comportamento integral. Testado
(`test_master_multi_filho_nunca_extrai_correlacao_do_texto_inteiro`).

### 9.3 `READY_FINAL` — reavaliado

O checkpoint distingue explicitamente `READY_FOR_LIVE_CORRIDOR_V2`
(ensaio read-only controlado) de `AUTOMATED_PRESTACAO_READY` (automação
de produção completa) -- 2 perguntas DIFERENTES, nunca confundidas
(§8 do checkpoint). Reavaliando os 3 "bloqueios" do ADR original (§9
anterior) sob essa luz:

- **Persistência durável de `dados_correlacao`**: NÃO é bloqueio para
  o ENSAIO -- a correlação same-run transitória agora funciona de
  verdade pela borda real (§9.1, provado). Continua bloqueio só para
  AUTOMAÇÃO persistente (múltiplas execuções precisando enxergar a
  correlação umas das outras).
- **Extração de PDF por página**: NÃO é bloqueio para o ENSAIO se a
  amostra usar só documentos UNITÁRIOS (sem master multi-cliente) --
  ver §9.4, a amostra recomendada é toda unitária. Continua limitação
  real para documentos master.
- **Vigência de UNIDADE_POSTO para ciclo corrente**: o ensaio alvo é a
  competência HISTÓRICA do SKY (Junho/2026, via regra -1 sobre o
  ciclo-base Julho) -- sem vigência comprovada para Junho,
  `NAO_ENCONTRADA` é o resultado CORRETO e esperado (prova que o robô
  não inventa), nunca um bloqueio para declarar o ensaio
  tecnicamente executável.

`MOTOR_LAB_READY = TRUE`. `ORQUESTRADOR_REAL_EXISTE = TRUE`.
`ADAPTERS_REAIS_MONTAVEIS = TRUE`. `EXECUCAO_LIVE_READONLY_TECNICAMENTE_
POSSIVEL = TRUE`. `MIGRATION_NECESSARIA_PARA_ENSAIO = FALSE` (correlação
same-run comprovada suficiente). `PDF_POR_PAGINA_NECESSARIO_PARA_AMOSTRA
= FALSE` (amostra recomendada é 100% unitária, ver §9.4).
`LIVE_AUTORIZADO = FALSE`. `LIVE_EXECUTADO = FALSE`.
`AUTOMATED_PRESTACAO_READY = PARTIAL` (automação de produção contínua
ainda depende de persistência durável real e de decisão de vigência
para ciclo corrente -- nenhuma contradição com o ensaio: são perguntas
diferentes, §8 do checkpoint).

**`READY_FOR_LIVE_CORRIDOR_V2 = TRUE`** (correção desta reavaliação --
o ADR original confundia os 2 níveis, exatamente o erro que o
checkpoint pediu para não cometer).

### 9.4 Achado adicional na preparação do plano — campos de anexo não comprovados

Auditoria dos IDs de campo já confirmados no repositório (nunca
inventados, §13/§24 do checkpoint): `F_HOL_PDF`
(`fldGXsgmuADtZIgtx`) e `F_EXT_PDF` (`fldznv1E24rfbZt34`)
(`airtable_escrita.py`) são campos de ANEXO real, já confirmados (o
adapter de escrita não funcionaria sem esses IDs corretos). **Nenhum
campo de anexo de FGTS Guia (`TABLE_FGTS`) nem de Guias/DCTFWeb
(`TABLE_GUIAS`) nem de Relatório de Benefícios está comprovado em
nenhum lugar do repositório** -- busca completa confirma. Por isso,
seguindo §13/§24 do checkpoint ("se algum ID necessário não estiver
comprovado: STOP e registrar precisamente"), a amostra seguRA do plano
(§10) usa só Holerite + Extrato (2 documentos, campos de anexo
comprovados) -- FGTS Guia e qualquer par de relação documental ficam
DE FORA da amostra desta rodada, precisamente porque o campo de anexo
não está comprovado, nunca por presunção.

## 10. `PLANO_AUTORIZACAO_LIVE_SKY_V1`

**NÃO EXECUTAR.** Produzido porque `READY_FOR_LIVE_CORRIDOR_V2 = TRUE`
(§9.3). Produzir este plano NÃO autoriza live -- `LIVE_AUTORIZADO =
FALSE`, `LIVE_EXECUTADO = FALSE`; execução futura exige nova
autorização humana específica, numa mensagem distinta desta.

- **SISTEMA**: Airtable.
- **BASE**: `appaCpIVj7Q97VhFy` (já usada por todos os adapters reais
  desta sessão).
- **CLIENTE**: EDIFICIO SKY TATUI.
- **CLIENTE RECORD ID**: `recrqv5NvbC37WfSl` (`REFERENCIA_CLIENTE_SKY_
  TATUI`, `competencia_esperada_prestacao.py`, já confirmado em missão
  anterior por leitura somente-GET).
- **CICLO BASE**: Julho/2026.
- **COMPETÊNCIA SKY**: Junho/2026 (regra -1, `POLITICA_COMPETENCIA_
  PRESTACAO_V1`, já registrada).
- **MODO**: READ-ONLY. Injetar `cliente_do_ciclo=REFERENCIA_CLIENTE_
  SKY_TATUI` em `ExecucaoCorredorReadonly` -- conhecimento operacional
  do run, nunca inferido do documento (§15 do checkpoint).

### Amostra (reduzida por achado real, §9.4 -- nunca por presunção)

**2 documentos, ambos UNITÁRIOS** (nunca um PDF master que dependa de
extração por página):

1. **1 Holerite** unitário do SKY Tatuí, competência Junho/2026.
2. **1 Extrato** unitário do SKY Tatuí, competência Junho/2026.

**FGTS Guia e qualquer documento relacional ficam FORA desta amostra**
-- campo de anexo não comprovado para `TABLE_FGTS`/`TABLE_GUIAS` (§9.4).
Incluí-los exigiria primeiro uma auditoria read-only de schema
(GET, sem payload de registro) para confirmar o field id do anexo --
fora do escopo desta missão, gate novo e separado.

### Tabelas e campos (só IDs já comprovados no repositório)

| Uso | Tabela | Campo | Confirmado em |
|---|---|---|---|
| Holerite -- registro | `TABLE_HOL` (`tblVaUgZeFfa5zRcH`) | -- | `airtable_escrita.py` |
| Holerite -- vínculo funcionário | mesma | `F_HOL_FUNC` (`fldTXMjeHfgyDas9f`) | `airtable_escrita.py` |
| Holerite -- **anexo (download)** | mesma | `F_HOL_PDF` (`fldGXsgmuADtZIgtx`) | `airtable_escrita.py` |
| Extrato -- registro | `TABLE_EXTRATO` (`tblJCUcFBVTH5W2kP`) | -- | `airtable_leitura.py` |
| Extrato -- vínculo cliente | mesma | `F_EXT_CLIENTE` (`fldKtdZpZ4fd7XpAX`) | `airtable_leitura.py` |
| Extrato -- **anexo (download)** | mesma | `F_EXT_PDF` (`fldznv1E24rfbZt34`) | `airtable_escrita.py` |
| Colaborador -- vínculo local | `TABLE_FUNC` (`tblNd8G66kjwos3eP`) | `F_FUNC_LOCAIS` (`fldqpwuLJsZsavaEJ`) | `airtable_vinculos_prestacao.py` |
| Local -- vínculo cliente | `TABLE_LOCAIS` (`tblZy1WfzmGIeR8ZP`) | `F_LOCAL_CLIENTE` (`fldu9xd2vvoMQ2Iqb`) | `airtable_vinculos_prestacao.py` |
| Clientes -- CNPJ/Nome (cliente_direto) | `TABLE_CLIENTES` (`tbl0znyuCEzoCHtCV`) | `'CNPJ'`/`'Nome'` (por nome de campo, não ID -- `listar_clientes()`) | `airtable_leitura.py` |

**STOP registrado** (§13/§24 do checkpoint): nenhum campo de anexo
comprovado para `TABLE_FGTS` (`tbl8ehgLa00cE1U3s`) nem `TABLE_GUIAS`
(`tbl6FT1YzK1yqI77l`) -- excluídos da amostra por esse motivo exato.

### Limites e execução

- **DOWNLOAD**: mínimo necessário -- 1 download por documento (2 no
  total), direto para memória, nunca persistido em disco fora do fluxo
  de teste, nunca commitado.
- **LEITURA**: `extrair_texto_pdf` (mesma extração já em produção) →
  `ExecucaoCorredorReadonly.processar_documento(pdf_bytes=...)`.
- **ESCRITA**: ZERO -- nenhuma escrita em nenhum sistema externo.
- **PII**: processado internamente só o necessário para granularidade
  (CPF do colaborador do Holerite, CNPJ do Extrato) -- nunca exibido/
  logado; `documento_id`/`tipo`/`estado` sanitizados nos resultados.

### STOP -- interromper e reportar, nunca prosseguir, se:

- schema divergente do já documentado acima;
- field id necessário não comprovado (FGTS/Guias/relação, já
  identificado -- por isso fora da amostra);
- attachment inesperado (mais de 1 por documento, formato não-PDF);
- mais de 2 documentos processados;
- qualquer tentativa de escrita;
- qualquer segredo exposto;
- qualquer conflito de schema não previsto;
- necessidade de nova regra de negócio;
- necessidade de migration;
- qualquer tentativa de usar o snapshot atual (`Status`/vínculo de
  hoje) como prova de vigência histórica -- UNIDADE_POSTO honestamente
  `NAO_ENCONTRADA` para Junho é o resultado ESPERADO, nunca um erro a
  corrigir com override.

## 11. Preservado

`app.py` intocado; nenhuma migration criada/aplicada/alterada; zero
acesso Airtable/Gmail live; zero escrita externa; `EscopoClientesFixo`/
`EscopoClientesAtivosDoCiclo`/`FonteUnidadePostoPrestacaoAirtableShadow`/
`FonteClienteDiretoDocumentoAirtableShadow` intocados (só compostos, nunca
alterados); `VINCULO` `NAO_APLICAVEL`; DCTF broadcast preservado; FGTS
client-level preservado, nunca broadcast.

## 12. Regressão

1370 passed (era 1363 antes do checkpoint final pré-merge; 1339 no
HEAD pós-merge do PR #109), 34 falhas/17 erros pré-existentes
idênticos ao baseline (pdfplumber/cryptography do sandbox), 6 skipped.
Testes novos totais desta missão: 16 (`test_magnata_os_classificacao_
orquestrador_corredor_readonly.py`) + 13 (`test_importacao_lote_
composicao_corredor_readonly.py`, incluindo os 5 casos E2E de
correlação same-run pela borda real + proteção de master + pacote
externo+local do checkpoint) + 2 (arquitetura, positive control) = 31.
`test_magnata_os_classificacao_arquitetura_sem_dependencia_airtable.py`:
7/7.
