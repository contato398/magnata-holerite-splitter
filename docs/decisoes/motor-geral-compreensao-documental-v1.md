# Motor geral de compreensão documental multi-evidência (Fase 2E)

**Data:** 2026-08-30
**Branch:** `fix/motor-geral-compreensao-documental`
**Status:** ✅ Implementado, testado (shadow), pronto para revisão

## Resumo executivo

Antes desta missão, `TIPO_DOCUMENTAL` era decidido por UMA fonte só —
regex textual (`classificador_documental.py`), traduzida para o
contrato canônico pelo PR #93. Esta missão adiciona um **resolvedor
geral multi-evidência** que combina QUALQUER número de produtores
(textual, entidades, contextual — e, no futuro, estrutural e relacional,
sem alterar o resolvedor) para decidir `RESOLVIDA`/`AMBIGUA`/
`NAO_ENCONTRADA`/`CONFLITO` — nunca especializado a nenhum tipo
documental.

## O que foi criado

- **`magnata_os/classificacao/resolucao_tipo_documental.py`** (novo,
  puro): `HipoteseTipoDocumental` (tipo candidato + evidências de
  qualquer produtor) e `resolver_tipo_documental(hipoteses, *,
  quantidade_entidades_distintas=None) -> ResolucaoDimensao`. Regra de
  combinação de força documentada no próprio módulo (nunca uma escala
  paralela — só FORTE/MODERADA/FRACA/INDETERMINADA já existentes);
  regra de resolução com precedência explícita: nenhuma evidência →
  NAO_ENCONTRADA; único candidato com força FORTE/MODERADA → RESOLVIDA;
  único candidato só FRACA → NAO_ENCONTRADA (nunca força reconhecimento
  "a qualquer custo"); múltiplas entidades distintas → CONFLITO mesmo
  com candidato único forte (generaliza "PDF mestre suspeito", antes só
  para Holerite avulso); dois ou mais candidatos empatados em FORTE →
  CONFLITO; empatados em MODERADA/FRACA → AMBIGUA.

