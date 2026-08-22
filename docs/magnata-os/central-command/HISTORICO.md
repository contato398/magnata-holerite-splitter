# HISTORICO — memória operacional preservada (12/06 a 01/07/2026)

**Etapa 4 da Central Command, 2026-08-22.**

## Por que este arquivo existe em vez dos 31 originais

Os 31 documentos originais de `docs/historico/` **não puderam ser
copiados para a linha canônica**. Auditoria de LGPD desta etapa,
executada antes de qualquer cópia:

| Achado | Medida |
|---|---|
| Arquivos com **CPF real de funcionário** | **8** de 31 |
| CPFs pessoais distintos expostos | ~8 (mais 5 CNPJs, que não são dado pessoal) |
| Arquivos com **nome completo de funcionário real** | **29** de 31 |
| Arquivos totalmente livres de dado pessoal | **2** — `magnata_os_arquiteto_chefe.md`, `padrao_deploy_render_confirmar_versao.md` |
| Pior caso num único arquivo | 51 candidatos a nome de pessoa |

`CLAUDE.md` §6 é literal: *"Dado pessoal (CPF, nome de funcionário real,
holerite real) segue a LGPD: nunca em teste, nunca em commit, nunca em
log, nunca em documento de exemplo."* E §12-I: a autonomia operacional
**nunca** autoriza o que §6 veda.

Mascaramento automático em massa foi avaliado e **rejeitado**: com 29
arquivos e até 51 nomes num só, um único nome escapando viraria violação
permanente na linha canônica do projeto. O risco de errar é maior que o
ganho de ter o texto bruto.

**Solução adotada:** preservar o **conhecimento** — que é o que tem
valor — de forma verificadamente livre de dado pessoal, com proveniência
exata para cada registro. A lição de cada documento sobrevive aqui; a
identidade de quem apareceu nele, não.

⚠️ **Consequência declarada, não escondida:** o **texto integral** dos 29
arquivos com PII continua existindo apenas em
`origin/fix/recibos-outros-documentos`. Este arquivo preserva a lição,
não o detalhe bruto. Desidentificar os originais é um trabalho próprio,
que precisa de decisão humana — ver §4.

---

## 1. Proveniência

| Campo | Valor |
|---|---|
| Branch | `origin/fix/recibos-outros-documentos` |
| Commit | `1027fc8a0c774de88715e6fecc447fc3ae1a94f4` |
| Data | 2026-07-23 22:51:18 −0300 |
| Mensagem | `docs: preserva historico de memoria do projeto (12/06 a 22/07/2026)` |
| Arquivos | 31 (30 registros + `MEMORY.md`) |
| Posição | 10 commits à frente, **106 atrás** de `main` |

⚠️ **Imprecisão do próprio commit, registrada:** o título diz "12/06 a
22/07/2026", mas o conteúdo real para em **01/07/2026**. O intervalo
01/07–20/07 não está aqui — está nas mensagens de commit de `main`
(~35 commits, `v2.67` a `v3.17`), conforme mestre §0-B.5.

---

## 2. Os 30 registros — lição preservada, identidade removida

`ORIGEM HISTÓRICA → LIÇÃO CANÔNICA → STATUS`

### 2.1 Plataforma e processo de trabalho

| Origem (blob) | Lição preservada | Status |
|---|---|---|
| `repo_producao_caminho_oficial.md` `4d74a17dbec1` | Produção é o clone Git ligado ao Render — **nunca** uma cópia solta em pasta de downloads. Sempre editar e commitar no caminho oficial | ✅ Vigente |
| `padrao_deploy_render_confirmar_versao.md` `2ee042cd1607` | Sempre incrementar a versão em `/health` e **confirmar por requisição real** antes de declarar deploy concluído | ✅ Vigente — **arquivo livre de PII** |
| `magnata_os_arquiteto_chefe.md` `d5e972607433` | Diretiva da Direção de **2026-07-22**: avaliar tudo contra a arquitetura do Magnata OS antes de implementar. É a origem do papel de arquiteto-chefe | ✅ Vigente — **arquivo livre de PII**. Ver `DIRECTIVES.md` |
| `artifact_nao_abre_usar_pdf.md` `28996177005b` | Limitação de ambiente: gerar PDF direto e verificar programaticamente em vez de depender de visualização interativa | 🟡 Específico da época |

### 2.2 Identidade, cadastro e qualidade de base

