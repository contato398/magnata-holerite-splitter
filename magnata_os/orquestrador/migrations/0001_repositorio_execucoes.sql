-- Magnata OS — Grande Orquestrador
-- Migration 0001: repositorio duravel de execucoes e auditorias.
--
-- INERTE: nenhum modulo aplica esta migration automaticamente. Provisionar
-- banco, fornecer secret e aplicar schema exigem gates humanos separados.

CREATE SCHEMA IF NOT EXISTS magnata_orquestrador;

CREATE TABLE magnata_orquestrador.execucoes (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    estado TEXT NOT NULL CHECK (estado IN (
        'RECEIVED', 'VALIDATED', 'CLASSIFIED', 'WAITING_GATE', 'EXECUTING',
        'SUCCEEDED', 'FAILED_RETRYABLE', 'FAILED_FINAL', 'IGNORED', 'SUPERSEDED'
    )),
    nivel_autonomia INTEGER NOT NULL CHECK (nivel_autonomia BETWEEN -1 AND 5),
    acao TEXT NOT NULL,
    resultado TEXT,
    evidencia TEXT,
    attempt INTEGER NOT NULL CHECK (attempt >= 0),
    next_retry_at TIMESTAMPTZ,
    last_error_classe TEXT,
    last_error_at TIMESTAMPTZ,
    criado_em TIMESTAMPTZ NOT NULL,
    atualizado_em TIMESTAMPTZ NOT NULL,
    evento_json TEXT,
    manualmente_reiniciado_por TEXT,
    manualmente_reiniciado_em TIMESTAMPTZ,
    motivo_reinicio_manual TEXT
);

CREATE TABLE magnata_orquestrador.auditoria (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES magnata_orquestrador.execucoes(event_id),
    estado_anterior TEXT NOT NULL,
    estado_novo TEXT NOT NULL,
    registrado_em TIMESTAMPTZ NOT NULL,
    motivo TEXT
);

CREATE TABLE magnata_orquestrador.auditoria_recuperacao (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES magnata_orquestrador.execucoes(event_id),
    decisao TEXT NOT NULL,
    estado_observado TEXT NOT NULL,
    registrado_em TIMESTAMPTZ NOT NULL,
    motivo TEXT NOT NULL,
    evidencia TEXT
);

CREATE INDEX execucoes_estado_retry_idx
    ON magnata_orquestrador.execucoes (estado, next_retry_at);
CREATE INDEX auditoria_evento_idx
    ON magnata_orquestrador.auditoria (event_id, id);
CREATE INDEX auditoria_recuperacao_evento_idx
    ON magnata_orquestrador.auditoria_recuperacao (event_id, id);

CREATE FUNCTION magnata_orquestrador.bloquear_mutacao_auditoria()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'auditoria do Orquestrador e append-only';
END;
$$;

CREATE TRIGGER auditoria_append_only
BEFORE UPDATE OR DELETE ON magnata_orquestrador.auditoria
FOR EACH ROW EXECUTE FUNCTION magnata_orquestrador.bloquear_mutacao_auditoria();

CREATE TRIGGER auditoria_recuperacao_append_only
BEFORE UPDATE OR DELETE ON magnata_orquestrador.auditoria_recuperacao
FOR EACH ROW EXECUTE FUNCTION magnata_orquestrador.bloquear_mutacao_auditoria();
