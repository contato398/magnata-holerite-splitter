-- Magnata OS Documental — Modulo 01, Fase 3
-- Migration 0005: tabela lotes_documentais
--
-- NAO aplicada automaticamente por nenhuma ferramenta nesta fase --
-- mesma disciplina das migrations 0001-0004 (Fase 2). Aplicar
-- manualmente quando um adapter Postgres para a esteira for construido
-- (fora do escopo desta fase). Ver MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3.md.

CREATE TABLE IF NOT EXISTS lotes_documentais (
    lote_id             TEXT PRIMARY KEY,
    origem              TEXT NOT NULL,
    recebido_em         TIMESTAMPTZ NOT NULL,
    quantidade_arquivos INTEGER NOT NULL CHECK (quantidade_arquivos >= 0),
    situacao            TEXT NOT NULL CHECK (situacao IN (
                            'AGUARDANDO', 'EM_PROCESSAMENTO', 'EM_REVISAO', 'PRONTO',
                            'CONCLUIDO', 'ERRO', 'BLOQUEADO'
                        )),
    correlation_id      TEXT NOT NULL,
    criado_em           TIMESTAMPTZ NOT NULL,
    atualizado_em       TIMESTAMPTZ NOT NULL,
    metadados           JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE lotes_documentais IS
    'Magnata OS Documental - Modulo 01, Fase 3: agrupa N arquivos recebidos '
    'numa mesma operacao de entrada. Ver magnata_os/documental/modulo01/dominio_esteira.py';
