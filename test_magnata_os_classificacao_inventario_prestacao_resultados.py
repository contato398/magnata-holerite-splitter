from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.inventario_prestacao import FonteInventarioPrestacao
from magnata_os.classificacao.inventario_prestacao_resultados import (
    FonteInventarioPrestacaoResultadosShadow,
)
from magnata_os.documental.importacao_lote.contratos import (
    ClassificacaoCorrespondencia,
    MotivoSanitizado,
    ResultadoCompetencia,
    ResultadoItem,
    TipoDocumental,
)


CLIENTE = ReferenciaCanonica("CLIENTE", "recCLIENTE")
COMPETENCIA = ReferenciaCanonica("COMPETENCIA", "2026-07")


def _resultado(
    identidade="a" * 64,
    classificacao=ClassificacaoCorrespondencia.EXACT,
    cliente_id="recCLIENTE",
    resultado_competencia=ResultadoCompetencia.CONFIRMADA,
    competencia=(2026, 7),
):
    return ResultadoItem(
        manifesto_item_id="item-1",
        tipo_documental=TipoDocumental.EXTRATO_CLIENTE,
        classificacao=classificacao,
        pronto_para_gravacao=True,
        entidade_resolvida=cliente_id,
        identidade_documental=identidade,
        identidade_documental_truncada=identidade[:12] if identidade else None,
        motivo=MotivoSanitizado.OK,
        criterio_usado="cnpj_exato",
        resultado_competencia=resultado_competencia,
        competencia_ano_mes_extraido=competencia,
        competencia_estrategia="rotulo_explicito",
    )


def _listar(resultados):
    fonte: FonteInventarioPrestacao = FonteInventarioPrestacaoResultadosShadow(
        tuple(resultados)
    )
    return fonte.listar(CLIENTE, COMPETENCIA)


def test_resultado_completo_gera_um_item_neutro():
    itens = _listar((_resultado(),))
    assert len(itens) == 1
    assert itens[0].documento_id == "a" * 64
    assert itens[0].tipo_documental == "extrato_cliente"
    assert itens[0].cliente == CLIENTE
    assert itens[0].competencia == COMPETENCIA


def test_cliente_ambiguo_nao_gera_item():
    assert _listar(
        (_resultado(classificacao=ClassificacaoCorrespondencia.AMBIGUOUS, cliente_id=None),)
    ) == ()


def test_competencia_ausente_nao_gera_item():
    assert _listar((_resultado(resultado_competencia=None, competencia=None),)) == ()


def test_conflito_nao_gera_item():
    assert _listar(
        (_resultado(classificacao=ClassificacaoCorrespondencia.CONFLICT, cliente_id=None),)
    ) == ()


def test_multiplos_resultados_validos_tem_saida_deterministica():
    primeiro = _resultado("a" * 64)
    segundo = _resultado("b" * 64)
    ordem_a = _listar((segundo, primeiro))
    ordem_b = _listar((primeiro, segundo))
    assert ordem_a == ordem_b
    assert tuple(item.documento_id for item in ordem_a) == (
        "a" * 64,
        "b" * 64,
    )


def test_item_nao_recebe_pii_ou_payload_bruto():
    item = _listar((_resultado(),))[0]
    assert all(
        not hasattr(item, campo)
        for campo in (
            "cpf",
            "cnpj",
            "nome",
            "email",
            "texto_bruto",
            "conteudo",
            "payload",
        )
    )
