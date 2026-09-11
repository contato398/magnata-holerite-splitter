-- Magnata OS — Grande Orquestrador
-- Migration 0006: conclusão durável do ciclo de assinatura por ação.
--
-- INERTE: nenhum módulo aplica esta migration automaticamente. Aplicação em
-- banco real exige revisão do blob final, backup e nova autorização humana
-- (mesmo processo já usado para 0001-0003). NÃO aplicar em produção nesta
-- missão.
--
-- Por que uma tabela nova, não uma coluna em acoes_execucao_plano: aquela
-- tabela representa o ciclo de TRANSPORTE (enviado), com seu próprio
-- invariante de terminalidade (`acoes_execucao_terminal_coerente`); o
-- ciclo de ASSINATURA é um processo de negócio independente e mais longo
-- (pode levar dias), com transições próprias que precisam de histórico
-- auditável (CLAUDE.md §4: separar sempre estado/etapa; histórico
-- append-only). Mistura-los violaria a separação já estabelecida.
--
-- Por que não reaproveitar magnata_orquestrador.auditoria/
-- auditoria_recuperacao: ambas são chaveadas por event_id (o evento), não
-- por acao_execucao_id (o destinatário/ação individual) -- um evento pode
-- ter N ações, cada uma com ciclo de assinatura independente.
--
-- Numeração: 0001-0003 aplicadas em produção; 0004 mesclada e inerte
-- (envelope_sha256); 0005 (execucoes_prestacao, PR #147) mesclada e
-- inerte -- 0006 é o próximo número livre neste pacote, sem colisão.

BEGIN;

CREATE TABLE magnata_orquestrador.conclusao_obrigacao_assinatura (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    acao_execucao_id TEXT NOT NULL
        REFERENCES magnata_orquestrador.acoes_execucao_plano(acao_execucao_id),
    estado TEXT NOT NULL CHECK (estado IN (
        'AGUARDANDO_ASSINATURA', 'ASSINADO', 'COMPROVANTE_VALIDADO', 'CONCLUIDO'
    )),
    correlacao_externa TEXT,   -- id opaco da obrigação no adapter legado; nunca CPF/nome
    evidencia_sha256 TEXT CHECK (evidencia_sha256 IS NULL OR evidencia_sha256 ~ '^[0-9a-f]{64}$'),
    registrado_em TIMESTAMPTZ NOT NULL
);

CREATE INDEX conclusao_obrigacao_assinatura_acao_idx
    ON magnata_orquestrador.conclusao_obrigacao_assinatura (acao_execucao_id, id);

-- Append-only: mesma trigger de propósito já usada em auditoria/
-- auditoria_recuperacao (migration 0001) -- reaproveita a função já
-- existente, não cria uma nova.
CREATE TRIGGER conclusao_obrigacao_assinatura_append_only
BEFORE UPDATE OR DELETE ON magnata_orquestrador.conclusao_obrigacao_assinatura
FOR EACH ROW EXECUTE FUNCTION magnata_orquestrador.bloquear_mutacao_auditoria();

COMMIT;
