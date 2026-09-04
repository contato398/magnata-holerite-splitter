-- Magnata OS — Rollback de vigência histórica: Posto ↔ Cliente
-- Migration Rollback 0002: remove tabela vigencia_cliente_por_posto
--
-- Esta migration desfaz EXCLUSIVAMENTE os objetos criados por 0002_criar_vigencia_cliente_por_posto.sql
-- Ordem segura: índices primeiro, depois constraint, depois tabela.
--
-- IDEMPOTENTE: pode ser executada múltiplas vezes sem erro.

-- Remove índices (em qualquer ordem)
DROP INDEX IF EXISTS idx_vigencia_cliente_por_posto_vigencia;
DROP INDEX IF EXISTS idx_vigencia_cliente_por_posto_cliente_id;
DROP INDEX IF EXISTS idx_vigencia_cliente_por_posto_posto_id;

-- Remove constraint EXCLUDE (bloco idempotente, mesmo padrão de 0002)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'vigencia_cliente_por_posto_sem_sobreposicao'
    ) THEN
        ALTER TABLE vigencia_cliente_por_posto
            DROP CONSTRAINT vigencia_cliente_por_posto_sem_sobreposicao;
    END IF;
END $$;

-- Remove constraint CHECK (se existir)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'vigencia_cliente_por_posto_vigencia_valida'
    ) THEN
        ALTER TABLE vigencia_cliente_por_posto
            DROP CONSTRAINT vigencia_cliente_por_posto_vigencia_valida;
    END IF;
END $$;

-- Remove tabela (sem CASCADE -- relacionamentos futuros precisam ser gerenciados explicitamente)
DROP TABLE IF EXISTS vigencia_cliente_por_posto;

-- Confirmação de sucesso do rollback
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_name = 'vigencia_cliente_por_posto'
    ) THEN
        RAISE NOTICE 'Rollback 0002 completado: tabela vigencia_cliente_por_posto removida com sucesso';
    ELSE
        RAISE WARNING 'Rollback 0002: tabela vigencia_cliente_por_posto ainda existe após DROP';
    END IF;
END $$;
