# Ativação da camada comum de resolução semântica (Fase 2E)

**Data:** 2026-08-30
**Branch:** `fix/resolucao-semantica-fase2e`
**Status:** ✅ Implementado, testado (shadow), pronto para revisão

## Resumo executivo

A auditoria da Fase 2E (missão anterior) encontrou algo mais importante
do que uma lacuna: a "camada comum de compreensão documental" que se
pretendia desenhar **já existia inteira como contrato**, em
`magnata_os/classificacao/contratos.py` — `DimensaoResolucao` (incluindo
`TIPO_DOCUMENTAL`), `EstadoResolucaoDimensao` (8 estados),
`NivelConfianca`, `EvidenciaSanitizada`, `ResolucaoDimensao`,
`ResultadoResolucaoSemantico`, `MetadadosExecucaoResolucao`,
`EntradaResolucaoDocumento`, `PerfilAplicabilidadeResolucao`. O que
faltava não era desenho — era **composição real**. Esta missão fecha
exatamente esse gap, sem criar nenhuma arquitetura nova.

## O que foi criado

- **`magnata_os/classificacao/resolucao_semantica.py`** (novo, puro) —
  o compositor: `compor_resolucao_semantica(entrada, perfil,
  resolucoes) -> ResultadoResolucaoSemantico`. Recebe `ResolucaoDimensao`
  já produzidas por especialistas e monta o resultado consolidado.
  Nunca classifica, nunca extrai texto, nunca lê Airtable/Gmail/Postgres,
  nunca resolve CPF/CNPJ, nunca calcula competência, nunca conhece
  nenhum tipo documental por nome — prova estrutural (AST) garante isso
  em teste (`test_compositor_e_estruturalmente_generico`).
  Reutiliza inteiramente as invariantes que o próprio contrato já
  impõe (`ResultadoResolucaoSemantico.__post_init__`/`ResolucaoDimensao.
  validar_contra` — conjunto de dimensões == perfil, cardinalidade,
  coerência de NAO_APLICAVEL): o compositor nunca duplica essa
  validação.
  Também hospeda `resolucao_competencia_de_validacao` — tradução de
  `ResultadoCompetencia` (importacao_lote/contratos.py, resultado de
  `validar_competencia`, função pura já existente e reaproveitada sem
  alteração) para `ResolucaoDimensao` da dimensão COMPETENCIA. Genérico
  a qualquer tipo documental, nunca assume Holerite.

## O que foi ajustado (menor mudança possível, sem reescrever nada)

- **`classificador_documental.py`**: `resultado_classificacao_para_
  resolucao_dimensao` — traduz `ResultadoClassificacaoDocumental`/
  `EstadoClassificacao` (4 estados, vocabulário histórico deste
  classificador) para `ResolucaoDimensao`/`EstadoResolucaoDimensao` (8
  estados, o vocabulário que CLIENTE/COMPETENCIA/COLABORADOR já usam).
  As 17 regras, a precedência histórica e a detecção de colisão
  continuam **inteiramente intocadas** — a tradução só acontece depois
  que `classificar_documento` já decidiu tudo. Mapeamento: RESOLVIDA →
  RESOLVIDA (confiança FORTE se match único e limpo, MODERADA se
  decidido por precedência histórica sobre colisão real); AMBIGUA →
  AMBIGUA; NAO_RECONHECIDA → NAO_ENCONTRADA; INVALIDA → INVALIDA.
  Evidência: só os identificadores de regra (já sanitizados por
  desenho), nunca texto bruto.

- **`politica_identificacao_holerite.py`**: `correspondencia_para_
  resolucao_dimensao` passou a popular `evidencias` de verdade (antes
  só `motivos`) — `EvidenciaSanitizada` com `referencia_fonte`/`metodo`
  = o critério já usado por `resolver_funcionario` ("cpf_exato"/
  "nome_normalizado_exato", já sanitizado), nunca CPF/nome. Força:
  CPF → FORTE, nome → MODERADA — preserva explicitamente o princípio
  "CPF exato > nome" já estabelecido em `resolver_funcionario`, nunca
  reescrito. `resolver_funcionario` em si **não foi tocado**.
  Também ganhou `mestre_suspeito_para_resolucao_dimensao` — traduz
  `MestreSuspeitoIdentificacaoHolerite` (conceito específico de Holerite
  avulso) para `ResolucaoDimensao(COLABORADOR, CONFLITO)`. Deliberadamente
  vive AQUI, não no compositor genérico — mantém qualquer conhecimento
  de "Holerite"/"MestreSuspeito" fora da camada comum.

