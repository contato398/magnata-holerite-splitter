# Adapters Reais — UNIDADE_POSTO + Candidatos de Relação Documental — V1

Documento de decisão da missão macro "MESCLAR PR #107 + CONSTRUIR OS
DOIS ADAPTERS REAIS QUE BLOQUEIAM A PRIMEIRA VALIDAÇÃO LIVE —
`FonteUnidadePostoPrestacao` + `FonteCandidatosRelacaoDocumental`".
Fecha a seção 10 ("Pendência restante — adapters reais") de
`docs/decisoes/costura-relacao-documental-corredor-v1.md`.

## 0. Correção pré-merge — "ADENDO PRÉ-MERGE — PR #108" (3 achados reais, não escondidos)

A primeira versão desta missão continha 3 erros reais, corrigidos
antes do merge — as seções 2/3/6 abaixo foram reescritas para refletir
o estado CORRIGIDO (o texto anterior não representa mais o código):

1. **Temporalidade do UNIDADE_POSTO confundida com o ciclo do runner.**
   O adapter usava `ContextoCicloPrestacao.competencia_base` ("qual
   competência este runner está processando") como se fosse prova de
   que o SNAPSHOT do Airtable é válido para aquela competência —
   conceitos diferentes, nunca equivalentes (um cliente com
   deslocamento, ex.: SKY Tatuí, processa o ciclo-base Julho mas a
   competência documental real é Junho; o snapshot corrente não prova
   Junho só porque o runner está processando Julho). Corrigido:
   `competencia_snapshot_comprovada`, um parâmetro NOVO e DESACOPLADO
   de `ContextoCicloPrestacao` — só a competência para a qual quem
   constrói o adapter tem prova real de vigência. Sem essa prova
   (`None`, default), toda resolução cai em `NAO_ENCONTRADA`.
2. **Universo de clientes da descoberta de candidatos amarrado a
   "ativos hoje".** `FonteCandidatosRelacaoDocumentalDoInventario`
   usava `FonteClientesPrestacao.listar_ativos` como universo de busca
   para QUALQUER competência — um cliente historicamente legítimo mas
   inativo hoje nunca seria encontrado. Corrigido: novo Protocol
   `FonteEscopoClientesPrestacao.escopo_para_competencia(competencia)`
   — o universo de clientes passa a ser resolvido POR competência,
   nunca fixo em "hoje". `EscopoClientesAtivosDoCiclo` (implementação
   de referência) só devolve os ativos quando a competência pedida é
   exatamente a corrente do ciclo — para qualquer outra, devolve vazio
   (nunca a lista de hoje disfarçada de histórico).
3. **`fonte_dados_correlacao` exigia um fake in-memory só para
   representar ausência.** Corrigido: parâmetro agora `Optional[...]
   = None` — nenhuma implementação precisa ser injetada só para dizer
   "não existe dado".

Nenhuma das 3 correções muda o que já estava correto: PR #107,
orientação A/B, relação genérica, benefícios, FGTS cliente-level, DCTF
broadcast, VINCULO `NAO_APLICAVEL`, zero Airtable no core e os
utilitários promovidos (`airtable_link_utils.py`) permanecem intocados.

## 1. Fase 0 — PR #107

PR #107 validado (aberto, base `main`, HEAD `b287d44` exato, mergeable
`clean`, CI verde nas 2 checks em cada um dos 3 commits, nenhum review
bloqueante, 3 commits — todos já conhecidos desta sessão, nenhum
inesperado) e **mesclado** (merge commit `60d0931`). `main` sincronizado
localmente (`git pull --ff-only`) — HEAD canônico
`60d09318641175157acab177293de3061f9059a3`. Branch nova:
`fix/adapters-reais-unidade-posto-candidatos-relacao-v1`.

## 2. `FonteUnidadePostoPrestacaoAirtableShadow` — COMPLETO

`magnata_os/documental/importacao_lote/adapters/airtable_unidade_posto_prestacao.py`.

