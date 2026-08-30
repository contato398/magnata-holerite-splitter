"""Corpus E2E HETEROGÊNEO (missão "AUTOMAÇÃO DOCUMENTAL REAL V1", §19):
"documentos que NÃO dependam do nome perfeito... resultado deve ser
semanticamente correto ou revisão explícita, nunca classificação
silenciosamente errada".

Cada caso usa o MESMO motor (`classificador_documental.py` + produtores
de evidência + `resolver_tipo_documental`) — nunca um classificador
paralelo por documento (§21)."""
from magnata_os.classificacao.classificador_documental import classificar_documento
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao
from magnata_os.classificacao.finalidade_comprovante_pagamento import (
    hipoteses_de_finalidade_pagamento,
    sinais_textuais_de_finalidade_pagamento,
)
from magnata_os.classificacao.produtores_evidencia_documental import hipoteses_textuais_de_classificacao
from magnata_os.classificacao.produtores_evidencia_extrato import hipoteses_de_rotulo_alternativo_de_extrato
from magnata_os.classificacao.produtores_evidencia_fiscal import (
    hipoteses_fiscais_de_texto,
    reconciliar_evidencia_fiscal_com_finalidade,
)
from magnata_os.classificacao.produtores_evidencia_ponto import hipoteses_estruturais_de_ponto
from magnata_os.classificacao.reconciliacao_origem_conteudo import (
    ResultadoReconciliacaoOrigem,
    reconciliar_origem_com_resolucao_semantica,
)
from magnata_os.classificacao.resolucao_tipo_documental import resolver_tipo_documental
from magnata_os.classificacao.automacao_por_confianca import DecisaoAutomacao, decidir_proxima_acao
from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    DimensaoResolucao,
    EntradaResolucaoDocumento,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    RegraAplicabilidadeDimensao,
    ResolucaoDimensao,
)
from magnata_os.classificacao.resolucao_semantica import compor_resolucao_semantica


def _perfil():
    return PerfilAplicabilidadeResolucao(
        perfil_id='corpus-heterogeneo-v1', version='1', escopo_documental='teste',
        regras=(
            RegraAplicabilidadeDimensao(DimensaoResolucao.TIPO_DOCUMENTAL, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COLABORADOR, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.UNIDADE_POSTO, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.VINCULO, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
        ),
    )


def _resultado(resolucao_tipo, documento_id):
    return compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id=documento_id, hash_sha256='a' * 64, resolver_id='corpus', resolver_version='1',
            politica_id='corpus-heterogeneo-v1', politica_version='1',
            contexto_fontes_fingerprint='corpus-heterogeneo-e2e',
        ),
        perfil=_perfil(),
        resolucoes=(
            resolucao_tipo,
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
            ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ),
    )


def _hipoteses_textuais(texto):
    return hipoteses_textuais_de_classificacao(classificar_documento(texto))


# ============================================================================
# 1) Holerite SEM a palavra "Holerite"
# ============================================================================

def test_holerite_sem_a_palavra_holerite():
    texto = 'Recibo de Pagamento -- Competência 07/2026\nTotal de Vencimentos: R$ 3.200,00\nValor Líquido: R$ 2.850,00'
    assert 'holerite' not in texto.lower()
    resolucao_tipo = resolver_tipo_documental(_hipoteses_textuais(texto))
    resultado = _resultado(resolucao_tipo, 'holerite-sem-titulo')
    assert resolucao_tipo.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_tipo.valores_confirmados[0].entidade_id == 'Holerite'
    assert decidir_proxima_acao(resultado) == DecisaoAutomacao.AVANCA_AUTOMATICO


# ============================================================================
# 2) Folha de Ponto SEM o título "Folha de Ponto"
# ============================================================================

def test_ponto_sem_titulo_folha_de_ponto():
    texto = (
        '29/04/26 - Qua - C1 18:56 01:00 01:53 09:05\n'
        '30/04/26 - Qui - C1 18:50 01:00 01:50 09:00\n'
        'Período: 01/04/2026 até 30/04/2026'
    )
    assert 'folha de ponto' not in texto.lower() and 'secullum' not in texto.lower()
    hipoteses = _hipoteses_textuais(texto) + hipoteses_estruturais_de_ponto(texto)
    resolucao_tipo = resolver_tipo_documental(hipoteses)
    assert resolucao_tipo.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_tipo.valores_confirmados[0].entidade_id == 'Folha de Ponto'


# ============================================================================
# 3) Extrato chamado "Resumo da Folha" (nunca "Extrato Mensal")
# ============================================================================

def test_extrato_chamado_resumo_da_folha():
    texto = 'Resumo da Folha de Pagamento -- Competência 07/2026'
    assert 'extrato' not in texto.lower()
    hipoteses = _hipoteses_textuais(texto) + hipoteses_de_rotulo_alternativo_de_extrato(texto)
    resolucao_tipo = resolver_tipo_documental(hipoteses)
    assert resolucao_tipo.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_tipo.valores_confirmados[0].entidade_id == 'Extrato da Folha de Pagamento'


