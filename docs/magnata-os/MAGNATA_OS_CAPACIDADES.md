# Magnata OS — Catálogo de Capacidades

**Versão:** 1.0  
**Status:** Mapa estrutural ativo  
**Data:** 2026-07-25  
**Escopo:** Definição canônica das capacidades do Magnata OS

---

## 1. Conceito de Capacidade

Uma **capacidade** é algo que o Magnata OS deve conseguir realizar de forma:
- **Repetível:** funciona consistentemente em múltiplas execuções
- **Controlada:** estado e efeitos são auditáveis
- **Auditável:** deixa evidência de execução
- **Segura:** sem risco à operação existente

**Distinguir de:**
- **Módulo:** domínio funcional (Ingestão, Classificação, etc.)
- **Camada:** responsabilidade arquitetural (Entrada, Inteligência, etc.)
- **Sistema externo:** ferramenta fora da fronteira (Airtable, Secullum, etc.)
- **Componente técnico:** implementação (classe, função, tabela)
- **Interface:** canal de comunicação (API, webhook, etc.)
- **Agente:** operador autônomo (skill, subagente)
- **Automação isolada:** ação sem contexto operacional

---

## 2. Escala de Maturidade

| Nível | Nome | Significado | Risco |
|---|---|---|---|
| 1 | Inexistente | Não existe nem como ideia | N/A |
| 2 | Identificada | Reconhecida como necessária | Alto |
| 3 | Legado operacional | Funciona em produção mas sem documentação | Alto |
| 4 | Parcialmente estruturada | Tem documentação parcial e/ou código desorganizado | Médio |
| 5 | Documentada | Contrato oficial definido | Médio |
| 6 | Preparada para implementação | Pronta para ser desenvolvida segundo contrato | Baixo |
| 7 | Implementada | Código novo em branch de desenvolvimento | Baixo |
| 8 | Validada em controlado | Testada em ambiente não-produção | Baixo |
| 9 | Autorizada para produção | Aprovada formalmente para uso real | Crítico |

**Regras:**
- Código existente ≠ nível 9 automaticamente
- Documentação ≠ implementação
- Integração real ≠ autonomia
- Nível 9 exige aprovação explícita

---

## 3. Categorias e Capacidades Mapeadas

### 3.1 Entrada e Ingestão
| Capacidade | Descrição | Módulos | Camadas | Maturidade | Estado Atual |
|---|---|---|---|---|---|
| Recebimento de e-mail | Captura segura de mensagens de entrada | Ingestão | Entrada | 3 | Legado operacional via Gmail Apps Script |
| Recebimento de upload | Aceitar arquivos via interface web | Ingestão | Entrada | 2 | Identificada, não implementada |
| Rastreabilidade de origem | Registrar fonte e timestamp de entrada | Ingestão | Auditoria | 4 | Parcialmente estruturada (hash do arquivo) |
| Validação de entrada | Verificar integridade do conteúdo | Ingestão | Inteligência | 5 | Documentada em contrato |
| Armazenamento temporário | Manter arquivo até processamento | Ingestão | Negócio | 3 | Legado via Airtable (tabela Arquivos) |

### 3.2 Classificação
| Capacidade | Descrição | Módulos | Camadas | Maturidade | Estado Atual |
|---|---|---|---|---|---|
| Identificação de tipo documental | Determinar categoria de documento | Classificação | Inteligência | 2 | Identificada, não automatizada |
| Extração de texto | OCR/parsing de conteúdo | Classificação | Transformação | 2 | Identificada, parcial via PDF parsing |
| Associação a entidade | Vincular documento a colaborador/cliente | Classificação | Inteligência | 4 | Parcialmente estruturada |
| Cálculo de confiança | Medir probabilidade de classificação correta | Classificação | Inteligência | 5 | Documentada, não implementada |
| Revisão humana para baixa confiança | Encaminhar para operador | Classificação | Negócio | 3 | Legado via tabela Pendências/Revisar |

### 3.3 Cadastro e Identidade
| Capacidade | Descrição | Módulos | Camadas | Maturidade | Estado Atual |
|---|---|---|---|---|---|
| Identificação de colaborador | Localizar pessoa por CPF, nome ou documento | Cadastro | Inteligência | 3 | Legado via Secullum sync |
| Identificação de cliente | Localizar empresa por CNPJ ou contato | Cadastro | Inteligência | 3 | Legado via Airtable (tabela Clientes) |
| Deduplicação | Detectar duplicatas de mesma entidade | Cadastro | Inteligência | 2 | Identificada, sem automação |
| Sincronização bidirecional | Manter dados consistentes com fonte | Cadastro | Transformação | 4 | Parcialmente estruturada (Secullum) |
| Reconciliação de aliases | Unificar identidades divergentes | Cadastro | Inteligência | 2 | Identificada, manual |

