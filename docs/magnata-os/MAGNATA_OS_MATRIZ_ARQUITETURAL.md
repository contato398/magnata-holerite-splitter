# Magnata OS — Matriz Arquitetural

**Versão:** 1.0  
**Propósito:** Relacionar capacidades, módulos, camadas e estado atual vs. alvo  
**Data:** 2026-07-25

---

## Princípios da Matriz

1. **Camada ≠ Módulo:** Uma camada contém responsabilidades; um módulo executa domínio
2. **Capacidade ≠ Componente:** Capacidade é o "o quê"; componente é o "como"
3. **Estado atual ≠ Alvo:** Hoje funciona diferente; amanhã será como desenhado
4. **Hierarquias paralelas:** Frontend e Magnata OS são domínios independentes

---

## Matriz Principal

| Capacidade | Módulo(s) | Camada(s) | Componente Atual | Estado Atual | Componente Alvo | Estado-Alvo | Nível de Operação | Risco | ADR |
|---|---|---|---|---|---|---|---|---|---|
| **Recebimento e-mail** | Ingestão | Entrada | Gmail + Apps Script | Legado (3) | API + adapter | Implementar (7) | Leitura local | Alto | Não |
| **Rastreabilidade origem** | Ingestão | Auditoria | Hash SHA256 (parcial) | Parcial (4) | Hash + evento | Completar (5) | Análise assistida | Baixo | Não |
| **Identificação tipo** | Classificação | Inteligência | Manual em app.py | Inexistente (2) | ML/heurística + modelo | Novo (7) | Nenhuma autonomia | Alto | Sim |
| **Extração texto** | Classificação | Transformação | PDFPlumber (parcial) | Parcial (2) | OCR + NLP | Novo (6) | Leitura local | Médio | Não |
| **Associação entidade** | Classificação | Inteligência | Match manual | Parcial (4) | Lookup automático | Completar (6) | Execução controlada | Médio | Não |
| **Identificação colaborador** | Cadastro | Inteligência | Secullum sync | Legado (3) | PostgreSQL + dedup | Migrar (7) | Execução controlada | Crítico | Não |
| **Identificação cliente** | Cadastro | Inteligência | Airtable lookup | Legado (3) | PostgreSQL + CNPJ | Migrar (7) | Execução controlada | Crítico | Não |
| **Deduplicação** | Cadastro | Inteligência | Manual | Inexistente (2) | Automático + review | Novo (6) | Execução controlada | Crítico | Não |
| **Captura escala** | Ponto | Entrada | Secullum API | Legado (3) | Adapter + mock | Manter (4) | Leitura local | Alto | Não |
| **Cálculo horas** | Ponto | Transformação | Colunar em app.py | Legado (3) | Módulo novo + testes | Migrar (7) | Análise assistida | Crítico | Não |
| **Geração holerite** | Documentação | Transformação | Template hardcoded | Legado (3) | Motor de template | Migrar (7) | Nenhuma autonomia | Crítico | Não |
| **Geração FGTS** | Documentação | Transformação | Específico por cliente | Legado (3) | Template unificada | Migrar (7) | Nenhuma autonomia | Crítico | Não |
| **Seleção canal** | Distribuição | Negócio | Se/então em app.py | Legado (3) | Regras declarativas | Migrar (6) | Nenhuma autonomia | Médio | Não |
| **Envio e-mail** | Distribuição | Entrega | SMTP direto | Legado (3) | SMTP adapter | Manter (4) | Execução controlada | Médio | Não |
| **Envio WhatsApp** | Distribuição | Entrega | Evolution API | Legado (3) | Evolution adapter | Manter (4) | Execução controlada | Médio | Não |
| **Rastreamento entrega** | Distribuição | Auditoria | Campo Status único | Legado (3) | Evento + tentativa | Migrar (6) | Execução controlada | Médio | Não |
| **Geração link assinável** | Assinaturas | Negócio | Formulário simples | Legado (3) | Protocolo robusto | Migrar (7) | Nenhuma autonomia | Médio | Não |
| **Captura assinatura** | Assinaturas | Negócio | Caneta + envio | Legado (3) | Nativa com evidência | Migrar (7) | Nenhuma autonomia | Médio | Não |
| **Registro evento** | Auditoria | Auditoria | Disperso (sem padrão) | Parcial (2) | EventLog centralizado | Novo (8) | Execução supervisionada | Baixo | Não |
| **Correlação requisição** | Auditoria | Auditoria | Inexistente | Inexistente (1) | Correlation ID ponta a ponta | Novo (6) | Execução supervisionada | Baixo | Não |

---

## Legenda de Estados

| Nível | Significado |
|---|---|
| 1 | Inexistente |
| 2 | Identificada, não implementada |
| 3 | Legado operacional |
| 4 | Parcialmente estruturada |
| 5 | Documentada |
| 6 | Preparada para implementação |
| 7 | Implementada |
| 8 | Validada em controlado |
| 9 | Autorizada para produção |

---

## Relacionamentos entre Módulos

```
Ingestão
  ↓ (documento com hash)
Classificação
  ↓ (tipo + proprietário)
Cadastro ← (valida proprietário)
  ↓
RH + Ponto ← (identidade)
  ↓
Documentação ← (dados para holerite)
  ↓
Distribuição ← (documento pronto)
  ↓
Assinaturas ← (se precisa assinatura)
  ↓
Auditoria ← (tudo registra evento)
```

**Plataforma** fornece serviços para todos.

---

## Matriz de Operação por Fase

