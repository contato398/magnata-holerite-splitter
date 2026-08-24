# ORQUESTRADOR — núcleos de negócio e arquitetura de fontes

**Etapa 5 da Central Command, 2026-08-22.**
**Reconciliado na Etapa 14, 2026-08-24, contra o código real em `main`.**

**Natureza:** registro de requisito e de evidência. Onde este documento descreve estado técnico, o código em `main` prevalece sobre texto histórico.

---

## 1. Os oito núcleos — classificação por evidência

A visão macro do Magnata OS prevê a Central Command coordenando oito núcleos de negócio. Abaixo, o que a evidência sustenta — sem inventar implementação e sem rebaixar o que existe.

**Legenda:** `EXISTE` (código real, em produção) · `EM CONSTRUÇÃO` (código novo, testado, ainda não em produção) · `EXISTE FORA DESTE REPOSITÓRIO` · `PLANEJADO` · `SEM EVIDÊNCIA`.

| Núcleo | Classificação | Evidência verificada | Módulo oficial correspondente |
|---|---|---|---|
| **Documental** | ✅ **EXISTE** + 🟡 **EM CONSTRUÇÃO** | Legado: `app.py` (split, geração, assinatura, distribuição), em produção. Novo: `magnata_os/documental/modulo01/` Fases 1-4 mescladas e testadas, nada em produção | 1 Ingestão · 2 Classificação · 6 Documentos |
| **RH** | ✅ **EXISTE** (legado) | Kit Admissão, vínculo trabalhista, `test_kit_admissao_identidade.py` | 3 Cadastro · 4 RH · 5 Ponto |
| **Operações** | ✅ **EXISTE** (difuso) | Filas de envio, disparo, reconciliação, Celery, `importacao_lote/` | 7 Distribuição · 9 Auditoria · 10 Plataforma |
| **Contábil/Fiscal** | ✅ **EXISTE** (parcial) | Remetentes DP/Fiscal, rotas de guias/FGTS e pipeline fiscal | 6 Documentos — sem módulo fiscal formal |
| **Financeiro** | ✅ **EXISTE FORA DESTE REPOSITÓRIO** | Airtable: `Pagamentos`, `Recebimentos`, `Despesas`, `Patrimônio` | — |
| **Comercial** | ✅ **EXISTE FORA DESTE REPOSITÓRIO** | Airtable: `Clientes`, `Locais`; `Contrato Comercial` é conceito oficial | — |
| **Marketing** | 🚫 **SEM EVIDÊNCIA** | Sem evidência no repositório nem nas tabelas mapeadas do Airtable | — |
| **Diretoria/BI** | 🔍 **A CONFIRMAR** | `DIA HOJE` / `DIA QR CODE` parecem painéis operacionais | — |

### 1.1 Correções acumuladas

Leituras anteriores classificaram Comercial e Financeiro como sem evidência porque procuravam apenas no código. A leitura do schema do Airtable mostrou que ambos já existem operacionalmente fora do repositório. Portanto, nesses núcleos o caminho é integração, não construção do zero.

---

## 2. Divergência de taxonomia — registrada para ADR futura

Coexistem três recortes com fonte real:

| Recorte | Fonte | Data | Situação |
|---|---|---|---|
| **9 módulos** | `MAGNATA_OS_ARQUITETURA.md` §2 | 2026-07-22 | ❌ SUPERADO pelo de 10 |
| **10 módulos** | `docs/magnata-os/MAGNATA_OS_MODULOS.md` v1.0 | 2026-07-25 | ✅ VIGENTE |
| **8 núcleos de negócio** | Direção | 2026-08 | ⚠️ SEM ADR |

Os 8 núcleos são recorte de negócio; os 10 módulos são recorte funcional. Não são intercambiáveis. Enquanto não houver ADR, os 10 módulos continuam sendo a taxonomia funcional vigente e os 8 núcleos são visão de destino.

---

## 3. Arquitetura de fontes de verdade — fronteiras