# ============================================================================
# 4) Guia DARF/FGTS sem "DCTFWeb" -- nunca depende de filename (o motor
# nunca sequer recebe filename como parâmetro)
# ============================================================================

def test_guia_fgts_sem_dctfweb_e_sem_depender_de_filename():
    texto = 'Guia do FGTS Digital -- Código de Receita: 0561 -- Total FGTS'
    hipoteses = _hipoteses_textuais(texto) + hipoteses_fiscais_de_texto(texto)
    resolucao_tipo = resolver_tipo_documental(hipoteses)
    assert resolucao_tipo.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_tipo.valores_confirmados[0].entidade_id == 'FGTS'
    # nenhuma função usada acima aceita sequer um parâmetro "filename".
    import inspect
    for func in (classificar_documento, hipoteses_fiscais_de_texto, resolver_tipo_documental):
        assert 'filename' not in inspect.signature(func).parameters


# ============================================================================
# 5) VR/VA com nomes diferentes (nunca a sigla isolada decidindo sozinha)
# ============================================================================

def test_vr_va_com_estrutura_bancaria_e_descricao_variada():
    texto = 'PIX efetuado -- crédito referente ao VR do mês de referência'
    ocorrencias = sinais_textuais_de_finalidade_pagamento(texto)
    resolucao_finalidade = resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias))
    assert resolucao_finalidade.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_finalidade.valores_confirmados[0].entidade_id == 'Comprovante de Pagamento - VR/VA'


# ============================================================================
# 6) Documento em tabela "errada" -- origem contraditória ao conteúdo
# ============================================================================

def test_documento_com_origem_contraditoria_ao_conteudo_vira_conflito():
    """Registro chegou pela tabela 'Holerites' (origem), mas o CONTEÚDO
    resolve para FGTS -- REGRA CRÍTICA §12: origem sozinha nunca prova o
    tipo; a divergência tem que aparecer como CONFLITO explícito."""
    texto = 'Guia do FGTS Digital -- Código de Receita: 0561 -- Total FGTS'
    hipoteses = _hipoteses_textuais(texto) + hipoteses_fiscais_de_texto(texto)
    resolucao_tipo = resolver_tipo_documental(hipoteses)
    resultado = _resultado(resolucao_tipo, 'doc-tabela-errada')

    reconciliacao = reconciliar_origem_com_resolucao_semantica('Holerite', resultado)
    assert reconciliacao.resultado == ResultadoReconciliacaoOrigem.CONFLITO
    assert reconciliacao.tipo_resolvido == 'FGTS'

    # mesmo documento, origem CORRETA -> reforço, nunca conflito.
    reconciliacao_correta = reconciliar_origem_com_resolucao_semantica('FGTS', resultado)
    assert reconciliacao_correta.resultado == ResultadoReconciliacaoOrigem.REFORCO


# ============================================================================
# 7) Reforço fiscal <-> finalidade -- reforça sem depender do nome do banco
# ============================================================================

def test_comprovante_fgts_sem_depender_do_nome_do_banco():
    """O reforço fiscal só CONFIRMA uma finalidade já sustentada por
    descrição -- nunca infere sozinho a partir de estrutura bancária
    isolada (ex.: só citar 'Sicoob', sem nenhuma frase característica,
    nunca basta: ver `produtores_evidencia_fiscal.py`)."""
    texto_fiscal = 'Guia do FGTS -- Código de Receita: 0561'
    ocorrencias = sinais_textuais_de_finalidade_pagamento(texto_fiscal) + reconciliar_evidencia_fiscal_com_finalidade(texto_fiscal)
    resolucao_finalidade = resolver_tipo_documental(hipoteses_de_finalidade_pagamento(ocorrencias))
    assert resolucao_finalidade.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_finalidade.valores_confirmados[0].entidade_id == 'Comprovante de Pagamento - FGTS'
    assert 'sicoob' not in texto_fiscal.lower() and 'banco' not in texto_fiscal.lower()


# ============================================================================
# 8) Documento verdadeiramente desconhecido -- nunca "classificação
# silenciosamente errada", sempre estado explícito de desconhecido
# ============================================================================

def test_documento_desconhecido_nunca_e_classificado_silenciosamente():
    texto = 'lorem ipsum dolor sit amet, nenhuma evidencia conhecida aqui'
    resolucao_tipo = resolver_tipo_documental(_hipoteses_textuais(texto))
    resultado = _resultado(resolucao_tipo, 'doc-desconhecido')
    assert resolucao_tipo.estado != EstadoResolucaoDimensao.RESOLVIDA
    assert decidir_proxima_acao(resultado) in (DecisaoAutomacao.DESCONHECIDO, DecisaoAutomacao.REVISAO_HUMANA)
