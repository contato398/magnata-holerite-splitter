-- Magnata OS — Identidade Canônica de Colaborador V1
-- Migration 0003: identidade_colaborador_observada
--
-- INERTE: nenhum módulo aplica esta migration automaticamente -- mesma
-- disciplina de 0001/0002 deste pacote e de todas as migrations do
-- Módulo 01. Aplicar manualmente quando um Postgres real for
-- provisionado -- gate humano separado, nunca produção nesta missão.
--
-- Contexto (missão "IDENTIDADE CANÔNICA DE COLABORADOR V1"): fecha a
-- lacuna comprovada por auditoria -- não existe hoje nenhuma tabela
-- que represente "identificador observado (ex.: CPF extraído de um
-- documento) -> colaborador_id", persistida, consultável sem Airtable
-- em runtime. `vinculo_trabalhista` (migration 0001) exclui CPF/nome
-- por decisão de escopo deliberada e documentada (dependência
-- estrutural mínima de `alocacao`, nunca um cadastro de RH) -- esta
-- tabela é uma entidade SEPARADA, de propósito, nunca uma extensão de
-- `vinculo_trabalhista`.
--
-- DECISÃO DE MODELO (Opção A do ULTRAPLAN aprovado, "TRANSIÇÃO
-- CONSERVADORA"): `colaborador_id` aqui é o MESMO identificador opaco
-- já usado em `vinculo_trabalhista.colaborador_id` e em
-- `ReferenciaCanonica('COLABORADOR', ...)` em todo `classificacao/` --
-- hoje, de fato, o Airtable record id de Funcionários (ver comentário
-- idêntico em `0001_criar_vinculo_trabalhista_e_alocacao.sql`). Esta
-- tabela NUNCA declara esse id como identidade definitiva -- é
-- LEGADO/TRANSICIONAL, documentado explicitamente aqui e no domínio
-- Python (`identidade_colaborador.py`), até uma decisão futura e
-- separada introduzir um `colaborador_id` próprio do Magnata OS (fora
-- do escopo desta missão -- ver ULTRAPLAN aprovado, Opção B, adiada
-- por ampliar demais este escopo).
--
-- CPF NUNCA EM CLARO: `identificador_hash` é o HMAC-SHA256 (hex) do
-- valor normalizado com uma chave secreta (nunca hardcoded, nunca
-- neste repositório) -- ver `configuracao_identidade_colaborador.py`.
-- Um hash determinístico SEM segredo (SHA-256 puro) foi
-- explicitamente reprovado no ULTRAPLAN aprovado por ser suscetível a
-- enumeração/força bruta contra o domínio pequeno de CPF.
--
-- CHAVE PRIMÁRIA COMPOSTA, sem coluna substituta: `identificador_hash`
-- já difere naturalmente entre versões de chave (o HMAC produz um
-- valor diferente para cada chave usada), então `(tipo_identificador,
-- identificador_hash)` já é suficiente para garantir unicidade --
-- introduzir um `identificador_id` sintético adicional seria
-- duplicar a mesma informação sem necessidade (avaliado e reprovado no
-- ULTRAPLAN aprovado).
--
-- `versao_chave` é coluna companion, NUNCA parte da chave primária --
-- serve só para auditoria/rotação (saber qual chave produziu qual
-- hash), nunca para desambiguar unicidade (que já vem do próprio
-- valor do hash).
--
-- IDEMPOTÊNCIA: a chave primária composta garante que o MESMO
-- identificador (mesmo tipo + mesmo hash) nunca gera uma segunda
-- linha -- mesma disciplina de `documentos.hash_sha256` UNIQUE.
-- Conflito (mesmo identificador observado apontando para
-- `colaborador_id` DIFERENTE do já persistido) é erro a relatar pela
-- camada de aplicação (bootstrap recusa e sinaliza) -- este schema não
-- impõe isso via CHECK (não há como comparar "valor anterior" numa
-- CHECK constraint de linha única), mas a PRIMARY KEY já impede duas
-- linhas com o mesmo (tipo_identificador, identificador_hash) -- uma
-- tentativa de INSERT com o mesmo par e `colaborador_id` diferente
-- falha por violação de chave primária, nunca sobrescreve em silêncio.

CREATE TABLE IF NOT EXISTS identidade_colaborador_observada (
    tipo_identificador   TEXT NOT NULL,

    -- HMAC-SHA256 (hex, 64 chars) do valor normalizado -- nunca o
    -- valor em claro. Ver configuracao_identidade_colaborador.py para
    -- a derivação e o segredo (lido de variável de ambiente, nunca
    -- hardcoded, nunca commitado).
    identificador_hash   TEXT NOT NULL,

    -- Identidade opaca do Colaborador -- HOJE o mesmo Airtable record
    -- id já usado em vinculo_trabalhista.colaborador_id e em
    -- ReferenciaCanonica('COLABORADOR', ...) em todo classificacao/.
    -- LEGADO/TRANSICIONAL por decisão explícita (Opção A do ULTRAPLAN
    -- aprovado) -- NUNCA declarado aqui como identidade definitiva do
    -- Magnata OS. Sem FK própria: não existe tabela `colaborador` no
    -- Postgres (mesma limitação já documentada em
    -- vinculo_trabalhista.colaborador_id).
    colaborador_id       TEXT NOT NULL,

    -- Proveniência: de onde este par (identificador, colaborador_id)
    -- foi observado -- nunca "Airtable" hardcoded como valor único;
    -- texto livre para permitir origem futura sem migration nova.
    origem               TEXT NOT NULL,

    -- Versão da chave HMAC que produziu identificador_hash -- NUNCA
    -- parte da chave primária (ver decisão de modelo acima). Permite
    -- rotação: backfill sob uma versão nova produz linhas novas (hash
    -- diferente), sem tocar as linhas da versão anterior; promover a
    -- versão "atual" é decisão da camada de configuração, nunca deste
    -- schema.
    versao_chave         TEXT NOT NULL,

    criado_em            TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT identidade_colaborador_observada_pkey
        PRIMARY KEY (tipo_identificador, identificador_hash)
);

COMMENT ON TABLE identidade_colaborador_observada IS
    'Identidade Canônica de Colaborador V1: mapeia um identificador '
    'OBSERVADO (ex.: CPF extraído de um documento), protegido por '
    'HMAC-SHA256 com segredo, para o colaborador_id opaco já usado em '
    'todo o Magnata OS. Persistente e consultável sem Airtable em '
    'runtime -- Airtable serve só de bootstrap transitório (ver '
    'magnata_os/documental/importacao_lote/adapters/'
    'bootstrap_identidade_colaborador_airtable.py). CPF nunca em '
    'claro nesta tabela.';

COMMENT ON COLUMN identidade_colaborador_observada.colaborador_id IS
    'Identidade opaca do Colaborador -- HOJE o Airtable record id de '
    'Funcionários (mesmo valor de vinculo_trabalhista.colaborador_id). '
    'LEGADO/TRANSICIONAL -- nunca a identidade definitiva do Magnata '
    'OS (ver ULTRAPLAN "IDENTIDADE CANÔNICA DE COLABORADOR V1", Opção '
    'A). Uma futura tabela `colaborador` própria exigiria só um '
    'mapeamento adicional Airtable-id -> Magnata-id, nunca reescrever '
    'esta tabela.';

COMMENT ON COLUMN identidade_colaborador_observada.identificador_hash IS
    'HMAC-SHA256 (hex) do valor normalizado com segredo versionado -- '
    'nunca SHA-256 puro (reprovado por vulnerabilidade a força bruta '
    'contra o domínio pequeno de CPF) e nunca o valor em claro.';

CREATE INDEX IF NOT EXISTS idx_identidade_colaborador_observada_colaborador_id
    ON identidade_colaborador_observada (colaborador_id);

CREATE INDEX IF NOT EXISTS idx_identidade_colaborador_observada_versao_chave
    ON identidade_colaborador_observada (versao_chave);
