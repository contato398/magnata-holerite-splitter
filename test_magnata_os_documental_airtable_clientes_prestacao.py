"""Testes de `FonteClientesPrestacaoAirtable` (Fase 6 da missão
"POLÍTICA OPERACIONAL REAL DE CLIENTES/REQUISITOS"). Nenhuma chamada
Airtable real -- só um stub local do leitor, seguindo o mesmo padrão
já usado pelos testes de `FonteVinculosPrestacaoAirtableShadow`."""
from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.importacao_lote.adapters.airtable_clientes_prestacao import (
    FonteClientesPrestacaoAirtable,
)
from magnata_os.documental.importacao_lote.contratos import CandidatoCliente

_CONTEXTO = ContextoCicloPrestacao(competencia_base=(2026, 7))


class _LeitorStub:
    """Nunca faz rede -- devolve candidatos pré-definidos, mesmo papel
    de `LeitorAirtableSomenteLeitura` sem nenhum `requests.get`."""

    def __init__(self, candidatos):
        self._candidatos = candidatos

    def listar_clientes(self):
        return self._candidatos


def test_listar_ativos_traduz_candidatos_em_referencias_canonicas():
    leitor = _LeitorStub((
        CandidatoCliente(cliente_id='rec_a', cnpj='11222333000181', nome_normalizado='CLIENTE A'),
        CandidatoCliente(cliente_id='rec_b', cnpj=None, nome_normalizado='CLIENTE B'),
    ))
    fonte = FonteClientesPrestacaoAirtable(leitor)
    ativos = fonte.listar_ativos(_CONTEXTO)
    assert ativos == (
        ReferenciaCanonica('CLIENTE', 'rec_a'),
        ReferenciaCanonica('CLIENTE', 'rec_b'),
    )


def test_listar_ativos_nunca_expoe_nome_ou_cnpj_como_identidade():
    """Identidade é sempre o record id -- nunca o nome/CNPJ (Fase 2:
    "não transportar nome como identidade primária")."""
    leitor = _LeitorStub((
        CandidatoCliente(cliente_id='rec_x', cnpj='99888777000160', nome_normalizado='NOME QUALQUER'),
    ))
    fonte = FonteClientesPrestacaoAirtable(leitor)
    ativos = fonte.listar_ativos(_CONTEXTO)
    assert ativos[0].entidade_id == 'rec_x'
    assert 'NOME QUALQUER' not in ativos[0].entidade_id


def test_lista_vazia_nunca_levanta_excecao():
    fonte = FonteClientesPrestacaoAirtable(_LeitorStub(()))
    assert fonte.listar_ativos(_CONTEXTO) == ()


def test_nenhum_metodo_de_escrita_existe():
    """Prova estrutural -- a superfície da classe nunca tem create/update/delete."""
    metodos = {nome for nome in dir(FonteClientesPrestacaoAirtable) if not nome.startswith('_')}
    assert metodos == {'listar_ativos'}