- **`magnata_os/classificacao/produtores_evidencia_documental.py`**
  (novo, puro): três produtores, cada um reaproveitando um especialista
  já existente, sem reimplementar nada:
  1. `hipoteses_textuais_de_classificacao` — reaproveita
     `classificador_documental.classificar_documento` +
     `resultado_classificacao_para_resolucao_dimensao` (PR #93) sem
     alteração; as 17 regras e a precedência histórica continuam
     intocadas.
  2. `contar_entidades_distintas_no_texto` — reaproveita
     `extrair_cpfs_distintos_de_texto` (importacao_lote/dominio.py) sem
     alteração; generaliza o sinal de "múltiplas entidades" para
     qualquer tipo, não só Holerite.
  3. `hipoteses_contextuais`/`SinalContextual` — produtor genérico para
     remetente/assunto/origem, estruturalmente limitado a evidência
     FRACA; a regra de correspondência sinal→tipo é responsabilidade de
     quem compõe o pipeline (nunca hardcoded aqui, nunca duplica
     `REMETENTE_FISCAL`/`app.py`).

## Integração com o compositor (PR #93)

`resolver_tipo_documental` devolve exatamente o mesmo `ResolucaoDimensao`
que `compor_resolucao_semantica` já consome — nenhuma adaptação
necessária, provado em
`test_magnata_os_classificacao_resolucao_tipo_documental.py::
test_resultado_alimenta_o_compositor_sem_nenhuma_adaptacao`.

## Prova de generalidade

- AST: `resolucao_tipo_documental.py` nunca contém, em código
  executável, "holerite"/"extrato"/"fgts"/"dctfweb"/"folha de ponto"/
  "if tipo ==", nem importa `classificador_documental`/
  `politica_identificacao_holerite`.
- Estrutural: nenhuma função do motor aceita `filename`/`nome_arquivo`
  como parâmetro — provado por inspeção de assinatura, não só por
  convenção.
- Comportamental: fila heterogênea de 11 documentos sintéticos (9 tipos
  reconhecidos automaticamente + 1 desconhecido + 1 ambíguo) processada
  pelo MESMO resolvedor, produzindo os 3 estados esperados
  (`RESOLVIDA`/`NAO_ENCONTRADA`/`AMBIGUA`) sem nenhum `if` por tipo.

## Cobertura do universo documental canônico da Prestação

Ver relatório da sessão para a matriz completa campo-a-campo (24 itens).
Resumo por estado:

| Estado | Itens |
|---|---|
| RECONHECIMENTO ROBUSTO | Holerite, DCTFWeb - Declaração, DCTFWeb - Recibo de Entrega, Guia DCTFWeb/DARF (multi-evidência arquitetural provada; hoje só 1 produtor textual ativo por padrão, mas o fail-safe de múltiplas entidades e a combinação de força já valem para todos) |
| RECONHECIMENTO PARCIAL | Extrato da Folha de Pagamento, FGTS (Guia), Folha de Ponto, Guia genérica, Boleto, Nota Fiscal — reconhece o TIPO, mas granularidade CLIENTE (Extrato/FGTS) depende de separação master→filhos ainda não portada |
| NECESSITA EVIDÊNCIA ADICIONAL | Comprovante de Pagamento (genérico — salário/FGTS/DCTF/VR/VA nunca devem colapsar num tipo só sem evidência que distinga a finalidade), FGTS Comprovante de Pagamento vs. Guia |
| NECESSITA SEPARAÇÃO | Extrato Mensal por cliente, FGTS por cliente (ambos master→por-cliente, legado `construir_mapa_cliente` ainda não portado) |
| NECESSITA REGRA DE NEGÓCIO | Comprovante de assinatura digital (é estado de outra etapa ou tipo documental próprio? decisão de negócio não registrada), vínculo Guia/certidão→cliente |
| AINDA NÃO MODELADO | Assiduidade, Horas Extras, Diárias, VR, VA, benefícios vinculados à pessoa/cliente, Certidões (hoje só existem no Airtable, confirmado na auditoria anterior) |

**Nenhum documento do universo ficou fora do mapa** — cada um tem um
caminho arquitetural identificado dentro do MESMO motor (nunca uma
arquitetura paralela), mesmo os que ainda não têm produtor de evidência
implementado.

## SKY Tatuí

Não tocado nesta missão, nem precisava ser — SKY usa os mesmos tipos e
o mesmo motor; a única diferença (competência `base - 1 mês`) já vive
inteiramente em `PoliticaCompetenciaPrestacao` (PR #91/#92), dimensão
ortogonal a `TIPO_DOCUMENTAL`.

## O que NÃO foi feito (registrado, não escondido)

- Nenhum produtor estrutural real (layout/geometria de página,
  `pdfplumber.extract_tables()`) — os sinais hoje chamados "estruturais"
  no texto (código de barras, linha digitável) já eram capturados pelos
  regex existentes; estrutura de verdade (posição/tabela) é gap
  registrado, não implementado.
- Nenhum novo tipo documental/regex novo — o universo de 17 tipos
  continua o mesmo; o motor geral é a capacidade de COMBINAR evidência
  para os tipos já existentes e para os futuros.
- OCR — fora de escopo, arquitetura já preparada para alimentar a MESMA
  camada de evidências quando implementado (o produtor textual já
  aceita qualquer texto extraído, de qualquer origem).
- Separação master→filhos — não portada; o motor não pressupõe
  "1 PDF = 1 entidade", mas a implementação real do fatiamento
  (`construir_mapa_cliente`) continua pendente.

## Documentação relacionada

- `docs/decisoes/resolucao-semantica-fase2e-v1.md` — compositor geral
  (PR #93), reaproveitado sem alteração.
- `docs/decisoes/competencia-esperada-prestacao-v1.md` — SKY Tatuí,
  dimensão ortogonal, sem relação com este motor.
