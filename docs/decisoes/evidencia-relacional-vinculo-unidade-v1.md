# Evidência Relacional Documento↔Documento + Vínculo/Unidade_Posto Reais — V1

Documento de decisão da missão macro "MERGE PR #105 + EVIDÊNCIA
RELACIONAL DOCUMENTO↔DOCUMENTO + VÍNCULO/UNIDADE_POSTO REAIS +
FECHAMENTO DO UNIVERSO DOCUMENTAL V1". Registra os achados de
auditoria, as decisões arquiteturais tomadas, os pontos deixados
deliberadamente em aberto (com o motivo) e a matriz do universo
documental — conforme `/CLAUDE.md` §2 ("nenhuma decisão arquitetural é
tomada em silêncio... registrada por escrito em algum artefato do
repositório").

## 0. Correção pré-merge — "ADENDO PRÉ-MERGE AO PR #106" (achado real,
não escondido)

Antes do merge do PR #106, uma revisão identificou 2 problemas reais na
primeira versão desta missão, corrigidos na mesma branch:

1. **VINCULO fabricado.** `vinculo_unidade_prestacao.resolucao_vinculo_
   a_partir_de_cliente` (removida) criava `ReferenciaCanonica('VINCULO',
   f'{colaborador}:{cliente}')` por espelhamento da resolução de
   CLIENTE — uma identidade DERIVADA, nunca uma evidência real de
   vínculo. Pior: para competência histórica sem prova, a função ainda
   retornava `RESOLVIDA` (só com um motivo sanitizado anexado) — o
   motivo não muda o SIGNIFICADO do estado, então isso violava
   diretamente "vínculo corrente não prova vínculo histórico".
   **Corrigido**: VINCULO agora segue o MESMO padrão de UNIDADE_POSTO —
   só resolvido por uma fonte REAL (`FonteVinculoPrestacao`, Protocol),
   nunca fabricado. Como nenhuma fonte real de produção existe ainda,
   `perfil_aplicabilidade_documental.py` reverteu VINCULO para
   `NAO_APLICAVEL` em todo perfil (a promoção da seção 2 abaixo foi
   revertida) — "melhor manter fora do gate operacional do que inventar
   uma resolução falsa" (texto do adendo). A capacidade (Protocol +
   resolvedor validado) fica pronta e testada isoladamente
   (`test_magnata_os_classificacao_vinculo_unidade_prestacao.py`,
   casos A-H) para quando uma fonte real existir — nenhum trabalho
   perdido, só não gateado ainda.
2. **CONFLITO global por 1 candidato descartável.** `resolver_relacao_
   documental_dentre_candidatos` tratava QUALQUER evidência
   contraditória, de QUALQUER candidato, como CONFLITO da resolução
   INTEIRA — um candidato mal formado impedia outro, forte e coerente,
   de ser resolvido. **Corrigido**: avaliação por candidato — um
   candidato contraditório fica incompatível (nunca elegível), mas
   nunca contamina os demais; CONFLITO global só quando TODOS os
   candidatos são contraditórios (a própria identidade de
   `documento_a_id` fica em disputa, não um candidato isolado).

A seção 2 (VINCULO/UNIDADE_POSTO) e a seção 3 (relação documental)
abaixo foram atualizadas para refletir o estado CORRIGIDO — o texto
anterior a este adendo não é apagado silenciosamente onde ainda é
relevante como contexto, mas as afirmações de estado (o que está
`OBRIGATORIA` hoje, o que resolve e quando) refletem a correção.

## 1. Auditoria prévia (§1 da missão)

Antes de criar qualquer contrato novo, o repositório foi auditado para
os conceitos que a missão pediu para provar ausência/presença:

- **Funcionário→Local, Local→Cliente**: `vinculos_prestacao.py` já
  existia ANTES desta missão e já resolvia CLIENTE a partir de
  `_ORIGENS_SUPORTADAS = {"COLABORADOR", "FUNCIONARIO", "UNIDADE_POSTO"}`
  — a porta já antecipava o fluxo COLABORADOR→VÍNCULO→UNIDADE/POSTO→
  CLIENTE antes desta missão começar. Reaproveitado, nunca reimplementado.
