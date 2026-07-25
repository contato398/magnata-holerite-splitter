-- Magnata OS Documental — Modulo 01, Fase 3
-- Migration 0007: vinculo formal de documentos.lote_id -> lotes_documentais
--
-- documentos.lote_id ja existe desde a migration 0001 (Fase 2), mas sem
-- FK -- so um TEXT nullable. Esta migration adiciona a constraint agora
-- que lotes_documentais existe (migration 0005). NULL continua permitido
-- (FK padrao do Postgres nao exige NOT NULL) -- e exatamente isso que
-- preserva compatibilidade com documentos criados antes da Fase 3, que
-- nunca tiveram lote_id preenchido.
--
-- Idempotente via bloco DO + checagem em pg_constraint -- ALTER TABLE
-- ADD CONSTRAINT nao aceita "IF NOT EXISTS" nativamente no Postgres.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'documentos_lote_id_fkey'
    ) THEN
        ALTER TABLE documentos
            ADD CONSTRAINT documentos_lote_id_fkey
            FOREIGN KEY (lote_id) REFERENCES lotes_documentais (lote_id);
    END IF;
END $$;

COMMENT ON CONSTRAINT documentos_lote_id_fkey ON documentos IS
    'Vinculo formal com lotes_documentais (Fase 3). NULL permitido -- '
    'documentos anteriores a Fase 3 nunca tiveram lote_id preenchido.';
