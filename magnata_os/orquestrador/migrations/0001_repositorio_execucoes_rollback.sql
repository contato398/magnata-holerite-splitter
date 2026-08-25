-- Rollback da migration 0001 do Grande Orquestrador.
-- Destrutivo: nunca executar automaticamente. Exige backup e gate humano.

DROP SCHEMA magnata_orquestrador CASCADE;
