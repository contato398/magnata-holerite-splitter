# Magnata OS — Roadmap de Implantação

**Versão:** 1.0
**Estratégia:** Migração incremental via strangler pattern
**Data:** 2026-07-25

---

## Princípios

1. **Nunca interromper operação:** Legado continua rodando
2. **Validar antes de expandir:** Cada fase é validada antes da próxima
3. **Rollback sempre possível:** Reverter fase é operação documentada
4. **Operação assistida, local, reversível e sem autonomia de produção:** Nenhuma fase autoriza "Produção autorizada" antes de Phase 11. Todas usam níveis qualitativos de operação
5. **Preservação ativa:** Operações legadas são monitoradas continuamente

---

## Fase 0 — Fundação e Governança (CONCLUÍDA)

**Objetivo:** Estabelecer constituição, contratos, ferramental técnico

**Entregáveis:**
- ✓ CLAUDE.md e hierarquia (Etapa 2)
- ✓ Skills e subagentes (Etapa 3)
- ✓ Capacidades, módulos, roadmap, matriz (Etapa 4)
- ✓ Contratos oficiais definidos
- ✓ Máquinas de estado documentadas
- ✓ Processos de decisão formal (ADR)

**Pré-requisitos:** Nenhum

**Critério de saída:** Documentação completa, sem decisões silenciosas

**Impacto no legado:** Zero

**Nível de autonomia:** N/A (governança)

---

## Fase 1 — Observabilidade e Auditoria

**Objetivo:** Capturar o que acontece para investigação e conformidade

**Escopo:**
- Inventário de eventos por módulo
- Logs estruturados (não fmt. de texto)
- Correlação de requisição (ponta a ponta)
- Alertas de anomalia (padrão x desvio)
- Armazenamento de auditoria (append-only)

**Pré-requisitos:** Fase 0

**Entregáveis:**
- EventLog schema em PostgreSQL
- Adapter de log estruturado
- Correlação ID em toda requisição
- Alertas iniciais (falha de envio, etc.)
- Relatório consolidado

**Critério de saída:** Evento de 100% das operações críticas é registrado

**Risco:** Alto (descobrir o que já está quebrado)

**Rollback:** Remover logs, voltar a observabilidade legada (nenhuma)

**Impacto no legado:** Passivo (só observa)

**Nível de operação:** Análise assistida (logging é automático, mas executado em ambiente isolado com supervisão)

---

## Fase 2 — Encapsulamento do Legado

**Objetivo:** Reduzir acoplamento de app.py sem reescrever

**Escopo:**
- Contratos de entrada/saída explícitos
- Testes de regressão para cada operação
- Interfaces de proteção (evitar mudanças internas)
- Rollback documentado (como voltar)
- Redução de comunicação direta (tudo via contrato)

**Pré-requisitos:** Fase 1

**Entregáveis:**
- Suíte de testes de regressão
- Documentação de rollback por operação
- Interface de app.py vs. novo
- Plano de desativação gradual

**Critério de saída:** Qualquer mudança em app.py é testada antes

**Risco:** Médio (testes podem ser incompletos)

**Rollback:** Remover testes, aceitar risco

**Impacto no legado:** Protetor (evita regressões)

**Nível de operação:** Nenhuma autonomia (proteção apenas, sem execução)

---

## Fase 3 — Ingestão Controlada

**Objetivo:** Capturar dados de forma segura, rastreável e idempotente

**Escopo:**
- API REST de recebimento (e-mail, upload)
- Validação de integridade (hash SHA256)
- Armazenamento imutável de original
- Idempotência por hash (não duplica)
- Rastreamento de origem
- Passthrough para Classificação

**Pré-requisitos:** Fases 0, 1, 2

**Entregáveis:**
- Módulo Ingestão (src/ingestao/)
- Testes de idempotência
- Contrato com Classificação
- Rollback para Gmail/upload legado

**Critério de saída:** 99% de acurácia no recebimento

**Risco:** Médio (mudança de fluxo de entrada)

**Rollback:** Desativar API, voltar a Gmail

**Impacto no legado:** Paraleliza inicialmente

**Nível de operação:** Leitura local (com validação assistida)

---

## Fase 4 — Classificação Autônoma

**Objetivo:** Determinar tipo e proprietário de documento

