"""Suíte E2E obrigatória (§20 da missão "MERGE PR #105 + EVIDÊNCIA
RELACIONAL DOCUMENTO↔DOCUMENTO + VÍNCULO/UNIDADE_POSTO REAIS +
FECHAMENTO DO UNIVERSO DOCUMENTAL V1") -- casos A a J, cada um mapeado
1:1 ao texto da missão. Casos A-C exercitam o corredor REAL
(`processar_documento_prestacao`) com os produtores de VÍNCULO/
UNIDADE_POSTO desta missão; casos D-I exercitam a capacidade relacional
genérica (`relacao_documental.py`) diretamente -- honesto sobre o
escopo: a costura completa dessa capacidade DENTRO do corredor
(auto-atribuição de clientes lógicos ao comprovante global via
`avancar_para_inventario`) ainda não foi feita nesta missão (ver
documento de decisão, seção "PENDÊNCIA REGISTRADA") -- os testes aqui
provam a CAPACIDADE em si, não uma costura de orquestração que ainda
não existe. Caso J prova idempotência da camada pura (resolvedores sem
I/O nem estado mutável -- mesma entrada, mesma saída sempre)."""
from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.classificacao.perfil_aplicabilidade_documental import perfil_para_tipo
from magnata_os.classificacao.produtores_evidencia_beneficios import (
    dados_correlacao_beneficios,
    derivar_clientes_logicos_do_comprovante_global,
)
from magnata_os.classificacao.relacao_documental import (
    DadosCorrelacaoDocumental,
    TipoRelacaoDocumental,
    produzir_evidencias_correlacao,
    resolver_relacao_documental_par,
)
from magnata_os.classificacao.resolucao_documento_prestacao import (
    ContextoResolucaoDocumentoPrestacao,
    EstadoCorredorDocumentoPrestacao,
    processar_documento_prestacao,
)
from magnata_os.classificacao.vinculo_unidade_prestacao import (
    MOTIVO_VINCULO_ATUAL_COMO_PROXY,
    resolucao_vinculo_a_partir_de_cliente,
)
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario


class _FonteVinculosFake:
    def __init__(self, cliente_id='cli-sky'):
        self._cliente_id = cliente_id

    def resolver_clientes(self, origem, competencia):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(ReferenciaCanonica('CLIENTE', self._cliente_id),),
        )


class _FonteUnidadePostoFake:
    def __init__(self, postos=(ReferenciaCanonica('UNIDADE_POSTO', 'posto-1'),)):
        self._postos = postos

    def resolver_unidade_posto(self, colaborador, competencia):
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=self._postos,
        )


def _candidatos():
    return [CandidatoFuncionario(func_id='f1', cpf='11122233344', nome_normalizado='X')]


def _contexto(documento_id, fonte_unidade_posto, competencia_e_corrente=True):
    return ContextoResolucaoDocumentoPrestacao(
        documento_id=documento_id, hash_sha256='a' * 64, competencia_esperada=(2026, 7),
        candidatos_colaborador=_candidatos(), fonte_vinculos=_FonteVinculosFake(),
        fonte_unidade_posto=fonte_unidade_posto, competencia_e_corrente=competencia_e_corrente,
    )


# --- Caso A: Holerite completo -- colaborador->vínculo->posto->cliente->pacote ---

def test_caso_a_holerite_colaborador_vinculo_posto_cliente_pacote():
    resultado = processar_documento_prestacao(
        'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026\nCPF: 111.222.333-44',
        _contexto('e2e-a', _FonteUnidadePostoFake()),
    )
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    resolucoes = {r.dimensao: r for r in resultado.resolucao_semantica.resolucoes}
    assert resolucoes[DimensaoResolucao.COLABORADOR].estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucoes[DimensaoResolucao.VINCULO].estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucoes[DimensaoResolucao.UNIDADE_POSTO].estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucoes[DimensaoResolucao.CLIENTE].estado == EstadoResolucaoDimensao.RESOLVIDA


# --- Caso B: colaborador com 2 postos legítimos -- nunca escolhido silenciosamente ---

