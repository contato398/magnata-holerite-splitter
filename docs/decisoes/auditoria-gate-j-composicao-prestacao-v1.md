# Auditoria Gate J — Composição real do Contexto da Prestação (V1)

- **Data:** 2026-09-23
- **Base auditada:** `origin/main` = `ff1aee5` (inclui o merge do PR #181)
- **Natureza:** auditoria somente leitura. Nenhum código de produção foi
  alterado, nenhuma migration aplicada, nenhum secret criado, nenhuma
  chamada a Airtable/Evolution/rede.
- **Ponto de partida:** o PR #181 não é reaberto. O Gate J começa onde ele
  terminou: `executar_prestacao_contato_ate_pending_shadow_v1` recebe um
  `ContextoComposicaoPrestacao` pronto, e ninguém em produção sabe
  construí-lo.

## 1. Conclusão

O Gate J **não é só "composition root ausente"**. É uma **combinação**:

| Categoria | Existe? |
|---|---|
| Wiring ausente | **Sim**: a aquisição não repassa ao corredor as fontes de resolução de colaborador/cliente/posto (§3.1) |
| Defeito de contrato já em `main` | **Sim**: `candidatos_colaborador` recebe tipos documentais em vez de candidatos (§3.1) |
| Fonte interna ausente | **Sim**: não há índice interno persistido documento ↔ cliente/competência/tipo/colaborador (§3.2) |
| Adapter ausente | **Sim**: vínculos, colaboradores esperados, clientes e candidatos a colaborador só têm adapter Airtable (§4) |
| Legado ainda indispensável | **Sim**: o vínculo holerite ↔ funcionário hoje só existe no Airtable (tabela Holerites, alimentada por `/processar-holerites` em `app.py`) |
| Configuração/composição ausente | Sim, mas é a parte **menor**: a infraestrutura pós-Prestação já tem composição por ambiente reutilizável (`distribuir_documento_v1.py::_compor_*_a_partir_do_ambiente`) |

**Consequência:** mesmo que alguém escrevesse hoje um composition root
completo usando apenas adapters existentes, o fluxo real produziria
**zero Ordens** para Holerite. Não há falha estrutural, mas o resultado
fica vazio por fail-closed.

## 2. Risco novo: o fluxo "provado" só foi provado com corredor substituído

Todos os testes que chegam a PENDING pela Prestação
(`test_wiring_prestacao_ate_distribuicao_documental_shadow.py`,
`test_integracao_prestacao_contato_ate_pending.py`,
`test_executar_prestacao_contato_ate_pending_shadow_v1.py`,
`test_executar_prestacao_contato_ate_pending_shadow_v1_real.py`) fazem
`patch` de `executar_documento_readonly` (e de `extrair_texto_seguro`).
A cadeia a jusante (Contato → Ordem → Orquestrador → PENDING) está
provada. **A aquisição/resolução real da Prestação nunca foi exercitada
até PRONTO.** Isso não invalida o PR #181, mas limita o que "fluxo já
provado" significa.

## 3. Evidência

### 3.1 Aquisição não injeta as fontes do corredor (provado empiricamente)

`composicao_ciclo_persistente_prestacao.py`, em `adquirir_por_necessidades`
(linhas ~651-669) e `_adquirir_inventario_via_corredor` (~467-485), monta
`ContextoExecucaoCorredorPrestacao` com:

- `candidatos_colaborador=contexto.tipos_obrigatorios_por_colaborador`:
  isso é uma tupla de **tipos documentais** (`str`). O corredor espera
  `CandidatoFuncionario` (`importacao_lote/contratos.py`). Resultado real:
  `AttributeError: 'str' object has no attribute 'cpf'` em
  `resolver_funcionario`, engolido como evento `corredor_falhou`. O
  documento é descartado.
- `fonte_vinculos=None`, `fonte_cliente_direto=None`,
  `fonte_unidade_posto=None`: fixos. `ContextoComposicaoPrestacao` não
  tem campo para injetá-los.

Prova com script efêmero, 100% sintético (fora do repositório), corredor
**real**, holerite sintético:

| Cenário | Resultado real |
|---|---|
| A) como a composição passa hoje | `AttributeError` (documento descartado) |
| B) candidato sintético correto, sem `fonte_vinculos` | `REVISAO_NECESSARIA`: CLIENTE `NAO_AVALIADA` |
| C) + `fonte_vinculos` sintética | `REVISAO_NECESSARIA`: UNIDADE_POSTO `NAO_AVALIADA` |
| D) + `fonte_unidade_posto` sintética | `RESOLVIDO_E_AVANCOU`, sem revisão humana |

Então o corredor real precisa de **3 fontes** que a composição hoje não
consegue receber: candidatos a colaborador, vínculos colaborador →
cliente e unidade/posto. Para documentos de granularidade cliente
(Extrato, FGTS, DCTFWeb, Guia), também falta `fonte_cliente_direto`.

Armadilha menor, de configuração: o default
`tipos_obrigatorios_por_colaborador = ('Holerite da Folha de Pagamento',)`
não bate com o vocabulário do motor (`TIPO_HOLERITE = 'Holerite'`). Todo
teste relevante sobrescreve esse valor.

### 3.2 Não existe fonte interna real de candidatos por necessidade

- `FonteCandidatosDocumentoInventarioInterna` existe e está correta, mas
  depende de um `FonteInventarioPrestacao` cujos `documento_id` sejam ids
  de `Documento` interno (`repositorio_documentos.buscar_por_id`).
