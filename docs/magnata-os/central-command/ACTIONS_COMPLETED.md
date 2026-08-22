# ACTIONS_COMPLETED — Magnata OS

Ações concretas executadas (deploy, correção, migração de dado,
implementação concluída) extraídas das fontes auditadas. Uma linha por
item de `docs/historico/` (30 arquivos, branch `fix/recibos-outros-documentos`,
12/06 a 01/07/2026) mais as ações da própria auditoria (Etapa 1/2,
2026-08-21). Todas as datas/números abaixo são **os que constavam no
documento fonte, no momento em que foi escrito** — nenhum foi
reconfirmado contra produção nesta auditoria (regra `CLAUDE.md` §6).
Ver `PENDING.md` para o que ficou em aberto em cada uma.

Legenda: ✅ concluída e confirmada no documento fonte · 🔍 concluída
mas com resultado parcial/pendência residual explícita no próprio
documento.

| ID | Ação | Data | Fonte (`docs/historico/`) | Status no documento | Evidência técnica |
|---|---|---|---|---|---|
| ACT-001 | Correção de valores financeiros zerados nos holerites Maio/Jun 2026 (`/corrigir-valores`, app.py v2.5) | 2026-06-12 | `holerites_correcao_maio2026.md` | ✅ 78/78 atualizados, 0 erros | commit `e0ecbaf` |
| ACT-002 | Fase 5C: pré-cadastro automático a partir de Contrato de Experiência/Trabalho (app.py v2.16) | 2026-06-13 | `fase5c_pre_cadastro_funcionarios.md` | 🔍 implementado com 3 saídas; arquitetura de 4 ramos pedida pela diretoria (DIR-001) não confirmada | commit `e0b131f` |
| ACT-003 | Diretriz de Distribuição Mensal de Documentos registrada (não implementada na época) | 2026-06-14 | `distribuicao_mensal_documentos_arquitetura.md` | 🔍 diretriz, não ação concluída | — |
| ACT-004 | Faxina da tabela Funcionários no Airtable (182→149 linhas, dedup, normalização WhatsApp) | 2026-06-15 | `faxina_base_funcionarios_jun2026.md` | ✅ concluída, decisões registradas | Airtable MCP direto |
| ACT-005 | Correção do classificador de conteúdo — Cartão Ponto Secullum caía em "Outro" | 2026-06-15 (corrigido v2.26) | `classificador_secullum_v2_26.md` | ✅ corrigido, coberto por teste | commit `7dd89d6`, `test_classificar_cartao_ponto_secullum` |
| ACT-006 | Cruzamento Cartão Ponto × Status (reativação de 3 inativos por engano, gestão de desligado no meio do mês) | 2026-06-15 | `ponto_status_inativos_mes.md` | ✅ concluída | Airtable direto |
| ACT-007 | v2.25 — Envio combinado Holerite + Cartão Ponto na mesma mensagem WhatsApp | 2026-06-15 | `v2_25_envio_combinado.md` | ✅ deployado, `/health` confirmado 2.25 | commit `bfca841` |
| ACT-008 | v2.27 — `/processar-folha-ponto`, fatiamento do mestre de Cartão Ponto por CPF | 2026-06-15 | `v2_27_ponto_master_splitter.md` | ✅ corrigido (81/152 anexados, resto sem CPF por desenho) | commit `0810be4` |
| ACT-009 | v2.29-2.31 — Distribuição por e-mail: fatiador por cliente, fila de e-mail, motor SMTP, protocolo de entrega | 2026-06-15 | `v2_29_distribuicao_email.md` | 🔍 concluído com várias pendências residuais explícitas (Contratações/Rescisões/Férias no pacote cliente, FGTS broadcast, ambiguidade de remetente) | commits `727f2e7`,`84028ba`,`15ecdd7`,`133de29`,`c9114f8`,`afeed01`,`1cd3448`,`5f511c4` |
| ACT-010 | Reprocesso direcionado de holerites sem duplicar (sub-PDF por CPF) | 2026-06-15 | `reprocesso_direcionado_holerites.md` | ✅ procedimento validado | — |
| ACT-011 | Confirmação do repositório de produção oficial (correção de quase-erro) | 2026-06-15/24 | `repo_producao_caminho_oficial.md` | ✅ registrado como lição | — |
| ACT-012 | Padrão de deploy: bump de versão + confirmação via `/health` | anterior a 2026-06-15 | `padrao_deploy_render_confirmar_versao.md` | ✅ adotado como prática | — |
| ACT-013 | Documentos do Instituto de Nefrologia (cliente novo) mapeados para envio de Maio | 2026-06-15/16 | `instituto_nefrologia_docs_maio.md` | 🔍 FGTS de Maio ficou pendente (precisa re-fatiar) | — |
| ACT-014 | Módulo `sync_new_employees.py` — extração de cadastro do header do holerite | 2026-06-25 | `automacao_cadastro_holerite_sync_new_employees.md` | 🔍 validado só em dry-run, **nunca executado de verdade** (nem grava Airtable nem chama Secullum) | `src/sync_new_employees.py` |
| ACT-015 | Automação DP (e-mail) + Assinatura Nativa via WhatsApp com evidências jurídicas | 2026-06-22 | `automacao_dp_email_assinatura_v2_36_a_v2_41.md` | ✅ testado ponta a ponta com funcionário real, deployado v2.35→v2.41 | Apps Script + rotas `/assinatura/*` |
| ACT-016 | Auditoria de integridade da tabela Arquivos (5.109 registros, 2 sem anexo) | 2026-06-23 | `auditoria_integridade_arquivos_jun2026.md` | ✅ concluída (read-only) | Airtable MCP |
| ACT-017 | Processamento do backlog de Holerite do import retroativo de 15/06 (v2.46-2.48) | 2026-06-23 | `v2_48_processamento_backlog_holerites.md` | 🔍 248 arquivados corretamente, 111 sinalizados como pendência (ver `PENDING.md` PEN-004) | script `executar_holerite_ponto.py` |
| ACT-018 | Reclassificação de rescisões mal classificadas como Holerite | 2026-06-23 | `v2_48_processamento_backlog_holerites.md` | ✅ 56/56 reclassificadas e processadas | scripts `reclassificar_rescisoes.py`, `processar_rescisoes.py` |
| ACT-019 | Relatório de colaboradores crônicos (Batida Ímpar) por posto, Junho/2026 | 2026-06-24 | `cronicos_relatorio_postos_jun2026.md` | 🔍 relatório entregue, decisão de estratégia de agregação **nunca tomada** (sessão pausada) | — |
| ACT-020 | Integração Secullum Ponto Web — módulo `/secullum`, endpoints reais, 3 travas de negócio (v2.49-2.50) | 2026-06-24 | `v2_49_secullum_ponto.md` | ✅ dry-run validado; gravação real ainda não feita neste ponto | `src/services/secullum_ponto.py` |
| ACT-021 | Folga Trabalhada via marcador literal + Bônus de Assiduidade via colunas nativas (v2.53-2.54) | 2026-06-25 | `v2_53_folga_bonus_assiduidade.md` | ✅ mecanismo revisado após 3 achados de dado não confiável | mesmo módulo |
| ACT-022 | Primeira gravação real do motor de auditoria de ponto (v2.55-2.56), autorizada pela diretoria | 2026-06-25 | `v2_55_gravacao_real_jun2026.md` | ✅ 566→ depois 698 alertas gravados (janela ampliada), bônus calculado | mesmo módulo |
| ACT-023 | Saneamento de 20 "invisíveis" Secullum — schema real do POST descoberto | 2026-06-27 | `v2_60_saneamento_secullum_jun2026.md` | 🔍 5/20 concluído, 13 bloqueados (ver DIR-006/DIR-008) | mesmo módulo |
| ACT-024 | Migração de 32 colaboradores para horários "SEM INTERVALO" | 2026-06-28 | `v2_62_estabilizacao_secullum_e_onboarding_zero_batida.md` | ✅ 100% migrados, 2 correções de dado no Airtable | interface web Secullum (manual, sem API) |
| ACT-025 | Diagnóstico de inconsistência de escala (rótulo × comportamento real) v2.61 | 2026-06-27 | `v2_61_diagnostico_inconsistencia_escala.md` | ✅ 2 bugs de cálculo corrigidos (v2.61.1); achado sistêmico de paridade registrado, não "corrigido" (é rótulo interno da Secullum) | `detectar_inconsistencia_escala` |
| ACT-026 | Correção de erro de identidade — CPF de um colaborador atribuído por engano à análise de outro (nomes no documento fonte) | 2026-06-28 | `v2_64_erro_identidade_cpf_milton_eduardo.md` | ✅ identificado e corrigido pelo próprio autor da análise; lição de processo registrada | — |
| ACT-027 | Saneamento final de escalas pós-migração (11 correções + 2 reversões) | 2026-06-29 | `v2_65_saneamento_final_escalas_jun2026.md` | ✅ todas confirmadas na tela da Secullum | — |
| ACT-028 | Mudança da Fase 5C para "aprovação por exceção" (v2.66) | 2026-07-01 | `v2_66_aprovacao_por_excecao_5c.md` | ✅ implementado; investigação de suposta trava de inativação concluiu que a trava não existia | ver DIR-001b |
| ACT-029 | Preservação do histórico de memória do projeto em `docs/historico/` | 2026-07-23 | commit `1027fc8` (branch `fix/recibos-outros-documentos`) | 🔍 concluído como commit, **nunca mesclado em `main`** — é o próprio objeto desta Etapa 2 | ver `SOURCES_AND_PROVENANCE.md` §2 |
| ACT-030 | Fallback de entrega de documento longo via HTML→PDF (Artifact não abria no ambiente do usuário) | data não especificada (anterior a 2026-07-12) | `artifact_nao_abre_usar_pdf.md` | ✅ adotado como prática confiável | Edge headless |

