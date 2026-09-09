-- Destrutivo: nunca executar automaticamente.
-- Remove somente a extensao criada pela migration 0004.

BEGIN;

ALTER TABLE magnata_orquestrador.acoes_execucao_plano
    DROP CONSTRAINT ck_acoes_execucao_plano_envelope_sha256;

ALTER TABLE magnata_orquestrador.acoes_execucao_plano
    DROP COLUMN envelope_sha256;

COMMIT;
