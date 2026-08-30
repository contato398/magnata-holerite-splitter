"""Testes do adapter read-only de colaboradores ESPERADOS por cliente
(ADENDO DE CONTINUIDADE, item 3) -- mesmo padrão de
`test_airtable_vinculos_prestacao.py`, direção inversa."""
from pathlib import Path

import pytest

from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.documental.importacao_lote.adapters.airtable_colaboradores_esperados_prestacao import (
    F_FUNC_STATUS,
    STATUS_FUNCIONARIO_ATIVO,
    FonteColaboradoresEsperadosPrestacaoAirtableShadow,
)
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import TABLE_FUNC
from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import (
    F_FUNC_LOCAIS,
    F_LOCAL_CLIENTE,
    TABLE_LOCAIS,
)

_CONTEXTO = ContextoCicloPrestacao(competencia_base=(2026, 7))
_CLIENTE = ReferenciaCanonica('CLIENTE', 'cliente-1')


class LeitorFake:
    def __init__(self, funcionarios=(), locais=()):
        self._funcionarios = list(funcionarios)
        self._locais = list(locais)
        self.chamadas = []

    def listar_registros(self, table_id, fields, filter_by_formula=None):
        self.chamadas.append((table_id, tuple(fields), filter_by_formula))
        return self._funcionarios if table_id == TABLE_FUNC else self._locais


def _fonte(leitor):
    return FonteColaboradoresEsperadosPrestacaoAirtableShadow(leitor)


def test_cliente_sem_nenhum_local_devolve_tupla_vazia():
    leitor = LeitorFake(locais=({'id': 'local-x', 'fields': {F_LOCAL_CLIENTE: ['cliente-outro']}},))
    resultado = _fonte(leitor).colaboradores_esperados_para(_CLIENTE, _CONTEXTO)
    assert resultado == ()


def test_funcionario_ativo_do_local_do_cliente_e_esperado():
    leitor = LeitorFake(
        locais=({'id': 'local-1', 'fields': {F_LOCAL_CLIENTE: ['cliente-1']}},),
        funcionarios=({'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1'], F_FUNC_STATUS: 'Ativo'}},),
    )
    resultado = _fonte(leitor).colaboradores_esperados_para(_CLIENTE, _CONTEXTO)
    assert resultado == (ReferenciaCanonica('COLABORADOR', 'func-1'),)


def test_funcionario_inativo_nunca_e_esperado():
    leitor = LeitorFake(
        locais=({'id': 'local-1', 'fields': {F_LOCAL_CLIENTE: ['cliente-1']}},),
        funcionarios=(
            {'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1'], F_FUNC_STATUS: 'Ativo'}},
            {'id': 'func-2', 'fields': {F_FUNC_LOCAIS: ['local-1'], F_FUNC_STATUS: 'Inativo'}},
        ),
    )
    resultado = _fonte(leitor).colaboradores_esperados_para(_CLIENTE, _CONTEXTO)
    assert resultado == (ReferenciaCanonica('COLABORADOR', 'func-1'),)


def test_funcionario_de_outro_cliente_nunca_e_esperado():
    leitor = LeitorFake(
        locais=(
            {'id': 'local-1', 'fields': {F_LOCAL_CLIENTE: ['cliente-1']}},
            {'id': 'local-2', 'fields': {F_LOCAL_CLIENTE: ['cliente-outro']}},
        ),
        funcionarios=(
            {'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1'], F_FUNC_STATUS: 'Ativo'}},
            {'id': 'func-2', 'fields': {F_FUNC_LOCAIS: ['local-2'], F_FUNC_STATUS: 'Ativo'}},
        ),
    )
    resultado = _fonte(leitor).colaboradores_esperados_para(_CLIENTE, _CONTEXTO)
    assert resultado == (ReferenciaCanonica('COLABORADOR', 'func-1'),)


def test_funcionario_vinculado_a_2_locais_do_mesmo_cliente_nunca_duplica():
    leitor = LeitorFake(
        locais=(
            {'id': 'local-1', 'fields': {F_LOCAL_CLIENTE: ['cliente-1']}},
            {'id': 'local-2', 'fields': {F_LOCAL_CLIENTE: ['cliente-1']}},
        ),
        funcionarios=({'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1', 'local-2'], F_FUNC_STATUS: 'Ativo'}},),
    )
    resultado = _fonte(leitor).colaboradores_esperados_para(_CLIENTE, _CONTEXTO)
    assert resultado == (ReferenciaCanonica('COLABORADOR', 'func-1'),)


def test_resultado_e_sempre_ordenado_deterministico():
    leitor = LeitorFake(
        locais=({'id': 'local-1', 'fields': {F_LOCAL_CLIENTE: ['cliente-1']}},),
        funcionarios=(
            {'id': 'func-b', 'fields': {F_FUNC_LOCAIS: ['local-1'], F_FUNC_STATUS: 'Ativo'}},
            {'id': 'func-a', 'fields': {F_FUNC_LOCAIS: ['local-1'], F_FUNC_STATUS: 'Ativo'}},
        ),
    )
    resultado = _fonte(leitor).colaboradores_esperados_para(_CLIENTE, _CONTEXTO)
    assert resultado == (ReferenciaCanonica('COLABORADOR', 'func-a'), ReferenciaCanonica('COLABORADOR', 'func-b'))


def test_cliente_invalido_e_rejeitado():
    with pytest.raises(ValueError):
        _fonte(LeitorFake()).colaboradores_esperados_para(ReferenciaCanonica('COLABORADOR', 'x'), _CONTEXTO)


def test_status_ativo_confirma_valor_do_legado():
    assert STATUS_FUNCIONARIO_ATIVO == 'Ativo'


def test_adapter_nunca_solicita_campos_de_identidade_pessoal():
    """AST, não busca textual crua -- a PRÓPRIA docstring do módulo cita
    'Nome Completo'/'CPF' em prosa (para explicar o least-privilege);
    o que não pode existir é o literal de código, fora de docstring,
    passado a `fields=[...]` num `listar_registros`."""
    import ast

    caminho = Path('magnata_os/documental/importacao_lote/adapters/airtable_colaboradores_esperados_prestacao.py')
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


def test_adapter_usa_somente_superficie_read_only():
    caminho = Path('magnata_os/documental/importacao_lote/adapters/airtable_colaboradores_esperados_prestacao.py')
    conteudo = caminho.read_text(encoding='utf-8').lower()
    assert 'listar_registros' in conteudo
    assert all(termo not in conteudo for termo in ('requests.post', 'patch(', 'delete('))


def test_resultado_nao_expoe_pii_ou_payload():
    leitor = LeitorFake(
        locais=({'id': 'local-1', 'fields': {F_LOCAL_CLIENTE: ['cliente-1']}},),
        funcionarios=({'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1'], F_FUNC_STATUS: 'Ativo'}},),
    )
    resultado = _fonte(leitor).colaboradores_esperados_para(_CLIENTE, _CONTEXTO)
    representacao = repr(resultado).lower()
    assert all(termo not in representacao for termo in ('nome', 'cpf', 'cnpj', 'email', 'payload', 'conteudo_bruto'))
