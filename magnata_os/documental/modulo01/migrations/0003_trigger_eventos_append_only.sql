-- Magnata OS Documental — Modulo 01, Fase 2
-- Migration 0003: bloqueia UPDATE/DELETE comuns em eventos_documentais
--
-- Historico e append-only por principio (ver MAGNATA_OS_ESTADOS.md e
-- MAGNATA_OS_DOCUMENTAL_MODULO01.md). Esta trigger torna essa regra uma
-- garantia de banco, nao so de disciplina de codigo.

CREATE OR REPLACE FUNCTION eventos_documentais_bloquear_update_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'eventos_documentais e append-only: % nao e permitido (evento_id=%)',
        TG_OP, COALESCE(OLD.evento_id, NULL);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_eventos_documentais_bloquear_update ON eventos_documentais;
CREATE TRIGGER trg_eventos_documentais_bloquear_update
    BEFORE UPDATE ON eventos_documentais
    FOR EACH ROW EXECUTE FUNCTION eventos_documentais_bloquear_update_delete();

DROP TRIGGER IF EXISTS trg_eventos_documentais_bloquear_delete ON eventos_documentais;
CREATE TRIGGER trg_eventos_documentais_bloquear_delete
    BEFORE DELETE ON eventos_documentais
    FOR EACH ROW EXECUTE FUNCTION eventos_documentais_bloquear_update_delete();