- Todos os inventários reais existentes (`FonteInventarioHoleritesAirtableShadow`,
  `FonteInventarioPrestacaoAirtableShadow`) devolvem **record ids do
  Airtable**. Plugados ali, o resultado é zero candidatos (fail-closed).
- `ponte_prestacao_holerite.py` produz itens com `documento_id` interno,
  mas a partir de um DTO em memória da esteira (`servico_lote.py`), sem
  persistência e **sem nenhum caller de produção**.
- Nenhuma migration existente cria um índice documento ↔
  cliente/competência/tipo/colaborador. Tabelas existentes: `documentos`,
  `eventos_documentais`, `lotes_documentais`,
  `estados_esteira_documental`, `itens_importacao_lote`,
  `resolucao_documental_temporal` (ponto), alocação e contato.

## 4. Mapa de dependências

Formato: necessidade → implementação existente → origem atual → origem
canônica desejada → gap → solução mínima.

| # | Dependência | Implementação existente | Origem atual | Canônica desejada | Gap | Solução mínima |
|---|---|---|---|---|---|---|
| 1 | `fonte_clientes` | `FonteClientesPrestacaoAirtable` | Airtable (Clientes.Status) | cadastro interno de clientes | nenhuma fonte interna | **decisão**: aceitar Airtable read-only como fonte transitória ou criar cadastro interno |
| 2 | `fonte_requisitos` + `requisitos_base` | `FonteRequisitosPrestacaoCanonica` + `CADASTRO_REQUISITOS_PRESTACAO_V2` | interna (código) | idem | **nenhum** | reutilizar |
| 3 | `fonte_colaboradores_esperados` | `FonteColaboradoresEsperadosPrestacaoAirtableShadow` | Airtable (Cliente → Local → Funcionário Ativo) | alocação interna (`alocacao`/`vinculo_trabalhista`/`vigencia_cliente_por_posto`) | adapter interno ausente; estado de aplicação das migrations de alocação **não verificado** | **decisão** + adapter novo sobre `RepositorioAlocacao*` |
| 4 | `politica_competencia` / `competencias_por_cliente` | `POLITICA_COMPETENCIA_PRESTACAO_V1` | interna | idem | nenhum | reutilizar |
| 5 | `repositorio_execucoes` (Prestação) | `RepositorioExecucoesPrestacaoPostgres` (migration orquestrador 0005) | Postgres | idem | nenhum (e não é usado por `resultados_aquisicao_prontos_por_cliente`) | reutilizar |
| 6 | `fonte_inventario_base` | adapters Airtable shadow (Extrato/FGTS/Guias, Holerites) | Airtable | inventário interno | ids Airtable; serve para readiness, não para aquisição | **decisão** |
| 7 | `repositorio_documentos` / `armazenamento_arquivos` | `RepositorioDocumentosPostgres` / `ArmazenamentoArquivosS3` | Postgres/S3 | idem | nenhum (composição por ambiente já existe em `distribuir_documento_v1.py`) | reutilizar |
| 8 | `fonte_candidatos_por_necessidade` | `FonteCandidatosDocumentoInventarioInterna` | depende de um inventário com ids internos, que não existe | índice interno persistido | **fonte interna ausente** (provavelmente migration nova) | **gate**: migration/schema |
| 9 | candidatos a colaborador (corredor) | nenhum na composição (`CandidatoFuncionario` vem de `airtable_leitura.listar_funcionarios`) | Airtable (CPF/nome) | `identidade_colaborador_observada` (interna) | campo ausente no contexto; defeito §3.1 | **wiring** (campo) + **decisão** de fonte (PII) |
| 10 | `fonte_vinculos` (corredor) | `FonteVinculosPrestacaoAirtableShadow` | Airtable | alocação interna | campo ausente; adapter interno ausente | **wiring** + **decisão** |
| 11 | `fonte_unidade_posto` (corredor) | `resolver_unidade_posto_via_alocacao` (interna) + adapter Airtable | alocação interna / Airtable | alocação interna | campo ausente; adaptador de Protocol não verificado | **wiring** |
| 12 | `fonte_cliente_direto` (corredor) | `airtable_cliente_direto_documento.py` | Airtable | cadastro interno | campo ausente | **wiring** + **decisão** |
| 13 | Contato Canônico | `RepositorioContatoColaboradorPostgres` + resolvedor V1 | Postgres (migration 0004 **não aplicada**) | idem | Gates B/C/D/E | fora do Gate J |
| 14 | Infra do Orquestrador (execuções, autorizações, ações, materializador, assinatura) | `distribuir_documento_v1.py::_compor_*` | Postgres/ambiente | idem | nenhum | reutilizar |

## 5. Responsabilidades que o legado ainda cumpre sozinho

- Separar o PDF de holerites por funcionário e **vincular cada holerite
  ao funcionário** (tabela Holerites do Airtable, via `/processar-holerites`,
  `app.py`). O Magnata OS não reproduz esse vínculo em nenhum armazenamento
  interno persistido.
- Cadastro de clientes ativos e da relação Cliente → Local → Funcionário.
- Distribuição real (`/webhook/enviar-whatsapp`, `/whatsapp/enviar-*`):
  fora de escopo, intocada.

## 6. Composition roots existentes

- `magnata_os/documental/modulo01/composicao.py::construir_pipeline_modulo01`: ingestão Módulo 01.
- `magnata_os/orquestrador/ciclo_producao_v1.py`: ciclo do Orquestrador (conexão, S3, assinatura).
- `magnata_os/orquestrador/distribuir_documento_v1.py`: todas as dependências de infraestrutura pós-Ordem.
- `scripts/prestacao_readiness_shadow_real.py`: só readiness, 1 cliente, **fabrica** uma resolução. Não serve de base.
- `ciclo_piloto_prestacao.py`: runner dry-run sem composição concreta.

