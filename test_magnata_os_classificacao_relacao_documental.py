"""Testes de `relacao_documental.py` (missão "MERGE PR #105 + EVIDÊNCIA
RELACIONAL DOCUMENTO↔DOCUMENTO + VÍNCULO/UNIDADE_POSTO REAIS +
FECHAMENTO DO UNIVERSO DOCUMENTAL V1", §5-§9; correção de
`resolver_relacao_documental_dentre_candidatos` pelo "ADENDO PRÉ-MERGE
AO PR #106", §6-§10 -- avaliação por candidato, nunca CONFLITO global
por causa de 1 candidato descartável; orientação A/B corrigida pelo
"ADENDO PRÉ-MERGE AO PR #107" -- COMPROVA nunca inverte quem é
relatante (A) e quem é comprovante (B), mesmo quando o lado FIXO em
mãos de quem resolve é o comprovante)."""
import re

from magnata_os.classificacao.contratos import EstadoResolucaoDimensao, NivelConfianca
from magnata_os.classificacao.relacao_documental import (
    DadosCorrelacaoDocumental,
    EvidenciaRelacaoDocumental,
    TipoRelacaoDocumental,
    extrair_dados_correlacao_de_texto,
    produzir_evidencias_correlacao,
    resolver_relacao_documental_dentre_candidatos,
    resolver_relacao_documental_para_comprovante_dentre_candidatos,
    resolver_relacao_documental_par,
)


def _ev(forca, contraditoria=False):
    return EvidenciaRelacaoDocumental(tipo_evidencia='T', forca=forca, contraditoria=contraditoria)


def test_nenhuma_evidencia_nunca_encontrada():
    r = resolver_relacao_documental_par('doc-a', 'doc-b', TipoRelacaoDocumental.COMPROVA, ())
    assert r.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert r.documento_b_id is None


def test_uma_evidencia_moderada_isolada_nunca_basta():
    """Cláusula pétrea §6: nenhuma evidência isolada resolve sozinha --
    mesmo MODERADA."""
    r = resolver_relacao_documental_par('doc-a', 'doc-b', TipoRelacaoDocumental.COMPROVA, (_ev(NivelConfianca.MODERADA),))
    assert r.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_duas_evidencias_moderadas_combinam_para_forte_resolvida():
    r = resolver_relacao_documental_par(
        'doc-a', 'doc-b', TipoRelacaoDocumental.COMPROVA, (_ev(NivelConfianca.MODERADA), _ev(NivelConfianca.MODERADA)),
    )
    assert r.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert r.documento_b_id == 'doc-b'


def test_uma_evidencia_forte_isolada_resolve():
    r = resolver_relacao_documental_par('doc-a', 'doc-b', TipoRelacaoDocumental.COMPROVA, (_ev(NivelConfianca.FORTE),))
    assert r.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_evidencia_contraditoria_sempre_vira_conflito_mesmo_com_outras_favoraveis():
    r = resolver_relacao_documental_par(
        'doc-a', 'doc-b', TipoRelacaoDocumental.COMPROVA,
        (_ev(NivelConfianca.MODERADA), _ev(NivelConfianca.MODERADA), _ev(NivelConfianca.FORTE, contraditoria=True)),
    )
    assert r.estado == EstadoResolucaoDimensao.CONFLITO


def test_dentre_candidatos_nenhum_atinge_forte_nao_encontrada():
    candidatos = (
        ('doc-b1', (_ev(NivelConfianca.MODERADA),)),
        ('doc-b2', (_ev(NivelConfianca.FRACA),)),
    )
    r = resolver_relacao_documental_dentre_candidatos('doc-a', TipoRelacaoDocumental.COMPROVA, candidatos)
    assert r.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert set(r.candidatos_documento_b_id) == {'doc-b1', 'doc-b2'}


