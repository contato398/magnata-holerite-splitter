#!/bin/bash
# Magnata OS — Padrões Canônicos de Governança
# Fonte única de verdade para validação de regras
# Importado por: .githooks/pre-commit, scripts/ci/validate_governance.sh

# ============================================================================
# BRANCHES AUTORIZADAS — Trabalho de desenvolvimento do Magnata OS
# ============================================================================
# Enumeração fechada para branches "feat/..." — toda branch feat/ nova
# precisa ser adicionada aqui explicitamente, um nome exato por vez. "main"
# não é branch de desenvolvimento local; eventos de CI sobre main
# (pull_request, push) já são tratados à parte, sem depender desta lista.
#
# Exceção restrita, registrada explicitamente (não em silêncio): branches
# "fix/..." usam um padrão único, não uma lista de nomes exatos, porque
# correções pontuais (como fix/remetente-dp-email-intake) são mais
# numerosas e de vida mais curta que as branches feat/ de módulo. O padrão
# abaixo é deliberadamente restrito — não é "^fix/.*$" — e não abre nenhum
# outro prefixo (feat/, chore/, docs/, test/ continuam exigindo entrada
# exata nesta lista, como antes).

AUTHORIZED_BRANCHES=(
  "^feat/magnata-os-claude-powerpack$"
  "^feat/magnata-os-etapa6-governanca$"
  "^feat/magnata-os-etapa6-estabilizacao$"
  "^fix/[a-z0-9][a-z0-9-]*$"
  "^claude/macro-6a-[a-z0-9-]*$"
)

# Verifica se uma branch está na lista de branches de trabalho autorizadas
is_authorized_branch() {
  local branch="$1"
  for pattern in "${AUTHORIZED_BRANCHES[@]}"; do
    if [[ "$branch" =~ $pattern ]]; then
      return 0
    fi
  done
  return 1
}

# ============================================================================
# ARQUIVOS PROTEGIDOS — Não podem ser alterados sem autorização explícita
# ============================================================================

PROTECTED_FILES=(
  "^app\.py$"
  "^magnata_os/documental/modulo01/migrations/"
  "^frontend/CLAUDE\.md$"
  "^frontend/assets/brand/"
)

# ============================================================================
# PADRÕES DE SEGREDO — segredo real vs. identificador/header/placeholder
# ============================================================================
# A versão anterior (SECRET_PATTERNS, bare grep -qi por arquivo inteiro)
# bloqueava qualquer ocorrência do NOME de uma variável/header sensível
# (ex.: "apiKey", "'X-API-KEY'", "DATABASE_URL" como identificador), mesmo
# sem nenhum valor literal de segredo presente — falso positivo confirmado
# em apps_script_email_intake.gs (branch fix/remetente-dp-email-intake,
# 2026-08-03): a variável `apiKey` e o header `'X-API-KEY'` já existiam no
# código original, sem nenhuma credencial real.
#
# Duas camadas, ambas operando só sobre CONTEÚDO STAGED e só linhas
# ADICIONADAS (ver linha_contem_segredo_real, arquivo_staged_tem_segredo,
# usadas por .githooks/pre-commit e por scripts/ci/validate_governance.sh
# — mesma fonte, para hook local e CI nunca divergirem):
#
#   1. SECRET_PATTERNS_ABSOLUTOS — formato inequívoco (chave privada,
#      formato reconhecível de credencial de provedor, Bearer com valor,
#      URL com credencial embutida). Qualquer ocorrência já basta — não
#      precisa de contexto de atribuição, o formato em si é a prova.
#
#   2. SECRET_CONTEXT_KEYWORDS — nomes sensíveis (api_key, token,
#      password, secret, database_url, airtable_key etc. — inclui os
#      mesmos termos que já estavam no SECRET_PATTERNS anterior) só
#      bloqueiam quando atribuídos a um valor LITERAL (aspas ou token
#      solto até o fim da linha) que não é vazio nem um placeholder
#      conhecido (ver SECRET_PLACEHOLDER_REGEX). Nome de variável, header,
#      chamada a getenv/getProperty, ou referência a outra variável nunca
#      batem, porque o valor não é uma string literal.

SECRET_PATTERNS_ABSOLUTOS=(
  "BEGIN RSA PRIVATE KEY"
  "BEGIN PRIVATE KEY"
  "BEGIN OPENSSH PRIVATE KEY"
  "-----BEGIN"
  "AKIA[0-9A-Z]{16}"
  "gh[posur]_[A-Za-z0-9]{20,}"
  "Bearer[[:space:]]+[A-Za-z0-9._-]{8,}"
  "://[^/[:space:]:]+:[^/[:space:]@]+@"
)

SECRET_CONTEXT_KEYWORDS='private[_-]?key|api[_-]?key|secret[_-]?key|access[_-]?key|access[_-]?token|client[_-]?secret|password|passwd|token|secret|credentials|aws[_-]?secret|database[_-]?url|airtable[_-]?key|sendgrid[_-]?api|render[_-]?api|stripe[_-]?secret|jwt[_-]?secret|github[_-]?token'

# Placeholder/valor vazio — nunca é segredo real, mesmo em atribuição
# literal. Âncorado (^...$) contra o VALOR capturado inteiro, não contra um
# prefixo — cada alternativa casa o valor INTEIRO (exceto as com sufixo
# [a-z0-9_-]* explícito, únicas com continuação livre, por já terem um
# marcador de placeholder inequívoco no início). Nunca usar alternativa
# vazia solta aqui — "()*"-like construções combinadas com sufixo genérico
# greedy classificariam QUALQUER valor alfanumérico como placeholder
# (armadilha real encontrada e corrigida durante os testes desta correção).
SECRET_PLACEHOLDER_REGEX='^$|^(changeme|change_me|xxx+|placeholder|todo|fixme|exemplo|example|dummy|fake|test|sample)$|^(cole[_-]?aqui|your[_-][a-z_]*key)[a-z0-9_-]*$|^<[^>]*>$|^\*{3,}$|^\.{3,}$'

# Verifica se um VALOR já capturado (sem aspas) é placeholder/vazio.
# Retorno: 0 = é placeholder (seguro); 1 = não é (segue candidato a segredo).
_valor_e_placeholder() {
  local valor="$1"
  local nocase_ja_ligado=0
  shopt -q nocasematch && nocase_ja_ligado=1
  shopt -s nocasematch
  local resultado=1
  if [[ "$valor" =~ $SECRET_PLACEHOLDER_REGEX ]]; then
    resultado=0
  fi
  [ $nocase_ja_ligado -eq 0 ] && shopt -u nocasematch
  return $resultado
}

