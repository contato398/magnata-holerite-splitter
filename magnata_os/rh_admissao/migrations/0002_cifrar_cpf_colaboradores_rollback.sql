-- Rollback da migration 0002_cifrar_cpf_colaboradores.sql
-- NÃO APLICADA automaticamente -- mesma disciplina das demais
-- migrations do Magnata OS.
--
-- Reverte para o formato de 0001 (`cpf` TEXT em claro) -- só é seguro
-- se não houver linha real com `cpf_cifrado` gravado (mesma ressalva
-- de "sem backfill" da migration 0002: nenhuma foi aplicada em
-- ambiente real nesta missão).

ALTER TABLE rh_admissao_colaboradores ADD COLUMN IF NOT EXISTS cpf TEXT;

ALTER TABLE rh_admissao_colaboradores DROP COLUMN IF EXISTS cpf_cifrado;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'rh_admissao_colaboradores_cpf_nao_vazio'
    ) THEN
        ALTER TABLE rh_admissao_colaboradores
            ADD CONSTRAINT rh_admissao_colaboradores_cpf_nao_vazio CHECK (cpf <> '');
    END IF;
END $$;

ALTER TABLE rh_admissao_colaboradores ALTER COLUMN cpf SET NOT NULL;
