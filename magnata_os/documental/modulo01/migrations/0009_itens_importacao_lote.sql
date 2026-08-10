-- Magnata OS Documental — Modulo 01, Fase 4 (escrita real da importacao em lote)
-- Migration 0009: itens_importacao_lote + documentos_versionamento_logico
--                  + eventos_itens_importacao_lote (correcao de auditoria)
--
-- NAO aplicada automaticamente por nenhuma ferramenta -- mesma disciplina
-- das migrations 0001-0008. Aplicar manualmente quando o Postgres real for
-- provisionado (gate humano separado). Ver
-- magnata_os/documental/importacao_lote/escritor.py e
-- MAGNATA_OS_DOCUMENTAL_MODULO01.md.
--
-- Cardinalidade desta migration (corrigida apos revisao — documento_id
-- NUNCA e chave primaria de item de execucao, o mesmo conteudo pode
-- legitimamente aparecer em mais de uma execucao/retry):
--
--   lotes_documentais 1 ──< N itens_importacao_lote >── N documentos
--                                  │                          │
--                                  │ 1                        │ 1
--                                  ▼                          ▼
--                    eventos_itens_importacao_lote  documentos_versionamento_logico
--                       (N por item, append-only)         (1:1 com documentos)
--
-- Reaproveita integralmente: documentos (migration 0001), lotes_documentais
-- (migration 0005), eventos_documentais (migration 0002) -- nenhuma dessas
-- tabelas e alterada aqui. Nenhuma linha e escrita por esta migration --
-- so define schema.

-- ─── A. Idempotencia de EXECUCAO em lotes_documentais ───────────────────────
--
-- Uma execucao da importacao em lote e identificada por
-- (message_id_estavel, package_sha256) -- guardados em
-- lotes_documentais.metadados (JSONB, ja existente desde a migration 0005,
-- sem ALTER TABLE necessario). Indice UNICO parcial por expressao: no
-- maximo um lote por execucao entre os lotes criados por este modulo
-- (origem = 'importacao_lote') -- nunca cria um segundo lote para o mesmo
-- pacote reenviado; a aplicacao busca o lote existente e retoma, em vez de
-- recriar. Lotes de outras origens (ex.: entrada avulsa da Fase 3) nunca
-- entram nesta constraint -- a condicao WHERE restringe a own origem.
CREATE UNIQUE INDEX IF NOT EXISTS idx_lotes_documentais_execucao_unica
    ON lotes_documentais (
        ((metadados ->> 'message_id_estavel')),
        ((metadados ->> 'package_sha256'))
    )
    WHERE origem = 'importacao_lote'
      AND metadados ? 'message_id_estavel'
      AND metadados ? 'package_sha256';

COMMENT ON INDEX idx_lotes_documentais_execucao_unica IS
    'Idempotencia de execucao: no maximo um lote por '
    '(message_id_estavel, package_sha256) entre lotes origem=importacao_lote. '
    'Reenvio do mesmo pacote nunca cria um segundo lote -- a aplicacao busca '
    'e retoma o existente.';


-- ─── B. documentos_versionamento_logico ──────────────────────────────────────
--
-- Companheira 1:1 de `documentos` (mesmo padrao ja usado por
-- estados_esteira_documental, migration 0006, para o estado da esteira) --
-- so existe linha aqui para um documento_id que JA faz parte do modelo de
-- identidade logica/versionamento; documentos que nunca passaram pela
-- escrita real (ex.: legados) nao tem linha aqui, e isso e esperado.
--
-- documento_logico_id: identidade de NEGOCIO (tipo + competencia +
-- entidade) -- nunca inclui hash de conteudo nem PII (ver
-- dominio_versionamento.calcular_documento_logico_id). hash_sha256, o
-- CONTEUDO fisico, continua vivendo em documentos.hash_sha256
-- (migration 0001) -- nunca duplicado aqui.
CREATE TABLE IF NOT EXISTS documentos_versionamento_logico (
    documento_id           TEXT PRIMARY KEY REFERENCES documentos (documento_id),
    documento_logico_id    TEXT NOT NULL,
    versao_documento       INTEGER NOT NULL CHECK (versao_documento >= 1),

    -- Auto-referencia para DENTRO desta mesma tabela (nunca para
    -- documentos.documento_id diretamente) -- decisao explicita do Ajuste
    -- 5.2: um documento so pode ser referenciado como "substituido" se ele
    -- proprio ja pertence ao modelo de versionamento (ja tem linha aqui).
    -- Evita lineage apontando para um documento arbitrario fora da cadeia.
    substitui_documento_id TEXT REFERENCES documentos_versionamento_logico (documento_id),

    criado_em               TIMESTAMPTZ NOT NULL,

    CONSTRAINT documentos_versionamento_nao_autoreferencia
        CHECK (substitui_documento_id IS NULL OR substitui_documento_id <> documento_id)
);

