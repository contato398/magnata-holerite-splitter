-- Magnata OS — RH/Admissão, missão "CADASTRO DE COLABORADOR
-- PERSISTENTE V1" — correção pré-merge do PR #215
-- Migration 0002: cifrar CPF em repouso (rh_admissao_colaboradores)
--
-- NÃO APLICADA por nenhuma ferramenta -- mesma disciplina de 0001 e de
-- todas as migrations do Magnata OS (preparada, nunca executada
-- automaticamente; aplicação em Postgres real exige autorização humana
-- específica, `/CLAUDE.md` §6/§8/§12-I).
--
-- POR QUE UMA MIGRATION NOVA, NÃO UMA EDIÇÃO DE 0001: a própria
-- migration 0001 nunca foi aplicada em nenhum Postgres real (só no
-- efêmero de CI/local desta missão) -- mas o padrão já estabelecido
-- neste repositório para migrations já COMMITADAS é tratá-las como
-- aplicadas e nunca editá-las (ver
-- magnata_os/documental/modulo01/migrations/CLAUDE.md: "nunca editar
-- uma migration já aplicada... mesmo que ainda não tenha sido aplicada
-- em nenhum ambiente real -- se já foi commitado, trate como
-- aplicado"; mesmo princípio de `/CLAUDE.md` §8 raiz). 0001 já está
-- commitada nesta branch desde antes desta correção -- editá-la em vez
-- de criar 0002 quebraria esse precedente por conveniência local.
-- Decisão registrada em docs/decisoes/cadastro-colaborador-
-- persistente-v1.md §6.
--
-- O QUE MUDA: `cpf` (TEXT, texto puro) é substituído por `cpf_cifrado`
-- (BYTEA, token Fernet) -- mesmo mecanismo já aprovado e em produção
-- local para telefone/WhatsApp
-- (`documental/alocacao/migrations/0004_criar_contato_colaborador_
-- observado.sql`, `contato_colaborador.py::cifrar_valor_contato`).
-- Cifra/decifra só acontece em
-- `adapters/repositorio_colaboradores_postgres.py` -- o domínio
-- (`dominio_cadastro_colaborador.py`) nunca sabe que existe cifra.
--
-- SEM BACKFILL: como a migration 0001 nunca foi aplicada em nenhum
-- ambiente real, não existe linha real com `cpf` em texto puro para
-- migrar -- `DROP COLUMN cpf` aqui não perde nenhum dado de produção
-- (decisão possível só porque 0001 nunca chegou a rodar fora de
-- Postgres efêmero de teste; se já houvesse dado real, esta migration
-- precisaria de um passo de backfill cifrado antes do DROP, o que não
-- é o caso aqui).
--
-- IDEMPOTENTE por instrução (`/CLAUDE.md`
-- documental/modulo01/migrations/CLAUDE.md, "idempotência por
-- instrução"): `ADD COLUMN IF NOT EXISTS`, `DROP COLUMN` guardado por
-- checagem em `information_schema.columns`, `SET NOT NULL` (idempotente
-- por natureza -- reaplicar quando já é NOT NULL não é erro).

ALTER TABLE rh_admissao_colaboradores ADD COLUMN IF NOT EXISTS cpf_cifrado BYTEA;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'rh_admissao_colaboradores' AND column_name = 'cpf'
    ) THEN
        ALTER TABLE rh_admissao_colaboradores DROP COLUMN cpf;
    END IF;
END $$;

ALTER TABLE rh_admissao_colaboradores ALTER COLUMN cpf_cifrado SET NOT NULL;

COMMENT ON COLUMN rh_admissao_colaboradores.cpf_cifrado IS
    'CPF cifrado (Fernet -- AES-128-CBC + HMAC autenticado), nunca '
    'texto puro. Cifra/decifra só em '
    'adapters/repositorio_colaboradores_postgres.py; chave sempre fora '
    'deste banco (variável de ambiente '
    'MAGNATA_RH_ADMISSAO_CPF_FERNET_CHAVE, ver '
    'configuracao_cpf_colaborador.py). Ver docs/decisoes/'
    'cadastro-colaborador-persistente-v1.md §6.';