- **Competência/período do vínculo**: auditoria live anterior (sessão
  anterior desta mesma missão macro) confirmou que o cadastro hoje só
  expõe vínculo CORRENTE — nenhum campo de vigência/período no schema
  Airtable de Funcionário/Local. Não inventado; tratado como limitação
  real (ver §4 desta missão / seção 3 abaixo).
- **Documento↔Documento**: `dominio_versionamento.py`
  (`importacao_lote`) modela SUPERSESSÃO DE VERSÃO do MESMO documento
  lógico (`calcular_documento_logico_id`, `determinar_vigente`) — um
  conceito DIFERENTE de relação semântica entre DOIS documentos
  DISTINTOS. Nenhum outro módulo modelava essa segunda coisa antes
  desta missão — confirmado por busca textual e por leitura de
  `classificacao/contratos.py` (nenhuma menção a "relacao"/"lote_id"
  como dimensão). `relacao_documental.py` (novo, seção 3) preenche essa
  lacuna, uma única vez, de forma reutilizável.
- **Lote/pedido/comprovante, IDs de origem, hash, correlation_id**:
  presentes em `dtos_esteira.py`/`servico_lote.py`/migrations do
  Módulo 01 (nível de ESTEIRA/persistência, não do motor semântico) —
  não são reaproveitados diretamente pelo motor semântico porque
  pertencem a uma camada abaixo (esteira operacional); a camada
  semântica nova (`relacao_documental.py`) é intencionalmente mais alta
  e desacoplada dessas tabelas concretas, coerente com "domínio sem
  dependência de driver" (`/CLAUDE.md` §3).

## 2. VÍNCULO e UNIDADE_POSTO como dimensões reais (§2-§4)

Ver `magnata_os/classificacao/vinculo_unidade_prestacao.py` (módulo
novo, docstring completa no próprio arquivo). Resumo das decisões:

- **VÍNCULO** (CORRIGIDO pelo adendo pré-merge, ver seção 0): nunca mais
  espelha CLIENTE. Resolvido exclusivamente por uma fonte REAL
  (`FonteVinculoPrestacao`, Protocol, mesmo padrão de
  `FonteUnidadePostoPrestacao`) via `resolver_vinculo_validado` — nunca
  fabrica `ReferenciaCanonica('VINCULO', ...)`. Como nenhuma fonte real
  de produção existe ainda, permanece `NAO_APLICAVEL` em TODO perfil
  (`perfil_aplicabilidade_documental.py`) — a capacidade está pronta e
  testada isoladamente (casos A-E,
  `test_magnata_os_classificacao_vinculo_unidade_prestacao.py`), sem
  gatear o corredor até haver prova de uma fonte real.
- **UNIDADE_POSTO** ganhou um produtor real
  (`FonteUnidadePostoPrestacao`, Protocol, nunca Airtable direto no
  core) com cardinalidade múltipla genuína — um colaborador com 2
  postos legítimos na mesma competência nunca é colapsado a 1 (provado
  pelo Caso E2E-B/Caso H). Promovido a `OBRIGATORIA` **somente para
  Holerite** — a única família com regra semântica comprovada e demanda
  E2E explícita nesta missão. As demais famílias de granularidade
  colaborador (Ponto, os 5 tipos de Comprovante, Relatório de
  Benefícios) permanecem com UNIDADE_POSTO `NAO_APLICAVEL` —
  deliberado, não esquecido.