## Integração com o corredor real

`test_resolucao_semantica_corredor_real.py` prova, com as peças REAIS
do corredor (não mocks de contrato): `classificar_documento` real +
`resolver_funcionario`/`correspondencia_para_resolucao_dimensao` reais +
`resolver_clientes_validado` real (vinculos_prestacao.py) +
`validar_competencia` real + `PoliticaCompetenciaPrestacao`/
`POLITICA_COMPETENCIA_PRESTACAO_V1` reais (a mesma política que já
ativa a exceção do SKY Tatuí em produção) — que essas quatro peças, sem
nenhuma alteração de forma, alimentam o compositor e produzem UM
`ResultadoResolucaoSemantico` RESOLVIDA/pronto_para_routing_logico=True
para um cliente comum e para o SKY Tatuí (competência deslocada,
`base − 1 mês`, sem nenhuma regressão da regra já ativada no PR #92).

**Decisão explícita de escopo:** `servico_lote.py`/`ponte_prestacao_
holerite.py`/`ItemResumoLote` **não foram alterados**. Substituir a
ponte agora para consumir `ResultadoResolucaoSemantico` diretamente
exigiria injetar `FonteVinculosPrestacao` dentro de `ServicoCriacaoLote`
(hoje só a ponte tem acesso a vínculos) — uma mudança de escopo maior
do que esta missão pede, e um risco real de regressão num componente já
testado e aprovado em 3 PRs anteriores (#90, #91, #92). Por isso,
`ResultadoResolucaoSemantico` fica disponível como **saída canônica
paralela**, provada contra as peças reais, pronta para a migração
futura quando fizer sentido conectar `ServicoCriacaoLote`/ponte
diretamente ao compositor — não feita aqui, para preservar
"regressão zero" como prioridade sobre "integração completa agora".

## Prova de generalidade (não é uma arquitetura "de Holerite")

- Teste estrutural (AST): `resolucao_semantica.py` nunca contém, em
  código executável (excluindo docstring), nenhuma das palavras
  proibidas pela missão ("holerite", "filename", "subject", "sender",
  "cpf", "cnpj", etc.) nem importa `politica_identificacao_holerite`/
  `servico_lote`/`ponte_prestacao_holerite`/`servico_avanco_esteira`.
- Teste comportamental: o MESMO `compor_resolucao_semantica`, sem
  nenhuma alteração de código, compõe corretamente um segundo cenário
  com tipo documental diferente ("Extrato da Folha de Pagamento"),
  cliente resolvido por um método diferente (CNPJ exato, nunca por
  vínculo colaborador→cliente) e um perfil que declara COLABORADOR como
  NAO_APLICAVEL (documento sem colaborador).
- Auditoria manual do diff (grep, não só teste): toda ocorrência de
  "Holerite"/"holerite" no diff de produção está em prosa de docstring
  explicando o que o compositor NUNCA faz, ou dentro do arquivo já
  legitimamente escopado a Holerite (`politica_identificacao_holerite.py`,
  na função de tradução que existe exatamente para manter esse
  conhecimento fora do compositor).

## O que NÃO foi feito (registrado, não escondido)

- **Segundo tipo documental real (Extrato Mensal):** não migrado — a
  auditoria já havia identificado que Extrato/FGTS dependem de
  separação master→por-cliente (`construir_mapa_cliente`, legado),
  ainda não portada. A prova de generalidade usou dados sintéticos para
  esse tipo (nunca produção), exatamente como a missão autoriza quando
  a extensão real exigiria resolver primeiro a separação.
- **Separação master→filhos:** não implementada. O desenho do
  compositor não pressupõe "1 PDF = 1 entidade final" — `ResolucaoDimensao`/
  `ResultadoResolucaoSemantico` são por `documento_id`, então continuam
  válidos para documentos filhos que uma futura etapa SEPARACAO possa
  gerar; nenhuma mudança feita aqui inviabiliza isso.
- **OCR:** não implementado, fora de escopo desta missão.

## Documentação relacionada

- `docs/decisoes/corredor-prestacao-holerite-e2e-v1.md` — corredor
  Holerite original (PR #90).
- `docs/decisoes/competencia-esperada-prestacao-v1.md` — política de
  competência esperada, incluindo a exceção do SKY Tatuí (PR #91/#92),
  reutilizada sem alteração pela prova de integração desta missão.
- `magnata_os/classificacao/contratos.py` — contratos canônicos,
  preservados sem nenhuma alteração de forma.
