-- Magnata OS — RH/Admissão, missão "CADASTRO DE COLABORADOR
-- PERSISTENTE V1" — correção pré-merge do PR #215
-- Migration 0003: rh_admissao_historico_correcao_local_trabalho
-- (histórico append-only real de correção de local_trabalho)
--
-- NÃO APLICADA por nenhuma ferramenta -- mesma disciplina de 0001/0002.
--
-- CONTEXTO: até esta correção, uma correção de `local_trabalho` já
-- definido (`dominio_cadastro_colaborador.
-- aplicar_determinacao_local_trabalho`, produz
-- `EventoCorrecaoLocalTrabalho`) só ia para log estruturado -- nunca
-- uma tabela persistida. Violação de `/CLAUDE.md` §4 ("Histórico é
-- imutável e append-only") -- log não é histórico consultável nem
-- garantidamente retido. Esta migration fecha essa lacuna. Ver
-- docs/decisoes/cadastro-colaborador-persistente-v1.md §4/§6.
--
-- MODELO: uma linha por `EventoCorrecaoLocalTrabalho`
-- (dominio_cadastro_colaborador.py) -- mesmos campos, sem cifra (local
-- de trabalho e motivo de correção não são CPF/nome; mesma disciplina
-- já aplicada em `EventoCorrecaoLocalTrabalho.como_evidencia`, que
-- nunca inclui dado pessoal sensível).
--
-- "QUEM REGISTROU": `determinado_por` já é um campo OBRIGATÓRIO em
-- `DeterminacaoLocalTrabalho`/`EventoCorrecaoLocalTrabalho`
-- (identificador do operador humano, nunca dado do colaborador,
-- validado como texto não vazio em
-- `EventoCorrecaoLocalTrabalho.__post_init__`) -- reaproveitado aqui
-- como NOT NULL, não como campo novo opcional: o conceito de "quem"
-- já existe neste domínio (não existe, hoje, um conceito de
-- usuário/operador AUTENTICADO mais forte que isso -- ex.: uma FK para
-- uma tabela de operadores -- no Magnata OS; `determinado_por`
-- continua sendo texto livre, mesma limitação já aceita pelo domínio
-- antes desta migration).
--
-- FK para rh_admissao_colaboradores: um evento de correção nunca pode
-- existir para um colaborador_id inexistente -- imposto pelo banco,
-- mesmo padrão de `eventos_documentais.documento_id` (migration 0002
-- do Módulo 01).
--
-- APPEND-ONLY IMPOSTO A NÍVEL DE BANCO (não só disciplina de código):
-- trigger que bloqueia UPDATE/DELETE, mesmo padrão exato de
-- `documental/modulo01/migrations/0003_trigger_eventos_append_only.sql`
-- (reproduzido aqui, não importado -- é SQL, não há import entre
-- migrations). Nome de função/trigger específico deste pacote para
-- nunca colidir com o trigger do Módulo 01 no mesmo banco.

CREATE TABLE IF NOT EXISTS rh_admissao_historico_correcao_local_trabalho (
    evento_id                BIGSERIAL PRIMARY KEY,

    colaborador_id            TEXT NOT NULL
        REFERENCES rh_admissao_colaboradores (colaborador_id),

    local_trabalho_anterior   TEXT NOT NULL CHECK (local_trabalho_anterior <> ''),
    local_trabalho_novo       TEXT NOT NULL CHECK (local_trabalho_novo <> ''),
    motivo_correcao           TEXT NOT NULL CHECK (motivo_correcao <> ''),

    -- Identificador do operador humano que determinou a correção --
    -- já obrigatório no domínio (ver cabeçalho desta migration).
    determinado_por           TEXT NOT NULL CHECK (determinado_por <> ''),

    -- Quando a determinação humana foi tomada (entrada do chamador --
    -- `DeterminacaoLocalTrabalho.determinado_em`). Distinto de
    -- `registrado_em` (quando ESTA LINHA foi gravada pelo banco).
    determinado_em             TIMESTAMPTZ NOT NULL,

    registrado_em              TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE rh_admissao_historico_correcao_local_trabalho IS
    'Histórico append-only real de toda correção de local_trabalho já '
    'definido (EventoCorrecaoLocalTrabalho, '
    'dominio_cadastro_colaborador.py). Nunca UPDATE nem DELETE em '
    'operação normal -- ver trigger '
    'rh_admissao_historico_correcao_local_trabalho_bloquear_update_delete '
    'nesta mesma migration (garantia de banco, não só disciplina de '
    'código, mesmo padrão de eventos_documentais/migration 0003 do '
    'Módulo 01).';

COMMENT ON COLUMN rh_admissao_historico_correcao_local_trabalho.determinado_por IS
    'Identificador do operador humano que determinou a correção -- '
    'texto livre (mesmo formato já usado em DeterminacaoLocalTrabalho). '
    'Nenhum conceito de usuário/operador autenticado mais forte (ex.: '
    'FK para tabela de operadores) existe hoje no Magnata OS -- mesma '
    'limitação já aceita pelo domínio antes desta migration, não uma '
    'omissão nova.';

CREATE INDEX IF NOT EXISTS idx_rh_admissao_historico_correcao_local_trabalho_colaborador_id
    ON rh_admissao_historico_correcao_local_trabalho (colaborador_id);

CREATE OR REPLACE FUNCTION rh_admissao_historico_correcao_local_trabalho_bloquear_update_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'rh_admissao_historico_correcao_local_trabalho e append-only: % nao e permitido (evento_id=%)',
        TG_OP, COALESCE(OLD.evento_id, NULL);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_rh_admissao_historico_correcao_bloquear_update
    ON rh_admissao_historico_correcao_local_trabalho;
CREATE TRIGGER trg_rh_admissao_historico_correcao_bloquear_update
    BEFORE UPDATE ON rh_admissao_historico_correcao_local_trabalho
    FOR EACH ROW EXECUTE FUNCTION rh_admissao_historico_correcao_local_trabalho_bloquear_update_delete();

DROP TRIGGER IF EXISTS trg_rh_admissao_historico_correcao_bloquear_delete
    ON rh_admissao_historico_correcao_local_trabalho;
CREATE TRIGGER trg_rh_admissao_historico_correcao_bloquear_delete
    BEFORE DELETE ON rh_admissao_historico_correcao_local_trabalho
    FOR EACH ROW EXECUTE FUNCTION rh_admissao_historico_correcao_local_trabalho_bloquear_update_delete();
