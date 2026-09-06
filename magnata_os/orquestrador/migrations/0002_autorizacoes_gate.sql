-- Magnata OS — Grande Orquestrador
-- Migration 0002: autorizacoes humanas de gate como fatos append-only.
--
-- INERTE: nenhum modulo aplica esta migration automaticamente.
-- Depende da migration 0001 (schema/tabela de execucoes).
-- Aplicacao em qualquer banco real exige gate humano separado.

CREATE TABLE magnata_orquestrador.autorizacoes_gate (
    autorizacao_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES magnata_orquestrador.execucoes(event_id),
    preview_id TEXT NOT NULL,
    decisao TEXT NOT NULL CHECK (decisao IN ('AUTORIZADO', 'RECUSADO')),
    ator_referencia TEXT NOT NULL,
    registrado_em TIMESTAMPTZ NOT NULL,
    proveniencia TEXT NOT NULL,
    CONSTRAINT autorizacoes_gate_evento_preview_unico UNIQUE (event_id, preview_id),
    CONSTRAINT autorizacoes_gate_autorizacao_id_tamanho CHECK (char_length(autorizacao_id) BETWEEN 1 AND 500),
    CONSTRAINT autorizacoes_gate_event_id_tamanho CHECK (char_length(event_id) BETWEEN 1 AND 500),
    CONSTRAINT autorizacoes_gate_preview_id_tamanho CHECK (char_length(preview_id) BETWEEN 1 AND 500),
    CONSTRAINT autorizacoes_gate_ator_tamanho CHECK (char_length(ator_referencia) BETWEEN 1 AND 500),
    CONSTRAINT autorizacoes_gate_proveniencia_tamanho CHECK (char_length(proveniencia) BETWEEN 1 AND 500)
);

CREATE INDEX autorizacoes_gate_evento_idx
    ON magnata_orquestrador.autorizacoes_gate (event_id, registrado_em);

CREATE FUNCTION magnata_orquestrador.bloquear_mutacao_autorizacao_gate()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'autorizacao de gate e append-only';
END;
$$;

CREATE TRIGGER autorizacoes_gate_append_only
BEFORE UPDATE OR DELETE ON magnata_orquestrador.autorizacoes_gate
FOR EACH ROW EXECUTE FUNCTION magnata_orquestrador.bloquear_mutacao_autorizacao_gate();
