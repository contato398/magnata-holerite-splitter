-- Magnata OS Documental — Modulo 01, Fase 2
-- Migration 0001: tabela documentos
--
-- NAO aplicada automaticamente por nenhuma ferramenta nesta fase. Aplicar
-- manualmente (ou via ferramenta de migracao apropriada) quando o adapter
-- Postgres for de fato conectado a um banco real -- fora do escopo desta
-- fase de fundacao. Ver MAGNATA_OS_DOCUMENTAL_MODULO01_FASE2.md.

CREATE TABLE IF NOT EXISTS documentos (
    documento_id      TEXT PRIMARY KEY,
    arquivo_original  TEXT NOT NULL,
    nome_original     TEXT NOT NULL,
    mime_type         TEXT NOT NULL,
    tamanho           BIGINT NOT NULL CHECK (tamanho >= 0),
    hash_sha256       TEXT NOT NULL,
    origem            TEXT NOT NULL,
    recebido_em       TIMESTAMPTZ NOT NULL,
    lote_id           TEXT,
    status            TEXT NOT NULL CHECK (status IN (
                          'RECEBIDO', 'REGISTRADO', 'DUPLICADO',
                          'AGUARDANDO_PROCESSAMENTO', 'EM_PROCESSAMENTO',
                          'EM_REVISAO', 'ERRO'
                      )),
    correlation_id    TEXT NOT NULL,
    criado_em         TIMESTAMPTZ NOT NULL,
    atualizado_em     TIMESTAMPTZ NOT NULL,

    CONSTRAINT documentos_hash_sha256_unique UNIQUE (hash_sha256)
);

COMMENT ON TABLE documentos IS
    'Magnata OS Documental - Modulo 01: entidade central Documento. '
    'Ver magnata_os/documental/modulo01/dominio.py';

COMMENT ON CONSTRAINT documentos_hash_sha256_unique ON documentos IS
    'Garante idempotencia por hash a nivel de banco -- base da atomicidade '
    'real de salvar_se_ausente_por_hash sob concorrencia entre processos.';
