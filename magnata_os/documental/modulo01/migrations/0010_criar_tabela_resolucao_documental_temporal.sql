-- Magnata OS Documental — Modulo 01, missão "IDENTIDADE TEMPORAL
-- DOCUMENTAL DA FOLHA/CARTÃO DE PONTO V1"
-- Migration 0010: tabela resolucao_documental_temporal
--
-- NAO aplicada automaticamente por nenhuma ferramenta nesta fase (mesma
-- disciplina de 0001-0009). Aplicar manualmente quando um Postgres real
-- for de fato conectado -- fora do escopo desta missão.
--
-- Proposta e auditoria completas em
-- docs/decisoes/identidade-temporal-ponto-auditoria-v1.md. Extensão
-- relacional MÍNIMA sobre `documentos` (já existente, migration 0001) —
-- NUNCA uma segunda entidade documental. Fecha a lacuna real: nenhuma
-- migration existente liga competência/período/colaborador a um
-- documento_id.
--
-- DECISÃO DE MODELO (auditada e reforçada por revisão independente):
-- cliente/posto NUNCA é coluna aqui. Um PDF de Folha de Ponto cobre um
-- INTERVALO de dias, e o colaborador pode ter tido mais de uma alocação
-- válida dentro desse intervalo (transferência de posto/cliente no meio
-- do ciclo) -- uma coluna única seria ativamente ERRADA nesse caso (não
-- representaria os múltiplos clientes legítimos sem duplicar a linha ou
-- inventar uma escolha arbitrária). Cliente é sempre resolvido em tempo
-- de consulta, por JOIN com `alocacao` (migration
-- documental/alocacao/migrations/0001) usando colaborador_id +
-- interseção de [periodo_inicio, periodo_fim] -- nunca denormalizado
-- aqui.
--
-- IDEMPOTÊNCIA: UNIQUE(documento_id) -- 1 resolução canônica por
-- documento (mesmo padrão de documentos.hash_sha256 UNIQUE); reprocessar
-- o mesmo documento nunca cria uma segunda linha.

CREATE TABLE IF NOT EXISTS resolucao_documental_temporal (
    resolucao_id      TEXT PRIMARY KEY,
    documento_id      TEXT NOT NULL REFERENCES documentos (documento_id),
    tipo_documental   TEXT NOT NULL,

    -- Identidade opaca do colaborador -- mesmo padrão de
    -- vinculo_trabalhista.colaborador_id (documental/alocacao migration
    -- 0001): sem FK própria, tabela colaborador não existe ainda no
    -- Postgres. NULL só quando o documento não tem granularidade de
    -- colaborador (fora do escopo desta missão -- Folha de Ponto sempre
    -- tem).
    colaborador_id    TEXT,

    -- Período REAL extraído do conteúdo do documento -- nunca do nome
    -- do arquivo, data de upload ou cadastro atual. NULL quando a
    -- extração não encontrou/validou um período (estado_resolucao
    -- reflete isso).
    periodo_inicio    DATE,
    periodo_fim       DATE,

    -- Competência derivada do fechamento do período (AAAA-MM), mesmo
    -- vocabulário canônico já usado em toda magnata_os/classificacao/.
    competencia       TEXT,

    -- Vocabulário de EstadoResolucaoDimensao (classificacao/contratos.py)
    -- -- nenhum vocabulário novo.
    estado_resolucao  TEXT NOT NULL CHECK (estado_resolucao IN (
                          'NAO_AVALIADA', 'NAO_APLICAVEL', 'RESOLVIDA',
                          'AMBIGUA', 'NAO_ENCONTRADA', 'CONFLITO',
                          'INVALIDA', 'ERRO_TECNICO'
                      )),

    -- Proveniência sanitizada (EvidenciaSanitizada) -- nunca CPF/nome,
    -- nunca conteúdo bruto do PDF.
    evidencias        JSONB NOT NULL DEFAULT '{}'::jsonb,

    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT resolucao_documental_temporal_periodo_valido
        CHECK (periodo_fim IS NULL OR periodo_inicio IS NULL OR periodo_fim >= periodo_inicio),

    CONSTRAINT resolucao_documental_temporal_documento_unico
        UNIQUE (documento_id)
);

COMMENT ON TABLE resolucao_documental_temporal IS
    'Identidade temporal (período/competência/colaborador) de 1 documento '
    'já existente em `documentos` -- nunca uma segunda entidade documental. '
    'Cliente/posto NUNCA é coluna aqui -- sempre resolvido em tempo de '
    'consulta via alocacao (interseção de período). Ver '
    'docs/decisoes/identidade-temporal-ponto-auditoria-v1.md.';

COMMENT ON COLUMN resolucao_documental_temporal.documento_id IS
    'FK obrigatória para documentos.documento_id -- uma resolução temporal '
    'nunca existe para um Documento inexistente, imposto pelo banco.';

COMMENT ON CONSTRAINT resolucao_documental_temporal_documento_unico
    ON resolucao_documental_temporal IS
    'Idempotência: reprocessar o mesmo documento nunca cria uma segunda '
    'resolução -- mesma disciplina de documentos.hash_sha256 UNIQUE.';

CREATE INDEX IF NOT EXISTS idx_resolucao_documental_temporal_colaborador_id
    ON resolucao_documental_temporal (colaborador_id);

CREATE INDEX IF NOT EXISTS idx_resolucao_documental_temporal_competencia
    ON resolucao_documental_temporal (competencia);
