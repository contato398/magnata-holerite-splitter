---
name: v2_62_estabilizacao_secullum_e_onboarding_zero_batida
description: "28/06/2026: migração de 32 colaboradores Solo p/ horários SEM INTERVALO, bug de virada de dia pós-recálculo (instável), Sidney/Wilza zero-batida = onboarding não risco"
metadata: 
  node_type: memory
  type: project
  originSessionId: c4f52740-3116-4b22-a0f6-9006fb43317c
---

## Migração para horários "SEM INTERVALO" (28/06/2026)
Diretoria criou manualmente 10 horários novos na Secullum (Numero 18-27,
nomenclatura "SEM INTERVALO" PAR/ÍMPAR para os turnos 18h-06h, 19h-07h,
06h-18h, 07h-19h, 20h-08h) e migrou os 32 colaboradores Turno Solo
(cargo/posto sem rendição, ver `EXCEPTION_POSTO_IDS`/`_funcao_e_solo` em
[[v2_61_diagnostico_inconsistencia_escala]]) manualmente pela interface web
— **não existe endpoint na API da Secullum pra isso** (`Funcionarios` só
tem post/get/delete, sem put/patch; `Horarios` só get/delete, sem post;
`Estruturas` é hierarquia organizacional, não tem campo de horário).
Confirmado exaustivamente via Swagger oficial.

Verificado em 28/06/2026 via `GET /IntegracaoExterna/Horarios` direto (não
o `/secullum/debug?listar_horarios=1`, que só deriva de funcionários já
vinculados e por isso não detecta horário recém-criado sem ninguém nele
ainda — usar `listar_horarios_catalogo=1`, novo em v2.61.2): migração dos
32 está 100% completa, nenhum Turno Solo com escala 12x36 real ficou
pendente. 2 correções de dado feitas no Airtable: Pedro Augusto Machado
Lopes (posto errado, Quality Life → Lago dos Ipês, que é posto de
exceção com intervalo); Lucas Rodrigues Machado e Vitor Ivaldo Oliveira
de Andrade (Status Ativo desatualizado → Inativo, não trabalham mais lá).

## Bug de virada de dia pós-recálculo — AINDA INSTÁVEL, dados mudam entre consultas
Depois do "Reprocessamento de Cálculos" da Secullum, comparei scan antes x
depois (mesma competência 2026-06): bônus elegível caiu de 11 para 6 —
piorou, não melhorou. Causa: várias pessoas (migradas e não-migradas, ex.
Lucídio Nunes dos Santos que está intocado no horário antigo Numero 3)
passaram a exibir "Falta de 11:00"/"Batida Ímpar" em sequência longa de
dias — claramente artefato de cálculo, não falta real. Confirmado com
dado bruto do Milton Paes (já migrado, Numero 21): a maioria dos plantões
pareia certo numa única linha, mas 1-2 dias residuais (ex. entrada
isolada de manhã sem plantão na noite anterior, já que o dia anterior era
folga) não se explicam pela teoria de "entrada colada com jornada
anterior" — **não implementei nenhuma regra automática de "limpar
falta falsa"** porque o padrão não é uniforme e a contraprova (Milton)
mostrou que aplicar isso cegamente teria inventado plantão que não dá pra
confirmar que aconteceu. Pior ainda: o mesmo funcionário (Milton) mudou de
resultado (Falta vs Folga no mesmo dia 28/05) entre duas consultas
seguidas minutos depois — **a Secullum ainda está processando a fila em
segundo plano em 28/06/2026**, dados não são confiáveis pra fechar
planilha de bônus/Art.71 até estabilizar. Decisão: aguardar, não rodar
nova varredura completa nem fechar relatório até confirmação de
estabilização.

## Zero batida ≠ risco operacional, quando é onboarding em andamento
Confirmado pela diretoria (28/06/2026): SIDNEY SALVADORI JUNIOR e WILZA
APARECIDA DE SOUZA nunca bateram ponto — não é risco/afastamento, é
porque foram incluídos recentemente na Secullum (lote do saneamento de
27/06/2026, ver [[v2_60_saneamento_secullum_jun2026]]) e ainda não
começaram a usar o relógio de ponto. Mesma lógica provavelmente vale pros
outros 3 do mesmo lote (Jose Jacson Biscaia Martins, Guilherme Marques de
Almeida, Cinthia Renata Bastida Flor de Souza) se também aparecerem com
zero batidas. Plano da empresa: folha de ponto individual manual pra maio
desses casos; a partir de amanhã (29/06/2026) a diretoria aumenta o plano
da Secullum (remove o limite de 85 ativos) e passa a exigir batida
correta de todos. **Não classificar esses casos como "Glosa Crítica:
risco operacional/afastamento não parametrizado"** no texto do motor —
é uma categoria diferente (onboarding em andamento), e a Glosa Crítica
genérica do v2.57 ainda não distingue isso; ajuste sugerido mas não
implementado ainda (esperando a estabilização da Secullum antes de
qualquer mudança no motor).

## Pendências em aberto
- Wilza ainda precisa de decisão PAR ou ÍMPAR pro horário 19h-07h (ela é
  nova, sem histórico de batida real pra inferir).
- Aguardar Secullum estabilizar o reprocessamento antes de rodar nova
  varredura completa ou fechar qualquer planilha de bônus/Art.71.
- Considerar diferenciar "Glosa Crítica" (risco real) de "onboarding sem
  uso ainda" no texto do motor, quando formos tocar nele de novo.
