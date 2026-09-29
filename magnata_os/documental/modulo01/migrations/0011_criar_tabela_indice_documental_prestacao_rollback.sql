-- Magnata OS Documental — Modulo 01
-- Rollback explícito da migration 0011
-- (0011_criar_tabela_indice_documental_prestacao.sql)
--
-- NAO aplicada automaticamente -- companheira de reversão para uso
-- manual (mesmo padrão de 0009/0010). O índice é acelerador de
-- localização: removê-lo não perde documento nem histórico (tudo fica
-- em `documentos`/`eventos_documentais`); a localização volta a
-- depender da busca por conteúdo. Nunca toca `documentos`.

DROP INDEX IF EXISTS idx_indice_documental_prestacao_cliente_competencia;
DROP TABLE IF EXISTS indice_documental_prestacao;
