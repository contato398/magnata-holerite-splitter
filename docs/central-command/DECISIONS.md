# DECISIONS — Magnata OS

Decisões arquiteturais e técnicas extraídas das fontes auditadas (ver
`SOURCES_AND_PROVENANCE.md`). Cada registro segue o esquema pedido:
ID, descrição, categoria, data/origem, fonte, status atual, evidência
técnica, implementada?, testada?, em produção?, substituída?/por quê.

Legenda: ✅ FUNCIONANDO/CONFIRMADO · 🟡 EM EVOLUÇÃO · ⚠️ PENDENTE ·
❌ DESCARTADO/SUPERADO · 🔍 PRECISA SER VALIDADO · 🚫 PLANEJADO MAS NÃO EXECUTADO

---

### DEC-001 — Migração para "Magnata OS" via strangler pattern, com papel de arquiteto-chefe
- **Categoria:** decisão arquitetural fundacional
- **Data/origem:** 2026-07-22
- **Fonte:** `docs/historico/magnata_os_arquiteto_chefe.md` (branch `fix/recibos-outros-documentos`)
- **Status atual:** ✅ FUNCIONANDO/CONFIRMADO — é o princípio vigente hoje, reafirmado em `MAGNATA_OS_MANIFESTO.md` e `CLAUDE.md` (`main`)
- **Evidência técnica:** `MAGNATA_OS_MANIFESTO.md` em `main`; `magnata_os/` como diretório de código novo isolado
- **Implementada?** Sim, como princípio orientador — a implementação concreta (módulos) está em andamento (ver `ARCHITECTURE.md`)
- **Testada?** N/A (decisão de direção, não código)
- **Em produção?** N/A
- **Substituída?** Não

### DEC-002 — Nomenclatura da entidade central: "Documento" (código) vs. "Item de Ingestão" (documentos)
- **Categoria:** conflito de nomenclatura, registrado e não resolvido
- **Data/origem:** identificado formalmente em `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA1.md` §4.1 (2026-07-30); proposta de resolução em `docs/magnata-os/MAGNATA_OS_ADR_001_NOMENCLATURA_ITEM_INGESTAO_VS_DOCUMENTO.md` (só existe na branch powerpack)
- **Fonte:** `CLAUDE.md` §5 (`main`, vigente), `feat/magnata-os-claude-powerpack`
- **Status atual:** ⚠️ PENDENTE — `CLAUDE.md` §5 já resolve isso **operacionalmente** ("em código novo, seguir `Documento`"), mas a decisão formal (ADR-001) nunca foi aprovada nem chegou a `main`
- **Evidência técnica:** zero ocorrência de "Item de Ingestão" como nome de classe em `magnata_os/` (confirmado Etapa 1)
- **Implementada?** Sim, na prática (código usa `Documento`)
- **Testada?** N/A
- **Em produção?** N/A (é convenção de nome, não funcionalidade)
- **Substituída?** Não — ainda aberta

### DEC-003 — Autorização por fase com checkpoint humano em mensagem distinta (`CLAUDE.md` §6)
- **Categoria:** decisão de governança/segurança
- **Data/origem:** commits `80bf8f6` (2026-08-03, "formaliza autonomia operacional ampliada") e `e3eb40d` (2026-08-03, "alinha ações externas à autorização por fase")
- **Fonte:** `CLAUDE.md` §6 e §12 (`main`, vigente)
- **Status atual:** ✅ FUNCIONANDO/CONFIRMADO — mecanismo em vigor, citado como já usado em `MAGNATA_OS_HANDOFF_ATIVACAO_JULHO2026.md` §0
- **Evidência técnica:** texto de `CLAUDE.md` em `main`
- **Implementada?** Sim (é regra de processo, não código)
- **Testada?** N/A
- **Em produção?** Sim, é a regra vigente de operação
- **Substituída?** Não

