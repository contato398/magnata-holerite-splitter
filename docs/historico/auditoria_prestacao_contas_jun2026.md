---
name: auditoria-prestacao-contas-jun2026
description: "Auditoria read-only de 12/07/2026 da prestação de contas mensal — achado central de competência Sky Tatuí contaminando 4 fluxos, mais pendências fiscais e de envio"
metadata: 
  node_type: memory
  type: project
  originSessionId: aa03776e-e1d0-4966-80f8-990a966bd5e6
---

Em 12/07/2026 foi feita uma auditoria completa e somente-leitura (nenhuma escrita) de tudo que já havia sido processado no Airtable para a prestação de contas mensal (competência: todos os clientes = Junho/2026, exceto Edifício Sky Tatuí = Maio/2026). Entregue como PDF em `C:\Users\Lenovo\Downloads\Auditoria Prestacao de Contas Magnata.pdf` (Artifact não abriu — ver [[artifact-nao-abre-usar-pdf]]).

**Achado central**: os envios manuais de meados de junho (pacotes de e-mail 17/06 e WhatsApp individual 15/06) respeitaram corretamente a exceção Sky Tatuí=Maio. Mas os reprocessamentos automáticos feitos DEPOIS ignoraram a exceção e gravaram tudo como Junho/2026 em 4 frentes: Holerites (lote 05/07 — 8/9 colaboradores do Sky Tatuí ganharam holerite indevido de Junho, 5 duplicados + 3 sem Maio nunca gerado), Assinaturas Digitais de Folha de Ponto (100% dos 104 registros abertos em 11/07 rotulados "Junho 2026", incluindo os 9 do Sky Tatuí), Benefícios via Extrato Bancário (docs de hoje gravados como Junho), FGTS Digital (só existe o de Junho, falta o de Maio).

**Outras pendências relevantes encontradas**:
- Villa Verde condominio: zero FGTS/Extrato Mensal/pacote de envio em qualquer competência.
- "Edifício Sky" (registro de envio) preso em Status="Preparando" desde 12/05, nunca enfileirado em nenhum canal.
- Holerites_Junho2026.pdf (arquivo-mestre) e as 7 Notas Fiscais de dpfiscal.contabilidade2 falharam em Erro silencioso, sem log nem pendência aberta.
- 65% dos registros de "Processar Arquivos" dos últimos 45 dias estão em Erro — sistêmico, não isolado.
- DCTFWeb: nenhum documento de Maio/Junho encontrado (mais recente = Abril). Certidão FGTS vencida desde 23/06.
- VILLAGIO VITTA e Porto de Areia Romanha: FGTS Digital de Junho não lançado.
- Cadastros possivelmente duplicados: "CDG CONSTRUTORA"/"CDG  CONSTRUTORA" (espaço duplo); "EDIFICIO SKY TATUI"/"EDIFICIO SKY".
- Condomínio Marina: Status=Inativo mas recebeu documento de Benefícios processado no mesmo dia da auditoria.

**Como aplicar**: antes de aceitar qualquer holerite/assinatura/FGTS/benefício do Sky Tatuí como "correto", confirmar a competência explicitamente — o bug de reprocessamento em lote ignorando a exceção pode se repetir em ciclos futuros se a lógica de competência por cliente não for centralizada no código (hoje parece estar espalhada/reimplementada em cada rota de processamento em lote). O relatório completo (PDF) tem o plano de correção proposto (Seção G, 9 itens) — aguardando autorização do usuário para execução, ainda não confirmado se foi executado.