COMMENT ON TABLE documentos_versionamento_logico IS
    'Magnata OS Documental - Fase 4: identidade logica e cadeia de '
    'versoes de um Documento -- separada de documentos.hash_sha256 '
    '(conteudo fisico) de proposito. Ver dominio_versionamento.py.';

COMMENT ON COLUMN documentos_versionamento_logico.substitui_documento_id IS
    'Auto-referencia -- so pode apontar para outro documento_id que ja '
    'esteja nesta tabela. Nunca aponta para documentos.documento_id fora '
    'do modelo de versionamento.';

-- Consulta de todas as versoes de um documento logico (ver
-- dominio_versionamento.determinar_vigente).
CREATE INDEX IF NOT EXISTS idx_versionamento_logico_documento_logico_id
    ON documentos_versionamento_logico (documento_logico_id);

-- Invariante 5.1 (obrigatoria): uma versao anterior nunca pode ter dois
-- sucessores confirmados ao mesmo tempo -- imposta pelo proprio banco via
-- UNIQUE parcial (ignora NULL, que e o caso normal de uma versao ainda nao
-- substituida). Uma segunda tentativa de INSERT com o mesmo
-- substitui_documento_id falha em nivel de banco, nao so de aplicacao.
CREATE UNIQUE INDEX IF NOT EXISTS idx_versionamento_logico_substitui_unico
    ON documentos_versionamento_logico (substitui_documento_id)
    WHERE substitui_documento_id IS NOT NULL;

-- Nao existem dois documentos com o MESMO numero de versao para o mesmo
-- documento logico -- cadeia sempre com numeracao sem duplicidade (mesmo
-- que a ordenacao real venha do grafo de substitui_documento_id, nao deste
-- numero -- ver determinar_vigente).
CREATE UNIQUE INDEX IF NOT EXISTS idx_versionamento_logico_versao_unica
    ON documentos_versionamento_logico (documento_logico_id, versao_documento);


-- ─── C. itens_importacao_lote ────────────────────────────────────────────────
--
-- Um item de execucao por (lote_id, manifesto_item_id) -- NUNCA por
-- documento_id (correcao de cardinalidade desta rodada). documento_id e
-- nullable e NAO-UNICO: o mesmo conteudo pode aparecer legitimamente em
-- itens de execucoes/lotes diferentes (reenvio do mesmo pacote, o mesmo
-- PDF chegando por dois pacotes distintos) -- ver cenario W.
CREATE TABLE IF NOT EXISTS itens_importacao_lote (
    item_importacao_id      TEXT PRIMARY KEY,
    lote_id                 TEXT NOT NULL REFERENCES lotes_documentais (lote_id),
    manifesto_item_id       TEXT NOT NULL,
    tipo_documental         TEXT NOT NULL CHECK (tipo_documental IN (
                                'holerite', 'extrato_cliente'
                             )),

    -- Nullable, NAO-UNICO de proposito -- ver docstring da tabela acima.
    documento_id             TEXT REFERENCES documentos (documento_id),

    identidade_ingestao      TEXT NOT NULL,

    situacao                 TEXT NOT NULL CHECK (situacao IN (
                                 'PENDENTE', 'EM_PROCESSAMENTO', 'SUCESSO',
                                 'FAILED_RETRYABLE', 'FAILED_COMPENSATED',
                                 'FAILED_ORPHANED', 'BLOQUEADO_CONFLITO_VERSAO',
                                 'IGNORADO_NAO_EXACT'
                             )),
    tentativas                INTEGER NOT NULL DEFAULT 0 CHECK (tentativas >= 0),

    external_record_id                 TEXT,
    external_criado_por_esta_execucao  BOOLEAN NOT NULL DEFAULT FALSE,
    attachment_confirmado              BOOLEAN NOT NULL DEFAULT FALSE,
    ultimo_erro_sanitizado             TEXT,

    criado_em                TIMESTAMPTZ NOT NULL,
    atualizado_em             TIMESTAMPTZ NOT NULL,

    -- Unica constraint de unicidade no nivel do item: um item por
    -- manifesto dentro do MESMO lote. Nao ha UNIQUE(documento_id) --
    -- redundante seria impedir o cenario W. Nao ha UNIQUE(identidade_ingestao)
    -- separado: identidade_ingestao ja e 1:1 com (lote_id, manifesto_item_id)
    -- por construcao (deriva de message_id_estavel+package_sha256, que a
    -- idempotencia de execucao do item A ja torna 1:1 com lote_id) -- uma
    -- constraint adicional aqui seria redundante sem invariante nova.
    CONSTRAINT itens_importacao_lote_unico_por_lote UNIQUE (lote_id, manifesto_item_id)
);

