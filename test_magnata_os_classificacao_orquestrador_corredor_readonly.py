"""Testes do orquestrador canônico/puro (missão "CONSTRUIR ORQUESTRADOR
REAL READ-ONLY DO CORREDOR V2 + PREPARAR PRIMEIRO LIVE CONTROLADO SEM
EXECUTÁ-LO"). Casos mapeados aos §25-31 da missão -- só Protocols/fakes
locais, nenhum acesso Airtable real (ver `test_importacao_lote_
composicao_corredor_readonly.py` para a composição de borda com
adapters reais e Mock de leitor)."""
from magnata_os.classificacao.competencia_esperada_prestacao import (
    DESLOCAMENTO_SKY_TATUI,
    POLITICA_COMPETENCIA_PRESTACAO_V1,
    REFERENCIA_CLIENTE_SKY_TATUI,
    ContextoCicloPrestacao,
    PoliticaCompetenciaPrestacao,
)
from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.classificacao.fonte_candidatos_relacao_documental_do_inventario import (
    EscopoClientesFixo,
    FonteCandidatosRelacaoDocumentalDoInventario,
    FonteDadosCorrelacaoEmMemoria,
)
from magnata_os.classificacao.inventario_prestacao_memoria import InventarioPrestacaoEmMemoria
from magnata_os.classificacao.orquestrador_corredor_readonly import (
    ContextoExecucaoCorredorPrestacao,
    executar_documento_readonly,
)
from magnata_os.classificacao.pacote_prestacao import EstadoPacotePrestacao
from magnata_os.classificacao.politica_requisitos_prestacao import PoliticaRequisitosPrestacao
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao, RequisitoDocumentalPrestacao
from magnata_os.classificacao.resolucao_documento_prestacao import EstadoCorredorDocumentoPrestacao
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario

_CLIENTE_A = ReferenciaCanonica('CLIENTE', 'cli-a')
_CLIENTE_B = ReferenciaCanonica('CLIENTE', 'cli-b')
_COMPETENCIA_0726 = ReferenciaCanonica('COMPETENCIA', '2026-07')
_COMPETENCIA_0626 = ReferenciaCanonica('COMPETENCIA', '2026-06')


class _FonteVinculosFake:
    def __init__(self, cliente=_CLIENTE_A):
        self._cliente = cliente

    def resolver_clientes(self, origem, competencia):
        if self._cliente is None:
            return ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA)
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(self._cliente,),
        )


class _FonteUnidadePostoSempreNaoEncontradaFake:
    def resolver_unidade_posto(self, colaborador, competencia):
        return ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA)


class _FonteClienteDiretoFake:
    """Fake de `FonteClienteDiretoDocumento` -- resolve por CNPJ literal
    presente no texto contra um índice injetado, mesmo contrato
    (`Optional[ReferenciaCanonica]`, `None` quando ambíguo/ausente/
    desconhecido) do adapter real, sem nenhum I/O."""

    def __init__(self, indice_cnpj_para_cliente):
        self._indice = indice_cnpj_para_cliente

    def resolver_cliente_direto(self, texto_documento):
        encontrados = {
            cliente for cnpj, cliente in self._indice.items() if cnpj in texto_documento
        }
        if len(encontrados) == 1:
            return next(iter(encontrados))
        return None


def _candidato(func_id, cpf, nome):
    return CandidatoFuncionario(func_id=func_id, cpf=cpf, nome_normalizado=nome)


def _contexto(**kwargs):
    base = dict(
        documento_id='doc-1', hash_sha256='a' * 64,
        ciclo=ContextoCicloPrestacao((2026, 7)),
    )
    base.update(kwargs)
    return ContextoExecucaoCorredorPrestacao(**base)


# ============================================================================
# §25 -- Holerite E2E obrigatório
# ============================================================================