| Camada | É verdade sobre | Não é verdade sobre | Estado atual |
|---|---|---|---|
| **Central Command** | Memória, decisão, estado consolidado, proveniência | Código atual, dado operacional, execução | ✅ Existe e recebe AUTO_FACT |
| **GitHub** | Versionamento, evolução técnica, PRs/CI | Se o código está em produção | ✅ Existe |
| **Graphify** | Estrutura de código, símbolos, dependências e acoplamento | Decisão de negócio, dado de cliente | ✅ Adotado como sensor estrutural; snapshot versionado e uso seletivo |
| **Produção (Render)** | Execução real | Intenção, decisão | ✅ Existe · verificabilidade depende do acesso à produção |
| **Airtable / bancos** | Dado operacional | Arquitetura, decisão | ✅ Airtable ativo · Postgres próprio ainda não é fonte primária operacional |
| **Gmail / WhatsApp** | Eventos/canais de entrada e saída | Estado consolidado | ✅ Existem como canais; integração ao Orquestrador é progressiva |
| **Arquivo seguro** | Fonte histórica sensível com PII | Memória pública | 🔴 Requisito ainda não consolidado como camada automática |

### 3.1 Graphify — estado real

A afirmação histórica “não instalado, nenhuma referência” está **SUPERADA**.

Hoje o Graphify é usado como **sensor estrutural de código**, não como memória total do projeto. O fluxo desejado é:

> pergunta técnica → Graphify/snapshot → módulos e símbolos relevantes → leitura apenas dos arquivos necessários.

O modo code-only/AST é o caminho seguro para estrutura local; qualquer modo que envie conteúdo a provider externo deve respeitar os gates de segurança. `ARQUITETURA_SNAPSHOT.json` é DERIVED e pode ser regenerado. Graphify não substitui GitHub, decisão humana, estado de produção ou memória de negócio.

---

## 4. O que a arquitetura documental já garante

1. Proveniência e separação de fontes.
2. Distinção entre memória, dado operacional, código e execução.
3. Distinção: discutido ≠ autorizado ≠ implementado ≠ testado ≠ integrado ≠ implantado ≠ funcionando em produção.
4. AUTO_FACT pode ser atualizado mecanicamente sem sobrescrever HUMAN_DECISION.
5. Contexto progressivo reduz leitura massiva e preserva continuidade entre agentes/sessões.

A afirmação histórica de que “a Central Command é regenerada apenas por auditoria manual” também está **SUPERADA**. O Orquestrador já atualiza AUTO_FACT pelo caminho `sensor → motor → ação → ESTADO/AUDITORIA`, e existe um workflow agendado para disparo sem sessão humana. O que ainda não é completo é a autonomia operacional ponta a ponta em todas as fontes e ações.

---

## 5. Correções por evidência nova

### 5.1 Financeiro e Comercial existem fora do repositório

A leitura do schema do Airtable confirmou:

| Núcleo | Onde estava | Classificação corrigida |
|---|---|---|
| **Financeiro** | `Pagamentos` · `Recebimentos` · `Despesas` · `Patrimônio` | ✅ EXISTE FORA DESTE REPOSITÓRIO |
| **Comercial** | `Clientes` · `Locais` | ✅ EXISTE FORA DESTE REPOSITÓRIO |
| **Contábil/Fiscal** | `Contabilidade Mensal` · `Certidões` · `FGTS Digital` · `Escritórios Contabilidade` | ✅ EXISTE — mais amplo do que o registrado originalmente |
| **Marketing** | nenhuma tabela mapeada | 🚫 SEM EVIDÊNCIA |
| **Diretoria/BI** | `DIA HOJE` · `DIA QR CODE` | 🔍 A CONFIRMAR |

### 5.2 Graphify

Graphify não deve ser tratado como mero analisador estático nem como fonte primária. É sensor derivado; o código em `main` continua vencendo qualquer inferência estrutural.

---

## 6. Arquitetura de fontes do Grande Orquestrador

