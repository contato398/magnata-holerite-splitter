# Magnata OS — Dez Módulos Funcionais

**Versão:** 1.0  
**Status:** Definição canônica de domínios  
**Data:** 2026-07-25  

---

## Preâmbulo

Os dez módulos abaixo definem domínios funcionais do Magnata OS. Cada módulo:
- Tem responsabilidade clara e exclusiva
- Opera em uma ou mais camadas arquiteturais
- Comunica com outros via contrato
- Tem critérios de entrada e saída
- Tem limites de autonomia bem definidos

**Não confundir:** módulo ≠ diretório ≠ camada.

---

## 0. Responsabilidades Transversais

Segurança, observabilidade, infraestrutura e governança são **requisitos não funcionais** aplicados a todos os 10 módulos abaixo, não módulos por si mesmos.

**Responsabilidades:**
- Criptografia de dados sensível (CPF, conta bancária) — responsabilidade de todos
- Isolamento de ambientes (prod, staging, dev) — responsabilidade de Plataforma
- Conformidade LGPD (direito ao esquecimento, portabilidade) — responsabilidade de Cadastro + Auditoria
- Backup e recovery (recuperação de estado) — responsabilidade de Plataforma
- Idempotência de operação (reexecução segura) — responsabilidade de Ingestão, Transformação, Negócio

Cada módulo abaixo **integra** essas responsabilidades em seu design. Não há "módulo de Segurança" — segurança é critério obrigatório de todos.

---

## 1. Ingestão

**Propósito:** Capturar dados brutos de múltiplas origens de forma segura e rastreável.

**Responsabilidades:**
- Receber dados por e-mail, upload, API
- Validar integridade
- Armazenar arquivo original (imutável)
- Gerar hash de idempotência
- Registrar origem e timestamp
- Fazer passthrough para Classificação

**Não faz:**
- Classificar tipo de documento
- Decidir destinatário
- Transformar conteúdo

**Entidades envolvidas:** Item de Ingestão (ou Documento, conforme ADR)

**Camadas:** Entrada, Auditoria

**Estado atual:** Legado operacional (Gmail, upload parcial)  
**Arquitetura-alvo:** API REST + adapter de armazenamento

**Critérios de saída:** Arquivo armazenado, hash registrado, rastreabilidade confirmada

---

## 2. Classificação

**Propósito:** Determinar tipo, categoria e proprietário de cada documento.

**Responsabilidades:**
- Extrair texto via OCR/parsing
- Identificar tipo de documento
- Associar a colaborador/cliente/projeto
- Calcular confiança de classificação
- Escalar para review humano se confiança baixa
- Passar para Documentação

**Não faz:**
- Modificar arquivo original
- Decidir canal de distribuição
- Gerar documentos novos

**Entidades envolvidas:** Documento, Tipo Documental, Colaborador, Cliente

**Camadas:** Inteligência, Transformação

**Estado atual:** Não implementado (legado via app.py manual)  
**Arquitetura-alvo:** Módulo novo, com ML/heurísticas

**Critérios de saída:** Tipo definido, proprietário associado, confiança registrada

---

## 3. Cadastro

**Propósito:** Manter identidade oficial de pessoas, empresas e unidades.

**Responsabilidades:**
- Sincronizar dados de Secullum, CNPJ, contratos
- Deduplicar entidades
- Reconciliar aliases (mesma pessoa, nomes diferentes)
- Validar endereços e documentos
- Manter histórico de mudanças
- Prover referência canônica para outros módulos

**Não faz:**
- Criar dados de zero (recebe de fontes)
- Deletar registros (apenas marcar inativo)
- Fazer contas ou cálculos

**Entidades envolvidas:** Colaborador, Cliente, Posto de Trabalho, Vínculo

**Camadas:** Inteligência, Transformação

**Estado atual:** Legado parcial (Secullum, Airtable)  
**Arquitetura-alvo:** PostgreSQL com sincronização bidirecional

**Critérios de saída:** Entidade validada, canônica, com rastreabilidade

