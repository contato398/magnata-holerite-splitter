-- Rollback da migration 0001_criar_tabela_colaboradores.sql
-- NÃO APLICADA automaticamente -- mesma disciplina das demais
-- migrations do Magnata OS.

DROP INDEX IF EXISTS idx_rh_admissao_colaboradores_situacao_cadastro;
DROP TABLE IF EXISTS rh_admissao_colaboradores;