COMMENT ON TABLE itens_importacao_lote IS
    'Magnata OS Documental - Fase 4: OCORRENCIA de processamento de um item '
    'de manifesto dentro de uma execucao (lote). documento_id aponta para o '
    'conteudo fisico quando resolvido -- nullable e nao-unico, nunca chave '
    'primaria (mesmo documento pode aparecer em mais de um item/execucao).';

COMMENT ON COLUMN itens_importacao_lote.documento_id IS
    'Nullable ate o conteudo ser lido/hasheado; nao-unico -- o mesmo '
    'documento fisico pode ser referenciado por itens de lotes diferentes '
    '(reenvio do mesmo pacote, mesmo PDF em pacotes distintos). Ver cenario W.';

CREATE INDEX IF NOT EXISTS idx_itens_importacao_lote_documento_id
    ON itens_importacao_lote (documento_id);

CREATE INDEX IF NOT EXISTS idx_itens_importacao_lote_situacao
    ON itens_importacao_lote (situacao);

-- Suporta retomada/consulta por identidade de ingestao sem depender de
-- conhecer lote_id+manifesto_item_id de antemao.
CREATE INDEX IF NOT EXISTS idx_itens_importacao_lote_identidade_ingestao
    ON itens_importacao_lote (identidade_ingestao);