### 3.4 RH e Ponto
| Capacidade | Descrição | Módulos | Camadas | Maturidade | Estado Atual |
|---|---|---|---|---|---|
| Captura de escala | Receber jornada do relógio de ponto | Ponto | Entrada | 3 | Legado via Secullum API |
| Cálculo de horas | Processar batidas para folha | Ponto | Transformação | 3 | Legado (colunar em `app.py`) |
| Detecção de anomalias | Alertar desvios de escala | Ponto | Inteligência | 2 | Identificada, não automatizada |
| Admissão de colaborador | Registrar novo contrato de trabalho | RH | Negócio | 2 | Identificada, ainda legado |
| Encerramento de vínculo | Finalizar relacionamento trabalhista | RH | Negócio | 2 | Identificada, manual |

### 3.5 Documentação
| Capacidade | Descrição | Módulos | Camadas | Maturidade | Estado Atual |
|---|---|---|---|---|---|
| Geração de holerite | Produzir recibo de pagamento | Documentos | Transformação | 3 | Legado em `app.py` |
| Geração de FGTS | Produzir guia de fundo de garantia | Documentos | Transformação | 3 | Legado, específico por cliente |
| Geração de comprovante | Emitir documento de comprovação | Documentos | Transformação | 2 | Identificada, parcial |
| Versionamento de documento | Manter histórico de alterações | Documentos | Auditoria | 4 | Parcialmente estruturada em contrato |
| Associação a período | Vincular documento a competência/data | Documentos | Transformação | 3 | Legado via Airtable (Contabilidade Mensal) |

### 3.6 Distribuição
| Capacidade | Descrição | Módulos | Camadas | Maturidade | Estado Atual |
|---|---|---|---|---|---|
| Seleção de canal | Decidir entre e-mail, WhatsApp, combinado | Distribuição | Negócio | 3 | Legado (se/então em `app.py`) |
| Preparação de fila | Montar payload para envio | Distribuição | Transformação | 3 | Legado via tabela Envios de Documentos |
| Rastreamento de entrega | Registrar status de envio | Distribuição | Auditoria | 3 | Legado (status único por envio) |
| Reenvio controlado | Retry com limite de tentativas | Distribuição | Entrega | 3 | Legado com flag Tentativa |
| Comprovante de recebimento | Confirmar leitura ou entrega | Distribuição | Auditoria | 2 | Identificada, parcial em WhatsApp |

### 3.7 Assinaturas
| Capacidade | Descrição | Módulos | Camadas | Maturidade | Estado Atual |
|---|---|---|---|---|---|
| Geração de link | Criar URL assinável exclusiva | Assinaturas | Negócio | 3 | Legado via tabela Assinaturas |
| Assinatura nativa | Capturar assinatura sem certificado | Assinaturas | Negócio | 3 | Legado, evidência de IP/CPF |
| Assinatura certificada | Integração com serviço de certificado | Assinaturas | Entrega | 2 | Identificada, não implementada |
| Rastreamento de assinatura | Saber quem assinou e quando | Assinaturas | Auditoria | 3 | Legado via Status (Assinado/Expirado) |
| Expiração de link | Invalidar link após prazo | Assinaturas | Segurança | 2 | Identificada, sem automação |

### 3.8 Auditoria e Observabilidade
| Capacidade | Descrição | Módulos | Camadas | Maturidade | Estado Atual |
|---|---|---|---|---|---|
| Registro de eventos | Capturar o que, quando, quem fez | Auditoria | Auditoria | 4 | Parcialmente estruturada em contrato |
| Correlação de requisição | Rastrear transação ponta a ponta | Auditoria | Auditoria | 2 | Identificada, correlation_id em código novo |
| Logging estruturado | Formato padrão de logs | Auditoria | Auditoria | 2 | Identificada, não centralizado |
| Alertas de anomalia | Notificar desvios de comportamento | Auditoria | Auditoria | 2 | Identificada, sem automação |
| Relatório de operação | Consolidar execuções do período | Auditoria | Entrega | 2 | Identificada, manual |

