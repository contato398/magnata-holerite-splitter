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