def test_dentre_candidatos_exatamente_um_forte_resolve():
    candidatos = (
        ('doc-b1', (_ev(NivelConfianca.MODERADA), _ev(NivelConfianca.MODERADA))),
        ('doc-b2', (_ev(NivelConfianca.FRACA),)),
    )
    r = resolver_relacao_documental_dentre_candidatos('doc-a', TipoRelacaoDocumental.COMPROVA, candidatos)
    assert r.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert r.documento_b_id == 'doc-b1'


def test_dentre_candidatos_dois_empatados_em_forte_nunca_escolhe_arbitrario_vira_ambigua():
    candidatos = (
        ('doc-b1', (_ev(NivelConfianca.MODERADA), _ev(NivelConfianca.MODERADA))),
        ('doc-b2', (_ev(NivelConfianca.MODERADA), _ev(NivelConfianca.MODERADA))),
    )
    r = resolver_relacao_documental_dentre_candidatos('doc-a', TipoRelacaoDocumental.COMPROVA, candidatos)
    assert r.estado == EstadoResolucaoDimensao.AMBIGUA
    assert set(r.candidatos_documento_b_id) == {'doc-b1', 'doc-b2'}


def test_produzir_evidencias_valor_sozinho_nunca_forte():
    a = DadosCorrelacaoDocumental(valor_total='1.000,00')
    b = DadosCorrelacaoDocumental(valor_total='1.000,00')
    evidencias = produzir_evidencias_correlacao(a, b)
    assert len(evidencias) == 1
    assert evidencias[0].forca != NivelConfianca.FORTE
    r = resolver_relacao_documental_par('doc-a', 'doc-b', TipoRelacaoDocumental.COMPROVA, evidencias)
    assert r.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_produzir_evidencias_data_sozinha_nunca_basta():
    a = DadosCorrelacaoDocumental(data='01/07/2026')
    b = DadosCorrelacaoDocumental(data='01/07/2026')
    evidencias = produzir_evidencias_correlacao(a, b)
    r = resolver_relacao_documental_par('doc-a', 'doc-b', TipoRelacaoDocumental.COMPROVA, evidencias)
    assert r.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_produzir_evidencias_fornecedor_sozinho_nunca_basta():
    a = DadosCorrelacaoDocumental(fornecedor='vr beneficios')
    b = DadosCorrelacaoDocumental(fornecedor='vr beneficios')
    evidencias = produzir_evidencias_correlacao(a, b)
    r = resolver_relacao_documental_par('doc-a', 'doc-b', TipoRelacaoDocumental.COMPROVA, evidencias)
    assert r.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_produzir_evidencias_combinadas_resolve():
    a = DadosCorrelacaoDocumental(valor_total='1.000,00', competencia=(2026, 7))
    b = DadosCorrelacaoDocumental(valor_total='1.000,00', competencia=(2026, 7))
    evidencias = produzir_evidencias_correlacao(a, b)
    r = resolver_relacao_documental_par('doc-a', 'doc-b', TipoRelacaoDocumental.COMPROVA, evidencias)
    assert r.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_produzir_evidencias_identificador_divergente_vira_conflito():
    a = DadosCorrelacaoDocumental(identificador_pedido='P1', valor_total='1.000,00', competencia=(2026, 7))
    b = DadosCorrelacaoDocumental(identificador_pedido='P2', valor_total='1.000,00', competencia=(2026, 7))
    evidencias = produzir_evidencias_correlacao(a, b)
    r = resolver_relacao_documental_par('doc-a', 'doc-b', TipoRelacaoDocumental.COMPROVA, evidencias)
    assert r.estado == EstadoResolucaoDimensao.CONFLITO


def test_extrair_dados_correlacao_de_texto_campos_genericos():
    texto = 'Relatorio de Beneficios\nPedido no: P-999\nTotal do Pedido: R$ 1.234,56\nCompetencia: 07/2026\nData: 05/07/2026'
    dados = extrair_dados_correlacao_de_texto(texto)
    assert dados.identificador_pedido == 'P-999'
    assert dados.valor_total == '1.234,56'
    assert dados.competencia == (2026, 7)
    assert dados.data == '05/07/2026'