def test_holerite_unidade_historica_sem_prova_resultado_honesto():
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026\nCPF: 111.222.333-44'
    ctx = _contexto(
        paginas=(texto,),
        candidatos_colaborador=[_candidato('func-1', '11122233344', 'JOAO')],
        fonte_vinculos=_FonteVinculosFake(), fonte_unidade_posto=_FonteUnidadePostoSempreNaoEncontradaFake(),
    )
    sink = InventarioPrestacaoEmMemoria()
    resultados = executar_documento_readonly(ctx, sink)
    assert len(resultados) == 1
    resultado = resultados[0].resultado_corredor
    # Classificação/competência/colaborador honestamente resolvidos --
    # UNIDADE_POSTO honestamente NAO_ENCONTRADA nunca impede o resto.
    assert resultado.tipo_documental == 'Holerite'
    dimensoes = {r.dimensao: r.estado for r in resultado.resolucao_semantica.resolucoes}
    assert dimensoes[DimensaoResolucao.COMPETENCIA] == EstadoResolucaoDimensao.RESOLVIDA
    assert dimensoes[DimensaoResolucao.COLABORADOR] == EstadoResolucaoDimensao.RESOLVIDA
    assert dimensoes[DimensaoResolucao.CLIENTE] == EstadoResolucaoDimensao.RESOLVIDA
    assert dimensoes[DimensaoResolucao.UNIDADE_POSTO] == EstadoResolucaoDimensao.NAO_ENCONTRADA
    # Nunca forçado como pacote completo -- REVISAO_NECESSARIA honesto,
    # nunca RESOLVIDO_E_AVANCOU maquiado.
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.REVISAO_NECESSARIA
    assert resultados[0].itens_inventario == ()


# ============================================================================
# §26 -- Extrato E2E obrigatório
# ============================================================================

def test_extrato_caso_a_cnpj_cliente_resolve_e_avanca_para_inventario():
    texto = 'Extrato Mensal\nCNPJ: 11.222.333/0001-44\nCompetência: 07/2026'
    ctx = _contexto(
        paginas=(texto,),
        fonte_cliente_direto=_FonteClienteDiretoFake({'11.222.333/0001-44': _CLIENTE_A}),
    )
    sink = InventarioPrestacaoEmMemoria()
    resultados = executar_documento_readonly(ctx, sink)
    resultado = resultados[0]
    assert resultado.resultado_corredor.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    assert len(resultado.itens_inventario) == 1
    assert resultado.itens_inventario[0].cliente == _CLIENTE_A


def test_extrato_caso_b_sem_cnpj_nunca_avanca():
    texto = 'Extrato Mensal\nsem nenhum CNPJ neste texto\nCompetência: 07/2026'
    ctx = _contexto(paginas=(texto,), fonte_cliente_direto=_FonteClienteDiretoFake({}))
    sink = InventarioPrestacaoEmMemoria()
    resultados = executar_documento_readonly(ctx, sink)
    resultado = resultados[0]
    assert resultado.resultado_corredor.estado != EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    assert resultado.itens_inventario == ()
    dimensoes = {r.dimensao: r.estado for r in resultado.resultado_corredor.resolucao_semantica.resolucoes}
    assert dimensoes[DimensaoResolucao.CLIENTE] != EstadoResolucaoDimensao.RESOLVIDA


def test_extrato_caso_c_dois_clientes_reais_no_texto_conflito():
    texto = 'Extrato Mensal\nCNPJ: 11.222.333/0001-44\nCNPJ: 55.666.777/0001-88\nCompetência: 07/2026'
    fonte = _FonteClienteDiretoFake({'11.222.333/0001-44': _CLIENTE_A, '55.666.777/0001-88': _CLIENTE_B})
    ctx = _contexto(paginas=(texto,), fonte_cliente_direto=fonte)
    sink = InventarioPrestacaoEmMemoria()
    resultados = executar_documento_readonly(ctx, sink)
    resultado = resultados[0]
    # Nunca escolhe arbitrariamente -- fake devolve None para 2+
    # encontrados (mesma disciplina do adapter real: CONFLICT -> None).
    assert resultado.resultado_corredor.estado != EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    assert resultado.itens_inventario == ()


# ============================================================================
# §27 -- FGTS E2E obrigatório
# ============================================================================

