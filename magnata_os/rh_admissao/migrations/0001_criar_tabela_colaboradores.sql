-- Magnata OS — RH/Admissão, missão "CADASTRO DE COLABORADOR
-- PERSISTENTE V1"
-- Migration 0001: tabela rh_admissao_colaboradores
--
-- NÃO APLICADA por nenhuma ferramenta -- mesma disciplina das demais
-- migrations do Magnata OS (ver migrations/CLAUDE.md do Módulo 01,
-- mesmo princípio vale aqui: preparada, nunca executada
-- automaticamente). Aplicação em Postgres real exige autorização
-- humana específica, registrada em .magnata/migration-authorizations/
-- (gate de governança, `/CLAUDE.md` §6/§8/§12-I) -- ver
-- docs/decisoes/cadastro-colaborador-persistente-v1.md §5.
--
-- O QUE É: cadastro PRÓPRIO do Magnata OS para o colaborador citado num
-- Kit de Admissão -- não Airtable, não Secullum. `colaborador_id` é a
-- MESMA identidade opaca que `gatilho_admissao.DadosColaboradorKitAdmissao`
-- já usa (hoje, o Airtable record id de Funcionários -- LEGADO/
-- TRANSICIONAL, nunca declarado aqui como identidade definitiva, mesma
-- disciplina de contato_colaborador_observado/identidade_colaborador_
-- observada em documental/alocacao/migrations/).
--
-- LOCAL DE TRABALHO NUNCA É AUTOMÁTICO (docs/decisoes/local-trabalho-
-- determinacao-humana-admissao-v1.md): `local_trabalho` só é
-- preenchido por determinação humana explícita -- nunca inferido desta
-- tabela nem de nenhuma outra.
--
-- IDEMPOTÊNCIA: `colaborador_id` é chave primária -- a mesma chave de
-- idempotência já usada por
-- gatilho_admissao.RegistroGatilhoAdmissaoEmMemoria. Reprocessar o
-- mesmo Kit nunca duplica linha (adapter faz UPSERT por esta chave).
--
-- DUAS DIMENSÕES SEPARADAS, NUNCA FUNDIDAS (`/CLAUDE.md` §4):
-- `situacao_cadastro` (o cadastro está completo ou pendente?) e
-- `local_trabalho` (qual é o valor, quando existe?). O CHECK abaixo é
-- defesa em profundidade da MESMA invariante já validada em
-- `dominio_cadastro_colaborador.Colaborador.__post_init__`.
--
-- LGPD (`/CLAUDE.md` §6) -- RISCO DECLARADO, NÃO ESCONDIDO: `cpf` é
-- armazenado em texto puro nesta V1 (mesmo formato transitório já
-- usado por `gatilho_admissao.DadosColaboradorKitAdmissao`/
-- `porta_secullum.IntencaoCadastroSecullum`, que hoje só trafega CPF
-- em memória, nunca persiste). Diferente de `contato_colaborador_
-- observado.valor_cifrado` (telefone, migration 0004 de
-- documental/alocacao/), esta tabela NÃO cifra o CPF -- decisão de
-- escopo explícita desta missão, não uma omissão silenciosa. Ver
-- docs/decisoes/cadastro-colaborador-persistente-v1.md §6 para o
-- risco registrado e a recomendação de cifragem como trabalho futuro.

CREATE TABLE IF NOT EXISTS rh_admissao_colaboradores (
    colaborador_id     TEXT NOT NULL,
    cpf                 TEXT NOT NULL CHECK (cpf <> ''),
    nome                TEXT NOT NULL CHECK (nome <> ''),
    cargo               TEXT NULL,

    -- Determinação humana pontual (grupo_escala_id) -- NULL enquanto
    -- pendente. Nunca preenchido por inferência automática.
    local_trabalho      TEXT NULL,

    situacao_cadastro   TEXT NOT NULL
        CHECK (situacao_cadastro IN ('AGUARDANDO_LOCAL_TRABALHO', 'CADASTRO_COMPLETO')),

    -- Defesa em profundidade da invariante de domínio: situação e local
    -- de trabalho nunca divergem entre si (ver Colaborador.__post_init__).
    CONSTRAINT chk_rh_admissao_colaboradores_situacao_local_trabalho CHECK (
        (situacao_cadastro = 'AGUARDANDO_LOCAL_TRABALHO' AND local_trabalho IS NULL)
        OR
        (situacao_cadastro = 'CADASTRO_COMPLETO' AND local_trabalho IS NOT NULL)
    ),

    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT rh_admissao_colaboradores_pkey PRIMARY KEY (colaborador_id)
);

COMMENT ON TABLE rh_admissao_colaboradores IS
    'Cadastro de Colaborador PRÓPRIO do Magnata OS (não Airtable, não '
    'Secullum) -- nasce de um Kit de Admissão classificado. '
    'local_trabalho nunca é preenchido por inferência automática -- só '
    'por determinação humana explícita (ver docs/decisoes/local-'
    'trabalho-determinacao-humana-admissao-v1.md).';

COMMENT ON COLUMN rh_admissao_colaboradores.colaborador_id IS
    'Identidade opaca do Colaborador -- HOJE o Airtable record id de '
    'Funcionários (mesmo valor usado por gatilho_admissao.py). '
    'LEGADO/TRANSICIONAL -- nunca a identidade definitiva do Magnata OS.';

COMMENT ON COLUMN rh_admissao_colaboradores.cpf IS
    'Texto puro nesta V1 -- risco LGPD declarado, ver cabeçalho desta '
    'migration e docs/decisoes/cadastro-colaborador-persistente-v1.md §6.';

CREATE INDEX IF NOT EXISTS idx_rh_admissao_colaboradores_situacao_cadastro
    ON rh_admissao_colaboradores (situacao_cadastro);
