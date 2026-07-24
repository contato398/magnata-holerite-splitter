---
name: v2-27-ponto-master-splitter
description: Mestre consolidado de Cartão Ponto NÃO vai pela fila — usar /processar-folha-ponto (v2.27) que fatia por CPF e anexa por colaborador
metadata: 
  node_type: memory
  type: project
  originSessionId: 798af317-f0d2-4a99-9677-e8e8f77ce019
---

**Achado + correção (2026-06-15, v2.27, commit `0810be4`).** O handler de fila `_processar_folha_ponto` (`/processar-fila {"tipo_documento":"Folha de Ponto"}`) foi feito para **1 PDF por colaborador**: ele extrai 1 CPF/nome do texto e anexa o **arquivo inteiro** a essa única pessoa. Quando se manda o **mestre consolidado** (todos num PDF só), ele gruda o mestre inteiro **só na 1ª pessoa** (foi o que aconteceu: só o ADRIANO ficou com o ponto, 870 KB).

**Correção:** novo endpoint **`POST /processar-folha-ponto`** (v2.27) que **espelha o `/processar-holerites`** — fatia o mestre por CPF (`construir_mapa_cpf` + `extrair_pdf_colaborador`), casa por CPF (`buscar_funcionario_por_cpf`) e anexa o cartão individual em `F_FUNC_PDF_FOLHA` (`fldgBhXpEFmy20yxd`) via `_anexar_attachment` (upload base64 em content.airtable.com). **Não exige X-API-KEY** (só a AIRTABLE_API_KEY do servidor) → dá pra chamar do terminal: `-F "pdf=@mestre.pdf" -F "folha_mensal=Maio 2026"`.

**Resultado Maio/2026:** 152 páginas → **81 anexados** (1 por colaborador) + 71 "CPF não extraído" (são as **2ªs páginas** do Secullum, que não têm CPF — normal, a página-cartão com os registros diários é a que tem CPF). Demora ~330s no Render free (perto do timeout de 300s — atenção a mestres grandes).

**Regra para os próximos meses:** Holerite mestre → `/processar-holerites`; Cartão Ponto mestre → **`/processar-folha-ponto`** (NÃO o `/processar-fila`, que é para arquivos individuais). Depois rodar `/gerar-fila-envios-combinado`. Se um colaborador já tiver envio combinado "Preparando" com ponto errado, apagar o envio para regenerar (o gerador pula quem já tem pendente). Relaciona com [[v2_25_envio_combinado]] e [[reprocesso_direcionado_holerites]].
