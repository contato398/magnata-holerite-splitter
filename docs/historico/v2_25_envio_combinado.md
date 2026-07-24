---
name: v2-25-envio-combinado
description: app.py v2.25 — endpoint /gerar-fila-envios-combinado envia Holerite + Cartão Ponto na MESMA mensagem WhatsApp
metadata: 
  node_type: memory
  type: project
  originSessionId: 798af317-f0d2-4a99-9677-e8e8f77ce019
---

Em 2026-06-15 implementei e dei deploy da **v2.25** (commit `bfca841`, Render `https://magnata-holerite-splitter.onrender.com`, `/health` confirmado 2.25).

**Funcionalidade:** `POST /gerar-fila-envios-combinado` (função `_gerar_fila_envios_combinado`) — cria **1 único envio WhatsApp por colaborador** com os 2 PDFs anexados em sequência **[Holerite, Ponto]** no campo `F_ENVIO_ARQUIVOS` (`fldiO4G7OO1FAjn5o`), Tipo=`TIPO_ENVIO_COMBINADO` = "Holerite + Cartão Ponto Mensal". A Evolution API envia os dois anexos na mesma mensagem.

**Critério de "pronto" (gera só pra quem tem os 3):** WhatsApp preenchido + Holerite do mês com PDF (filtra por `folha_mensal`, ex.: "Maio 2026", tem que bater exato com o campo) + PDF Folha de Ponto no prontuário (`F_FUNC_PDF_FOLHA`). Quem falta algum vai p/ `ignorados` com `motivos` (`holerite_do_mes_ausente`/`pdf_folha_ponto_ausente`/`whatsapp_ausente`). Ignora quem já tem envio combinado pendente (Status Preparando/Enviado) p/ não duplicar. Body: `{folha_mensal, limit, dry_run}` (dry_run=true padrão). Auth: header `X-API-KEY` = `EMAIL_WEBHOOK_KEY`.

**Limitação de acesso (importante):** as chaves `EMAIL_WEBHOOK_KEY` e `AIRTABLE_API_KEY` só existem no ambiente do Render — **não estão no ambiente local**, então NÃO consigo chamar os endpoints autenticados daqui. Para simular "quem está pronto" eu leio o Airtable direto via MCP (read-only). O disparo em si é externo (Evolution API lendo a fila de Envios). Convive com [[faxina_base_funcionarios_jun2026]] e os endpoints individuais `/gerar-fila-envios` e `/gerar-fila-envios-ponto`.