**Nenhum** deles compõe `ContextoComposicaoPrestacao`. Não há composition
root "pronto e desconectado" a religar.

## 7. Decisão desta auditoria

Nenhum código foi escrito. O gap não é pequeno nem inequivocamente
técnico. Ele exige decisões materiais que o `CLAUDE.md` §12-I reserva ao
humano:

1. **Fonte de colaborador/vínculo/posto/cliente**: Airtable read-only
   como fonte transitória **explícita** (nova dependência de runtime desta
   cadeia) ou adapters internos sobre alocação/identidade (depende do
   estado real das migrations de alocação, não verificado aqui).
2. **Índice interno documento ↔ necessidade** (item 8): quase certamente
   exige migration nova (Gate B/schema) e um produtor desse índice na
   ingestão.
3. **Correção do defeito §3.1**: é código de domínio de aquisição já em
   `main`. Muda o comportamento observável (a exceção vira resolução
   `NOT_FOUND`/`REVISAO`). É funcional, pequeno e reversível, mas é
   pré-requisito dos itens 1 e 2, não fecha o Gate J sozinho.

## 8. Incrementos propostos (nenhum autorizado)

- **J1, só código, reversível:** estender `ContextoComposicaoPrestacao`
  com campos opcionais (`candidatos_colaborador`, `fonte_vinculos`,
  `fonte_unidade_posto`, `fonte_cliente_direto`) e repassá-los em
  `adquirir_por_necessidades`. Corrigir o uso de
  `tipos_obrigatorios_por_colaborador` como candidatos. Testar com
  **corredor real** (sem `patch`) até PRONTO → PENDING, só com fontes
  em memória.
- **J2, decisão de fonte:** escolher Airtable-transitório ou interno para
  os itens 1, 3, 9, 10, 11 e 12.
- **J3, schema:** índice interno de candidatos por necessidade (migration
  nova, não aplicada) e seu produtor.
- **J4:** composition root por ambiente, reutilizando
  `distribuir_documento_v1.py::_compor_*`, só depois de J1-J3.

## 9. J1: escopo original (2026-09-24), autorizado pelo humano (commit 1)

**Decisão J2 provisória registrada (humano, mensagem distinta):** Airtable
pode continuar como fonte transitória declarada só onde o Magnata OS
ainda não reproduz a responsabilidade. Fonte interna canônica é
preferida quando existir. Adapter Airtable novo, se indispensável, fica
atrás dos Protocols existentes, como bridge transitório, nunca como
fonte de verdade. **O J1 não usa essa decisão:** ele não cria nem
consome nenhum adapter Airtable.

**Mudança** (`composicao_ciclo_persistente_prestacao.py`):
- `ContextoComposicaoPrestacao` ganha 4 campos opcionais, derivados dos
  contratos reais de `ContextoExecucaoCorredorPrestacao` →
  `ContextoResolucaoDocumentoPrestacao`, que são as fontes que resolvem
  dimensões:
  - `candidatos_colaborador: Tuple[CandidatoFuncionario, ...]`: validado
    em `__post_init__` (`TypeError` para qualquer outro tipo) e fora do
    `repr` (CPF);
  - `fonte_vinculos: FonteVinculosPrestacao`;
  - `fonte_unidade_posto: FonteUnidadePostoPrestacao`;
  - `fonte_cliente_direto: FonteClienteDiretoDocumento`.
  `fonte_candidatos_relacao` ficou de fora de propósito, porque não
  resolve dimensão.
- Novo helper `_contexto_corredor`: ponto único usado pelas 2 aquisições
  (`adquirir_por_necessidades` e a primitiva em bloco).
- **Terceiro defeito encontrado durante o J1:** `politica_competencia=None`
  (default do contexto) era repassado ao corredor junto com
  `cliente_do_ciclo`, e o corredor chamava `.competencia_esperada_para`
  em `None`. O resultado era `AttributeError` em **todo** documento de
  `adquirir_por_necessidades`, inclusive os de granularidade cliente.
  Correção: sem política informada, vale o default canônico que o
  próprio corredor declara (`POLITICA_COMPETENCIA_PRESTACAO_V1`).
- **Fixtures dos testes do #181 e anteriores:** as resoluções *fake* de
  Holerite em 4 arquivos
  (`test_wiring_prestacao_ate_distribuicao_documental_shadow.py`,
  `test_integracao_prestacao_contato_ate_pending.py`,
  `test_executar_prestacao_contato_ate_pending_shadow_v1.py`,
  `..._real.py`) não tinham a dimensão COLABORADOR, que o corredor real
  sempre produz para Holerite. A função recebia `colaborador` e o
  ignorava. A dimensão foi adicionada à fixture. Nenhuma asserção mudou.

**Prova:** `test_aquisicao_prestacao_corredor_real_j1.py`, com PDF
sintético real, extração real e corredor real, **sem nenhum `patch`**,
até PENDING, incluindo replay. Contra o código anterior ao J1, 11 dos
12 testes do escopo original falham.

## 10. Achado posterior da Ultrareview: fail-closed de elegibilidade (commit 2)

**O que foi achado.** `adquirir_por_necessidades` registra 1 resultado
por (necessidade, candidato) em **qualquer** estado do corredor. Isso é
correto para avaliar âncora. Mas `resultados_aquisicao_prontos_por_cliente`
repassava todos esses resultados à distribuição assim que o cliente
ficava PRONTO.

