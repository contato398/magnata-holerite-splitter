# DIRECTIVES — Magnata OS

Ordens explícitas da Direção/gerência da Magnata, extraídas das fontes
auditadas. Diferem de `DECISIONS.md` por serem instruções de negócio
("faça X", "a regra é Y a partir de agora"), não escolhas de arquitetura
de software — embora várias tenham disparado decisões técnicas.

Legenda: ✅ FUNCIONANDO/CONFIRMADO · 🟡 EM EVOLUÇÃO · ⚠️ PENDENTE ·
❌ DESCARTADO/SUPERADO · 🔍 PRECISA SER VALIDADO · 🚫 PLANEJADO MAS NÃO EXECUTADO

---

### DIR-001 — Pré-cadastro automático não deve ser etapa manual obrigatória
- **Categoria:** diretiva de automação/RH
- **Data/origem:** 2026-06-13
- **Fonte:** `docs/historico/fase5c_pre_cadastro_funcionarios.md`
- **Texto da diretiva:** máxima automação; revisão manual só em exceções (CPF inválido, nome suspeito, data inválida, duplicidade, divergência, baixa confiança, texto truncado) — não em todo contrato válido.
- **Status atual:** 🟡 EM EVOLUÇÃO. A versão v2.16 (época da diretiva) só tinha 3 saídas; a arquitetura de 4 ramos pedida pela diretiva nunca foi confirmada como implementada nesta auditoria. **Superada operacionalmente** por uma mudança posterior — ver DIR-001b abaixo e `SUPERSEDED_DECISIONS.md` SUP-001.
- **Evidência técnica:** `_processar_contrato_stub`/`_montar_campos_pre_cadastro` em `app.py` — não relidos linha a linha nesta auditoria
- **Implementada?** 🔍 parcialmente, precisa reconfirmação contra `app.py` atual
- **Testada?** `test_kit_admissao_identidade.py` cobre parte do fluxo de identidade, não necessariamente os 4 ramos originais
- **Em produção?** 🔍 sim, alguma versão está — qual exatamente não foi confirmado
- **Substituída por:** DIR-001b (v2.66, "aprovação por exceção")

### DIR-001b — Evolução: "aprovação por exceção" no cadastro (v2.66)
- **Categoria:** ajuste de diretiva anterior
- **Data/origem:** 2026-07-01
- **Fonte:** `docs/historico/v2_66_aprovacao_por_excecao_5c.md`
- **Texto:** contrato/admissão cria cadastro IMEDIATO com Status="Validação Pendente" em vez de reter o arquivo; inativação/ajuste manual fica com o humano.
- **Status atual:** ✅ FUNCIONANDO/CONFIRMADO à época (2026-07-01) — não reconfirmado nesta sessão contra o `app.py` atual (2026-08-21), mas nenhuma branch/commit encontrado que reverta isso
- **Evidência técnica:** `decidir_acao_documento`, handlers de admissão citados no documento
- **Implementada?** Sim, à época
- **Testada?** Dry-run de ~70 contratos citado no mesmo documento
- **Em produção?** 🔍 presumivelmente sim, não reconfirmado
- **Substituída?** Não, é a versão mais recente conhecida desta diretiva

### DIR-002 — Arquitetura de Distribuição Mensal de Documentos (2 fluxos)
- **Categoria:** diretiva de arquitetura de produto
- **Data/origem:** 2026-06-14
- **Fonte:** `docs/historico/distribuicao_mensal_documentos_arquitetura.md`
- **Texto:** todo documento tem destino Colaborador (WhatsApp individual) e/ou Cliente (pacote mensal por e-mail); Holerite e Folha de Ponto têm os dois destinos.
- **Status atual:** 🟡 EM EVOLUÇÃO — o fluxo Cliente/E-mail evoluiu bastante ao longo de 2026-06-15 a 2026-06-15 (v2.29 a v2.31, ver `ACTIONS_COMPLETED.md`), mas a modelagem explícita ("campo Destino(s)", "tabela Pacotes Mensais") citada como não-implementada no documento original não foi reconfirmada nesta auditoria.
- **Evidência técnica:** `_gerar_fila_envios_email`, `_gerar_fila_envios_combinado` em `app.py`
- **Implementada?** 🟡 parcialmente (o fluxo funciona, a modelagem de dados formal pedida talvez não)
- **Testada?** Parcial, via testes de fila de envio
- **Em produção?** Sim, o fluxo de distribuição em si está em produção
- **Substituída?** Não formalmente — mas o pacote atômico Holerite+Ponto (DEC-006, 2026-08-12) é uma evolução direta desta diretiva original

