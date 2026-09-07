-- Rollback da migration 0003 de acoes persistentes do PlanoDisparo.
-- Destrutivo: nunca executar automaticamente. Exige backup e gate humano.

BEGIN;
DROP TABLE magnata_orquestrador.acoes_execucao_plano;
COMMIT;
