"""Testes de `fonte_candidatos_relacao_documental_do_inventario.py`
(missão "MESCLAR PR #107 + CONSTRUIR OS DOIS ADAPTERS REAIS..."；
corrigido pelo "ADENDO PRÉ-MERGE — PR #108 — ESCOPO HISTÓRICO DE
CANDIDATOS + AUSÊNCIA EXPLÍCITA DE DADOS DE CORRELAÇÃO"). Casos F-J
mapeados 1:1 ao §18 do adendo."""
from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.fonte_candidatos_relacao_documental_do_inventario import (
    EscopoClientesAtivosDoCiclo,
    EscopoClientesFixo,
    FonteCandidatosRelacaoDocumentalDoInventario,
    FonteDadosCorrelacaoEmMemoria,
)
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.classificacao.relacao_documental import DadosCorrelacaoDocumental, TipoRelacaoDocumental

_COMPETENCIA = (2026, 6)
_COMPETENCIA_REF = ReferenciaCanonica('COMPETENCIA', '2026-06')
_COMPETENCIA_HISTORICA = (2025, 1)
_COMPETENCIA_HISTORICA_REF = ReferenciaCanonica('COMPETENCIA', '2025-01')
_CLI_A = ReferenciaCanonica('CLIENTE', 'cli-a')
_CLI_B = ReferenciaCanonica('CLIENTE', 'cli-b')
_CLI_INATIVO_HOJE = ReferenciaCanonica('CLIENTE', 'cli-inativo-hoje')


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


def _fonte_com_escopo_fixo(clientes, itens_por_cliente, dados_correlacao=None):
    return FonteCandidatosRelacaoDocumentalDoInventario(
        fonte_escopo_clientes=EscopoClientesFixo(clientes),
        fonte_inventario=_FonteInventarioFake(itens_por_cliente),
        fonte_dados_correlacao=dados_correlacao,
    )


# --- Caso F: corrente ativo -> encontra ---

def test_caso_f_cliente_ativo_no_ciclo_corrente_encontra_candidato():
    item = ItemInventarioPrestacao(
        documento_id='rel-1', tipo_documental='Relatório de Benefícios', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    fonte_clientes = _FonteClientesFake((_CLI_A,))
    contexto_ciclo = ContextoCicloPrestacao(_COMPETENCIA)
    escopo = EscopoClientesAtivosDoCiclo(fonte_clientes, contexto_ciclo)
    fonte = FonteCandidatosRelacaoDocumentalDoInventario(
        fonte_escopo_clientes=escopo, fonte_inventario=_FonteInventarioFake({_CLI_A: (item,)}),
    )
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios', _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert len(candidatos) == 1
    assert candidatos[0].documento_id == 'rel-1'


def test_escopo_ativos_do_ciclo_nunca_usa_ativos_hoje_para_competencia_diferente_da_corrente():
    """`EscopoClientesAtivosDoCiclo` é documentado como válido só para
    a competência CORRENTE do ciclo -- pedir por outra competência
    devolve escopo vazio, nunca a lista de ativos hoje disfarçada de
    histórico."""
    fonte_clientes = _FonteClientesFake((_CLI_A,))
    contexto_ciclo = ContextoCicloPrestacao(_COMPETENCIA)  # corrente = 2026-06
    escopo = EscopoClientesAtivosDoCiclo(fonte_clientes, contexto_ciclo)
    assert escopo.escopo_para_competencia(_COMPETENCIA_HISTORICA_REF) == ()
    assert escopo.escopo_para_competencia(_COMPETENCIA_REF) == (_CLI_A,)


# --- Caso G: histórico de cliente hoje inativo -- não pode ser perdido ---

def test_caso_g_cliente_inativo_hoje_mas_presente_no_escopo_historico_nao_e_perdido():
    """Prova central da correção: o adapter NUNCA decide sozinho quem
    é "ativo" -- ele só usa o escopo que recebe. Um escopo com
    proveniência histórica real (`EscopoClientesFixo`) inclui um
    cliente hoje inativo, e o candidato é encontrado normalmente."""
    item = ItemInventarioPrestacao(
        documento_id='rel-historico', tipo_documental='Relatório de Benefícios',
        cliente=_CLI_INATIVO_HOJE, competencia=_COMPETENCIA_HISTORICA_REF,
    )
    fonte = _fonte_com_escopo_fixo((_CLI_INATIVO_HOJE,), {_CLI_INATIVO_HOJE: (item,)})
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios',
        _COMPETENCIA_HISTORICA, TipoRelacaoDocumental.COMPROVA,
    )
    assert len(candidatos) == 1
    assert candidatos[0].documento_id == 'rel-historico'
    assert candidatos[0].referencias_logicas == (_CLI_INATIVO_HOJE,)


# --- Caso H: sem correlação -- candidato real, relação NAO_ENCONTRADA (via módulo genérico) ---

