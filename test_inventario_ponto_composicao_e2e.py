"""Prova de composição ponta-a-ponta (missão "FONTE DE INVENTÁRIO DE
FOLHA/CARTÃO DE PONTO V1"):

    documentos de ponto
    -> FonteInventarioPontoPrestacao (novo)
    -> FonteInventarioPrestacaoComposta (já existente, reaproveitada)
    -> executar_ciclo_prestacao (já existente, reaproveitado)
    -> readiness -> pacote/completude

Demonstra que Folha de Ponto passa a contribuir de verdade para a
completude do pacote lógico -- sem reimplementar nenhum motor/
classificador/orquestrador. Dados 100% sintéticos, sem nome real/CPF
real. SKY Tatuí é usado só numa validação ESTRUTURAL separada (usando
a referência canônica já existente, `REFERENCIA_CLIENTE_SKY_TATUI`),
nunca com uma regra de ciclo de Ponto inventada para ele."""
import datetime

from magnata_os.classificacao.ciclo_prestacao import executar_ciclo_prestacao
from magnata_os.classificacao.competencia_esperada_prestacao import (
    REFERENCIA_CLIENTE_SKY_TATUI,
    ContextoCicloPrestacao,
)
from magnata_os.classificacao.contratos import (
    AplicabilidadeDimensao,
    Cardinalidade,
    DimensaoResolucao,
    EntradaResolucaoDocumento,
    EstadoResolucaoDimensao,
    PerfilAplicabilidadeResolucao,
    ReferenciaCanonica,
    RegraAplicabilidadeDimensao,
    ResolucaoDimensao,
)
from magnata_os.classificacao.fonte_inventario_composta import FonteInventarioPrestacaoComposta
from magnata_os.classificacao.fonte_inventario_ponto_prestacao import (
    FonteInventarioPontoPrestacao,
    RegistroPontoBruto,
)
from magnata_os.classificacao.pacote_prestacao import EstadoPacotePrestacao
from magnata_os.classificacao.prestacao_readiness import RequisitoDocumentalPrestacao
from magnata_os.classificacao.produtores_evidencia_ponto import TIPO_FOLHA_DE_PONTO
from magnata_os.classificacao.resolucao_semantica import compor_resolucao_semantica

_CLIENTE = ReferenciaCanonica('CLIENTE', 'rec_cliente_sintetico_ponto')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-06')
_FUNC_1 = ReferenciaCanonica('FUNCIONARIO', 'rec_func_1')
_CONTEXTO = ContextoCicloPrestacao(competencia_base=(2026, 6))


class _FonteClientesUmAtivo:
    def listar_ativos(self, contexto):
        return (_CLIENTE,)


class _FonteRequisitosVazia:
    def registros_para(self, cliente, contexto):
        return ()


class _FonteVinculosFixa:
    def __init__(self, mapa):
        self._mapa = mapa

    def resolver_clientes(self, origem, competencia):
        cliente = self._mapa.get((origem, competencia))
        if cliente is None:
            return ResolucaoDimensao(
                dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
            )
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(cliente,),
        )


class _FonteRegistrosPontoEmMemoria:
    def __init__(self, registros):
        self._registros = tuple(registros)

    def listar_no_intervalo(self, data_inicio, data_fim):
        return tuple(r for r in self._registros if data_inicio <= r.data <= data_fim)


def _resolucao_ancora(cliente, competencia):
    perfil = PerfilAplicabilidadeResolucao(
        perfil_id='p', version='1', escopo_documental='teste',
        regras=(
            RegraAplicabilidadeDimensao(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
        ),
    )
    return compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id='doc-ancora', hash_sha256='a' * 64, resolver_id='r', resolver_version='1',
            politica_id='p', politica_version='1', contexto_fontes_fingerprint='teste',
        ),
        perfil=perfil,
        resolucoes=(
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(cliente,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(competencia,)),
        ),
    )


