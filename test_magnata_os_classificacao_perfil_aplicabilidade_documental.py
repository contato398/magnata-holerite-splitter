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
    # UNIDADE_POSTO: NAO_APLICAVEL nesta missão -- nenhum produtor a
    # resolve ainda (ver docstring de _perfil_granularidade_colaborador).
    assert perfil.regra_para(DimensaoResolucao.UNIDADE_POSTO).aplicabilidade == AplicabilidadeDimensao.NAO_APLICAVEL


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


def test_vinculo_nunca_aplicavel_em_nenhum_perfil():
    """Decisão registrada (Fase 16): nenhum produtor resolve VINCULO
    isoladamente ainda -- nunca marcado aplicável para preencher a
    dimensão com um valor inventado."""
    for tipo in tipos_com_perfil_cadastrado():
        perfil = perfil_para_tipo(tipo)
        assert perfil.regra_para(DimensaoResolucao.VINCULO).aplicabilidade == AplicabilidadeDimensao.NAO_APLICAVEL


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
