"""Testes de `FonteInventarioHoleritesAirtableShadow` (missão
"INVENTÁRIO DOCUMENTAL REAL DA PRESTAÇÃO", Fase 4)."""
from pathlib import Path

from magnata_os.classificacao.contratos import (
    ConfiancaResolucao,
    DimensaoResolucao,
    EstadoResolucaoDimensao,
    NivelConfianca,
    ReferenciaCanonica,
    ResolucaoDimensao,
)
from magnata_os.documental.importacao_lote.adapters.airtable_holerites_prestacao import (
    F_HOL_FUNC,
    TABLE_HOL,
    TIPO_HOLERITE,
    FonteInventarioHoleritesAirtableShadow,
)

_CLIENTE = ReferenciaCanonica('CLIENTE', 'rec_cliente')
_OUTRO_CLIENTE = ReferenciaCanonica('CLIENTE', 'rec_outro')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')


class _LeitorFake:
    def __init__(self, registros):
        self._registros = registros
        self.chamadas = []

    def listar_registros(self, table_id, fields, filter_by_formula=None):
        self.chamadas.append((table_id, tuple(fields), filter_by_formula))
        return self._registros if table_id == TABLE_HOL else []


class _FonteVinculosFake:
    """Resolve cada FUNCIONARIO para os clientes de um mapa fixo --
    nunca faz rede, mesmo papel de `FonteVinculosPrestacaoAirtableShadow`
    sem I/O."""

    def __init__(self, mapa_func_para_clientes):
        self._mapa = mapa_func_para_clientes

    def resolver_clientes(self, origem, competencia):
        clientes = self._mapa.get(origem.entidade_id, ())
        if not clientes:
            estado = EstadoResolucaoDimensao.NAO_ENCONTRADA
        elif len(clientes) == 1:
            estado = EstadoResolucaoDimensao.RESOLVIDA
        else:
            estado = EstadoResolucaoDimensao.AMBIGUA
        return ResolucaoDimensao(
            dimensao=DimensaoResolucao.CLIENTE, estado=estado,
            valores_confirmados=clientes if estado == EstadoResolucaoDimensao.RESOLVIDA else (),
            candidatos=clientes if estado == EstadoResolucaoDimensao.AMBIGUA else (),
            confianca=ConfiancaResolucao(NivelConfianca.FORTE if clientes else NivelConfianca.INDETERMINADA),
        )


def test_holerite_do_cliente_pedido_aparece_com_colaborador_sanitizado():
    leitor = _LeitorFake(({'id': 'rec_hol_1', 'fields': {F_HOL_FUNC: ['rec_func_a']}},))
    fonte_vinculos = _FonteVinculosFake({'rec_func_a': (_CLIENTE,)})
    fonte = FonteInventarioHoleritesAirtableShadow(leitor, fonte_vinculos)
    itens = fonte.listar(_CLIENTE, _COMPETENCIA)
    assert len(itens) == 1
    assert itens[0].tipo_documental == TIPO_HOLERITE
    assert itens[0].colaborador == ReferenciaCanonica('COLABORADOR', 'rec_func_a')
    assert itens[0].documento_id == 'rec_hol_1'


def test_holerite_de_outro_cliente_nunca_aparece():
    leitor = _LeitorFake(({'id': 'rec_hol_1', 'fields': {F_HOL_FUNC: ['rec_func_a']}},))
    fonte_vinculos = _FonteVinculosFake({'rec_func_a': (_OUTRO_CLIENTE,)})
    fonte = FonteInventarioHoleritesAirtableShadow(leitor, fonte_vinculos)
    assert fonte.listar(_CLIENTE, _COMPETENCIA) == ()


def test_vinculo_ambiguo_nunca_e_tratado_como_resolvido():
    leitor = _LeitorFake(({'id': 'rec_hol_1', 'fields': {F_HOL_FUNC: ['rec_func_a']}},))
    fonte_vinculos = _FonteVinculosFake({'rec_func_a': (_CLIENTE, _OUTRO_CLIENTE)})
    fonte = FonteInventarioHoleritesAirtableShadow(leitor, fonte_vinculos)
    assert fonte.listar(_CLIENTE, _COMPETENCIA) == ()


def test_colaborador_vinculado_a_2_clientes_genuinamente_aparece_nos_2():
    """Vínculo múltiplo GENUÍNO (RESOLVIDA com 2+ valores) -- diferente
    de AMBIGUA -- o mesmo Holerite aparece para cada cliente, 1
    identidade documental, nunca duplicada fisicamente."""
    leitor = _LeitorFake(({'id': 'rec_hol_1', 'fields': {F_HOL_FUNC: ['rec_func_a']}},))

    class _FonteVinculosMultiplo:
        def resolver_clientes(self, origem, competencia):
            return ResolucaoDimensao(
                dimensao=DimensaoResolucao.CLIENTE, estado=EstadoResolucaoDimensao.RESOLVIDA,
                valores_confirmados=(_CLIENTE, _OUTRO_CLIENTE),
                confianca=ConfiancaResolucao(NivelConfianca.FORTE),
            )

    fonte = FonteInventarioHoleritesAirtableShadow(leitor, _FonteVinculosMultiplo())
    item_cliente = fonte.listar(_CLIENTE, _COMPETENCIA)
    item_outro = fonte.listar(_OUTRO_CLIENTE, _COMPETENCIA)
    assert len(item_cliente) == 1 and len(item_outro) == 1
    assert item_cliente[0].documento_id == item_outro[0].documento_id == 'rec_hol_1'


def test_funcionario_sem_vinculo_nunca_quebra_a_listagem():
    leitor = _LeitorFake(({'id': 'rec_hol_1', 'fields': {F_HOL_FUNC: ['rec_func_a']}},))
    fonte_vinculos = _FonteVinculosFake({})
    fonte = FonteInventarioHoleritesAirtableShadow(leitor, fonte_vinculos)
    assert fonte.listar(_CLIENTE, _COMPETENCIA) == ()


def test_competencia_usa_formato_folha_mensal_ja_estabelecido():
    leitor = _LeitorFake(())
    FonteInventarioHoleritesAirtableShadow(leitor, _FonteVinculosFake({})).listar(_CLIENTE, _COMPETENCIA)
    assert leitor.chamadas == [(TABLE_HOL, (F_HOL_FUNC,), '{Folha Mensal}="Julho 2026"')]


def test_adapter_nunca_solicita_campos_de_identidade_pessoal():
    import ast

    caminho = Path('magnata_os/documental/importacao_lote/adapters/airtable_holerites_prestacao.py')
    arvore = ast.parse(caminho.read_text(encoding='utf-8'))
    nos_de_docstring = {
        id(no.value) for no in ast.walk(arvore)
        if isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant) and isinstance(no.value.value, str)
    }
    literais = {
        no.value for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in nos_de_docstring
    }
    assert 'Nome Completo' not in literais
    assert 'CPF' not in literais


def test_nenhum_metodo_de_escrita_existe():
    metodos = {n for n in dir(FonteInventarioHoleritesAirtableShadow) if not n.startswith('_')}
    assert metodos == {'listar'}