def test_extrair_dados_correlacao_de_texto_fornecedor_via_padrao_injetado():
    padrao = re.compile(r'iFood|VR Beneficios', re.IGNORECASE)
    texto = 'Comprovante iFood Beneficios\nTotal do Pedido: R$ 500,00'
    dados = extrair_dados_correlacao_de_texto(texto, padrao_fornecedor=padrao)
    assert dados.fornecedor == 'ifood'


def test_extrair_dados_correlacao_de_texto_sem_campos_nunca_inventa():
    dados = extrair_dados_correlacao_de_texto('Texto qualquer sem nenhum marcador')
    assert dados == DadosCorrelacaoDocumental()


def test_ambiguidade_exige_ao_menos_2_candidatos_invariante_estrutural():
    import pytest
    from magnata_os.classificacao.relacao_documental import ResolucaoRelacaoDocumental

    with pytest.raises(ValueError):
        ResolucaoRelacaoDocumental(
            documento_a_id='a', tipo_relacao=TipoRelacaoDocumental.COMPROVA,
            estado=EstadoResolucaoDimensao.AMBIGUA, candidatos_documento_b_id=('b1',),
        )


def test_resolvida_exige_documento_b_id_invariante_estrutural():
    import pytest
    from magnata_os.classificacao.relacao_documental import ResolucaoRelacaoDocumental

    with pytest.raises(ValueError):
        ResolucaoRelacaoDocumental(
            documento_a_id='a', tipo_relacao=TipoRelacaoDocumental.COMPROVA,
            estado=EstadoResolucaoDimensao.RESOLVIDA,
        )


# --- Adendo pré-merge ao PR #106, §6-§10: candidato contraditório nunca contamina os demais ---

def test_adendo_i_candidato_contraditorio_isolado_nao_impede_candidato_forte():
    candidatos = (
        ('doc-b1', (_ev(NivelConfianca.FORTE, contraditoria=True),)),
        ('doc-b2', (_ev(NivelConfianca.MODERADA), _ev(NivelConfianca.MODERADA))),
    )
    r = resolver_relacao_documental_dentre_candidatos('doc-a', TipoRelacaoDocumental.COMPROVA, candidatos)
    assert r.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert r.documento_b_id == 'doc-b2'


def test_adendo_j_dois_candidatos_fortes_coerentes_ambigua():
    candidatos = (
        ('doc-b1', (_ev(NivelConfianca.MODERADA), _ev(NivelConfianca.MODERADA))),
        ('doc-b2', (_ev(NivelConfianca.MODERADA), _ev(NivelConfianca.MODERADA))),
    )
    r = resolver_relacao_documental_dentre_candidatos('doc-a', TipoRelacaoDocumental.COMPROVA, candidatos)
    assert r.estado == EstadoResolucaoDimensao.AMBIGUA


def test_adendo_k_todos_candidatos_contraditorios_vira_conflito():
    candidatos = (
        ('doc-b1', (_ev(NivelConfianca.FORTE, contraditoria=True),)),
        ('doc-b2', (_ev(NivelConfianca.MODERADA, contraditoria=True),)),
    )
    r = resolver_relacao_documental_dentre_candidatos('doc-a', TipoRelacaoDocumental.COMPROVA, candidatos)
    assert r.estado == EstadoResolucaoDimensao.CONFLITO


def test_adendo_l_candidato_apenas_com_valor_igual_nao_resolve():
    candidatos = (
        ('doc-b1', (_ev(NivelConfianca.MODERADA),)),
    )
    r = resolver_relacao_documental_dentre_candidatos('doc-a', TipoRelacaoDocumental.COMPROVA, candidatos)
    assert r.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_adendo_m_mesmo_id_e_competencia_resolve_pela_combinacao_ja_estabelecida():
    candidatos = (
        ('doc-b1', (_ev(NivelConfianca.MODERADA), _ev(NivelConfianca.MODERADA))),
    )
    r = resolver_relacao_documental_dentre_candidatos('doc-a', TipoRelacaoDocumental.COMPROVA, candidatos)
    assert r.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert r.documento_b_id == 'doc-b1'


