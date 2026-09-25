-- Destrutivo: nunca executar automaticamente.
-- Remove somente o que a migration 0007 criou. Sem CASCADE -- se algo
-- além desta migration passar a depender da tabela, o rollback falha
-- explicitamente em vez de arrastar dependências ocultas. A função
-- bloquear_mutacao_auditoria pertence à 0001 e NÃO é removida aqui.

BEGIN;

DROP TRIGGER IF EXISTS correlacao_documento_prestacao_append_only
    ON magnata_orquestrador.correlacao_documento_prestacao;

DROP TABLE magnata_orquestrador.correlacao_documento_prestacao;

COMMIT;