def test_caso_b_colaborador_com_2_postos_legitimos_cardinalidade_preservada():
    dois_postos = (ReferenciaCanonica('UNIDADE_POSTO', 'posto-A'), ReferenciaCanonica('UNIDADE_POSTO', 'posto-B'))
    resultado = processar_documento_prestacao(
        'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026\nCPF: 111.222.333-44',
        _contexto('e2e-b', _FonteUnidadePostoFake(postos=dois_postos)),
    )
    resolucao_unidade_posto = next(
        r for r in resultado.resolucao_semantica.resolucoes if r.dimensao == DimensaoResolucao.UNIDADE_POSTO
    )
    assert resolucao_unidade_posto.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert set(resolucao_unidade_posto.valores_confirmados) == set(dois_postos)
    assert len(resolucao_unidade_posto.valores_confirmados) == 2  # nunca colapsado a 1


# --- Caso C: vínculo corrente sem prova histórica -- nunca vira verdade histórica ---

def test_caso_c_vinculo_corrente_como_proxy_nunca_verdade_historica():
    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-1')
    resolucao_cliente = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(ReferenciaCanonica('CLIENTE', 'cli-x'),),
    )
    resolucao_vinculo = resolucao_vinculo_a_partir_de_cliente(colaborador, resolucao_cliente, competencia_e_corrente=False)
    assert resolucao_vinculo.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert MOTIVO_VINCULO_ATUAL_COMO_PROXY in resolucao_vinculo.motivos

    resolucao_vinculo_corrente = resolucao_vinculo_a_partir_de_cliente(
        colaborador, resolucao_cliente, competencia_e_corrente=True,
    )
    assert MOTIVO_VINCULO_ATUAL_COMO_PROXY not in resolucao_vinculo_corrente.motivos


# --- Caso D: comprovante global entra só nos clientes corretos ---

def test_caso_d_comprovante_global_beneficios_entra_somente_nos_clientes_corretos():
    clientes_do_relatorio = (ReferenciaCanonica('CLIENTE', 'cli-a'), ReferenciaCanonica('CLIENTE', 'cli-b'))
    a = DadosCorrelacaoDocumental(identificador_pedido='PED-1', valor_total='900,00', competencia=(2026, 7))
    b = DadosCorrelacaoDocumental(identificador_pedido='PED-1', valor_total='900,00', competencia=(2026, 7))
    relacao = resolver_relacao_documental_par(
        'comprovante-global-1', 'relatorio-1', TipoRelacaoDocumental.COMPROVA, produzir_evidencias_correlacao(a, b),
    )
    assert relacao.estado == EstadoResolucaoDimensao.RESOLVIDA
    clientes_do_comprovante = derivar_clientes_logicos_do_comprovante_global(
        relacao.estado == EstadoResolucaoDimensao.RESOLVIDA, clientes_do_relatorio,
    )
    assert clientes_do_comprovante == clientes_do_relatorio
    assert ReferenciaCanonica('CLIENTE', 'cli-c') not in clientes_do_comprovante  # nunca broadcast a mais


# --- Caso E: comprovante sem relação suficiente -- não resolve ---

def test_caso_e_comprovante_beneficios_sem_relacao_suficiente_nao_resolve():
    a = DadosCorrelacaoDocumental(fornecedor='vr benefícios')
    b = DadosCorrelacaoDocumental(fornecedor='vr benefícios')
    relacao = resolver_relacao_documental_par(
        'comprovante-2', 'relatorio-2', TipoRelacaoDocumental.COMPROVA, produzir_evidencias_correlacao(a, b),
    )
    assert relacao.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert derivar_clientes_logicos_do_comprovante_global(
        relacao.estado == EstadoResolucaoDimensao.RESOLVIDA, (ReferenciaCanonica('CLIENTE', 'cli-a'),),
    ) == ()


# --- Caso F: mesmo valor, pedido diferente -- nunca relaciona só por valor ---

def test_caso_f_mesmo_valor_pedido_diferente_nunca_relaciona_so_por_valor():
    a = DadosCorrelacaoDocumental(identificador_pedido='PED-A', valor_total='500,00')
    b = DadosCorrelacaoDocumental(identificador_pedido='PED-B', valor_total='500,00')
    relacao = resolver_relacao_documental_par(
        'comprovante-3', 'relatorio-3', TipoRelacaoDocumental.COMPROVA, produzir_evidencias_correlacao(a, b),
    )
    assert relacao.estado == EstadoResolucaoDimensao.CONFLITO


# --- Caso G: FGTS guia+comprovante -- relação comprovada, mesma infra genérica ---