def test_adendo_candidato_incompativel_isolado_nao_e_elegivel_mesmo_sem_outro_candidato():
    """Um único candidato, contraditório -- nunca resolve, nunca vira
    'o único então serve'."""
    candidatos = (
        ('doc-b1', (_ev(NivelConfianca.FORTE, contraditoria=True),)),
    )
    r = resolver_relacao_documental_dentre_candidatos('doc-a', TipoRelacaoDocumental.COMPROVA, candidatos)
    assert r.estado == EstadoResolucaoDimensao.CONFLITO
    assert r.documento_b_id is None


# --- Adendo pré-merge ao PR #107: orientação da relação nunca inverte ---
# quando o lado FIXO é o comprovante (B) e os candidatos disputam o
# lado relatante (A) -- `resolver_relacao_documental_para_comprovante_
# dentre_candidatos`, MESMO núcleo de seleção, nunca uma segunda engine.

def test_orientacao_para_comprovante_resolvida_documento_a_e_o_vencedor_documento_b_e_o_fixo():
    candidatos_a = (
        ('rel-a', (_ev(NivelConfianca.MODERADA), _ev(NivelConfianca.MODERADA))),
    )
    r = resolver_relacao_documental_para_comprovante_dentre_candidatos(
        'comp-b', TipoRelacaoDocumental.COMPROVA, candidatos_a,
    )
    assert r.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert r.documento_a_id == 'rel-a'  # o RELATANTE vencedor, nunca o fixo
    assert r.documento_b_id == 'comp-b'  # o COMPROVANTE, sempre o fixo


def test_orientacao_para_comprovante_dois_relatantes_fortes_ambigua_candidatos_no_lado_a():
    candidatos_a = (
        ('rel-1', (_ev(NivelConfianca.MODERADA), _ev(NivelConfianca.MODERADA))),
        ('rel-2', (_ev(NivelConfianca.MODERADA), _ev(NivelConfianca.MODERADA))),
    )
    r = resolver_relacao_documental_para_comprovante_dentre_candidatos(
        'comp-b', TipoRelacaoDocumental.COMPROVA, candidatos_a,
    )
    assert r.estado == EstadoResolucaoDimensao.AMBIGUA
    assert set(r.candidatos_documento_a_id) == {'rel-1', 'rel-2'}
    assert r.candidatos_documento_b_id == ()
    assert r.documento_b_id == 'comp-b'


def test_orientacao_para_comprovante_candidato_contraditorio_nao_impede_candidato_forte():
    candidatos_a = (
        ('rel-errado', (_ev(NivelConfianca.FORTE, contraditoria=True),)),
        ('rel-certo', (_ev(NivelConfianca.MODERADA), _ev(NivelConfianca.MODERADA))),
    )
    r = resolver_relacao_documental_para_comprovante_dentre_candidatos(
        'comp-b', TipoRelacaoDocumental.COMPROVA, candidatos_a,
    )
    assert r.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert r.documento_a_id == 'rel-certo'
    assert r.documento_b_id == 'comp-b'


def test_orientacao_para_comprovante_todos_contraditorios_conflito_documento_b_preservado():
    candidatos_a = (
        ('rel-1', (_ev(NivelConfianca.FORTE, contraditoria=True),)),
        ('rel-2', (_ev(NivelConfianca.FORTE, contraditoria=True),)),
    )
    r = resolver_relacao_documental_para_comprovante_dentre_candidatos(
        'comp-b', TipoRelacaoDocumental.COMPROVA, candidatos_a,
    )
    assert r.estado == EstadoResolucaoDimensao.CONFLITO
    assert r.documento_a_id is None
    assert r.documento_b_id == 'comp-b'