def test_fgts_caso_d_guia_com_cliente_client_level():
    texto = 'Guia do FGTS Digital -- Total FGTS\nCNPJ: 11.222.333/0001-44\nCompetência: 07/2026'
    ctx = _contexto(paginas=(texto,), fonte_cliente_direto=_FonteClienteDiretoFake({'11.222.333/0001-44': _CLIENTE_A}))
    sink = InventarioPrestacaoEmMemoria()
    resultados = executar_documento_readonly(ctx, sink)
    resultado = resultados[0]
    assert resultado.resultado_corredor.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    assert len(resultado.itens_inventario) == 1
    assert resultado.itens_inventario[0].cliente == _CLIENTE_A


def test_fgts_caso_e_sem_cliente_nunca_avanca():
    texto = 'Guia do FGTS Digital -- Total FGTS\nsem CNPJ\nCompetência: 07/2026'
    ctx = _contexto(paginas=(texto,), fonte_cliente_direto=_FonteClienteDiretoFake({}))
    sink = InventarioPrestacaoEmMemoria()
    resultados = executar_documento_readonly(ctx, sink)
    assert resultados[0].resultado_corredor.estado != EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU


def test_fgts_caso_f_nunca_broadcast_mesmo_sem_fonte_cliente_direto():
    """Sem `fonte_cliente_direto` nenhuma, FGTS cai em NAO_AVALIADA --
    NUNCA em NAO_APLICAVEL (broadcast). Broadcast é reservado só a
    DCTF, nunca a FGTS (perfil_aplicabilidade_documental.py, intocado
    por esta missão)."""
    texto = 'Guia do FGTS Digital -- Total FGTS\nCompetência: 07/2026'
    ctx = _contexto(paginas=(texto,))  # nenhuma fonte_cliente_direto
    sink = InventarioPrestacaoEmMemoria()
    resultados = executar_documento_readonly(ctx, sink)
    dimensoes = {r.dimensao: r.estado for r in resultados[0].resultado_corredor.resolucao_semantica.resolucoes}
    assert dimensoes[DimensaoResolucao.CLIENTE] != EstadoResolucaoDimensao.NAO_APLICAVEL


# ============================================================================
# §28 -- DCTF E2E obrigatório
# ============================================================================

def test_dctf_broadcast_preservado_cliente_nao_obrigatorio():
    texto = 'Guia de Recolhimento DCTFWeb\nCompetência: 07/2026'
    ctx = _contexto(paginas=(texto,), clientes_broadcast=(_CLIENTE_A, _CLIENTE_B))
    sink = InventarioPrestacaoEmMemoria()
    resultados = executar_documento_readonly(ctx, sink)
    resultado = resultados[0]
    assert resultado.resultado_corredor.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    dimensoes = {r.dimensao: r.estado for r in resultado.resultado_corredor.resolucao_semantica.resolucoes}
    assert dimensoes[DimensaoResolucao.CLIENTE] == EstadoResolucaoDimensao.NAO_APLICAVEL
    # Broadcast real -- 1 item por cliente na lista injetada.
    assert len(resultado.itens_inventario) == 2
    assert {item.cliente for item in resultado.itens_inventario} == {_CLIENTE_A, _CLIENTE_B}


# ============================================================================
# §29 -- Relação documental E2E (correlação transitória)
# ============================================================================