| Origem (blob) | Lição preservada | Status |
|---|---|---|
| `v2_64_erro_identidade_cpf_...md` `0065b18a8500` | **Erro real:** dois colaboradores distintos foram confundidos por várias mensagens. **Lição: sempre confirmar o nome devolvido pela API, nunca só o identificador que se acredita ter.** | ✅ **Vigente e crítica** — virou regra de contrato: *nome não é identificador confiável* |
| `faxina_base_funcionarios_jun2026.md` `35ac8918491e` | Faxina de 15/06: base de 182 → 149 linhas. Regras adotadas: manter quem tem Ativo + WhatsApp; deduplicar por CPF; afastado volta a Ativo. Em duplicata, prevalece o registro cujo CPF bate com a folha | ✅ Vigente |
| `fase5c_pre_cadastro_funcionarios.md` `bd1bd2e230d4` | Contrato processado cria pré-cadastro com Status "Ativo" — **decisão deliberada**, não efeito colateral | ❌ **Superado** por `v2_66` (passa a "Validação Pendente") |
| `v2_66_aprovacao_por_excecao_5c.md` `ea3063011037` | Contrato cria cadastro imediato como **"Validação Pendente"**, destravando a fila. **Lição de método: verificar a causa real antes de "remover uma trava" — a trava alegada pode não existir.** Dry-run pegou 3 duplicatas por CPF ausente/sujo; 53 de 70 contratos ilegíveis | ✅ Vigente — supera `fase5c` |
| `automacao_cadastro_holerite_sync_new_employees.md` `79bd42d90d2c` | Cadastro automático lê a tabela de Holerites, sem pasta local. PIS não existe no modelo. **Nunca executado de verdade** | 🚫 Planejado, não executado |

### 2.3 Ponto / Secullum

| Origem (blob) | Lição preservada | Status |
|---|---|---|
| `v2_49_secullum_ponto.md` `beffd3bb7a5c` | Integração de ponto: rate limit 429 exige *throttle*; 3 travas conhecidas (só faltas, virada 12x36, troca de plantão, batida ímpar) | ✅ Vigente |
| `classificador_secullum_v2_26.md` `79c035ff9de7` | Cartão de ponto caía em "Outro" por regex de nome. **Lição: classificar por CONTEÚDO, nunca por nome de arquivo** | ✅ **Vigente e generalizável** |
| `ponto_status_inativos_mes.md` `ed2e6e884667` | Cruzar cartão de ponto com Status: quem trabalha volta a Ativo; desligado no mês recebe só o mês e volta a Inativo | ✅ Vigente |
| `v2_53_folga_bonus_assiduidade.md` `036fd34df608` | Campo de descrição de horário **não é confiável** (3 achados) — usar atrasos/adiantamentos nativos. Folga trabalhada cruzada é praticamente indetectável (0 pareamentos reais) | ✅ Vigente |
| `v2_55_gravacao_real_jun2026.md` `8a332f8fe2b3` | 1ª gravação real: intervalo por posto/função, Art. 71 CLT em turno solo, saldo de plantões. **566 alertas gravados, 49 de 78 bônus deferidos** | ✅ Marco histórico |
| `v2_60_saneamento_secullum_jun2026.md` `64434c44b4aa` | **Achado de API:** o POST usa schema próprio (camelCase, descrições) — **não** os identificadores devolvidos pelo GET. 5 de 20 criados; 13 bloqueados por limite de plano | ✅ **Vigente** — armadilha de integração |
| `v2_61_diagnostico_inconsistencia_escala.md` `0a3a1abadc77` | 40 de 85 divergentes, mas **31 tinham paridade invertida na mesma direção** → achado **sistêmico de convenção**, não 31 bugs. **Lição de método: quando o erro é 100% na mesma direção, a causa é convenção, não incidente** | ✅ **Vigente e generalizável** |
| `v2_62_estabilizacao_secullum...md` `f3600a7ea254` | 32 migrados pela interface (API não suportava). **Bug de virada de dia instável: dados mudam entre consultas consecutivas** — não tratar como cacheável. Zero-batida = onboarding, não risco | ⚠️ **Bug ainda em aberto** |
| `v2_65_saneamento_final_escalas_jun2026.md` `aade9e5a5d1f` | 11 corrigidos, 2 revertidos para horário com intervalo; posto grande mantido na exceção, posto pequeno removido | ✅ Vigente |
| `cronicos_relatorio_postos_jun2026.md` `5dc371606d06` | **14 colaboradores concentram 58,7% dos alertas**; 4 postos com 2–3 crônicos cada. Decisão de agregação **pendente** | ⚠️ Decisão pendente |

### 2.4 Documentos, holerite e competência

