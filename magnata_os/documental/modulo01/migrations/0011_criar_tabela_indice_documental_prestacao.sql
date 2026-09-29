-- Magnata OS Documental — Modulo 01, missão "PRESTAÇÃO -> ESTEIRA
-- DOCUMENTAL INTELIGENTE" (J3 da auditoria Gate J)
-- Migration 0011: tabela indice_documental_prestacao
--
-- NAO aplicada automaticamente por nenhuma ferramenta (mesma disciplina
-- de 0001-0010). Aplicação exige autorização humana específica em
-- .magnata/migration-authorizations/ (gate de governança) -- ver
-- docs/decisoes/localizacao-documental-pdf-composto-v1.md §6.
--
-- O QUE É: o índice interno "documento <-> cliente/competência/tipo/
-- colaborador" que faltava (auditoria-gate-j-composicao-prestacao-v1.md
-- §3.2 e item J3). Uma linha = um ItemInventarioPrestacao
-- (classificacao/prestacao_readiness.py) já CONFERIDO pelo corredor
-- contra a necessidade que o buscou -- só documento elegível entra
-- (produtor: composicao_ciclo_persistente_prestacao.
-- _alimentar_indice_documental). É acelerador de localização, nunca
-- fonte de verdade da validação: o corredor continua conferindo.
--
-- Extensão relacional MÍNIMA sobre `documentos` (migration 0001) --
-- nunca uma segunda entidade documental. Sem CPF, sem nome: só ids
-- opacos (cliente_id, colaborador_id) e vocabulário canônico.
--
-- IDEMPOTÊNCIA: identidade lógica canônica do item
-- (`ItemInventarioPrestacao.identidade_logica` = documento, cliente,
-- colaborador). Um documento broadcast gera 1 linha por cliente; um
-- documento fatiado por colaborador, 1 linha por colaborador -- nunca
-- colapsados. Reprocessar nunca duplica (INSERT ... ON CONFLICT DO
-- NOTHING no adapter). Append-only: o adapter nunca faz UPDATE nem
-- DELETE.

CREATE TABLE IF NOT EXISTS indice_documental_prestacao (
    documento_id      TEXT NOT NULL REFERENCES documentos (documento_id),
    cliente_id        TEXT NOT NULL CHECK (cliente_id <> ''),
    -- '' = documento sem granularidade de colaborador (Extrato, FGTS,
    -- DCTFWeb...). Nunca NULL: a identidade lógica precisa ser comparável
    -- num UNIQUE simples.
    colaborador_id    TEXT NOT NULL DEFAULT '',
    competencia       TEXT NOT NULL CHECK (competencia ~ '^[0-9]{4}-[0-9]{2}$'),
    tipo_documental   TEXT NOT NULL CHECK (tipo_documental <> ''),
    registrado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_indice_documental_prestacao_identidade
        UNIQUE (documento_id, cliente_id, colaborador_id)
);

-- Consulta da localização: listar(cliente, competencia).
CREATE INDEX IF NOT EXISTS idx_indice_documental_prestacao_cliente_competencia
    ON indice_documental_prestacao (cliente_id, competencia);