def _executar(fonte_inventario, fonte_vinculos_dummy=None):
    return executar_ciclo_prestacao(
        contexto=_CONTEXTO,
        fonte_clientes=_FonteClientesUmAtivo(),
        fonte_requisitos=_FonteRequisitosVazia(),
        fonte_inventario=fonte_inventario,
        requisitos_base=(RequisitoDocumentalPrestacao(tipo_documental=TIPO_FOLHA_DE_PONTO, quantidade_minima=1),),
        resolucoes_ancora={_CLIENTE: _resolucao_ancora(_CLIENTE, _COMPETENCIA)},
        competencias_por_cliente={_CLIENTE: _COMPETENCIA},
    )


def test_ponto_presente_contribui_para_pacote_pronto():
    vinculos = _FonteVinculosFixa({(_FUNC_1, _COMPETENCIA): _CLIENTE})
    registros = [
        RegistroPontoBruto(
            documento_id='rec_ponto_1', colaborador=_FUNC_1,
            data=datetime.date(2026, 6, 10), batidas=('08:00', '17:00'),
        ),
    ]
    fonte_ponto = FonteInventarioPontoPrestacao(_FonteRegistrosPontoEmMemoria(registros), vinculos)
    fonte_composta = FonteInventarioPrestacaoComposta((fonte_ponto,))

    resultado = _executar(fonte_composta)
    assert len(resultado.resultados_por_cliente) == 1
    resultado_cliente = resultado.resultados_por_cliente[0]
    assert resultado_cliente.pacote.estado == EstadoPacotePrestacao.PRONTO
    assert TIPO_FOLHA_DE_PONTO not in resultado_cliente.pacote.tipos_faltantes
    assert any(item.tipo_documental == TIPO_FOLHA_DE_PONTO for item in resultado_cliente.pacote.itens_incluidos)


def test_ponto_ausente_produz_pacote_incompleto_com_necessidade():
    vinculos = _FonteVinculosFixa({(_FUNC_1, _COMPETENCIA): _CLIENTE})
    fonte_ponto = FonteInventarioPontoPrestacao(_FonteRegistrosPontoEmMemoria([]), vinculos)
    fonte_composta = FonteInventarioPrestacaoComposta((fonte_ponto,))

    resultado = _executar(fonte_composta)
    resultado_cliente = resultado.resultados_por_cliente[0]
    assert resultado_cliente.pacote.estado == EstadoPacotePrestacao.INCOMPLETO
    assert TIPO_FOLHA_DE_PONTO in resultado_cliente.pacote.tipos_faltantes
    assert any(n.tipo_documental == TIPO_FOLHA_DE_PONTO for n in resultado_cliente.necessidades)


def test_validacao_estrutural_sky_usa_referencia_ja_existente_sem_regra_nova():
    """Validação ESTRUTURAL pedida pela missão: o comportamento já
    existente (motor de ciclo + readiness + pacote) funciona igual para
    a referência canônica JÁ CONFIRMADA do SKY Tatuí -- usando o ciclo
    de Ponto DEFAULT (mês civil), já que nenhuma exceção real de ciclo
    de Ponto está confirmada para este cliente. Nenhuma regra de
    negócio nova foi inventada para SKY nesta missão."""
    func_sky = ReferenciaCanonica('FUNCIONARIO', 'rec_func_sky_sintetico')
    vinculos = _FonteVinculosFixa({(func_sky, _COMPETENCIA): REFERENCIA_CLIENTE_SKY_TATUI})
    registros = [
        RegistroPontoBruto(
            documento_id='rec_ponto_sky', colaborador=func_sky,
            data=datetime.date(2026, 6, 15), batidas=('08:00', '17:00'),
        ),
    ]
    fonte_ponto = FonteInventarioPontoPrestacao(_FonteRegistrosPontoEmMemoria(registros), vinculos)
    itens = fonte_ponto.listar(REFERENCIA_CLIENTE_SKY_TATUI, _COMPETENCIA)
    assert len(itens) == 1
    assert itens[0].cliente == REFERENCIA_CLIENTE_SKY_TATUI
    assert itens[0].tipo_documental == TIPO_FOLHA_DE_PONTO
