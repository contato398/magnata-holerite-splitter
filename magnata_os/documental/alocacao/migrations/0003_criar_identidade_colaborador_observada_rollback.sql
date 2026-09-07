-- Rollback da migration 0003_criar_identidade_colaborador_observada.sql
-- INERTE -- nunca aplicada automaticamente. Mesma disciplina das
-- demais migrations deste pacote.

DROP INDEX IF EXISTS idx_identidade_colaborador_observada_versao_chave;
DROP INDEX IF EXISTS idx_identidade_colaborador_observada_colaborador_id;
DROP TABLE IF EXISTS identidade_colaborador_observada;
