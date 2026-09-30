-- Rollback da migration 0003_criar_historico_correcao_local_trabalho.sql
-- NÃO APLICADA automaticamente -- mesma disciplina das demais
-- migrations do Magnata OS.

DROP TRIGGER IF EXISTS trg_rh_admissao_historico_correcao_bloquear_delete
    ON rh_admissao_historico_correcao_local_trabalho;
DROP TRIGGER IF EXISTS trg_rh_admissao_historico_correcao_bloquear_update
    ON rh_admissao_historico_correcao_local_trabalho;
DROP FUNCTION IF EXISTS rh_admissao_historico_correcao_local_trabalho_bloquear_update_delete();

DROP INDEX IF EXISTS idx_rh_admissao_historico_correcao_local_trabalho_colaborador_id;
DROP TABLE IF EXISTS rh_admissao_historico_correcao_local_trabalho;
