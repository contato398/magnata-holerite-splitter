-- Magnata OS — Prestação de Contas (J3)
-- Migration 0007: índice de correlação Documento interno ↔ escopo da
-- Prestação (cliente, competência, tipo documental, colaborador opcional).
--
-- INERTE: nenhum módulo aplica esta migration automaticamente. Aplicação
-- em banco real exige revisão do blob final, backup e nova autorização
-- humana (mesmo processo de 0001-0006). NÃO aplicar em produção nesta
-- missão. Decisão completa: docs/decisoes/correlacao-documento-prestacao-v1.md.
--
-- DEPENDÊNCIA DECLARADA: `documentos` (modulo01 migration 0001, schema
-- padrão) precisa existir -- a FK abaixo é a garantia, no banco, de que
-- nenhuma correlação aponta para um Documento inexistente (nem para um
-- record-id do Airtable fingindo ser `documento_id` interno).
--
-- POR QUE NÃO UMA COLUNA `cliente_id` EM `resolucao_documental_temporal`
-- (modulo01 0010): lá cliente/posto NUNCA é propriedade única da
-- resolução (um período pode cobrir 2 alocações) -- decisão original
-- preservada. Esta tabela guarda RELAÇÕES (1 documento -> N escopos),
-- nunca uma segunda entidade documental: o Documento canônico continua
-- único em `documentos`.
--
-- FORMA: append-only (mesmo padrão de 0006 e de auditoria/0001). Cada
-- linha é uma OBSERVAÇÃO do estado de UMA relação lógica:
--   relacao_id = sha256 canônico de (documento_id, cliente_id, competencia,
--                tipo_documental, colaborador_id|vazio) -- a identidade
--                lógica completa; o mesmo documento pode ter N relações
--                legítimas (broadcast, vínculo múltiplo, transferência de
--                posto no período) e cada uma é uma relacao_id distinta.
--   sequencia  = versão da relação POR ORIGEM (1, 2, ...), UNIQUE
--                (relacao_id, origem, sequencia) -- a mesma relação pode
--                ser observada por 2 produtores (ex.: corredor e
--                resolução temporal de ponto), cada um com sua própria
--                história; replay e concorrência nunca duplicam uma
--                versão; o produtor só insere quando o estado MUDA
--                (advisory lock por documento+origem na mesma transação).
--   estado     = VIGENTE (a última resolução do documento sustenta a
--                relação) | SUPERADA (reprocessamento não a sustenta
--                mais: foi para revisão, ou nova evidência mudou o
--                escopo). O histórico nunca é apagado nem editado.
-- O estado corrente de uma relação, por origem, é a linha de maior
-- `sequencia`; a relação está disponível se VIGENTE em alguma origem.

BEGIN;

CREATE TABLE magnata_orquestrador.correlacao_documento_prestacao (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    relacao_id TEXT NOT NULL CHECK (relacao_id ~ '^[0-9a-f]{64}$'),
    sequencia INTEGER NOT NULL CHECK (sequencia >= 1),
    documento_id TEXT NOT NULL REFERENCES documentos (documento_id),
    cliente_id TEXT NOT NULL CHECK (length(btrim(cliente_id)) > 0),
    competencia TEXT NOT NULL CHECK (competencia ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    tipo_documental TEXT NOT NULL CHECK (length(btrim(tipo_documental)) > 0),
    -- NULL = relação de nível cliente (documento sem colaborador).
    colaborador_id TEXT CHECK (colaborador_id IS NULL OR length(btrim(colaborador_id)) > 0),
    estado TEXT NOT NULL CHECK (estado IN ('VIGENTE', 'SUPERADA')),
    -- Produtor que observou a relação (ex.: corredor da Prestação,
    -- resolução temporal de ponto). A reconciliação de um reprocessamento
    -- é sempre por (documento_id, origem): um produtor nunca supera
    -- relações observadas por outro.
    origem TEXT NOT NULL CHECK (length(btrim(origem)) > 0),
    -- Proveniência sanitizada: hash das resoluções semânticas que
    -- sustentam a observação -- nunca CPF, nome, e-mail ou texto do PDF.
    evidencia_sha256 TEXT CHECK (evidencia_sha256 IS NULL OR evidencia_sha256 ~ '^[0-9a-f]{64}$'),
    registrado_em TIMESTAMPTZ NOT NULL,

    CONSTRAINT correlacao_documento_prestacao_versao_unica UNIQUE (relacao_id, origem, sequencia)
);

COMMENT ON TABLE magnata_orquestrador.correlacao_documento_prestacao IS
    'J3: relações Documento interno -> (cliente, competência, tipo, '
    'colaborador opcional) da Prestação. Append-only; estado corrente = '
    'maior sequencia por (relacao_id, origem). Nunca uma segunda entidade documental. '
    'Ver docs/decisoes/correlacao-documento-prestacao-v1.md.';

-- Consumidor: candidatos por necessidade (cliente, competência, tipo).
CREATE INDEX correlacao_documento_prestacao_escopo_idx
    ON magnata_orquestrador.correlacao_documento_prestacao
    (cliente_id, competencia, tipo_documental, relacao_id, sequencia DESC);

-- Produtor: reconciliação do reprocessamento por documento+origem.
CREATE INDEX correlacao_documento_prestacao_documento_idx
    ON magnata_orquestrador.correlacao_documento_prestacao
    (documento_id, origem, relacao_id, sequencia DESC);

-- Append-only: reaproveita a função já existente (migration 0001), como 0006.
CREATE TRIGGER correlacao_documento_prestacao_append_only
BEFORE UPDATE OR DELETE ON magnata_orquestrador.correlacao_documento_prestacao
FOR EACH ROW EXECUTE FUNCTION magnata_orquestrador.bloquear_mutacao_auditoria();

COMMIT;
