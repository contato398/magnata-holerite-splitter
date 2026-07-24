---
name: classificador-secullum-v2-26
description: "Cartão Ponto do Secullum cai como \"Outro\" no intake se o regex não tiver \"Cartão Ponto\"/\"Secullum\" — corrigido na v2.26"
metadata: 
  node_type: memory
  type: project
  originSessionId: 798af317-f0d2-4a99-9677-e8e8f77ce019
---

**Bug descoberto em 2026-06-15 (corrigido na v2.26, commit `7dd89d6`).** O intake classifica documentos pelo **conteúdo (texto)** do PDF, não pelo nome do arquivo (`classificar_documento` + `TIPO_DOC_REGRAS` em app.py, com `re.IGNORECASE`).

O Cartão de Ponto vem do **Secullum** e o cabeçalho do PDF é **"CARTÃO PONTO"** + "Secullum Ponto Web | Sonoda Informática" — **não** "Folha de Ponto". O regex antigo de 'Folha de Ponto' só tinha `Folha\s+de\s+Ponto` e `Espelho\s+de\s+Ponto`, então o arquivo caía em **"Outro"** e NÃO era processado pelo `/processar-fila {"tipo_documento":"Folha de Ponto"}`.

**Correção (v2.26):** adicionados ao tipo 'Folha de Ponto' os padrões `Cart[ãa]o\s+(?:de\s+)?Ponto`, `Secullum`, `Ponto\s+Web`. Cobertos por teste (`test_classificar_cartao_ponto_secullum`).

**Cuidado nos próximos meses:** se um documento novo cair em "Outro" no intake, a 1ª suspeita é o **regex de conteúdo** não bater com o cabeçalho real (cada sistema escreve diferente). Para corrigir um item já enfileirado ANTES do fix, basta editar o campo "Tipo de Documento" do registro na tabela "Processar Arquivos" (`tblXaLXvGJMyFOayc`, campo `fldvkOVlwCMywGTES`) para o tipo certo — o código novo só reclassifica e-mails futuros, não os já na fila. O nome do arquivo NÃO influencia a classificação (ex.: `olerite salário maio.pdf` sem "H" não atrapalha). Relaciona com [[v2_25_envio_combinado]] e [[faxina_base_funcionarios_jun2026]].
