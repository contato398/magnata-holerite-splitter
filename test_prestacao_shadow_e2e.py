from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    ConfiancaResolucao,
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    EstadoResultadoSemantico,
    NivelConfianca,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    RegraAplicabilidadeDimensao,
    ResolucaoDimensao,
    ResultadoResolucaoSemantico,
)
from magnata_os.classificacao.inventario_prestacao_resultados import (
    FonteInventarioPrestacaoResultadosShadow,
)
from magnata_os.classificacao.politica_requisitos_prestacao import (
    OverrideRequisitosPrestacao,
    PoliticaRequisitosPrestacao,
)
from magnata_os.classificacao.prestacao_readiness import (
    EstadoPrestacaoReadiness,
    ItemInventarioPrestacao,
    RequisitoDocumentalPrestacao,
)
from magnata_os.classificacao.prestacao_shadow import avaliar_prestacao_shadow
from magnata_os.classificacao.vinculos_prestacao import FonteVinculosPrestacao
from magnata_os.documental.importacao_lote.contratos import (
    ClassificacaoCorrespondencia,
    MotivoSanitizado,
    ResultadoCompetencia,
    ResultadoItem,
    TipoDocumental,
)


CLIENTE = ReferenciaCanonica("CLIENTE", "cliente-shadow")
COMPETENCIA = ReferenciaCanonica("COMPETENCIA", "2026-07")
TIPOS_BASE = (
    "DCTFWeb - Declaração",
    "DCTFWeb - Recibo de Entrega",
    "Guia DCTFWeb/DARF",
    "FGTS",
    "extrato_cliente",
)


class FonteFake:
    def __init__(self, itens):
        self.itens = itens
        self.chamadas = []

    def listar(self, cliente, competencia):
        self.chamadas.append((cliente, competencia))
        return self.itens


class FonteVinculosPrestacaoFake:
    """Implementação fake de FonteVinculosPrestacao para testes."""

    def __init__(self, resolucao: ResolucaoDimensao):
        self._resolucao = resolucao
        self.chamadas = []

    def resolver_clientes(
        self,
        origem: ReferenciaCanonica,
        competencia: ReferenciaCanonica,
    ) -> ResolucaoDimensao:
        self.chamadas.append((origem, competencia))
        return self._resolucao


def _resolucao():
    regras = tuple(
        RegraAplicabilidadeDimensao(
            dimensao=dimensao,
            aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA,
            cardinalidade=Cardinalidade(1, 1),
        )
        for dimensao in (
            DimensaoResolucao.CLIENTE,
            DimensaoResolucao.COMPETENCIA,
        )
    )
    perfil = PerfilAplicabilidadeResolucao(
        perfil_id="prestacao-shadow",
        version="1",
        escopo_documental="prestacao-contas",
        regras=regras,
    )
    resolucoes = tuple(
        ResolucaoDimensao(
            dimensao=dimensao,
            estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(referencia,),
            confianca=ConfiancaResolucao(NivelConfianca.FORTE),
        )
        for dimensao, referencia in (
            (DimensaoResolucao.CLIENTE, CLIENTE),
            (DimensaoResolucao.COMPETENCIA, COMPETENCIA),
        )
    )
    return ResultadoResolucaoSemantico(
        documento_id="inventario-prestacao-shadow",
        resolver_id="resolver-shadow",
        resolver_version="1",
        politica_id="prestacao-readiness",
        politica_version="1",
        perfil=perfil,
        resolucoes=resolucoes,
        estado_consolidado=EstadoResultadoSemantico.RESOLVIDA,
        necessita_revisao_humana=False,
    )


def _inventario_base():
    return tuple(
        ItemInventarioPrestacao(
            documento_id=f"doc-{indice}",
            tipo_documental=tipo,
            cliente=CLIENTE,
            competencia=COMPETENCIA,
        )
        for indice, tipo in enumerate(TIPOS_BASE, start=1)
    )


