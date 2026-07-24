---
name: v2_65_saneamento_final_escalas_jun2026
description: "29/06/2026: estado final do saneamento de escalas pós-migração SEM INTERVALO — 11 correções de paridade/turno confirmadas, 2 revertidas pra horário com intervalo, metodologia validada"
metadata: 
  node_type: memory
  type: project
  originSessionId: c4f52740-3116-4b22-a0f6-9006fb43317c
---

Fecha o ciclo iniciado em [[v2_61_diagnostico_inconsistencia_escala]] e
[[v2_62_estabilizacao_secullum_e_onboarding_zero_batida]]. Todas as
correções abaixo foram **confirmadas na Secullum** (não só recomendadas).

## Metodologia que funcionou (validada com dado real)
Em vez de calcular paridade pelo dia-do-mês (falha, ver v2.61) ou usar o
rótulo Horario.Descricao (não confiável, ver v2.53), usar: **qual dos
dois dias-base reais (28/05 ou 29/05) tem a primeira batida de entrada
real do colaborador** → 28/05=PAR, 29/05=ÍMPAR. Funciona porque os 10
horários "SEM INTERVALO" da Secullum têm uma Data Base fixa e real
configurada (não uma conta de calendário). Confirmar SEMPRE turno
(diurno/noturno) E intervalo (tem ou não) com a operação antes de fechar
— ver casos abaixo onde meu cálculo automático errou.

## 11 colaboradores corrigidos (paridade/turno), confirmados na tela
Arthur Soares, Gabriel Gonçalves B.C. Pinto, Leandro Oliveira dos Santos,
José Francisco de Moraes Lima, Celso Conceição Lima, Matheus Augusto Muza
Medeiros, José Antonio Generoso Neto (esse também corrigiu TURNO, não só
paridade — era diurno cadastrado, é noturno 18h-06h real), Pedro
Kempoviki Junior (turno noturno 18h-06h, Quinta das Palmeiras — ajuste
manual da diretoria, não meu) e Raphael Antonio Pedroso Marino (ajuste
manual da diretoria).

## 2 casos revertidos para horário COM intervalo (não são Turno Solo)
- **Lucídio Nunes dos Santos** (Moradas do Sol): tem intervalo de
  verdade → voltou pro Numero 11 ("12X36 19H-07 PAR", com intervalo),
  NÃO o "SEM INTERVALO" que eu tinha sugerido inicialmente.
- **Denilson Felipe Rodrigues da Cruz** (Lago dos Ipês): tem intervalo
  de verdade → voltou pro Numero 3 ("12x36 07h-19h ÍMPAR", com
  intervalo).
- **Pendência de monitoramento**: ambos voltaram pra horários "estilo
  antigo" (sem o parâmetro de virada dos novos "SEM INTERVALO") — só dá
  pra confirmar que o bug de virada de dia não volta observando batida
  real nos próximos 2-3 dias. Reconferir antes de declarar definitivo.

## Postos de exceção (100% intervalo) — granularidade importa
- **Unimed Virgílio** (só 2 pessoas: João Sales, Teodolino): removido
  da exceção de vez no código (`EXCEPTION_POSTO_IDS`, v2.62) — confirmado
  que é turno solo real pros dois.
- **Moradas do Sol** (18 pessoas!): **NÃO removido da exceção.** O
  Lucídio inicialmente parecia ser exceção aqui também, mas a diretoria
  confirmou que ele TEM intervalo — a regra do posto continua certa.
  Não generalizar de 1 pessoa pra um posto com 18 vinculados sem
  confirmação explícita.

## Erros meus identificados e corrigidos nesta rodada
- Recomendei "manter 07h-19h" pro Lucídio quando o real era 19h-07h
  noturno (não carreguei o achado antigo do v2.61 pra cá).
  Recomendei horário 06H-18H pro Denilson quando o real era 07h-19h
  (troquei a faixa por engano ao montar a tabela final). Lição: ao
  montar tabela de correção em lote, sempre re-confirmar contra o
  cadastro ORIGINAL da pessoa, não só contra a paridade calculada.
- Erro de identidade CPF Milton x Eduardo Caetano: ver [[v2_64_erro_identidade_cpf_milton_eduardo]].