| Fonte | Verdade que fornece | Autoridade | Frequência | Reação à divergência |
|---|---|---|---|---|
| **Direção** | Decisão de negócio, vocabulário, prioridade | Máxima sobre decisão | Evento | Registra como HUMAN_DECISION; automação não sobrescreve |
| **Produção** | O que executa de fato | Máxima sobre execução | Contínua | Divergência com `main` é incidente a investigar |
| **Código em `main`** | O que o sistema faz | Alta | Por commit | Código prevalece sobre plano/documento técnico |
| **GitHub** | Versionamento, autoria, PRs, CI | Alta sobre histórico técnico | Por evento | Branch/PR/merge são validados por estado real |
| **Airtable** | Dado operacional real | Máxima sobre dado | Contínua | Dado vence memória; regra escondida é dívida a extrair |
| **Graphify** | Foto estrutural derivada do código | Média | Sob demanda/regenerável | Contradição com código → código vence |
| **Gmail / WhatsApp** | Eventos/canais | Média sobre ocorrência do evento | Contínua | Integrações devem evoluir por shadow/read-only antes de escrita |
| **Central Command** | Estado consolidado, decisão, proveniência | Alta sobre memória | Automática + auditoria | Nunca vence fonte primária; é reconciliada |

### 6.1 Regra de arbitragem

> **Direção > produção (execução) > código em `main` > dado operacional > memória consolidada > derivados.**

### 6.2 Estado real do Orquestrador

A afirmação anterior “o Orquestrador ainda não existe de fato” está **SUPERADA**.

| Peça | Estado atual |
|---|---|
| Memória, decisão, proveniência | ✅ Existe |
| Taxonomia da memória | ✅ Formalizada |
| Matriz de autonomia | ✅ Formalizada e reconciliada |
| Arquitetura de eventos | ✅ Formalizada |
| **Motor executável** | ✅ **Existe** em `magnata_os/orquestrador/motor.py` |
| Envelope/eventos e máquina de estados | ✅ Existe |
| Política de autonomia | ✅ Existe |
| Deduplicação/idempotência | ✅ Existe |
| Retry/backoff/classificação de falha | ✅ Existe |
| Persistência de execução | ✅ Existe (incluindo SQLite no caminho de confiabilidade implementado) |
| Observabilidade/auditoria | ✅ Existe |
| Proteção contra escrita em HUMAN_DECISION/caminho protegido | ✅ Validada em runtime |
| AUTO_FACT → `ESTADO.json` | ✅ Existe |
| Métrica compacta de contexto + stale detection | ✅ Existe após PR #52 |
| **Gatilho automático sem sessão** | ✅ Existe em `.github/workflows/orquestrador-sensor.yml` (`schedule` + `workflow_dispatch`) |
| Branch/commit/push automáticos de AUTO_FACT | ✅ Implementados no workflow |
| Abertura automática de PR | 🟡 Implementada no workflow; depende da permissão/configuração do GitHub Actions para criar PR |
| Health persistente de ponta a ponta | 🟡 Próxima frente de robustez |
| E2E único cobrindo ciclo completo operacional | 🟡 Próxima frente de prova |
| Produção/Render como fonte automaticamente reconciliada | 🔴 Ainda não consolidado |
| Gmail/Airtable/WhatsApp como fontes operacionais conectadas ao motor | 🟡 Progressivo; preservar shadow/read-only e gates antes de escrita |

### 6.3 O que define a próxima fase

A próxima fase não é “criar um Orquestrador”. Ele já existe.

O objetivo agora é transformá-lo em uma **rotina operacional permanente**, com prioridade para automação e humano apenas por exceção:

> evento → detectar → ler estado → classificar → aplicar política → agir se seguro → validar → persistir → auditar → atualizar memória → chamar humano somente em gate real.

Prioridade técnica:

1. health persistente;
2. E2E completo e repetível;
3. provar/desbloquear abertura automática de PR pelo GitHub Actions;
4. expandir fontes em shadow/read-only;
5. ampliar tipos de evento e ações `EXECUTE_SAFE` com idempotência e observabilidade;
6. manter produção, decisão humana, escrita externa sensível e destruição sob gates explícitos até haver política específica autorizada.

---

## 7. Princípio permanente de operação

O Grande Orquestrador final não deve transformar pessoas em cron jobs humanos. Tarefas repetitivas, verificáveis e reversíveis devem ser automatizadas. O humano deve receber decisões, exceções, risco, conflito e irreversibilidade — não trabalho mecânico que o sistema consegue executar e provar sozinho.
