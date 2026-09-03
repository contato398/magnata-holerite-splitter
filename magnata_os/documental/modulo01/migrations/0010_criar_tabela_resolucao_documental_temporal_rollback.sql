-- Magnata OS Documental — Modulo 01, missão "IDENTIDADE TEMPORAL
-- DOCUMENTAL DA FOLHA/CARTÃO DE PONTO V1"
-- Rollback explícito da migration 0010
-- (0010_criar_tabela_resolucao_documental_temporal.sql)
--
-- NAO aplicada automaticamente -- companheira de reversão pronta para
-- uso manual se a migration 0010 precisar ser desfeita antes de uma
-- correção futura (mesmo padrão de
-- 0009_itens_importacao_lote_rollback.sql e
-- documental/alocacao/migrations/0001_..._rollback.sql). Nunca editar
-- 0010_criar_tabela_resolucao_documental_temporal.sql para "desfazer"
-- -- este arquivo é o único caminho de reversão.
--
-- Nunca toca `documentos` nem `eventos_documentais` -- tabelas de fases
-- anteriores já tratadas como aplicadas (CLAUDE.md raiz §7, "não editar
-- migration já aplicada"); esta migration nunca alterou o schema delas,
-- só referenciou `documentos` via FK e reaproveitou `eventos_
-- documentais` para escrita (nunca para schema).

DROP INDEX IF EXISTS idx_resolucao_documental_temporal_competencia;
DROP INDEX IF EXISTS idx_resolucao_documental_temporal_colaborador_id;
DROP TABLE IF EXISTS resolucao_documental_temporal;