**Por que só apareceu depois do J1.** Antes, o corredor real quebrava em
todo documento, então nenhum resultado real chegava ali. O J1 tornou o
caminho alcançável. Provado com o corredor real: um candidato em
`REVISAO_NECESSARIA` foi selecionado para distribuição junto com o
documento válido. Um documento **resolvido para outro colaborador**, mas
devolvido como candidato para a necessidade do colaborador A, entraria
na Ordem de A. Ou seja, o documento de uma pessoa seria enviado a outra
(risco de LGPD).

**Por que fail-closed.** O filtro só retira e nunca reatribui. Não
existe cenário em que ele faça algo ser distribuído que antes não seria.
Correção: `_elegivel_para_distribuicao` só deixa passar documento
`RESOLVIDO_E_AVANCOU`, sem revisão humana, cuja resolução real confirme,
com valor único, o cliente e a competência da necessidade e também o
colaborador, quando a necessidade tiver um. O inelegível é omitido e
registrado (evento `documento_inelegivel_distribuicao`, só com ids).

**Prova:** testes específicos em `test_aquisicao_prestacao_corredor_real_j1.py`
(documento em revisão, documento de outro colaborador, documento válido
continua elegível e chega a PENDING). Sem o filtro, os 2 testes de
bloqueio falham.

## 11. Bloqueios abertos depois do J1 (não corrigidos)

**J1b: novo bloqueio, separado do J1. É pré-requisito de qualquer
cliente real.** `resultados_aquisicao_prontos_por_cliente` agrupa por
cliente/competência. O wiring de Prestação (protegido) exige 1
colaborador por Ordem (`ColaboradorDivergenteEntreDocumentos`). Um
cliente real com 2 ou mais colaboradores prontos gera **zero Ordens**
(erro isolado e logado). Um documento de granularidade cliente adquirido
junto (colaborador `None`) gera `ColaboradorAusenteNaNecessidade`.
Resolver isso exige decidir o agrupamento por colaborador a jusante da
aquisição.

Outros pontos:
1. O default `tipos_obrigatorios_por_colaborador =
   ('Holerite da Folha de Pagamento',)` não bate com o vocabulário do
   motor (`'Holerite'`). Todo composer real precisa informar
   `(TIPO_HOLERITE,)`. Não foi alterado para não mudar a semântica de
   quem usa o default.
2. Com a política default V1, a competência esperada de SKY Tatuí na
   aquisição é base−1, enquanto o ciclo usa `competencias_por_cliente`.
   Quem compõe precisa manter os dois coerentes.
3. Continuam abertos J2 (fontes reais), J3 (índice interno, migration),
   J4 (composition root por ambiente) e os gates B, C, D, E, G, H e I.

## 12. J1b: distribuição por colaborador (2026-09-24)

**Causa raiz do zero Ordens.** `executar_prestacao_ate_distribuicao_documental_shadow`
entregava o pacote do cliente inteiro (`resultados_aquisicao_prontos_por_cliente`)
a `montar_ordem_distribuicao_documental_de_prestacao`. Essa função, por
contrato, só aceita 1 colaborador por Ordem. Com 2 ou mais colaboradores,
ela levantava `ColaboradorDivergenteEntreDocumentos`. Com documento de
nível cliente junto, levantava `ColaboradorAusenteNaNecessidade`. Em
ambos os casos, o cliente inteiro era descartado. O resolvedor de
contato também assumia um grupo homogêneo (`resultados[0].necessidade.colaborador`).

**Unidade canônica de distribuição: cliente + competência + colaborador.**
Evidência:
- `OrdemDistribuicaoDocumental` tem `funcionario_id` e um único
  `destinatario`, e o `event_id` já os inclui.
- No legado, o envio individual `/webhook/enviar-whatsapp` (`app.py`) é
  por `funcionario_id` e só leva documentos individuais (`Holerite`,
  `Folha Ponto`).
- Documentos de nível cliente (guias, extratos, certidões) vão no pacote
  de **e-mail por cliente** (`/gerar-fila-envios-email`,
  `/webhook/enviar-email-cliente`), nunca ao colaborador.

**Solução (ESTENDER, sem contrato novo).**
- `_particionar_por_colaborador` e `resultados_aquisicao_prontos_por_colaborador`
  (`composicao_ciclo_persistente_prestacao.py`) mantêm o mesmo formato de
  trio, o mesmo gate de readiness **por cliente** e o mesmo filtro de
  elegibilidade do J1. Só particionam por `necessidade.colaborador`.
- O wiring da Prestação passa a iterar por colaborador (troca de 1
  chamada). O log de isolamento agora inclui o id opaco do colaborador.
- Resolvedor, `OrdemDistribuicaoDocumental`, núcleo genérico, Plano,
  Envelope e Orquestrador ficaram intocados.
- Resultado: N colaboradores prontos geram N Ordens de destinatário único
  e N `event_id` distintos.

**Documento de nível cliente.** Continua participando da readiness e do
pacote do cliente, mas **não entra em Ordem de colaborador**: não é
duplicado nem anexado a ninguém. A omissão é registrada (evento
`documento_nivel_cliente_fora_ordem_colaborador`). A distribuição desses
documentos ao cliente (equivalente ao pacote de e-mail do legado) é
outra capacidade e **continua aberta**. Nenhuma Ordem de cliente foi
inventada.

**Mesmo documento para 2 necessidades do mesmo colaborador:** aparece 1
vez na Ordem.