- **Temporalidade (§4, corrigida pelo adendo)**: a responsabilidade de
  decidir se uma competência histórica está comprovada é inteiramente
  da FONTE (nunca deste módulo) — quando a fonte só conhece o vínculo/
  posto CORRENTE e a competência pedida é histórica sem vigência
  provada, ela devolve `NAO_ENCONTRADA` (nunca `RESOLVIDA` com um
  motivo anexado só para registrar a ressalva — o motivo NUNCA muda o
  SIGNIFICADO do estado). Vocabulário sanitizado disponível para
  qualquer fonte real:
  `vinculo_unidade_prestacao.MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA`.
  Provado pelos Casos C/G (`test_magnata_os_classificacao_vinculo_
  unidade_prestacao.py`): vínculo/posto corrente nunca vira verdade
  histórica silenciosa; Caso D prova que, quando a fonte REALMENTE
  comprova a competência histórica, `RESOLVIDA` é correto.

## 3. Relação Documento↔Documento — capacidade genérica (§5-§9)

Novo módulo `magnata_os/classificacao/relacao_documental.py` — ver
docstring completa no arquivo para a regra de combinação de força
(mesma regra já estabelecida em `resolucao_tipo_documental`, réplicada
porque a original é privada do módulo de tipo documental — a REGRA é a
mesma, nunca uma segunda decisão paralela).

Contrato: `TipoRelacaoDocumental` (COMPROVA, PERTENCE_AO_LOTE,
DERIVADO_DE, FILHO_DE, REFERENCIA, SUBSTITUI, COMPLEMENTA — só COMPROVA
tem uso concreto nesta missão; as demais são reservadas com aplicação
futura documentada no próprio enum, nunca especulativas sem descrição).
`EvidenciaRelacaoDocumental` / `ResolucaoRelacaoDocumental`
reaproveitam `EstadoResolucaoDimensao` (RESOLVIDA/AMBIGUA/
NAO_ENCONTRADA/CONFLITO) — nenhum enum de estado novo.

`DadosCorrelacaoDocumental` + `produzir_evidencias_correlacao` +
`extrair_dados_correlacao_de_texto` são GENÉRICOS por desenho — nenhuma
classe `RelacaoComprovanteIfood`/`RelacaoVrBeneficios`/
`RelacaoFgtsEspecial` foi criada (proibição explícita da missão). A
prova de reuso está no próprio Caso E2E-G (FGTS) usando a MESMA função
`resolver_relacao_documental_par` sem nenhum módulo específico de FGTS.

