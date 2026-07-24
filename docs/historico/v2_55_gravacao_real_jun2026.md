---
name: v2_55_gravacao_real_jun2026
description: "v2.55: intervalo por posto/função, distinção jurídica de troca, 1ª gravação REAL no Airtable (Jun/2026)"
metadata: 
  node_type: memory
  type: project
  originSessionId: c4f52740-3116-4b22-a0f6-9006fb43317c
---

Primeira gravação real (dry_run=false) do motor `/secullum` ([[v2_49_secullum_ponto]],
[[v2_53_folga_bonus_assiduidade]]), autorizada explicitamente pela diretoria em
25/06/2026, período 01-24/06/2026.

## Regras v2.55 (diretivas finais da diretoria)
- **Intervalo por posto+função**: 5 postos de exceção (IDs Airtable, não texto:
  rec7sjIAiKZd0ermb=Moradas do Sol, rechZpE1xGvFXUNyL=Castrolanda,
  recd8OPca3z9dk2fq=Lago dos Ipês, reclQfhuQSPVLZgB3=Unimed Virgílio,
  recZKE9y6Hn1Hl1Kg=Unimed Shopping) → 100% intervalo, qualquer função.
  Fora desses postos, decide pelo Cargo (Airtable, fallback Funcao Secullum):
  Controlador/Portaria/Perímetro = turno solo (2 batidas, +1h Art.71 CLT,
  bônus preservado); demais = têm intervalo (2 batidas = Intervalo
  Pré-Assinalado CLT, sem Desvio, mas corta bônus por "falta de zelo").
- **Saldo de plantões**: classifica pareamento falta-crítica×folga-trabalhada
  por saldo do mês. Neutro pra ambos → "Troca de Plantão (Informal)" (bônus
  preservado de quem cedeu). B acima/A abaixo → "Dobra/Cobertura de
  Emergência (FT)" (falta de A mantida p/ atestado). Ambíguo → fallback antigo.
- Campo novo no Airtable: **"Bônus Assiduidade Jun/2026"** (singleSelect,
  `fldPMJrQP5IAAEMxL`, tabela Funcionários) — criado nesta sessão.

## Resultado da gravação real (01-24/06/2026)
- **566 alertas** detectados (292 Desvio de Carga + 274 Batida Ímpar; 358
  novos criados, 208 já existentes via dedup). **0 casos** de Troca
  Informal/Cobertura de Emergência (esperado — depende de Folga Trabalhada,
  que é estruturalmente quase indetectável, ver [[v2_53_folga_bonus_assiduidade]]).
- **78/88 processados** (8 inativos, 2 com erro persistente da Secullum:
  VICTOR HENRIQUE MACHADO DA SILVA e VITOR IVALDO OLIVEIRA DE ANDRADE —
  precisam reprocesso isolado depois, quando a cota da Secullum normalizar).
- **Bônus gravado**: 49 Sim (R$100) / 29 Não (R$0). Maioria dos "Não" por
  "falta de zelo" (intervalo não registrado) — concentrado nos 5 postos de
  exceção, consistente com o achado de [[cronicos_relatorio_postos_jun2026]]
  (mesmos postos problemáticos). 30 funcionários ganharam hora extra Art.71
  CLT (turno solo), total 297h no período.

## Operacional (reforça [[v2_53_folga_bonus_assiduidade]])
Hoje (25/06) o volume de chamadas de debug+validação+scan real esgotou a
cota da Secullum várias vezes — servidor (gunicorn 1 worker) trava até o
/health enquanto uma chamada longa em retry está em andamento; esperar
2-3min e tentar de novo resolve. Lotes de 2-5 funcionários foram necessários
na cauda do scan.

## v2.56 (mesmo dia) — período de apuração oficial 28→28
Diretoria corrigiu: a folha da Magnata fecha do dia 28 do mês anterior ao
dia 28 do mês de competência (não mês comercial 01-30). Nova função
`periodo_folha(ano, mes)` + parâmetro `competencia="YYYY-MM"` em
`/secullum/varrer` (prioridade sobre data_inicio/data_fim; default = a
competência vigente). Data final nunca passa de hoje (`periodo_incompleto`
no resumo quando corta). Reprocesso real Jun/2026 com a janela 28/05-25/06
(28-30/06 ainda não existem — falta reprocessar depois): **0 erros** em
todos os 88 funcionários (Victor/Vitor do v2.55 resolveram sozinhos, cota
Secullum normalizou). 132 alertas novos (cobrindo os dias 28-31/05 e 25/06
recém-incluídos), 600 já existentes (dedup ok). Bônus recalculado na janela
maior: 45 Sim / 35 Não (caiu de 49 porque a janela maior pegou mais
ausências/atrasos). Art.71 CLT: 34 funcionários, 356h.
**Pendência**: reprocessar de novo após 28/06/2026 para fechar com os dias
26-28/06 reais (rodar `{"dry_run": false, "competencia": "2026-06"}` de novo).