### 3.9 Integração e Plataforma
| Capacidade | Descrição | Módulos | Camadas | Maturidade | Estado Atual |
|---|---|---|---|---|---|
| Adapter de persistência | Abstrair banco/Airtable | Plataforma | Plataforma | 6 | Preparada para implementação (PostgreSQL) |
| Adapter de armazenamento | Abstrair S3/R2 | Plataforma | Plataforma | 6 | Preparada para implementação |
| Adapter de integração externa | Interfacear APIs reais | Plataforma | Plataforma | 4 | Parcialmente estruturada (Secullum, Evolution) |
| Governança de acesso | Controle de permissão por função | Plataforma | Segurança | 2 | Identificada, sem RBAC |
| Painel operacional | Interface para operador humano | Plataforma | Entrega | 2 | Identificada, sem implementação |

### 3.10 Responsabilidades Transversais (Segurança, Observabilidade, Governança)

**Nota:** Segurança, observabilidade, infraestrutura e governança são **requisitos não funcionais** aplicados a todos os 10 módulos, não módulos por si mesmos. São responsabilidades compartilhadas da Plataforma e critérios obrigatórios de cada módulo.

| Capacidade | Descrição | Aplica-se a | Camadas | Maturidade | Estado Atual |
|---|---|---|---|---|---|
| Criptografia de dado sensível | Proteger CPF, conta bancária | Todos (obrigatório) | Transformação | 2 | Identificada, sem implementação |
| Isolamento de ambiente | Produção ≠ staging ≠ dev | Todos (Plataforma) | Plataforma | 3 | Legado via Render (sem isolamento total) |
| Conformidade LGPD | Direito ao esquecimento, portabilidade | Ingestão, Cadastro, Auditoria | Auditoria | 2 | Identificada, sem automação |
| Backup e recovery | Recuperação de estado anterior | Todos (Plataforma) | Plataforma | 2 | Identificada, sem plano explícito |
| Idempotência de operação | Reexecução segura | Ingestão, Transformação, Negócio | Transformação | 5 | Documentada em contrato |

---

## 4. Matriz Consolidada de Capacidades

| Capacidade | Categoria | Módulos | Maturidade | Risco | Operação | Decisão |
|---|---|---|---|---|---|---|
| Recebimento de e-mail | Entrada | Ingestão | 3 | Alto | Nenhuma autonomia | Legado, preservar |
| Rastreabilidade de origem | Entrada | Ingestão | 4 | Médio | Leitura local | Contrato definido |
| Identificação de tipo | Classificação | Classificação | 2 | Alto | Nenhuma autonomia | Necessário ADR |
| Deduplicação | Cadastro | Cadastro | 2 | Alto | Nenhuma autonomia | Necessário design |
| Captura de escala | RH/Ponto | Ponto | 3 | Alto | Análise assistida | Legado com risco |
| Geração de holerite | Documentação | Documentos | 3 | Alto | Execução controlada | Legado crítico |
| Seleção de canal | Distribuição | Distribuição | 3 | Médio | Nenhuma autonomia | Legado simples |
| Assinatura nativa | Assinaturas | Assinaturas | 3 | Médio | Nenhuma autonomia | Legado, testar |
| Registro de eventos | Auditoria | Auditoria | 4 | Baixo | Análise assistida | Contrato, implementar |
| Adapter de persistência | Plataforma | Plataforma | 6 | Baixo | Execução supervisionada | Pronto para dev |

---

## 5. Decisões Pendentes

1. **Autonomia de classificação:** Qual nível de confiança autoriza envio sem review?
2. **Sincronização de cadastro:** Bidirecional sempre ou somente leitura?
3. **Reenvio automático:** Quantas tentativas antes de escalar para operador?
4. **Expiração de link de assinatura:** Qual é o prazo apropriado?
5. **Isolamento de ambiente:** PostgreSQL nova vs. continuação em Airtable?

---

## 6. Próximas Fases

- **Fase 1:** Observabilidade (capacidades de auditoria)
- **Fase 2:** Encapsulamento do legado (com testes de regressão)
- **Fase 3:** Ingestão controlada (novo design)
- **Fase 4:** Classificação autônoma (com review)
- ...continuar até desativação do legado

**Nota:** Nenhuma capacidade é autorizada para produção (nível "Produção autorizada") antes de Phase 10+. Todas as fases usam níveis qualitativos de operação: Nenhuma autonomia → Leitura local → Análise assistida → Execução controlada → Execução supervisionada (máx. em Fase 10) → Produção autorizada (Fase 11+ apenas).
