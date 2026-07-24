---
name: fase5c-pre-cadastro-funcionarios
description: Status da Fase 5C (pré-cadastro automático em Funcionários a partir de Contrato de Experiência/Trabalho) no projeto magnata-holerite-splitter
metadata: 
  node_type: memory
  type: project
  originSessionId: 798af317-f0d2-4a99-9677-e8e8f77ce019
---

Fase 5C implementada e validada em produção (app.py v2.16, commit `e0b131f`, repo `https://github.com/contato398/magnata-holerite-splitter.git`).

`/processar-fila` com `tipo_documento="Contrato de Experiência"/"Contrato de Trabalho"` agora, além da extração da Fase 5B, decide `decisao_5c` ∈ {`criar_pre_cadastro`, `funcionario_ja_existe`, `enviar_para_revisao`} e, em `dry_run=false`, cria registro em Funcionários (campos: Nome Completo, CPF, Status, Cargo, Data de Admissão).

**DIRETRIZ DEFINITIVA (2026-06-13) sobre Status no pré-cadastro automático**: o usuário decidiu que "Pré-cadastro" NÃO deve ser etapa manual obrigatória/corriqueira. Objetivo: máxima automação, revisão manual só em exceções.

Nova arquitetura de decisão exigida para a Fase 5C (ainda NÃO implementada — código v2.16 continua com apenas 3 saídas: `criar_pre_cadastro` [grava Status="Ativo"], `funcionario_ja_existe`, `enviar_para_revisao`):

- `cadastrar_ativo_automaticamente`: dados essenciais válidos + confiança alta + sem ambiguidade + CPF não duplicado → cria em Funcionários com Status="Ativo" direto.
- `criar_pre_cadastro_seguro`: dados essenciais válidos mas com alguma incerteza intermediária (estado de transição/segurança) → Status="Pré-cadastro".
- `enviar_para_revisao`: CPF ausente/inválido, nome ausente/suspeito, data ausente/inválida, duplicidade/divergência, baixa confiança, avisos de qualidade/texto truncado.
- `ignorar_documento`: documento não aplicável (ainda não modelado no código atual).

**Why:** revisão manual deve ocorrer só em exceções (CPF inválido, nome suspeito, data inválida, duplicidade, divergência, baixa confiança, texto truncado) — não em todo contrato válido.

**How to apply:** ao implementar essa mudança (autorização pendente), expandir `_processar_contrato_stub`/`_montar_campos_pre_cadastro` para os 4 ramos acima, com 2 limiares de confiança (um para "Ativo automático", outro menor para "pré-cadastro seguro"). Não confundir com a v2.16 atual, que já grava "Ativo" para todo `criar_pre_cadastro` (sem o ramo intermediário "Pré-cadastro").

Primeiro registro real criado por essa lógica: `rechTPdRDdTLgG9WW` (Funcionários), CPF `385.051.798-54`, Nome "INARA RAFAAELI DE OLIVEIRA MUNIZ", a partir do contrato de teste `recjxU9wZnJmOzdZg`.

Cuidado: requisições duplicadas (ex. duplo Enter no PowerShell durante testes) podem gerar 2 chamadas ao endpoint — a lógica de checagem de CPF evita duplicidade real, mas o JSON retornado ao cliente pode refletir apenas a 2ª chamada (`funcionario_ja_existe`) mesmo que a 1ª tenha criado o registro. Sempre verificar o estado real no Airtable se o resultado parecer inconsistente com testes anteriores.
