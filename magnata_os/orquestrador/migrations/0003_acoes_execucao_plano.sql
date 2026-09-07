-- Magnata OS — Grande Orquestrador
-- Migration 0003: checkpoint persistente por acao de PlanoDisparo autorizado.
--
-- INERTE: nenhum modulo aplica esta migration automaticamente. Aplicacao em
-- banco real exige revisao do blob final, backup e nova autorizacao humana.
-- Nesta fase, o SQL existe apenas para validacao em PostgreSQL efemero.

BEGIN;

CREATE TABLE magnata_orquestrador.acoes_execucao_plano (
    acao_execucao_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES magnata_orquestrador.execucoes(event_id),
    preview_id TEXT NOT NULL,
    autorizacao_id TEXT NOT NULL
        REFERENCES magnata_orquestrador.autorizacoes_gate(autorizacao_id),
    ordem INTEGER NOT NULL CHECK (ordem > 0),
    tipo TEXT NOT NULL CHECK (tipo IN (
        'texto', 'video', 'documento', 'imagem', 'audio'
    )),
    destinatario_sha256 TEXT NOT NULL,
    nome_sha256 TEXT,
    conteudo_sha256 TEXT,
    texto_sha256 TEXT,
    estado TEXT NOT NULL DEFAULT 'PENDING' CHECK (estado IN (
        'PENDING', 'EXECUTING', 'SUCCEEDED',
        'FAILED_RETRYABLE', 'FAILED_FINAL'
    )),
    attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    proxima_tentativa_em TIMESTAMPTZ,
    claim_sha256 TEXT,
    reivindicado_em TIMESTAMPTZ,
    ultimo_erro_classe TEXT,
    resultado_referencia TEXT,
    evidencia_sha256 TEXT,
    criado_em TIMESTAMPTZ NOT NULL,
    atualizado_em TIMESTAMPTZ NOT NULL,
    concluido_em TIMESTAMPTZ,
    CONSTRAINT acoes_execucao_plano_gate_exato
        FOREIGN KEY (event_id, preview_id)
        REFERENCES magnata_orquestrador.autorizacoes_gate(event_id, preview_id),
    CONSTRAINT acoes_execucao_plano_identidade_unica
        UNIQUE (event_id, preview_id, ordem, destinatario_sha256),
    CONSTRAINT acoes_execucao_id_sha256
        CHECK (acao_execucao_id ~ '^[0-9a-f]{64}$'),
    CONSTRAINT acoes_execucao_destinatario_sha256
        CHECK (destinatario_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT acoes_execucao_nome_sha256
        CHECK (nome_sha256 IS NULL OR nome_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT acoes_execucao_conteudo_sha256
        CHECK (conteudo_sha256 IS NULL OR conteudo_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT acoes_execucao_texto_sha256
        CHECK (texto_sha256 IS NULL OR texto_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT acoes_execucao_claim_sha256
        CHECK (claim_sha256 IS NULL OR claim_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT acoes_execucao_evidencia_sha256
        CHECK (evidencia_sha256 IS NULL OR evidencia_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT acoes_execucao_identidade_conteudo
        CHECK (
            (tipo = 'texto' AND texto_sha256 IS NOT NULL AND conteudo_sha256 IS NULL)
            OR
            (tipo <> 'texto' AND conteudo_sha256 IS NOT NULL)
        ),
    CONSTRAINT acoes_execucao_terminal_coerente
        CHECK (
            (estado IN ('SUCCEEDED', 'FAILED_FINAL') AND concluido_em IS NOT NULL)
            OR
            (estado NOT IN ('SUCCEEDED', 'FAILED_FINAL') AND concluido_em IS NULL)
        )
);

CREATE INDEX acoes_execucao_plano_elegiveis_idx
    ON magnata_orquestrador.acoes_execucao_plano
        (event_id, preview_id, estado, proxima_tentativa_em, ordem);

COMMIT;
