"""Testes do adaptador GERAL `ResultadoResolucaoSemantico` ->
`ItemInventarioPrestacao` (missão "CORREDOR OPERACIONAL DA PRESTAÇÃO DE
CONTAS", Fase 3)."""
import ast
import inspect

import pytest

from magnata_os.classificacao import adaptador_inventario_prestacao as modulo
from magnata_os.classificacao.adaptador_inventario_prestacao import (
    itens_para_clientes_broadcast,
    resultado_semantico_para_item_inventario,
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
from magnata_os.classificacao.resolucao_semantica import compor_resolucao_semantica

_TIPO = ReferenciaCanonica('TIPO_DOCUMENTAL', 'Holerite')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')
_CLIENTE = ReferenciaCanonica('CLIENTE', 'rec_cliente_a')


def _regra(dimensao, aplicabilidade):
    cardinalidade = Cardinalidade(1, 1) if aplicabilidade == AplicabilidadeDimensao.OBRIGATORIA else Cardinalidade(0, 0)
    return RegraAplicabilidadeDimensao(dimensao=dimensao, aplicabilidade=aplicabilidade, cardinalidade=cardinalidade)


def _perfil(cliente_aplicabilidade=AplicabilidadeDimensao.OBRIGATORIA):
    return PerfilAplicabilidadeResolucao(
        perfil_id='teste-adaptador-v1', version='1', escopo_documental='prestacao-contas',
        regras=(
            _regra(DimensaoResolucao.TIPO_DOCUMENTAL, AplicabilidadeDimensao.OBRIGATORIA),
            _regra(DimensaoResolucao.CLIENTE, cliente_aplicabilidade),
            _regra(DimensaoResolucao.COMPETENCIA, AplicabilidadeDimensao.OBRIGATORIA),
            _regra(DimensaoResolucao.COLABORADOR, AplicabilidadeDimensao.NAO_APLICAVEL),
            _regra(DimensaoResolucao.UNIDADE_POSTO, AplicabilidadeDimensao.NAO_APLICAVEL),
            _regra(DimensaoResolucao.VINCULO, AplicabilidadeDimensao.NAO_APLICAVEL),
        ),
    )


def _resolucoes(estado_cliente=EstadoResolucaoDimensao.RESOLVIDA, valores_cliente=(_CLIENTE,)):
    return (
        ResolucaoDimensao(
            dimensao=DimensaoResolucao.TIPO_DOCUMENTAL, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(_TIPO,),
        ),
        ResolucaoDimensao(dimensao=DimensaoResolucao.CLIENTE, estado=estado_cliente, valores_confirmados=valores_cliente),
        ResolucaoDimensao(
            dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.RESOLVIDA,
            valores_confirmados=(_COMPETENCIA,),
        ),
        ResolucaoDimensao(dimensao=DimensaoResolucao.COLABORADOR, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ResolucaoDimensao(dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
        ResolucaoDimensao(dimensao=DimensaoResolucao.VINCULO, estado=EstadoResolucaoDimensao.NAO_APLICAVEL),
    )


def _compor(perfil, resolucoes, documento_id='doc-1'):
    return compor_resolucao_semantica(
        entrada=EntradaResolucaoDocumento(
            documento_id=documento_id, hash_sha256='a' * 64, resolver_id='r', resolver_version='1',
            politica_id='teste', politica_version='1', contexto_fontes_fingerprint='teste',
        ),
        perfil=perfil, resolucoes=resolucoes,
    )


def test_documento_com_todas_as_dimensoes_resolvidas_vira_item():
    resultado = _compor(_perfil(), _resolucoes())
    item = resultado_semantico_para_item_inventario('doc-1', resultado)
    assert item is not None
    assert item.documento_id == 'doc-1'
    assert item.tipo_documental == 'Holerite'
    assert item.cliente == _CLIENTE
    assert item.competencia == _COMPETENCIA


def test_cliente_ambiguo_nunca_vira_item():
    resultado = _compor(_perfil(), _resolucoes(
        estado_cliente=EstadoResolucaoDimensao.AMBIGUA, valores_cliente=(),
    ))
    assert resultado_semantico_para_item_inventario('doc-1', resultado) is None


def test_documento_global_sem_cliente_broadcast_injetado_nunca_vira_item():
    """CLIENTE NAO_APLICAVEL (documento global) sem `cliente_broadcast`
    -- nunca inventa, devolve None."""
    resolucoes = _resolucoes(estado_cliente=EstadoResolucaoDimensao.NAO_APLICAVEL, valores_cliente=())
    resultado = _compor(_perfil(cliente_aplicabilidade=AplicabilidadeDimensao.NAO_APLICAVEL), resolucoes)
    assert resultado_semantico_para_item_inventario('doc-1', resultado) is None


def test_documento_global_com_cliente_broadcast_injetado_vira_item():
    resolucoes = _resolucoes(estado_cliente=EstadoResolucaoDimensao.NAO_APLICAVEL, valores_cliente=())
    resultado = _compor(_perfil(cliente_aplicabilidade=AplicabilidadeDimensao.NAO_APLICAVEL), resolucoes)
    item = resultado_semantico_para_item_inventario('doc-1', resultado, cliente_broadcast=_CLIENTE)
    assert item is not None
    assert item.cliente == _CLIENTE


def test_itens_para_clientes_broadcast_preserva_mesmo_documento_id():
    """1 documento -> N itens lógicos, MESMO documento_id em todos --
    nunca duplica identidade documental (Fase 11)."""
    cliente_b = ReferenciaCanonica('CLIENTE', 'rec_cliente_b')
    resolucoes = _resolucoes(estado_cliente=EstadoResolucaoDimensao.NAO_APLICAVEL, valores_cliente=())
    resultado = _compor(_perfil(cliente_aplicabilidade=AplicabilidadeDimensao.NAO_APLICAVEL), resolucoes)
    itens = itens_para_clientes_broadcast('doc-broadcast-1', resultado, (_CLIENTE, cliente_b))
    assert len(itens) == 2
    assert {item.cliente for item in itens} == {_CLIENTE, cliente_b}
    assert all(item.documento_id == 'doc-broadcast-1' for item in itens)


def test_competencia_nao_resolvida_nunca_vira_item():
    resolucoes = list(_resolucoes())
    resolucoes[2] = ResolucaoDimensao(dimensao=DimensaoResolucao.COMPETENCIA, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA)
    resultado = _compor(_perfil(), tuple(resolucoes))
    assert resultado_semantico_para_item_inventario('doc-1', resultado) is None


def _e_docstring(no_expr: ast.Expr) -> bool:
    valor = no_expr.value
    return isinstance(valor, ast.Constant) and isinstance(valor.value, str)


def test_adaptador_e_estruturalmente_generico():
    """Nunca conhece nenhum tipo documental por nome -- só lê dimensões
    já resolvidas (mesma prova AST das missões anteriores)."""
    codigo_fonte = inspect.getsource(modulo)
    arvore = ast.parse(codigo_fonte)
    nos_de_docstring = {
        id(no.value) for no in ast.walk(arvore)
        if isinstance(no, ast.Expr) and _e_docstring(no)
    }
    identificadores, literais = set(), set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Name, ast.arg)):
            identificadores.add(no.id if isinstance(no, ast.Name) else no.arg)
        elif isinstance(no, (ast.FunctionDef, ast.ClassDef)):
            identificadores.add(no.name)
        elif isinstance(no, ast.Constant) and isinstance(no.value, str):
            if id(no) not in nos_de_docstring:
                literais.add(no.value)
    codigo_executavel = {s.lower() for s in identificadores | literais}
    proibidos = ['holerite', 'extrato', 'fgts', 'dctfweb', 'certidao', 'filename', 'if tipo ==']
    for termo in proibidos:
        achados = {s for s in codigo_executavel if termo in s}
        assert not achados, f'termo proibido em código executável: {termo!r} em {achados!r}'


def test_nenhuma_funcao_do_modulo_aceita_filename():
    for nome, obj in inspect.getmembers(modulo, inspect.isfunction):
        parametros = inspect.signature(obj).parameters
        assert 'filename' not in parametros and 'nome_arquivo' not in parametros, nome
