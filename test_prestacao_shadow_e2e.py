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
