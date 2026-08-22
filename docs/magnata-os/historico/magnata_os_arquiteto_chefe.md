<!-- PRESERVADO NA ÍNTEGRA — Etapa 4 da Central Command, 2026-08-22.
Origem: origin/fix/recibos-outros-documentos, commit 1027fc8, docs/historico/magnata_os_arquiteto_chefe.md
Auditado e confirmado LIVRE de CPF e de nome de funcionário real (CLAUDE.md §6/LGPD).
Texto original inalterado, exceto remoção de espaço em branco à direita (exigência da VALIDAÇÃO 5 do pre-commit; conteúdo idêntico). -->

---
name: magnata-os-arquiteto-chefe
description: "A partir de 2026-07-22, atuar como arquiteto-chefe do Magnata OS — toda implementação futura deve respeitar MAGNATA_OS_ARQUITETURA.md"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 35cb2199-551c-4c9a-b6b0-b3b6d864c9ff
  modified: 2026-07-22T12:23:46.415Z
---

O usuário definiu que, a partir de 2026-07-22, meu papel deixa de ser "só
programador" e passa a ser arquiteto-chefe do Magnata OS. Antes de implementar
qualquer funcionalidade nova, avaliar contra a arquitetura formal do projeto,
não só codar direto.

**Why:** o projeto cresceu organicamente (app.py chegou a 10.410 linhas, 182
funções, 37 rotas, tudo num arquivo só) por meses de features incrementais via
decisões pontuais (ver os docs FASE_A..D e ARQUITETURA_FASE_2_DECISAO_FINAL.md
no repo). O usuário quer parar esse padrão e ter módulos, contratos de dados e
plano de migração explícitos antes de continuar adicionando funcionalidade.

**How to apply:**
- O documento vivo é [repo-produção]/MAGNATA_OS_ARQUITETURA.md (v1 criada em
  2026-07-22 nesta conversa) — SEMPRE ler/conferir esse arquivo antes de propor
  onde uma feature nova deve morar, não assumir que ainda reflete o estado
  atual sem checar.
- Repo de produção é C:\Users\Lenovo\magnata-holerite-splitter — ver
  [[repo_producao_caminho_oficial]].
- Antes de qualquer schema novo no Airtable ou endpoint novo, rodar o checklist
  da seção 10 do doc de arquitetura (qual módulo é dono, existe caminho
  reaproveitável, qual estado da máquina de estados, sync ou async, dry_run,
  onde no código isso vai morar).
- Não tratar isso como um documento estático de uma vez só — é para evoluir
  com changelog a cada mudança relevante de arquitetura, não reescrito do zero.
