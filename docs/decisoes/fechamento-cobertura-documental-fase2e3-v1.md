# Fechamento amplo da cobertura documental (Fase 2E.3)

**Data:** 2026-08-30
**Branch:** `fix/fechamento-cobertura-documental-fase2e3`
**Base:** `main @ 05dccde1bba82ed50597f0e43b1b36aac98565c8` (PR #95 mesclado)
**Status:** ✅ Implementado, testado (shadow), pronto para revisão

## Resumo executivo

Esta missão amplia o motor geral de compreensão documental por
CAPACIDADE (nunca por documento individual), fechando gaps registrados
nos PRs #94/#95 que afetavam VÁRIAS famílias ao mesmo tempo:

1. **Separação completa** — cliente por CNPJ (já existia) + cliente por
   NOME normalizado (fallback, novo) + colaborador por CPF (novo),
   todos na MESMA engine (`separacao_documental.py`).
2. **3 produtores gerais novos** — fiscal, ponto (estrutural), temporal/
   certidão — cada um alimentando o MESMO `resolver_tipo_documental`.
3. **Família "comprovante de pagamento" ampliada** — Horas Extras
   (nova categoria) + reforço combinatório de VR/VA (abreviação isolada
   nunca decide sozinha, mas reforça).
4. **Prova de integração de dimensões** por família (Holerite com
   colaborador vs. Guia fiscal sem colaborador).
5. **Segundo corredor completo** até readiness (Extrato Mensal pós-
   separação), provando que o corredor da Prestação não é exclusivo de
   Holerite.

## Decisões arquiteturais registradas

### 1. Separação por colaborador exige índice (desvio deliberado do legado)

`construir_mapa_cpf` usa o CPF cru como chave, sem índice prévio.
`estrategia_por_cpf_colaborador` exige um índice CPF→colaborador
INJETADO — porque `extrair_cpfs_distintos_de_texto` documenta que "CPF
é estritamente TRANSITÓRIO — nunca retornado em DTO"; sem índice, o CPF
cru viraria `GrupoSeparado.entidade_id` (um DTO puro). Exigir índice
também cumpre a cláusula pétrea #10 ("não inventar colaborador") — CPF
desconhecido nunca vira grupo novo.

### 2. Nome ambíguo é mais rigoroso que o legado (desvio deliberado)

O legado (`_carregar_indice_clientes`) resolve nome batendo o PRIMEIRO
da lista ordenada por tamanho, sem detectar ambiguidade. A nova
estratégia (`estrategia_por_cnpj_ou_nome_cliente`) trata 2+ nomes
diferentes batendo na mesma página como AMBÍGUO (`ENTIDADE_
DESCONHECIDA`) — nunca escolhe um vencedor arbitrário. Mais seguro,
nunca inventa cliente.

### 3. Produtor fiscal e família "finalidade de pagamento" continuam vocabulários distintos (gap registrado, não escondido)

`produtores_evidencia_fiscal.py` alimenta o tipo `'Guia'` (dimensão
TIPO_DOCUMENTAL). `finalidade_comprovante_pagamento.py` resolve
finalidades como `'Comprovante de Pagamento - FGTS'` (mesma dimensão,
valores diferentes). Os dois NUNCA colidem (candidatos com nomes
diferentes no mesmo resolvedor), mas também não se reforçam mutuamente
hoje — um comprovante de FGTS com código de receita mas sem a frase
"recolhimento do FGTS" continua INCONCLUSIVO no lado finalidade, mesmo
que o lado fiscal já veja sinal. Integrar as duas famílias de evidência
sob um vocabulário comum é trabalho futuro, não forçado aqui para não
arriscar uma unificação prematura de conceitos ainda em validação.

### 4. Assinatura digital — decisão parcial (Fase H)

Auditoria do legado (`app.py`, `_gerar_comprovante_assinatura_pdf`/
`_gerar_comprovante_assinatura_pacote_pdf`) confirma: "Comprovante de
Assinatura Eletrônica" é um PDF GERADO PELA PRÓPRIA MAGNATA (nunca
recebido de fora), anexado a um pacote já assinado, com aviso explícito
"evidências — não de assinatura digital certificada ICP-Brasil". Isso
responde a pergunta registrada no PR #94 para o caso INTERNO: é
**Opção B — estado/evidência de outro documento**, nunca um tipo
documental recebido para reconhecer. Para o caso ainda NÃO modelado —
um comprovante de assinatura digital externo (ICP-Brasil real) chegando
como documento de ENTRADA — não há evidência suficiente no repositório
para decidir sozinho; fica registrado como decisão de negócio
pendente, não inventada aqui (cláusula pétrea #10).

## O que foi criado/ampliado

- **`separacao_documental.py`**: `normalizar_texto_busca` (porta pura
  de `_normalizar_texto_busca`), `estrategia_por_cnpj_ou_nome_cliente`,
  `estrategia_por_cpf_colaborador`.
- **`produtores_evidencia_fiscal.py`** (novo): código de receita, linha
  digitável/autenticação bancária de guia, identificador de obrigação
  → tipo `'Guia'`.
- **`produtores_evidencia_ponto.py`** (novo): linhas de marcação
  repetidas (mesmo formato de `app.py::_LINHA_CARTAO_PONTO_RE`) +
  período declarado → tipo `'Folha de Ponto'`, SEM depender da frase
  literal.
- **`produtores_evidencia_temporal.py`** (novo): palavra "certidão"
  (nunca sozinha) + validade/emissão declaradas → tipo `'Certidão'`
  (primeira capacidade semântica de código para Certidões).
- **`finalidade_comprovante_pagamento.py`** (ampliado): `FINALIDADE_
  HORAS_EXTRAS` (nova categoria) + `ABREVIACAO_VR_VA` (sinal FRACA
  sempre emitido, nunca decide sozinho, reforça quando combinado).
- **`test_magnata_os_classificacao_perfis_aplicabilidade_por_
  familia.py`** (novo): prova Holerite-com-colaborador vs.
  Guia-fiscal-sem-colaborador no MESMO compositor.
- **`test_corredor_extrato_mensal_pos_separacao.py`** (novo): segundo
  corredor completo (master → separação → motor → composição →
  readiness) usando os MESMOS módulos do corredor de Holerite.
- **`test_fechamento_cobertura_documental_fila_heterogenea.py`**
  (novo): fila ampliada, incluindo master multi-colaborador SEPARADO
  de verdade (não só detectado), filename enganoso, e as 3 novas
  famílias (Ponto estrutural, Certidão, Guia fiscal reforçada).

## Matriz de cobertura do universo documental canônico (21 famílias)

| Família | Antes (PR #95) | Depois (esta missão) | Produtores utilizados | Granularidade/Master | Dimensões resolvidas | Gap restante |
|---|---|---|---|---|---|---|
| Holerite/recibo | ROBUSTO | ROBUSTO | textual, estrutural, separação CPF | detecção + separação por CPF disponíveis | TIPO, COLABORADOR, COMPETENCIA, CLIENTE (via vínculo) | fallback por nome de colaborador não implementado |
| Folha de Ponto | PARCIAL (só frase literal) | **ROBUSTO** | textual + **estrutural novo** (linhas de marcação) | separação por CPF disponível (mesma engine) | TIPO, COLABORADOR (via mesma separação) | extração completa de dias/horários não portada |
| Pagamento de salário | PARCIAL | PARCIAL | finalidade (descrição + estrutura bancária) | n/a | TIPO (finalidade) | valor/vínculo ainda não combinados |
| Assiduidade | PARCIAL | PARCIAL (sem mudança) | finalidade | n/a | TIPO (finalidade) | mesma limitação anterior |
| Horas Extras | **NÃO MODELADO** | **PARCIAL (novo)** | finalidade (nova categoria) | n/a | TIPO (finalidade) | só descrição específica, sem reforço estrutural próprio |
| Diárias | PARCIAL | PARCIAL (sem mudança) | finalidade | n/a | TIPO (finalidade) | mesma limitação anterior |
| VR | NECESSITA EVIDÊNCIA | **PARCIAL (melhorado)** | finalidade + **abreviação fraca nova** | n/a | TIPO (finalidade) | integração com produtor bancário genérico ainda não feita |
| VA | NECESSITA EVIDÊNCIA | **PARCIAL (melhorado)** | idem VR | n/a | TIPO (finalidade) | idem VR |
| Benefícios (vínculo pessoa/cliente) | NÃO MODELADO | NÃO MODELADO | — | — | — | vínculo formal benefício→pessoa/cliente não modelado |
| Assinatura digital | NECESSITA REGRA DE NEGÓCIO | NECESSITA REGRA DE NEGÓCIO (parcial) | — | — | — | caso interno decidido (Opção B); caso externo real não modelado |
| Extrato Mensal (por cliente) | PARCIAL (só CNPJ) | **PARCIAL (ampliado)** | textual + separação CNPJ+**nome novo** | separação real, corredor até readiness PROVADO | TIPO, CLIENTE, COMPETENCIA | UNIDADE_POSTO não coberta; nome ambíguo vira revisão (correto, mas reduz automação) |
| FGTS (guia) | ROBUSTO | ROBUSTO (reforçado) | textual + **fiscal novo** | n/a | TIPO | — |
| FGTS (comprovante de pagamento) | PARCIAL | PARCIAL (sem integração com fiscal — gap registrado) | finalidade | n/a | TIPO (finalidade) | ver decisão #3 acima |
| DCTF declaração | ROBUSTO | ROBUSTO | textual | n/a | TIPO | — |
| DCTF recibo | ROBUSTO | ROBUSTO | textual | n/a | TIPO | — |
| DCTF/DARF guia | ROBUSTO | ROBUSTO (reforçado) | textual + fiscal | n/a | TIPO | — |
| DCTF/DARF (comprovante de pagamento) | PARCIAL | PARCIAL (sem integração com fiscal — gap registrado) | finalidade | n/a | TIPO (finalidade) | ver decisão #3 acima |
| Certidões | **NÃO MODELADO** (só Airtable) | **PARCIAL (novo)** | **temporal/certidão novo** | n/a | TIPO | vínculo a cliente/competência ainda não modelado |
| Guias (genéricas) | PARCIAL | **ROBUSTO (multi-evidência provada)** | textual + **fiscal novo** | n/a | TIPO | — |
| Boletos | ROBUSTO | ROBUSTO | textual | n/a | TIPO | — |
| Notas fiscais | ROBUSTO | ROBUSTO | textual | n/a | TIPO | — |
| Outros (fallback) | por design, nunca "modelado" | idem | — | — | — | não é gap — é o comportamento correto do fallback |

**Nenhuma família saiu do mapa.** Progresso mensurável: Folha de Ponto
e Guias saem de PARCIAL para ROBUSTO; Certidões e Horas Extras saem de
NÃO MODELADO para PARCIAL; VR/VA saem de NECESSITA EVIDÊNCIA para
PARCIAL melhorado; Extrato Mensal ganha separação por nome + corredor
completo provado até readiness.

## Dependência de regex

**Antes:** reconhecimento de tipo dependia quase inteiramente de
`classificador_documental.py` (17 regras regex, único produtor textual
ativo).
**Depois:** 3 novos produtores NÃO-regex-textual-de-tipo (estrutural de
ponto conta linhas de formato, temporal combina palavra+padrão de data,
fiscal combina rótulos de campo) competem/reforçam no MESMO resolvedor
— regex continua presente (nos padrões dos NOVOS produtores também),
mas a ARQUITETURA deixou de depender de UM ÚNICO regex por tipo: Folha
de Ponto agora resolve mesmo se o classificador textual falhar
completamente (prova em `test_estrutura_de_marcacao_reconhece_ponto_
sem_a_frase_literal`).

## Dependência de filename

**Resultado:** continua zero. `test_filename_enganoso_nunca_influencia_
o_resultado` prova que processar o MESMO texto sob 2 nomes fictícios
diferentes produz resultado idêntico — nenhuma função do motor aceita
parâmetro de nome de arquivo (mesma prova estrutural por assinatura já
usada desde o PR #94).

## OCR

Reconfirmado (mesma auditoria do PR #95, sem infraestrutura nova
surgida): nenhuma infraestrutura OCR reaproveitável. **OCR NÃO é o
maior bloqueio transversal agora** — os gaps mais impactantes
remanescentes (integração fiscal↔finalidade, vínculo de benefícios,
fallback de nome para colaborador) são todos de COMPOSIÇÃO de evidência
já extraível de texto, não de extração de texto em si. OCR permanece
relevante só para o dia em que documentos digitalizados sem camada de
texto começarem a chegar — sem sinal disso no repositório hoje.

## Documentação relacionada

- `docs/decisoes/capacidades-transversais-motor-documental-v1.md` —
  evidência estrutural, master, separação (base desta missão).
- `docs/decisoes/motor-geral-compreensao-documental-v1.md` — motor
  geral de TIPO_DOCUMENTAL (PR #94).
- `docs/decisoes/resolucao-semantica-fase2e-v1.md` — compositor geral.
