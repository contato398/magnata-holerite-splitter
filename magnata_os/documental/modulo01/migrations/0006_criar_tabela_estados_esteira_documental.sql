-- Magnata OS Documental — Modulo 01, Fase 3
-- Migration 0006: tabela estados_esteira_documental
--
-- Depende das migrations 0001 (documentos) e 0005 (lotes_documentais).
-- Uma linha por documento_id -- estado ATUAL da esteira, nao historico
-- (o historico de transicoes vai para eventos_documentais via eventos
-- ESTEIRA_*, reaproveitando a tabela da migration 0002/Fase 2 em vez de
-- duplicar uma tabela de eventos so para a esteira).
--
-- lote_id e NULLABLE de proposito: documentos legados (anteriores a
-- Fase 3, ou que nunca passaram por ServicoCriacaoLote) nunca tem
-- estado de esteira nenhum -- nao ha linha nesta tabela para eles. Para
-- os que TEM linha aqui via um fluxo futuro que os vincule sem lote,
-- lote_id pode ficar NULL. Ver "Documentos legados" em
-- MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3.md.

CREATE TABLE IF NOT EXISTS estados_esteira_documental (
    documento_id      TEXT PRIMARY KEY REFERENCES documentos (documento_id),
    lote_id           TEXT REFERENCES lotes_documentais (lote_id),
    etapa_atual       TEXT NOT NULL CHECK (etapa_atual IN (
                          'ENTRADA', 'REGISTRO', 'CLASSIFICACAO', 'SEPARACAO', 'IDENTIFICACAO',
                          'VALIDACAO', 'MONTAGEM_PACOTE', 'DISTRIBUICAO', 'CONFIRMACAO', 'AUDITORIA'
                      )),
    situacao          TEXT NOT NULL CHECK (situacao IN (
                          'AGUARDANDO', 'EM_PROCESSAMENTO', 'EM_REVISAO', 'PRONTO',
                          'CONCLUIDO', 'ERRO', 'BLOQUEADO'
                      )),

    -- motivo_bloqueio (MotivoBloqueio) -- colunas prefixadas, todas
    -- NULL quando situacao <> 'BLOQUEADO'.
    motivo_bloqueio_codigo                     TEXT,
    motivo_bloqueio_descricao                  TEXT,
    motivo_bloqueio_detalhe_tecnico            TEXT,
    motivo_bloqueio_resolvivel_automaticamente BOOLEAN,

    -- proxima_acao (ProximaAcao) -- colunas prefixadas; NULL quando nao
    -- ha proxima acao (ex.: etapa AUDITORIA concluida, terminal).
    proxima_acao_acao        TEXT,
    proxima_acao_tipo        TEXT CHECK (proxima_acao_tipo IN ('AUTOMATICA', 'HUMANA')),
    proxima_acao_prazo       TIMESTAMPTZ,
    proxima_acao_responsavel TEXT,

    entrou_na_etapa_em TIMESTAMPTZ NOT NULL,
    atualizado_em      TIMESTAMPTZ NOT NULL,
    correlation_id     TEXT NOT NULL,

    CONSTRAINT estados_esteira_motivo_bloqueio_consistente CHECK (
        (situacao <> 'BLOQUEADO' AND motivo_bloqueio_codigo IS NULL)
        OR (situacao = 'BLOQUEADO' AND motivo_bloqueio_codigo IS NOT NULL)
    )
);

COMMENT ON TABLE estados_esteira_documental IS
    'Magnata OS Documental - Modulo 01, Fase 3: estado OPERACIONAL atual de um '
    'Documento na esteira -- separado de documentos.status (estado TECNICO, '
    'Fase 1/2) de proposito. Ver dominio_esteira.py.';

COMMENT ON COLUMN estados_esteira_documental.lote_id IS
    'Nullable -- documentos legados (anteriores a Fase 3) nunca tem lote. '
    'FK para lotes_documentais quando presente.';
