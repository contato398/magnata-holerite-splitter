-- Magnata OS Documental — Modulo 01, Fase 2
-- Migration 0004: indices de suporte a consulta

CREATE INDEX IF NOT EXISTS idx_documentos_status
    ON documentos (status);

CREATE INDEX IF NOT EXISTS idx_eventos_documentais_documento_id_timestamp
    ON eventos_documentais (documento_id, "timestamp");

CREATE INDEX IF NOT EXISTS idx_eventos_documentais_correlation_id
    ON eventos_documentais (correlation_id);
