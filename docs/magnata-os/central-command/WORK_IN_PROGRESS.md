# WORK_IN_PROGRESS — Magnata OS

Trabalho começado, com código/documento real, mas não concluído nem
mesclado em `main`. Complementa `CENTRAL_COMMAND_MAGNATA_OS.md` §9.3
com o detalhe de proveniência de cada item.

Legenda: 🟡 EM EVOLUÇÃO · 🚫 PLANEJADO MAS NÃO EXECUTADO

---

### WIP-001 — Fundação documental completa do Magnata OS
- **Branch:** `feat/magnata-os-claude-powerpack`
- **Início:** 2026-07-30 (mas o conteúdo em si — Manifesto, Entidades,
  Contratos, Estados, Eventos — já existia localmente, não versionado,
  desde antes; ver `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA1.md`)
- **Estado:** 5 commits, parado desde 2026-07-30. 6 dos documentos
  foram copiados para `main` pontualmente em 2026-08-03 (DEC-005); os
  demais (`ARQUITETURA`, `ENTIDADES`, `DECISOES_ENTIDADES`, `EVENTOS`,
  `CONTRATOS`, `ESTADOS`, ADR-001, skills/subagentes,
  `MATRIX_DE_RESPONSABILIDADES`) seguem só na branch.
- **Status:** 🟡 EM EVOLUÇÃO, mas estagnado — falta decisão sobre
  reconciliar com os 70 commits que `main` já ganhou desde a
  divergência (`CENTRAL_COMMAND_MAGNATA_OS.md` §3, §14 item 1).

### WIP-002 — Painel visual do Módulo 01 (Documental, Fase 5)
- **Branch:** `feat/magnata-os-documental-modulo01-fase5-painel`
- **Início/última alteração:** 2026-07-25, 1 commit
- **Estado:** não lido em detalhe nesta auditoria (ver
  `SOURCES_AND_PROVENANCE.md` §4) — existência e não-mesclagem
  confirmadas na Etapa 1.
- **Status:** 🚫 PLANEJADO MAS NÃO EXECUTADO (em produção); código existe

### WIP-003 — ADR: fiação HTTP do Módulo 01
- **Branch:** `fix/adr-modulo01-http-wiring`
- **Data:** 2026-08-13
- **Estado:** proposta completa (3 opções, recomendação A, 3
  pré-condições), aguardando aprovação humana — ver DEC-008
- **Status:** 🚫 PLANEJADO MAS NÃO EXECUTADO

### WIP-004 — Plano de consolidação Ingestão → Distribuição
- **Branch:** `claude/evolution-api-instances-1s9raa` (= `fix/plano-modulo01-email-captura`)
- **Data:** 2026-08-17
- **Estado:** plano de direção registrado, próxima ação concreta
  (adapter de e-mail para o Módulo 01) aguardando confirmação — ver DEC-009
- **Status:** 🚫 PLANEJADO MAS NÃO EXECUTADO
- **Correção declarada (2026-08-23):** adapter implementado e auditado
  na mesma branch (PR #22), 10 testes, suíte geral 649→659, rebaseado
  sobre `main` atual, `clean`, CI/governança verdes — ver DEC-009.
  **Status corrigido: 🟡 EM EVOLUÇÃO** (pronto para merge, gate humano
  pendente; não conectado a fonte de e-mail real).

### WIP-005 — Correção da regressão em `_status_funcionario_elegivel`
- **Branch:** `fix/status-funcionario-pii`
- **Data:** 2026-08-17
- **Estado:** correção pronta (commit `448978d`), mas a branch está 18
  commits atrás de `main` e não foi rebaseada nem mesclada — a
  regressão que ela corrige está **ativa em `main` hoje**, confirmada
  por execução real de teste na Etapa 1 (6 testes falhando)
- **Status:** 🟡 EM EVOLUUÇÃO — é o item de maior prioridade técnica
  imediata desta lista (pequeno, isolado, causa raiz já identificada)

### WIP-006 — `magnata gate` (verificação automatizada de fase)
- **Fonte:** `docs/magnata-os/MAGNATA_OS_GATE_ESPECIFICACAO.md` (`main`)
- **Estado:** só especificação, explicitamente não implementada por
  instrução — decisões em aberto (onde a baseline de falhas
  pré-existentes vive, CLI vs. skill vs. parte do CI)
- **Status:** 🚫 PLANEJADO MAS NÃO EXECUTADO

### WIP-007 — Ativação real da esteira de importação em lote (Julho/2026)
- **Fonte:** `docs/magnata-os/MAGNATA_OS_HANDOFF_ATIVACAO_JULHO2026.md` (`main`)
- **Estado:** runbook completo, dry-run reconfirmado (135 itens: 114
  prontos, 21 em exceção), canário selecionado — falta só o
  provisionamento real de Postgres no Render e a execução, ambos gates
  humanos fora do alcance de qualquer sessão sem essa ferramenta
- **Status:** 🚫 PLANEJADO MAS NÃO EXECUTADO (código e plano prontos)

### WIP-008 — Reorganização física de `docs/magnata-os/` (numeração 00-10)
- **Fonte:** `docs/magnata-os/README.md` §"Por que os arquivos não foram movidos para cá" (`main`)
- **Estado:** proposta de estrutura descrita, não executada — exige
  reescrever 294+ referências cruzadas primeiro
- **Status:** 🚫 PLANEJADO MAS NÃO EXECUTADO
