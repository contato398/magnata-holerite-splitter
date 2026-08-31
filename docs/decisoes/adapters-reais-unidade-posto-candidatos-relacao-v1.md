# Adapters Reais — UNIDADE_POSTO + Candidatos de Relação Documental — V1

Documento de decisão da missão macro "MESCLAR PR #107 + CONSTRUIR OS
DOIS ADAPTERS REAIS QUE BLOQUEIAM A PRIMEIRA VALIDAÇÃO LIVE —
`FonteUnidadePostoPrestacao` + `FonteCandidatosRelacaoDocumental`".
Fecha a seção 10 ("Pendência restante — adapters reais") de
`docs/decisoes/costura-relacao-documental-corredor-v1.md`.

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

**Temporalidade**: sem campo de vigência no schema (confirmado por
auditoria anterior), o adapter só responde pela competência CORRENTE
do ciclo, injetada via `ContextoCicloPrestacao` (já existente,
`competencia_esperada_prestacao.py` — nenhum contrato novo) — nunca lê
o relógio. Qualquer competência diferente da corrente devolve
`NAO_ENCONTRADA` com `MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA` (já
cadastrado desde o adendo pré-merge ao PR #106) — nunca `RESOLVIDA`
"com ressalva". Cardinalidade múltipla preservada (2+ postos legítimos
nunca colapsados a 1, provado por teste).

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

**Testado** (`test_airtable_unidade_posto_prestacao.py`, 6 casos, só
`LeitorFake` local, zero Airtable real): 1 posto resolve; 2 postos
preservam cardinalidade; sem local vinculado → `NAO_ENCONTRADA`;
competência histórica sem vigência → nunca resolve, nunca sequer
consulta o Airtable; competência corrente configurável (não hardcoded)
resolve; atravessa `resolver_unidade_posto_validado` (o mesmo
validador genérico já usado por qualquer fonte fake de teste) sem
ajuste algum.

## 3. `FonteCandidatosRelacaoDocumentalDoInventario` — descoberta REAL, correlação com pendência nomeada

`magnata_os/classificacao/fonte_candidatos_relacao_documental_do_inventario.py`.

Implementa `FonteCandidatosRelacaoDocumental` (Protocol, PR #106/#107)
por COMPOSIÇÃO de 2 Protocols já reais e já auditados — nenhuma tabela
Airtable nova, nenhuma suposição de schema não confirmada:

- `FonteClientesPrestacao.listar_ativos` — já tem adapter real de
  produção (`airtable_clientes_prestacao.py`);
- `FonteInventarioPrestacao.listar` — já tem adapters reais de
  produção (`airtable_inventario_prestacao.py`/`airtable_holerites_
  prestacao.py`, compostos por `FonteInventarioPrestacaoComposta`).

Varre cliente ativo × inventário daquele cliente na competência
pedida, filtra por `tipo_documental`, deduplica por `documento_id`
(um mesmo documento em 2+ clientes — vínculo múltiplo genuíno — tem
suas `referencias_logicas` UNIDAS, nunca tratado como 2 candidatos).
Isso é **100% real** — nenhuma parte desta descoberta depende de algo
que não existe hoje.

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
injetado no adapter. Sem uma implementação real desse Protocol, um
candidato descoberto continua tendo identidade REAL
(`documento_id`/`tipo_documental`/`referencias_logicas` genuínos), mas
`dados_correlacao` fica com os defaults vazios do dataclass — a
resolução de relação correspondente cai honestamente em
`NAO_ENCONTRADA` (evidência insuficiente), nunca finge ter evidência
que não tem. `FonteDadosCorrelacaoEmMemoria` (no mesmo módulo) é uma
referência local/piloto — mesmo padrão de `InventarioPrestacaoEmMemoria`
— nunca a fonte de registro de produção.

**A pendência que restava ("adapter de candidatos não existe") está
fechada.** A pendência NOVA, mais precisa, é menor: "não existe
armazenamento durável de `dados_correlacao` por `documento_id`" — um
gate de escopo/arquitetura para uma futura missão, não mais um adapter
inteiro faltando.

**Testado** (`test_magnata_os_classificacao_fonte_candidatos_relacao_
documental_do_inventario.py`, 8 casos, só fakes locais): descoberta
por tipo funciona e ignora outros tipos; nunca devolve o próprio
documento atual como candidato; documento em 2 clientes une
referências sem duplicar; dados de correlação vêm da fonte injetada
quando disponível; sem fonte injetada, fica honestamente vazio (nunca
inventado); nenhum cliente ativo devolve vazio; ordem determinística;
**integra direto em `corredor_relacao_documental.resolver_relacao_e_
avancar` sem NENHUM ajuste** — prova de que a costura automática do
PR #107 já funciona com um adapter real de descoberta, hoje.

## 4. Preservado (confirmado, nenhum arquivo tocado além do listado)

`vinculo_unidade_prestacao.py` (VINCULO continua `NAO_APLICAVEL`,
nenhuma fonte real criada para ele nesta missão — não foi pedido);
`perfil_aplicabilidade_documental.py`; `relacao_documental.py`;
`politica_consequencia_relacao_documental.py`; `corredor_relacao_
documental.py`; `app.py` intocado.

## 5. Regressão

1296 passed (era 1282), 34 falhas/17 erros pré-existentes idênticos ao
baseline (pdfplumber/cryptography do sandbox — nada relacionado).
`test_airtable_vinculos_prestacao.py` (7/7, zero mudança de
comportamento após a promoção de utilitários). Teste arquitetural
(zero Airtable) estendido ao novo módulo de composição
(`fonte_candidatos_relacao_documental_do_inventario`, que nunca importa
Airtable — só compõe Protocols).

## 6. Reavaliação de `READY_FOR_LIVE_CORRIDOR_V2`

Os 2 blocos EXPLICITAMENTE nomeados como bloqueio (`docs/decisoes/
costura-relacao-documental-corredor-v1.md`, seção 10) estão
**fechados**: existe hoje um adapter real para UNIDADE_POSTO (completo)
e um adapter real para descoberta de candidatos de relação (completo
para identidade; a correlação depende de uma pendência nova e menor,
seção 3 acima).

**Isso NÃO foi, nesta missão, uma reauditoria completa de todo o
corredor de validação live planejado** (`PLANO_VALIDACAO_LIVE_
CORREDOR_V2`: Holerite + Extrato + FGTS Guia). Em particular:
`cliente_direto` (usado por Extrato/FGTS Guia, granularidade cliente)
é responsabilidade de wiring da camada de intake (quem descobre a
origem do documento já resolvida a 1 cliente) — não fazia parte do
escopo desta missão (só os 2 adapters nomeados) e não foi re-verificado
aqui se essa wiring já está pronta para produção.

**`READY_FOR_LIVE_CORRIDOR_V2` permanece `FALSE` nesta entrega** — não
porque os 2 adapters pedidos não estejam prontos (estão), mas porque
declarar `TRUE` exigiria uma reavaliação explícita do corredor
completo (`cliente_direto` de Extrato/FGTS Guia incluído), e essa
reavaliação — como qualquer decisão que abre caminho para acesso live
— é, por desenho desta constituição, um checkpoint humano separado
(`/CLAUDE.md` §6), nunca uma inferência automática só porque 2
adapters específicos ficaram prontos. Recomendação registrada: pedir
explicitamente essa reavaliação como próximo passo, se o objetivo for
autorizar a primeira validação live.
