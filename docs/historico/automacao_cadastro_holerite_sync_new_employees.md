---
name: automacao_cadastro_holerite_sync_new_employees
description: "src/sync_new_employees.py: extrai cadastro do header do holerite (regex), casa por CPF no Airtable, prepara sync Secullum — PIS não existe no modelo"
metadata: 
  node_type: memory
  type: project
  originSessionId: c4f52740-3116-4b22-a0f6-9006fb43317c
---

Módulo criado em 25/06/2026: `src/sync_new_employees.py` (standalone, não
registrado como Blueprint/rotas no app.py ainda — roda hoje só localmente/CLI,
`python -m src.sync_new_employees --dry-run`).

## Achado importante: não existe "pasta de insumos" local
Holerites chegam por e-mail/upload e ficam só como anexo na tabela
**Holerites** do Airtable (`tblVaUgZeFfa5zRcH`, campo "PDF HOLERITE"
`fldGXsgmuADtZIgtx`). Não há diretório local que o robô varra. O script lê
essa tabela (mais recentes primeiro), não um filesystem.

## Achado importante: o holerite da Magnata NÃO imprime PIS
Confirmado contra 2 PDFs reais (Maio/2026, Davi Leme dos Santos e Leandro
Faustino Silveira): o cabeçalho do holerite tem Nome/CBO/Departamento,
Cargo+Admissão (mesma linha: "CONTROLADOR DE ACESSO Admissão: DD/MM/YYYY")
e CPF (rodapé, isolado), mas **PIS não aparece em lugar nenhum** do
documento. O regex de PIS existe no código por completude mas sempre
retorna `None` nesse template — não é bug, é ausência real do dado. Se PIS
for obrigatório, precisa vir de outra fonte (carteira de trabalho, ficha de
registro, e-Social).

## 3 campos novos na tabela Funcionários (Airtable, criados nesta sessão)
- **Grupo de Escala** (`fldMPI8FCJm33KFBC`, singleSelect: "Escala A - Dias
  Pares" / "Escala B - Dias Ímpares") — intenção definida na admissão, não
  leitura de dado existente. Cuidado: o rótulo PAR/ÍMPAR do
  Horario.Descricao da Secullum se mostrou NÃO confiável (ver
  [[v2_53_folga_bonus_assiduidade]] — funcionário rotulado "PAR" trabalha
  de fato dias ÍMPARES). Depois que houver batida real, confirmar que a
  escala efetiva bate com o grupo aqui definido.
- **Status de Sincronização** (`fldBwlxrtwnQmHQvh`, singleSelect:
  "Pendente" / "Sincronizado").
- **Secullum ID** (`fldPh3AVURpYXA60r`, texto) — guarda o `Id` retornado
  por `secullum_ponto.sincronizar_funcionario`.

## Atribuição manual (debate com a gerência, 25/06/2026)
LEANDRO FAUSTINO SILVEIRA (CPF 295.642.148-40, rec `recT1kfQl9Om73LGZ`) →
Escala A - Dias Pares. DAVI LEME DOS SANTOS (CPF 397.529.068-42, rec
`recCaqdv0ZF8Y1GbD`) → Escala B - Dias Ímpares. Ambos no posto INDI
(Instituto de Nefrologia e Diálise de Itapetininga), 07h-19h, Cargo
"Controlador de Acesso" — Status de Sincronização ainda "Pendente" (não
sincronizado com a Secullum ainda, só a extração/dry_run foi validada).

## Status
Extração validada (dry_run) contra os 2 holerites reais — Nome/Cargo/
Admissão/CPF saem certos, PIS fica None (esperado). Lógica de dedup/criação
no Airtable validada via mock com o estado real dos registros. **Ainda não
executado de verdade** (nem grava no Airtable nem chama a Secullum) — falta
decidir se/quando registrar como Blueprint no app.py para rodar no Render
(só lá existem AIRTABLE_API_KEY/credenciais Secullum).
