"""Prova de integração do compositor geral de resolução semântica
(magnata_os/classificacao/resolucao_semantica.py) com os especialistas
REAIS do corredor documental -- missão "RECONCILIAÇÃO E ATIVAÇÃO DA
FASE 2E".

Nenhuma peça aqui é reimplementada nem mockada no nível de contrato:
usa `classificar_documento` real, `resolver_funcionario` real,
`resolver_clientes_validado` real (só a fonte de dados externa é fake,
mesmo padrão já usado em toda a suíte), `validar_competencia` real e
`PoliticaCompetenciaPrestacao`/`POLITICA_COMPETENCIA_PRESTACAO_V1`
reais (a mesma política que já ativa a exceção do SKY Tatuí em
produção).

Este teste NÃO reescreve `servico_lote.py`/`ponte_prestacao_holerite.py`
-- prova que as peças que eles já produzem hoje (classificação,
identificação, vínculo, competência) podem alimentar o compositor sem
nenhuma alteração de forma. A integração DENTRO do módulo produtor
(`ItemResumoLote`/ponte) fica registrada como próxima migração (ver PR),
não feita aqui -- exatamente a opção que a missão autoriza quando
substituir a ponte agora ampliaria o escopo sem necessidade comprovada.
"""
from magnata_os.classificacao.classificador_documental import (
    classificar_documento,
    resultado_classificacao_para_resolucao_dimensao,
)
from magnata_os.classificacao.competencia_esperada_prestacao import (
    POLITICA_COMPETENCIA_PRESTACAO_V1,
    REFERENCIA_CLIENTE_SKY_TATUI,
    ContextoCicloPrestacao,
    PoliticaCompetenciaPrestacao,
)
from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    ConfiancaResolucao,
    DimensaoResolucao,
    EntradaResolucaoDocumento,
    EstadoResolucaoDimensao,
    EstadoResultadoSemantico,
    NivelConfianca,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    RegraAplicabilidadeDimensao,
    ResolucaoDimensao,
)
from magnata_os.classificacao.resolucao_semantica import (
    compor_resolucao_semantica,
    resolucao_competencia_de_validacao,
)
from magnata_os.classificacao.vinculos_prestacao import resolver_clientes_validado
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario
from magnata_os.documental.importacao_lote.dominio import (
    resolver_funcionario,
    validar_competencia,
)
from magnata_os.documental.importacao_lote.contratos import (
    CompetenciaExtraida,
    StatusExtracaoCompetencia,
)
from magnata_os.documental.modulo01.politica_identificacao_holerite import (
    correspondencia_para_resolucao_dimensao,
)


class _FonteVinculosFake:
    """Mesmo papel de FonteVinculosPrestacaoFake já usado em
    test_prestacao_shadow_e2e.py/test_corredor_prestacao_holerite_e2e.py
    -- fonte de dados externa fake, contrato real (`resolver_clientes_validado`)
    sem alteração."""

    def __init__(self, resolucao):
        self._resolucao = resolucao

    def resolver_clientes(self, origem, competencia):
        return self._resolucao


def _perfil_documento_avulso():
    """Perfil genérico usado por este teste: 4 dimensões obrigatórias
    (as que já têm resolvedor real hoje) e 2 explicitamente NAO_APLICAVEL
    (UNIDADE_POSTO/VINCULO -- nenhum resolvedor real existe ainda para
    elas, e o perfil declara isso honestamente em vez de omitir)."""
    obrigatorias = (
        DimensaoResolucao.TIPO_DOCUMENTAL,
        DimensaoResolucao.COLABORADOR,
        DimensaoResolucao.CLIENTE,
        DimensaoResolucao.COMPETENCIA,
    )
    nao_aplicaveis = (DimensaoResolucao.UNIDADE_POSTO, DimensaoResolucao.VINCULO)
    regras = tuple(
        RegraAplicabilidadeDimensao(
            dimensao=dimensao, aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA,
            cardinalidade=Cardinalidade(1, 1),
        )
        for dimensao in obrigatorias
    ) + tuple(
        RegraAplicabilidadeDimensao(
            dimensao=dimensao, aplicabilidade=AplicabilidadeDimensao.NAO_APLICAVEL,
            cardinalidade=Cardinalidade(0, 0),
        )
        for dimensao in nao_aplicaveis
    )
    return PerfilAplicabilidadeResolucao(
        perfil_id='documento-avulso-v1', version='1',
        escopo_documental='prestacao-contas', regras=regras,
    )