# Verifica se UMA linha de conteúdo (sem prefixo "+"/"-" de diff) contém um
# segredo real. Retorno: 0 = segredo real encontrado; 1 = linha limpa
# (identificador, header, placeholder, ou valor vazio).
linha_contem_segredo_real() {
  local linha="$1"
  local nocase_ja_ligado=0
  shopt -q nocasematch && nocase_ja_ligado=1
  shopt -s nocasematch

  local achou=1

  for pat in "${SECRET_PATTERNS_ABSOLUTOS[@]}"; do
    if [[ "$linha" =~ $pat ]]; then
      achou=0
      break
    fi
  done

  # Valor entre aspas: '"'"'chave'"'"' = '"'"'valor'"'"' ou "chave": "valor"
  if [ $achou -ne 0 ]; then
    local regex_aspas="['\"]?(${SECRET_CONTEXT_KEYWORDS})['\"]?[[:space:]]*[:=][[:space:]]*['\"]([^'\"]*)['\"]"
    if [[ "$linha" =~ $regex_aspas ]]; then
      if ! _valor_e_placeholder "${BASH_REMATCH[2]}"; then
        achou=0
      fi
    fi
  fi

  # Valor sem aspas até o fim da linha (estilo .env / shell): CHAVE=valor —
  # exige fim de linha logo após o token, para não capturar o início de uma
  # chamada de função/expressão (ex.: "apiKey = Foo.getBar().getX('K');"
  # não termina em token solto, continua com ".getBar()...").
  if [ $achou -ne 0 ]; then
    local regex_livre="['\"]?(${SECRET_CONTEXT_KEYWORDS})['\"]?[[:space:]]*[:=][[:space:]]*([A-Za-z0-9_+/=-]+)[[:space:]]*;?[[:space:]]*\$"
    if [[ "$linha" =~ $regex_livre ]]; then
      local valor_livre="${BASH_REMATCH[2]}"
      # Atribuição variável-a-variável não contém literal de segredo.
      if [[ "$valor_livre" =~ ^(${SECRET_CONTEXT_KEYWORDS})$ ]]; then
        :
      elif ! _valor_e_placeholder "$valor_livre"; then
        achou=0
      fi
    fi
  fi

  # Bug real encontrado e corrigido durante os testes desta correção:
  # faltava restaurar nocasematch aqui — sem isso, uma vez chamada esta
  # função (sempre, na Validação 4), nocasematch ficava ligado pelo resto
  # da execução do hook, tornando case-sensível em outras validações
  # (ex.: Validação 6/7, comparação de nome de arquivo) incorretamente
  # case-insensível — "Test_....py" passava a bater com "^test_" e com a
  # exceção nominal, quando não deveria.
  [ $nocase_ja_ligado -eq 0 ] && shopt -u nocasematch

  return $achou
}

# Escaneia um arquivo staged por segredo real — só conteúdo do índice
# (git diff --cached), só linhas adicionadas. Imprime achados mascarados
# (arquivo, linha, categoria — nunca o valor) em stdout.
# Retorno: 0 = achou segredo; 1 = arquivo limpo.
arquivo_staged_tem_segredo() {
  local arquivo="$1"
  local encontrou=1
  local linha_num=0

  while IFS= read -r linha_diff; do
    if [[ "$linha_diff" =~ ^@@[[:space:]]-[0-9]+(,[0-9]+)?[[:space:]]\+([0-9]+) ]]; then
      linha_num="${BASH_REMATCH[2]}"
      continue
    fi
    if [[ "$linha_diff" == "+++"* ]]; then
      continue
    fi
    if [[ "$linha_diff" == "+"* ]]; then
      local conteudo="${linha_diff:1}"
      if linha_contem_segredo_real "$conteudo"; then
        echo "  Arquivo: $arquivo"
        echo "  Linha: $linha_num"
        echo "  Categoria: valor literal em campo sensível (ou formato de credencial reconhecível)"
        encontrou=0
      fi
      linha_num=$((linha_num + 1))
    fi
  done < <(git diff --cached --unified=0 -- "$arquivo" 2>/dev/null)

  return $encontrou
}

# ============================================================================
# PADRÕES DOCUMENTAIS — Estruturas proibidas
# ============================================================================

# Gate 7: Segurança como 11º módulo funcional (proibido)
GATE_11_MODULE_PATTERNS=(
  "11º módulo"
  "módulo onze"
  "novo módulo.*Segurança"
  "módulo funcional.*adicional.*Segurança"
)

# Gate 8: Arquitetura de 9 camadas ou 6+3 (proibido)
GATE_9_LAYERS_PATTERNS=(
  "9 camadas"
  "nove camadas"
  "modelo 6\\+3"
  "seis.*mais.*três"
)

# Gate 9: Autonomia percentual abstrata (proibido)
GATE_AUTONOMY_PERCENT_PATTERNS=(
  "autonomia.*[0-9]+%"
  "[0-9]+%.*autônom"
  "nível de autonomia.*%"
)

# Gate 10: ADR silenciosa — renomeação sem referência (proibido)
GATE_ADR_SILENT_PATTERNS=(
  "Item de Ingestão.*renomeado.*Documento"
  "Documento substitui.*Item de Ingestão"
  "mudança de nomenclatura.*aprovada"
)

# ============================================================================
# DOCUMENTOS NORMATIVOS — Arquitetura-de-registro do Magnata OS
# ============================================================================
# Escopo EXCLUSIVO dos gates semânticos 7-10 (11º módulo, 9 camadas,
# autonomia %, ADR silenciosa). Enumeração fechada por caminho exato — não
# regex genérica — de propósito: documentação técnica de CI/hooks/testes
# (docs/magnata-os/MAGNATA_AI_*.md, .githooks/README.md) e relatórios de
# etapa (MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA*.md, pareceres, planos,
# validações) NÃO entram aqui — podem citar os padrões proibidos em prosa,
# ao descrever o próprio gate, sem que isso seja uma violação real.

NORMATIVE_DOC_PATTERNS=(
  "^MAGNATA_OS_MANIFESTO\.md$"
  "^MAGNATA_OS_ARQUITETURA\.md$"
  "^MAGNATA_OS_CONTRATOS\.md$"
  "^MAGNATA_OS_ESTADOS\.md$"
  "^MAGNATA_OS_EVENTOS\.md$"
  "^MAGNATA_OS_ENTIDADES\.md$"
  "^MAGNATA_OS_DECISOES_ENTIDADES\.md$"
  "^MAGNATA_OS_DOCUMENTAL_MODULO01\.md$"
  "^MAGNATA_OS_DOCUMENTAL_MODULO01_FASE2\.md$"
  "^MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3\.md$"
  "^MAGNATA_OS_DOCUMENTAL_MODULO01_FASE4\.md$"
  "^MAGNATA_OS_MODULO_01_INGESTAO\.md$"
  "^MAGNATA_OS_MODULO_01_DECISOES_IMPLEMENTACAO\.md$"
  "^MAGNATA_OS_MODULO_01_PLANO_TECNICO_FASES_0_1\.md$"
  "^MAGNATA_OS_MODULO_01_FASE_0_OBSERVABILIDADE\.md$"
  "^docs/magnata-os/MAGNATA_OS_CAPACIDADES\.md$"
  "^docs/magnata-os/MAGNATA_OS_MODULOS\.md$"
  "^docs/magnata-os/MAGNATA_OS_ROADMAP\.md$"
  "^docs/magnata-os/MAGNATA_OS_MATRIZ_ARQUITETURAL\.md$"
  "^docs/magnata-os/MAGNATA_OS_ADR_001_NOMENCLATURA_ITEM_INGESTAO_VS_DOCUMENTO\.md$"
)

# ============================================================================
# DOCUMENTOS OBRIGATÓRIOS — Devem estar presentes
# ============================================================================

REQUIRED_DOCS=(
  "MAGNATA_OS_MANIFESTO.md"
  "MAGNATA_OS_CAPACIDADES.md"
  "MAGNATA_OS_MODULOS.md"
  "MAGNATA_OS_ROADMAP.md"
  "MAGNATA_OS_MATRIZ_ARQUITETURAL.md"
)

# ============================================================================
# CLAUDE.md OBRIGATÓRIOS — 4 níveis de hierarquia
# ============================================================================

CLAUDE_HIERARCHY=(
  "CLAUDE.md"
  "frontend/CLAUDE.md"
  "magnata_os/CLAUDE.md"
  "magnata_os/documental/modulo01/migrations/CLAUDE.md"
)

# Verifica se um caminho é EXATAMENTE um dos 4 arquivos da hierarquia
# CLAUDE.md — comparação de igualdade de string contra CLAUDE_HIERARCHY,
# nunca por padrão/regex. É a única exceção documental reconhecida por
# PROTECTED_FILES e ALLOWED_PATHS (Validação 6 do pre-commit): libera
# exclusivamente estes 4 caminhos exatos, nunca um diretório inteiro nem
# qualquer outro CLAUDE.md fora desta lista.
is_claude_hierarchy_path() {
  local file="$1"
  local path
  for path in "${CLAUDE_HIERARCHY[@]}"; do
    if [[ "$file" == "$path" ]]; then
      return 0
    fi
  done
  return 1
}