**Escopo:**
- OCR/parsing de conteúdo
- Identificação de tipo documental
- Associação a colaborador/cliente
- Cálculo de confiança
- Escala para review se confiança baixa
- Tratamento de exceção

**Pré-requisitos:** Fases 0-3

**Entregáveis:**
- Módulo Classificação (src/classificacao/)
- Modelo de ML ou heurísticas
- Testes de precisão por tipo
- Review human loop
- Contrato com Documentação

**Critério de saída:** 95% de precisão no tipo

**Risco:** Alto (decisão de negócio)

**Rollback:** Enviar tudo para review manual

**Impacto no legado:** Sobrescreve classificação legada

**Nível de operação:** Nenhuma autonomia (quase tudo é review humano)

---

## Fase 5 — Cadastro e Identidade

**Objetivo:** Fonte única de verdade sobre quem é quem

**Escopo:**
- Sincronização bidirecional (Secullum ↔ Magnata)
- Deduplicação de entidades
- Reconciliação de aliases
- Validação de endereço/documento
- Histórico de mudanças
- Referência canônica

**Pré-requisitos:** Fases 0-4

**Entregáveis:**
- Módulo Cadastro (src/cadastro/)
- Schema de Colaborador, Cliente, Posto
- Sincronizador com Secullum
- Dedup com review
- Testes de integridade

**Critério de saída:** 100% das identidades validadas

**Risco:** Crítico (dados incorretos afetam tudo)

**Rollback:** Parar sincronização, voltar a Airtable

**Impacto no legado:** Substitui Airtable como fonte

**Nível de operação:** Execução controlada (sync automática em ambiente isolado, dedup com review)

---

## Fase 6 — RH e Vínculo Trabalhista

**Objetivo:** Gerenciar ciclo de vida da relação trabalhista

**Escopo:**
- Admissão (contrato, salário, cargo)
- Manutenção de vínculo ativo
- Encerramento (rescisão)
- Integração com folha
- Arquivo de documentos
- Histórico de alterações

**Pré-requisitos:** Fases 0-5

**Entregáveis:**
- Módulo RH (src/rh/)
- Workflow de admissão/encerramento
- Schema de Vínculo Trabalhista
- Testes de ciclo completo

**Critério de saída:** 100% dos vínculos ativos têm contrato

**Risco:** Alto (afeta folha de pagamento)

**Rollback:** Parar workflow novo, voltar a manual

**Impacto no legado:** Substitui processo manual

**Nível de operação:** Leitura local (admin de novo vínculo é assistido, encerramento é review)

---

## Fase 7 — Ponto e RH Integrado

**Objetivo:** Sincronizar jornada com folha de pagamento

**Escopo:**
- Recebimento de batidas (Secullum)
- Cálculo de horas por período
- Detecção de anomalias
- Alertas para supervisor
- Geração de colunar
- Tratamento defensivo para falhas

**Pré-requisitos:** Fases 0-6

**Entregáveis:**
- Módulo Ponto (extração de src/secullum_ponto.py)
- Testes de cálculo por cliente
- Alertas configuráveis
- Rollback de colunar

**Critério de saída:** Cálculo equivalente ao legado para 100% dos casos

**Risco:** Crítico (folha de pagamento)

**Rollback:** Parar novo cálculo, voltar a legado

**Impacto no legado:** Sobrescreve cálculo

**Nível de operação:** Análise assistida (cálculo com validação de colunar antes de produção)

---

## Fase 8 — Documentação (Folha, FGTS, Guias)

**Objetivo:** Gerar documentos oficiais de forma auditável

**Escopo:**
- Motor de template (não hardcoded)
- Geração de holerite
- Geração de FGTS
- Geração de comprovantes
- Versionamento por período
- Armazenamento em S3
- Passthrough para Distribuição

**Pré-requisitos:** Fases 0-7

**Entregáveis:**
- Módulo Documentação (extração de src/report_generator.py)
- Templates versionadas
- Testes de geração por cliente
- Schema de versão

**Critério de saída:** PDF gerado é idêntico ao legado para amostra

**Risco:** Crítico (documento oficial)

**Rollback:** Parar geração nova, voltar a legado

**Impacto no legado:** Sobrescreve geração

**Nível de operação:** Nenhuma autonomia (tudo é validado antes de saída)

---

## Fase 9 — Distribuição Unificada

**Objetivo:** Entregar documentos por canal apropriado

