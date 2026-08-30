"""Testes focados de `ciclo_prestacao.py` (missão "POLÍTICA
OPERACIONAL REAL DE CLIENTES/REQUISITOS", Fases 9-12)."""
import ast
import inspect

from magnata_os.classificacao import ciclo_prestacao as modulo
from magnata_os.classificacao.ciclo_prestacao import (
    NecessidadeDocumentoPrestacao,
    executar_ciclo_prestacao,
)
from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
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
