-- Migration 0004: Criar tabela execucoes_prestacao
--
-- Fundação persistente de execução de ciclos de Prestação de Contas.
--
-- Identidade: execucao_prestacao_id (UUID opaco).
-- Propósito: Rastrear execuções concretas de Prestação, anteriores a ações filhas.
-- Constraints: estado restrito a (INICIADA, CONCLUIDA, FALHA).
--             concluido_em NOT NULL se estado = CONCLUIDA/FALHA.
--
-- Índices: competencia_base, estado para queries operacionais.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'magnata_orquestrador'
        AND table_name = 'execucoes_prestacao'
    ) THEN
        CREATE TABLE magnata_orquestrador.execucoes_prestacao (
            execucao_prestacao_id TEXT PRIMARY KEY,
            competencia_base VARCHAR(7) NOT NULL,
            estado VARCHAR(32) NOT NULL
                CHECK (estado IN ('INICIADA', 'CONCLUIDA', 'FALHA')),
            origem VARCHAR(64),
            criado_em TIMESTAMP WITH TIME ZONE NOT NULL,
            atualizado_em TIMESTAMP WITH TIME ZONE NOT NULL,
            concluido_em TIMESTAMP WITH TIME ZONE
        );

        -- Índices para queries operacionais
        CREATE INDEX idx_execucoes_prestacao_competencia
            ON magnata_orquestrador.execucoes_prestacao(competencia_base);
        CREATE INDEX idx_execucoes_prestacao_estado
            ON magnata_orquestrador.execucoes_prestacao(estado);
        CREATE INDEX idx_execucoes_prestacao_criado_em
            ON magnata_orquestrador.execucoes_prestacao(criado_em DESC);
    END IF;
END $$;