**Escopo:**
- Unificação das 4 rotas de envio
- Decisão de canal (regra, não hardcode)
- Preparação de payload
- Envio via Evolution API / SMTP
- Retry automático
- Rastreamento de status

**Pré-requisitos:** Fases 0-8

**Entregáveis:**
- Módulo Distribuição (refatoração de 4 rotas)
- Retry policy documentada
- Testes de cada canal
- Escala manual para falha crítica

**Critério de saída:** 99% de entrega

**Risco:** Médio (falha de envio pode impactar operador)

**Rollback:** Parar novo, voltar a 4 rotas

**Impacto no legado:** Substitui rotas

**Nível de operação:** Execução controlada (retry automático em ambiente isolado, falha crítica escalada para manual)

---

## Fase 10 — Assinaturas Nativas

**Objetivo:** Capturar assinatura com evidências legais

**Escopo:**
- Geração de link único
- Captura de assinatura digital
- Registro de evidência (IP, timestamp, CPF)
- Expiração de link
- Arquivo de evidência
- Integração com Distribuição

**Pré-requisitos:** Fases 0-9

**Entregáveis:**
- Módulo Assinaturas
- Protocolo de evidência
- Testes legais
- Integração com Distribuição

**Critério de saída:** Evidência é aceitável legalmente

**Risco:** Alto (legal)

**Rollback:** Parar novo, voltar a assinatura legada

**Impacto no legado:** Sobrescreve assinatura

**Nível de operação:** Execução supervisionada (geração automática com supervisão, validação humana antes de link)

---

## Fase 11 — Desativação Gradual do Legado

**Objetivo:** Remover app.py quando substituição for completa e validada

**Pré-requisitos:** Fases 0-10 + evidência de equivalência

**Condições para desativar:**
- Cada operação legada tem equivalente novo
- Testes de regressão passam
- Auditoria mostra paridade de resultados
- Operador autoriza
- Rollback foi testado e funciona

**Processo:**
1. Congelar app.py (sem mudanças)
2. Executar em paralelo (legado + novo)
3. Comparar resultados (diff diário)
4. Identificar diferenças (e corrigi-las)
5. Migrar operador para novo interface
6. Monitorar por período de estabilidade
7. Remover app.py (irreversível)

**Risco:** Crítico (mais importante do roadmap)

**Rollback:** Reativar app.py (preparado para isso)

**Impacto:** Fim da duplicação de lógica

**Nível de operação:** Produção autorizada (com operador presente supervisionando legado + novo em paralelo até validação completa)

---

## Timeline Estimada

| Fase | Duração | Início estimado |
|---|---|---|
| 0 | Completa | 2026-07-22 |
| 1 | 3-4 semanas | 2026-07-29 |
| 2 | 4-6 semanas | 2026-08-26 |
| 3 | 4-6 semanas | 2026-10-07 |
| 4 | 6-8 semanas | 2026-11-18 |
| 5 | 6-8 semanas | 2027-01-13 |
| 6 | 4-6 semanas | 2027-03-02 |
| 7 | 4-6 semanas | 2027-04-13 |
| 8 | 4-6 semanas | 2027-05-25 |
| 9 | 3-4 semanas | 2027-07-06 |
| 10 | 3-4 semanas | 2027-08-03 |
| 11 | 4-8 semanas | 2027-08-31 |

**Total estimado:** 12-18 meses da Fase 1 ao fim da Fase 11

---

## Critérios de Parada

A fase é **interrompida** se:
- Operação legada quebra durante paralelo
- Auditoria mostra diferença > 1% entre legado e novo
- Operador relata impacto funcional
- Teste de regressão falha
- Rollback não funciona como documentado

Fase é **retomada** quando:
- Causa raiz é identificada
- Teste específico é adicionado
- Correo é implementada
- Rollback é revalidado

---

## Decisões Pendentes por Fase

- **Fase 4:** Qual nível de confiança (%) autoriza envio sem review?
- **Fase 5:** Bidirecional sempre ou pull-only? Frequência de sync?
- **Fase 7:** Limite de tentativas de retry? Prazo de alerta?
- **Fase 9:** Quais são os "canais secundários"? Email bloqueado, usar WhatsApp?
- **Fase 10:** Prazo de expiração de link de assinatura?
- **Fase 11:** Quanto tempo em paralelo antes de remover legado? (recomendado: 30 dias min.)

Todas as fases exigem ADR antes de começar (não é silencioso).
