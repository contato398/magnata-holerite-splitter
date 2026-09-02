-- Rollback da migration 0001_criar_auditoria_operacoes.sql
-- Idempotente (IF EXISTS) -- seguro rodar contra um banco onde a
-- migration nunca foi aplicada.

DROP TRIGGER IF EXISTS trg_auditoria_operacoes_bloquear_delete ON auditoria_operacoes;
DROP TRIGGER IF EXISTS trg_auditoria_operacoes_bloquear_update ON auditoria_operacoes;
DROP FUNCTION IF EXISTS auditoria_operacoes_bloquear_update_delete();
DROP TABLE IF EXISTS auditoria_operacoes;
