"""Testes de `FonteClientesPrestacaoAirtable` (Fase 6 da missão
"POLÍTICA OPERACIONAL REAL DE CLIENTES/REQUISITOS" — corrigido pela
validação live read-only, missão "MERGE PR #100 + VALIDAÇÃO LIVE
READ-ONLY": Clientes TEM um campo Status real, `listar_ativos` agora
filtra por ele). Nenhuma chamada Airtable real -- só um stub local do
leitor, seguindo o mesmo padrão já usado pelos testes de
`FonteVinculosPrestacaoAirtableShadow`."""
from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.importacao_lote.adapters.airtable_clientes_prestacao import (
    F_CLI_STATUS,
    FonteClientesPrestacaoAirtable,
)
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import TABLE_CLIENTES

_CONTEXTO = ContextoCicloPrestacao(competencia_base=(2026, 7))


class _LeitorStub:
    """Nunca faz rede -- devolve registros pré-definidos, mesmo papel
    de `LeitorAirtableSomenteLeitura` sem nenhum `requests.get`."""

    def __init__(self, registros):
        self._registros = registros
        self.chamadas = []

    def listar_registros(self, table_id, fields, filter_by_formula=None):
        self.chamadas.append((table_id, tuple(fields), filter_by_formula))
        return self._registros if table_id == TABLE_CLIENTES else []


def test_listar_ativos_so_devolve_clientes_com_status_ativo():
    leitor = _LeitorStub((
        {'id': 'rec_a', 'fields': {F_CLI_STATUS: 'Ativo'}},
        {'id': 'rec_b', 'fields': {F_CLI_STATUS: 'Inativo'}},
    ))
    fonte = FonteClientesPrestacaoAirtable(leitor)
    ativos = fonte.listar_ativos(_CONTEXTO)
    assert ativos == (ReferenciaCanonica('CLIENTE', 'rec_a'),)


def test_listar_ativos_nunca_expoe_nome_ou_cnpj_como_identidade():
    """Identidade é sempre o record id -- nunca o nome/CNPJ (Fase 2:
    "não transportar nome como identidade primária"). Este adapter nem
    sequer solicita os campos Nome/CNPJ ao Airtable (least-privilege de
    campo)."""
    leitor = _LeitorStub((
        {'id': 'rec_x', 'fields': {F_CLI_STATUS: 'Ativo'}},
    ))
    fonte = FonteClientesPrestacaoAirtable(leitor)
    ativos = fonte.listar_ativos(_CONTEXTO)
    assert ativos[0].entidade_id == 'rec_x'
    assert leitor.chamadas == [(TABLE_CLIENTES, (F_CLI_STATUS,), None)]


def test_status_desconhecido_nunca_e_tratado_como_ativo():
    """Nenhum valor além de 'Ativo' literal conta -- nunca um default
    permissivo para status ausente/desconhecido/vazio."""
    leitor = _LeitorStub((
        {'id': 'rec_y', 'fields': {}},
        {'id': 'rec_z', 'fields': {F_CLI_STATUS: 'algo_inesperado'}},
    ))
    fonte = FonteClientesPrestacaoAirtable(leitor)
    assert fonte.listar_ativos(_CONTEXTO) == ()


def test_lista_vazia_nunca_levanta_excecao():
    fonte = FonteClientesPrestacaoAirtable(_LeitorStub(()))
    assert fonte.listar_ativos(_CONTEXTO) == ()


def test_nenhum_metodo_de_escrita_existe():
    """Prova estrutural -- a superfície da classe nunca tem create/update/delete."""
    metodos = {nome for nome in dir(FonteClientesPrestacaoAirtable) if not nome.startswith('_')}
    assert metodos == {'listar_ativos'}