def _compor_para_colaborador(
    *, cliente_esperado: ReferenciaCanonica, competencia_esperada: tuple,
    resolucao_vinculo: ResolucaoDimensao, documento_id: str,
):
    """Atravessa os especialistas REAIS (classificação, identificação,
    vínculo, competência) e compõe UM ResultadoResolucaoSemantico --
    nenhuma peça aqui conhece o resultado final antes da composição."""
    # 1) Classificação real -- mesmo texto que o corredor de Holerite já
    # usa em produção (roteamento_documental.py/servico_lote.py).
    resultado_classificacao = classificar_documento(
        'Recibo de Pagamento\nTotal de Vencimentos\nValor Líquido')
    resolucao_tipo = resultado_classificacao_para_resolucao_dimensao(resultado_classificacao)
    assert resolucao_tipo.estado == EstadoResolucaoDimensao.RESOLVIDA

    # 2) Identificação real -- resolver_funcionario + tradutor já usado
    # pelo gate de identificação de Holerite avulso.
    candidatos = [CandidatoFuncionario(func_id='func-1', cpf='12345678901', nome_normalizado='JOAO DA SILVA')]
    correspondencia = resolver_funcionario('12345678901', 'JOAO DA SILVA', candidatos)
    resolucao_colaborador = correspondencia_para_resolucao_dimensao(correspondencia)
    assert resolucao_colaborador.estado == EstadoResolucaoDimensao.RESOLVIDA

    # 3) Vínculo real -- resolver_clientes_validado (vinculos_prestacao.py),
    # já a forma correta de ResolucaoDimensao(CLIENTE), sem tradução.
    origem = ReferenciaCanonica('COLABORADOR', 'func-1')
    fonte_vinculos = _FonteVinculosFake(resolucao_vinculo)
    resolucao_cliente = resolver_clientes_validado(
        fonte_vinculos, origem, ReferenciaCanonica('COMPETENCIA', '2026-07'))
    assert resolucao_cliente.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_cliente.valores_confirmados == (cliente_esperado,)

    # 4) Competência real -- validar_competencia (importacao_lote/dominio.py)
    # + PoliticaCompetenciaPrestacao/ContextoCicloPrestacao reais.
    ano_esperado, mes_esperado = competencia_esperada
    competencia_observada = CompetenciaExtraida(
        status=StatusExtracaoCompetencia.ENCONTRADA, ano_mes=(ano_esperado, mes_esperado),
        estrategia='mm_aaaa_numerico',
    )
    resultado_validacao = validar_competencia(competencia_observada, ano_esperado, mes_esperado)
    resolucao_competencia = resolucao_competencia_de_validacao(
        resultado_validacao, (ano_esperado, mes_esperado))
    assert resolucao_competencia.estado == EstadoResolucaoDimensao.RESOLVIDA

    # 5) Composição.
    entrada = EntradaResolucaoDocumento(
        documento_id=documento_id,
        hash_sha256='a' * 64,
        resolver_id='resolucao-semantica-v1',
        resolver_version='1',
        politica_id='documento-avulso-v1',
        politica_version='1',
        contexto_fontes_fingerprint='classificacao+identificacao+vinculo+competencia',
    )
    perfil = _perfil_documento_avulso()
    resolucoes = (
        resolucao_tipo,
        resolucao_colaborador,
        resolucao_cliente,
        resolucao_competencia,
        ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
    )
    return compor_resolucao_semantica(entrada, perfil, resolucoes)


# ============================================================================
# CASO 7 -- resultado semântico com tipo + colaborador + cliente +
# competência, todos resolvidos pelas peças reais do corredor.
# ============================================================================