## Ações completadas nesta própria Etapa 2 (2026-08-21)

| ID | Ação | Evidência |
|---|---|---|
| ACT-031 | Publicação de `CENTRAL_COMMAND_MAGNATA_OS.md` (Etapa 1) | commit `ea95ab6`, branch `claude/magnata-central-command-0n0713` |
| ACT-032 | Leitura integral dos 30 arquivos de `docs/historico/` (branch `fix/recibos-outros-documentos`) | esta sessão |
| ACT-033 | Leitura de `MAGNATA_AI_ENGINEERING_POWERPACK_INVENTARIO.md`, `_ETAPA1.md`, `_ETAPA4_DIVERGENCIAS_REVISAO.md` (branch powerpack) | esta sessão |
| ACT-034 | Identificação da origem exata dos documentos fundacionais em `main` (commit `19445e9`) | `git show --stat 19445e9` |
| ACT-035 | Construção dos registros estruturados (`DECISIONS.md`, `DIRECTIVES.md`, `ACTIONS_COMPLETED.md`, `WORK_IN_PROGRESS.md`, `PENDING.md`, `ARCHITECTURE.md`, `SUPERSEDED_DECISIONS.md`, `SOURCES_AND_PROVENANCE.md`, `COBERTURA.md`) | este commit |