---

## 4. RH (Recursos Humanos)

**Propósito:** Gerenciar ciclo de vida de relacionamento trabalhista.

**Responsabilidades:**
- Registrar admissão (contrato, salário, cargo)
- Manter vínculo ativo/inativo
- Processar encerramento
- Integrar com folha de pagamento
- Arquivar documentos contratuais
- Prover dados para outros módulos

**Não faz:**
- Calcular impostos
- Gerar recibos (Documentação faz)
- Gerenciar benefícios (fora de escopo)

**Entidades envolvidas:** Colaborador, Vínculo Trabalhista, Contrato, Alocação

**Camadas:** Negócio

**Estado atual:** Legado em app.py (admissão manual)  
**Arquitetura-alvo:** Módulo novo com workflow

**Critérios de saída:** Vínculo registrado, documentos arquivados, dados validados

---

## 5. Ponto (Secullum)

**Propósito:** Integrar com relógio de ponto e processar jornada.

**Responsabilidades:**
- Receber batidas do Secullum
- Calcular horas por período
- Detectar anomalias (falta, atraso)
- Alertar supervisor
- Gerar colunar para folha
- Manter histórico imutável

**Não faz:**
- Aprovar compensação
- Gerar holerite (Documentação faz)
- Alterar dados de Secullum

**Entidades envolvidas:** Colaborador, Escala, Batida, Alerta

**Camadas:** Entrada, Transformação

**Estado atual:** Legado (Secullum API, cálculo em app.py)  
**Arquitetura-alvo:** Módulo novo com tratamento defensivo

**Critérios de saída:** Colunar calculada, alertas gerados, histórico registrado

---

## 6. Documentos (Folha, FGTS, Guias)

**Propósito:** Gerar, versionar e arquivar documentos oficiais.

**Responsabilidades:**
- Receber dados de Ponto, RH, Cadastro
- Gerar holerite, FGTS, comprovantes
- Versionar cada documento
- Associar a período/competência
- Armazenar PDF
- Passar para Distribuição

**Não faz:**
- Calcular valores (Ponto faz)
- Enviar documentos (Distribuição faz)
- Modificar após geração

**Entidades envolvidas:** Documento, Holerite, FGTS, Guia, Período

**Camadas:** Transformação

**Estado atual:** Legado (template em app.py, específico por cliente)  
**Arquitetura-alvo:** Motor de template com contrato definido

**Critérios de saída:** PDF gerado, assinado, versionado, enviável

---

## 7. Distribuição

**Propósito:** Entregar documentos pelo canal apropriado.

**Responsabilidades:**
- Decidir entre e-mail, WhatsApp, combinado
- Preparar payload
- Enviar via Evolution API / SMTP
- Registrar status de entrega
- Retry automático com limite
- Escalar falhas para operador

**Não faz:**
- Gerar documento (Documentação faz)
- Processar respostas (Assinatura faz se assinável)
- Modificar destinatário

**Entidades envolvidas:** Envio, Tentativa, Canal, Status

**Camadas:** Entrega, Auditoria

**Estado atual:** Legado (4 rotas duplicadas em app.py)  
**Arquitetura-alvo:** Módulo unificado, parametrizado por canal

**Critérios de saída:** Documento entregue, status registrado, rastreabilidade confirmada

---

## 8. Assinaturas

**Propósito:** Capturar assinatura nativa com evidências legais.

**Responsabilidades:**
- Gerar link único assinável
- Capturar assinatura digital
- Registrar IP, timestamp, dados
- Validar CPF se fornecido
- Expirar link após prazo
- Arquivar evidência

**Não faz:**
- Gerar documento (Documentação faz)
- Decidir quem assina (Classificação/operador)
- Certificação digital (out of scope)

**Entidades envolvidas:** Solicitação de Assinatura, Link, Evidência

**Camadas:** Negócio, Auditoria

**Estado atual:** Legado (formulário simples, IP/CPF como evidência)  
**Arquitetura-alvo:** Módulo novo com protocolo robusto