| Origem (blob) | Lição preservada | Status |
|---|---|---|
| `holerites_correcao_maio2026.md` `459fc212ed1b` | Correção de valores com `dry_run`/`limit`, 78 atualizados. Cuidados registrados para os meses seguintes | ✅ Vigente |
| `reprocesso_direcionado_holerites.md` `f0d637670519` | O processamento casa por CPF e **não deduplica** — corrigir o CPF e reprocessar só as páginas faltantes; deduplicar o mês por data de criação | ✅ Vigente |
| `v2_27_ponto_master_splitter.md` `317a93753870` | Arquivo mestre de cartão de ponto vai pela rota de fatiamento por CPF, **nunca** pela fila — a fila é para arquivo individual | ✅ Vigente |
| `v2_48_processamento_backlog_holerites.md` `42fd03188cef` | Competência por extenso, com guarda. 248 holerites arquivados na competência certa (~22 competências), 111 sinalizados. **Render free devolve 502 sob carga → lotes pequenos com retry** | ✅ Vigente |
| `auditoria_integridade_arquivos_jun2026.md` `f02c923b309a` | 5.109 arquivos, só 2 sem anexo físico. **Usar filtro de vazio em vez de varrer tudo.** O risco real não é perda — é documento travado em "Processando" | ✅ **Vigente** |
| `auditoria_prestacao_contas_jun2026.md` `c678d1b21391` | **Achado central: reprocessamentos automáticos ignoraram uma exceção de competência em 4 frentes distintas.** Os envios manuais estavam corretos — **a automação regrediu o que a mão tinha acertado** | ✅ **Vigente e grave** |

### 2.5 Distribuição, e-mail e assinatura

| Origem (blob) | Lição preservada | Status |
|---|---|---|
| `v2_25_envio_combinado.md` `45b771f19afe` | Holerite + Ponto na **mesma** mensagem de WhatsApp. Chaves só em variável de ambiente | ✅ **Vigente** — é o ancestral direto do pacote atômico `HOLERITE_FOLHA_PONTO` |
| `v2_29_distribuicao_email.md` `13e7ce1e0f10` | Fatiador por cliente **seccionado por tomador**: excluir a própria empresa do índice (senão "rouba" páginas), *carry-forward* por seção, e tomador desconhecido **quebra** o carry-forward em vez de grudar no anterior. Resolve o caso "SEM CLIENTE". Match por nome completo — filial não casa | ✅ **Vigente** — algoritmo detalhado |
| `distribuicao_mensal_documentos_arquitetura.md` `1c3fc8882696` | Diretriz: colaborador por WhatsApp, cliente por e-mail | ✅ Virou realidade |
| `instituto_nefrologia_docs_maio.md` `ac770d873171` | Cliente novo recebe os próprios documentos; caso com pendência de re-fatiar e e-mail faltando | 🔍 Fechamento não confirmado |
| `automacao_dp_email_assinatura_v2_36_a_v2_41.md` `58333ede1369` | Captura de Admissão/Rescisão/EPI por script de e-mail; **Assinatura Nativa por WhatsApp com evidências de IP e CPF, custo zero** | ✅ **Vigente** — base do fluxo de assinatura atual |

---

## 3. O que estes registros provam sobre o sistema de hoje

Três regras vivas em produção **nasceram aqui** e só agora ganham
registro canônico:

1. **Nome não é identificador** (`v2_64`) → hoje é regra de contrato em
   `MAGNATA_OS_CONTRATOS.md` §16 e `MAGNATA_OS_ENTIDADES.md` §8.
2. **Envio combinado numa mensagem só** (`v2_25`) → hoje é o pacote
   atômico `HOLERITE_FOLHA_PONTO`, com decisão própria em
   `docs/decisoes/pacote-holerite-folha-ponto.md`.
3. **Assinatura nativa com evidência de IP/CPF** (`v2_36-2.41`) → hoje é
   o fluxo que 100+ colaboradores usam.

E um alerta que **continua valendo**: `auditoria_prestacao_contas` mostra
automação regredindo correção manual por ignorar uma exceção de
competência. É exatamente a classe de falha que o pacote atômico e a
reconciliação de backlog tentam evitar hoje.

---

## 4. O que ainda depende da branch — e o gate

**Depende exclusivamente de `origin/fix/recibos-outros-documentos`:** o
texto integral dos 29 arquivos com dado pessoal — números exatos,
identificadores de registro, tabelas nominais, passo a passo de cada
saneamento.

**O que NÃO depende mais:** a lição, a decisão e a proveniência de todos
os 30 registros — está nesta página, versionada e livre de PII.

**Gate humano — desidentificação dos originais.** Se você quiser o texto
bruto preservado, o caminho é um trabalho próprio: revisar arquivo por
arquivo, substituir nome por rótulo estável e remover CPF, com
conferência humana. **Não é automatizável com segurança** nesta escala, e
não é decisão minha — envolve o dado pessoal dos seus funcionários.

**Enquanto isso não acontece: não apagar a branch.** Ela deixou de ser a
única cópia do *conhecimento*, mas continua sendo a única cópia do
*registro bruto*.