def _resultados_base_e2e():
    """Cria ResultadoItem para os 5 tipos base (EXTRATO_CLIENTE e documentos fiscais).

    Cada um é classificado como EXACT, com cliente resolvido como CLIENTE,
    competência confirmada como COMPETENCIA (2026-07).
    """
    return tuple(
        ResultadoItem(
            manifesto_item_id=f"fiscal:00{indice}",
            tipo_documental=TipoDocumental.EXTRATO_CLIENTE,
            classificacao=ClassificacaoCorrespondencia.EXACT,
            pronto_para_gravacao=True,
            entidade_resolvida=CLIENTE.entidade_id,
            identidade_documental=f"doc-fiscal-{indice}",
            identidade_documental_truncada=f"doc-fiscal-{indice}",
            motivo=MotivoSanitizado.OK,
            resultado_competencia=ResultadoCompetencia.CONFIRMADA,
            competencia_ano_mes_extraido=(2026, 7),
            competencia_estrategia="extracao-shadow",
        )
        for indice in range(1, 6)
    )


def test_composicao_com_cinco_tipos_resulta_pronto_sem_efeitos():
    fonte = FonteFake(_inventario_base())
    resultado = avaliar_prestacao_shadow(
        CLIENTE,
        COMPETENCIA,
        _resolucao(),
        fonte,
        PoliticaRequisitosPrestacao(version="1"),
    )

    assert resultado.estado == EstadoPrestacaoReadiness.PRONTO
    assert fonte.chamadas == [(CLIENTE, COMPETENCIA)]


def test_override_exato_adiciona_requisito_ausente():
    politica = PoliticaRequisitosPrestacao(
        version="1",
        overrides=(
            OverrideRequisitosPrestacao(
                cliente=CLIENTE,
                competencia=COMPETENCIA,
                requisitos_adicionais=(
                    RequisitoDocumentalPrestacao("HOLERITE"),
                ),
            ),
        ),
    )
    resultado = avaliar_prestacao_shadow(
        CLIENTE,
        COMPETENCIA,
        _resolucao(),
        FonteFake(_inventario_base()),
        politica,
    )

    assert resultado.estado == EstadoPrestacaoReadiness.FALTANDO
    assert resultado.tipos_faltantes == ("HOLERITE",)


def test_e2e_holerite_com_vinculo_unico_resulta_pronto():
    """Cenário positivo do fluxo E2E:
    HOLERITE → FUNCIONARIO → vínculo → CLIENTE → inventário → readiness PRONTO
    """
    # Criar resultado de HOLERITE classificado como EXACT
    funcionario = ReferenciaCanonica("FUNCIONARIO", "funcionario-shadow-001")
    resultado_holerite = ResultadoItem(
        manifesto_item_id="holerite:001",
        tipo_documental=TipoDocumental.HOLERITE,
        classificacao=ClassificacaoCorrespondencia.EXACT,
        pronto_para_gravacao=True,
        entidade_resolvida=funcionario.entidade_id,
        identidade_documental="doc-holerite-shadow-001",
        identidade_documental_truncada="doc-holerite-shadow-001",
        motivo=MotivoSanitizado.OK,
        resultado_competencia=ResultadoCompetencia.CONFIRMADA,
        competencia_ano_mes_extraido=(2026, 7),
        competencia_estrategia="extracao-shadow",
    )

    # Fonte de vínculos que resolve FUNCIONARIO → CLIENTE (exatamente 1)
    resolucao_vinculos_sucesso = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE,
        estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(CLIENTE,),
        confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )
    fonte_vinculos = FonteVinculosPrestacaoFake(resolucao_vinculos_sucesso)

    # Inventário que enriquece HOLERITE com vínculo
    # (FonteInventarioPrestacaoResultadosShadow só converte HOLERITE e EXTRATO_CLIENTE)
    fonte_inventario_shadow = FonteInventarioPrestacaoResultadosShadow(
        resultados=(resultado_holerite,),
        fonte_vinculos=fonte_vinculos,
    )

    # Combinar: 5 tipos base + HOLERITE enriquecido
    # Criamos uma fonte composta que retorna ambos
    class FonteInventarioCompostoFake:
        def listar(self, cliente, competencia):
            base = _inventario_base() if cliente == CLIENTE and competencia == COMPETENCIA else ()
            holerite = fonte_inventario_shadow.listar(cliente, competencia)
            return base + holerite

    fonte_inventario = FonteInventarioCompostoFake()

    # Política que exige holerite como adicional
    # (usar lowercase, conforme TipoDocumental.HOLERITE.value)
    politica = PoliticaRequisitosPrestacao(
        version="1",
        overrides=(
            OverrideRequisitosPrestacao(
                cliente=CLIENTE,
                competencia=COMPETENCIA,
                requisitos_adicionais=(
                    RequisitoDocumentalPrestacao("holerite"),
                ),
            ),
        ),
    )

    # Avaliar readiness shadow
    resultado = avaliar_prestacao_shadow(
        CLIENTE,
        COMPETENCIA,
        _resolucao(),
        fonte_inventario,
        politica,
    )

    # Esperado: PRONTO porque todos os requisitos foram encontrados:
    # - 5 tipos base via _inventario_base()
    # - HOLERITE enriquecido com vínculo
    assert resultado.estado == EstadoPrestacaoReadiness.PRONTO
    assert resultado.tipos_faltantes == ()
    assert fonte_vinculos.chamadas == [(funcionario, COMPETENCIA)]