def test_relacao_documental_correlacao_transitoria_comprova():
    """Relatório de Benefícios processado primeiro (dados_correlacao
    extraídos e registrados na fonte transitória, injetada por quem
    compõe -- este módulo nunca decide se registra, só devolve o
    extraído quando pedido); Comprovante processado depois encontra o
    candidato e resolve COMPROVA."""
    dados_correlacao_transitoria = FonteDadosCorrelacaoEmMemoria()
    item_relatorio = ItemInventarioPrestacao(
        documento_id='rel-1', tipo_documental='Relatório de Benefícios',
        cliente=_CLIENTE_A, competencia=_COMPETENCIA_0726,
    )

    class _FonteInventarioFake:
        def listar(self, cliente, competencia):
            return (item_relatorio,) if cliente == _CLIENTE_A and competencia == _COMPETENCIA_0726 else ()

    fonte_candidatos = FonteCandidatosRelacaoDocumentalDoInventario(
        fonte_escopo_clientes=EscopoClientesFixo(_COMPETENCIA_0726, (_CLIENTE_A,)),
        fonte_inventario=_FonteInventarioFake(),
        fonte_dados_correlacao=dados_correlacao_transitoria,
    )
    sink = InventarioPrestacaoEmMemoria()

    # Relatório de Benefícios é granularidade COLABORADOR (perfil_
    # aplicabilidade_documental.py: `_perfil_granularidade_colaborador`)
    # -- cliente vem do vínculo do colaborador, nunca de cliente_direto.
    texto_relatorio = (
        'Relatório de Benefícios\nCPF: 111.222.333-44\nCompetência: 07/2026\nVale-Refeição   R$ 450,00\n'
        'Vale-Alimentação   R$ 450,00\nPedido: PED-77\nValor Total: R$ 900,00'
    )
    ctx_relatorio = _contexto(
        documento_id='rel-1', paginas=(texto_relatorio,),
        candidatos_colaborador=[_candidato('func-1', '11122233344', 'COLAB 1')],
        fonte_vinculos=_FonteVinculosFake(_CLIENTE_A),
        registrar_dados_correlacao=True,
    )
    resultado_relatorio = executar_documento_readonly(ctx_relatorio, sink)[0]
    assert resultado_relatorio.dados_correlacao_extraidos is not None
    dados_correlacao_transitoria.registrar('rel-1', resultado_relatorio.dados_correlacao_extraidos)

    # Comprovante VR/VA é granularidade COLABORADOR (perfil_aplicabilidade_
    # documental.py: `_perfil_granularidade_colaborador`) -- cliente vem
    # do vínculo do colaborador, nunca de cliente_direto.
    texto_comprovante = (
        'Comprovante de transferência -- pagamento de vale-refeição\n'
        'CPF: 111.222.333-44\nCompetência: 07/2026\nPedido: PED-77\nValor Total: R$ 900,00'
    )
    ctx_comprovante = _contexto(
        documento_id='comp-1', paginas=(texto_comprovante,),
        candidatos_colaborador=[_candidato('func-1', '11122233344', 'COLAB 1')],
        fonte_vinculos=_FonteVinculosFake(_CLIENTE_A),
        fonte_candidatos_relacao=fonte_candidatos,
    )
    resultado_comprovante = executar_documento_readonly(ctx_comprovante, sink)[0]
    assert resultado_comprovante.resolucao_relacao is not None
    resolucao_relacao = resultado_comprovante.resolucao_relacao.resolucao_relacao
    assert resolucao_relacao is not None
    assert resolucao_relacao.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resolucao_relacao.documento_a_id == 'rel-1'


def test_relacao_documental_restart_da_fonte_dado_nao_existe():
    """Reinstanciar `FonteDadosCorrelacaoEmMemoria` (equivalente a
    reiniciar o processo) apaga o cache -- limitação documentada, nunca
    chamada de persistência."""
    fonte_nova = FonteDadosCorrelacaoEmMemoria()
    assert fonte_nova.obter_dados_correlacao('rel-1') is None


# ============================================================================
# §30 -- SKY E2E
# ============================================================================

def test_sky_base_julho_competencia_esperada_junho_unidade_posto_nao_encontrada():
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 06/2026\nCPF: 111.222.333-44'
    ctx = _contexto(
        paginas=(texto,), ciclo=ContextoCicloPrestacao((2026, 7)),
        cliente_do_ciclo=REFERENCIA_CLIENTE_SKY_TATUI,
        politica_competencia=POLITICA_COMPETENCIA_PRESTACAO_V1,
        candidatos_colaborador=[_candidato('func-1', '11122233344', 'JOAO')],
        fonte_vinculos=_FonteVinculosFake(REFERENCIA_CLIENTE_SKY_TATUI),
        fonte_unidade_posto=_FonteUnidadePostoSempreNaoEncontradaFake(),
    )
    sink = InventarioPrestacaoEmMemoria()
    resultado = executar_documento_readonly(ctx, sink)[0].resultado_corredor
    dimensoes = {r.dimensao: r.estado for r in resultado.resolucao_semantica.resolucoes}
    # Competência esperada Junho (Julho - 1, regra SKY) bate com a
    # observada no texto -- nunca a competência base (Julho) usada
    # crua, nunca override manual algum.
    assert dimensoes[DimensaoResolucao.COMPETENCIA] == EstadoResolucaoDimensao.RESOLVIDA
    assert dimensoes[DimensaoResolucao.UNIDADE_POSTO] == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_sky_sem_cliente_do_ciclo_usa_competencia_base_sem_deslocamento():
    """Sem `cliente_do_ciclo` informado, nenhum deslocamento é aplicado
    -- competência esperada é a base crua do ciclo, nunca a regra SKY
    aplicada por engano a um documento de outro cliente."""
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 07/2026\nCPF: 111.222.333-44'
    ctx = _contexto(paginas=(texto,), ciclo=ContextoCicloPrestacao((2026, 7)))
    sink = InventarioPrestacaoEmMemoria()
    resultado = executar_documento_readonly(ctx, sink)[0].resultado_corredor
    dimensoes = {r.dimensao: r.estado for r in resultado.resolucao_semantica.resolucoes}
    assert dimensoes[DimensaoResolucao.COMPETENCIA] == EstadoResolucaoDimensao.RESOLVIDA