def test_caso_g_fgts_guia_comprovante_relacao_comprovada_mesma_infra_generica():
    """Reaproveita a MESMA `relacao_documental` -- nenhum motor/classe
    específico de FGTS criado (§9)."""
    guia = DadosCorrelacaoDocumental(identificador_pedido='GUIA-77', competencia=(2026, 7), valor_total='2.500,00')
    comprovante = DadosCorrelacaoDocumental(identificador_pedido='GUIA-77', competencia=(2026, 7), valor_total='2.500,00')
    relacao = resolver_relacao_documental_par(
        'comprovante-fgts-1', 'guia-fgts-1', TipoRelacaoDocumental.COMPROVA,
        produzir_evidencias_correlacao(guia, comprovante),
    )
    assert relacao.estado == EstadoResolucaoDimensao.RESOLVIDA
    # FGTS continua cliente-level (perfil preservado do PR #105 -- nunca broadcast).
    perfil_fgts = perfil_para_tipo('FGTS')
    from magnata_os.classificacao.contratos import AplicabilidadeDimensao, Cardinalidade
    assert perfil_fgts.regra_para(DimensaoResolucao.CLIENTE).cardinalidade == Cardinalidade(1, 1)


# --- Caso H: DCTF guia+comprovante -- broadcast preservado ---

def test_caso_h_dctf_guia_comprovante_relacao_modelada_broadcast_preservado():
    from magnata_os.classificacao.contratos import AplicabilidadeDimensao

    guia = DadosCorrelacaoDocumental(identificador_pedido='DCTF-9', competencia=(2026, 7))
    comprovante = DadosCorrelacaoDocumental(identificador_pedido='DCTF-9', competencia=(2026, 7))
    relacao = resolver_relacao_documental_par(
        'comprovante-dctf-1', 'guia-dctf-1', TipoRelacaoDocumental.COMPROVA,
        produzir_evidencias_correlacao(guia, comprovante),
    )
    assert relacao.estado == EstadoResolucaoDimensao.RESOLVIDA
    perfil_dctf = perfil_para_tipo('Guia DCTFWeb/DARF')
    assert perfil_dctf.regra_para(DimensaoResolucao.CLIENTE).aplicabilidade == AplicabilidadeDimensao.NAO_APLICAVEL


# --- Caso I: fornecedor de benefício desconhecido -- fluxo idêntico ---

def test_caso_i_fornecedor_desconhecido_fluxo_relacional_identico():
    texto_relatorio = 'Relatório de Benefícios\nPedido no: PED-55\nTotal do Pedido: R$ 300,00\nFornecedor Novo Ltda'
    texto_comprovante = 'Comprovante de Pagamento\nPedido no: PED-55\nTotal do Pedido: R$ 300,00'
    dados_a = dados_correlacao_beneficios(texto_relatorio)
    dados_b = dados_correlacao_beneficios(texto_comprovante)
    assert dados_a.fornecedor is None  # fornecedor desconhecido: nunca extraído, nunca bloqueia
    relacao = resolver_relacao_documental_par(
        'comprovante-4', 'relatorio-4', TipoRelacaoDocumental.COMPROVA, produzir_evidencias_correlacao(dados_a, dados_b),
    )
    assert relacao.estado == EstadoResolucaoDimensao.RESOLVIDA


# --- Caso J: execução repetida -- idempotente ---

def test_caso_j_execucao_repetida_idempotente_camada_pura():
    a = DadosCorrelacaoDocumental(identificador_pedido='PED-1', valor_total='900,00', competencia=(2026, 7))
    b = DadosCorrelacaoDocumental(identificador_pedido='PED-1', valor_total='900,00', competencia=(2026, 7))
    r1 = resolver_relacao_documental_par('doc-a', 'doc-b', TipoRelacaoDocumental.COMPROVA, produzir_evidencias_correlacao(a, b))
    r2 = resolver_relacao_documental_par('doc-a', 'doc-b', TipoRelacaoDocumental.COMPROVA, produzir_evidencias_correlacao(a, b))
    assert r1 == r2

    colaborador = ReferenciaCanonica('COLABORADOR', 'colab-1')
    resolucao_cliente = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(ReferenciaCanonica('CLIENTE', 'cli-x'),),
    )
    v1 = resolucao_vinculo_a_partir_de_cliente(colaborador, resolucao_cliente, competencia_e_corrente=False)
    v2 = resolucao_vinculo_a_partir_de_cliente(colaborador, resolucao_cliente, competencia_e_corrente=False)
    assert v1 == v2
