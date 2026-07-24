---
name: v2-48-processamento-backlog-holerites
description: "v2.46-2.48 competência do holerite + execução do backlog 15/06 (248 arquivados, 111 sinalizados)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 798af317-f0d2-4a99-9677-e8e8f77ce019
---

23/06/2026: processado o backlog de Holerite do import retroativo de 15/06 (ver [[auditoria-integridade-arquivos-jun2026]]).

**Correção de código (v2.46→2.48):** `extrair_competencia_holerite()` lê a competência do PDF — holerite usa mês POR EXTENSO ("Mensalista Abril de 2026" / "Março de 2026"); fallback numérico ("Competência: 04/2026") p/ extratos. `_processar_holerite` arquiva no mês da competência, não no default "mês anterior". GUARDA: sem competência detectada → `acao=competencia_nao_detectada`, status Erro + Pendência, NÃO cria holerite (rescisão mal classificada como Holerite não vira holerite-fantasma em Maio).

**Execução (script `executar_holerite_ponto.py`, lotes de 5, retry em 502/503):** Render free tier dá 502/503 sob carga pesada de PDF — resolver com lotes pequenos + pausa + retry com backoff. Resultado final, fila zerada:
- 359 registros tipo "Holerite" processados.
- 248 holerites ARQUIVADOS no mês correto (223 atualizados, 15 criados, 10 c/ anexo conflitante preservado), distribuídos em ~22 competências (Fev/2026 73, Jan/2026 53, Dez/2025 50… cauda até 2024; só 2 em Maio/2026). Sem a correção, os 248 cairiam todos em Maio errado.
- 111 sinalizados como Pendência: 59 `funcionario_nao_encontrado` + 52 `competencia_nao_detectada` (rescisões mal classificadas).
- Folha de Ponto: 13 → 12 anexadas ao prontuário, 1 não encontrado.

**Pendências geradas a tratar:** (1) ~~reclassificar rescisões~~ FEITO (ver abaixo); (2) revisar os ~59 holerites com funcionário não encontrado (ex-colaboradores fora da base ou CPF não extraído) — seguem como Tipo=Holerite Status=Erro c/ Pendência "Funcionário não encontrado". "Outro"(404)+"Não Identificado"(129) do backlog seguem intocados de propósito (já salvos; processá-los = só ruído).

**Reclassificação rescisões (concluída 23/06):** `reclassificar_rescisoes.py` releu os 115 Holerite+Erro e separou por conteúdo: 47 → Rescisão (sem competência + marcador de rescisão), 59 mantêm Holerite (têm competência), 9 ambíguos (comprovantes salário/RPA/Buritis — deixados). Depois `processar_rescisoes.py` rodou /processar-fila tipo=Rescisão → 56 rescisões (47 reclassificadas + 9 originais) viraram `rescisao_extraida_pendencia_criada` (Pendência rica c/ nome/CPF/data/aviso/motivo p/ confirmação humana; handler nunca inativa funcionário sozinho). **LIÇÃO:** rede local do usuário cai intermitentemente falando com api.airtable.com; um PATCH que dá ConnectionError no cliente PODE ter aplicado no servidor (35 dos 47 aplicaram apesar de "falha"). Para WRITES quando a rede está instável, usar **Airtable MCP** (server-side, imune) em vez de script local. Os 9 ambíguos seguem como Holerite+Erro.
