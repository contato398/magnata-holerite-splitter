-- Destrutivo: nunca executar automaticamente.
-- Remove somente a tabela criada pela migration 0006. Sem CASCADE --
-- se algo além desta migration passar a depender da tabela, o rollback
-- deve falhar explicitamente em vez de arrastar dependências ocultas.

BEGIN;

DROP TRIGGER IF EXISTS conclusao_obrigacao_assinatura_append_only
    ON magnata_orquestrador.conclusao_obrigacao_assinatura;

DROP TABLE magnata_orquestrador.conclusao_obrigacao_assinatura;

COMMIT;
