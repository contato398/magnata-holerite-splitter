-- Magnata OS Documental — Modulo 01, Fase 3
-- Migration 0008: indices de consulta da esteira
--
-- Cobrem exatamente as consultas de consultas_esteira.py: por lote,
-- por etapa, por situacao, documentos bloqueados e documentos parados
-- (tempo na etapa atual). CREATE INDEX IF NOT EXISTS ja e idempotente
-- nativamente no Postgres.

CREATE INDEX IF NOT EXISTS idx_estados_esteira_lote_id
    ON estados_esteira_documental (lote_id);

CREATE INDEX IF NOT EXISTS idx_estados_esteira_etapa_atual
    ON estados_esteira_documental (etapa_atual);

CREATE INDEX IF NOT EXISTS idx_estados_esteira_situacao
    ON estados_esteira_documental (situacao);

-- Indice parcial -- so indexa as linhas efetivamente bloqueadas, que
-- sao a minoria consultada com mais frequencia (paineis de pendencia).
CREATE INDEX IF NOT EXISTS idx_estados_esteira_bloqueados
    ON estados_esteira_documental (atualizado_em)
    WHERE situacao = 'BLOQUEADO';

-- Suporta "documentos parados a partir de X" (consultas_esteira.py:
-- documentos_parados_a_partir_de) -- filtro por entrou_na_etapa_em.
CREATE INDEX IF NOT EXISTS idx_estados_esteira_entrou_na_etapa_em
    ON estados_esteira_documental (entrou_na_etapa_em);

CREATE INDEX IF NOT EXISTS idx_lotes_documentais_criado_em
    ON lotes_documentais (criado_em DESC);
