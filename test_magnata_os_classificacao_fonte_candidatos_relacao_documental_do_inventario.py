"""Testes de `fonte_candidatos_relacao_documental_do_inventario.py`
(missão "MESCLAR PR #107 + CONSTRUIR OS DOIS ADAPTERS REAIS QUE
BLOQUEIAM A PRIMEIRA VALIDAÇÃO LIVE")."""
from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.fonte_candidatos_relacao_documental_do_inventario import (
    FonteCandidatosRelacaoDocumentalDoInventario,
    FonteDadosCorrelacaoEmMemoria,
)
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.classificacao.relacao_documental import DadosCorrelacaoDocumental, TipoRelacaoDocumental

_COMPETENCIA = (2026, 6)
_COMPETENCIA_REF = ReferenciaCanonica('COMPETENCIA', '2026-06')
_CLI_A = ReferenciaCanonica('CLIENTE', 'cli-a')
_CLI_B = ReferenciaCanonica('CLIENTE', 'cli-b')


class _FonteClientesFake:
    def __init__(self, clientes):
        self._clientes = clientes

    def listar_ativos(self, contexto):
        return self._clientes


class _FonteInventarioFake:
    def __init__(self, itens_por_cliente):
        self._itens_por_cliente = itens_por_cliente

    def listar(self, cliente, competencia):
        return tuple(item for item in self._itens_por_cliente.get(cliente, ()) if item.competencia == competencia)


def _fonte(clientes, itens_por_cliente, dados_correlacao=None):
    fonte_dados = dados_correlacao if dados_correlacao is not None else FonteDadosCorrelacaoEmMemoria()
    return FonteCandidatosRelacaoDocumentalDoInventario(
        fonte_clientes=_FonteClientesFake(clientes),
        fonte_inventario=_FonteInventarioFake(itens_por_cliente),
        fonte_dados_correlacao=fonte_dados,
        contexto_ciclo=ContextoCicloPrestacao(_COMPETENCIA),
    )


def test_descobre_candidato_do_tipo_pedido_ignora_outros_tipos():
    item_relatorio = ItemInventarioPrestacao(
        documento_id='rel-1', tipo_documental='Relatório de Benefícios', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    item_holerite = ItemInventarioPrestacao(
        documento_id='hol-1', tipo_documental='Holerite', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    fonte = _fonte((_CLI_A,), {_CLI_A: (item_relatorio, item_holerite)})
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios', _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert len(candidatos) == 1
    assert candidatos[0].documento_id == 'rel-1'
    assert candidatos[0].referencias_logicas == (_CLI_A,)


def test_nunca_devolve_o_proprio_documento_atual_como_candidato():
    item = ItemInventarioPrestacao(
        documento_id='comp-1', tipo_documental='Comprovante de Pagamento - VR/VA', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    fonte = _fonte((_CLI_A,), {_CLI_A: (item,)})
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Comprovante de Pagamento - VR/VA', _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert candidatos == ()


def test_mesmo_documento_em_2_clientes_une_referencias_nunca_duplica_candidato():
    item_a = ItemInventarioPrestacao(
        documento_id='rel-multi', tipo_documental='Relatório de Benefícios', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    item_b = ItemInventarioPrestacao(
        documento_id='rel-multi', tipo_documental='Relatório de Benefícios', cliente=_CLI_B, competencia=_COMPETENCIA_REF,
    )
    fonte = _fonte((_CLI_A, _CLI_B), {_CLI_A: (item_a,), _CLI_B: (item_b,)})
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios', _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert len(candidatos) == 1
    assert set(candidatos[0].referencias_logicas) == {_CLI_A, _CLI_B}


def test_dados_correlacao_vem_da_fonte_injetada_quando_disponivel():
    item = ItemInventarioPrestacao(
        documento_id='rel-1', tipo_documental='Relatório de Benefícios', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    dados_correlacao = FonteDadosCorrelacaoEmMemoria()
    dados_correlacao.registrar('rel-1', DadosCorrelacaoDocumental(identificador_pedido='PED-1', valor_total='900,00'))
    fonte = _fonte((_CLI_A,), {_CLI_A: (item,)}, dados_correlacao=dados_correlacao)
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios', _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert candidatos[0].dados_correlacao.identificador_pedido == 'PED-1'


def test_dados_correlacao_ausente_nunca_inventa_fica_com_defaults_vazios():
    """Pendência honesta (docstring do módulo): sem `FonteDadosCorrelacao
    Documental` real, o candidato existe (identidade é real) mas
    `dados_correlacao` fica vazio -- nunca fabricado."""
    item = ItemInventarioPrestacao(
        documento_id='rel-1', tipo_documental='Relatório de Benefícios', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    fonte = _fonte((_CLI_A,), {_CLI_A: (item,)})
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios', _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert candidatos[0].dados_correlacao == DadosCorrelacaoDocumental()


def test_nenhum_cliente_ativo_devolve_vazio():
    fonte = _fonte((), {})
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios', _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert candidatos == ()


def test_integra_com_o_corredor_de_relacao_sem_nenhuma_alteracao():
    """Prova de integração real: o adapter conecta direto em
    `corredor_relacao_documental.resolver_relacao_e_avancar` (o mesmo
    orquestrador já usado com fakes de teste) sem nenhum ajuste --
    fecha a pendência "adapters reais" registrada no PR #107."""
    from magnata_os.classificacao.corredor_relacao_documental import (
        ContextoRelacaoDocumentoPrestacao,
        resolver_relacao_e_avancar,
    )
    from magnata_os.classificacao.inventario_prestacao_memoria import InventarioPrestacaoEmMemoria

    item = ItemInventarioPrestacao(
        documento_id='rel-real-1', tipo_documental='Relatório de Benefícios', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    dados_correlacao = FonteDadosCorrelacaoEmMemoria()
    dados_correlacao.registrar('rel-real-1', DadosCorrelacaoDocumental(identificador_pedido='PED-77', valor_total='900,00', competencia=_COMPETENCIA))
    fonte_candidatos = _fonte((_CLI_A,), {_CLI_A: (item,)}, dados_correlacao=dados_correlacao)

    contexto = ContextoRelacaoDocumentoPrestacao(
        documento_id='comp-real-1', tipo_documental='Comprovante de Pagamento - VR/VA', competencia=_COMPETENCIA,
        dados_correlacao=DadosCorrelacaoDocumental(identificador_pedido='PED-77', valor_total='900,00', competencia=_COMPETENCIA),
        fonte_candidatos=fonte_candidatos,
    )
    resultado = resolver_relacao_e_avancar(contexto, InventarioPrestacaoEmMemoria())
    assert resultado.resolucao_relacao.estado.value == 'RESOLVIDA'
    assert resultado.resolucao_relacao.documento_a_id == 'rel-real-1'


def test_ordem_deterministica_por_documento_id():
    item_z = ItemInventarioPrestacao(
        documento_id='rel-z', tipo_documental='Relatório de Benefícios', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    item_a = ItemInventarioPrestacao(
        documento_id='rel-a', tipo_documental='Relatório de Benefícios', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    fonte = _fonte((_CLI_A,), {_CLI_A: (item_z, item_a)})
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios', _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert [c.documento_id for c in candidatos] == ['rel-a', 'rel-z']