**Teste existente ajustado.**
`test_wiring_prestacao_ate_distribuicao_documental_shadow.py::test_erro_de_dominio_de_um_cliente_nao_impede_os_demais`
usava, como veículo do "erro de domínio", justamente 1 cliente com 2
colaboradores. Esse é o bloqueio do J1b, e agora produz 2 Ordens
legítimas. O veículo passou a ser 2 documentos do mesmo colaborador sob
preset unitário (`PoliticaAgrupamentoNaoSuportada`). A intenção do teste
(isolamento) é a mesma.

**Prova** (`test_aquisicao_prestacao_corredor_real_j1.py`, corredor real
sem `patch`):
- 1 colaborador: `event_id` idêntico ao caminho anterior;
- 2 e 3 colaboradores até PENDING;
- isolamento A/B, inclusive do contato resolvido;
- documento em revisão;
- readiness continua por cliente;
- Extrato fora das Ordens de colaborador;
- replay;
- troca de contato de B muda só a identidade de B;
- a ordem de listagem dos colaboradores não altera o resultado;
- deduplicação na partição.

Com o wiring anterior, 7 dos 11 testes J1b falham.

**Pontos abertos depois do J1b:**
1. **Distribuição de documento de nível cliente ao cliente** (pacote,
   equivalente ao e-mail do legado): capacidade nova, fora do J1b.
2. **Preset por colaborador com 2 ou mais documentos** (ex.: Holerite +
   Folha de Ponto): o resolvedor usa o preset fixo do chamador. Com o
   preset unitário, um colaborador com 2 documentos cai em
   `PoliticaAgrupamentoNaoSuportada`, erro isolado só daquele
   colaborador. Escolher o preset pelo conteúdo do grupo é decisão de
   política operacional.
3. A elegibilidade (J1) confere cliente, competência e colaborador, mas
   **não** o tipo documental da necessidade. Um documento do colaborador
   A pode satisfazer outra necessidade de A. Não há vazamento entre
   pessoas, mas vale um incremento próprio.

(Os itens 2 e 3 foram resolvidos no hardening da §13.)

## 13. J1b hardening: distribuição documental genérica por destinatário (2026-09-24)

### Cláusulas arquiteturais

> **A distribuição documental do Magnata OS é agnóstica ao tipo
> documental.** Tipos documentais pertencem às regras dos domínios e às
> políticas de elegibilidade, não à infraestrutura de distribuição nem
> ao canal.

> **Assinatura digital é uma modalidade/capacidade da distribuição, e
> não uma propriedade intrínseca de um tipo documental.**

### O que o legado mostrou
Evidência levantada por subagentes só de leitura:
- **Assinatura:** o núcleo e os presets decidem **só pela flag
  `exigir_assinatura` do preset**, indexado por `preset_id`, nunca por
  tipo. Os literais de tipo (`HOLERITE_FOLHA_PONTO`, `KIT_ADMISSAO`)
  aparecem só no adapter legado
  (`adapters/obrigacao_assinatura_legado_http.py`) e no `app.py`. Esse
  encapsulamento foi preservado.
- **N documentos:** o modelo estabelecido é **1 ação = 1 conteúdo = 1
  chamada Evolution = 1 Envelope**. O legado (`/webhook/enviar-whatsapp`)
  já envia N documentos como N chamadas. `montar_plano_disparo` gera 1
  ação por passo. O repositório e o executor já tratam N ações por
  evento, e `wiring_prestacao_orquestrador_postgres_shadow.py` já
  persiste todas as ações do plano.
- **Vocabulário de tipos:** a necessidade e o corredor usam as mesmas
  strings canônicas. A única tradução conhecida é
  `TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL`.

### Classificação do problema
Foi uma combinação de três limitações:

