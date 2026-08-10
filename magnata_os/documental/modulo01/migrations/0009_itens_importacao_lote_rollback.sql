-- Magnata OS Documental — Modulo 01, Fase 4
-- Rollback explicito da migration 0009 (itens_importacao_lote.sql)
--
-- NAO aplicada automaticamente -- companheira de reversao pronta para uso
-- manual se a migration 0009 precisar ser desfeita antes de uma correcao
-- futura (ver migrations/CLAUDE.md, "Rollback explicito"). Nunca editar
-- 0009_itens_importacao_lote.sql para "desfazer" -- este arquivo e o
-- unico caminho de reversao.
--
-- Ordem inversa de dependencia (item -> versionamento -> indice de lote).
-- Nunca toca documentos, lotes_documentais ou eventos_documentais --
-- essas tabelas sao de fases anteriores ja tratadas como aplicadas
-- (CLAUDE.md raiz §7, "nao editar migration ja aplicada") e esta migration
-- nunca alterou o schema delas (so leu/indexou via expressao).

DROP TRIGGER IF EXISTS trg_eventos_itens_importacao_lote_bloquear_delete ON eventos_itens_importacao_lote;
DROP TRIGGER IF EXISTS trg_eventos_itens_importacao_lote_bloquear_update ON eventos_itens_importacao_lote;
DROP FUNCTION IF EXISTS eventos_itens_importacao_lote_bloquear_update_delete();
DROP INDEX IF EXISTS idx_eventos_itens_importacao_lote_documento_id;
DROP INDEX IF EXISTS idx_eventos_itens_importacao_lote_lote_id;
DROP INDEX IF EXISTS idx_eventos_itens_importacao_lote_item_timestamp;
DROP TABLE IF EXISTS eventos_itens_importacao_lote;

DROP INDEX IF EXISTS idx_itens_importacao_lote_identidade_ingestao;
DROP INDEX IF EXISTS idx_itens_importacao_lote_situacao;
DROP INDEX IF EXISTS idx_itens_importacao_lote_documento_id;
DROP TABLE IF EXISTS itens_importacao_lote;

DROP INDEX IF EXISTS idx_versionamento_logico_versao_unica;
DROP INDEX IF EXISTS idx_versionamento_logico_substitui_unico;
DROP INDEX IF EXISTS idx_versionamento_logico_documento_logico_id;
DROP TABLE IF EXISTS documentos_versionamento_logico;

DROP INDEX IF EXISTS idx_lotes_documentais_execucao_unica;
