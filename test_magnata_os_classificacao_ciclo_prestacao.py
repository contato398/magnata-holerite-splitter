"""Testes focados de `ciclo_prestacao.py` (missão "POLÍTICA
OPERACIONAL REAL DE CLIENTES/REQUISITOS", Fases 9-12)."""
import ast
import inspect

from magnata_os.classificacao import ciclo_prestacao as modulo
from magnata_os.classificacao.ciclo_prestacao import (
    NecessidadeDocumentoPrestacao,
    executar_ciclo_prestacao,
    executar_ciclo_prestacao_descoberta,
)
from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.holerite_obrigatorio_prestacao import TIPO_HOLERITE
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
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
from magnata_os.classificacao.pacote_prestacao import EstadoPacotePrestacao
from magnata_os.classificacao.prestacao_readiness import RequisitoDocumentalPrestacao
from magnata_os.classificacao.resolucao_semantica import compor_resolucao_semantica

_CONTEXTO = ContextoCicloPrestacao(competencia_base=(2026, 7))
_CLIENTE_COM_CONTEXTO = ReferenciaCanonica('CLIENTE', 'rec_com_contexto')
_CLIENTE_SEM_CONTEXTO = ReferenciaCanonica('CLIENTE', 'rec_sem_contexto')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')


class _FonteClientesDoisAtivos:
    def listar_ativos(self, contexto):
        return (_CLIENTE_COM_CONTEXTO, _CLIENTE_SEM_CONTEXTO)


class _FonteRequisitosVazia:
    def registros_para(self, cliente, contexto):
        return ()


class _FonteInventarioVazia:
    def listar(self, cliente, competencia):
        return ()


def _resolucao_ancora(cliente):
    perfil = PerfilAplicabilidadeResolucao(
        perfil_id='p', version='1', escopo_documental='teste',
        regras=(
            RegraAplicabilidadeDimensao(DimensaoResolucao.CLIENTE, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
            RegraAplicabilidadeDimensao(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA, Cardinalidade(1, 1)),
        ),
    )
    return compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id='doc', hash_sha256='a' * 64, resolver_id='r', resolver_version='1',
            politica_id='p', politica_version='1', contexto_fontes_fingerprint='teste',
        ),
        perfil=perfil,
        resolucoes=(
            ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(cliente,)),
            ResolucaoDimensao(dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.RESOLVIDA, valores_confirmados=(_COMPETENCIA,)),
        ),
    )


def test_cliente_ativo_sem_competencia_ou_ancora_nunca_vira_pacote_ficticio():
    """Cliente listado como ativo, mas sem competência efetiva NEM
    resolução-âncora disponível -- nunca inventa, simplesmente fica de
    fora do resultado deste ciclo (cláusula pétrea #14: nunca inventar)."""
    resultado = executar_ciclo_prestacao(
        contexto=_CONTEXTO,
        fonte_clientes=_FonteClientesDoisAtivos(),
        fonte_requisitos=_FonteRequisitosVazia(),
        fonte_inventario=_FonteInventarioVazia(),
        requisitos_base=(),
        resolucoes_ancora={_CLIENTE_COM_CONTEXTO: _resolucao_ancora(_CLIENTE_COM_CONTEXTO)},
        competencias_por_cliente={_CLIENTE_COM_CONTEXTO: _COMPETENCIA},
    )
    clientes_no_resultado = {r.cliente for r in resultado.resultados_por_cliente}
    assert clientes_no_resultado == {_CLIENTE_COM_CONTEXTO}
    assert _CLIENTE_SEM_CONTEXTO not in clientes_no_resultado


# ==== Incremento 6 (evolução do contrato do ciclo de Prestação V1) ====
# Cliente com COMPETÊNCIA conhecida mas SEM âncora real (chave ausente
# em `resolucoes_ancora`) NÃO é mais descartado silenciosamente --
# aparece no resultado com estado EM_REVISAO explícito. Distinto do
# teste acima: lá, `_CLIENTE_SEM_CONTEXTO` também não tem competência
# (gap de configuração, fora do escopo deste incremento); aqui, SÓ a
# âncora está ausente.


