"""Testes de `decisao_pos_classificacao.py` (Fase K da missão
"CAPACIDADES TRANSVERSAIS DO MOTOR DOCUMENTAL")."""
from magnata_os.classificacao.contratos import ConfiancaResolucao, NivelConfianca
from magnata_os.classificacao.resolucao_master_documental import (
    DecisaoGranularidadeDocumento,
    EstadoGranularidadeDocumento,
)
from magnata_os.documental.modulo01.decisao_pos_classificacao import (
    proxima_etapa_sugerida_apos_classificacao,
)
from magnata_os.documental.modulo01.dominio_esteira import (
    EtapaEsteira,
    validar_transicao_etapa,
)


def _decisao(estado: EstadoGranularidadeDocumento) -> DecisaoGranularidadeDocumento:
    return DecisaoGranularidadeDocumento(
        estado=estado, evidencias=(), confianca=ConfiancaResolucao(NivelConfianca.MODERADA),
    )


def test_potencialmente_master_sugere_separacao():
    etapa = proxima_etapa_sugerida_apos_classificacao(_decisao(EstadoGranularidadeDocumento.POTENCIALMENTE_MASTER))
    assert etapa == EtapaEsteira.SEPARACAO


def test_unitario_sugere_identificacao_pulando_separacao():
    etapa = proxima_etapa_sugerida_apos_classificacao(_decisao(EstadoGranularidadeDocumento.UNITARIO))
    assert etapa == EtapaEsteira.IDENTIFICACAO


def test_inconclusivo_nunca_sugere_etapa_automaticamente():
    """Evidência insuficiente nunca escolhe um caminho sozinha -- fica
    para decisão humana (/CLAUDE.md §4, "automação por confiança; ação
    humana para exceção")."""
    etapa = proxima_etapa_sugerida_apos_classificacao(_decisao(EstadoGranularidadeDocumento.INCONCLUSIVO))
    assert etapa is None


def test_ambas_as_sugestoes_sao_transicoes_realmente_permitidas():
    """Prova que esta função nunca sugere algo que a política de
    transição já estabelecida (`TRANSICOES_ETAPA_PERMITIDAS`) rejeitaria
    -- nenhuma alteração foi feita nessa tabela para esta missão."""
    for estado in (EstadoGranularidadeDocumento.POTENCIALMENTE_MASTER, EstadoGranularidadeDocumento.UNITARIO):
        etapa_sugerida = proxima_etapa_sugerida_apos_classificacao(_decisao(estado))
        validar_transicao_etapa(EtapaEsteira.CLASSIFICACAO, etapa_sugerida)  # não levanta
