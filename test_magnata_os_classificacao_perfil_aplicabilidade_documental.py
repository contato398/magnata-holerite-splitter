"""Testes de `perfil_aplicabilidade_documental.py` (missão "CORREDOR
AUTÔNOMO PÓS-CLASSIFICAÇÃO V1", Fase 2/3/6)."""
from magnata_os.classificacao.contratos import AplicabilidadeDimensao, Cardinalidade, DimensaoResolucao
from magnata_os.classificacao.perfil_aplicabilidade_documental import (
    perfil_para_tipo,
    tipos_com_perfil_cadastrado,
)


def test_tipo_sem_perfil_cadastrado_devolve_none_nunca_inventa():
    assert perfil_para_tipo('Tipo Que Nao Existe Ainda') is None


def test_holerite_granularidade_colaborador():
    perfil = perfil_para_tipo('Holerite')
    assert perfil.regra_para(DimensaoResolucao.COLABORADOR).aplicabilidade == AplicabilidadeDimensao.OBRIGATORIA
    assert perfil.regra_para(DimensaoResolucao.CLIENTE).aplicabilidade == AplicabilidadeDimensao.OBRIGATORIA
    assert perfil.regra_para(DimensaoResolucao.CLIENTE).cardinalidade == Cardinalidade(1, None)
    # UNIDADE_POSTO: PROMOVIDA a OBRIGATORIA só para Holerite (missão
    # "EVIDÊNCIA RELACIONAL DOCUMENTO↔DOCUMENTO + VÍNCULO/UNIDADE_POSTO
    # REAIS") -- único caso com regra semântica comprovada nesta missão.
    assert perfil.regra_para(DimensaoResolucao.UNIDADE_POSTO).aplicabilidade == AplicabilidadeDimensao.OBRIGATORIA
    assert perfil.regra_para(DimensaoResolucao.UNIDADE_POSTO).cardinalidade == Cardinalidade(1, None)
    # VINCULO: PROMOVIDA a OBRIGATORIA em toda família de granularidade
    # colaborador -- espelha CLIENTE (já derivado de vínculo), nunca um
    # produtor de I/O novo.
    assert perfil.regra_para(DimensaoResolucao.VINCULO).aplicabilidade == AplicabilidadeDimensao.OBRIGATORIA


def test_extrato_granularidade_cliente_sem_colaborador():
    perfil = perfil_para_tipo('Extrato da Folha de Pagamento')
    assert perfil.regra_para(DimensaoResolucao.CLIENTE).aplicabilidade == AplicabilidadeDimensao.OBRIGATORIA
    assert perfil.regra_para(DimensaoResolucao.CLIENTE).cardinalidade == Cardinalidade(1, 1)
    assert perfil.regra_para(DimensaoResolucao.COLABORADOR).aplicabilidade == AplicabilidadeDimensao.NAO_APLICAVEL


def test_dctf_broadcast_cliente_nao_aplicavel():
    for tipo in ('Guia DCTFWeb/DARF', 'DCTFWeb - Declaração', 'DCTFWeb - Recibo de Entrega'):
        perfil = perfil_para_tipo(tipo)
        assert perfil.regra_para(DimensaoResolucao.CLIENTE).aplicabilidade == AplicabilidadeDimensao.NAO_APLICAVEL
        assert perfil.regra_para(DimensaoResolucao.COLABORADOR).aplicabilidade == AplicabilidadeDimensao.NAO_APLICAVEL


_TIPOS_GRANULARIDADE_COLABORADOR = frozenset({
    'Holerite', 'Folha de Ponto', 'Comprovante de Pagamento - Salário', 'Comprovante de Pagamento - VR/VA',
    'Comprovante de Pagamento - Assiduidade', 'Comprovante de Pagamento - Diárias',
    'Comprovante de Pagamento - Horas Extras', 'Relatório de Benefícios',
})


def test_vinculo_obrigatorio_so_em_granularidade_colaborador_nunca_inventado_em_broadcast_cliente():
    """VINCULO é OBRIGATORIA (espelha CLIENTE, já derivado de vínculo)
    em toda família de granularidade colaborador; NAO_APLICAVEL nas
    demais (broadcast/cliente direto), onde não há vínculo de
    colaborador envolvido -- nunca marcado aplicável para preencher a
    dimensão com um valor inventado."""
    for tipo in tipos_com_perfil_cadastrado():
        perfil = perfil_para_tipo(tipo)
        esperado = (
            AplicabilidadeDimensao.OBRIGATORIA if tipo in _TIPOS_GRANULARIDADE_COLABORADOR
            else AplicabilidadeDimensao.NAO_APLICAVEL
        )
        assert perfil.regra_para(DimensaoResolucao.VINCULO).aplicabilidade == esperado, tipo


def test_todo_perfil_cadastrado_cobre_as_6_dimensoes_canonicas():
    for tipo in tipos_com_perfil_cadastrado():
        perfil = perfil_para_tipo(tipo)
        dimensoes = {regra.dimensao for regra in perfil.regras}
        assert dimensoes == set(DimensaoResolucao)


def test_comprovante_fgts_e_broadcast_nunca_confundido_com_guia_fgts_generica():
    """'FGTS' (Guia) e 'Comprovante de Pagamento - FGTS' (finalidade)
    são tipos DISTINTOS -- cada um com seu próprio perfil, nunca
    fundidos."""
    assert perfil_para_tipo('FGTS') is not perfil_para_tipo('Comprovante de Pagamento - FGTS')