Implementa `FonteUnidadePostoPrestacao` (Protocol, `vinculo_unidade_
prestacao.py`) sobre `LeitorAirtableSomenteLeitura` já existente,
lendo o MESMO link Funcionário→Local já lido por `FonteVinculosPrestacaoAirtableShadow`
(`TABLE_FUNC`/`F_FUNC_LOCAIS`, reaproveitados por import, nunca uma
segunda leitura com IDs redefinidos) — a diferença é resolver o
PRÓPRIO Local como UNIDADE_POSTO, nunca seguir até o Cliente.

**Temporalidade (corrigida, ver seção 0.1)**: sem campo de vigência no
schema (confirmado por auditoria anterior), o adapter só responde
quando quem o constrói fornece `competencia_snapshot_comprovada` —
um parâmetro NOVO, EXPLÍCITO e DESACOPLADO de `ContextoCicloPrestacao`
(que representa "qual competência o runner está processando", nunca
"para qual competência o snapshot é válido" — os dois nunca são
confundidos, nem no código nem no nome). Sem esse parâmetro (`None`,
default), ou para qualquer competência diferente da informada, devolve
`NAO_ENCONTRADA` com `MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA` (já
cadastrado desde o adendo pré-merge ao PR #106) — nunca `RESOLVIDA`
"com ressalva", nunca por coincidência de valores. Cardinalidade
múltipla preservada (2+ postos legítimos nunca colapsados a 1, provado
por teste). Caso SKY Tatuí (ciclo-base Julho/2026 → competência
documental Junho/2026 pela regra -1) explicitamente testado: vigência
comprovada só para Julho NUNCA resolve para Junho.

**Reuso, sem duplicação**: `_ids_vinculados`/`_escapar_formula`/
`_filtro_ids` (antes privadas de `airtable_vinculos_prestacao.py`)
promovidas para um módulo novo, neutro,
`airtable_link_utils.py` — mesmo princípio já usado no repositório para
`_extrair_texto_pdf` (promovida de `importacao_lote/orquestrador.py`
quando um segundo consumidor precisou dela). `airtable_vinculos_
prestacao.py` agora importa essas funções em vez de as redefinir —
zero mudança de comportamento (7/7 testes existentes continuam
passando sem alteração). Deliberadamente um módulo NOVO, não uma
edição de `airtable_leitura.py` (múltiplos consumidores já existentes,
disciplina própria documentada em seu CLAUDE.md) — menor superfície de
risco para esta promoção.

**Testado** (`test_airtable_unidade_posto_prestacao.py`, 7 casos, só
`LeitorFake` local, zero Airtable real) — casos A-E mapeados ao §18 do
adendo: (A) ciclo processado nunca é prova de vigência (sem
`competencia_snapshot_comprovada`, nunca resolve, nunca sequer
consulta o Airtable); (B) competência histórica sem vigência nunca
resolve; (C) SKY Tatuí — vigência comprovada só para Julho nunca
resolve Junho; (D) vigência comprovada para a competência exata
resolve; (E) 2 postos comprovados preservam cardinalidade. Mais: sem
local vinculado → `NAO_ENCONTRADA`; atravessa `resolver_unidade_posto_
validado` (o mesmo validador genérico já usado por qualquer fonte fake
de teste) sem ajuste algum.

## 3. `FonteCandidatosRelacaoDocumentalDoInventario` — descoberta REAL, correlação com pendência nomeada

`magnata_os/classificacao/fonte_candidatos_relacao_documental_do_inventario.py`.

Implementa `FonteCandidatosRelacaoDocumental` (Protocol, PR #106/#107)
por COMPOSIÇÃO de Protocols já reais e já auditados — nenhuma tabela
Airtable nova, nenhuma suposição de schema não confirmada:

- `FonteEscopoClientesPrestacao.escopo_para_competencia` — Protocol
  NOVO (corrigido, ver seção 0.2), resolvido POR competência, nunca
  fixo em "hoje". `EscopoClientesAtivosDoCiclo` (implementação de
  referência) usa `FonteClientesPrestacao.listar_ativos` (já tem
  adapter real de produção, `airtable_clientes_prestacao.py`) —
  documentada como válida SOMENTE quando a competência pedida é a
  corrente do próprio ciclo; para qualquer outra, devolve escopo
  vazio (nunca a lista de hoje disfarçada de histórico).
  `EscopoClientesFixo` é a alternativa para quando quem chama já tem
  um conjunto de clientes com proveniência temporal real.
- `FonteInventarioPrestacao.listar` — já tem adapters reais de
  produção (`airtable_inventario_prestacao.py`/`airtable_holerites_
  prestacao.py`, compostos por `FonteInventarioPrestacaoComposta`).

Varre o escopo de clientes (resolvido por competência) × inventário
daquele cliente na competência pedida, filtra por `tipo_documental`,
deduplica por `documento_id` (um mesmo documento em 2+ clientes —
vínculo múltiplo genuíno — tem suas `referencias_logicas` UNIDAS,
nunca tratado como 2 candidatos). A descoberta em si é **100% real**
— nenhuma parte depende de algo que não existe hoje; a CORREÇÃO da
seção 0.2 fecha, além disso, a perda de candidatos históricos que a
versão anterior tinha por usar "ativos hoje" incondicionalmente.

### Pendência honesta, nomeada e menor do que a anterior

`dados_correlacao` (identificador de pedido, valor total etc.) NUNCA
vem do inventário — `ItemInventarioPrestacao` nunca carrega esses
campos, por desenho (nunca PDF/texto bruto). Esses dados só existem no
momento em que o documento é processado (extraídos do próprio texto) e
hoje **não são persistidos em lugar nenhum** para consulta posterior —
não existe "banco de correlação" de produção, e criar um agora seria
uma mudança arquitetural fora do escopo pedido nesta missão (2
adapters, não uma nova capacidade de persistência).

Corrigido com honestidade estrutural, não com invenção: um Protocol
próprio e nomeado, `FonteDadosCorrelacaoDocumental` (`obter_dados_
correlacao(documento_id) -> Optional[DadosCorrelacaoDocumental]`),
**opcional** no construtor (corrigido, ver seção 0.3 — `Optional[...]
= None`, nunca exige injetar um fake só para representar ausência).
Sem uma implementação real desse Protocol, um candidato descoberto
continua tendo identidade REAL (`documento_id`/`tipo_documental`/
`referencias_logicas` genuínos), mas `dados_correlacao` fica com os
defaults vazios do dataclass — a resolução de relação correspondente
cai honestamente em `NAO_ENCONTRADA` (evidência insuficiente), nunca
finge ter evidência que não tem. `FonteDadosCorrelacaoEmMemoria` (no
mesmo módulo) é uma referência local/piloto — mesmo padrão de
`InventarioPrestacaoEmMemoria` — nunca a fonte de registro de
produção.

**A pendência que restava ("adapter de candidatos não existe") está
fechada.** A pendência NOVA, mais precisa, é menor: "não existe
armazenamento durável de `dados_correlacao` por `documento_id`" — um
gate de escopo/arquitetura para uma futura missão, não mais um adapter
inteiro faltando.

**Testado** (`test_magnata_os_classificacao_fonte_candidatos_relacao_
documental_do_inventario.py`, 11 casos, só fakes locais) — casos F-J
mapeados ao §18 do adendo: (F) cliente ativo no ciclo corrente
encontra candidato, e `EscopoClientesAtivosDoCiclo` devolve vazio para
qualquer outra competência (nunca ativos-hoje disfarçado de
histórico); (G) cliente HOJE INATIVO mas presente no escopo histórico
(`EscopoClientesFixo`) não é perdido — prova central da correção; (H)
sem `fonte_dados_correlacao` (nem informada), candidato é real mas
dados ficam honestamente vazios; (I) com correlação disponível, dados
chegam ao candidato; (J) documento em 2 clientes une referências, não
duplica. Mais: descoberta por tipo ignora outros tipos; nunca devolve
o próprio documento atual como candidato; escopo vazio devolve vazio;
ordem determinística; **integra direto em `corredor_relacao_
documental.resolver_relacao_e_avancar` sem NENHUM ajuste** — prova de
que a costura automática do PR #107 já funciona com um adapter real de
descoberta, hoje.

## 4. Preservado (confirmado, nenhum arquivo tocado além do listado)

`vinculo_unidade_prestacao.py` (VINCULO continua `NAO_APLICAVEL`,
nenhuma fonte real criada para ele nesta missão — não foi pedido);
`perfil_aplicabilidade_documental.py`; `relacao_documental.py`;
`politica_consequencia_relacao_documental.py`; `corredor_relacao_
documental.py`; `app.py` intocado.

## 5. Regressão

1300 passed (era 1282 antes desta missão; 1296 no meio do caminho,
antes da correção do adendo), 34 falhas/17 erros pré-existentes
idênticos ao baseline (pdfplumber/cryptography do sandbox — nada
relacionado). `test_airtable_vinculos_prestacao.py` (7/7, zero mudança
de comportamento após a promoção de utilitários). Teste arquitetural
(zero Airtable) estendido ao módulo de composição
(`fonte_candidatos_relacao_documental_do_inventario`, que nunca importa
Airtable — só compõe Protocols).

## 6. Reavaliação de `READY_FOR_LIVE_CORRIDOR_V2` — por família (§16 do adendo)

Não chamar de "completo em produção" algo que só está completo na
interface (§15 do adendo) — por isso a reavaliação abaixo é por
família, nunca um veredito único:

| Família | Estado | Motivo |
|---|---|---|
| **Holerite** | **PARTIAL** | CLIENTE via `FonteVinculosPrestacaoAirtableShadow` (real). UNIDADE_POSTO via `FonteUnidadePostoPrestacaoAirtableShadow` (real) — mas só resolve quando quem compõe o corredor fornecer `competencia_snapshot_comprovada` com prova real de vigência para a competência exata sendo processada; sem essa prova (caso comum para qualquer cliente com deslocamento tipo SKY), UNIDADE_POSTO fica `NAO_ENCONTRADA` e o Holerite não avança automaticamente. |
| **Extrato** | **BLOCKED** | Depende de `cliente_direto` (granularidade cliente) — auditoria (§17 do adendo) confirmou que NENHUM adapter real ou wiring de produção preenche esse campo hoje; toda ocorrência no repositório é em teste. Lacuna registrada, não fazia parte do escopo desta missão (só os 2 adapters nomeados). |
| **FGTS Guia** | **BLOCKED** | Mesma dependência de `cliente_direto` (ou separação por CNPJ) que o Extrato — mesma lacuna, mesmo motivo. |
| **Relação documental** (benefícios/FGTS comprovante/DCTF) | **BLOCKED** | Descoberta de candidato é real (`FonteCandidatosRelacaoDocumentalDoInventario`), mas: (a) depende de um `FonteEscopoClientesPrestacao` com proveniência temporal comprovada para a competência pedida — `EscopoClientesAtivosDoCiclo` só serve ao ciclo corrente; (b) `dados_correlacao` não tem fonte de produção (`FonteDadosCorrelacaoDocumental` sem implementação real) — sem os 2, a relação nunca resolve de verdade em produção, mesmo com identidade de candidato correta. |

**Auditoria `cliente_direto` (§17 do adendo)**: `grep` completo do
repositório por `cliente_direto=` confirma que o único preenchimento
real é `estrategia_por_cnpj_cliente` (`separacao_documental.py`, via o
hook `personalizar_contexto_do_grupo`) — usado quando um documento
MASTER é separado por CNPJ, uma identidade derivada da ESTRUTURA do
próprio documento (real, correta, já funciona hoje para essa via).
Para um Extrato/FGTS Guia que chega como documento ÚNICO (não separado
de um master), não existe nenhum adapter que resolva `cliente_direto`
a partir da origem de intake (email/upload já vinculado a um cliente
específico) — essa é uma lacuna real de produção, não um "já correto"
que essa missão precisasse preservar, e não foi corrigida aqui (fora
do escopo: 2 adapters nomeados, não uma terceira capacidade de
intake).

**`READY_FOR_LIVE_CORRIDOR_V2 = FALSE`** — não alterado automaticamente
por esta correção (§16 do adendo: "não mudar para TRUE nesta correção
automaticamente"). Nenhuma família do plano original (Holerite/
Extrato/FGTS Guia) está `READY` sem ressalva; a decisão de avançar
(seja para completar `cliente_direto`, seja para injetar
`competencia_snapshot_comprovada` real do Holerite) é um checkpoint
humano separado (`/CLAUDE.md` §6), nunca uma inferência automática.
