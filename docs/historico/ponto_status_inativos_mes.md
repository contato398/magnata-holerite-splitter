---
name: ponto-status-inativos-mes
description: Cruzar o Cartão Ponto do mês com o Status dos Funcionários — reativar quem trabalha mas está Inativo por engano; desligados do mês recebem só aquele mês
metadata: 
  node_type: memory
  type: project
  originSessionId: 798af317-f0d2-4a99-9677-e8e8f77ce019
---

**Aprendizado (2026-06-15).** O Cartão Ponto mensal (Secullum) lista todo mundo que teve marcação no mês — inclusive (a) gente que está **Inativa por engano** mas continua trabalhando, e (b) **desligados no meio do mês** que têm ponto parcial.

Como o disparo é filtrado por **Status="Ativo"**, sempre **cruzar o ponto com o Status** antes de enviar e tratar caso a caso. No fechamento de Maio/2026 (base `appaCpIVj7Q97VhFy`, TABLE_FUNC `tblNd8G66kjwos3eP`):
- **DIEGO LUIS NOGUEIRA DE CAMPOS** (Lago dos Ipes), **GUSTAVO MATOS MEDEIROS** (Cond. Tivolli), **LUCIANO MOREIRA DIAS** (Colaso) — estavam Inativos por engano → **reativados** (Status=Ativo) + WhatsApp normalizado (estavam fora da normalização por serem Inativos).
- **EVERTON SOUZA SANTOS** — desligado em 23/05/2026, mas trabalhou parte do mês → reativado **só para receber os documentos de Maio**. **DEVE voltar a Inativo após o disparo de Maio** (senão recebe Junho+).
- **DAVI CORREIA** — Inativo de verdade, fica fora (correto).

**Regra para os próximos meses:** ao reativar alguém vindo do ponto, lembrar de **normalizar o WhatsApp** dele também (a normalização em massa só pega Ativos). E manter uma lista dos "Ativos temporários do mês" (desligados) para reverter a Inativo depois do envio. Relaciona com [[faxina_base_funcionarios_jun2026]] e [[classificador_secullum_v2_26]].
