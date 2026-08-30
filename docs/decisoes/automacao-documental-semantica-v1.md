# Automação documental real V1 — motor semântico + universo completo + automação por confiança

**Data:** 2026-08-30
**Branch:** `fix/automacao-documental-semantica-v1`
**Base:** `main @ bdde7984184f2dddc14242026e70cf0416266e4c` (PR #102 mesclado)
**Status:** ✅ Implementado, testado — gaps genuínos fechados; nenhum trabalho já existente refeito.

## Fase 0 — Merge do PR #102

HEAD citado (`9ad3b024b600e241cff9e9def9d8744b509663cf`) confirmado idêntico ao HEAD real, base `main`, CI verde. Mesclado. Merge commit: `bdde7984184f2dddc14242026e70cf0416266e4c`.

## Correção conceitual (§0) — respeitada, nada mudou

"Mesmo contrato" (`ItemInventarioPrestacao`) nunca significou juntar documentos — cada família continua sendo produzida por um adapter/produtor próprio (Extrato, FGTS Guia, DCTF Declaração/Recibo/Guia, Holerite continuam objetos `ItemInventarioPrestacao` DISTINTOS, nunca fundidos). `FonteInventarioPrestacaoComposta` (PR #102) só agrega a LISTA de itens já distintos — nunca concatena PDF nem cria um documento lógico único a partir de vários. Nenhuma mudança necessária aqui.

## Auditoria do legado (§18) — antes de criar qualquer regra nova

O motor multi-evidência já existia e já é extenso: `classificador_documental.py` (17 regras, espelho 1:1 do legado `app.py::TIPO_DOC_REGRAS`, precedência histórica explícita, nunca uma regra nova aqui), `resolucao_tipo_documental.py` (combinação de força/conflito), `finalidade_comprovante_pagamento.py` (Salário/FGTS/DCTF-DARF/VR-VA/Assiduidade/Diárias/Horas Extras — já cobre TODO o universo de "comprovante de pagamento" do §6), `produtores_evidencia_fiscal.py` (Código de Receita, linha digitável, reforço fiscal↔finalidade), `produtores_evidencia_ponto.py` (Folha de Ponto por ESTRUTURA, já sem depender do título), `produtores_evidencia_temporal.py` (Certidões), `resolucao_master_documental.py` (master/separação). Nada disso foi refeito.

**Gaps genuínos encontrados e fechados nesta missão:**
1. Extrato só reconhecia "Extrato Mensal"/"Extrato da Folha de Pagamento" — nunca "Resumo da Folha" (§9).
2. Nenhum mecanismo comparava origem declarada (tabela/campo externo) com o resultado semântico já resolvido — Airtable podia, na prática, "vencer por omissão" (§12, REGRA CRÍTICA).
3. Nenhuma classificação fina do motivo de não-avanço automático para métrica/observabilidade — só o binário `necessita_revisao_humana` já existente (§14/§20).
4. `NecessidadeDocumentoPrestacao.fontes_ainda_nao_consultadas` já existia, mas nada decidia qual é a PRÓXIMA fonte (§17).

## O que foi construído

- **`produtores_evidencia_extrato.py`** (novo): `hipoteses_de_rotulo_alternativo_de_extrato` — reconhece "Resumo da Folha[ de Pagamento]" como MODERADA, somando ao MESMO `resolver_tipo_documental`. **Nunca** altera `classificador_documental.py` (provado por teste: as 17 regras legadas continuam não reconhecendo "Resumo da Folha" sozinhas).
- **`reconciliacao_origem_conteudo.py`** (novo): `reconciliar_origem_com_resolucao_semantica(tipo_origem, resolucao)` → `REFORCO`/`CONFLITO`/`SEM_RESOLUCAO`. Fecha a REGRA CRÍTICA do §12 — nunca decide um tipo sozinho, só compara.
- **`automacao_por_confianca.py`** (novo): `DecisaoAutomacao` (AVANCA_AUTOMATICO/REVISAO_HUMANA/AMBIGUO/CONFLITO/RETRY_TECNICO/DESCONHECIDO) + `decidir_proxima_acao`/`calcular_metricas_automacao`/`MetricasAutomacao`. Nunca recalcula RESOLVIDA/PARCIAL/... (`compor_resolucao_semantica` continua a única fonte de verdade) — só classifica o motivo mais grave entre as dimensões já resolvidas, para métrica e para decidir avançar/parar.
- **`estrategia_aquisicao_documental.py`** (novo): `proxima_fonte_a_consultar` — ordem fixa `airtable → gmail → armazenamento_documental`, reaproveitando o campo já existente `fontes_ainda_nao_consultadas`. Nenhuma busca live executada.
- **`test_corpus_heterogeneo_motor_semantico_e2e.py`** (novo, 8 casos): Holerite sem a palavra "Holerite"; Ponto sem título "Folha de Ponto"; Extrato chamado "Resumo da Folha"; Guia FGTS reconhecida sem depender de filename (provado por inspeção de assinatura — nenhuma função do motor aceita parâmetro `filename`); VR com estrutura bancária + descrição variada; documento com origem declarada CONTRADITÓRIA ao conteúdo → `CONFLITO` explícito (nunca silencioso); reforço fiscal↔finalidade sem depender do nome do banco; documento verdadeiramente desconhecido → nunca classificado silenciosamente, sempre `DESCONHECIDO`/`REVISAO_HUMANA`.

## Dependências — antes/depois

| | Antes | Depois |
|---|---|---|
| Palavra exata | Já dependia MODERADAMENTE — motor já combina evidências estruturais (Ponto) e fiscais (Código de Receita) sem depender de título | Extrato também não depende mais de rótulo exato (Resumo da Folha) |
| Filename | Nunca dependeu — nenhuma função do motor aceita `filename` | Confirmado por teste explícito (inspeção de assinatura) |
| Airtable | Tabela/campo de origem era usado como o PRÓPRIO `tipo_documental` do item de inventário, sem comparação com conteúdo quando disponível | Mecanismo de reconciliação existe e está testado — origem que diverge do conteúdo semântico vira `CONFLITO`, nunca aceito silenciosamente (ainda não *conectado* automaticamente a todo ponto de ingestão — ver "o que não foi feito") |

## Universo documental — matriz de cobertura (motor + evidência, nunca obrigatoriedade)

| Família | Reconhecimento | Depende de palavra exata? | Fonte de evidência |
|---|---|---|---|
| Holerite | ✅ | Não (Recibo de Pagamento + Total de Vencimentos + Valor Líquido bastam) | classificador + estrutura |
| Folha de Ponto | ✅ | Não (linhas de marcação repetidas + período) | produtor estrutural |
| Extrato/Resumo da Folha | ✅ | Não (2 rótulos legados + 1 alternativo novo) | classificador + produtor novo |
| FGTS Guia | ✅ | Não (Código de Receita, linha digitável) | classificador + fiscal |
| FGTS Comprovante | ✅ | Não (reforço fiscal↔finalidade) | finalidade + fiscal |
| DCTFWeb Declaração/Recibo/Guia | ✅ | Não (precedência histórica comprovada) | classificador |
| DCTFWeb/DARF Comprovante | ✅ | Não (mesmo mecanismo de FGTS Comprovante, `FINALIDADE_DCTF_DARF`) | finalidade + fiscal |
| Comprovante Salário/VR/VA/Assiduidade/Horas Extras/Diárias | ✅ (todos já tinham finalidade própria) | Não | `finalidade_comprovante_pagamento.py` |
| Certidões | ✅ | Não (evidência temporal — validade) | `produtores_evidencia_temporal.py` |
| Master (múltiplos subdocumentos) | ✅ (já existia, `resolucao_master_documental.py`) | — | estrutural |
| Origem × conteúdo | ✅ (novo) | — | `reconciliacao_origem_conteudo.py` |

Nenhuma família essencial ficou fora do mapa. Nenhum "classificador por documento" foi criado — todo produtor novo alimenta o MESMO `resolver_tipo_documental`.

## Automação por confiança — resultado do corpus de teste

`test_corpus_heterogeneo_motor_semantico_e2e.py` + `test_magnata_os_classificacao_automacao_por_confianca.py` provam a política: RESOLVIDA → `AVANCA_AUTOMATICO`; AMBIGUA/CONFLITO/ERRO_TECNICO/NAO_ENCONTRADA → cada um mapeado para uma categoria própria, nunca confundidos. `MetricasAutomacao` valida internamente que a soma das categorias sempre bate com o total (nunca perde nem duplica um resultado).

## ADENDO OBRIGATÓRIO (review pré-merge, mesmo dia) — 2 correções arquiteturais

Corrigido nesta mesma branch/PR, antes do merge, por review explícito:

1. **`estrategia_aquisicao_documental.py` criava precedência estrutural
   do Airtable** (`ORDEM_FALLBACK_AQUISICAO` fixa, Airtable primeiro,
   hardcoded dentro da função). Corrigido: `proxima_fonte_a_consultar`
   agora recebe `ordem_fontes` como parâmetro explícito, sempre injetado
   por quem chama; a constante antiga virou `ORDEM_FALLBACK_PADRAO_V1`
   — só uma sugestão de composição, nunca aplicada automaticamente
   dentro da função quando uma ordem diferente é informada. Testado com
   `Gmail+armazenamento` sem Airtable, e com `armazenamento antes de
   Gmail` — nenhuma mudança de domínio necessária em nenhum dos casos.
2. **Reconciliação origem×conteúdo comparava por igualdade direta**,
   sem normalizar vocabulário — `'extrato_cliente'` (Família B) vs.
   `'Extrato da Folha de Pagamento'` (motor geral) viraria `CONFLITO`
   falso. Corrigido: ambos os lados são normalizados via
   `TRADUCAO_FAMILIA_B_PARA_MOTOR_GERAL` (já existente, nunca uma
   segunda tabela, nunca fuzzy matching) antes de comparar. Uma
   divergência SEM equivalência canônica comprovada continua `CONFLITO`
   — testado nos dois sentidos (origem Família B/conteúdo motor geral e
   vice-versa) e reconfirmado que o caso genuinamente divergente
   (Holerite declarado, FGTS resolvido) continua `CONFLITO`.

Também confirmado (nenhuma mudança de código necessária, já estava
correto): `automacao_por_confianca.py` nunca duplica a decisão de
`compor_resolucao_semantica` (um teste novo prova que uma dimensão
TIPO_DOCUMENTAL isoladamente `RESOLVIDA`, mas com `estado_consolidado`
diferente de `RESOLVIDA`, nunca avança automático); `ERRO_TECNICO`
sempre vira `RETRY_TECNICO`, nunca `REVISAO_HUMANA` direta (novo teste
explícito). E: um novo teste prova que "Resumo da Folha" (MODERADA,
`produtores_evidencia_extrato.py`) nunca vence uma evidência fiscal
forte concorrente (FGTS) no mesmo texto — o sinal continua sendo só um
sinal, nunca identidade.

## O que NÃO foi feito (registrado, não escondido)

- A reconciliação origem×conteúdo (§12) está pronta e testada, mas **não foi conectada automaticamente** a nenhum ponto real de ingestão (ex.: `FonteInventarioPrestacaoAirtableShadow` continua atribuindo o tipo pela tabela de origem, sem chamar a reconciliação) — conectar isso exigiria ter, no mesmo ponto, tanto a origem quanto uma resolução semântica já composta do MESMO documento, o que hoje só acontece no corredor de importação por PDF (Família B/Módulo 01), não no corredor Airtable-shadow (que nunca lê o conteúdo do documento). Registrado como o gap real a fechar quando o corredor de leitura de conteúdo for conectado ao inventário Airtable-shadow.
- Nenhuma leitura live (Airtable ou Gmail) foi executada — fora de escopo desta missão.
- Nenhum "score universal" foi criado — a decisão de automação usa os estados qualitativos já existentes (`NivelConfianca`/`EstadoResolucaoDimensao`), nunca um número novo.

## Validação

- Testes específicos: 30 (4 módulos novos) + 8 (corpus heterogêneo) = 38, todos verdes.
- Suíte geral: 1009 passed, 6 skipped — sem regressão (falhas pré-existentes de ambiente, já reconfirmadas em missões anteriores).
- Pre-commit: 14/14. Governança: 15/15. `git diff --check`: limpo.
- `app.py` intocado. Zero escrita externa. Zero segredo/PII no diff.

## Documentação relacionada

- `docs/decisoes/inventario-real-prestacao-v1.md` — inventário real, fonte composta.
- `docs/decisoes/fechamento-cobertura-documental-fase2e3-v1.md` — matriz de cobertura original (produtores fiscal/ponto/temporal).
- `docs/decisoes/capacidades-transversais-motor-documental-v1.md` — evidência estrutural, master, separação.