### DIR-003 — Papel de arquiteto-chefe do Magnata OS (origem fundacional)
- **Categoria:** diretiva fundacional — a mais importante encontrada nesta auditoria
- **Data/origem:** 2026-07-22
- **Fonte:** `docs/historico/magnata_os_arquiteto_chefe.md`
- **Texto:** a partir desta data, toda implementação nova deve ser avaliada contra a arquitetura formal do projeto antes de codar — motivada por `app.py` ter chegado a 10.410 linhas / 182 funções / 37 rotas por acúmulo orgânico de features pontuais.
- **Status atual:** ✅ FUNCIONANDO/CONFIRMADO — é o princípio que originou `MAGNATA_OS_MANIFESTO.md` e toda a árvore de documentos fundacionais, vigente até hoje via `CLAUDE.md`
- **Evidência técnica:** `MAGNATA_OS_MANIFESTO.md`, `CLAUDE.md` (`main`)
- **Implementada?** Sim
- **Testada?** N/A
- **Em produção?** É o princípio operante da própria engenharia, não uma funcionalidade
- **Substituída?** Não — é a diretiva-mãe de tudo que veio depois

### DIR-004 — Regras finais do motor de auditoria de ponto (Secullum) v2.55
- **Categoria:** diretiva de regra de negócio (RH/Ponto)
- **Data/origem:** 2026-06-25
- **Fonte:** `docs/historico/v2_55_gravacao_real_jun2026.md`
- **Texto:** intervalo por posto+função (5 postos de exceção nomeados por ID), saldo de plantões para classificar Troca Informal x Cobertura de Emergência.
- **Status atual:** ✅ FUNCIONANDO/CONFIRMADO à época — primeira gravação real autorizada explicitamente pela diretoria em 2026-06-25; refinada em DIR-005/DIR-006 e `v2_65_saneamento_final_escalas_jun2026.md` (postos de exceção ajustados manualmente pela diretoria depois)
- **Evidência técnica:** `src/services/secullum_ponto.py`
- **Implementada?** Sim
- **Testada?** Dry-run + gravação real confirmados no documento
- **Em produção?** 🔍 sim à época; estado atual não reconfirmado
- **Substituída?** Refinada por ajustes pontuais posteriores (não uma substituição completa)

### DIR-005 — Correção do período de apuração oficial da folha (28→28)
- **Categoria:** diretiva de regra de negócio (fechamento de folha)
- **Data/origem:** 2026-06-25 (mesmo dia de DIR-004, correção no mesmo ciclo)
- **Fonte:** `docs/historico/v2_55_gravacao_real_jun2026.md` (seção "v2.56")
- **Texto:** a folha da Magnata fecha do dia 28 do mês anterior ao dia 28 do mês de competência — não o mês comercial 01-30.
- **Status atual:** ✅ FUNCIONANDO/CONFIRMADO à época — `periodo_folha(ano, mes)` implementada no mesmo ciclo
- **Evidência técnica:** função `periodo_folha` citada no documento
- **Implementada?** Sim
- **Testada?** Reprocesso real citado (88 funcionários, 0 erros)
- **Em produção?** 🔍 sim à época, não reconfirmado hoje
- **Substituída?** Não

### DIR-006 — Saneamento de colaboradores "invisíveis" na Secullum
- **Categoria:** diretiva operacional (RH/Cadastro)
- **Data/origem:** 2026-06-27 ("ordem da diretoria" — texto explícito do documento)
- **Fonte:** `docs/historico/v2_60_saneamento_secullum_jun2026.md`
- **Texto:** sanear em massa os 20 colaboradores Ativos no Airtable sem registro na Secullum.
- **Status atual:** ⚠️ PENDENTE — 5 concluídos com sucesso, 13 bloqueados por limite de plano contratual da Secullum (85 ativos), aguardando decisão da diretoria (upgrade de plano ou desativação de inativos). Ver DIR-009.
- **Evidência técnica:** documento cita os 13 CPFs/nomes bloqueados
- **Implementada?** Parcial (5/20)
- **Testada?** Sim, confirmações individuais citadas
- **Em produção?** Sim, os 5 concluídos
- **Substituída?** Não — segue como pendência aberta até confirmação de DIR-009

