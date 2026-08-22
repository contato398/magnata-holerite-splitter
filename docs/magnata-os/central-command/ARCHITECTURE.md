# ARCHITECTURE — Magnata OS (pointer + achados de proveniência)

Este arquivo **não repete** `CENTRAL_COMMAND_MAGNATA_OS.md` §2/§4 nem os
documentos fundacionais em `docs/magnata-os/`. Registra só o que a
auditoria de memória (Etapa 2) acrescentou sobre **como a arquitetura
documentada chegou a este estado** — proveniência, não conteúdo.

## Linha do tempo da fundação documental

1. **2026-07-20** — `ARQUITETURA_FASE_2_DECISAO_FINAL.md`: última
   decisão arquitetural do modelo antigo (reaproveitamento de campos
   Airtable), pré-Manifesto. Nunca versionada à época; hoje só recuperável
   na branch `feat/magnata-os-claude-powerpack`. Ver DEC-011.
2. **2026-07-22** — Diretiva "arquiteto-chefe" (DIR-003): usuário decide
   parar o crescimento orgânico de `app.py` (10.410 linhas, 182 funções,
   37 rotas) e exigir avaliação contra arquitetura formal antes de
   implementar. `MAGNATA_OS_ARQUITETURA.md` v1 criado **na mesma
   conversa**, guardado só localmente (Windows do usuário).
3. **~2026-07-22 a 2026-07-30** — Documentos fundacionais volumosos
   (`ENTIDADES`, `CONTRATOS`, `ESTADOS`, `EVENTOS`, `DECISOES_ENTIDADES`,
   `MODULO_01_INGESTAO`, `MODULO_01_DECISOES_IMPLEMENTACAO`) escritos,
   também só localmente — nunca commitados nesse intervalo. Risco de
   perda total por falha de máquina, declarado explicitamente em
   `MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA1.md` §7 como o motivo de
   existir a etapa "Powerpack".
4. **2026-07-30** — Branch `feat/magnata-os-claude-powerpack` criada a
   partir de `main` (`f1c0edc`). Etapa 1 do Powerpack ("Preservação e
   Governança da Documentação Fundacional") commita os 9 documentos
   fundacionais + histórico de memória pela primeira vez em qualquer
   controle de versão. Parecer da própria etapa: "FUNDAÇÃO PROTEGIDA —
   risco de perda total eliminado a partir deste commit."
5. **Etapas 2-6 do Powerpack** (mesma branch, 2026-07-30, datas internas
   variam): `CLAUDE.md` e hierarquia de 4 arquivos (Etapa 2); 5 skills +
   5 subagentes técnicos (Etapa 3); `CAPACIDADES`/`MODULOS`/`ROADMAP`/
   `MATRIZ_ARQUITETURAL` (Etapa 4, com 3 bloqueadores registrados em
   `ETAPA4_DIVERGENCIAS_REVISAO.md` — ver DEC-004); git hooks locais
   (Etapa 5); CI de governança (Etapa 6, **esta sim mesclada em `main`**
   via PR #13, `d616d521`, em 2026-08-03).
6. **2026-08-03** — Commit `19445e9` (na verdade originado da branch
   `feat/magnata-os-etapa6-governanca`, não da powerpack diretamente)
   copia **6 dos 9** documentos fundacionais + os 3 `CLAUDE.md`
   escopados para `main`, para destravar uma contradição real entre
   dois gates do CI (Gate 12 exigia a hierarquia de `CLAUDE.md`; a
   Validação 6 do pre-commit bloqueava os mesmos caminhos). **Não foi
   uma decisão de "adotar toda a fundação"** — foi uma correção pontual
   de CI que teve o efeito colateral de trazer parte da fundação
   junto. Ver DEC-005.
7. **2026-08-21 (hoje)** — Etapa 1 desta auditoria encontra a lacuna
   (README cita 9 documentos, só 6-ish existem); Etapa 2 reconstrói essa
   linha do tempo completa a partir do commit e dos relatórios de fase.

## O que isso muda na leitura da arquitetura "oficial"

- `MAGNATA_OS_MODULOS.md`, `MAGNATA_OS_CAPACIDADES.md`,
  `MAGNATA_OS_ROADMAP.md`, `MAGNATA_OS_MATRIZ_ARQUITETURAL.md` (em
  `main`) **não são o primeiro rascunho** — são a versão que sobreviveu
  depois de bloqueadores terem sido levantados e (aparentemente)
  resolvidos numa revisão que não deixou rastro formal (DEC-004). Tratar
  como estável, mas com uma nota de proveniência incompleta.
- `MAGNATA_OS_ARQUITETURA.md` propriamente dito (o documento "estado
  real + plano", topo da cadeia de precedência do próprio
  `docs/magnata-os/README.md`) **nunca chegou a `main`** — o que está
  em `main` hoje é a camada de baixo (`CAPACIDADES`/`MODULOS`/
  `ROADMAP`/`MATRIZ`), sem o documento que deveria estar no topo dela.
  Isso não é um erro novo desta etapa — já era o achado central da
  Etapa 1 (§3) — mas agora está com a causa raiz completa.

## Débito técnico histórico, ainda não confirmado como resolvido

`ARQUITETURA_FASE_2_DECISAO_FINAL.md` (2026-07-20) registrou que o
campo `Tipo de Documento` (Airtable, `Processar Arquivos`) mistura
categoria real de documento com códigos de erro técnico do hotfix —
classificado como "não corrigir agora, débito técnico para fase
futura de limpeza". Nenhuma fonte posterior auditada confirma correção.
Ver `PENDING.md` PEN-002.
