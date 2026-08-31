"""Testes de `airtable_unidade_posto_prestacao.py` (missão "MESCLAR
PR #107 + CONSTRUIR OS DOIS ADAPTERS REAIS QUE BLOQUEIAM A PRIMEIRA
VALIDAÇÃO LIVE"). Mesmo padrão de `test_airtable_vinculos_prestacao.py`
-- nenhum acesso Airtable real, só `LeitorFake` local."""
from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.vinculo_unidade_prestacao import (
    MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA,
    resolver_unidade_posto_validado,
)
from magnata_os.documental.importacao_lote.adapters.airtable_leitura import TABLE_FUNC
from magnata_os.documental.importacao_lote.adapters.airtable_unidade_posto_prestacao import (
    FonteUnidadePostoPrestacaoAirtableShadow,
)
from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import F_FUNC_LOCAIS

_COMPETENCIA_CORRENTE = ReferenciaCanonica('COMPETENCIA', '2026-07')
_COMPETENCIA_HISTORICA = ReferenciaCanonica('COMPETENCIA', '2025-01')
_COLABORADOR = ReferenciaCanonica('COLABORADOR', 'func-1')


class LeitorFake:
    def __init__(self, funcionarios=()):
        self._funcionarios = list(funcionarios)
        self.chamadas = []

    def listar_registros(self, table_id, fields, filter_by_formula=None):
        self.chamadas.append((table_id, tuple(fields), filter_by_formula))
        return self._funcionarios if table_id == TABLE_FUNC else []


def _fonte(leitor, competencia_base=(2026, 7)):
    return FonteUnidadePostoPrestacaoAirtableShadow(leitor, ContextoCicloPrestacao(competencia_base))


def test_colaborador_com_1_posto_e_resolvido():
    leitor = LeitorFake(funcionarios=({'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1']}},))
    resultado = resolver_unidade_posto_validado(_fonte(leitor), _COLABORADOR, _COMPETENCIA_CORRENTE)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (ReferenciaCanonica('UNIDADE_POSTO', 'local-1'),)
    assert leitor.chamadas[0][0] == TABLE_FUNC


def test_colaborador_com_2_postos_legitimos_cardinalidade_preservada():
    leitor = LeitorFake(funcionarios=({'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-a', 'local-b']}},))
    resultado = resolver_unidade_posto_validado(_fonte(leitor), _COLABORADOR, _COMPETENCIA_CORRENTE)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert set(resultado.valores_confirmados) == {
        ReferenciaCanonica('UNIDADE_POSTO', 'local-a'), ReferenciaCanonica('UNIDADE_POSTO', 'local-b'),
    }
    assert len(resultado.valores_confirmados) == 2  # nunca colapsado a 1


def test_colaborador_sem_local_vinculado_nao_encontrada():
    leitor = LeitorFake(funcionarios=({'id': 'func-1', 'fields': {}},))
    resultado = resolver_unidade_posto_validado(_fonte(leitor), _COLABORADOR, _COMPETENCIA_CORRENTE)
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_competencia_historica_sem_vigencia_nunca_resolve():
    """Regra pétrea: schema sem campo de vigência -- vínculo/posto
    corrente nunca prova histórico (adendo pré-merge ao PR #106)."""
    leitor = LeitorFake(funcionarios=({'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1']}},))
    resultado = resolver_unidade_posto_validado(_fonte(leitor), _COLABORADOR, _COMPETENCIA_HISTORICA)
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA in resultado.motivos
    # Nunca sequer consulta o Airtable para uma competência sem vigência.
    assert leitor.chamadas == []


def test_competencia_corrente_configurada_diferente_ainda_resolve_para_a_propria_corrente():
    leitor = LeitorFake(funcionarios=({'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1']}},))
    fonte = _fonte(leitor, competencia_base=(2026, 6))
    competencia_junho = ReferenciaCanonica('COMPETENCIA', '2026-06')
    resultado = resolver_unidade_posto_validado(fonte, _COLABORADOR, competencia_junho)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_adapter_atravessa_resolver_unidade_posto_validado_como_qualquer_fonte_fake():
    """`FonteUnidadePostoPrestacaoAirtableShadow` implementa o mesmo
    formato duck-typed usado pelos fakes puro-Python dos testes do
    corredor -- o validador genérico (`resolver_unidade_posto_
    validado`) nunca precisa saber que este é o adapter real."""
    leitor = LeitorFake(funcionarios=({'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1']}},))
    resultado = resolver_unidade_posto_validado(_fonte(leitor), _COLABORADOR, _COMPETENCIA_CORRENTE)
    assert resultado.dimensao.value == 'UNIDADE_POSTO'
