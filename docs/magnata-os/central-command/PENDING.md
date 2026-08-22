# PENDING — Magnata OS

Pendências e problemas conhecidos extraídos das fontes auditadas.
**Aviso geral, válido para todo item abaixo com data anterior a
2026-08-21:** nenhum destes números/estados foi reconfirmado contra
Airtable/Secullum/produção reais nesta auditoria (regra `CLAUDE.md`
§6) — cada um está marcado 🔍 pela própria natureza de "não
reconfirmável a partir do repositório", mesmo quando o documento fonte
soava conclusivo.

Legenda: ⚠️ PENDENTE (aberta, ação clara) · 🔍 PRECISA SER VALIDADO
(pode já estar resolvida ou não — sem como saber daqui).

---

## Pendências ativas, de escopo técnico (Etapa 1 e 2 desta sessão)

- **PEN-001** ⚠️ 6 testes falhando em `main` hoje, em
  `test_pacote_assinatura_holerite_ponto.py` — causa raiz confirmada,
  correção pronta em `fix/status-funcionario-pii` (ver WIP-005).
- **PEN-002** 🔍 débito técnico do campo `Tipo de Documento`
  (Processar Arquivos, Airtable) contaminado com códigos de erro
  técnico do hotfix (`UPLOAD_FAILED`, `PDF_DOWNLOAD_FAILED` etc.),
  registrado em `ARQUITETURA_FASE_2_DECISAO_FINAL.md` (2026-07-20) como
  "não corrigir agora". Nenhum documento posterior encontrado confirma
  correção.
- **PEN-003** ⚠️ Reconciliação de `feat/magnata-os-claude-powerpack`
  com `main` (WIP-001) — a pendência estrutural mais importante desta
  auditoria.
- **PEN-004** 🔍 111 documentos sinalizados como pendência no
  processamento do backlog de 23/06/2026 (59 `funcionario_nao_encontrado`
  + 52 `competencia_nao_detectada`, dos quais 9 ambíguos nunca
  resolvidos) — `v2_48_processamento_backlog_holerites.md`. Estado
  atual desconhecido.
- **PEN-005** 🔍 ~1.300 documentos no backlog de 15/06/2026 travados em
  Status="Processando" (nunca classificados/distribuídos) — citado em
  `auditoria_integridade_arquivos_jun2026.md` e
  `automacao_dp_email_assinatura_v2_36_a_v2_41.md` como pendência fora
  de escopo, "precisa de investigação dedicada". Nenhum documento
  posterior confirma resolução.
- **PEN-006** 🔍 13 colaboradores bloqueados de sincronizar com a
  Secullum por limite de plano (85 ativos) — depende de DIR-008
  (aumento de plano), cuja execução não foi confirmada.
- **PEN-007** ⚠️ Achado sistêmico de paridade PAR/ÍMPAR invertida (31
  pessoas) na Secullum — `v2_61_diagnostico_inconsistencia_escala.md`
  registra explicitamente "confirmar primeiro com quem configura as
  escalas o que o rótulo de fato representa", nunca feito segundo os
  documentos disponíveis.
- **PEN-008** 🔍 FGTS Digital de Maio/2026 do Instituto de Nefrologia
  nunca gerado (cliente ficou de fora do fatiamento original) —
  `instituto_nefrologia_docs_maio.md`.
- **PEN-009** 🔍 Estratégia de agregação/supressão para os 14
  colaboradores crônicos (58,7% dos alertas de ponto de Junho/2026)
  nunca decidida — sessão foi pausada antes da decisão
  (`cronicos_relatorio_postos_jun2026.md`).
- **PEN-010** 🔍 Pendências residuais do pacote mensal por cliente
  (v2.29-2.31): falta ligar Contratações/Rescisões/Férias e
  Comprovantes de pagamento ao e-mail automático; vários IDs de
  broadcast (certidões) marcados "PDF pendente upload manual" no
  próprio documento.
- **PEN-011** ⚠️ ADR-001 (nomenclatura Documento vs. Item de Ingestão)
  nunca aprovada formalmente — ver DEC-002.
- **PEN-012** ⚠️ ADR de fiação HTTP do Módulo 01 nunca aprovada — ver
  DEC-008/WIP-003.
- **PEN-013** ⚠️ 3 decisões `PENDENTE` em `MAGNATA_OS_DECISOES_ENTIDADES.md`
  (`DEC-ENT-010/011/012`) — documento só existe na branch powerpack,
  não lido em detalhe nesta etapa (ver `SOURCES_AND_PROVENANCE.md`).
  Aguardando resposta da Direção desde pelo menos 2026-07-30.
- **PEN-014** 🔍 `RELATORIO_SCHEMA_AIRTABLE_COMPLETO.md` — nunca
  versionado, existência atual desconhecida (ver
  `SOURCES_AND_PROVENANCE.md` §7). Risco de perda declarado desde
  2026-07-30, nunca mitigado dentro do alcance desta auditoria.
- **PEN-015** ⚠️ `DEC-004` (`DECISIONS.md`) — falta confirmar
  formalmente que a resolução dos 3 bloqueadores da Etapa 4 do
  Powerpack (módulo Segurança, camadas, autonomia da Fase 1) foi
  deliberada e não uma reescrita não registrada.
- **PEN-016** ⚠️ Regra operacional DIR-010 (caminho oficial de
  produção) precisa de reafirmação adaptada a ambientes de execução em
  nuvem/efêmeros — a instrução literal está desatualizada, o princípio
  não.

## Pendências de arquitetura já conhecidas (herdadas da Etapa 1, repetidas aqui por completude)

- **PEN-017** ⚠️ Postgres declarado em `render.yaml`, nunca provisionado.
- **PEN-018** 🚫 Ativação real do lote de importação de Julho/2026
  (handoff pronto, execução pendente de gate humano de infraestrutura).
- **PEN-019** ⚠️ Branches órfãs com trabalho pronto ou quase pronto —
  ver `WORK_IN_PROGRESS.md`.

## Observação sobre confiabilidade destes números

Praticamente toda pendência quantitativa acima (contagens de
documentos, colaboradores, registros) tem 30 a 60 dias de idade em
relação à data desta auditoria (2026-08-21). Documentos operacionais
posteriores (Agosto/2026, `docs/decisoes/*`, branches `fix/*` mais
recentes) tratam de assuntos diferentes e não mencionam revisitar essas
pendências especificamente — o que **não prova** que foram resolvidas,
só que esta auditoria não encontrou evidência nem de resolução nem de
persistência. Tratar cada uma como aberta até confirmação explícita,
não como presumivelmente resolvida pelo tempo decorrido.
