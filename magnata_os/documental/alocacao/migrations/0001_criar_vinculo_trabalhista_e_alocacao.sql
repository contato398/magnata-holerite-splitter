-- Magnata OS — Persistência temporal canônica de Alocação
-- Migration 0001: vinculo_trabalhista (dependência estrutural mínima) + alocacao
--
-- INERTE: nenhum módulo aplica esta migration automaticamente -- mesma
-- disciplina de magnata_os/documental/modulo01/migrations/ e
-- magnata_os/orquestrador/migrations/ (ver migrations/CLAUDE.md do
-- modulo01, que rege a convenção seguida aqui). Aplicar manualmente
-- quando um Postgres real for provisionado -- gate humano separado,
-- nunca produção nesta missão.
--
-- Contexto (missão "IMPLEMENTAÇÃO ESTRUTURAL DA ENTIDADE alocacao COM
-- VIGÊNCIA HISTÓRICA"): fecha o maior bloqueio real do segundo live SKY
-- Junho/2026 -- UNIDADE_POSTO nunca provável para competência histórica
-- porque o vínculo Funcionário->Local do Airtable é snapshot corrente,
-- sem vigência (achado já documentado, antes desta missão, em
-- docs/magnata-os/central-command/BANCO_PROPRIO_MODELO.md §5.1 e
-- MAGNATA_OS_ENTIDADES.md §5, entidade Alocação).
--
-- ─── Cadeia canônica preservada (decisão explícita, não um atalho) ────────
--
--   colaborador ──< vinculo_trabalhista ──< alocacao >── posto (opaco)
--
-- `vinculo_trabalhista` é criado NESTA migration só como DEPENDÊNCIA
-- ESTRUTURAL MÍNIMA de `alocacao` (autorização explícita da missão,
-- Opção A: "não usar alocacao.colaborador_id como atalho... a cadeia
-- canônica deve permanecer colaborador -> vinculo_trabalhista ->
-- alocacao -> posto") -- NUNCA como fundação de um módulo de RH/folha de
-- pagamento completo. Por isso, deliberadamente ausentes (autorização
-- explícita: "não inventar salário, cargo, regime, matrícula ou outras
-- dimensões se não forem necessárias para esta missão"):
--   - cargo, salário, regime, matrícula, empresa (sempre a Magnata nesta
--     fase -- constante, não coluna);
--   - "situação" como campo próprio -- já representada, sem duplicação,
--     por `data_desligamento IS NULL` (mesma disciplina de
--     `alocacao.vigente_ate IS NULL` = vigente agora).
--
-- ─── Desvio deliberado do esboço original (registrado, não escondido) ────
--
-- BANCO_PROPRIO_MODELO.md §5.1 esboça `id uuid PRIMARY KEY`. Esta
-- migration usa `id TEXT PRIMARY KEY` (gerado pela aplicação, nunca por
-- default do banco) -- mesma convenção JÁ estabelecida em TODAS as
-- migrations existentes do projeto (documentos.documento_id,
-- execucoes.event_id, itens_importacao_lote.item_importacao_id, todas
-- TEXT) -- nenhuma delas usa uuid nativo nem gen_random_uuid()/
-- uuid_generate_v4() (que exigiriam confirmar versão/extensão do
-- Postgres real, ainda não provisionado -- ver migrations/CLAUDE.md do
-- modulo01, "sem sintaxe que só funcione numa versão não confirmada").
--
-- ─── Regra canônica V1 de sobreposição -- DECISÃO HUMANA EXPLÍCITA ───────
--
-- BANCO_PROPRIO_MODELO.md §5.1 esboça a constraint de não-sobreposição
-- como `EXCLUDE USING gist (vinculo_trabalhista_id WITH =, daterange(...)
-- WITH &&)` -- impediria QUALQUER sobreposição para o mesmo vínculo.
-- MAGNATA_OS_ENTIDADES.md §5 (entidade Alocação) documenta
-- explicitamente: "Pode haver mais de uma Alocação no mesmo período para
-- o mesmo Vínculo (rateio entre Clientes)". As 2 afirmações, lidas ao pé
-- da letra, se contradizem -- conflito de regra de negócio/arquitetura,
-- não uma diferença de detalhe técnico.
--
-- A primeira versão desta migration resolveu esse conflito sozinha
-- ("reconciliação"), sem parar para decisão humana -- **correção
-- registrada, não escondida**: isso violava a mesma regra que já havia
-- pausado esta missão uma vez (Fase 1, conflito da FK). Corrigido na
-- revisão independente do PR #112: a decisão abaixo foi tomada pelo
-- humano, em mensagem distinta desta migration, não inferida pelo
-- agente.
--
-- **DECISÃO HUMANA (revisão do PR #112, regra canônica V1):** um mesmo
-- vínculo trabalhista PODE ter múltiplas alocações simultâneas em
-- POSTOS DIFERENTES (rateio legítimo entre clientes); NÃO pode ter duas
-- alocações temporalmente sobrepostas para o MESMO posto (registro
-- duplicado/conflitante). A constraint abaixo implementa exatamente
-- essa regra -- nunca menos, nunca mais -- e preserva a mesma
-- cardinalidade múltipla que `FonteUnidadePostoPrestacaoAirtableShadow`/
-- `vinculo_unidade_prestacao.py` já tratam como válida (nunca colapsada
-- a 1, nunca AMBIGUA só por existir mais de um posto na mesma
-- competência).
--
-- ─── posto_id sem FK própria (decisão explícita) ──────────────────────────
--
-- `posto_trabalho` como tabela Postgres não existe e criá-la está FORA
-- do escopo desta missão (autorização cobre só `vinculo_trabalhista`
-- como dependência de `alocacao`, "não expandir para... RH completo").
-- `alocacao.posto_id` guarda a MESMA identidade opaca já usada em todo
-- o código existente (`ReferenciaCanonica('UNIDADE_POSTO', local_id)`,
-- hoje o Airtable record id de `Locais`) -- sem FK, porque não há tabela
-- alvo. Mesma disciplina de `colaborador_id` abaixo.

CREATE TABLE IF NOT EXISTS vinculo_trabalhista (
    id                  TEXT PRIMARY KEY,

    -- Identidade opaca do Colaborador -- hoje o mesmo Airtable record id
    -- já usado em ReferenciaCanonica('COLABORADOR', func_id) em todo o
    -- código de classificacao/. Sem FK própria: não existe tabela
    -- `colaborador` no Postgres (fora do escopo desta missão).
    colaborador_id      TEXT NOT NULL,

    data_admissao       DATE NOT NULL,
    -- NULL = vínculo ainda vigente (mesma disciplina de
    -- alocacao.vigente_ate abaixo). Readmissão NUNCA reaproveita este
    -- registro -- gera uma linha NOVA (MAGNATA_OS_ENTIDADES.md §5,
    -- "readmissão gera um novo Vínculo, nunca reaproveita o antigo"),
    -- garantido pela constraint de não-sobreposição abaixo.
    data_desligamento   DATE,

    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT vinculo_trabalhista_desligamento_apos_admissao
        CHECK (data_desligamento IS NULL OR data_desligamento >= data_admissao)
);

COMMENT ON TABLE vinculo_trabalhista IS
    'Dependência estrutural mínima de alocacao (missão "IMPLEMENTAÇÃO '
    'ESTRUTURAL DA ENTIDADE alocacao"). NÃO é o módulo de RH/folha de '
    'pagamento -- só o suficiente para ancorar Alocação por período de '
    'vínculo. Ver MAGNATA_OS_ENTIDADES.md §5, entidade "Vínculo '
    'Trabalhista", para o modelo conceitual completo (cargo/salário/'
    'regime/matrícula ficam para uma missão futura dedicada).';

COMMENT ON COLUMN vinculo_trabalhista.colaborador_id IS
    'Identidade opaca do Colaborador (hoje: Airtable record id de '
    'Funcionários) -- sem FK própria, tabela colaborador não existe '
    'ainda no Postgres.';

-- Impede 2 vínculos sobrepostos para o MESMO colaborador -- uma
-- readmissão só é válida depois que o vínculo anterior encerrou
-- (data_desligamento preenchida e anterior à nova data_admissao).
--
-- Requisito de extensão (auditado na revisão do PR #112, nunca testado
-- contra Postgres real -- risco remanescente explícito, ver ADR):
-- `btree_gist` é EXTENSÃO "trusted" desde o PostgreSQL 13 -- instalável
-- pelo DONO do banco/schema (`CREATE EXTENSION`), SEM exigir privilégio
-- de superusuário, diferente de extensões não confiáveis. Comportamento
-- se já existir: `IF NOT EXISTS` já a torna idempotente nativamente
-- (não precisa do bloco DO -- diferente de ADD CONSTRAINT, que não
-- aceita IF NOT EXISTS). Risco remanescente até validação real: se o
-- provedor de Postgres (ex.: um plano gerenciado restrito) bloquear
-- CREATE EXTENSION mesmo para o dono do banco, esta migration falha
-- nesta linha -- nunca testado nesta sessão (nenhum Postgres real
-- disponível).
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Idempotente via bloco DO + checagem em pg_constraint -- mesmo padrão
-- já estabelecido em magnata_os/documental/modulo01/migrations/
-- 0007_vinculo_documentos_lote.sql (ALTER TABLE ADD CONSTRAINT não
-- aceita "IF NOT EXISTS" nativamente no Postgres -- corrigido na
-- revisão do PR #112; a primeira versão desta migration não seguia
-- esse padrão já documentado em migrations/CLAUDE.md do modulo01).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'vinculo_trabalhista_sem_sobreposicao'
    ) THEN
        ALTER TABLE vinculo_trabalhista
            ADD CONSTRAINT vinculo_trabalhista_sem_sobreposicao
            EXCLUDE USING gist (
                colaborador_id WITH =,
                daterange(data_admissao, data_desligamento, '[]') WITH &&
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_vinculo_trabalhista_colaborador_id
    ON vinculo_trabalhista (colaborador_id);


CREATE TABLE IF NOT EXISTS alocacao (
    id                      TEXT PRIMARY KEY,

    vinculo_trabalhista_id  TEXT NOT NULL REFERENCES vinculo_trabalhista (id),

    -- Identidade opaca do Posto/Unidade -- ver nota de decisão no topo
    -- do arquivo ("posto_id sem FK própria").
    posto_id                TEXT NOT NULL,

    vigente_de              DATE NOT NULL,
    -- NULL = vigente agora (mesmo padrão de vinculo_trabalhista.data_desligamento
    -- e do desenho original em BANCO_PROPRIO_MODELO.md §5.1).
    vigente_ate             DATE,

    criado_em               TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT alocacao_vigencia_valida
        CHECK (vigente_ate IS NULL OR vigente_ate >= vigente_de)
);

COMMENT ON TABLE alocacao IS
    'Onde, em qual Posto de Trabalho e durante qual período um '
    'Colaborador (via Vínculo Trabalhista) efetivamente trabalha -- '
    'entidade canônica já aprovada em MAGNATA_OS_ENTIDADES.md §5 e '
    'BANCO_PROPRIO_MODELO.md §5.1. Responde, de forma determinística e '
    'auditável, "em qual posto/unidade este colaborador estava alocado '
    'nesta data/competência?" -- nunca usa snapshot atual (Airtable '
    '"Locais de trabalho") como prova histórica.';

COMMENT ON COLUMN alocacao.posto_id IS
    'Identidade opaca do Posto/Unidade (hoje: Airtable record id de '
    'Locais, mesma ReferenciaCanonica(''UNIDADE_POSTO'', local_id) já '
    'usada em vinculo_unidade_prestacao.py) -- sem FK própria, tabela '
    'posto_trabalho não existe ainda no Postgres (fora do escopo desta '
    'missão).';

COMMENT ON COLUMN alocacao.vigente_ate IS
    'NULL = alocação vigente agora. Transferência de posto = UMA '
    'operação de aplicação que fecha vigente_ate da alocação antiga e '
    'abre uma nova linha -- nunca um UPDATE que apaga o histórico '
    'anterior (histórico é sempre append-only nesta tabela).';

-- Impede 2 alocações sobrepostas para o MESMO vínculo NO MESMO posto
-- (registro duplicado/conflitante) -- mas permite sobreposição entre
-- POSTOS DIFERENTES do mesmo vínculo (rateio legítimo entre clientes,
-- MAGNATA_OS_ENTIDADES.md §5, decisão humana explícita -- ver nota no
-- topo do arquivo). Reaproveita a mesma extensão já habilitada acima.
-- Idempotente pelo mesmo padrão (bloco DO + pg_constraint) usado acima.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'alocacao_sem_sobreposicao_mesmo_posto'
    ) THEN
        ALTER TABLE alocacao
            ADD CONSTRAINT alocacao_sem_sobreposicao_mesmo_posto
            EXCLUDE USING gist (
                vinculo_trabalhista_id WITH =,
                posto_id WITH =,
                daterange(vigente_de, vigente_ate, '[]') WITH &&
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_alocacao_vinculo_trabalhista_id
    ON alocacao (vinculo_trabalhista_id);

-- Suporta a consulta central desta migration: "quais postos estavam
-- vigentes para este vínculo, nesta janela de datas" -- varredura por
-- vinculo_trabalhista_id já coberta pelo índice acima; este índice
-- adicional acelera a checagem de sobreposição por período em si
-- (consulta "vigente_de <= X AND (vigente_ate IS NULL OR vigente_ate >= Y)").
CREATE INDEX IF NOT EXISTS idx_alocacao_vigencia
    ON alocacao (vinculo_trabalhista_id, vigente_de, vigente_ate);