# ============================================================================
# MODOS GIT — Permissões obrigatórias
# ============================================================================

# Executáveis (100755)
EXECUTABLE_FILES=(
  ".githooks/pre-commit"
  ".githooks/post-commit"
  ".githooks/pre-push"
  ".githooks/commit-msg"
  ".githooks/test-hooks.sh"
  "scripts/ci/validate_governance.sh"
  "scripts/ci/test_governance.sh"
)

# Não-executáveis (100644)
NON_EXECUTABLE_FILES=(
  ".github/workflows/magnata-governance.yml"
  ".magnata/patterns.sh"
  "MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA6.md"
  "docs/magnata-os/MAGNATA_AI_CI_GOVERNANCA.md"
)

# ============================================================================
# CAMINHOS PERMITIDOS — Escopo do CI
# ============================================================================

ALLOWED_PATHS=(
  "^\.github/workflows/"
  "^\.magnata/"
  "^\.githooks/"
  "^scripts/ci/"
  "^docs/magnata-os/"
  "^MAGNATA_AI_ENGINEERING_POWERPACK_ETAPA[0-9]+.*\.md$"
  "^MAGNATA_OS_.*\.md$"
  "^\.github/README\.md$"
  "^\.githooks/README\.md$"
  # Protocolo raiz do Codex. Exceção nominal exata: não libera outros
  # AGENTS.md em subdiretórios nem qualquer classe genérica de Markdown.
  "^AGENTS\.md$"
  # Exceção exata e restrita (decisão registrada, branch
  # fix/remetente-dp-email-intake, 2026-08-04) — só estes 4 caminhos
  # exatos, não um padrão genérico. Não libera nenhum outro .gs, .py, .js
  # ou docs/decisoes/* — cada um bate por igualdade de string completa via
  # âncora $ no fim.
  "^apps_script_email_intake\.gs$"
  "^docs/decisoes/remetentes-dp-fiscal\.md$"
  "^test_apps_script_email_intake_remetentes\.py$"
  "^test_interpretar_resposta_webhook\.js$"
  # Exceção exata e restrita (decisão registrada, branch
  # fix/competencia-documental-confiavel, 2026-08-11) — Macro 5,
  # competência documental confiável. Só estes 6 caminhos exatos, não um
  # padrão genérico — não libera "^magnata_os/" nem "^test_" de forma
  # ampla; qualquer outro arquivo em magnata_os/ (inclusive outro arquivo
  # do mesmo diretório importacao_lote/) ou outro test_*.py continua
  # bloqueado, cada um batido por igualdade de string completa via
  # âncora $ no fim.
  "^magnata_os/documental/importacao_lote/contratos\.py$"
  "^magnata_os/documental/importacao_lote/dominio\.py$"
  "^magnata_os/documental/importacao_lote/escritor\.py$"
  "^magnata_os/documental/importacao_lote/orquestrador\.py$"
  "^test_importacao_lote\.py$"
  "^test_importacao_lote_escrita\.py$"
  # Excecao exata e restrita (Document Resolution & Routing Shadow V1,
  # contratos puros) — somente o pacote, seus contratos e o teste nominal.
  # Nao libera magnata_os/classificacao/ nem test_*.py genericamente.
  "^magnata_os/classificacao/__init__\.py$"
  "^magnata_os/classificacao/contratos\.py$"
  "^test_magnata_os_classificacao_contratos\.py$"
  "^magnata_os/classificacao/prestacao_readiness\.py$"
  "^test_magnata_os_classificacao_prestacao_readiness\.py$"
  "^magnata_os/classificacao/inventario_prestacao\.py$"
  "^test_magnata_os_classificacao_inventario_prestacao\.py$"
  # Adapter Airtable shadow de inventario de extratos e seu teste nominal.
  "^magnata_os/documental/importacao_lote/adapters/airtable_inventario_prestacao\.py$"
  "^test_airtable_inventario_prestacao\.py$"
  # Politica pura e coordenador do readiness shadow da Prestacao de Contas.
  "^magnata_os/classificacao/politica_requisitos_prestacao\.py$"
  "^magnata_os/classificacao/prestacao_shadow\.py$"
  "^test_prestacao_shadow_e2e\.py$"
  "^scripts/prestacao_readiness_shadow_real\.py$"
  "^test_prestacao_readiness_shadow_real\.py$"
  "^magnata_os/documental/importacao_lote/adapters/airtable_leitura\.py$"
  "^magnata_os/classificacao/inventario_prestacao_resultados\.py$"
  "^test_magnata_os_classificacao_inventario_prestacao_resultados\.py$"
  "^magnata_os/classificacao/vinculos_prestacao\.py$"
  "^test_magnata_os_classificacao_vinculos_prestacao\.py$"
  "^magnata_os/documental/importacao_lote/adapters/airtable_vinculos_prestacao\.py$"
  "^test_airtable_vinculos_prestacao\.py$"
  # Classificação nominal e conservadora da Guia DCTFWeb/DARF no legado.
  "^test_classificacao_guia_dctfweb_darf\.py$"
  # Excecao exata e restrita (migração segura do classificador
  # documental do legado app.py TIPO_DOC_REGRAS, branch
  # fix/classificador-documental-legado-seguro) — somente o módulo novo
  # e seu teste nominal. Nao libera magnata_os/classificacao/ nem
  # test_*.py genericamente.
  "^magnata_os/classificacao/classificador_documental\.py$"
  "^test_classificador_documental_migracao\.py$"
  # Excecao exata e restrita (ponte shadow de roteamento documental,
  # branch fix/roteamento-documental-shadow) — somente o módulo novo
  # e seu teste nominal. Nao libera magnata_os/classificacao/ nem
  # test_*.py genericamente. Inclui tambem o modulo neutro de extracao
  # de texto de PDF, promovido de importacao_lote/orquestrador.py
  # (_extrair_texto_pdf, privada) para reuso sem duplicacao — nao libera
  # "^magnata_os/documental/" de forma ampla, so este caminho exato.
  "^magnata_os/classificacao/roteamento_documental\.py$"
  "^test_roteamento_documental_shadow\.py$"
  "^magnata_os/documental/extracao_texto\.py$"
  # Excecao exata e restrita (integracao shadow entre ingestao real do
  # lote e o roteamento documental, branch
  # fix/roteamento-shadow-integracao-lote) — somente estes 2 arquivos
  # existentes tocados (dtos_esteira.py ganha RoteamentoShadowDTO +
  # conversores; servico_lote.py chama decidir_roteamento no ponto
  # exato onde Documento ja existe e os bytes ainda estao em escopo) e
  # o teste de integracao nominal. Nao libera
  # "^magnata_os/documental/modulo01/" nem "^test_" de forma ampla.
  "^magnata_os/documental/modulo01/dtos_esteira\.py$"
  "^magnata_os/documental/modulo01/servico_lote\.py$"
  "^test_servico_lote_roteamento_shadow\.py$"
  # Excecao exata e restrita (gate controlado REGISTRO->CLASSIFICACAO,
  # branch fix/gate-classificacao-esteira) — modulo novo de politica pura
  # de transicao (nao depende de RoteamentoShadowDTO, so de
  # DecisaoRoteamentoDocumental), o metodo novo em
  # servico_avanco_esteira.py que compoe avancar_etapa/registrar_bloqueio
  # ja existentes, a chamada em servico_lote.py que reaproveita a MESMA
  # decisao ja calculada, e os 2 testes nominais. Nao libera
  # "^magnata_os/documental/modulo01/" nem "^test_" de forma ampla.
  "^magnata_os/documental/modulo01/politica_classificacao\.py$"
  "^magnata_os/documental/modulo01/servico_avanco_esteira\.py$"
  "^test_politica_classificacao\.py$"
  "^test_gate_classificacao_esteira\.py$"
  # Exceção exata e restrita (correção da incompatibilidade dos testes
  # de Fase 3/Fase 4 com a nova semântica intencional do gate
  # REGISTRO->CLASSIFICACAO, mesma branch fix/gate-classificacao-esteira,
  # 2026-08-29). Estes 2 arquivos já existiam (mesclados via PR #27,
  # antes deste hook de governança existir) — nunca passaram por esta
  # checagem até agora. Libera só estes 2 caminhos exatos para a
  # correção pontual dos fixtures/asserts afetados pelo gate; não libera
  # "^test_" de forma ampla nem qualquer outro arquivo de Fase 3/4.
  "^test_magnata_os_documental_modulo01_fase3\.py$"
  "^test_magnata_os_documental_modulo01_fase4\.py$"
  # Exceção exata e restrita (decisão registrada, branch
  # claude/macro-6a-commit-recovery-k7rsly, 2026-08-12) — Macro 6A,
  # auditoria e esteira documental. Somente estes 8 caminhos exatos de
  # teste, não um padrão genérico — não libera "^test_" de forma ampla;
  # qualquer outro test_*.py continua bloqueado, cada um batido por
  # igualdade de string completa via âncora $ no fim.
  "^test_competencia_fiscal\.py$"
  "^test_fase_c_async_separar\.py$"
  "^test_fila_envios_v2_23\.py$"
  "^test_idempotencia_esteira\.py$"
  "^test_idempotencia_pendencia_kit\.py$"
  "^test_kit_admissao_identidade\.py$"
  "^test_sanitizacao_v2_20\.py$"
  "^test_seguranca_rotas_dp_fiscal\.py$"
  # Exceção exata (decisão registrada, branch
  # fix/holerite-ponto-pacote-assinatura) — pacote atômico de assinatura
  # eletrônica Holerite + Folha de Ponto (Holerite nunca assinável
  # isolado, só pareado com a Folha de Ponto da mesma competência). Só
  # este caminho exato — não libera "^test_" de forma ampla.
  "^test_pacote_assinatura_holerite_ponto\.py$"
  "^docs/decisoes/pacote-holerite-folha-ponto\.md$"
  # Macro de fechamento do mesmo pacote — rotina de reconciliação de
  # backlog por competência (só leitura, ver macro §5) e seu teste. Só
  # estes 2 caminhos exatos — não libera "^scripts/" nem "^test_" de
  # forma ampla.
  "^scripts/reconciliacao_backlog_holerite_ponto\.py$"
  "^test_reconciliacao_backlog_holerite_ponto\.py$"
  # Exceção exata e restrita (decisão registrada, branch
  # fix/pacote-holerite-ponto-entrega-real, 2026-08-19) — correção da
  # entrega real do pacote Holerite + Folha de Ponto (auditoria de
  # 18-19/08/2026 encontrou que o colaborador nunca via o PDF em lugar
  # nenhum). Script standalone de homologação (dispara 1 registro de
  # teste antes do lote, não executado pelo agente). Só este caminho
  # exato — não libera "^teste_" nem "^test_" de forma ampla.
  "^teste_homologacao\.py$"
  # Exceção exata e restrita (decisão registrada, branch
  # fix/pacote-holerite-ponto-entrega-real, 2026-08-20) — capacidade do
  # servidor para o disparo em lote do pacote Holerite + Folha de Ponto.
  # Desde a pré-visualização em imagem, CADA página de documento é uma
  # requisição que busca o registro, baixa o PDF e o renderiza; com 1
  # worker e reciclagem a cada 50 requisições, um pico de cliques
  # enfileira e derruba requisições em andamento. Os 2 arquivos entram
  # juntos porque precisam declarar o MESMO comando — divergência entre
  # eles faz o ajuste sumir em silêncio. Só estes 2 caminhos exatos —
  # não libera "^.*\.yaml$" nem nenhum outro arquivo de infraestrutura.
  "^Procfile$"
  "^render\.yaml$"
  # Exceção exata e restrita (proposta da Etapa 8 da Central Command,
  # 2026-08-22) — recuperação do painel visual da Fase 5 do Módulo 01,
  # hoje parado numa branch com 50 arquivos porque 49 deles são barrados
  # aqui. Ver docs/magnata-os/central-command/FASE5_AUDITORIA.md §5.1.
  #
  # IMPACTO DECLARADO, não escondido: isto AMPLIA a superfície de escrita
  # do repositório. Passa a ser possível commitar em frontend/src/,
  # frontend/styles/, frontend/tests/ e frontend/index.html sem nova
  # decisão a cada arquivo.
  #
  # O que continua protegido, de propósito: "^frontend/" NÃO foi liberado
  # como prefixo genérico. frontend/CLAUDE.md e frontend/assets/brand/
  # seguem em PROTECTED_FILES e nenhum padrão abaixo os alcança — os
  # assets oficiais de marca continuam exigindo autorização explícita
  # (CLAUDE.md §7).
  "^frontend/index\.html$"
  "^frontend/src/"
  "^frontend/styles/"
  "^frontend/tests/"
  # Exceção exata e restrita (2026-08-22) — remoção de CPF REAL de código
  # versionado. A trava de PII do sensor do Graphify
  # (scripts/ci/graphify_regenerar.sh) encontrou 3 CPFs com dígito
  # verificador válido commitados nestes 3 arquivos; todos os demais no
  # repositório são fixtures sintéticas que falham a validação.
  # `CLAUDE.md` §6 proíbe dado pessoal em commit — a correção não é
  # opcional. Só estes 3 caminhos exatos, por igualdade de string
  # completa; não libera "^src/" nem "^test_" de forma ampla.
  "^src/sync_new_employees\.py$"
  "^test_leitura_ponto\.py$"
  "^test_folha_ponto_v2_21\.py$"
  # Excecao exata e restrita (branch
  # fix/orquestrador-autorrecuperacao-segura, 2026-08-25) — nucleo de
  # autorrecuperacao sobre health persistente. Somente os arquivos
  # efetivamente alterados por esta fase; nao libera "^magnata_os/",
  # "^docs/decisoes/" nem "^test_" de forma ampla.
  "^magnata_os/orquestrador/autorrecuperacao\.py$"
  "^magnata_os/orquestrador/politica_recuperacao\.py$"
  "^magnata_os/orquestrador/eventos\.py$"
  "^magnata_os/orquestrador/fila_desistencia\.py$"
  "^magnata_os/orquestrador/motor\.py$"
  "^magnata_os/orquestrador/repositorio_execucoes\.py$"
  "^magnata_os/orquestrador/supervisor\.py$"
  "^docs/decisoes/autorrecuperacao-segura-v1\.md$"
  "^test_magnata_os_orquestrador_autorrecuperacao\.py$"
  "^test_magnata_os_orquestrador_concurrency\.py$"
  "^test_magnata_os_orquestrador_crash_consistency\.py$"
  "^test_magnata_os_orquestrador_fila_desistencia\.py$"
  # Excecao exata e restrita (branch
  # fix/orquestrador-persistencia-duravel, 2026-08-25) — adapter Postgres
  # inerte e contrato versionado do supervisor. Nao libera o diretorio de
  # migrations nem qualquer outro arquivo do Orquestrador.
  "^magnata_os/orquestrador/repositorio_execucoes_postgres\.py$"
  "^magnata_os/orquestrador/fabrica_repositorio_execucoes\.py$"
  "^magnata_os/orquestrador/migrations/0001_repositorio_execucoes\.sql$"
  "^magnata_os/orquestrador/migrations/0001_repositorio_execucoes_rollback\.sql$"
  "^docs/decisoes/persistencia-duravel-orquestrador-v1\.md$"
  "^test_magnata_os_orquestrador_postgres\.py$"
  # Excecao exata e restrita (primeiro gate controlado
  # CLASSIFICACAO->IDENTIFICACAO, so Holerite avulso, branch
  # fix/identificacao-holerite-avulso) — modulo novo de politica pura de
  # transicao (nao depende de ItemManifestoHolerite/ConfiguracaoExecucao/
  # processar_holerite, so de resolver_funcionario ja existente e do
  # contrato neutro ResolucaoDimensao ja existente em
  # magnata_os/classificacao/contratos.py). Nao libera
  # "^magnata_os/documental/modulo01/" nem "^test_" de forma ampla. Os
  # arquivos ja modificados nesta branch (roteamento_documental.py,
  # dominio.py, dtos_esteira.py, servico_avanco_esteira.py,
  # servico_lote.py) ja estavam em ALLOWED_PATHS de branches anteriores —
  # nao precisam de entrada nova aqui.
  "^magnata_os/documental/modulo01/politica_identificacao_holerite\.py$"
  "^test_politica_identificacao_holerite\.py$"
  "^test_gate_identificacao_holerite_esteira\.py$"
  # Excecao exata e restrita (composition root V1 do Modulo 01, branch
  # fix/composition-root-modulo01-v1) — modulo novo que monta o pipeline
  # completo (FonteMensagensEmail -> AdapterCapturaEmail ->
  # ServicoCriacaoLote -> repositorios/FonteCandidatosFuncionario) a
  # partir de dependencias ja construidas, sem decidir backend, sem ler
  # env, sem abrir rede/conexao. Nao libera
  # "^magnata_os/documental/modulo01/" nem "^test_" de forma ampla. O
  # arquivo de teste ja existia (mesclado antes deste hook existir, mesmo
  # caso ja registrado para fase3/fase4/gate-classificacao-esteira) —
  # nunca havia passado por esta checagem ate agora.
  "^magnata_os/documental/modulo01/composicao\.py$"
  "^test_magnata_os_documental_modulo01_email_captura\.py$"
  "^docs/decisoes/composition-root-modulo01-v1\.md$"
  # Excecao exata e restrita (primeiro corredor automatizado E2E da
  # Prestacao de Contas, Holerite primeiro, branch
  # fix/corredor-prestacao-holerite-e2e) — ponte pura Modulo 01 ->
  # Prestacao que traduz um Holerite avulso ja identificado
  # (HoleriteConfirmadoDTO, dtos_esteira.py, ja liberado acima) num
  # ItemInventarioPrestacao (contrato neutro ja existente), so quando
  # competencia observada bate com uma competencia esperada
  # INDEPENDENTE (parametro explicito, nunca inferida do documento) e o
  # colaborador resolve para exatamente 1 cliente (FonteVinculosPrestacao
  # ja existente, sem alteracao). Nao libera
  # "^magnata_os/documental/modulo01/" nem "^test_" de forma ampla.
  "^magnata_os/documental/modulo01/ponte_prestacao_holerite\.py$"
  "^test_corredor_prestacao_holerite_e2e\.py$"
  "^docs/decisoes/corredor-prestacao-holerite-e2e-v1\.md$"
  # Excecao exata e restrita (fonte automatica de competencia esperada
  # da Prestacao de Contas, branch fix/competencia-esperada-prestacao)
  # — politica pura e versionada (PoliticaCompetenciaPrestacao,
  # mesmo padrao ja usado por PoliticaRequisitosPrestacao/
  # OverrideRequisitosPrestacao) que resolve a competencia esperada a
  # partir de um contexto de ciclo (fornecido uma vez por execucao,
  # nunca por documento) + deslocamento opcional por cliente (vazio por
  # padrao -- nenhuma excecao real comprovada na auditoria). Ajusta
  # minimamente ponte_prestacao_holerite.py (ja liberado acima) para
  # resolver cliente antes de perguntar a competencia esperada. Nao
  # libera "^magnata_os/classificacao/" nem "^test_" de forma ampla.
  "^magnata_os/classificacao/competencia_esperada_prestacao\.py$"
  "^test_magnata_os_classificacao_competencia_esperada_prestacao\.py$"
  "^docs/decisoes/competencia-esperada-prestacao-v1\.md$"
  # Excecao exata e restrita (compositor geral de resolucao semantica,
  # branch fix/resolucao-semantica-fase2e) — modulo novo e puro que
  # compoe ResultadoResolucaoSemantico a partir de ResolucaoDimensao ja
  # produzidas por especialistas existentes (classificador de tipo,
  # identificacao de colaborador, vinculos, competencia) — nenhuma regra
  # de classificacao/identificacao/vinculo/competencia reimplementada
  # aqui, so composicao. Ajustes de tradutor em
  # classificador_documental.py e politica_identificacao_holerite.py
  # (ja liberados acima, apenas modificados). Nao libera
  # "^magnata_os/classificacao/" nem "^test_" de forma ampla.
  "^magnata_os/classificacao/resolucao_semantica\.py$"
  "^test_magnata_os_classificacao_resolucao_semantica\.py$"
  "^test_resolucao_semantica_corredor_real\.py$"
  "^docs/decisoes/resolucao-semantica-fase2e-v1\.md$"
  # Excecao exata e restrita (motor geral de compreensao documental
  # multi-evidencia, branch fix/motor-geral-compreensao-documental) —
  # resolvedor geral de TIPO_DOCUMENTAL (resolucao_tipo_documental.py)
  # + produtores de evidencia (produtores_evidencia_documental.py) que
  # traduzem especialistas ja existentes (classificador_documental.py,
  # extrair_cpfs_distintos_de_texto) em evidencia combinavel — nenhuma
  # regra de classificacao reimplementada, so composicao multi-evidencia.
  # Nao libera "^magnata_os/classificacao/" nem "^test_" de forma ampla.
  "^magnata_os/classificacao/resolucao_tipo_documental\.py$"
  "^magnata_os/classificacao/produtores_evidencia_documental\.py$"
  "^test_magnata_os_classificacao_resolucao_tipo_documental\.py$"
  "^test_resolucao_tipo_documental_fila_heterogenea\.py$"
  "^docs/decisoes/motor-geral-compreensao-documental-v1\.md$"
  # Excecao exata e restrita (capacidades transversais do motor
  # documental, branch fix/capacidades-transversais-documentais) —
  # evidencia estrutural (contagem, nunca CPF/CNPJ bruto), detector
  # geral de granularidade (master != tipo documental, dataclass
  # propria, nunca estende DimensaoResolucao), engine de separacao
  # MASTER->FILHOS plugavel (generaliza construir_mapa_cliente do
  # legado, nunca importa app.py), producer de finalidade de
  # comprovante de pagamento (reusa resolver_tipo_documental, nenhuma
  # regra de combinacao nova) e a ligacao (so sugestao, sem alterar
  # TRANSICOES_ETAPA_PERMITIDAS) entre granularidade e EtapaEsteira.
  # Nao libera "^magnata_os/classificacao/" nem "^test_" de forma ampla.
  "^magnata_os/classificacao/evidencia_estrutural_documental\.py$"
  "^magnata_os/classificacao/resolucao_master_documental\.py$"
  "^magnata_os/classificacao/separacao_documental\.py$"
  "^magnata_os/classificacao/finalidade_comprovante_pagamento\.py$"
  "^magnata_os/documental/modulo01/decisao_pos_classificacao\.py$"
  "^test_magnata_os_classificacao_evidencia_estrutural_documental\.py$"
  "^test_magnata_os_classificacao_resolucao_master_documental\.py$"
  "^test_magnata_os_classificacao_separacao_documental\.py$"
  "^test_magnata_os_classificacao_finalidade_comprovante_pagamento\.py$"
  "^test_magnata_os_documental_modulo01_decisao_pos_classificacao\.py$"
  "^test_capacidades_transversais_fila_heterogenea\.py$"
  "^docs/decisoes/capacidades-transversais-motor-documental-v1\.md$"
  # Excecao exata e restrita (fechamento amplo da cobertura documental,
  # branch fix/fechamento-cobertura-documental-fase2e3) — produtores
  # transversais novos (fiscal, ponto, temporal/certidao), cada um
  # reaproveitando so extratores/padroes ja existentes ou portados do
  # legado, todos alimentando o MESMO resolver_tipo_documental. Nao
  # libera "^magnata_os/classificacao/" nem "^test_" de forma ampla.
  "^magnata_os/classificacao/produtores_evidencia_fiscal\.py$"
  "^magnata_os/classificacao/produtores_evidencia_ponto\.py$"
  "^magnata_os/classificacao/produtores_evidencia_temporal\.py$"
  "^test_magnata_os_classificacao_produtores_evidencia_fiscal_ponto_temporal\.py$"
  "^test_magnata_os_classificacao_perfis_aplicabilidade_por_familia\.py$"
  "^test_corredor_extrato_mensal_pos_separacao\.py$"
  "^test_fechamento_cobertura_documental_fila_heterogenea\.py$"
  "^docs/decisoes/fechamento-cobertura-documental-fase2e3-v1\.md$"
  # Excecao exata e restrita (corredor operacional da prestacao de
  # contas, branch fix/corredor-operacional-prestacao-v1) — adaptador
  # generico ResultadoResolucaoSemantico->ItemInventarioPrestacao
  # (nunca substitui os 2 caminhos existentes, so soma um 3o caminho
  # generico), pacote logico por cliente (nunca gera ZIP/PDF), extensao
  # aditiva de PoliticaRequisitosPrestacao (default identico ao
  # comportamento anterior). Nao libera "^magnata_os/classificacao/"
  # nem "^test_" de forma ampla.
  "^magnata_os/classificacao/adaptador_inventario_prestacao\.py$"
  "^magnata_os/classificacao/pacote_prestacao\.py$"
  "^magnata_os/classificacao/politica_requisitos_prestacao\.py$"
  "^test_magnata_os_classificacao_adaptador_inventario_prestacao\.py$"
  "^test_magnata_os_classificacao_pacote_prestacao\.py$"
  "^test_corredor_operacional_prestacao_e2e\.py$"
  "^docs/decisoes/corredor-operacional-prestacao-v1\.md$"
  # Excecao exata e restrita (politica operacional real de clientes/
  # requisitos, branch fix/politica-operacional-prestacao-v1) — fontes
  # canonicas substituiveis de clientes/requisitos, normalizacao pura,
  # adapter Airtable read-only de clientes (reaproveita
  # LeitorAirtableSomenteLeitura ja existente, nenhum cliente HTTP
  # novo), orquestrador de ciclo (so leitura, sem side effects). Nao
  # libera "^magnata_os/classificacao/" nem "^test_" de forma ampla.
  "^magnata_os/classificacao/fonte_clientes_prestacao\.py$"
  "^magnata_os/classificacao/fonte_requisitos_prestacao\.py$"
  "^magnata_os/classificacao/normalizacao_requisitos_prestacao\.py$"
  "^magnata_os/classificacao/ciclo_prestacao\.py$"
  "^magnata_os/documental/importacao_lote/adapters/airtable_clientes_prestacao\.py$"
  "^test_magnata_os_classificacao_normalizacao_requisitos_prestacao\.py$"
  "^test_magnata_os_documental_airtable_clientes_prestacao\.py$"
  "^test_ciclo_prestacao_multicliente_e2e\.py$"
  "^test_magnata_os_classificacao_ciclo_prestacao\.py$"
  "^docs/decisoes/politica-operacional-prestacao-v1\.md$"
  # Excecao exata e restrita (cadastro canonico real de requisitos da
  # prestacao, branch fix/cadastro-canonico-requisitos-prestacao-v1) —
  # cadastro declarativo versionado (base = intersecao comprovada de 2
  # fontes canonicas, zero clientes condicionais inventados),
  # reconciliacao fiscal<->finalidade, prova de vinculo de beneficio
  # (reaproveita FonteVinculosPrestacao existente, nenhuma peca nova).
  # Nao libera "^magnata_os/classificacao/" nem "^test_" de forma ampla.
  "^magnata_os/classificacao/cadastro_requisitos_prestacao\.py$"
  "^test_magnata_os_classificacao_cadastro_requisitos_prestacao\.py$"
  "^test_magnata_os_classificacao_reconciliacao_fiscal_finalidade\.py$"
  "^test_magnata_os_classificacao_vinculo_beneficio_prestacao\.py$"
  "^test_ciclo_prestacao_cadastro_canonico_e2e\.py$"
  "^docs/decisoes/cadastro-canonico-requisitos-prestacao-v1\.md$"
  # Excecao exata e restrita (Adendo de Regra de Negocio -- Holerite,
  # mesma branch fix/cadastro-canonico-requisitos-prestacao-v1) —
  # Holerite promovido a base universal com granularidade colaborador
  # (cardinalidade, nunca contagem plana), fonte de colaboradores
  # esperados (Protocol) e avaliacao pura de obrigatoriedade, ambos
  # aditivos e retrocompativeis. Nao libera "^magnata_os/classificacao/"
  # nem "^test_" de forma ampla.
  "^magnata_os/classificacao/fonte_colaboradores_esperados_prestacao\.py$"
  "^magnata_os/classificacao/holerite_obrigatorio_prestacao\.py$"
  "^test_magnata_os_classificacao_holerite_obrigatorio_prestacao\.py$"
  # Excecao exata e restrita (fechamento da base canonica + preparacao
  # do primeiro ciclo piloto real read-only, branch
  # fix/ciclo-piloto-prestacao-readonly-v1) — cadastro V2 (Guia
  # DCTFWeb/DARF promovido a base; Holerite permanece universal, avaliado
  # por cardinalidade colaborador -- ver ADENDO DE CONTINUIDADE, mesma
  # branch, que revogou uma instrução intermediária desta missão antes
  # do PR ser mesclado), runner READ-ONLY do ciclo piloto com saida
  # dry-run sanitizada (7 campos fixos, nunca CPF/nome/texto de PDF/
  # token/payload), adapter read-only de colaboradores esperados por
  # cliente (direcao inversa de airtable_vinculos_prestacao.py, nunca
  # Airtable live). Nao libera "^magnata_os/classificacao/",
  # "^magnata_os/documental/importacao_lote/adapters/" nem "^test_" de
  # forma ampla.
  "^magnata_os/classificacao/ciclo_piloto_prestacao\.py$"
  "^test_ciclo_piloto_prestacao_readonly_e2e\.py$"
  "^magnata_os/documental/importacao_lote/adapters/airtable_colaboradores_esperados_prestacao\.py$"
  "^test_airtable_colaboradores_esperados_prestacao\.py$"
  "^docs/decisoes/fechamento-base-canonica-ciclo-piloto-readonly-v1\.md$"
  # Excecao exata e restrita (merge PR #100 + validacao live read-only
  # do Airtable + primeiro piloto real, branch
  # fix/piloto-real-prestacao-readonly-v1) — correcao do adapter de
  # Clientes (campo Status real, confirmado por leitura live) e ADR da
  # validacao. Nao libera nenhum caminho de forma ampla.
  "^docs/decisoes/piloto-real-prestacao-readonly-v1\.md$"
  # Excecao exata e restrita (inventario documental real da prestacao +
  # preparacao do primeiro piloto completo SKY, branch
  # fix/inventario-real-prestacao-v1) — fonte composta de inventario
  # (agrega fontes existentes, nunca pipeline separado por familia),
  # adapter read-only de Holerites (reaproveita FonteVinculosPrestacao
  # ja existente), piloto SKY completo local com fixtures do schema
  # real (nunca Airtable live). Nao libera "^magnata_os/classificacao/",
  # "^magnata_os/documental/importacao_lote/adapters/" nem "^test_" de
  # forma ampla.
  "^magnata_os/classificacao/fonte_inventario_composta\.py$"
  "^magnata_os/documental/importacao_lote/adapters/airtable_holerites_prestacao\.py$"
  "^test_magnata_os_classificacao_fonte_inventario_composta\.py$"
  "^test_airtable_holerites_prestacao\.py$"
  "^test_piloto_sky_inventario_real_local_e2e\.py$"
  "^docs/decisoes/inventario-real-prestacao-v1\.md$"
  # Excecao exata e restrita (automacao documental real V1 -- motor
  # semantico multi-evidencia, universo documental, automacao por
  # confianca, branch fix/automacao-documental-semantica-v1) — produtor
  # adicional de rotulo alternativo de Extrato (nunca altera o
  # classificador espelho do legado), reconciliacao origem x conteudo
  # (nunca deixa o Airtable virar cerebro semantico), decisao fina de
  # automacao por confianca (reusa NivelConfianca/EstadoResolucaoDimensao
  # ja existentes, nenhum score novo), estrategia de aquisicao
  # complementar (reusa NecessidadeDocumentoPrestacao.fontes_ainda_nao_
  # consultadas ja existente), corpus E2E heterogeneo. Nao libera
  # "^magnata_os/classificacao/" nem "^test_" de forma ampla.
  "^magnata_os/classificacao/produtores_evidencia_extrato\.py$"
  "^magnata_os/classificacao/reconciliacao_origem_conteudo\.py$"
  "^magnata_os/classificacao/automacao_por_confianca\.py$"
  "^magnata_os/classificacao/estrategia_aquisicao_documental\.py$"
  "^test_magnata_os_classificacao_produtores_evidencia_extrato\.py$"
  "^test_magnata_os_classificacao_reconciliacao_origem_conteudo\.py$"
  "^test_magnata_os_classificacao_automacao_por_confianca\.py$"
  "^test_magnata_os_classificacao_estrategia_aquisicao_documental\.py$"
  "^test_corpus_heterogeneo_motor_semantico_e2e\.py$"
  "^docs/decisoes/automacao-documental-semantica-v1\.md$"
  # Excecao exata e restrita (integracao real do conteudo documental ao
  # motor semantico + automacao continua da esteira V1, branch
  # fix/integracao-conteudo-motor-semantico-v1) — ponte texto->motor
  # multi-evidencia (agrega produtores ja existentes para o MESMO
  # resolver_tipo_documental, nunca um segundo motor; reaproveita
  # extrair_texto_seguro de roteamento_documental.py, nunca uma segunda
  # extracao de PDF), politica de transicao CLASSIFICACAO->esteira que
  # usa o motor geral de 8 estados (mesmo contrato DecisaoTransicao
  # Classificacao ja consumido por ServicoAvancoEsteira, zero mudanca
  # nessa mecanica), reconciliacao origem x conteudo e competencia
  # esperada x observada (reusa extrair_competencia_de_texto/
  # validar_competencia/resolucao_competencia_de_validacao ja
  # existentes), teste arquitetural (nenhum modulo do corredor importa
  # Airtable), corpus E2E heterogeneo de 10 casos + metricas. Nao libera
  # "^magnata_os/classificacao/", "^magnata_os/documental/modulo01/" nem
  # "^test_" de forma ampla.
  "^magnata_os/classificacao/ponte_conteudo_motor_semantico\.py$"
  "^magnata_os/documental/modulo01/politica_classificacao_semantica\.py$"
  "^test_magnata_os_classificacao_ponte_conteudo_motor_semantico\.py$"
  "^test_magnata_os_classificacao_arquitetura_sem_dependencia_airtable\.py$"
  "^test_magnata_os_documental_modulo01_politica_classificacao_semantica\.py$"
  "^test_magnata_os_documental_modulo01_corpus_heterogeneo_classificacao_semantica\.py$"
  "^docs/decisoes/integracao-conteudo-motor-semantico-v1\.md$"
  # Excecao exata e restrita (corredor autonomo pos-classificacao V1,
  # branch fix/corredor-autonomo-pos-classificacao-v1) — cadastro
  # declarativo de perfil de aplicabilidade por tipo ja resolvido
  # (reusa PerfilAplicabilidadeResolucao/RegraAplicabilidadeDimensao ja
  # existentes, nenhum contrato novo), identificacao generica de
  # colaborador (extraida de politica_identificacao_holerite.py, que
  # continua existindo e so passa a delegar), orquestrador que compoe
  # ponte+perfil+identificacao+competencia+vinculo+compor_resolucao_
  # semantica+adaptador_inventario_prestacao (todos ja existentes,
  # nenhum duplicado) ate o item de inventario, sink de inventario em
  # memoria idempotente (referencia local/piloto, nunca Airtable/
  # Postgres real), corpus E2E de 10 casos (A-J) + metricas. Nao libera
  # "^magnata_os/classificacao/", "^magnata_os/documental/modulo01/" nem
  # "^test_" de forma ampla.
  "^magnata_os/classificacao/identificacao_documental\.py$"
  "^magnata_os/classificacao/perfil_aplicabilidade_documental\.py$"
  "^magnata_os/classificacao/resolucao_documento_prestacao\.py$"
  "^magnata_os/classificacao/inventario_prestacao_memoria\.py$"
  "^test_magnata_os_classificacao_identificacao_documental\.py$"
  "^test_magnata_os_classificacao_perfil_aplicabilidade_documental\.py$"
  "^test_magnata_os_classificacao_resolucao_documento_prestacao\.py$"
  "^test_magnata_os_classificacao_corpus_corredor_autonomo_pos_classificacao\.py$"
  "^docs/decisoes/corredor-autonomo-pos-classificacao-v1\.md$"
  # Excecao exata e restrita (Adendo substitutivo ao PR #105 -- correcao
  # de granularidade FGTS/Guia/beneficios VR-VA-iFood + dedupe, mesma
  # branch fix/corredor-autonomo-pos-classificacao-v1) — produtor de
  # relatorio/pedido de beneficios (VR/VA/iFood, fornecedor e evidencia
  # nunca identidade, nunca forca escolha exclusiva VR/VA) e seus testes
  # nominais. Arquivos ja existentes tocados nesta correcao (perfil_
  # aplicabilidade_documental.py, ponte_conteudo_motor_semantico.py,
  # prestacao_readiness.py, fonte_inventario_composta.py, inventario_
  # prestacao_memoria.py, test_magnata_os_classificacao_fonte_
  # inventario_composta.py) ja estavam no escopo permitido de missoes
  # anteriores, nao precisam de nova entrada. Nao libera
  # "^magnata_os/classificacao/" nem "^test_" de forma ampla.
  "^magnata_os/classificacao/produtores_evidencia_beneficios\.py$"
  "^test_magnata_os_classificacao_produtores_evidencia_beneficios\.py$"
  "^test_magnata_os_classificacao_adendo_beneficios_fgts_dedupe\.py$"
  # Excecao exata e restrita (missao "MERGE PR #105 + EVIDENCIA RELACIONAL
  # DOCUMENTO<->DOCUMENTO + VINCULO/UNIDADE_POSTO REAIS + FECHAMENTO DO
  # UNIVERSO DOCUMENTAL V1", branch fix/evidencia-relacional-vinculo-
  # unidade-v1) — produtor real de VINCULO (espelha CLIENTE ja derivado de
  # vinculo, nenhum I/O novo) e UNIDADE_POSTO (fonte via Protocol,
  # cardinalidade multipla genuina) com seus testes nominais; capacidade
  # GENERICA de relacao semantica Documento<->Documento (nunca uma classe
  # por familia/fornecedor) e seu teste nominal; suite E2E obrigatoria
  # (casos A-J) desta missao; documento de decisao. Arquivos ja existentes
  # tocados nesta missao (perfil_aplicabilidade_documental.py,
  # resolucao_documento_prestacao.py, produtores_evidencia_beneficios.py e
  # seus testes nominais, alem de test_magnata_os_classificacao_corpus_
  # corredor_autonomo_pos_classificacao.py e test_magnata_os_
  # classificacao_arquitetura_sem_dependencia_airtable.py) ja estavam no
  # escopo permitido de missoes anteriores, nao precisam de nova entrada.
  # Nao libera "^magnata_os/classificacao/" nem "^test_" de forma ampla.
  "^magnata_os/classificacao/vinculo_unidade_prestacao\.py$"
  "^test_magnata_os_classificacao_vinculo_unidade_prestacao\.py$"
  "^magnata_os/classificacao/relacao_documental\.py$"
  "^test_magnata_os_classificacao_relacao_documental\.py$"
  "^test_magnata_os_classificacao_e2e_vinculo_unidade_relacao_v1\.py$"
  "^docs/decisoes/evidencia-relacional-vinculo-unidade-v1\.md$"
  # Excecao exata e restrita (missao "CORRIGIR METADADOS + MERGE PR #106 +
  # COSTURA AUTOMATICA DE RELACAO DOCUMENTO<->DOCUMENTO NO CORREDOR V1",
  # branch fix/costura-relacao-documental-corredor-v1) — fonte GENERICA de
  # candidatos de relacao (Protocol source-neutral, nunca por familia/
  # fornecedor) e sua composta local; politica declarativa de consequencia
  # (deriva referencias OU preserva broadcast, nunca as duas); orquestrador
  # que liga fonte+relacao+politica+inventario ja existentes (nenhum motor
  # novo) com metricas relacionais permanentes; testes nominais. Arquivos
  # ja existentes tocados (produtores_evidencia_beneficios.py -- delegacao
  # da derivacao para a politica generica -- e test_magnata_os_
  # classificacao_arquitetura_sem_dependencia_airtable.py) ja estavam no
  # escopo permitido de missoes anteriores, nao precisam de nova entrada.
  # Nao libera "^magnata_os/classificacao/" nem "^test_" de forma ampla.
  "^magnata_os/classificacao/fonte_candidatos_relacao_documental\.py$"
  "^magnata_os/classificacao/politica_consequencia_relacao_documental\.py$"
  "^magnata_os/classificacao/corredor_relacao_documental\.py$"
  "^test_magnata_os_classificacao_fonte_candidatos_relacao_documental\.py$"
  "^test_magnata_os_classificacao_politica_consequencia_relacao_documental\.py$"
  "^test_magnata_os_classificacao_corredor_relacao_documental\.py$"
  "^docs/decisoes/costura-relacao-documental-corredor-v1\.md$"
)

