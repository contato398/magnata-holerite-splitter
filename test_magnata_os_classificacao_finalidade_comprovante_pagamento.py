"""Testes de `finalidade_comprovante_pagamento.py` (Fase G da missão
"CAPACIDADES TRANSVERSAIS DO MOTOR DOCUMENTAL"). Textos sintéticos --
frases institucionais genéricas, nunca dado real."""
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.finalidade_comprovante_pagamento import (
    FINALIDADE_DCTF_DARF,
    FINALIDADE_FGTS,
    FINALIDADE_SALARIO,
    OcorrenciaSinalFinalidade,
    SinalFinalidadePagamento,
    hipoteses_de_finalidade_pagamento,
    sinais_textuais_de_finalidade_pagamento,
)
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental


def _resolver(texto: str):
    ocorrencias = sinais_textuais_de_finalidade_pagamento(texto)
    hipoteses = hipoteses_de_finalidade_pagamento(ocorrencias)
    return resolver_tipo_documental(hipoteses)


def test_estrutura_bancaria_isolada_e_inconclusiva():
    """Sem NENHUMA descrição de finalidade específica, estrutura
    bancária sozinha nunca resolve -- exatamente a regra "1 evidência
    fraca -> inconclusivo"."""
    resultado = _resolver('Comprovante de transferência PIX efetuada com sucesso')
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_descricao_especifica_isolada_ja_resolve():
    """Uma frase característica (nunca uma palavra isolada) já é
    evidência suficiente sozinha."""
    resultado = _resolver('Comprovante de pagamento de salário do mês de referência')
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (
        ReferenciaCanonica('TIPO_DOCUMENTAL', FINALIDADE_SALARIO),
    )


def test_descricao_mais_estrutura_bancaria_continuam_resolvendo():
    """Estrutura bancária reforça (nunca derruba) uma descrição já
    suficiente -- continua RESOLVIDA."""
    texto = 'PIX efetuado -- pagamento de salário do colaborador'
    resultado = _resolver(texto)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (
        ReferenciaCanonica('TIPO_DOCUMENTAL', FINALIDADE_SALARIO),
    )


def test_sinais_moderados_empatados_para_finalidades_diferentes_geram_ambigua():
    """Salário e FGTS descritos com a mesma força (MODERADA, 1 sinal
    cada) no mesmo documento -- nunca escolhe um vencedor arbitrário."""
    texto = (
        'PIX -- pagamento de salário do colaborador\n'
        'TED -- recolhimento do FGTS da competência'
    )
    resultado = _resolver(texto)
    assert resultado.estado == EstadoResolucaoDimensao.AMBIGUA


def test_sinais_fortes_incompativeis_geram_conflito():
    """Quando CADA finalidade tem reforço suficiente para virar FORTE
    (2+ evidências MODERADA coerentes, regra já provada em
    `resolucao_tipo_documental.py`), duas finalidades incompatíveis
    empatadas em FORTE nunca resolvem sozinhas -- vão para CONFLITO."""
    ocorrencias = (
        OcorrenciaSinalFinalidade(SinalFinalidadePagamento.DESCRICAO_SALARIO, FINALIDADE_SALARIO, 'ref_1'),
        OcorrenciaSinalFinalidade(SinalFinalidadePagamento.DESCRICAO_SALARIO, FINALIDADE_SALARIO, 'ref_2'),
        OcorrenciaSinalFinalidade(SinalFinalidadePagamento.DESCRICAO_FGTS, FINALIDADE_FGTS, 'ref_3'),
        OcorrenciaSinalFinalidade(SinalFinalidadePagamento.DESCRICAO_FGTS, FINALIDADE_FGTS, 'ref_4'),
    )
    resultado = resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias))
    assert resultado.estado == EstadoResolucaoDimensao.CONFLITO


def test_documento_sem_nenhum_sinal_de_pagamento_nao_encontra_finalidade():
    resultado = _resolver('texto qualquer sem nenhuma relação com pagamento')
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert resultado.valores_confirmados == ()


def test_texto_vazio_nao_produz_nenhuma_ocorrencia():
    assert sinais_textuais_de_finalidade_pagamento('') == ()
    assert sinais_textuais_de_finalidade_pagamento(None) == ()


def test_dctf_darf_reconhecido_por_descricao_especifica():
    resultado = _resolver('DARF referente ao recolhimento do tributo apurado na competência')
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (
        ReferenciaCanonica('TIPO_DOCUMENTAL', FINALIDADE_DCTF_DARF),
    )