Cláusula pétrea §6 ("valor total sozinho NÃO basta, data sozinha NÃO
basta, fornecedor sozinho NÃO basta") implementada assim: nenhum campo
isolado de `produzir_evidencias_correlacao` emite força `FORTE` — até
"mesmo identificador de pedido/lote" é `MODERADA`, exigindo combinação
com outro campo (2+ MODERADA → FORTE, mesma regra do motor de tipo
documental). Um identificador DIVERGENTE entre os dois documentos é a
única evidência que sozinha decide — mas decide `CONFLITO`, nunca uma
relação — proteção deliberadamente assimétrica (fácil recusar, difícil
afirmar).

**CORRIGIDO pelo adendo pré-merge (ver seção 0)**:
`resolver_relacao_documental_dentre_candidatos` agora avalia cada
candidato ISOLADAMENTE. Um candidato com evidência contraditória fica
incompatível (nunca elegível a vencedor), mas nunca mais contamina os
demais candidatos com um `CONFLITO` global — só quando TODOS os
candidatos são contraditórios a resolução inteira vira `CONFLITO`
(nenhuma decisão válida é sequer possível). Provado pelos casos
adendo-I/J/K/L/M
(`test_magnata_os_classificacao_relacao_documental.py`,
`test_magnata_os_classificacao_e2e_vinculo_unidade_relacao_v1.py`).

### Benefícios — relatório↔comprovante (§6-§8)

`produtores_evidencia_beneficios.py` ganhou 2 funções: `dados_
correlacao_beneficios` (extração genérica + lista de fornecedores já
cadastrada, reaproveitada — nunca uma segunda lista) e `derivar_
clientes_logicos_do_comprovante_global` (regra pura: o comprovante
global só herda os clientes do relatório relacionado quando a relação
já está `RESOLVIDA`; nunca decompõe valores por si — "os valores sempre
vêm do relatório, o comprovante prova o pagamento do lote"). Identidade
física preservada: 1 `documento_id`, nunca duplicado; N relações
lógicas via `ItemInventarioPrestacao.identidade_logica`, já existente,
nunca alterado (§17).

### FGTS e DCTF (§9-§11)

Nenhum módulo específico de família criado — Casos E2E-G e E2E-H provam
que a MESMA `relacao_documental.py` cobre FGTS guia↔comprovante e DCTF
guia↔comprovante. FGTS continua cliente-level (perfil preservado do PR
#105, `Cardinalidade(1, 1)` confirmada pelo teste); DCTF continua
broadcast (`CLIENTE` `NAO_APLICAVEL`, confirmado pelo teste) — nenhum
dos dois perfis foi alterado por esta missão.

## 4. PENDÊNCIA REGISTRADA — costura de orquestração ainda não feita

> **ATUALIZAÇÃO**: esta pendência foi FECHADA pela missão "CORRIGIR
> METADADOS + MERGE PR #106 + COSTURA AUTOMÁTICA DE RELAÇÃO
> DOCUMENTO↔DOCUMENTO NO CORREDOR V1" — ver
> `docs/decisoes/costura-relacao-documental-corredor-v1.md`. Uma nova
> pendência distinta (adapters reais de produção) permanece registrada
> lá — nunca a mesma pendência reaberta, uma nova, nomeada
> explicitamente.

A capacidade relacional (`relacao_documental.py` + as 2 funções de
benefícios) está construída, testada e provadamente reutilizável — mas
**não está** ainda plugada dentro de `avancar_para_inventario`/
`inventario_prestacao_memoria.py`: hoje, um documento do tipo
Comprovante VR/VA passa pelo corredor normal (que já resolve CLIENTE
via vínculo do colaborador, como qualquer outro documento de
granularidade colaborador) — o caminho ESPECÍFICO do "comprovante
GLOBAL sem colaborador individualizável, relacionado por evidência a um
relatório multi-cliente" ainda não tem um ponto de entrada no
orquestrador (`resolucao_documento_prestacao.py`) que chame
`relacao_documental`/`derivar_clientes_logicos_do_comprovante_global`
automaticamente.

Por quê registrado como pendência e não fechado silenciosamente: a
costura completa exigiria decidir, no orquestrador, COMO um documento
"aponta" para seu candidato de relação (qual repositório fornece os
candidatos a `documento_b_id`?) — isso é uma decisão de infraestrutura
(fonte de candidatos, ainda sem contrato) fora do escopo desta missão
específica, que pediu a CAPACIDADE, não necessariamente a automação
ponta-a-ponta do caminho raro do comprovante verdadeiramente global
(o caminho comum — comprovante com colaborador individualizável —
já funciona hoje sem essa costura, porque já resolve CLIENTE via
vínculo normalmente). Não é uma regressão: é capacidade nova, testada
isoladamente, com o ponto de integração restante nomeado explicitamente
aqui — não escondido.

## 5. Perfis sem cobertura — auditoria §13

Tipos reconhecidos pelo motor (têm produtor de TIPO_DOCUMENTAL) mas
**sem perfil cadastrado** em `perfil_aplicabilidade_documental.py`:

| Tipo | Regra comprovada? | Decisão |
|---|---|---|
| **Certidão** | Não. `produtores_evidencia_temporal.py` já resolve TIPO_DOCUMENTAL + validade/emissão, mas não há, no legado auditado, nenhuma regra registrada de competência aplicável (uma certidão tem período de VALIDADE, não uma competência mensal recorrente) nem de granularidade (por colaborador? por cliente? por vínculo específico, tipo de certidão dependente — CND, FGTS, trabalhista, cada uma com regra própria potencialmente diferente). | **SEM_PERFIL, mantido.** Adicionar um perfil genérico "Certidão" agora seria inventar uma regra de competência/granularidade sem evidência — proibido explicitamente pela missão. |
| **Rescisão** | Não. `classificador_documental.py` já distingue Rescisão de Holerite (TRCT com "Valor Líquido" etc.), mas rescisão é um evento EXCEPCIONAL por colaborador (ocorre na saída, não em todo ciclo) — a regra de cardinalidade "1 por colaborador esperado por ciclo" do Holerite não se aplica; não há, no legado, uma regra registrada de QUANDO uma rescisão é esperada (depende de desligamento, não de calendário). | **SEM_PERFIL, mantido.** Tratar Rescisão com o mesmo perfil de Holerite obrigaria uma cardinalidade que não é verdadeira para este tipo. |
| **EPI** | Não. Ficha de controle de EPI é um registro de ENTREGA DE EQUIPAMENTO, não vinculado a competência (nenhuma menção, no legado auditado, de EPI amarrado a mês/ano de prestação). `roteamento_documental.py` já classifica EPI como escopo COLABORADOR, mas isso é sobre A QUEM pertence o documento, não sobre quando ele é esperado. | **SEM_PERFIL, mantido.** Nenhuma regra de competência aplicável comprovada — forçar COMPETENCIA `OBRIGATORIA` seria inventado. |

Em nenhum dos 3 casos um perfil foi adicionado "só para aumentar
cobertura" (proibição explícita §13) — cada um seguiu SEM_PERFIL com o
motivo documentado aqui, nunca silenciado.

## 6. Universo Documental — matriz (§14)

| Família | Estado |
|---|---|
| Holerite | AUTOMATIZADO (tipo, competência, colaborador, cliente, unidade/posto — todos resolvidos automaticamente; VINCULO fica NAO_APLICAVEL até existir fonte real, ver seção 0) |
| Folha de Ponto | PARCIAL (perfil cadastrado, granularidade colaborador; VINCULO/UNIDADE_POSTO NAO_APLICAVEL por decisão registrada) |
| Extrato da Folha de Pagamento | AUTOMATIZADO (broadcast cliente, perfil já cadastrado desde missões anteriores) |
| FGTS (Guia) | AUTOMATIZADO (cliente-level, perfil preservado do PR #105) |
| FGTS (Comprovante de Pagamento) | AUTOMATIZADO para classificação/cliente; SEM_EVIDENCIA_RELACIONAL para o vínculo Guia↔Comprovante em produção real — capacidade construída e testada (Caso E2E-G), não plugada no corredor ainda (ver seção 4) |
| DCTFWeb — Declaração / Recibo / Guia/DARF | AUTOMATIZADO (broadcast, perfis preservados do PR #105) |
| Comprovante de Pagamento - Salário | PARCIAL (perfil cadastrado, granularidade colaborador; VINCULO/UNIDADE_POSTO NAO_APLICAVEL por decisão) |
| Relatório de Benefícios | PARCIAL (tipo/competência/colaborador/cliente resolvidos, VINCULO NAO_APLICAVEL; relação com o comprovante correspondente é SEM_EVIDENCIA_RELACIONAL até a costura da seção 4) |
| Comprovante de Pagamento - VR/VA | PARCIAL (mesmo estado do Relatório de Benefícios — a relação lógica com o relatório é a peça pendente) |
| Comprovante de Pagamento - Assiduidade / Diárias / Horas Extras | PARCIAL (mesmo padrão dos demais Comprovante-* — perfil cadastrado, unidade/posto NAO_APLICAVEL por decisão) |
| Certidões | SEM_PERFIL (§13 — regra de competência/granularidade não comprovada) |
| Rescisão | SEM_PERFIL (§13 — evento excepcional, cardinalidade do Holerite não se aplica) |
| EPI | SEM_PERFIL (§13 — sem competência aplicável comprovada) |
| Assinatura digital ↔ documento | SEM_FONTE (nenhum produtor de evidência para essa relação existe ainda no motor semântico; fora do escopo desta missão, registrado como aplicação futura de `TipoRelacaoDocumental` — nenhum enum novo precisará ser criado quando chegar a vez) |
| Documentos fiscais complementares (não listados) | SEM_FONTE (nenhum tipo específico auditado nesta missão além dos já citados) |

Nenhuma família ficou invisível: toda família citada pela missão em
§14 tem uma linha e um estado explícito acima.

## 7. Readiness e dedupe (§16-§17)

Cardinalidade do Holerite (1 por colaborador esperado por ciclo/cliente
aplicável) **não foi alterada** — a adição de VINCULO/UNIDADE_POSTO
como dimensões obrigatórias não mexeu em `prestacao_readiness.py` nem
em `ItemInventarioPrestacao.identidade_logica`
(`documento_id + cliente + colaborador`, inalterada). Confirmado pela
suíte de regressão completa (nenhuma falha nova em
`resolucao_documento_prestacao`/`corpus_corredor_autonomo_pos_
classificacao`/`prestacao_readiness`).

Relação Documento↔Documento (`ResolucaoRelacaoDocumental`) tem sua
própria identidade natural (`documento_a_id` + `tipo_relacao` +
`documento_b_id`) — nunca precisou tocar a chave canônica do
inventário (§17: "não alterar chave canônica sem necessidade
comprovada" — necessidade não comprovada, chave intocada).

## 8. Plano de primeira validação live — `PLANO_VALIDACAO_LIVE_CORREDOR_V2` (§22)

**NÃO EXECUTADO nesta missão** — só planejado, conforme exigido.

- **Objetivo**: validar o corredor completo (classificação → perfil →
  vínculo → unidade/posto → cliente → inventário → readiness) contra um
  conjunto REAL pequeno, só leitura.
- **Cliente inicial**: EDIFICIO SKY TATUI (já usado como referência
  conhecida em `competencia_esperada_prestacao.py`).
- **Competência**: JUNHO/2026.
- **Conjunto máximo sugerido**: 1 Holerite + 1 Extrato da Folha de
  Pagamento + 1 Guia FGTS + 1 documento adicional só se necessário para
  provar vínculo/relação (ex.: 1 Comprovante FGTS, só se o Guia sozinho
  não bastar para exercitar a relação nova).
- **Sistema/fonte**: Airtable (bases/tabelas já usadas pelos adapters
  existentes de `importacao_lote/adapters/airtable_*`) — só leitura
  (`list_records`/GET equivalente), nunca escrita.
- **Campos**: os já mapeados pelos adapters existentes — nenhum campo
  novo a ser lido além do que os adapters de Módulo 01/importacao_lote
  já expõem.
- **Record IDs/filtros**: filtro por cliente=EDIFICIO SKY TATUI +
  competência=06/2026, limitado à quantidade máxima acima — a
  execução real (quando autorizada) deve registrar os record IDs
  usados no relatório de execução, nunca hard-coded aqui de antemão.
- **Downloads**: só o necessário para extrair texto dos documentos
  selecionados — nenhum PDF fora do conjunto acima.
- **PII/sanitização**: nenhum CPF/nome bruto sai do processo de
  validação para log/relatório — só IDs já sanitizados (documento_id,
  cliente_id, colaborador_id interno), como em qualquer execução do
  motor (§25).
- **Zero escrita**: nenhuma escrita em Airtable, Gmail, WhatsApp, ou
  qualquer sistema externo durante esta validação — só leitura.
- **Critérios de parada**: qualquer sinal de escrita acidental,
  qualquer PII vazando para log, qualquer volume acima do limite
  definido, qualquer erro técnico não tratado — parar e reportar,
  nunca continuar "para ver o que acontece".
- **Rollback**: não aplicável no sentido de reverter estado — nenhum
  estado externo é alterado por esta validação (só leitura); "rollback"
  aqui significa simplesmente encerrar a execução sem nenhum efeito
  colateral externo a desfazer.

**`READY_FOR_LIVE_CORRIDOR_V2 = FALSE`** — a costura de orquestração da
seção 4 (relação documental dentro do corredor real) ainda não está
plugada; rodar a validação live antes disso deixaria o caso de
comprovante global de fora do que está de fato integrado. Recomendação:
fechar a pendência da seção 4 (ou reduzir o escopo da primeira
validação live para excluir o caso de comprovante global) antes de
autorizar a execução real.
