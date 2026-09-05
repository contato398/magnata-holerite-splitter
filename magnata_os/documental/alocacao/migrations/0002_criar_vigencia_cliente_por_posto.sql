-- Magnata OS — Persistência de vigência histórica: Posto ↔ Cliente
-- Migration 0002: tabela vigencia_cliente_por_posto
--
-- INERTE: nenhum módulo aplica esta migration automaticamente -- mesma
-- disciplina de magnata_os/documental/modulo01/migrations/ e
-- magnata_os/orquestrador/migrations/ (ver migrations/CLAUDE.md do
-- modulo01, que rege a convenção seguida aqui). Aplicar manualmente
-- quando um Postgres real for provisionado -- gate humano separado,
-- nunca produção nesta missão.
--
-- Contexto (missão "FUNDAÇÃO TEMPORAL POSTO ↔ CLIENTE V1"): fecha o gap
-- real confirmado por auditoria -- não existe representação histórica da
-- relação Posto/UNIDADE_POSTO ↔ Cliente com vigência independente.
-- FonteVinculosPrestacaoAirtableShadow resolve cliente a partir de
-- unidade_posto HOJE, mas é snapshot apenas (nenhum campo de período).
-- Esta migration cria a verdade histórica durável no Postgres próprio.
--
-- SEPARAÇÃO CONCEITUAL EXPLÍCITA (missão anterior, auditada):
--   alocacao = "vigência do COLABORADOR por POSTO"
--   vigencia_cliente_por_posto = "vigência do CLIENTE por POSTO"
-- (nunca misturar as 2 na mesma tabela -- causaria confusão temporal)
--
-- INVARIANTE CENTRAL:
-- Um mesmo POSTO NÃO PODE pertencer a DOIS CLIENTES em períodos
-- sobrepostos (constraint EXCLUDE abaixo). Múltiplos postos podem ser
-- vigentes simultaneamente para o mesmo colaborador (rateio legítimo),
-- mas cada POSTO em particular tem 1 cliente por período.
--
-- LACUNAS SÃO PERMITIDAS E SIGNIFICAM RELAÇÃO HISTÓRICA NÃO COMPROVADA.
-- Se um período de alocação não tem correspondência em vigencia_cliente_por_posto,
-- a relação cliente fica NULL — não é preenchida automaticamente, refletindo
-- dado histórico que ainda não foi capturado ou comprovado.
--
-- BOOTSTRAP (FORA DO ESCOPO DESTA MIGRATION):
-- A população inicial desta tabela será feita em missão separada,
-- apenas com snapshot Airtable como evidência. Nenhuma história
-- anterior a essa captura será inventada. Períodos anteriores
-- continuarão indefinidos (cliente_id = NULL) até captura histórica real.
--
-- DESVIO DELIBERADO DO ESBOÇO ORIGINAL (registrado, não escondido):
-- BANCO_PROPRIO_MODELO.md esboçava id como uuid nativo. Esta migration
-- usa TEXT (gerado pela aplicação), mesma convenção JÁ ESTABELECIDA em
-- TODAS as migrations deste projeto (documentos.documento_id,
-- alocacao.id, vigencia_cliente_por_posto.id, todas TEXT).

CREATE TABLE IF NOT EXISTS vigencia_cliente_por_posto (
    id                  TEXT PRIMARY KEY,

    -- Identidade opaca do Posto/Unidade -- mesma forma conceitual de
    -- alocacao.posto_id, já usada em toda a classificacao/ como
    -- ReferenciaCanonica('UNIDADE_POSTO', local_id). Sem FK própria,
    -- pois tabela posto_trabalho não existe (fora do escopo desta
    -- missão) -- mesma disciplina de alocacao.
    posto_id            TEXT NOT NULL,

    -- Identidade opaca do Cliente -- mesma convenção de
    -- alocacao via vinculo_trabalhista.colaborador_id. Sem FK: tabela
    -- cliente não existe, só a identidade opaca já usada em toda
    -- classificacao/ (ReferenciaCanonica('CLIENTE', cliente_id)).
    cliente_id          TEXT NOT NULL,

    -- Período REAL de vigência da relação Posto ↔ Cliente.
    -- NULL vigente_ate = relação vigente agora (mesma disciplina
    -- alocacao, vinculo_trabalhista). Transição comprovada (ex., posto
    -- muda de cliente na data D) requer 2 rows:
    --   - anterior: vigente_ate = D-1
    --   - novo: vigente_de = D
    -- Nenhuma sobreposição do MESMO POSTO em períodos diferentes (constraint abaixo).
    -- Lacunas de histórico (períodos sem cliente comprovado retornando cliente_id=NULL)
    -- são permitidas e tratadas pelo resolvedor temporal.
    vigente_de          DATE NOT NULL,
    vigente_ate         DATE,

    -- Rastreabilidade de origem/evidência da relação.
    -- Valores esperados (aberto a futuras missões):
    --   'airtable_snapshot_inicial' (bootstrap)
    --   'captura_humana' (entrada manual)
    --   'documento_evidencia' (extraído de documento)
    -- etc. Permite auditar cada linha para origem de verdade.
    origem_evidencia    TEXT,

    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT vigencia_cliente_por_posto_vigencia_valida
        CHECK (vigente_ate IS NULL OR vigente_ate >= vigente_de)
);

