---
name: v2_53_folga_bonus_assiduidade
description: "v2.53/v2.54 Secullum: Folga Trabalhada via marcador literal (não PAR/ÍMPAR), Bônus Assiduidade via Atras./Adian. nativos, 3 achados de dados não-confiáveis"
metadata: 
  node_type: memory
  type: project
  originSessionId: c4f52740-3116-4b22-a0f6-9006fb43317c
---

Evolução do módulo `/secullum` ([[v2_49_secullum_ponto]]) em 25/06/2026, a
pedido do usuário: remover dependência de posto (Airtable) e adicionar Bônus
de Assiduidade (R$ 100,00/mês).

## 3 achados de dados NÃO confiáveis no Horario.Descricao (não usar p/ nada preciso)
1. **Tag PAR/ÍMPAR invertida**: funcionário rotulado "12X36 19H - 07 PAR"
   (Carlos Alberto) trabalha de fato nos dias ÍMPARES do calendário. É só
   nome de turma interno, não a paridade real.
2. **Coluna "Normais" sempre vazia em ~27/88 contas** (config de horário
   comum, ex. "12x36 06h-18h PAR" Id=1, "12x36 07h-19h ÍMPAR" Id=3): TODAS as
   horas (mesmo dia normal de trabalho) caem em "Extras", nunca em "Normais".
   Por isso a heurística "Normais=0 e Extras>0 ⇒ folga trabalhada" foi
   tentada e descartada (gerava falso-positivo em 100% dos dias normais
   desses funcionários — ex.: ARTHUR SOARES, ANDRE LUIZ).
3. **Faixa de horário do texto não bate com a real**: "12x36 07h - 19h -
   ÍMPAR" (André Luiz) mas as batidas reais são todas no período 19h-07h
   (plantão noturno). Calcular atraso/saída-antecipada a partir dessa faixa
   deu um "atraso de 11h46" absurdo num dia em que a Secullum nativa (coluna
   "Atras.") corretamente reportou ZERO atraso.

**Lição**: qualquer cálculo que precise ser preciso deve usar as colunas que
a própria Secullum já calcula (Faltas, Atras., Adian., marcador literal
FOLGA/Feriado), nunca texto livre de Horario.Descricao.

## Mecanismo final (v2.54)
- **Folga teórica**: SÓ pelo marcador literal "FOLGA"/"Feriado" nas colunas
  Entrada/Saída N (`_dia_e_folga_teorica`). Zero batidas num dia assim é
  ignorado (não é falta) — confirmado contra dados reais de 3 tipos de
  escala diferentes (12x36 noturno, 12x36 diurno, comercial+sábado).
- **Folga Trabalhada / Troca de Plantão cruzada**: ESTRUTURALMENTE quase
  impossível de detectar com os dados disponíveis — quando a pessoa bate
  ponto na folga, a Secullum aparentemente substitui o marcador "FOLGA"
  pelos horários reais (mesmo "look" de um dia normal trabalhado), sem
  sinal confiável que diferencie os dois casos. Resultado real do scan de
  junho: **0 pareamentos encontrados** (não é bug, é limitação de dados).
- **Desconsiderar postos**: removidas `_mapa_locais_airtable`/
  `_colegas_de_local`; pareamento (quando ocorre) é 100% por escala,
  empresa toda, sem filtro de local do Airtable.
- **Bônus de Assiduidade**: usa direto `Atras.`/`Adian.` (colunas nativas da
  Secullum, > 5 min tolerância) + `Faltas` > 0 com zero batidas. Dias de
  folga teórica não contam. Resultado em `resumo['bonus_assiduidade']`.

## Resultado do scan real (01-24/06/2026, dry_run, v2.54)
79 calculados (8 inativos, 1 erro: **PEDRO AUGUSTO MACHADO** trava/falha
repetidamente nas chamadas Secullum — investigar esse CPF específico antes
do próximo scan). 608 alertas (312 Desvio de Carga + 296 Batida Ímpar, 0
Troca/Folga). 66/79 elegíveis ao bônus parcial (mês não fechado, só até 24/06).

## Operacional
Render free + gunicorn 1 worker: requisições muito longas (vários 429 em
sequência) BLOQUEIAM até o /health, não só o /secullum. Usar lotes pequenos
(5 funcionários) quando suspeitar de funcionário problemático; nunca rodar
scan em loop bash sem checar `http_code`/JSON antes de reusar
`proximo_offset` (já vazou um loop infinito reprocessando dado stale 1x).
