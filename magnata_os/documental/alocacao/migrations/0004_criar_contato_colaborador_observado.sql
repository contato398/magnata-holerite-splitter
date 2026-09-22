-- Magnata OS — Contato Canônico de Colaborador V1
-- Migration 0004: contato_colaborador_observado
--
-- INERTE: nenhum módulo aplica esta migration automaticamente -- mesma
-- disciplina de 0001/0002/0003 deste pacote e de todas as migrations
-- do Módulo 01. Aplicar manualmente quando um Postgres real for
-- provisionado -- gate humano separado, nunca produção nesta missão.
--
-- Contexto (ULTRAPLAN "RESOLUÇÃO CANÔNICA DE DESTINATÁRIO PARA
-- DISTRIBUIÇÃO DOCUMENTAL"): fecha a lacuna comprovada por auditoria --
-- não existia nenhuma tabela que representasse "telefone/WhatsApp de
-- um colaborador_id", persistida, consultável sem Airtable em runtime.
-- A única fonte real anterior era um GET direto ao Airtable em app.py
-- (_buscar_funcionario_nome_whatsapp), a cada disparo.
--
-- DECISÃO DE MODELO: `colaborador_id` aqui é o MESMO identificador
-- opaco já usado em `identidade_colaborador_observada.colaborador_id`
-- (migration 0003) e em `ReferenciaCanonica('COLABORADOR', ...)` em
-- todo `classificacao/` -- hoje, de fato, o Airtable record id de
-- Funcionários. Mesma disciplina LEGADO/TRANSICIONAL já documentada em
-- 0001/0003: esta tabela nunca declara esse id como identidade
-- definitiva.
--
-- DECISÃO DE RETENÇÃO (aprovada explicitamente antes desta migration,
-- em mensagem distinta da que a redigiu): o telefone é armazenado
-- CIFRADO DE FORMA REVERSÍVEL (Fernet -- AES-128-CBC + HMAC
-- autenticado, biblioteca `cryptography`), NUNCA como hash-only
-- (precisa ser recuperável para disparo real) e NUNCA em texto puro.
-- A chave de cifragem vive fora deste banco (variável de ambiente, ver
-- configuracao_contato_colaborador.py) -- nunca nesta tabela, nunca
-- neste repositório. `hash_auxiliar` (HMAC-SHA256, chave SEPARADA da
-- chave de cifragem) existe só para permitir comparação/deduplicação/
-- detecção de conflito sem decifrar -- nunca permite recuperar o valor
-- sozinho.
--
-- CHAVE PRIMÁRIA COMPOSTA, sem coluna substituta: (colaborador_id,
-- canal) -- mesmo raciocínio de 0003 (nenhum id sintético adicional
-- necessário). `canal` é texto livre ('whatsapp' hoje) para permitir
-- canal novo (ex. 'email') sem migration de schema nova.
--
-- IDEMPOTÊNCIA: a chave primária composta garante que o MESMO par
-- (colaborador_id, canal) nunca gera uma segunda linha. Conflito
-- (mesmo par apontando para um `hash_auxiliar` DIFERENTE do já
-- persistido -- ou seja, telefone mudou) é erro a relatar pela camada
-- de aplicação (bootstrap recusa e sinaliza via
-- ConflitoContatoColaborador) -- este schema não impõe isso via CHECK
-- (mesma limitação já documentada em 0003), mas a PRIMARY KEY já
-- impede duas linhas com o mesmo (colaborador_id, canal).
--
-- FAIL-CLOSED para número alterado: uma mudança legítima de telefone
-- NUNCA é aplicada por sobrescrita automática desta migration/destes
-- adapters -- exige reconciliação explícita (fora do escopo desta V1),
-- nunca uma escrita silenciosa que mascare um conflito real.

CREATE TABLE IF NOT EXISTS contato_colaborador_observado (
    colaborador_id       TEXT NOT NULL,

    -- Canal do contato -- 'whatsapp' nesta V1; texto livre para
    -- permitir canal novo (ex. 'email') sem migration de schema.
    canal                 TEXT NOT NULL,

    -- Valor cifrado (Fernet) do contato normalizado -- NUNCA o valor
    -- em claro. Ver contato_colaborador.py::cifrar_valor_contato /
    -- decifrar_valor_contato para a derivação e a chave (sempre fora
    -- deste banco, lida de variável de ambiente, nunca hardcoded,
    -- nunca commitada).
    valor_cifrado         BYTEA NOT NULL,

    -- HMAC-SHA256 (hex, 64 chars) do valor normalizado, com uma chave
    -- SEPARADA da chave de cifragem -- serve só para deduplicação/
    -- detecção de conflito sem decifrar; nunca permite recuperar o
    -- valor em claro sozinho.
    hash_auxiliar         TEXT NOT NULL,

    -- Versão das chaves (Fernet + HMAC) que produziram esta linha --
    -- NUNCA parte da chave primária (mesmo raciocínio de 0003).
    -- Permite rotação: backfill sob uma versão nova produz linhas
    -- novas (valor/hash diferentes), sem tocar as linhas da versão
    -- anterior.
    versao_chave           TEXT NOT NULL,

    -- Proveniência: de onde este contato foi observado -- nunca
    -- "Airtable" hardcoded como valor único; texto livre para permitir
    -- origem futura (ex. cadastro direto por operador) sem migration
    -- nova.
    origem                 TEXT NOT NULL,

    criado_em              TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT contato_colaborador_observado_pkey
        PRIMARY KEY (colaborador_id, canal)
);

COMMENT ON TABLE contato_colaborador_observado IS
    'Contato Canônico de Colaborador V1: mapeia colaborador_id + canal '
    '(ex.: whatsapp) para um contato CIFRADO DE FORMA REVERSÍVEL '
    '(Fernet). Persistente e consultável sem Airtable em runtime -- '
    'Airtable serve só de bootstrap transitório (ver '
    'magnata_os/documental/importacao_lote/adapters/'
    'bootstrap_contato_colaborador_airtable.py). Valor em claro nunca '
    'nesta tabela; chave de cifragem sempre fora deste banco.';

COMMENT ON COLUMN contato_colaborador_observado.colaborador_id IS
    'Identidade opaca do Colaborador -- HOJE o Airtable record id de '
    'Funcionários (mesmo valor de identidade_colaborador_observada.'
    'colaborador_id, migration 0003). LEGADO/TRANSICIONAL -- nunca a '
    'identidade definitiva do Magnata OS.';

COMMENT ON COLUMN contato_colaborador_observado.valor_cifrado IS
    'Token Fernet (AES-128-CBC + HMAC autenticado) do valor '
    'normalizado -- nunca o valor em claro. Decifragem só no ponto '
    'autorizado de resolução (contato_colaborador.py::'
    'resolver_contato_colaborador_para_ordem).';

COMMENT ON COLUMN contato_colaborador_observado.hash_auxiliar IS
    'HMAC-SHA256 (hex) do valor normalizado, com chave separada da '
    'chave de cifragem -- só para deduplicação/conflito, nunca para '
    'recuperar o valor.';

CREATE INDEX IF NOT EXISTS idx_contato_colaborador_observado_colaborador_id
    ON contato_colaborador_observado (colaborador_id);

CREATE INDEX IF NOT EXISTS idx_contato_colaborador_observado_versao_chave
    ON contato_colaborador_observado (versao_chave);
