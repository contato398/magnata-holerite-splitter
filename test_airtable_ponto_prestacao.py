"""Testes do adapter read-only `airtable_ponto_prestacao.py` (missão
"FONTE DE INVENTÁRIO DE FOLHA/CARTÃO DE PONTO V1"). Usa um FAKE do
leitor (nunca rede real) -- prova só o mapeamento de schema e a
disciplina read-only, nunca lê/escreve o Airtable de verdade."""
import datetime

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.importacao_lote.adapters.airtable_ponto_prestacao import (
    AT_PONTO,
    F_DATA,
    F_ENTRADA,
    F_FUNC,
    F_SAIDA,
    FonteRegistrosPontoAirtableShadow,
)


class _LeitorFake:
    def __init__(self, registros):
        self._registros = registros
        self.chamadas = []

    def listar_registros(self, table_id, fields, filter_by_formula=None):
        self.chamadas.append({'table_id': table_id, 'fields': fields, 'filter_by_formula': filter_by_formula})
        return self._registros


def test_mapeia_registro_com_marcacao_para_registro_bruto():
    leitor = _LeitorFake([
        {'id': 'recPonto1', 'fields': {
            F_FUNC: ['recFunc1'], F_DATA: '2026-06-10',
            F_ENTRADA: '2026-06-10T08:00:00-03:00', F_SAIDA: '2026-06-10T17:00:00-03:00',
        }},
    ])
    fonte = FonteRegistrosPontoAirtableShadow(leitor)
    registros = fonte.listar_no_intervalo(datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))
    assert len(registros) == 1
    r = registros[0]
    assert r.documento_id == 'recPonto1'
    assert r.colaborador == ReferenciaCanonica('FUNCIONARIO', 'recFunc1')
    assert r.data == datetime.date(2026, 6, 10)
    assert r.possui_marcacao is True
    assert len(r.batidas) == 2


def test_registro_sem_batida_vira_possui_marcacao_falso():
    leitor = _LeitorFake([
        {'id': 'recPonto2', 'fields': {F_FUNC: ['recFunc1'], F_DATA: '2026-06-11'}},
    ])
    fonte = FonteRegistrosPontoAirtableShadow(leitor)
    registros = fonte.listar_no_intervalo(datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))
    assert len(registros) == 1
    assert registros[0].possui_marcacao is False
    assert registros[0].batidas == ()


def test_registro_sem_funcionario_vinculado_e_descartado():
    leitor = _LeitorFake([
        {'id': 'recPonto3', 'fields': {F_DATA: '2026-06-10', F_ENTRADA: '2026-06-10T08:00:00-03:00'}},
    ])
    fonte = FonteRegistrosPontoAirtableShadow(leitor)
    registros = fonte.listar_no_intervalo(datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))
    assert registros == ()


def test_registro_com_funcionario_multiplo_e_descartado():
    """Vínculo N:1 nunca esperado pelo schema real -- dado corrompido,
    descartado (nunca inventa qual dos N é o certo)."""
    leitor = _LeitorFake([
        {'id': 'recPonto4', 'fields': {
            F_FUNC: ['recFunc1', 'recFunc2'], F_DATA: '2026-06-10',
            F_ENTRADA: '2026-06-10T08:00:00-03:00',
        }},
    ])
    fonte = FonteRegistrosPontoAirtableShadow(leitor)
    assert fonte.listar_no_intervalo(datetime.date(2026, 6, 1), datetime.date(2026, 6, 30)) == ()


def test_registro_sem_data_valida_e_descartado():
    leitor = _LeitorFake([
        {'id': 'recPonto5', 'fields': {F_FUNC: ['recFunc1'], F_DATA: 'nao-e-data'}},
    ])
    fonte = FonteRegistrosPontoAirtableShadow(leitor)
    assert fonte.listar_no_intervalo(datetime.date(2026, 6, 1), datetime.date(2026, 6, 30)) == ()


def test_usa_table_id_e_campos_corretos_sempre_com_filtro_de_intervalo():
    leitor = _LeitorFake([])
    fonte = FonteRegistrosPontoAirtableShadow(leitor)
    fonte.listar_no_intervalo(datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))
    assert len(leitor.chamadas) == 1
    chamada = leitor.chamadas[0]
    assert chamada['table_id'] == AT_PONTO
    assert F_FUNC in chamada['fields'] and F_DATA in chamada['fields']
    assert chamada['filter_by_formula'] is not None


def test_leitor_e_usado_apenas_via_listar_registros_get_only():
    """`FonteRegistrosPontoAirtableShadow` nunca chama nenhum método de
    escrita -- a própria classe do leitor (`LeitorAirtableSomenteLeitura`)
    só tem GET, mas este teste garante que o adapter novo também nunca
    tenta invocar algo além de `listar_registros`."""
    leitor = _LeitorFake([])
    assert not hasattr(leitor, 'criar_registro')
    assert not hasattr(leitor, 'atualizar_registro')
    fonte = FonteRegistrosPontoAirtableShadow(leitor)
    fonte.listar_no_intervalo(datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))
    assert leitor.chamadas  # só a chamada de leitura aconteceu