COMMENT ON TABLE vigencia_cliente_por_posto IS
    'Vigência histórica da relação Posto/UNIDADE_POSTO ↔ Cliente. '
    'Reutiliza a mesma disciplina de alocacao: períodos fechados, '
    'append-only histórico, nenhuma mudança de fato sem nova linha. '
    'Um mesmo POSTO não pode pertencer a DOIS CLIENTES em intervalos '
    'sobrepostos (constraint EXCLUDE abaixo). Múltiplos clientes de '
    'postos DIFERENTES são permitidos (rateio legítimo). Ver missão '
    'fundacao-temporal-posto-cliente-v1.md.';

COMMENT ON COLUMN vigencia_cliente_por_posto.posto_id IS
    'Identidade opaca do Posto/Unidade (Airtable record id de "Locais", '
    'mesma ReferenciaCanonica(''UNIDADE_POSTO'', local_id) já usada em '
    'vinculo_unidade_prestacao.py) -- sem FK própria, tabela '
    'posto_trabalho não existe ainda no Postgres.';

COMMENT ON COLUMN vigencia_cliente_por_posto.cliente_id IS
    'Identidade opaca do Cliente (Airtable record id, mesma '
    'ReferenciaCanonica(''CLIENTE'', cliente_id) já usada em toda a '
    'classificacao/) -- sem FK própria, tabela cliente não existe.';

COMMENT ON COLUMN vigencia_cliente_por_posto.vigente_ate IS
    'NULL = relação vigente agora (mesma disciplina de alocacao '
    'e vinculo_trabalhista). Mudança comprovada = fechar vigente_ate '
    'da linha antiga e abrir nova linha -- nunca um UPDATE que apaga '
    'o histórico (histórico é sempre append-only nesta tabela).';

COMMENT ON COLUMN vigencia_cliente_por_posto.origem_evidencia IS
    'Rastreabilidade: de onde veio a informação desta linha. Permite '
    'auditar "bootstrap Airtable", "captura humana", etc. Sem validação '
    'de enum nesta missão -- aberto a futuras categorias.';

-- Impede 2 relações sobrepostas para o MESMO POSTO (possessão duplicada/
-- conflitante) -- mas permite que MÚLTIPLOS POSTOS tenham clientes
-- vigentes simultaneamente (rateio legítimo entre postos, não clientes
-- dentro do mesmo posto). Reutiliza a extensão btree_gist já habilitada
-- em migration 0001. Idempotente pelo mesmo padrão (bloco DO + pg_constraint).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'vigencia_cliente_por_posto_sem_sobreposicao'
    ) THEN
        ALTER TABLE vigencia_cliente_por_posto
            ADD CONSTRAINT vigencia_cliente_por_posto_sem_sobreposicao
            EXCLUDE USING gist (
                posto_id WITH =,
                daterange(vigente_de, vigente_ate, '[]') WITH &&
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_vigencia_cliente_por_posto_posto_id
    ON vigencia_cliente_por_posto (posto_id);

CREATE INDEX IF NOT EXISTS idx_vigencia_cliente_por_posto_cliente_id
    ON vigencia_cliente_por_posto (cliente_id);

-- Suporta consulta central: "qual cliente estava vigente para este
-- posto nesta janela de datas" -- varredura por posto_id já coberta
-- pelo índice acima; este índice adicional acelera a checagem de
-- vigência (consulta "vigente_de <= X AND (vigente_ate IS NULL OR vigente_ate >= Y)").
CREATE INDEX IF NOT EXISTS idx_vigencia_cliente_por_posto_vigencia
    ON vigencia_cliente_por_posto (posto_id, vigente_de, vigente_ate);
