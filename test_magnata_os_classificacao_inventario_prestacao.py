import inspect
from typing import get_type_hints

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
from magnata_os.classificacao.inventario_prestacao import FonteInventarioPrestacao
from magnata_os.classificacao.prestacao_readiness import (
    EntradaPrestacaoReadiness,
    EstadoPrestacaoReadiness,
    ItemInventarioPrestacao,
    RequisitoDocumentalPrestacao,
    avaliar_prestacao_readiness,
)


CLIENTE = ReferenciaCanonica("CLIENTE", "cliente-1")
COMPETENCIA = ReferenciaCanonica("COMPETENCIA", "2026-07")


class FonteFake:
    def __init__(self, itens=()):
        self._itens = tuple(itens)

    def listar(self, cliente, competencia):
        return self._itens


class OutraFonteFake:
    def listar(self, cliente, competencia):
        return ()


def _consumir(fonte: FonteInventarioPrestacao):
    return fonte.listar(CLIENTE, COMPETENCIA)


def _resolucao():
    regras = tuple(
        RegraAplicabilidadeDimensao(
            dimensao=dimensao,
            aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA,
            cardinalidade=Cardinalidade(1, 1),
        )
        for dimensao in (DimensaoResolucao.CLIENTE, DimensaoResolucao.COMPETENCIA)
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
        documento_id="inventario-prestacao-1",
        resolver_id="resolver-shadow",
        resolver_version="1",
        politica_id="prestacao-readiness",
        politica_version="1",
        perfil=perfil,
        resolucoes=resolucoes,
        estado_consolidado=EstadoResultadoSemantico.RESOLVIDA,
        necessita_revisao_humana=False,
    )


def test_fake_implementa_assinatura_neutra_e_retorna_tuple():
    item = ItemInventarioPrestacao("doc-1", "FGTS", CLIENTE, COMPETENCIA)
    resultado = _consumir(FonteFake((item,)))
    assert isinstance(resultado, tuple)
    assert resultado == (item,)


def test_assinatura_da_porta_usa_somente_modelos_neutros():
    assinatura = inspect.signature(FonteInventarioPrestacao.listar)
    assert tuple(assinatura.parameters) == ("self", "cliente", "competencia")
    tipos = get_type_hints(FonteInventarioPrestacao.listar)
    assert tipos == {
        "cliente": ReferenciaCanonica,
        "competencia": ReferenciaCanonica,
        "return": tuple[ItemInventarioPrestacao, ...],
    }


def test_saida_da_porta_alimenta_readiness_diretamente():
    item = ItemInventarioPrestacao("doc-1", "FGTS", CLIENTE, COMPETENCIA)
    resultado = avaliar_prestacao_readiness(
        EntradaPrestacaoReadiness(
            cliente=CLIENTE,
            competencia=COMPETENCIA,
            requisitos=(RequisitoDocumentalPrestacao("FGTS"),),
            inventario=_consumir(FonteFake((item,))),
            resolucao=_resolucao(),
        )
    )
    assert resultado.estado == EstadoPrestacaoReadiness.PRONTO


def test_consumidor_aceita_implementacoes_substituiveis():
    assert _consumir(FonteFake()) == _consumir(OutraFonteFake()) == ()


def test_contrato_nao_expoe_origem_pii_ou_conteudo_bruto():
    texto = inspect.getsource(FonteInventarioPrestacao).lower()
    proibidos = (
        "airtable",
        "gmail",
        "filesystem",
        "http",
        "url",
        "anexo",
        "cpf",
        "cnpj",
        "email",
        "texto_bruto",
        "conteudo",
    )
    assert all(nome not in texto for nome in proibidos)