### DIR-007 — Migração de 32 colaboradores "Turno Solo" para horários "SEM INTERVALO"
- **Categoria:** diretiva operacional (RH/Ponto)
- **Data/origem:** 2026-06-28
- **Fonte:** `docs/historico/v2_62_estabilizacao_secullum_e_onboarding_zero_batida.md`
- **Texto:** diretoria cria manualmente 10 horários novos na Secullum e migra 32 colaboradores de Turno Solo.
- **Status atual:** ✅ FUNCIONANDO/CONFIRMADO à época — migração 100% completa confirmada em `v2_65_saneamento_final_escalas_jun2026.md` (2026-06-29), com 2 reversões pontuais (Lucídio, Denilson tinham intervalo de verdade)
- **Evidência técnica:** `EXCEPTION_POSTO_IDS` em `secullum_ponto.py`
- **Implementada?** Sim
- **Testada?** Confirmado na tela da Secullum, não só no banco
- **Em produção?** Sim, à época
- **Substituída?** Refinada por `v2_65` (2 reversões)

### DIR-008 — Aumento do plano Secullum (remoção do limite de 85 ativos)
- **Categoria:** diretiva de contratação/orçamento (ação externa, sistema terceiro)
- **Data/origem:** planejada para 2026-06-29 ("a partir de amanhã a diretoria aumenta o plano da Secullum")
- **Fonte:** `docs/historico/v2_62_estabilizacao_secullum_e_onboarding_zero_batida.md`
- **Status atual:** 🔍 PRECISA SER VALIDADO — é uma ação em serviço externo (contrato com a Secullum), fora do alcance de qualquer auditoria de repositório. Nenhum documento posterior encontrado nesta sessão confirma execução.
- **Evidência técnica:** nenhuma (é uma intenção declarada, não uma ação registrada como concluída)
- **Implementada?** 🔍 desconhecido
- **Testada?** N/A
- **Em produção?** 🔍 desconhecido
- **Substituída?** Não

### DIR-009 — Regra permanente de deploy: sempre confirmar versão via `/health`
- **Categoria:** diretiva de processo de engenharia
- **Data/origem:** anterior a 2026-06-15 (registrada como lição aprendida)
- **Fonte:** `docs/historico/padrao_deploy_render_confirmar_versao.md`
- **Texto:** todo commit que vá para produção deve bumpar a string de versão em `/health` no mesmo commit e confirmar via `curl` antes de declarar deploy concluído.
- **Status atual:** ✅ FUNCIONANDO/CONFIRMADO como prática — consistente com o padrão observado nos commits de fix mais recentes (Etapa 1), embora não reverificado individualmente contra `/health` nesta auditoria (nenhum acesso a produção)
- **Evidência técnica:** rota `/health` em `app.py`
- **Implementada?** Sim, como prática de processo
- **Testada?** N/A
- **Em produção?** É uma regra de processo, não uma funcionalidade
- **Substituída?** Não

### DIR-010 — Caminho oficial do repositório de produção (contextual, desatualizada)
- **Categoria:** diretiva operacional de ambiente
- **Data/origem:** 2026-06-15 (implícito, referenciado por sessões posteriores)
- **Fonte:** `docs/historico/repo_producao_caminho_oficial.md`
- **Texto:** trabalhar sempre em `C:\Users\Lenovo\magnata-holerite-splitter`, nunca em `Downloads` (que tinha cópias antigas soltas).
- **Status atual:** 🔍 PRECISA SER VALIDADO/reinterpretada — o pressuposto de ambiente (máquina Windows fixa do usuário) não é mais universal: sessões como esta rodam em containers remotos efêmeros clonados direto do GitHub. **O princípio subjacente continua válido** (nunca trabalhar contra uma cópia desatualizada/fora do controle de versão) mas a instrução literal (caminho `C:\Users\Lenovo\...`) não se aplica a todo ambiente de execução atual.
- **Evidência técnica:** N/A
- **Implementada?** Sim, como prática histórica
- **Testada?** N/A
- **Em produção?** N/A
- **Substituída?** Não formalmente, mas precisa de uma reafirmação do princípio (não do caminho literal) para ambientes cloud — sugerido como item de `PENDING.md`
