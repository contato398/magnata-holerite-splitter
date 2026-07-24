---
name: reprocesso-direcionado-holerites
description: "Como reprocessar holerites faltantes sem duplicar — sub-PDF só com as páginas dos CPFs alvo, e dedup do mês por createdTime"
metadata: 
  node_type: memory
  type: project
  originSessionId: 798af317-f0d2-4a99-9677-e8e8f77ce019
---

**Procedimento (validado em 2026-06-15, fechamento de Maio).** A rota `POST /processar-holerites` (sem X-API-KEY, dá pra chamar do terminal com `-F "pdf=@arquivo" -F "folha_mensal=Maio 2026"`) fatia o mestre por CPF, casa por **CPF** e cria 1 Holerite + anexa por funcionário. Ela **NÃO deduplica** — rodar o mestre inteiro de novo recria tudo (duplicatas).

**Para corrigir faltantes sem duplicar:**
1. Primeiro **preencher/corrigir o CPF** dos funcionários que deram erro "Funcionário não encontrado" (o holerite traz o CPF correto; campo CPF = `fld0Y3bXdArkSIJxo`).
2. Montar um **sub-PDF só com as páginas desses CPFs** (pdfplumber localiza a página por CPF; pypdf/PyPDF2 escreve o novo PDF) e dar `/processar-holerites` só nele → cria apenas os que faltavam.

**Deduplicação do mês:** holerites duplicados se distinguem por `createdTime` (cada rodada tem um horário). Manter a rodada mais nova (mestre completo/correto) e apagar as antigas. Conferência: total − antigos = nº criados na rodada nova.

**Cuidados Maio/2026:** o mestre completo era `holerites salario maio.pdf` (93 CPFs), NÃO o `holerites maio 26.pdf` (parcial). Erros de CPF vieram de funcionários **sem CPF** na base ou com **CPF malformado** (ex.: LUIZ FERNANDO tinha `4393569687`). A rota demora ~280s p/ 93 holerites no Render free (perto do timeout de 300s) — para lotes grandes, vale dividir. Relaciona com [[ponto_status_inativos_mes]] e [[faxina_base_funcionarios_jun2026]].
