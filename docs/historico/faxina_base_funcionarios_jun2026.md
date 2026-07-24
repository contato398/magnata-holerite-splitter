---
name: faxina-base-funcionarios-jun2026
description: "Limpeza+normalização da tabela Funcionários do Airtable em 15/06/2026 (deduplicação, ruído, WhatsApp 55DDD) e decisões tomadas"
metadata: 
  node_type: memory
  type: project
  originSessionId: 798af317-f0d2-4a99-9677-e8e8f77ce019
---

Em 2026-06-15 fiz faxina completa na tabela Funcionários (base `appaCpIVj7Q97VhFy`, TABLE_FUNC `tblNd8G66kjwos3eP`) antes do disparo em massa pela Evolution API. Trabalhei direto via Airtable MCP (não pelo app) porque o ambiente local **não tem** `AIRTABLE_API_KEY`/`EMAIL_WEBHOOK_KEY` (só existem no Render).

**Resultado:** base passou de 182 → 149 linhas. 33 exclusões + 80 WhatsApp normalizados para `55+DDD+número` (campo `fld0rXBW9tF2tqq7O`). Status = `fld5T04dlg1Yt6Xj8`.

**Achado-chave:** TODOS os 87 funcionários da Folha Abril/2026 já existiam no Airtable — nenhum "novo" a cadastrar. Cadastrar em lote teria criado ~87 duplicatas. **Sempre cruzar a folha contra a base (por Nome+CPF) antes de criar.**

**Decisões deliberadas (reaproveitar nas próximas folhas):**
- Filtro de disparo é estrito: **Status="Ativo" E WhatsApp preenchido**. O filtro Ativo já blinda contra empresas/pessoais/sem-status (não precisam ser deletados, mas deletei por higiene).
- Em duplicatas, manter o registro que tem **CPF batendo com a folha** (ex.: RAFAEL DE OLIVEIRA → mantive `reciud`, CPF 474.520.468-03).
- Funcionários **afastados (DIAS AFAST. INSS)** apareciam como Status="Outro" — são reais, reclassifiquei p/ "Ativo" (GUILHERME MARQUES `recPQAw`, RAFAEL BATISTA ELIAS `recV8c`). NÃO deletar afastados.
- Variantes com prefixo "MAG ..." no nome eram duplicatas de ruído.

**Pendências p/ próxima vez:** Ativos SEM WhatsApp ficam fora do disparo até ganhar número (em 15/06: KEREN, DAVI LEME, SIDNEY SALVADORI, LEANDRO FAUSTINO, INARA RAFAAELI, PATRICK ADRIEL, PEDRO GABRIEL KURNICH, RAFAEL BATISTA ELIAS). FABIO DOMINGUES (`rec8Ubf`, "Outro") deixado intacto por ser ambíguo.

Anexo de holerites + disparo são feitos no **pipeline oficial do Render** (app v2.24, `/normalizar-whatsapp` existe lá). Relaciona com [[fase5c_pre_cadastro_funcionarios]] e [[distribuicao_mensal_documentos_arquitetura]].