def test_caso_h_sem_fonte_de_correlacao_candidato_e_real_mas_dados_ficam_vazios():
    """`fonte_dados_correlacao` nem precisa ser informada -- default
    `None`, nunca exige um fake in-memory só para representar
    ausência."""
    item = ItemInventarioPrestacao(
        documento_id='rel-1', tipo_documental='Relatório de Benefícios', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    fonte = _fonte_com_escopo_fixo((_CLI_A,), {_CLI_A: (item,)})  # fonte_dados_correlacao nao informada
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios', _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert len(candidatos) == 1  # identidade real
    assert candidatos[0].dados_correlacao == DadosCorrelacaoDocumental()  # honestamente vazio, nunca inventado


# --- Caso I: com correlação -- relação RESOLVIDA ---

def test_caso_i_com_fonte_de_correlacao_dados_disponiveis():
    item = ItemInventarioPrestacao(
        documento_id='rel-1', tipo_documental='Relatório de Benefícios', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    dados_correlacao = FonteDadosCorrelacaoEmMemoria()
    dados_correlacao.registrar('rel-1', DadosCorrelacaoDocumental(identificador_pedido='PED-1', valor_total='900,00'))
    fonte = _fonte_com_escopo_fixo((_CLI_A,), {_CLI_A: (item,)}, dados_correlacao=dados_correlacao)
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios', _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert candidatos[0].dados_correlacao.identificador_pedido == 'PED-1'


# --- Caso J: documento multi-cliente -- dedupe correto ---

def test_caso_j_mesmo_documento_em_2_clientes_une_referencias_nunca_duplica_candidato():
    item_a = ItemInventarioPrestacao(
        documento_id='rel-multi', tipo_documental='Relatório de Benefícios', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    item_b = ItemInventarioPrestacao(
        documento_id='rel-multi', tipo_documental='Relatório de Benefícios', cliente=_CLI_B, competencia=_COMPETENCIA_REF,
    )
    fonte = _fonte_com_escopo_fixo((_CLI_A, _CLI_B), {_CLI_A: (item_a,), _CLI_B: (item_b,)})
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios', _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert len(candidatos) == 1
    assert set(candidatos[0].referencias_logicas) == {_CLI_A, _CLI_B}


# --- Casos adicionais preservados ---

def test_descobre_candidato_do_tipo_pedido_ignora_outros_tipos():
    item_relatorio = ItemInventarioPrestacao(
        documento_id='rel-1', tipo_documental='Relatório de Benefícios', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    item_holerite = ItemInventarioPrestacao(
        documento_id='hol-1', tipo_documental='Holerite', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    fonte = _fonte_com_escopo_fixo((_CLI_A,), {_CLI_A: (item_relatorio, item_holerite)})
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
    fonte = _fonte_com_escopo_fixo((_CLI_A,), {_CLI_A: (item,)})
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Comprovante de Pagamento - VR/VA', _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert candidatos == ()


def test_nenhum_cliente_no_escopo_devolve_vazio():
    fonte = _fonte_com_escopo_fixo((), {})
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios', _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert candidatos == ()


def test_ordem_deterministica_por_documento_id():
    item_z = ItemInventarioPrestacao(
        documento_id='rel-z', tipo_documental='Relatório de Benefícios', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    item_a = ItemInventarioPrestacao(
        documento_id='rel-a', tipo_documental='Relatório de Benefícios', cliente=_CLI_A, competencia=_COMPETENCIA_REF,
    )
    fonte = _fonte_com_escopo_fixo((_CLI_A,), {_CLI_A: (item_z, item_a)})
    candidatos = fonte.candidatos_para_relacao(
        'comp-1', 'Comprovante de Pagamento - VR/VA', 'Relatório de Benefícios', _COMPETENCIA, TipoRelacaoDocumental.COMPROVA,
    )
    assert [c.documento_id for c in candidatos] == ['rel-a', 'rel-z']


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
    fonte_candidatos = _fonte_com_escopo_fixo((_CLI_A,), {_CLI_A: (item,)}, dados_correlacao=dados_correlacao)

    contexto = ContextoRelacaoDocumentoPrestacao(
        documento_id='comp-real-1', tipo_documental='Comprovante de Pagamento - VR/VA', competencia=_COMPETENCIA,
        dados_correlacao=DadosCorrelacaoDocumental(identificador_pedido='PED-77', valor_total='900,00', competencia=_COMPETENCIA),
        fonte_candidatos=fonte_candidatos,
    )
    resultado = resolver_relacao_e_avancar(contexto, InventarioPrestacaoEmMemoria())
    assert resultado.resolucao_relacao.estado.value == 'RESOLVIDA'
    assert resultado.resolucao_relacao.documento_a_id == 'rel-real-1'