def test_cliente_com_competencia_mas_sem_ancora_aparece_em_revisao_explicita():
    resultado = executar_ciclo_prestacao(
        contexto=_CONTEXTO,
        fonte_clientes=_FonteClientesDoisAtivos(),
        fonte_requisitos=_FonteRequisitosVazia(),
        fonte_inventario=_FonteInventarioVazia(),
        requisitos_base=(),
        resolucoes_ancora={},  # nenhum cliente tem âncora
        competencias_por_cliente={
            _CLIENTE_COM_CONTEXTO: _COMPETENCIA,
            _CLIENTE_SEM_CONTEXTO: _COMPETENCIA,
        },
    )
    clientes_no_resultado = {r.cliente for r in resultado.resultados_por_cliente}
    # Os DOIS aparecem agora -- nenhum descartado, os dois têm competência.
    assert clientes_no_resultado == {_CLIENTE_COM_CONTEXTO, _CLIENTE_SEM_CONTEXTO}
    for resultado_cliente in resultado.resultados_por_cliente:
        assert resultado_cliente.pacote.estado == EstadoPacotePrestacao.EM_REVISAO
        assert 'sem_evidencia_documental_real' in resultado_cliente.pacote.motivos


def test_cliente_com_ancora_real_nao_e_afetado_por_cliente_irmao_sem_ancora():
    """1 cliente com âncora real, outro sem -- cada um reflete seu
    PRÓPRIO estado, nunca contaminado pelo outro."""
    resultado = executar_ciclo_prestacao(
        contexto=_CONTEXTO,
        fonte_clientes=_FonteClientesDoisAtivos(),
        fonte_requisitos=_FonteRequisitosVazia(),
        fonte_inventario=_FonteInventarioVazia(),
        requisitos_base=(),
        resolucoes_ancora={_CLIENTE_COM_CONTEXTO: _resolucao_ancora(_CLIENTE_COM_CONTEXTO)},
        competencias_por_cliente={
            _CLIENTE_COM_CONTEXTO: _COMPETENCIA,
            _CLIENTE_SEM_CONTEXTO: _COMPETENCIA,
        },
    )
    por_cliente = {r.cliente: r for r in resultado.resultados_por_cliente}
    assert set(por_cliente) == {_CLIENTE_COM_CONTEXTO, _CLIENTE_SEM_CONTEXTO}
    assert por_cliente[_CLIENTE_COM_CONTEXTO].pacote.estado != EstadoPacotePrestacao.EM_REVISAO
    assert por_cliente[_CLIENTE_SEM_CONTEXTO].pacote.estado == EstadoPacotePrestacao.EM_REVISAO
    assert 'sem_evidencia_documental_real' in por_cliente[_CLIENTE_SEM_CONTEXTO].pacote.motivos


def test_necessidade_documento_exige_texto_nao_vazio():
    import pytest
    with pytest.raises(ValueError):
        NecessidadeDocumentoPrestacao(
            cliente=_CLIENTE_COM_CONTEXTO, competencia=_COMPETENCIA, tipo_documental='', motivo_exigencia='x',
        )


def _e_docstring(no_expr: ast.Expr) -> bool:
    valor = no_expr.value
    return isinstance(valor, ast.Constant) and isinstance(valor.value, str)


def test_ciclo_prestacao_nunca_hardcoda_nome_de_cliente():
    """Nenhum identificador literal de cliente (A/B/C/SKY, nomes
    próprios) em código executável -- só nas fixtures dos testes.

    'holerite' continua DELIBERADAMENTE fora da lista de termos
    proibidos -- Adendo de Regra de Negócio -- Holerite: "HOLERITE É
    OBRIGATÓRIO EM TODA PRESTAÇÃO DE CONTAS", universal, avaliado por
    cardinalidade colaborador. A missão "FECHAMENTO DA BASE CANÔNICA"
    chegou a instruir reverter isso para condicional-por-cliente; um
    "ADENDO DE CONTINUIDADE" do mesmo humano, no mesmo dia, revogou
    essa instrução ANTES do PR ser mesclado -- Holerite nunca chegou a
    virar condicional em produção (histórico completo em
    docs/decisoes/fechamento-base-canonica-ciclo-piloto-readonly-v1.md).
    Este módulo continua LEGITIMAMENTE importando `TIPO_HOLERITE`/usando
    o motivo `holerite_obrigatorio_por_colaborador_esperado` -- nunca um
    cliente/tipo arbitrário, é a ÚNICA exceção explicitamente
    autorizada. 'sky'/'extrato'/'fgts'/'dctfweb' continuam proibidos --
    nenhum outro tipo/cliente ganhou tratamento especial."""
    codigo_fonte = inspect.getsource(modulo)
    arvore = ast.parse(codigo_fonte)
    nos_de_docstring = {
        id(no.value) for no in ast.walk(arvore)
        if isinstance(no, ast.Expr) and _e_docstring(no)
    }
    literais = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Constant) and isinstance(no.value, str):
            if id(no) not in nos_de_docstring:
                literais.add(no.value.lower())
    proibidos = ['sky', 'extrato', 'fgts', 'dctfweb']
    for termo in proibidos:
        achados = {s for s in literais if termo in s}
        assert not achados, f'termo proibido em literal de código: {termo!r} em {achados!r}'