def test_e2e_holerite_com_vinculo_ambiguo_resulta_faltando():
    """Cenário ambíguo do fluxo E2E:
    HOLERITE → FUNCIONARIO → vínculo (AMBIGUO) → não entra no inventário
    → readiness FALTANDO HOLERITE
    """
    # Mesmo HOLERITE classificado como EXACT
    funcionario = ReferenciaCanonica("FUNCIONARIO", "funcionario-shadow-002")
    resultado_holerite = ResultadoItem(
        manifesto_item_id="holerite:002",
        tipo_documental=TipoDocumental.HOLERITE,
        classificacao=ClassificacaoCorrespondencia.EXACT,
        pronto_para_gravacao=True,
        entidade_resolvida=funcionario.entidade_id,
        identidade_documental="doc-holerite-shadow-002",
        identidade_documental_truncada="doc-holerite-shadow-002",
        motivo=MotivoSanitizado.OK,
        resultado_competencia=ResultadoCompetencia.CONFIRMADA,
        competencia_ano_mes_extraido=(2026, 7),
        competencia_estrategia="extracao-shadow",
    )

    # Fonte de vínculos que retorna AMBIGUA (dois clientes possíveis)
    cliente_alt = ReferenciaCanonica("CLIENTE", "cliente-shadow-alternativo")
    resolucao_vinculos_ambigua = ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE,
        estado=EstadoResolucaoDimensao.AMBIGUA,
        valores_confirmados=(),
        candidatos=(CLIENTE, cliente_alt),
        confianca=ConfiancaResolucao(NivelConfianca.FRACA),
    )
    fonte_vinculos = FonteVinculosPrestacaoFake(resolucao_vinculos_ambigua)

    # Inventário que tenta enriquecimento (mas falha por ambiguidade)
    fonte_inventario_shadow = FonteInventarioPrestacaoResultadosShadow(
        resultados=(resultado_holerite,),
        fonte_vinculos=fonte_vinculos,
    )

    # Combinar: 5 tipos base + nenhum HOLERITE (por ambiguidade)
    class FonteInventarioCompostoFake:
        def listar(self, cliente, competencia):
            base = _inventario_base() if cliente == CLIENTE and competencia == COMPETENCIA else ()
            holerite = fonte_inventario_shadow.listar(cliente, competencia)
            return base + holerite

    fonte_inventario = FonteInventarioCompostoFake()

    # Política que exige holerite como adicional
    politica = PoliticaRequisitosPrestacao(
        version="1",
        overrides=(
            OverrideRequisitosPrestacao(
                cliente=CLIENTE,
                competencia=COMPETENCIA,
                requisitos_adicionais=(
                    RequisitoDocumentalPrestacao("holerite"),
                ),
            ),
        ),
    )

    # Avaliar readiness shadow
    resultado = avaliar_prestacao_shadow(
        CLIENTE,
        COMPETENCIA,
        _resolucao(),
        fonte_inventario,
        politica,
    )

    # Esperado: FALTANDO porque vínculo é ambíguo
    # → _converter_resultado retorna None para HOLERITE
    # → HOLERITE não entra no inventário
    # → readiness mostra HOLERITE faltante
    assert resultado.estado == EstadoPrestacaoReadiness.FALTANDO
    assert resultado.tipos_faltantes == ("holerite",)
    assert fonte_vinculos.chamadas == [(funcionario, COMPETENCIA)]
