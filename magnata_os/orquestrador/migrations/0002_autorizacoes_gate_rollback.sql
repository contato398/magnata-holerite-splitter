-- Rollback da migration 0002 do Grande Orquestrador.
-- Destrutivo: nunca executar automaticamente. Exige backup e gate humano.

DROP TABLE magnata_orquestrador.autorizacoes_gate;
DROP FUNCTION magnata_orquestrador.bloquear_mutacao_autorizacao_gate();