**Critérios de saída:** Link expirado, evidência imutável, auditável

---

## 9. Auditoria e Observabilidade

**Propósito:** Registrar tudo que acontece para rastreabilidade e investigação.

**Responsabilidades:**
- Capturar evento de cada módulo (o quê, quando, quem)
- Manter histórico imutável
- Correlacionar requisições ponta a ponta
- Gerar alertas de anomalia
- Prover logs estruturados
- Consolidar relatórios operacionais

**Não faz:**
- Alterar estado de outro módulo (só observar)
- Tomar decisão (reportar e pronto)
- Corrigir dados

**Entidades envolvidas:** Evento, Log, Correlação, Relatório

**Camadas:** Auditoria

**Estado atual:** Parcialmente estruturado (eventos em código novo, não centralizado)  
**Arquitetura-alvo:** EventLog com replicação + dashboard

**Critérios de saída:** Evento gravado, recuperável, com correlação

---

## 10. Plataforma (Infraestrutura)

**Propósito:** Prover serviços compartilhados pelos 9 módulos acima.

**Responsabilidades:**
- Abstração de banco de dados (adapter)
- Abstração de armazenamento (S3/R2)
- Fila de processamento (Redis/Celery)
- API Gateway e autenticação
- Painel operacional
- Monitoramento de saúde
- Gestão de configuração

**Não faz:**
- Lógica de domínio (cada módulo tem a sua)
- Decisões de negócio

**Tecnologias:** Flask, Celery, Airtable (legado), PostgreSQL (alvo), S3

**Camadas:** Plataforma (todas)

**Estado atual:** Monólito legado em app.py, com extratos em src/  
**Arquitetura-alvo:** Monólito modular com pacotes por domínio

**Critérios de saída:** Serviço disponível, responde SLA, observável

---

## 11. Matriz de Dependências

| Módulo | Depende de | Fornece para | Via |
|---|---|---|---|
| Ingestão | Nenhum | Classificação | Contrato de item |
| Classificação | Ingestão, Cadastro | Documentação | Tipo + proprietário |
| Cadastro | Secullum, CNPJ | Todos (referência) | Lookup síncrono |
| RH | Cadastro | Ponto, Documentação | Vínculo ativo |
| Ponto | RH, Secullum | Documentação, Auditoria | Colunar |
| Documentação | Ponto, RH, Cadastro | Distribuição, Auditoria | PDF |
| Distribuição | Documentação | Auditoria | Status |
| Assinaturas | Distribuição | Auditoria | Evidência |
| Auditoria | Todos | Operador, relatórios | Evento |
| Plataforma | Sistema operacional | Todos | Serviços |

---

## 12. Riscos por Módulo

| Módulo | Risco crítico | Mitigação |
|---|---|---|
| Ingestão | Perda de arquivo | Hash + backup |
| Classificação | Classificação errada | Review humano + reprocessamento |
| Cadastro | Duplicata não detectada | Dedup com review |
| RH | Vínculo errado | Integração Secullum validada |
| Ponto | Cálculo incorreto | Testes por cliente, reprocessamento |
| Documentação | Geração errada | Template validado, revisão |
| Distribuição | Falha de entrega | Retry + escala manual |
| Assinaturas | Link expirado perdido | Resend + histórico |
| Auditoria | Log perdido | Replicação, imutabilidade |
| Plataforma | Downtime | Redundância + failover |

---

## 13. Estado e Próximas Ações

Todos os módulos estão **em transição**: legado funciona, novos estão em documentação ou preparação. Nenhum módulo recebe classificação "Produção autorizada" antes de Phase 10+. Todas as operações usam níveis qualitativos (Nenhuma autonomia, Leitura local, Análise assistida, Execução controlada, Execução supervisionada, Produção autorizada).

**Caminho recomendado:** Observabilidade → Encapsulamento → Ingestão → Classificação → RH/Ponto → Documentação → Distribuição → Assinaturas → Auditoria.
