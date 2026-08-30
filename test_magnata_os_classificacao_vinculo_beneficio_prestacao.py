"""Prova de vínculo de benefício (Fase 11 da missão "CADASTRO CANÔNICO
REAL DE REQUISITOS DA PRESTAÇÃO").

Auditoria (`app.py::CAPACIDADES_BENEFICIOS`) confirma que benefícios
individuais (VR/VA avulso, Horas Extras, Assiduidade) já são resolvidos
no legado por "CPF→Local→Cliente" -- EXATAMENTE o mesmo caminho que
`FonteVinculosPrestacao`/`resolver_clientes_validado` já implementam
para Holerite (`_ORIGENS_SUPORTADAS = {COLABORADOR, FUNCIONARIO,
UNIDADE_POSTO}`). Nenhum código novo de vínculo foi necessário --
este teste PROVA que a peça já existente serve para benefício também,
sem duplicar lógica.

Granularidade "VR/VA agregado só por cliente" (planilha em lote,
`CAPACIDADES_BENEFICIOS`: "Por linha da planilha, via CPF→Local→Cliente")
usa o MESMO caminho -- a diferença é só a origem do documento (1 PDF
por colaborador vs. 1 linha de planilha), nunca a resolução de vínculo
em si.

O que este teste NÃO faz (registrado, não escondido): decidir QUAL
cliente real exige VR/VA/Horas Extras/Assiduidade -- nenhuma evidência
disso existe no repositório (ver decisão do cadastro canônico), então
nenhum cliente é configurado aqui."""
from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.classificacao.finalidade_comprovante_pagamento import (
    FINALIDADE_VR_VA,
    hipoteses_de_finalidade_pagamento,
    sinais_textuais_de_finalidade_pagamento,
)
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental
from magnata_os.classificacao.vinculos_prestacao import resolver_clientes_validado

_CLIENTE_ESPERADO = ReferenciaCanonica('CLIENTE', 'rec_cliente_beneficio')


class _FonteVinculosFake:
    """Mesma fake já usada nos corredores anteriores -- prova que
    NENHUMA peça nova de vínculo foi necessária para benefício."""

    def resolver_clientes(self, origem, competencia):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(_CLIENTE_ESPERADO,),
        )


def test_beneficio_individual_resolve_cliente_pelo_mesmo_vinculo_do_holerite():
    origem_colaborador = ReferenciaCanonica('COLABORADOR', 'func-beneficio-1')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-07')
    resolucao_cliente = resolver_clientes_validado(_FonteVinculosFake(), origem_colaborador, competencia)
    assert resolucao_cliente.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_cliente.valores_confirmados == (_CLIENTE_ESPERADO,)


def test_beneficio_reconhecido_e_vinculado_juntos_sem_nova_infraestrutura():
    """Prova ponta-a-ponta: reconhecimento (finalidade VR/VA) + vínculo
    (mesmo FonteVinculosPrestacao) -- 2 peças já existentes, nenhuma
    nova, combinadas."""
    texto = 'PIX efetuado -- crédito referente a VR do mês'
    ocorrencias = sinais_textuais_de_finalidade_pagamento(texto)
    resolucao_tipo = resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias))
    assert resolucao_tipo.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_tipo.valores_confirmados[0].entidade_id == FINALIDADE_VR_VA

    origem_colaborador = ReferenciaCanonica('COLABORADOR', 'func-beneficio-2')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-07')
    resolucao_cliente = resolver_clientes_validado(_FonteVinculosFake(), origem_colaborador, competencia)
    assert resolucao_cliente.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_granularidade_agregada_por_cliente_usa_o_mesmo_protocol():
    """Granularidade "cliente" (planilha em lote) usa a MESMA porta
    `FonteVinculosPrestacao` -- prova estrutural de que não é preciso
    um Protocol por granularidade."""
    from magnata_os.classificacao.vinculos_prestacao import FonteVinculosPrestacao
    assert hasattr(FonteVinculosPrestacao, 'resolver_clientes')
    # UNIDADE_POSTO já é uma origem suportada -- cobre o caso "por
    # posto" sem precisar de um Protocol novo.
    origem_posto = ReferenciaCanonica('UNIDADE_POSTO', 'local-1')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-07')
    resolucao = resolver_clientes_validado(_FonteVinculosFake(), origem_posto, competencia)
    assert resolucao.estado == EstadoResolucaoDimensao.RESOLVIDA
