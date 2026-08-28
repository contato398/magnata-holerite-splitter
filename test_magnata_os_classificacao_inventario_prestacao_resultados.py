from pathlib import Path

from magnata_os.classificacao.contratos import (
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
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
    tipo_documental=TipoDocumental.EXTRATO_CLIENTE,
):
    return ResultadoItem(
        manifesto_item_id="item-1",
        tipo_documental=tipo_documental,
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


class FonteVinculosFake:
    def __init__(self, resolucao):
        self._resolucao = resolucao
        self.chamadas = []

    def resolver_clientes(self, origem, competencia):
        self.chamadas.append((origem, competencia))
        if isinstance(self._resolucao, Exception):
            raise self._resolucao
        return self._resolucao


def _resolucao(estado, confirmados=(), candidatos=()):
    return ResolucaoDimensao(
        dimensao=DimensaoResolucao.CLIENTE,
        estado=estado,
        valores_confirmados=confirmados,
        candidatos=candidatos,
    )


def _listar(resultados, fonte_vinculos=None):
    fonte: FonteInventarioPrestacao = FonteInventarioPrestacaoResultadosShadow(
        tuple(resultados), fonte_vinculos=fonte_vinculos
    )
    return fonte.listar(CLIENTE, COMPETENCIA)


def test_extrato_cliente_continua_funcionando_sem_vinculo():
    itens = _listar((_resultado(),))
    assert len(itens) == 1
    assert itens[0].documento_id == "a" * 64
    assert itens[0].tipo_documental == "extrato_cliente"
    assert itens[0].cliente == CLIENTE
    assert itens[0].competencia == COMPETENCIA


def test_resultado_de_funcionario_com_vinculo_unico_gera_item():
    vinculos = FonteVinculosFake(
        _resolucao(EstadoResolucaoDimensao.RESOLVIDA, (CLIENTE,))
    )
    itens = _listar(
        (_resultado(tipo_documental=TipoDocumental.HOLERITE),),
        vinculos,
    )
    assert len(itens) == 1
    assert itens[0].cliente == CLIENTE
    assert itens[0].tipo_documental == "holerite"
    assert vinculos.chamadas == [
        (ReferenciaCanonica("FUNCIONARIO", "recCLIENTE"), COMPETENCIA)
    ]


def test_funcionario_sem_vinculo_nao_gera_item():
    vinculos = FonteVinculosFake(
        _resolucao(EstadoResolucaoDimensao.NAO_ENCONTRADA)
    )
    assert _listar(
        (_resultado(tipo_documental=TipoDocumental.HOLERITE),), vinculos
    ) == ()


def test_vinculo_ambiguo_nao_gera_item():
    outro = ReferenciaCanonica("CLIENTE", "recOUTRO")
    vinculos = FonteVinculosFake(
        _resolucao(EstadoResolucaoDimensao.AMBIGUA, candidatos=(CLIENTE, outro))
    )
    assert _listar(
        (_resultado(tipo_documental=TipoDocumental.HOLERITE),), vinculos
    ) == ()


def test_vinculo_em_conflito_nao_gera_item():
    outro = ReferenciaCanonica("CLIENTE", "recOUTRO")
    vinculos = FonteVinculosFake(
        _resolucao(EstadoResolucaoDimensao.CONFLITO, candidatos=(CLIENTE, outro))
    )
    assert _listar(
        (_resultado(tipo_documental=TipoDocumental.HOLERITE),), vinculos
    ) == ()


def test_erro_na_fonte_de_vinculos_nao_gera_item():
    vinculos = FonteVinculosFake(RuntimeError("falha sanitizada"))
    assert _listar(
        (_resultado(tipo_documental=TipoDocumental.HOLERITE),), vinculos
    ) == ()


def test_competencia_nao_confirmada_nao_consulta_vinculos():
    vinculos = FonteVinculosFake(
        _resolucao(EstadoResolucaoDimensao.RESOLVIDA, (CLIENTE,))
    )
    assert _listar(
        (
            _resultado(
                tipo_documental=TipoDocumental.HOLERITE,
                resultado_competencia=ResultadoCompetencia.DIVERGENTE,
            ),
        ),
        vinculos,
    ) == ()
    assert vinculos.chamadas == []


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


def test_multiplos_holerites_validos_tem_saida_deterministica():
    vinculos = FonteVinculosFake(
        _resolucao(EstadoResolucaoDimensao.RESOLVIDA, (CLIENTE,))
    )
    primeiro = _resultado("a" * 64, tipo_documental=TipoDocumental.HOLERITE)
    segundo = _resultado("b" * 64, tipo_documental=TipoDocumental.HOLERITE)
    ordem_a = _listar((segundo, primeiro), vinculos)
    ordem_b = _listar((primeiro, segundo), vinculos)
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


def test_modulo_permanece_puro_e_sem_adapter_concreto():
    conteudo = Path(
        "magnata_os/classificacao/inventario_prestacao_resultados.py"
    ).read_text(encoding="utf-8").lower()
    assert "app.py" not in conteudo
    assert "airtable" not in conteudo
    assert "requests" not in conteudo
    assert "open(" not in conteudo
