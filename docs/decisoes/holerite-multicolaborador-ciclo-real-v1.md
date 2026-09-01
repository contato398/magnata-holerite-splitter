# Holerite Multicolaborador no Ciclo Real — V1

Documento de decisão da missão "HOLERITE MULTICOLABORADOR NO CICLO
REAL". Contexto: o primeiro live real do corredor V2 (Extrato Mensal,
SKY Tatuí, Junho/2026) foi bem-sucedido; o Holerite ficou bloqueado
porque a execução live encontrou 8 registros candidatos no mesmo
local/competência e tratou isso como ambiguidade a resolver ("escolher
1 entre N"), em vez de processar. Branch:
`fix/holerite-multicolaborador-ciclo-real`.

## FASE 1 — Auditoria e prova da cardinalidade

Auditados, com evidência de código e teste, antes de qualquer mudança:

1. **Modelagem do Holerite hoje** (`perfil_aplicabilidade_documental.py`):
   Holerite é `_perfil_granularidade_colaborador` — COLABORADOR é
   `OBRIGATORIA`/cardinalidade `(1,1)` **por documento** (1 Holerite = 1
   colaborador); CLIENTE é `OBRIGATORIA`/cardinalidade `(1,None)` (um
   colaborador pode ter vínculo com mais de 1 cliente na competência —
   gera 1 item por cliente, nunca escolhe 1). Nenhuma regra de
   cardinalidade "1 por cliente/competência" existe nem nunca existiu
   para Holerite — a única cardinalidade fixa em 1 é por-documento
   (1 documento ↔ 1 colaborador), nunca por-cliente.
2. **Conceito de colaboradores esperados**: já existe, protocolo pronto
   (`fonte_colaboradores_esperados_prestacao.FonteColaboradoresEsperadosPrestacao`)
   desde a missão "CADASTRO CANÔNICO REAL DE REQUISITOS DA PRESTAÇÃO".
3. **`FonteColaboradoresEsperadosPrestacaoAirtableShadow`**
   (`airtable_colaboradores_esperados_prestacao.py`): adapter real já
   existente — Cliente → Locais (`F_LOCAL_CLIENTE`) → Funcionários
   (`F_FUNC_LOCAIS`) com Status=Ativo (`F_FUNC_STATUS`). Já testado
   exaustivamente (`test_airtable_colaboradores_esperados_prestacao.py`,
   11 casos: inativo excluído, cliente errado excluído, dedupe por
   vínculo a 2 locais do mesmo cliente, nenhum campo de PII solicitado,
   superfície só-leitura). **Nunca chamado com Airtable live antes desta
   missão** (docstring do próprio arquivo já registrava isso) e **nunca
   wired em `ExecucaoCorredorReadonly`** (a composição de borda usada
   pelo live) — esse é o gap real.
4. **Um cliente/competência espera N holerites, um por colaborador**:
   confirmado por `holerite_obrigatorio_prestacao.avaliar_obrigatoriedade_holerite`
   (já existente) — compara `colaboradores_esperados` contra o
   inventário e devolve `colaboradores_com_holerite`/`colaboradores_faltantes`,
   nunca uma contagem agregada do tipo. Já testado com 9 casos
   (`test_magnata_os_classificacao_holerite_obrigatorio_prestacao.py`),
   incluindo E2E com 4 colaboradores esperados/3 presentes → 1
   necessidade específica.
5. **"8 candidatos" era falha de composição da execução live anterior,
   não necessidade legítima de escolher 1** — **CONFIRMADO**. O script
   ad hoc daquele live nunca consultou `FonteColaboradoresEsperadosPrestacaoAirtableShadow`;
   tratou "8 registros de Holerite para 8 funcionários do mesmo local"
   como "8 candidatos para 1 vaga", quando na verdade cada um é um
   documento legítimo e independente, de um colaborador diferente.
6. **Lógica reutilizável Holerite → colaborador → cliente/unidade →
   competência**: já existe por inteiro —
   `resolucao_documento_prestacao.py` (colaborador via CPF,
   UNIDADE_POSTO via `FonteUnidadePostoPrestacaoAirtableShadow`, cliente
   via `FonteVinculosPrestacaoAirtableShadow`) — nada disso foi
   reimplementado nesta missão.
7. **Temporalidade/evidência de vínculo**: gap já registrado e honesto
   (docstring de `airtable_colaboradores_esperados_prestacao.py`) — não
   existe campo de vigência período (início/fim) no schema auditado;
   "esperado nesta competência" é aproximado por "vinculado a um Local
   deste cliente E Status atual = Ativo". Mesma aproximação já usada por
   `FonteVinculosPrestacaoAirtableShadow`/`FonteUnidadePostoPrestacaoAirtableShadow`
   em toda leitura de vínculo deste módulo. **Não é uma lacuna nova
   desta missão** — continua registrada, não escondida, e não foi
   resolvida por inferência aqui (se um cliente real mostrar essa
   aproximação insuficiente, é decisão humana nova).

### Conclusão objetiva

```
CARDINALIDADE_CANONICA_HOLERITE = 1:N
  (1 documento por colaborador; N colaboradores esperados por
  cliente/unidade/competência -> N holerites esperados, cada um com
  identidade própria)
ESCOLHER_1_ENTRE_N_E_CORRETO = FALSE
EVIDENCIA_CANONICA_EXISTENTE = SUFICIENTE
  (protocolo + adapter real + avaliação pura + composição pura de
  ciclo -- `ciclo_prestacao.executar_ciclo_prestacao` -- já existem e já
  são testados; o único gap real era a AUSÊNCIA de wiring na
  composição de BORDA usada pelo live, nunca uma regra de negócio
  faltando)
```

Evidência suficiente e nenhuma regra de negócio nova exigida → FASE 2
prossegue (o próprio gate da missão: "se a evidência for insuficiente
ou exigir invenção de regra, pare e reporte" não se aplica aqui).

## FASE 2 — Implementação (mínima, justificada pela auditoria)

**Nenhuma regra de negócio nova. Nenhum pipeline paralelo.** Uma única
mudança, aditiva: `ExecucaoCorredorReadonly` (`composicao_corredor_readonly.py`)
passa a expor `fonte_colaboradores_esperados` (property), wired ao
MESMO `leitor` desta execução — reaproveitando
`FonteColaboradoresEsperadosPrestacaoAirtableShadow` tal como já
existia (zero linha de lógica de negócio nova). Mesmo padrão já usado
por `fonte_inventario_completa` (property análoga, já existente).

Uso pretendido, depois de processar os N documentos do ciclo (nunca
dentro de `processar_documento`, que é por-documento — a avaliação de
completude é por-CICLO):

```python
colaboradores = execucao.fonte_colaboradores_esperados.colaboradores_esperados_para(cliente, ciclo)
inventario = execucao.fonte_inventario_completa.listar(cliente, competencia)
resultado_holerite = avaliar_obrigatoriedade_holerite(cliente, competencia, colaboradores, inventario)
pacote = combinar_pacote_com_holerite(pacote, resultado_holerite)
```

Mesma composição que `ciclo_prestacao.executar_ciclo_prestacao` já faz
na camada pura — agora também disponível na borda real, sem duplicar a
lógica em nenhum lugar.

**Cada Holerite processado via `processar_documento` mantém identidade
própria** (nenhuma fusão, nenhum "documento master fabricado"). Dedupe
lógico já garantido, sem alteração, por
`FonteInventarioPrestacaoComposta` (`identidade_logica` =
`documento_id`+`cliente`+`colaborador`). Vínculo histórico continua
exigindo a mesma prova já em vigor (`competencia_snapshot_comprovada`
para UNIDADE_POSTO; Status=Ativo para colaboradores esperados) — nada
promovido a verdade sem essa prova.

Adicional de higiene, fora do escopo de negócio: `.venv/` (ambiente
virtual local usado para rodar a suíte nesta missão) adicionado ao
`.gitignore` — nunca deveria ser rastreado.

## FASE 3 — Testes adversariais (borda real, `Mock()` de leitor)

4 testes novos em `test_importacao_lote_composicao_corredor_readonly.py`,
mesma disciplina já estabelecida no arquivo (zero fake de domínio, só
`Mock()` do transporte Airtable):

1. `test_fonte_colaboradores_esperados_via_borda_real_bate_com_holerites_processados`
   — N=2 esperados ativos, 1 inativo no mesmo local corretamente
   excluído; 2 Holerites processados, cada um com identidade própria;
   `avaliar_obrigatoriedade_holerite` fecha completo.
2. `test_colaborador_esperado_sem_holerite_processado_rebaixa_pacote_pronto_para_incompleto`
   — 3 esperados, só 2 processados; pacote (que partiria PRONTO)
   corretamente rebaixado para INCOMPLETO, colaborador certo apontado
   como faltante — nunca first-match, nunca um palpite.
3. `test_colaborador_de_outro_cliente_nunca_conta_para_obrigatoriedade_do_cliente_a`
   — fail-safe de identidade cruzada: colaborador de um local do
   CLIENTE B nunca aparece como esperado nem presente para o CLIENTE A,
   mesmo com seu Holerite processado na mesma execução (continua
   corretamente contabilizado para B).
4. `test_holerite_reprocessado_para_mesmo_colaborador_via_borda_nao_duplica_nem_infla_obrigatoriedade`
   — idempotência (mesma disciplina já provada para Extrato) aplicada
   ao Holerite: reprocessar não duplica nem infla a avaliação de
   obrigatoriedade.

Os demais itens do checklist da missão já tinham cobertura real
pré-existente, auditada e não duplicada aqui (evitar suíte inflada por
teste redundante):

- N esperados → N holerites válidos / colaborador sem holerite →
  ausência apontada / vínculo a 2 clientes → 1 holerite por cliente,
  nunca duplicado: `test_magnata_os_classificacao_holerite_obrigatorio_prestacao.py`
  (9 casos, incl. 2 E2E).
- Funcionário inativo/de outro cliente nunca esperado, vínculo a 2
  locais do mesmo cliente nunca duplica, nenhum campo de PII solicitado:
  `test_airtable_colaboradores_esperados_prestacao.py` (11 casos).
- Competência errada rejeitada, vínculo/UNIDADE_POSTO sem prova
  temporal nunca inferido:
  `test_sky_ciclo_base_julho_snapshot_comprovado_julho_unidade_posto_junho_nao_encontrada`
  (já existente neste mesmo arquivo).
- Documento sem evidência suficiente → revisão: cobertura já existente
  em `resolucao_documento_prestacao.py`/testes do motor semântico
  (`REVISAO_NECESSARIA` quando dimensão obrigatória não resolve).

## FASE 4 — Duas revisões adversariais

**Primeira passagem (arquitetura, semântica, temporalidade,
cardinalidade, segurança, não-regressão):** nenhum contrato alterado;
nenhuma tabela/campo novo; nenhuma regra de competência/vigência
tocada; `fonte_colaboradores_esperados` é só uma property nova
(getter), zero mutação de estado, zero I/O na construção (o adapter
real só consulta quando `colaboradores_esperados_para` é chamado
explicitamente); nenhuma chamada automática nova a Airtable dentro de
`processar_documento` (a fonte fica disponível, mas não é consultada a
não ser que quem orquestra peça). Nenhuma regressão nos 17 testes
deste arquivo (13 pré-existentes + 4 novos, todos verdes).

**Segunda passagem (composição real, identidade, dedupe, fail-safe,
impacto no live, preparação para automação):** identidade sempre
`ReferenciaCanonica('COLABORADOR', func_id)`, nunca CPF/nome — mesma
disciplina de toda a família de fontes; dedupe por `identidade_logica`
já garantido, não duplicado; fail-safe de colaborador de outro cliente
provado por teste real (não só assumido); nenhuma escolha arbitrária
introduzida em lugar nenhum. Para o live: um próximo live do SKY Tatuí
já pode processar os 8 (ou 9, dependendo do status atual de cada um)
Holerites individualmente, cada `processar_documento` por CPF real
encontrado no PDF, sem mudança de código adicional — só precisa passar
por `execucao.fonte_colaboradores_esperados` na avaliação de
completude ao final do ciclo. Nenhum achado que exigisse correção fora
do escopo desta missão.

## Preservado

`app.py` intocado; nenhuma migration; zero escrita Airtable; zero
Gmail/WhatsApp/Render; nenhum contrato/adapter pré-existente alterado
(`fonte_inventario_completa`, `sink`, todas as `Fonte*AirtableShadow`
já existentes — intocadas); `FonteColaboradoresEsperadosPrestacaoAirtableShadow`
reaproveitada tal como estava, zero linha de lógica de negócio
modificada nela.