# ==== EVOLUÇÃO DO CONTRATO DO CICLO V1 — DESCOBERTA SEM ÂNCORA (Incremento 2) ====


class _FonteInventarioComItens:
    def __init__(self, itens):
        self._itens = itens

    def listar(self, cliente, competencia):
        return tuple(
            item for item in self._itens
            if item.cliente == cliente and item.competencia == competencia
        )


class _FonteColaboradoresEsperadosFake:
    def __init__(self, colaboradores):
        self._colaboradores = colaboradores

    def colaboradores_esperados_para(self, cliente, contexto):
        return self._colaboradores


def test_descoberta_gera_necessidades_sem_nenhuma_ancora():
    """A âncora nunca é exigida por `executar_ciclo_prestacao_descoberta`
    -- mesmos 2 clientes de `_FonteClientesDoisAtivos`, sem
    `resolucoes_ancora` em lugar nenhum da chamada (o parâmetro nem
    existe nesta função)."""
    resultado = executar_ciclo_prestacao_descoberta(
        contexto=_CONTEXTO,
        fonte_clientes=_FonteClientesDoisAtivos(),
        fonte_requisitos=_FonteRequisitosVazia(),
        fonte_inventario=_FonteInventarioVazia(),
        requisitos_base=(RequisitoDocumentalPrestacao('Extrato'),),
        competencias_por_cliente={
            _CLIENTE_COM_CONTEXTO: _COMPETENCIA,
            _CLIENTE_SEM_CONTEXTO: _COMPETENCIA,
        },
    )
    # Sem competência: nenhum cliente ficou de fora aqui (ambos têm
    # competência, diferente do teste de readiness que só dá competência
    # a 1 deles) -- os dois devem aparecer com a necessidade de Extrato.
    clientes_no_resultado = {r.cliente for r in resultado.resultados_por_cliente}
    assert clientes_no_resultado == {_CLIENTE_COM_CONTEXTO, _CLIENTE_SEM_CONTEXTO}
    for resultado_cliente in resultado.resultados_por_cliente:
        assert resultado_cliente.necessidades == (
            NecessidadeDocumentoPrestacao(
                cliente=resultado_cliente.cliente, competencia=_COMPETENCIA,
                tipo_documental='Extrato', motivo_exigencia='requisito_documental_da_politica_efetiva',
                fontes_ainda_nao_consultadas=('gmail', 'airtable', 'armazenamento_documental'),
            ),
        )


def test_descoberta_sem_competencia_conhecida_fica_de_fora_nunca_inventa():
    """Mesma disciplina de `executar_ciclo_prestacao`: cliente ativo sem
    competência conhecida nunca aparece no resultado -- nunca inventa."""
    resultado = executar_ciclo_prestacao_descoberta(
        contexto=_CONTEXTO,
        fonte_clientes=_FonteClientesDoisAtivos(),
        fonte_requisitos=_FonteRequisitosVazia(),
        fonte_inventario=_FonteInventarioVazia(),
        requisitos_base=(RequisitoDocumentalPrestacao('Extrato'),),
        competencias_por_cliente={_CLIENTE_COM_CONTEXTO: _COMPETENCIA},
    )
    clientes_no_resultado = {r.cliente for r in resultado.resultados_por_cliente}
    assert clientes_no_resultado == {_CLIENTE_COM_CONTEXTO}


