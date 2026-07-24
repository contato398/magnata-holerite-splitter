---
name: automacao-dp-email-assinatura-v2-36-a-v2-41
description: "Arquitetura do robô de captura de e-mails de DP (Admissão/Rescisão/EPI) + fluxo de Assinatura Nativa via WhatsApp com evidências jurídicas, custo zero"
metadata: 
  node_type: memory
  type: project
  originSessionId: 798af317-f0d2-4a99-9677-e8e8f77ce019
---

Em 2026-06-22 implementei e implantei (app.py v2.35 → v2.41, todos validados via `/health` no Render antes de declarar sucesso) dois sistemas novos para a Magnata:

**1. Captura automática de e-mails de DP — Google Apps Script + /email/webhook**
- Arquivo fonte: `C:\Users\Lenovo\Downloads\AppsScript_Magnata_EmailListener.gs` (vive no Apps Script do Gmail `contato@magnataservicos.com.br`, projeto "Magnata Email Listener")
- Gatilho de tempo a cada 5 min, busca e-mails de `dpessoal.contabilidade1@hotmail.com` com PDF e palavras-chave (admissão/rescisão/contrato/EPI/experiência/demissão)
- Envia para `/email/webhook` (já existia); se anexo for `.rar/.7z/.tar/.gz` (não-PDF), chama `/email/alerta-formato-invalido` que dispara e-mail automático cobrando reenvio em PDF/ZIP, listando colaboradores extraídos do nome do arquivo
- Labels de controle no Gmail: `Processado-Webhook`, `Erro-Webhook`, `Alerta-Formato-Enviado` — evitam reprocessamento
- `TIPO_DOC_REGRAS` em app.py ganhou 4 tipos novos (ordem importa — mais específico antes do genérico): Rescisão, EPI, Ficha de Registro de Empregado, Termo de Prorrogação de Contrato de Experiência. Handler de Rescisão (`_processar_rescisao_stub`) extrai dados e cria Pendência rica, nunca altera Status do funcionário sozinho

**2. Assinatura Nativa com evidências jurídicas — custo zero (sem API paga de terceiros)**
- Nova tabela Airtable "Assinaturas Digitais" (`tbl6xgW45637YJISv`, base `appaCpIVj7Q97VhFy`)
- Rotas no app.py: `POST /assinatura/gerar` (cria link + dispara WhatsApp via Evolution API já paga), `GET/POST /assinatura/<hash>` (página HTML pura, sem template engine), `POST /assinatura/processar-reenvios` (varre Status="Reenviar", zera tentativas, gera hash novo, redispara)
- Validação de identidade: só os 4 últimos dígitos do CPF (decisão deliberada do usuário — fricção mínima), com proteção contra força bruta (expira após 5 tentativas erradas, campo "Tentativas")
- Validação de telefone: bloqueia o disparo (nem cria registro) se Funcionário não tiver WhatsApp cadastrado
- Evidência jurídica: campo "Evidencias_Assinatura" consolida IP real (via X-Forwarded-For, atravessa proxy do Render) + timestamp BRT + User-Agent completo + CPF confirmado + texto do termo de aceite, tudo num campo de texto só — mais os campos individuais (IP Captura, User Agent, Data/Hora Assinatura, CPF Informado)
- Testado de ponta a ponta com funcionário real (Franklin Sebastiao Neves de Camargo) via curl direto em produção antes de declarar pronto; registro de teste apagado depois

**Pendência conhecida, fora do escopo:** 1.140 registros travados em "Processar Arquivos" (`tblXaLXvGJMyFOayc`) datados de 15/06/2026, Status="Processando" — backlog antigo de uma migração/faxina anterior, sem relação com os sistemas acima. Precisa de investigação dedicada.

**Como aplicar:** ao tocar em fluxo de e-mail de DP ou assinatura de documentos da Magnata, ler este arquivo primeiro — a arquitetura e os nomes de campo/tabela já existem, não recriar do zero. Ver também [[holerites_correcao_maio2026]] e [[v2_29_distribuicao_email]] para o histórico de versões anteriores do mesmo app.py.
