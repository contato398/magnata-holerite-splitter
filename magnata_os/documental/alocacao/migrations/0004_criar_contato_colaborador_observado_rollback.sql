-- Rollback da migration 0004_criar_contato_colaborador_observado.sql
-- INERTE -- nunca aplicada automaticamente. Mesma disciplina das
-- demais migrations deste pacote.

DROP INDEX IF EXISTS idx_contato_colaborador_observado_versao_chave;
DROP INDEX IF EXISTS idx_contato_colaborador_observado_colaborador_id;
DROP TABLE IF EXISTS contato_colaborador_observado;