def test_descoberta_inventario_parcial_reduz_necessidades_corretamente():
    """Inventário já contendo 1 dos 2 tipos exigidos reduz a necessidade
    só ao tipo realmente ausente -- reaproveita `calcular_tipos_faltantes`
    (mesma função usada pelo readiness real, Incremento 1)."""
    item_presente = ItemInventarioPrestacao(
        documento_id='doc-extrato-1', tipo_documental='Extrato',
        cliente=_CLIENTE_COM_CONTEXTO, competencia=_COMPETENCIA,
    )
    resultado = executar_ciclo_prestacao_descoberta(
        contexto=_CONTEXTO,
        fonte_clientes=_FonteClientesDoisAtivos(),
        fonte_requisitos=_FonteRequisitosVazia(),
        fonte_inventario=_FonteInventarioComItens((item_presente,)),
        requisitos_base=(
            RequisitoDocumentalPrestacao('Extrato'),
            RequisitoDocumentalPrestacao('FGTS'),
        ),
        competencias_por_cliente={_CLIENTE_COM_CONTEXTO: _COMPETENCIA},
    )
    (resultado_cliente,) = resultado.resultados_por_cliente
    tipos_pedidos = {n.tipo_documental for n in resultado_cliente.necessidades}
    assert tipos_pedidos == {'FGTS'}


def test_descoberta_holerite_por_colaborador_continua_coerente():
    """Holerite obrigatório por CARDINALIDADE colaborador (nunca por
    contagem simples) continua coerente na descoberta -- mesma função
    `avaliar_obrigatoriedade_por_tipo_documental` usada pelo readiness
    real, mesmo motivo de exigência, nunca um segundo mecanismo."""
    colaborador_com_holerite = ReferenciaCanonica('COLABORADOR', 'colab-1')
    colaborador_sem_holerite = ReferenciaCanonica('COLABORADOR', 'colab-2')
    item_holerite = ItemInventarioPrestacao(
        documento_id='doc-holerite-1', tipo_documental=TIPO_HOLERITE,
        cliente=_CLIENTE_COM_CONTEXTO, competencia=_COMPETENCIA,
        colaborador=colaborador_com_holerite,
    )
    resultado = executar_ciclo_prestacao_descoberta(
        contexto=_CONTEXTO,
        fonte_clientes=_FonteClientesDoisAtivos(),
        fonte_requisitos=_FonteRequisitosVazia(),
        fonte_inventario=_FonteInventarioComItens((item_holerite,)),
        requisitos_base=(RequisitoDocumentalPrestacao(TIPO_HOLERITE),),
        competencias_por_cliente={_CLIENTE_COM_CONTEXTO: _COMPETENCIA},
        fonte_colaboradores_esperados=_FonteColaboradoresEsperadosFake(
            (colaborador_com_holerite, colaborador_sem_holerite),
        ),
    )
    (resultado_cliente,) = resultado.resultados_por_cliente
    # Holerite tratado por cardinalidade colaborador -- necessidade
    # genérica de "Holerite" nunca aparece (excluída propositalmente),
    # só a necessidade específica do colaborador faltante.
    assert all(n.tipo_documental == TIPO_HOLERITE for n in resultado_cliente.necessidades)
    assert len(resultado_cliente.necessidades) == 1
    necessidade = resultado_cliente.necessidades[0]
    assert necessidade.colaborador == colaborador_sem_holerite
    assert necessidade.motivo_exigencia == 'holerite_obrigatorio_por_colaborador_esperado'


def test_descoberta_nunca_monta_pacote():
    """`ResultadoDescobertaCliente` nunca tem campo `pacote` -- não
    existe pacote sem readiness real avaliada."""
    resultado = executar_ciclo_prestacao_descoberta(
        contexto=_CONTEXTO,
        fonte_clientes=_FonteClientesDoisAtivos(),
        fonte_requisitos=_FonteRequisitosVazia(),
        fonte_inventario=_FonteInventarioVazia(),
        requisitos_base=(),
        competencias_por_cliente={_CLIENTE_COM_CONTEXTO: _COMPETENCIA},
    )
    (resultado_cliente,) = resultado.resultados_por_cliente
    assert not hasattr(resultado_cliente, 'pacote')
