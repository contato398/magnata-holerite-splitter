---
name: v2-66-aprovacao-por-excecao-5c
description: "v2.66 mudou 5C para \"aprovação por exceção\" (contrato cria cadastro imediato como Validação Pendente); Diego não tinha trava de inativação"
metadata: 
  node_type: memory
  type: project
  originSessionId: 798af317-f0d2-4a99-9677-e8e8f77ce019
---

Manutenção de 01/07/2026 (app.py v2.66).

**Mudança 5C — aprovação por exceção:** contratos/admissões agora criam o cadastro em Funcionários IMEDIATAMENTE com Status="Validação Pendente" em vez de reter o arquivo. Alterações: `decidir_acao_documento` — avisos de qualidade e confiança baixa NÃO retêm mais (viram `executar_com_status_intermediario`/criam); os dois handlers de admissão gravam `status_destino='Validação Pendente'`; `/processar-fila` — removida a trava record_id+limit=1 para Contrato de Experiência/Trabalho (agora processa em lote, cap 25/request). Mantido: funcionário existente (mesmo CPF) nunca duplicado; docs sem CPF válido/nome ainda vão para revisão. Objetivo: tabela sempre atualizada, inativação/ajuste manual pelo humano. Ver [[fase5c_pre_cadastro_funcionarios]].

**Diego Luis Nogueira de Campos (CPF 386.118.838-45):** o usuário achava que "o sistema forçava inativação automática" dele. INVESTIGADO: NÃO existe nenhuma rotina que inative funcionário automaticamente (nem o handler de Rescisão — só sugere em Pendência). Diego não tem rescisão; docs dele são Contrato+Termo Aditivo+Férias. Estava só marcado Inativo (faxina 15/06) apesar de trabalhar (ponto até 25/06). Reativado manualmente. LIÇÃO: sempre verificar a causa real antes de "remover uma trava" — a trava alegada pode não existir.

**Dry-run do lote retroativo (~70 contratos, NÃO descarregado):** só 3 "criariam" e os 3 eram DUPLICATAS (Emerson Coelho ×2 com CPF em branco no cadastro; Inara Rafaaeli com CPF sujo `...-54\n`) — dedup por CPF falhava. Corrigido preenchendo/limpando os 2 CPFs (Emerson fica Inativo, Inara Ativa/recente). 14 já existiam; 53 (todos os 41 Contrato de Trabalho + 12 Exp.) caem em REVISÃO = PDFs ilegíveis/multi-pessoa que o extrator não lê. Backlog retroativo não é fonte de cadastros novos legítimos. Investigar os 41 Contrato de Trabalho ilegíveis à parte (pendente). LIÇÃO: cadastros existentes com CPF ausente/sujo furam o dedup e geram duplicatas — dry-run pegou isso.
