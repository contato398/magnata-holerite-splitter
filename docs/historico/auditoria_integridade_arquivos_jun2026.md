---
name: auditoria-integridade-arquivos-jun2026
description: "Auditoria 23/06 da tabela Arquivos — 5.109 registros, só 2 sem anexo físico; backlog 15/06 íntegro"
metadata: 
  node_type: memory
  type: project
  originSessionId: 798af317-f0d2-4a99-9677-e8e8f77ce019
---

Auditoria de integridade feita em 23/06/2026 sobre a tabela **Arquivos** (`tblRsvhz8oOcUqhkv`, base `appaCpIVj7Q97VhFy`), motivada pela preocupação do usuário de que documentos do backlog de 15/06 pudessem ter se perdido na fila.

**Método:** filtro `isEmpty` no campo de anexo `fldm6S1xnp8S6sKFE` ("Attachments") via Airtable MCP — caminho muito mais eficiente que paginar 5.109 registros (que estourou limite de tokens e deu erro 500 ao delegar a agente). Lição: usar `filters` com `isEmpty` para achar registros vazios em vez de varrer tudo.

**Resultado:** 5.109 registros totais, apenas **2 sem anexo físico** (99,96% íntegros):
1. `REGISTRO, NR01, FICHA DE EPI JOSE FRANCISCO (1).pdf` (rec9Al2NyLbJ4zsdW) — e-mail origem "colaboradores Menegazzo"
2. `Recibo de Pagamento.pdf` (recfTrxAAbU2Rg85h) — e-mail origem "SAVIAN - RES: Posto Vale Horistas"

Ambos com `Hash do Anexo` (`fldOB09YlKDEqKSFO`) preenchido → binário foi recebido/processado na entrada mas não gravou no campo. Ambos ainda vinculados ao e-mail de origem (tabela Emails Savian) → recuperáveis rebaixando da caixa.

**Conclusão p/ o usuário:** o PDF de cada documento fica fisicamente no storage do Airtable (v5.airtableusercontent.com), não é link externo que expira. O risco real do backlog [[v2_27_ponto_master_splitter]] não é perda de arquivo, e sim documentos travados em Status="Processando" que nunca foram classificados/distribuídos pelo /processar-fila. Backlog 15/06 = import retroativo em massa de Extratos/Holerites de competências Jan-Abr/2026 (createdTime 15/06 ≠ data do documento). Pendente: reprocessar os 2 sem anexo + destravar os ~1.300 em Processando.
