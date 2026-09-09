-- Magnata OS — Grande Orquestrador
-- Migration 0004: referencia content-addressed do envelope executavel V1.
--
-- INERTE: nao aplicar automaticamente nem em producao. A coluna permanece
-- nullable para que acoes legadas da migration 0003 continuem preservadas,
-- mas inelegiveis para o executor recuperavel V1.

BEGIN;

ALTER TABLE magnata_orquestrador.acoes_execucao_plano
    ADD COLUMN envelope_sha256 TEXT;

ALTER TABLE magnata_orquestrador.acoes_execucao_plano
    ADD CONSTRAINT ck_acoes_execucao_plano_envelope_sha256
    CHECK (
        envelope_sha256 IS NULL
        OR envelope_sha256 ~ '^[0-9a-f]{64}$'
    );

COMMIT;
