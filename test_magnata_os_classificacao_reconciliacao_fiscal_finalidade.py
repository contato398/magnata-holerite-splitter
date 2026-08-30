"""Testes de `reconciliar_evidencia_fiscal_com_finalidade` (Fase 10 da
missão "CADASTRO CANÔNICO REAL DE REQUISITOS DA PRESTAÇÃO" -- fecha o
gap fiscal↔finalidade registrado nos PRs #96/#97)."""
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.finalidade_comprovante_pagamento import (
    FINALIDADE_FGTS,
    hipoteses_de_finalidade_pagamento,
    sinais_textuais_de_finalidade_pagamento,
)
from magnata_os.classificacao.produtores_evidencia_fiscal import (
    reconciliar_evidencia_fiscal_com_finalidade,
)
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental


def _resolver(texto: str):
    ocorrencias = sinais_textuais_de_finalidade_pagamento(texto) + reconciliar_evidencia_fiscal_com_finalidade(texto)
    return resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias))


def test_sinal_fiscal_isolado_sem_descricao_nunca_decide_sozinho():
    """Cláusula pétrea desta missão: nunca infere finalidade sem
    descrição já ter identificado uma."""
    assert reconciliar_evidencia_fiscal_com_finalidade('Código de Receita: 0561') == ()


def test_descricao_fgts_mais_codigo_de_receita_reforcam_a_mesma_finalidade():
    texto = 'Guia do FGTS -- Código de Receita: 0561'
    resultado = _resolver(texto)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (ReferenciaCanonica('TIPO_DOCUMENTAL', FINALIDADE_FGTS),)


def test_sem_sinal_fiscal_estrutural_nao_produz_reforco():
    texto = 'Guia do FGTS sem nenhum campo fiscal estruturado'
    assert reconciliar_evidencia_fiscal_com_finalidade(texto) == ()


def test_texto_vazio_nunca_produz_ocorrencia():
    assert reconciliar_evidencia_fiscal_com_finalidade('') == ()
    assert reconciliar_evidencia_fiscal_com_finalidade(None) == ()


def test_reconciliacao_nunca_cria_finalidade_fora_de_fgts_ou_dctf_darf():
    """Sinal fiscal reforça só FGTS/DCTF-DARF -- nunca Salário/VR-VA/
    Assiduidade/Diárias/Horas Extras, mesmo com sinal fiscal presente."""
    texto = 'Comprovante de pagamento de salário -- Código de Receita: 0561'
    ocorrencias = reconciliar_evidencia_fiscal_com_finalidade(texto)
    assert ocorrencias == ()