| Fase | Nível máximo de operação | Módulos | Justificativa |
|---|---|---|---|
| 0 | Nenhuma autonomia | Nenhum | Governança apenas |
| 1 | Análise assistida | Auditoria | Logging automático em ambiente isolado |
| 2 | Nenhuma autonomia | Legado | Proteção apenas, sem execução |
| 3 | Leitura local | Ingestão | Recebimento com validação |
| 4 | Nenhuma autonomia | Classificação | Quase tudo é review humano |
| 5 | Execução controlada | Cadastro | Sync automática em isolado, dedup com review |
| 6 | Leitura local | RH | Admin assistido, encerramento é review |
| 7 | Análise assistida | Ponto | Cálculo com validação antes de produção |
| 8 | Nenhuma autonomia | Documentação | Tudo é validado antes de saída |
| 9 | Execução controlada | Distribuição | Retry automático em isolado, falha é manual |
| 10 | Execução supervisionada | Assinaturas | Geração com supervisão, validação humana antes de link |
| 11 | Produção autorizada | Todos | Com operador supervisionando legado + novo em paralelo |

**Regra de ouro:** Nenhuma fase é autorizada para "Produção autorizada" antes da Fase 11. Fase 10 tem máximo "Execução supervisionada" com review obrigatório.

---

## Estado Atual vs. Alvo por Camada

### Camada: Entrada

| Hoje | Amanhã |
|---|---|
| Gmail + upload manual | API REST + upload programático |
| Sem contrato claro | Contrato definido |
| Sem validação padronizada | Validação por tipo |
| Sem rastreamento completo | Hash + evento + origem |

### Camada: Inteligência

| Hoje | Amanhã |
|---|---|
| Regras em if/then | Decisor (ML ou heurística) |
| Sem confiança | Confiança calculada |
| Acoplado ao tipo documental | Desacoplado, modular |
| Sem persistência de modelo | Versão de modelo registrada |

### Camada: Transformação

| Hoje | Amanhã |
|---|---|
| Cálculo em app.py (monólito) | Módulos especializados |
| Sem rollback explícito | Rollback documentado |
| Sem testes por caso | Testes de cobertura > 95% |
| Sem versionamento | Cada transformação é versionada |

### Camada: Negócio

| Hoje | Amanhã |
|---|---|
| Regras hardcoded | Regras declarativas |
| Sem audit trail | Evento de cada decisão |
| Sem intervenção clara | Escala automática com limite |
| Sem SLA | SLA por operação |

### Camada: Entrega

| Hoje | Amanhã |
|---|---|
| 4 rotas duplicadas | 1 módulo parametrizado |
| Sem retry policy | Retry automático + manual fallback |
| Sem rastreamento fino | Status + tentativa + evidência |
| Sem integração explícita | Adapter por canal |

### Camada: Auditoria

| Hoje | Amanhã |
|---|---|
| Disperso, sem padrão | EventLog centralizado |
| Sem correlação | Correlation ID ponta a ponta |
| Sem alertas | Alertas de anomalia |
| Sem conformidade | LGPD + segurança por padrão |

---

## Decisões Pendentes por Camada

### Entrada
- API REST ou apenas webhook? (recomendado: REST)
- Qual é o SLA de recebimento? (recomendado: < 5s)

### Inteligência
- ML ou heurísticas? Qual framework? (pendente de POC)
- Qual confiança autoriza envio sem review? (recomendado: > 95%)

### Transformação
- PostgreSQL ou Airtable? (recomendado: PostgreSQL para novo)
- Versionamento por conteúdo ou por hash? (recomendado: por hash)

### Negócio
- Limite de retry automático? (recomendado: 3 tentativas)
- Quem recebe escala manual? (recomendado: fila de pendências)

### Entrega
- Qual é a SLA de entrega? (recomendado: < 2h)
- Fallback se todos os canais falharem? (recomendado: notificar operador)

### Auditoria
- Replicação geográfica de EventLog? (recomendado: sim)
- Retenção de evento por quanto tempo? (recomendado: 7 anos)

---

## Rastreabilidade Legado → Canônico

| Conceito Legado | Tabela/Código | Conceito Canônico | Status |
|---|---|---|---|
| Item de Ingestão | Processar Arquivos | Documento | Pendente (ADR) |
| Tipo de Documento | Tipo (campo) | Tipo Documental | Implementado em contrato |
| Funcionário | Tabela Funcionários | Colaborador | Mapeado |
| Cliente | Tabela Clientes | Cliente | Mapeado |
| Holerite | Tabela Holerites | Documento (tipo holerite) | Mapeado |
| Envio | Tabela Envios de Documentos | Envio + Tentativa | Parcial (sem tentativa) |
| Assinatura | Tabela Assinaturas | Solicitação de Assinatura | Mapeado |

---

## Hierarquias Paralelas

### Frontend
- UI do operador
- Painel de gestão
- Integração com Airtable (legado)
- Não depende de nenhum módulo novo
- Será atualizado em paralelo na Fase 11

### Magnata OS (Servidor)
- Lógica de domínio
- Módulos funcionais (1-10)
- Adapters de serviço
- Será construído nas Fases 1-11

**Integração:** API REST entre Frontend e Magnata OS (contrato definido)

---

## Próximos Passos

1. **Fase 1 — Observabilidade:** Começar logging estruturado
2. **ADRs:** Decidir sobre os itens pendentes antes de cada fase
3. **Testes:** Suíte de regressão para cada módulo legado
4. **Rollback:** Documentar reversão de cada fase
5. **Operador:** Treinar em interface nova (paralelo à implementação)
