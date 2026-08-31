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

## 9. `READY_FINAL`

- `MOTOR_LAB_READY = TRUE` — corredor + orquestrador funcionam
  ponta-a-ponta com fakes/Protocols puros (29 testes novos).
- `ORQUESTRADOR_REAL_EXISTE = TRUE` — os 2 módulos desta missão
  fecham o achado maior do ADR anterior.
- `ADAPTERS_REAIS_MONTAVEIS = TRUE` — `ExecucaoCorredorReadonly`
  instancia e compõe TODOS os adapters reais já construídos, provado
  com `Mock()` de leitor (nunca rede real).
- `EXECUCAO_LIVE_READONLY_TECNICAMENTE_POSSIVEL = TRUE` — pela
  primeira vez nesta sessão: um entrypoint real (`ExecucaoCorredorReadonly.
  processar_documento`) existe, aceita PDF real ou texto, monta os
  adapters reais, e devolve resultado composto -- sem precisar
  escrever código novo para rodar contra dado real (só injetar um
  `LeitorAirtableSomenteLeitura` real e chamar).
- `LIVE_AUTORIZADO = FALSE` (fixo pela missão).
- `LIVE_EXECUTADO = FALSE` (fixo pela missão).
- `AUTOMATED_PRESTACAO_READY = PARTIAL` — falta: persistência real de
  `dados_correlacao` (gate de schema, §12-I, inalterado); política de
  vigência de UNIDADE_POSTO para ciclo corrente (quem prova, quando);
  extração de PDF por página (para separação master automática real).
- `READY_FOR_LIVE_CORRIDOR_V2 = FALSE` — a definição desta flag,
  estabelecida em missões anteriores, é sobre AUTOMAÇÃO de produção
  completa, não sobre a possibilidade técnica de um ensaio read-only
  controlado (que agora é `TRUE`, item acima). Os 3 bloqueios que a
  mantêm `FALSE` (persistência de correlação, vigência de UNIDADE_
  POSTO, extração por página) são gates reais, nenhum dispensável por
  autonomia.

## 10. Plano live (§41 da missão) — não produzido

`EXECUCAO_LIVE_READONLY_TECNICAMENTE_POSSIVEL = TRUE`, mas o gate
literal da missão para produzir `PLANO_AUTORIZACAO_LIVE_SKY_V1` é
`READY_FOR_LIVE_CORRIDOR_V2 = TRUE` (§41: "se READY_FOR_LIVE_CORRIDOR_
V2 = TRUE: produzir plano"), que permanece `FALSE` (§9). Por isso este
documento NÃO produz o plano de autorização live -- nomeia só os
bloqueios reais restantes (§9), consistente com a mesma decisão já
tomada no ADR anterior (`corredor-live-v2-bloqueios-reais-v1.md` §6).

## 11. Preservado

`app.py` intocado; nenhuma migration criada/aplicada/alterada; zero
acesso Airtable/Gmail live; zero escrita externa; `EscopoClientesFixo`/
`EscopoClientesAtivosDoCiclo`/`FonteUnidadePostoPrestacaoAirtableShadow`/
`FonteClienteDiretoDocumentoAirtableShadow` intocados (só compostos, nunca
alterados); `VINCULO` `NAO_APLICAVEL`; DCTF broadcast preservado; FGTS
client-level preservado, nunca broadcast.

## 12. Regressão

1363 passed (era 1339 no HEAD pós-merge do PR #109), 34 falhas/17 erros
pré-existentes idênticos ao baseline (pdfplumber/cryptography do
sandbox), 6 skipped. Testes novos: 16 (`test_magnata_os_classificacao_
orquestrador_corredor_readonly.py`) + 6 (`test_importacao_lote_
composicao_corredor_readonly.py`) + 2 (arquitetura, positive control) =
24. `test_magnata_os_classificacao_arquitetura_sem_dependencia_
airtable.py`: 7/7.
