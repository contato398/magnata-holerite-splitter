-- Rollback para 0004_execucoes_prestacao.sql
--
-- IMPORTANTE: Sem CASCADE
-- Se houver FKs futuras, o rollback FALHA explicitamente.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'magnata_orquestrador'
        AND table_name = 'execucoes_prestacao'
    ) THEN
        DROP TABLE magnata_orquestrador.execucoes_prestacao;
    END IF;
END $$;