### DEC-004 — Resolução aparente dos 3 bloqueadores arquiteturais da Etapa 4 do Powerpack
- **Categoria:** decisão arquitetural — 🔍 inferida, não confirmada por artefato explícito
- **Data/origem:** bloqueadores registrados em 2026-07-25 (`MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA4_DIVERGENCIAS_REVISAO.md`, só na branch powerpack)
- **Fonte:** comparação entre esse relatório e o conteúdo de `docs/magnata-os/MAGNATA_OS_MODULOS.md`/`MAGNATA_OS_CAPACIDADES.md`/`MAGNATA_OS_ROADMAP.md` hoje em `main`
- **Status atual:** 🔍 PRECISA SER VALIDADO. Os documentos em `main` **parecem** ter resolvido os 3 bloqueadores (ver `SUPERSEDED_DECISIONS.md` SUP-003/SUP-004/SUP-005), mas **nenhuma ADR-002 ou decisão explícita foi encontrada** registrando isso como resolução deliberada — pode ter sido uma reescrita direta dos documentos antes do commit, sem o rastro formal que o próprio `CLAUDE.md` §2 exige ("nenhuma decisão arquitetural em silêncio")
- **Evidência técnica:** diff de conteúdo entre a versão dos docs na branch powerpack (bloqueada) e a versão em `main` (sem os 3 conflitos)
- **Implementada?** Sim, o resultado está em `main`
- **Testada?** N/A
- **Em produção?** Os documentos sim; o que eles descrevem (módulos), não
- **Substituída?** Este próprio item é a "decisão de resolução" que falta confirmar

### DEC-005 — Cópia seletiva de documentos fundacionais da branch powerpack para `main`
- **Categoria:** decisão técnica pontual (não uma adoção completa da fundação)
- **Data/origem:** commit `19445e9`, 2026-08-03, "fix: alinha escopo documental com a governança"
- **Fonte:** `git show --stat 19445e9` (auditado nesta sessão)
- **Status atual:** ✅ FUNCIONANDO/CONFIRMADO como o que de fato aconteceu — mas **o texto do commit ("Inclui os 9 arquivos fundacionais") é impreciso**: só 6 dos documentos citados pelo índice foram copiados (`CLAUDE.md`, `MAGNATA_OS_MANIFESTO.md`, `MAGNATA_OS_CAPACIDADES.md`, `MAGNATA_OS_MATRIZ_ARQUITETURAL.md`, `MAGNATA_OS_MODULOS.md`, `MAGNATA_OS_ROADMAP.md`), mais os 3 `CLAUDE.md` escopados. `ARQUITETURA`, `ENTIDADES`, `EVENTOS`, `CONTRATOS`, `ESTADOS`, ADR-001, skills/agentes **não foram incluídos**, ao contrário do que a mensagem sugere.
- **Evidência técnica:** `git show --stat 19445e9` (12 arquivos alterados, listados)
- **Implementada?** Sim
- **Testada?** Sim — o próprio commit adiciona 5 testes de regressão (41-45) em `scripts/ci/test_governance.sh`
- **Em produção?** Sim, é o estado atual de `main`
- **Substituída?** Não, mas está incompleta em relação ao objetivo declarado — ver `PENDING.md`

### DEC-006 — Pacote atômico de assinatura: Holerite + Folha de Ponto
- **Categoria:** decisão de produto/negócio
- **Data/origem:** 2026-08-12
- **Fonte:** `docs/decisoes/pacote-holerite-folha-ponto.md` (`main`)
- **Status atual:** ✅ FUNCIONANDO/CONFIRMADO — branch `fix/holerite-ponto-pacote-assinatura` mesclada em `main` (confirmado Etapa 1)
- **Evidência técnica:** `test_pacote_assinatura_holerite_ponto.py` (68 testes, 62 passando hoje — 6 falhando por regressão não relacionada, ver `PENDING.md` PEN-001)
- **Implementada?** Sim
- **Testada?** Sim, majoritariamente (ver ressalva acima)
- **Em produção?** Sim
- **Substituída?** Não

### DEC-007 — Correção de remetentes monitorados de e-mail (DP e Fiscal)
- **Categoria:** decisão de configuração/integração
- **Data/origem:** 2026-08-03
- **Fonte:** `docs/decisoes/remetentes-dp-fiscal.md` (`main`)
- **Status atual:** 🔍 PRECISA SER VALIDADO — branch `fix/remetente-dp-email-intake` está mesclada em `main` (confirmado Etapa 1), mas o documento original dizia "aguardando autorização de publicação em produção"; como o remetente correto vive em `apps_script_email_intake.gs`, que precisa ser **publicado manualmente no Google Apps Script** (fora do controle de deploy do Git/Render), não há como esta auditoria confirmar se a publicação de fato ocorreu
- **Evidência técnica:** `apps_script_email_intake.gs` em `main`
- **Implementada?** No código-fonte, sim
- **Testada?** `test_apps_script_email_intake_remetentes.py` existe e passa
- **Em produção?** 🔍 não confirmável a partir do repositório
- **Substituída?** Não