# ============================================================================
# §17/§18 -- readiness/pacote (achado da revisão adversarial, §33)
# ============================================================================

def test_pacote_montado_quando_fontes_informadas_e_cliente_singular():
    texto = 'Extrato Mensal\nCNPJ: 11.222.333/0001-44\nCompetência: 07/2026'
    politica = PoliticaRequisitosPrestacao(
        version='v1', requisitos_base=(RequisitoDocumentalPrestacao('Extrato da Folha de Pagamento'),),
    )
    sink = InventarioPrestacaoEmMemoria()
    ctx = _contexto(
        paginas=(texto,), fonte_cliente_direto=_FonteClienteDiretoFake({'11.222.333/0001-44': _CLIENTE_A}),
        fonte_inventario_pacote=sink, politica_requisitos=politica,
    )
    resultado = executar_documento_readonly(ctx, sink)[0]
    assert resultado.pacote is not None
    assert resultado.pacote.cliente == _CLIENTE_A
    assert resultado.pacote.estado == EstadoPacotePrestacao.PRONTO


def test_pacote_nunca_montado_sem_as_2_fontes():
    texto = 'Extrato Mensal\nCNPJ: 11.222.333/0001-44\nCompetência: 07/2026'
    ctx = _contexto(paginas=(texto,), fonte_cliente_direto=_FonteClienteDiretoFake({'11.222.333/0001-44': _CLIENTE_A}))
    sink = InventarioPrestacaoEmMemoria()
    resultado = executar_documento_readonly(ctx, sink)[0]
    assert resultado.pacote is None


def test_pacote_nunca_montado_para_broadcast_dctf():
    """DCTF resolve para N clientes (broadcast) -- nunca fabrica um
    pacote de "1 cliente representativo" para esse caso."""
    texto = 'Guia de Recolhimento DCTFWeb\nCompetência: 07/2026'
    politica = PoliticaRequisitosPrestacao(version='v1', requisitos_base=())
    sink = InventarioPrestacaoEmMemoria()
    ctx = _contexto(
        paginas=(texto,), clientes_broadcast=(_CLIENTE_A, _CLIENTE_B),
        fonte_inventario_pacote=sink, politica_requisitos=politica,
    )
    resultado = executar_documento_readonly(ctx, sink)[0]
    assert resultado.pacote is None


# ============================================================================
# §31 -- Idempotência
# ============================================================================

def test_idempotencia_reprocessar_mesmo_documento_nao_duplica_inventario():
    texto = 'Extrato Mensal\nCNPJ: 11.222.333/0001-44\nCompetência: 07/2026'
    ctx = _contexto(paginas=(texto,), fonte_cliente_direto=_FonteClienteDiretoFake({'11.222.333/0001-44': _CLIENTE_A}))
    sink = InventarioPrestacaoEmMemoria()
    executar_documento_readonly(ctx, sink)
    executar_documento_readonly(ctx, sink)  # mesmo documento_id, de novo
    assert len(sink.listar(_CLIENTE_A, _COMPETENCIA_0726)) == 1
