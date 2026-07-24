---
name: v2_61_diagnostico_inconsistencia_escala
description: "v2.61/2.61.1: diagnóstico rótulo x ground truth da escala — 9 casos de turno errado (individual) e 31 de paridade PAR/ÍMPAR invertida (achado SISTÊMICO, não 31 bugs individuais)"
metadata: 
  node_type: memory
  type: project
  originSessionId: c4f52740-3116-4b22-a0f6-9006fb43317c
---

Em 27/06/2026, a pedido da diretoria, implementei `detectar_inconsistencia_escala`
em `secullum_ponto.py` (v2.61) para comparar o rótulo declarado da escala
(Horario.Descricao: tag PAR/ÍMPAR + faixa de horário) contra o
comportamento real (ground truth: marcador FOLGA real + Entrada1 real) —
resultado exposto em `resumo['inconsistencias_escala']` da varredura
`/secullum/varrer`. Ver também [[v2_55_gravacao_real_jun2026]] (ground
truth FOLGA) e [[automacao_cadastro_holerite_sync_new_employees]] (campo
Grupo de Escala que pode ter herdado a mesma suposição equivocada).

## 2 bugs corrigidos antes do resultado ser confiável (v2.61.1)
- `_primeira_entrada_minutos` usava `min()` entre TODAS as colunas
  Entrada do dia. Em turno noturno (ex. 19h-07h), a volta de intervalo
  (Entrada2, ex. 01h) é numericamente menor que a Entrada1 real (19h) sem
  ser o início do turno — invertia a leitura. Corrigido pra usar
  especificamente a Entrada1 (menor número de coluna).
- Checagem de paridade só faz sentido em escala que ALTERNA dia sim/dia
  não (12x36). Em escala cheia (5x2/6x1, quase sem folga) a distribuição
  cai perto de 50/50 só pelo calendário — não é erro. Exige agora >=20%
  de dias de folga no período E maioria clara (>=65%) antes de apontar.

## Resultado da varredura completa (competência 2026-06, 85 calculados)
**40/85 (47%) com alguma inconsistência**, mas em DUAS naturezas bem
diferentes:

### 9 casos de TURNO (dia/noite) errado — parecem erro INDIVIDUAL real
Mesmo padrão do caso original ANDRE LUIZ DE MORAES PEREIRA RIBEIRO
(declara 7h, bate de fato às 18h). Lista completa: Andre Luiz, Franklin
Sebastiao Neves de Camargo, Laercio de Proenca, Lucas Protasio Sebastiao,
Lucidio Nunes dos Santos, Pedro Kempoviki Junior, Rosa Antonia da Silva,
Teodolino Munis Fernandes Junior, Vitor Ivaldo Oliveira de Andrade.
Diferença declarado x real entre 6h e 12h. Candidatos a revisão manual de
horário vinculado.

### 31 casos de paridade PAR/ÍMPAR invertida — achado SISTÊMICO, não 31 bugs
Toda vez que o rótulo é "PAR", o real é majoritariamente ÍMPAR; toda vez
que é "IMPAR", o real é majoritariamente PAR — 100% consistente na mesma
direção em 31 pessoas diferentes (ex.: Carlos Alberto 2 par/14 ímpar,
Jerry Douglas 13 par/4 ímpar). Essa uniformidade descarta erro de
vinculação caso a caso — é muito mais provável que a etiqueta "PAR"/
"ÍMPAR" da Secullum não signifique literalmente "dia par/ímpar do
calendário" pra essa empresa (nome de turma/grupo interno com outro
referencial). **Não tratar como 31 correções individuais** — confirmar
primeiro com quem configura as escalas o que o rótulo de fato representa.
Lista completa dos 31: Adriano de Albuquerque Angarten, Antonio Marcos
Jose de Carvalho, Ariel Rodrigues de Moraes, Carlos Alberto Moutinho da
Silva Ferreira, Carlos Eduardo Tavares Rodrigues Junior, Celso Conceição
Lima, Divaldo da Silva, Douglas Patricio Domingues, Eduardo Caetano,
Gustavo Monteiro Ramos, Gustavo Vieira, Herbert de Souza Queiroz, Jeferson
William Queiroz, Jerry Douglas de Souza Diniz, Josiel Ricardo Nunes da
Silva, Kleber Willians Monteiro Gomes, Leonardo Henrique de Souza Bove
Ramos, Leonardo Miranda Vieira de Camargo, Lucas Vinicius de Lima Franci,
Luciano Moreira Dias, Luiz Carlos Martins Machado, Marcelo Jordao Amalfi,
Marcus Vinicius Machado, Marilia Aparecida Sampaio da Silva, Nyckollas
Daniel Vieira da Cruz, Rogerio Fernando Vaz, Samuel Ricardo Nunes da
Silva, Tiago Jose de Lima Vieira, Wandui Aparecido Lopes da Silva, William
Farias Gonçalves, Yuri Martins Vieira.

## Cuidado para o futuro
Confirmar o que "PAR"/"ÍMPAR" significa de fato na config da Secullum
antes de reaproveitar esse rótulo em qualquer lugar (já não é usado para
decisão de negócio no motor de auditoria, e isso deve continuar assim).
Reavaliar a atribuição manual de Leandro Faustino Silveira (Escala A =
Pares) e Davi Leme dos Santos (Escala B = Ímpares) quando eles tiverem
batidas reais — pode estar igualmente invertida.
