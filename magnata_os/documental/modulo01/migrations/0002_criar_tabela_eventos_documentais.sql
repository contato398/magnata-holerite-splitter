-- Magnata OS Documental — Modulo 01, Fase 2
-- Migration 0002: tabela eventos_documentais (historico append-only)
--
-- Depende da migration 0001 (FK para documentos).

CREATE TABLE IF NOT EXISTS eventos_documentais (
    evento_id         BIGSERIAL PRIMARY KEY,
    documento_id      TEXT NOT NULL REFERENCES documentos (documento_id),
    evento            TEXT NOT NULL,
    status_anterior   TEXT,
    status_novo       TEXT,
    "timestamp"       TIMESTAMPTZ NOT NULL,
    correlation_id    TEXT NOT NULL,
    detalhes          JSONB NOT NULL DEFAULT '{}'::jsonb,
    registrado_em     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE eventos_documentais IS
    'Historico append-only de eventos de um Documento. Nunca UPDATE nem '
    'DELETE em operacao normal -- ver migration 0003 (trigger que bloqueia '
    'isso a nivel de banco).';

COMMENT ON COLUMN eventos_documentais.documento_id IS
    'Vinculo obrigatorio: FK para documentos.documento_id. Um evento nunca '
    'pode existir para um Documento inexistente -- imposto pelo banco.';