-- ─── D. eventos_itens_importacao_lote (correcao de auditoria) ───────────────
--
-- `itens_importacao_lote` (secao C acima) guarda só o ESTADO ATUAL do
-- item -- mesma disciplina de `estados_esteira_documental` (migration
-- 0006) em relacao a `eventos_documentais` (migration 0002). Sem uma
-- trilha propria, transicoes ocorridas ANTES de documento_id existir
-- (ex.: item criado, tentativa que falhou antes do hash, Airtable
-- create bem-sucedido mas upload nunca tentado) ficariam representadas
-- só pelo estado atual -- perdendo a sequencia completa exigida pelo
-- principio permanente do Magnata OS de reconstruir execucao/item/
-- estados/tentativas/transicoes/falhas/retomadas sem depender de log.
--
-- `eventos_documentais` NAO pode ser reaproveitada para isso: sua FK
-- documento_id e NOT NULL (migration 0002) -- ela e, por desenho,
-- unicamente sobre o DOCUMENTO, nunca sobre uma ocorrencia de execucao
-- que ainda nao resolveu um documento. Forcá-la a aceitar documento_id
-- NULL alteraria uma migration ja tratada como aplicada (CLAUDE.md raiz
-- §7) só para representar uma entidade diferente -- por isso uma tabela
-- nova e pequena, dedicada ao ITEM, e a solucao minima correta (opcao C
-- da priorizacao desta rodada; A e B foram descartadas por essa razao).
--
-- documento_id aqui e NULLABLE (ao contrario de eventos_documentais) --
-- exatamente o que permite registrar eventos antes do documento existir.
-- Quando documento_id passa a existir, os eventos desta tabela continuam
-- correlacionaveis a `eventos_documentais` pelo mesmo documento_id --
-- sem duplicar semantica: esta tabela e a trilha do ITEM (toda
-- transicao), eventos_documentais continua sendo a trilha do DOCUMENTO
-- (só os eventos finais relevantes do lado do documento, ja como hoje).
CREATE TABLE IF NOT EXISTS eventos_itens_importacao_lote (
    evento_id           BIGSERIAL PRIMARY KEY,
    item_importacao_id  TEXT NOT NULL REFERENCES itens_importacao_lote (item_importacao_id),
    lote_id             TEXT NOT NULL REFERENCES lotes_documentais (lote_id),
    documento_id        TEXT REFERENCES documentos (documento_id),
    situacao            TEXT NOT NULL CHECK (situacao IN (
                            'PENDENTE', 'EM_PROCESSAMENTO', 'SUCESSO',
                            'FAILED_RETRYABLE', 'FAILED_COMPENSATED',
                            'FAILED_ORPHANED', 'BLOQUEADO_CONFLITO_VERSAO',
                            'IGNORADO_NAO_EXACT'
                         )),
    tentativas           INTEGER NOT NULL CHECK (tentativas >= 0),
    erro_sanitizado       TEXT,
    "timestamp"           TIMESTAMPTZ NOT NULL,
    detalhes              JSONB NOT NULL DEFAULT '{}'::jsonb,
    registrado_em          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE eventos_itens_importacao_lote IS
    'Magnata OS Documental - Fase 4: historico append-only de UM item de '
    'execucao, desde PENDENTE (criacao) ate a situacao terminal -- '
    'inclusive antes de documento_id existir. Complementa (nao duplica) '
    'eventos_documentais: aquela e a trilha do DOCUMENTO, esta e a '
    'trilha do ITEM. Ver escritor.py, _persistir_item.';

COMMENT ON COLUMN eventos_itens_importacao_lote.documento_id IS
    'Nullable -- diferenca deliberada de eventos_documentais.documento_id '
    '(NOT NULL, migration 0002). E exatamente essa nulabilidade que '
    'permite registrar eventos do item ANTES do documento existir.';

CREATE INDEX IF NOT EXISTS idx_eventos_itens_importacao_lote_item_timestamp
    ON eventos_itens_importacao_lote (item_importacao_id, "timestamp");

CREATE INDEX IF NOT EXISTS idx_eventos_itens_importacao_lote_lote_id
    ON eventos_itens_importacao_lote (lote_id);

CREATE INDEX IF NOT EXISTS idx_eventos_itens_importacao_lote_documento_id
    ON eventos_itens_importacao_lote (documento_id);

-- Trigger de append-only PROPRIA (nunca reaproveita a funcao de
-- eventos_documentais_bloquear_update_delete da migration 0003 -- essa
-- e de uma migration ja tratada como aplicada, com mensagem de erro
-- hardcoded para "eventos_documentais"; reusa-la aqui produziria uma
-- mensagem enganosa ao bloquear UPDATE/DELETE nesta tabela). Mesmo
-- padrao estrutural da 0003, generico via TG_TABLE_NAME.
CREATE OR REPLACE FUNCTION eventos_itens_importacao_lote_bloquear_update_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% e append-only: % nao e permitido (evento_id=%)',
        TG_TABLE_NAME, TG_OP, COALESCE(OLD.evento_id, NULL);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_eventos_itens_importacao_lote_bloquear_update ON eventos_itens_importacao_lote;
CREATE TRIGGER trg_eventos_itens_importacao_lote_bloquear_update
    BEFORE UPDATE ON eventos_itens_importacao_lote
    FOR EACH ROW EXECUTE FUNCTION eventos_itens_importacao_lote_bloquear_update_delete();

DROP TRIGGER IF EXISTS trg_eventos_itens_importacao_lote_bloquear_delete ON eventos_itens_importacao_lote;
CREATE TRIGGER trg_eventos_itens_importacao_lote_bloquear_delete
    BEFORE DELETE ON eventos_itens_importacao_lote
    FOR EACH ROW EXECUTE FUNCTION eventos_itens_importacao_lote_bloquear_update_delete();
