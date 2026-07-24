---
name: v2_64_erro_identidade_cpf_milton_eduardo
description: "28/06/2026: erro real meu — investiguei Eduardo Caetano (CPF 21380731810) rotulado como Milton Paes de Almeida (CPF real 08184946899) por várias mensagens; sempre confirmar Nome retornado, não só CPF"
metadata: 
  node_type: memory
  type: project
  originSessionId: c4f52740-3116-4b22-a0f6-9006fb43317c
---

## O erro
Durante a investigação do "bug de virada de dia" pós-migração SEM
INTERVALO (28/06/2026), usei CPF `21380731810` em múltiplas consultas
`/secullum/debug?cpf=...` rotuladas como "Milton Paes de Almeida" — toda
a análise detalhada (escala limpa até 12/06, colapso de 7 plantões
seguidos a partir de 14/06, a disputa com a diretoria sobre "data de
histórico 20/06") foi, na realidade, sobre **EDUARDO CAETANO**. O CPF
real do Milton Paes de Almeida é `081.849.468-99` (08184946899).

Só percebi ao montar uma tabela cruzando CPF+Nome lado a lado a partir de
dado fresco (Matriz 1 da auditoria de 4 matrizes) — o `21380731810`
aparecia com o nome "EDUARDO CAETANO", não Milton.

## Causa raiz provável
Peguei o CPF do Milton de um dict Python (`bonus_assiduidade`) numa
etapa anterior sem confirmar visualmente o campo `Nome`/`Cpf` retornado
pela própria chamada de debug — confiei que a chave que eu mesmo grabei
estava certa. Nunca validei cruzando nome confirmado pela API contra o
nome que eu pretendia investigar.

## Lição de processo (aplicar sempre)
Ao fazer qualquer consulta `/secullum/debug?cpf=X` pra investigar uma
pessoa específica, **sempre imprimir e confirmar
`funcionario_amostra.Nome` e `.Cpf` retornados antes de interpretar os
dados** — nunca assumir que o CPF que eu mesmo extraí de um dict
anterior é o correto sem essa reconfirmação. Isso vale especialmente
quando o CPF foi obtido por substring match de nome (`if 'MILTON' in
nome.upper()`) em vez de busca exata.

## Resultado real do Milton (CPF 081.849.468-99) — corrigido
Horário no momento da verificação: oscilou entre "07H AS 19H **PAR**
SEM INTERVALO" (na consulta que alimentou a Matriz 1) e "07H AS 19
**IMPAR** SEM INTERVALO" (numa consulta minutos depois) — terceira
evidência de instabilidade ainda não resolvida do lado da Secullum,
ver [[v2_62_estabilizacao_secullum_e_onboarding_zero_batida]]. Dado de
batida real (verificado): apenas 3 dias problemáticos em 32 (28/05 zero
batida, 14/06 e 24/06 batida ímpar isolada) — não tem nada parecido com
o "colapso de 14/06 em diante" que erroneamente atribuí a ele antes.

## Resultado real do Eduardo Caetano (CPF 213.807.318-10) — quem
realmente tem o padrão de colapso
Esse é o nome correto para a análise "limpo até 12/06, depois 7
plantões consecutivos vazios a partir de 16/06" que discuti extensamente
com a diretoria sob o nome errado. Esse achado em si continua válido
como dado — só o nome estava errado. Precisa de re-confirmação com a
diretoria sob o nome certo antes de qualquer decisão de bônus/Art.71.