### DEC-008 (proposta, não decidida) — ADR: fiação HTTP do Módulo 01 ao motor principal
- **Categoria:** decisão arquitetural proposta
- **Data/origem:** 2026-08-13
- **Fonte:** `docs/decisoes/modulo01-fiacao-http.md`, branch `fix/adr-modulo01-http-wiring`
- **Status atual:** 🚫 PLANEJADO MAS NÃO EXECUTADO — recomendação é a Opção A (Blueprint novo, aditivo), condicionada a autenticação real + Postgres provisionado (ou adapter Airtable) + aprovação humana explícita em mensagem distinta
- **Evidência técnica:** análise de código no próprio documento (`grep magnata_os app.py` → zero resultado, confirmado)
- **Implementada?** Não
- **Testada?** N/A
- **Em produção?** Não
- **Substituída?** Não

### DEC-009 (proposta, não decidida) — Plano de consolidação Ingestão → Classificação → Distribuição
- **Categoria:** decisão de direção técnica (roadmap tático)
- **Data/origem:** 2026-08-17
- **Fonte:** `docs/decisoes/plano-consolidacao-ingestao-distribuicao.md`, branch `claude/evolution-api-instances-1s9raa`
- **Status atual:** 🚫 PLANEJADO MAS NÃO EXECUTADO — recomendação explícita de **não construir nada novo no Make.com**; próxima ação proposta (adapter de e-mail para o Módulo 01, em paralelo ao Gmail Apps Script) **aguardando confirmação para iniciar**
- **Evidência técnica:** tabela de rotas legadas vs. cobertura do Módulo 01, construída por leitura de código nessa sessão
- **Implementada?** Não
- **Testada?** N/A
- **Em produção?** N/A
- **Substituída?** Não

### DEC-010 — Decisão oficial de e-mails de envio/recebimento
- **Categoria:** decisão de configuração
- **Data/origem:** 2026-06-15
- **Fonte:** `docs/historico/v2_29_distribuicao_email.md`
- **Status atual:** 🔍 PRECISA SER VALIDADO — o próprio documento já registrava ambiguidade não resolvida entre `contato@magnataservicos.com.br` (envio) e uma divergência de grafia do remetente de recebimento (`dpessoal.contabilidade1@hotmail.com` vs. `depessoalcontabilidade@hotmail.com`); `docs/decisoes/remetentes-dp-fiscal.md` (2026-08-03, DEC-007) trata parte disso, mas não fica claro nesta auditoria se a ambiguidade original foi 100% fechada
- **Evidência técnica:** `apps_script_email_intake.gs`, env vars `EMAIL_SENDER`/`SMTP_HOST` citadas em `app.py`
- **Implementada?** Sim, parcialmente (ver DEC-007)
- **Testada?** Parcial
- **Em produção?** 🔍 não confirmável
- **Substituída?** Parcialmente, por DEC-007

### DEC-011 (histórica, contexto pré-Manifesto) — Reaproveitamento de campos Airtable para classificação (Arquitetura Fase 2)
- **Categoria:** decisão arquitetural histórica
- **Data/origem:** 2026-07-20
- **Fonte:** `ARQUITETURA_FASE_2_DECISAO_FINAL.md`, branch `feat/magnata-os-claude-powerpack` (documento pré-Manifesto)
- **Status atual:** ❌ DESCARTADO/SUPERADO como *fonte de precedência* — o próprio `docs/magnata-os/README.md` (§"Documentos históricos") já o trata como precedente histórico substituído pela fundação atual, preservado só como registro. O **débito técnico que ele registrou** (campo `Tipo de Documento` do Airtable contaminado com códigos de erro técnico) segue sem confirmação de correção — ver `PENDING.md` PEN-002.
- **Evidência técnica:** análise de campos/Field IDs no próprio documento
- **Implementada?** Sim, à época (é decisão sobre o legado já em produção)
- **Testada?** Não declarado
- **Em produção?** Sim, é sobre dado real do Airtable
- **Substituída?** Sim — pela fundação Magnata OS como um todo (DEC-001)