def test_orientacao_para_comprovante_nenhum_candidato_nao_encontrada():
    r = resolver_relacao_documental_para_comprovante_dentre_candidatos(
        'comp-b', TipoRelacaoDocumental.COMPROVA, (),
    )
    assert r.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert r.documento_a_id is None
    assert r.documento_b_id == 'comp-b'


def test_orientacao_para_comprovante_exige_documento_b_id_nao_vazio():
    import pytest

    with pytest.raises(ValueError):
        resolver_relacao_documental_para_comprovante_dentre_candidatos('', TipoRelacaoDocumental.COMPROVA, ())


def test_resolvida_agora_tambem_exige_documento_a_id_invariante_estrutural():
    import pytest
    from magnata_os.classificacao.relacao_documental import ResolucaoRelacaoDocumental

    with pytest.raises(ValueError):
        ResolucaoRelacaoDocumental(
            documento_b_id='b', tipo_relacao=TipoRelacaoDocumental.COMPROVA,
            estado=EstadoResolucaoDimensao.RESOLVIDA,
        )


def test_ambiguidade_nunca_tem_candidatos_nos_2_lados_ao_mesmo_tempo():
    import pytest
    from magnata_os.classificacao.relacao_documental import ResolucaoRelacaoDocumental

    with pytest.raises(ValueError):
        ResolucaoRelacaoDocumental(
            tipo_relacao=TipoRelacaoDocumental.COMPROVA, estado=EstadoResolucaoDimensao.AMBIGUA,
            candidatos_documento_a_id=('a1', 'a2'), candidatos_documento_b_id=('b1', 'b2'),
        )


# --- Compatibilidade do contrato (correção final pré-merge ao PR #107) ---

def test_resolucao_relacao_documental_e_kw_only_construcao_posicional_e_rejeitada():
    """Auditoria do repositório (relacao_documental.py + seu teste
    nominal, únicos lugares que constroem `ResolucaoRelacaoDocumental`)
    confirmou: nenhum chamador, em lugar nenhum, usa posição -- todos
    usam nome. `kw_only=True` torna essa garantia ESTRUTURAL: nenhuma
    reordenação de campo, aqui ou futura, pode virar breaking change
    por posição, porque construção posicional nunca foi (nem é agora)
    parte do contrato público."""
    import pytest
    from magnata_os.classificacao.relacao_documental import ResolucaoRelacaoDocumental

    with pytest.raises(TypeError):
        ResolucaoRelacaoDocumental(TipoRelacaoDocumental.COMPROVA, EstadoResolucaoDimensao.RESOLVIDA)


def test_resolucao_relacao_documental_construcao_por_nome_continua_funcionando_nos_2_sentidos():
    """Caso A da correção final: A-fixo/B-candidato (uso original,
    `resolver_relacao_documental_dentre_candidatos`)."""
    from magnata_os.classificacao.relacao_documental import ResolucaoRelacaoDocumental

    resolucao_a_fixo = ResolucaoRelacaoDocumental(
        tipo_relacao=TipoRelacaoDocumental.COMPROVA, estado=EstadoResolucaoDimensao.RESOLVIDA,
        documento_a_id='rel-1', documento_b_id='comp-1',
    )
    assert resolucao_a_fixo.documento_a_id == 'rel-1'
    assert resolucao_a_fixo.documento_b_id == 'comp-1'

    # Caso B da correção final: B-fixo/A-candidato (uso do corredor,
    # `resolver_relacao_documental_para_comprovante_dentre_candidatos`).
    resolucao_b_fixo = ResolucaoRelacaoDocumental(
        tipo_relacao=TipoRelacaoDocumental.COMPROVA, estado=EstadoResolucaoDimensao.RESOLVIDA,
        documento_a_id='rel-2', documento_b_id='comp-2',
    )
    assert resolucao_b_fixo.documento_a_id == 'rel-2'
    assert resolucao_b_fixo.documento_b_id == 'comp-2'
