-- Magnata OS — Autenticação Administrativa Compartilhada
-- Migration 0001: auditoria_operacoes (trilha "quem fez", FASE 6 da
-- missão "AUTENTICAÇÃO ADMINISTRATIVA COMPARTILHADA V1")
--
-- INERTE: nenhum módulo aplica esta migration automaticamente -- mesma
-- disciplina de magnata_os/documental/modulo01/migrations/ e
-- magnata_os/documental/alocacao/migrations/. Aplicar manualmente
-- quando um Postgres real for provisionado -- gate humano separado,
-- NUNCA produção nesta missão.
--
-- Contexto: fecha o 2º gate registrado em
-- docs/decisoes/entrada-alocacao-postgres-v1.md (FASE 7) -- nem
-- `origem_confirmacao` é persistido hoje em `alocacao`/
-- `vinculo_trabalhista`, muito menos identidade de quem confirmou.
-- `eventos_documentais` (Módulo 01) foi avaliada e rejeitada como
-- reuso: tem FK obrigatória para `documentos`, não serve para
-- colaborador/posto (ou qualquer outro agregado futuro) sem uma
-- migration própria de qualquer forma.
--
-- GENÉRICA de propósito -- não é "auditoria de alocação", é a trilha
-- "quem fez" de QUALQUER operação administrativa autenticada do
-- Magnata OS (alocação é só o primeiro consumidor real). `operacao` e
-- `referencia_agregado` são texto opaco (nunca FK para uma tabela de
-- um módulo específico) -- exatamente o mesmo desenho já usado por
-- `alocacao.posto_id` ("posto_id sem FK própria", decisão já
-- registrada naquela migration) -- aqui pela mesma razão: acoplar este
-- schema compartilhado ao schema de um módulo específico contradiria o
-- próprio propósito de ser compartilhado.
--
-- Nenhum dado pessoal além do e-mail administrativo (LGPD -- já é o
-- mesmo dado que a sessão Google já verificou; nunca senha, nunca
-- token, nunca cookie). `erro_codigo` é sempre um nome de classe de
-- exceção (ex.: 'ConflitoTemporalEventoError'), nunca a mensagem livre
-- da exceção -- mesma disciplina de
-- modulo01/api/erros.py::ErroInternoNaoExposto (nunca vazar detalhe
-- técnico/interno numa trilha que pode ser lida por um Auditor).

CREATE TABLE IF NOT EXISTS auditoria_operacoes (
    id                      TEXT PRIMARY KEY,

    -- Identidade de quem executou -- sujeito_id pode ser NULL (nem
    -- todo provedor de identidade garante um id estável distinto do
    -- e-mail); email NUNCA é NULL (é a própria prova de identidade
    -- verificada pelo provedor OIDC).
    sujeito_id              TEXT,
    email                   TEXT NOT NULL,
    perfil                  TEXT NOT NULL,

    operacao                TEXT NOT NULL,
    referencia_agregado     TEXT,

    resultado               TEXT NOT NULL CHECK (resultado IN ('SUCESSO', 'ERRO')),
    -- Nome da classe de exceção, nunca a mensagem livre -- ver nota no
    -- topo do arquivo. NULL quando resultado = 'SUCESSO'.
    erro_codigo             TEXT,

    criado_em               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auditoria_operacoes_sujeito_id
    ON auditoria_operacoes (sujeito_id);
CREATE INDEX IF NOT EXISTS idx_auditoria_operacoes_operacao_criado_em
    ON auditoria_operacoes (operacao, criado_em);
CREATE INDEX IF NOT EXISTS idx_auditoria_operacoes_referencia_agregado
    ON auditoria_operacoes (referencia_agregado);

-- Append-only por garantia de banco, não só disciplina de código --
-- mesmo padrão de modulo01/migrations/0003_trigger_eventos_append_only.sql.
CREATE OR REPLACE FUNCTION auditoria_operacoes_bloquear_update_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'auditoria_operacoes e append-only: % nao e permitido (id=%)',
        TG_OP, COALESCE(OLD.id, NULL);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_auditoria_operacoes_bloquear_update ON auditoria_operacoes;
CREATE TRIGGER trg_auditoria_operacoes_bloquear_update
    BEFORE UPDATE ON auditoria_operacoes
    FOR EACH ROW EXECUTE FUNCTION auditoria_operacoes_bloquear_update_delete();

DROP TRIGGER IF EXISTS trg_auditoria_operacoes_bloquear_delete ON auditoria_operacoes;
CREATE TRIGGER trg_auditoria_operacoes_bloquear_delete
    BEFORE DELETE ON auditoria_operacoes
    FOR EACH ROW EXECUTE FUNCTION auditoria_operacoes_bloquear_update_delete();