def test_caso7_resultado_semantico_completo_cliente_comum():
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-comum')
    resolucao_vinculo = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(cliente,), confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )

    resultado = _compor_para_colaborador(
        cliente_esperado=cliente, competencia_esperada=(2026, 7),
        resolucao_vinculo=resolucao_vinculo, documento_id='doc-cliente-comum',
    )

    assert resultado.estado_consolidado == EstadoResultadoSemantico.RESOLVIDA
    assert resultado.necessita_revisao_humana is False
    assert resultado.pronto_para_routing_logico is True
    por_dimensao = {r.dimensao: r for r in resultado.resolucoes}
    assert por_dimensao[DimensaoResolucao.TIPO_DOCUMENTAL].valores_confirmados == (
        ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite'),)
    assert por_dimensao[DimensaoResolucao.COLABORADOR].valores_confirmados == (
        ReferenciaCanonica('COLABORADOR', 'func-1'),)
    assert por_dimensao[DimensaoResolucao.CLIENTE].valores_confirmados == (cliente,)
    assert por_dimensao[DimensaoResolucao.COMPETENCIA].valores_confirmados == (
        ReferenciaCanonica('COMPETENCIA', '2026-07'),)


# ============================================================================
# CASO 15/16 -- SKY continua base-1 e cliente comum continua base normal,
# através do MESMO compositor genérico, sem nenhuma condicional por tipo.
# ============================================================================

def test_caso15_sky_continua_base_menos_um_mes_via_compositor():
    contexto = ContextoCicloPrestacao(competencia_base=(2026, 7))
    competencia_sky = POLITICA_COMPETENCIA_PRESTACAO_V1.competencia_esperada_para(
        contexto, REFERENCIA_CLIENTE_SKY_TATUI, 'holerite')
    assert competencia_sky == (2026, 6)  # nenhuma regressão da regra já ativada

    resolucao_vinculo = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(REFERENCIA_CLIENTE_SKY_TATUI,), confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )

    resultado = _compor_para_colaborador(
        cliente_esperado=REFERENCIA_CLIENTE_SKY_TATUI, competencia_esperada=competencia_sky,
        resolucao_vinculo=resolucao_vinculo, documento_id='doc-sky',
    )

    assert resultado.estado_consolidado == EstadoResultadoSemantico.RESOLVIDA
    por_dimensao = {r.dimensao: r for r in resultado.resolucoes}
    assert por_dimensao[DimensaoResolucao.COMPETENCIA].valores_confirmados == (
        ReferenciaCanonica('COMPETENCIA', '2026-06'),)


def test_caso16_cliente_comum_continua_competencia_base_normal_via_compositor():
    contexto = ContextoCicloPrestacao(competencia_base=(2026, 7))
    politica_sem_excecoes = PoliticaCompetenciaPrestacao(version='1')
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-comum-2')
    competencia_comum = politica_sem_excecoes.competencia_esperada_para(contexto, cliente, 'holerite')
    assert competencia_comum == (2026, 7)  # base normal, sem deslocamento

    resolucao_vinculo = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(cliente,), confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )

    resultado = _compor_para_colaborador(
        cliente_esperado=cliente, competencia_esperada=competencia_comum,
        resolucao_vinculo=resolucao_vinculo, documento_id='doc-cliente-comum-2',
    )

    assert resultado.estado_consolidado == EstadoResultadoSemantico.RESOLVIDA


# ============================================================================
# Genericidade (macro-objetivo 5) -- o MESMO compositor, com um tipo
# documental diferente e um método de resolução de cliente diferente
# (nunca via vínculo/CPF), sem nenhuma alteração de código.
# ============================================================================

def test_compositor_aceita_outro_tipo_documental_e_outro_metodo_de_cliente():
    resultado_classificacao = classificar_documento('Extrato Mensal\nExtrato da Folha de Pagamento')
    resolucao_tipo = resultado_classificacao_para_resolucao_dimensao(resultado_classificacao)
    assert resolucao_tipo.valores_confirmados == (
        ReferenciaCanonica('TIPO_DOCUMENTAL', 'Extrato da Folha de Pagamento'),)

    # Cliente resolvido por um método TOTALMENTE diferente do vínculo
    # colaborador->cliente (aqui, CNPJ exato) -- o compositor não sabe
    # nem precisa saber a diferença.
    resolucao_cliente = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(ReferenciaCanonica('CLIENTE', 'cliente-por-cnpj'),),
        metodo='cnpj_exato', confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )
    # Este tipo documental é COMPETENCIA_GLOBAL/CLIENTE -- não tem
    # colaborador (perfil declara COLABORADOR como NAO_APLICAVEL aqui,
    # ao contrário do teste de Holerite acima).
    perfil = PerfilAplicabilidadeResolucao(
        perfil_id='documento-cliente-v1', version='1', escopo_documental='prestacao-contas',
        regras=(
            RegraAplicabilidadeDimensao(DimensaoResolucao.TIPO_DOCUMENTAL, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COLABORADOR, AplicabilidadeDimensao.NAO_APLICAVEL, Cardinalidade(0, 0)),
        ),
    )
    entrada = EntradaResolucaoDocumento(
        documento_id='doc-extrato', hash_sha256='b' * 64,
        resolver_id='resolucao-semantica-v1', resolver_version='1',
        politica_id='documento-cliente-v1', politica_version='1',
        contexto_fontes_fingerprint='classificacao+cliente-por-cnpj',
    )
    resolucoes = (
        resolucao_tipo,
        resolucao_cliente,
        ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
    )

    resultado = compor_resolucao_semantica(entrada, perfil, resolucoes)

    assert resultado.estado_consolidado == EstadoResultadoSemantico.RESOLVIDA
    assert resultado.pronto_para_routing_logico is True