# ============================================================================
# PADRÕES DE SCRATCH — Arquivos temporários proibidos em commit
# ============================================================================

SCRATCH_PATTERNS=(
  "^_"
  "^test_"
  "\.tmp$"
  "\.bak$"
  "\.swp$"
  "\.swo$"
)

# ============================================================================
# MENSAGENS E CÓDIGOS DE SAÍDA
# ============================================================================

MSG_APPROVED="✓ APROVADO"
MSG_BLOCKED="✗ BLOQUEADO"
MSG_WARNING="⚠ AVISO"
MSG_INFO="ℹ INFORMAÇÃO"
MSG_ERROR="✘ ERRO INTERNO"

EXIT_APPROVED=0
EXIT_BLOCKED=1
EXIT_WARNING=0      # Avisos não bloqueiam
EXIT_ERROR=1        # Erro interno sempre bloqueia

# ============================================================================
# FUNÇÕES ÚTEIS
# ============================================================================

# Verifica se arquivo é protegido
is_protected_file() {
  local file="$1"
  for pattern in "${PROTECTED_FILES[@]}"; do
    if [[ "$file" =~ $pattern ]]; then
      return 0  # É protegido
    fi
  done
  return 1  # Não é protegido
}

# Arquivos que definem ou testam os próprios padrões proibidos (segredo,
# 11º módulo, 9 camadas, autonomia %, ADR silenciosa) — não são violação
# real, são a fonte canônica de detecção (este arquivo) ou fixtures da
# suíte de testes do CI de governança. Movida para cá (antes vivia só
# dentro de .githooks/pre-commit) porque scripts/ci/validate_governance.sh
# também precisa dela — hook local e CI não podem divergir sobre o que é
# "fonte do próprio padrão" vs. violação real.
is_gate_pattern_source_file() {
  local file="$1"
  [[ "$file" == .githooks/* ]] || \
  [[ "$file" == ".magnata/patterns.sh" ]] || \
  [[ "$file" == "scripts/ci/test_governance.sh" ]] || \
  [[ "$file" == "scripts/ci/validate_governance.sh" ]]
}

# Verifica se um arquivo staged contém segredo real — alias mantido por
# compatibilidade de nome; delega inteiramente a arquivo_staged_tem_segredo
# (conteúdo do índice, só linhas adicionadas, valor literal não-placeholder).
# A versão anterior desta função escaneava o arquivo inteiro no working
# tree por bare match de identificador — substituída (ver cabeçalho da
# seção PADRÕES DE SEGREDO acima para o porquê).
has_secret_pattern() {
  local file="$1"
  arquivo_staged_tem_segredo "$file" > /dev/null
}

# Verifica modo Git de arquivo
get_file_mode() {
  local file="$1"
  git ls-files --stage "$file" | awk '{print $1}' | sed 's/^0//'
}

# Verifica se arquivo é documento normativo (escopo dos gates semânticos 7-10)
is_normative_doc() {
  local file="$1"
  for pattern in "${NORMATIVE_DOC_PATTERNS[@]}"; do
    if [[ "$file" =~ $pattern ]]; then
      return 0  # É normativo
    fi
  done
  return 1  # Não é normativo (técnico, relatório, ou outro)
}

# Exporta funções e variáveis
export PROTECTED_FILES SECRET_PATTERNS_ABSOLUTOS SECRET_CONTEXT_KEYWORDS SECRET_PLACEHOLDER_REGEX GATE_11_MODULE_PATTERNS
export GATE_9_LAYERS_PATTERNS GATE_AUTONOMY_PERCENT_PATTERNS GATE_ADR_SILENT_PATTERNS
export REQUIRED_DOCS CLAUDE_HIERARCHY EXECUTABLE_FILES NON_EXECUTABLE_FILES
export ALLOWED_PATHS SCRATCH_PATTERNS NORMATIVE_DOC_PATTERNS AUTHORIZED_BRANCHES
export MSG_APPROVED MSG_BLOCKED MSG_WARNING MSG_INFO MSG_ERROR
export EXIT_APPROVED EXIT_BLOCKED EXIT_WARNING EXIT_ERROR
export -f is_protected_file is_gate_pattern_source_file has_secret_pattern _valor_e_placeholder linha_contem_segredo_real arquivo_staged_tem_segredo get_file_mode is_normative_doc is_authorized_branch is_claude_hierarchy_path