1. **Defeito no núcleo genérico (anterior ao J1b, com impacto
   operacional).** `materializar_distribuicao_documental_shadow`
   persistia só `plano.acoes[0]`. No ramo sem assinatura, com a
   composição `'separado'`, essa é a **ação de texto**: **o documento
   nunca virava ação executável nem Envelope**. Nenhum teste anterior
   (#179, #181, J1, J1b) conferia o conteúdo da ação.
   **Correção:** persistir **todas** as ações do plano, cada uma com seu
   Envelope, seguindo o padrão já existente. O ramo com assinatura
   continua com exatamente 1 ação (mensagem com link) e agora falha
   fechado se não tiver. `ResultadoDistribuicaoDocumentalShadow` ganha o
   campo aditivo `acoes_persistidas`; `acao_persistida` continua sendo a
   primeira ação.
2. **Política por cardinalidade ausente.** O ramo sem assinatura só
   aceitava N=1.
   **Correção:** nova política genérica `DOCUMENTOS_SEPARADOS`, que
   aceita 1..N documentos quaisquer sem assinatura, e novo preset
   `DOCUMENTOS_SEM_ASSINATURA`. Com assinatura, continua valendo a tabela
   V1 (o motor legado de assinatura agrupa no máximo 2 por link, e isso
   continua encapsulado no adapter). Nomes de arquivo duplicados na
   mesma Ordem falham fechado (`NomeDocumentoDuplicadoNaOrdem`).
3. **Elegibilidade da Prestação ("pessoa certa, documento errado").**
   `_tipo_resolvido_atende_necessidade` exige que o tipo resolvido pelo
   corredor, com valor único, seja o tipo da necessidade. A comparação é
   genérica e reaproveita a tradução canônica. É regra da Prestação: a
   camada genérica nunca olha o tipo. A partição passa a ordenar os
   documentos do grupo por (`documento_id`, `hash`), porque a posição
   faz parte do `event_id` e uma ordem diferente de candidatos geraria
   uma Ordem "nova" (replay duplicado).

**Sem mudança:** Ordem, Envelope, executor, Orquestrador, autorização e
fluxo pós-PENDING.

### Modelo adotado
A cadeia é necessidade → documento elegível (Prestação: pessoa +
cliente + competência + tipo) → partição por destinatário → política
(preset por `preset_id`: modalidade e cardinalidade) → Ordem de
destinatário único com 1..N documentos → evento → Orquestrador → plano →
N ações, cada uma com seu Envelope.

- **Documento de nível cliente:** continua fora das Ordens de
  colaborador (§12).
- **Escolha do preset:** continua sendo do chamador. O
  `DOCUMENTOS_SEM_ASSINATURA` serve para 1..N documentos, então dispensa
  lógica de preset por quantidade.

### Prova
**Testes com tipos arbitrários** (`DOCUMENTO_A..D`) nunca existiram na
empresa. Eles cobrem:
- 1 destinatário com 1 documento;
- 1 destinatário com N documentos;
- A recebe A/B e B recebe C/D, sem vazamento, incluindo o conteúdo das
  ações;
- pessoa certa com documento errado, com tipos arbitrários **e** com o
  corredor real;
- ordem de entrada;
- replay;
- mesmo tipo sob modalidades diferentes;
- núcleo com N = 1, 2, 3 e 5;
- a regressão do defeito do `acoes[0]`;
- não acoplamento (AST): nenhum literal de nome documental real no
  núcleo, nos presets, na partição nem na checagem de tipo. O scanner foi
  validado detectando os literais do adapter legado.

**Fluxo real até PENDING** (PDF real → extração → corredor → elegibilidade
→ readiness → partição → Ordem → Contato → evento → Orquestrador →
PENDING) continua provado com os tipos que o corredor real sabe
classificar. O corredor não classifica tipos arbitrários; a genericidade
da camada de distribuição é provada acima dele.

**Fixture de teste:** o PDF sintético passou a ser determinístico
(`set_creation_date`). Sem isso, testes de identidade entre 2 ambientes
dependiam do relógio.

### Pontos abertos
1. **Envio de documento de nível cliente ao cliente** (pacote): continua
   aberto (§12).
2. **Assinatura para N > 2 documentos, ou para 2 documentos fora do
   pacote legado:** limitação do motor legado de assinatura, encapsulada
   no adapter e fail-closed. Generalizar isso é trabalho do domínio de
   assinatura e é pós-PENDING.
3. **Mudança única de identidade:** a ordenação dos documentos do grupo
   muda **uma vez** o `event_id` de grupos com 2 ou mais documentos
   cuja ordem anterior era diferente. Isso afeta só dados shadow
   gerados pelo commit `1185be9`, que nunca foi publicado. Em 1
   documento nada muda.
4. **CLI `distribuir_documento_v1`:** continua exibindo só o
   `acao_execucao_id` da primeira ação (texto). É informativo; os ids
   das ações de documento estão em `acoes_persistidas`.
5. **Canal:** os presets atuais são de WhatsApp. Outro canal é outro
   preset e outro executor; nada na Ordem nem no núcleo depende do canal
   além do valor opaco.

## 14. Prestação upstream real: fechamento operacional (2026-09-25)

- **Base:** `main` @ `de69fb2` (Gate 3 mesclado).
- **Branch:** `fix/prestacao-upstream-real-v1`. A missão pedia `feat/prestacao-upstream-real-v1`, mas o gate de governança só aceita `feat/*` enumerado em `.magnata/patterns.sh`, e todas as entregas anteriores usaram `fix/<slug>`. Divergência registrada; nenhuma alteração de governança.
- **Resultado:** **gate material no J3.** A parte independente foi entregue: o pacote/intenção de nível cliente.

### 14.1 Mapa J2: fonte de cada responsabilidade

Aplicada a decisão provisória do §9: fonte interna quando ela existe *de verdade*, Airtable read-only transitório atrás do Protocol quando não existe. "Existe de verdade" quer dizer tabela aplicada **e** produtor real gravando nela.

| Responsabilidade | Fonte antes | Fonte depois | Situação |
|---|---|---|---|
| clientes ativos | `FonteClientesPrestacaoAirtable` (não ligado) | igual | transitória. Não há cadastro interno de cliente; exige migration |
| requisitos | `FonteRequisitosPrestacaoCanonica` + `CADASTRO_REQUISITOS_PRESTACAO_V2` | igual | **canônica** |
| colaboradores esperados | `FonteColaboradoresEsperadosPrestacaoAirtableShadow` | igual | transitória. As tabelas de alocação existem, mas falta a consulta reversa por cliente e **não há produtor** de `vigencia_cliente_por_posto` |
| vínculo colaborador → cliente | `FonteVinculosPrestacaoAirtableShadow` | igual | transitória. Mesmo motivo; nenhum adapter interno implementa `resolver_clientes` |
| unidade/posto | adapter Airtable + `FonteUnidadePostoPrestacaoComPrioridadeHistorica` | igual | canônica **no código**, sem dados: a alocação não tem produtor real |
| identidade (universo do corredor) | `LeitorAirtableSomenteLeitura.listar_funcionarios` | igual | transitória. O interno guarda só o HMAC do CPF; trocar é mudança funcional |
| contato | `RepositorioContatoColaboradorPostgres` | igual | **canônica** no código. Operacionalmente depende da migration alocacao/0004 e do bootstrap |
| inventário | adapters Airtable (ids Airtable) | igual | transitória, só para readiness. Não serve para aquisição |
| documento candidato por necessidade | `None` em produção | igual | **gate J3** (§14.2) |
| cliente direto do documento | `FonteClienteDiretoDocumentoAirtableShadow` | igual | transitória. Não há cadastro interno de cliente/CNPJ |

Nesta missão nenhuma troca foi feita: onde havia fonte interna, faltava produtor ou dado, e trocar teria sido declarar "canônico" o que está vazio. Nenhuma dependência nova do Airtable foi criada. O domínio (`classificacao`) continua sem importar Airtable (`test_magnata_os_classificacao_arquitetura_sem_dependencia_airtable.py`).

### 14.2 J3: índice documento ↔ necessidade. Gate material

**Não é derivável** com o que é persistido hoje. Nenhuma tabela escrita por produtor real guarda, por `documento_id` interno, os cinco atributos de que a necessidade precisa: cliente, competência, tipo, colaborador e elegibilidade.

| Atributo | Onde está persistido | Produtor real |
|---|---|---|
| tipo | `resolucao_documental_temporal.tipo_documental` (modulo01/0010); `itens_importacao_lote` (0009); evento `IMPORTACAO_LOTE_ITEM_ESCRITO` | nenhum. `executar_escrita_do_lote` só é chamado em testes. A esteira calcula o tipo e grava só etapa/situação |
| competência | `resolucao_documental_temporal.competencia` | nenhum |
| colaborador | `resolucao_documental_temporal.colaborador_id` | nenhum. O id vigente é o record-id do Airtable |
| cliente | **nenhuma coluna**. A 0010 exclui cliente por decisão e o deriva por alocação, o que não serve para documento de nível cliente | — |
| elegibilidade | `estados_esteira_documental` (0006) | sim (esteira), mas não diz a qual necessidade o documento atende |

Todo inventário real devolve record-id do Airtable como `documento_id`. Por isso `FonteCandidatosDocumentoInventarioInterna` produz zero candidatos (fail-closed, correto). Usar record-id do Airtable como documento interno está proibido.

**Recomendação mínima (não executada):**
1. **Produtor, só código:** em `ServicoCriacaoLote._processar_um_arquivo`, depois do gate de classificação (e de identificação, para documento de colaborador), gravar em `resolucao_documental_temporal` via `RepositorioResolucaoTemporalPostgres.salvar_com_evento`. Esse caminho já é idempotente (UNIQUE `documento_id` + CAS + evento atômico).
2. **Consumidor, só código:** um adapter Postgres de `FonteCandidatosDocumentaisPorNecessidade` com `resolucao_documental_temporal ⋈ estados_esteira_documental`, filtrando tipo, competência, colaborador, `RESOLVIDA` e `CONCLUIDO` sem bloqueio. O cliente vem pela alocação (vigências) e o documento por `RepositorioDocumentosPostgres.buscar_por_id`.
3. **Schema (gate):** cliente do documento de nível cliente, que contraria o comentário da 0010 e por isso exige ADR. Duas opções: coluna `cliente_id` anulável numa migration 0011, ou tabela própria `resolucao_documental_cliente_direto` por `documento_id`. Opcionalmente, estado por dimensão. Ambas são aditivas e reversíveis com SQL de rollback, no padrão 0009/0010.
4. **Backfill:** reler o binário do S3 por hash e rodar o mesmo resolvedor. É idempotente por `salvar_com_evento`, mas é backfill real, logo gate.
5. **Pré-requisitos:** aplicar a 0010 (e a 0011) no banco real, gate de produção. Decidir o `colaborador_id` canônico versus o `func_id` do Airtable (J2 identidade).

### 14.3 Pacote/intenção de nível cliente (entregue)

- **Problema:** até aqui o documento sem colaborador ficava fora da Ordem de colaborador (correto) e não virava nada (só WARNING).
- **Onde:** extensão de `pacote_prestacao.py` (REUTILIZAR > ESTENDER > CRIAR).
- **Conceitos:**
  - `IntencaoDistribuicaoCliente`: `cliente + competência + papel_destinatario + documentos`. Não tem `funcionario_id`, endereço nem canal. `intencao_id` é determinístico.
  - `DocumentoIntencaoCliente`: `documento_id + hash + tipos das necessidades atendidas`. O mesmo documento aparece uma vez.
  - `PapelDestinatarioOrganizacional.CLIENTE_INSTITUCIONAL`: é papel, não endereço.
- **Composição** (`composicao_ciclo_persistente_prestacao.py`): `_separar_nivel_cliente`, `particionar_nivel_cliente`, `resultados_aquisicao_prontos_nivel_cliente`, `intencoes_distribuicao_cliente_de_trios` e `intencoes_distribuicao_cliente_prontas`.
  - `particionar_nivel_cliente` e `intencoes_distribuicao_cliente_de_trios` recebem trios já calculados. Assim um composition root deriva Ordens e intenções do **mesmo** snapshot de readiness, sem rodar o ciclo duas vezes.
  - Usam o **mesmo** gate de readiness por cliente e a **mesma** elegibilidade (`resultados_aquisicao_prontos_por_cliente` + `_elegivel_para_distribuicao`); nenhuma regra paralela.
- **Regras:**
  - A granularidade vem da necessidade (`colaborador is None`). Não existe lista de tipos: nenhum literal de nome documental, com teste AST.
  - Documento com granularidade de pessoa nunca entra no pacote do cliente. Recebe o evento `documento_com_colaborador_fora_intencao_cliente`.
    - Critério fail-closed: a dimensão COLABORADOR existe na resolução em qualquer estado diferente de `NAO_APLICAVEL` (confirmada, ambígua ou não encontrada), ou a resolução está ausente.
  - A partição por colaborador não mudou: documento de cliente continua fora de toda Ordem de colaborador.
  - Isolamento: erro de domínio de um cliente gera `cliente_falhou_intencao_distribuicao` e os demais seguem; erro sistêmico propaga.
- **Para na intenção.** Não há Orquestrador, evento, preview nem transporte. Motivos:
  - Não existe fonte canônica de destinatário do cliente. Os campos `Email`/`Email Contador` da tabela Clientes existem só no legado (`app.py`/Airtable).
  - Não existe executor de canal para cliente; o único é WhatsApp, e documento de cliente não é adaptado artificialmente a ele.
  - `OrdemDistribuicaoDocumental` é por contrato de um colaborador, e reusá-la com `funcionario_id` falso seria fabricação.
- **Gate de dado operacional:** a fonte de destinatário do cliente (Protocol novo, transitório sobre Airtable ou interno) e a política de canal (e-mail é só o precedente legado) são o próximo passo. Um contrato de Ordem sem `funcionario_id` exige ADR.

### 14.4 Readiness real

Coberta pela suíte existente, sem mudança de regra:

| Caso | Onde está coberto |
|---|---|
| universais / condicionais | `test_magnata_os_classificacao_cadastro_requisitos_prestacao.py` |
| cardinalidade por colaborador | `combinar_pacote_com_obrigatoriedade_documental` e testes |
| ausente → FALTANDO/INCOMPLETO | suíte de readiness |
| revisão → EM_REVISAO | suíte de readiness |
| outro cliente | `inventario_de_outro_cliente` → REVISAR |
| competência errada | DIVERGENTE/BLOQUEADO |
| tipo errado / outro colaborador (elegibilidade) | J1/J1b (`_tipo_resolvido_atende_necessidade`, `_elegivel_para_distribuicao`) |

`PRONTO` exige resolução real (âncora) e todos os requisitos presentes. Sem J3, nenhum cliente real chega a PRONTO: fica REVISAR (`sem_evidencia_documental_real`), fail-closed.

### 14.5 Composition root e piloto shadow real: bloqueados pelo J3

Composição mínima identificada, sem runner paralelo: estender `executar_prestacao_contato_ate_pending_shadow_v1.py`, que já compõe o Contato por ambiente, com:
- uma função **a criar**, `compor_contexto_composicao_prestacao_a_partir_do_ambiente` (ainda não existe);
- os composers de `distribuir_documento_v1`/`ciclo_producao_v1`, com `materializador=None` (o materializador legado **escreve** no Airtable) e sem assinatura.

Sem `fonte_candidatos_por_necessidade` real, essa composição roda de ponta a ponta e produz **zero** Ordens e zero intenções. Montá-la agora seria entregar um runner que nunca faz nada. O piloto shadow com documentos reais também depende do índice. Nenhum dos dois foi criado.

### 14.6 Dependências do Airtable remanescentes

- **Substituídas:** nenhuma nesta missão.
- **Já canônicas antes desta missão:** requisitos e contato (no código).
- **Transitórias atrás de Protocol:** clientes, colaboradores esperados, vínculo, identidade (universo do corredor), inventário para readiness, cliente direto e destinatário do cliente (só legado).
- **Plano de remoção:**
  1. J3 (índice + produtor na ingestão).
  2. Produtor real de alocação/vigência cliente-posto, que libera vínculo, colaboradores esperados e unidade/posto internos.
  3. Cadastro interno de cliente/CNPJ + destinatários do cliente, que libera clientes, cliente direto e destinatário.
  4. Identidade canônica de colaborador (decisão sobre `func_id`).

Nenhuma bridge foi removida sem substituto.

### 14.7 Riscos declarados

- `resultados_aquisicao_prontos_por_cliente` omite o cliente PRONTO sem aquisição própria nesta execução. Documentos de nível cliente que estejam só no inventário base (ids Airtable) nunca viram intenção; é o mesmo gap do J3.
- Deriva de vocabulário: o default `tipos_obrigatorios_por_colaborador='Holerite da Folha de Pagamento'` difere de `TIPO_HOLERITE='Holerite'` (§11). Sem `fonte_colaboradores_esperados`, um tipo de colaborador vira necessidade sem colaborador. A guarda nova impede que ele entre no pacote do cliente se a resolução confirmar colaborador, mas o composition root real precisa passar os tipos certos.
- **A intenção pode ser subconjunto do pacote:** contém só os documentos adquiridos nesta execução. Se a readiness do cliente dependeu de documento que está só no inventário base, esse documento não entra. Isso está declarado no docstring de `intencoes_distribuicao_cliente_prontas`. Fecha junto com o J3.
- **Candidatos duplicados:** dois documentos distintos que resolvem para a mesma necessidade de nível cliente entram os dois na intenção. É o mesmo comportamento das Ordens, sem regressão. No pacote do cliente isso significa possível entrega duplicada; a deduplicação por necessidade é decisão do consumidor da intenção.
- `tipos_documentais` faz parte do `intencao_id`: mudança de vocabulário muda a identidade para os mesmos documentos físicos.
- Certidões não aparecem em nenhum requisito. A granularidade de DCTFWeb (`broadcast_estrutural`, `clientes_broadcast=()`) provavelmente nunca fica elegível. Isso não foi alterado.
