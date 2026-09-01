-- Magnata OS — Persistência temporal canônica de Alocação
-- Rollback explícito da migration 0001
--
-- NÃO aplicada automaticamente -- companheira de reversão pronta para
-- uso manual, mesma disciplina de
-- magnata_os/documental/modulo01/migrations/CLAUDE.md ("Rollback
-- explícito") e do rollback já existente da migration 0009 do modulo01.
-- Nunca editar 0001_criar_vinculo_trabalhista_e_alocacao.sql para
-- "desfazer" -- este arquivo é o único caminho de reversão.
--
-- Ordem inversa de dependência (alocacao referencia vinculo_trabalhista,
-- nunca o contrário).

ALTER TABLE IF EXISTS alocacao
    DROP CONSTRAINT IF EXISTS alocacao_sem_sobreposicao_mesmo_posto;

DROP INDEX IF EXISTS idx_alocacao_vigencia;
DROP INDEX IF EXISTS idx_alocacao_vinculo_trabalhista_id;
DROP TABLE IF EXISTS alocacao;

ALTER TABLE IF EXISTS vinculo_trabalhista
    DROP CONSTRAINT IF EXISTS vinculo_trabalhista_sem_sobreposicao;

DROP INDEX IF EXISTS idx_vinculo_trabalhista_colaborador_id;
DROP TABLE IF EXISTS vinculo_trabalhista;

-- Nunca remove a extensão btree_gist aqui -- pode já estar em uso por
-- outra migration/tabela deste ou de outro módulo; DROP EXTENSION é
-- fora do escopo de reversão desta migration específica (mesma cautela
-- já registrada no rollback da migration 0009 do modulo01, que nunca
-- toca tabelas de fases anteriores).
