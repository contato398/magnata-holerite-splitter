"""Testes de `airtable_unidade_posto_prestacao.py` (missão "MESCLAR
PR #107 + CONSTRUIR OS DOIS ADAPTERS REAIS..."; corrigido pelo "ADENDO
PRÉ-MERGE — PR #108 — CORRIGIR TEMPORALIDADE DO SNAPSHOT"). Mesmo
padrão de `test_airtable_vinculos_prestacao.py` -- nenhum acesso
Airtable real, só `LeitorFake` local.

Casos A-E mapeados 1:1 ao §18 do adendo."""
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

_COMPETENCIA_JULHO = ReferenciaCanonica('COMPETENCIA', '2026-07')  # ciclo-base SKY
_COMPETENCIA_JUNHO = ReferenciaCanonica('COMPETENCIA', '2026-06')  # competência documental SKY (-1)
_COLABORADOR = ReferenciaCanonica('COLABORADOR', 'func-1')


class LeitorFake:
    def __init__(self, funcionarios=()):
        self._funcionarios = list(funcionarios)
        self.chamadas = []

    def listar_registros(self, table_id, fields, filter_by_formula=None):
        self.chamadas.append((table_id, tuple(fields), filter_by_formula))
        return self._funcionarios if table_id == TABLE_FUNC else []


def _fonte(leitor, competencia_snapshot_comprovada=None):
    return FonteUnidadePostoPrestacaoAirtableShadow(leitor, competencia_snapshot_comprovada)


# --- Caso A: ciclo sendo processado != prova temporal ---

def test_caso_a_ciclo_processado_nunca_e_prova_de_vigencia_do_snapshot():
    """Sem `competencia_snapshot_comprovada`, o fato de o runner estar
    processando uma competência (mesmo que igual à pedida) NUNCA basta
    -- a única coisa que decide é a vigência EXPLICITAMENTE comprovada,
    nunca uma competência de ciclo/processamento."""
    leitor = LeitorFake(funcionarios=({'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1']}},))
    fonte = _fonte(leitor)  # nenhuma vigência comprovada informada
    resultado = resolver_unidade_posto_validado(fonte, _COLABORADOR, _COMPETENCIA_JULHO)
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA in resultado.motivos
    assert leitor.chamadas == []  # nunca sequer consulta o Airtable


# --- Caso B: snapshot sem vigência + competência histórica -> NÃO RESOLVIDA ---

def test_caso_b_competencia_historica_sem_vigencia_nunca_resolve():
    leitor = LeitorFake(funcionarios=({'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1']}},))
    fonte = _fonte(leitor, competencia_snapshot_comprovada=(2026, 7))
    competencia_historica = ReferenciaCanonica('COMPETENCIA', '2025-01')
    resultado = resolver_unidade_posto_validado(fonte, _COLABORADOR, competencia_historica)
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA in resultado.motivos


# --- Caso C: SKY base julho -> competência documental junho -> NÃO RESOLVIDA sem prova ---

def test_caso_c_sky_tatui_ciclo_base_julho_competencia_documental_junho_nunca_resolve():
    """Caso obrigatório do adendo (§5): o snapshot corrente de
    Funcionário→Local NÃO prova Junho só porque o ciclo-base (Julho)
    é a competência que o runner está processando -- mesmo com
    `competencia_snapshot_comprovada=(2026, 7)` (vigência comprovada
    só para Julho), pedir a resolução para Junho (a competência
    documental real, após a regra SKY -1) nunca resolve."""
    leitor = LeitorFake(funcionarios=({'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1']}},))
    fonte = _fonte(leitor, competencia_snapshot_comprovada=(2026, 7))
    resultado = resolver_unidade_posto_validado(fonte, _COLABORADOR, _COMPETENCIA_JUNHO)
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert MOTIVO_VINCULO_HISTORICO_SEM_VIGENCIA in resultado.motivos
    assert leitor.chamadas == []


# --- Caso D: referência temporal realmente comprovada -> RESOLVIDA ---

def test_caso_d_vigencia_comprovada_para_a_competencia_exata_resolve():
    leitor = LeitorFake(funcionarios=({'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1']}},))
    fonte = _fonte(leitor, competencia_snapshot_comprovada=(2026, 7))
    resultado = resolver_unidade_posto_validado(fonte, _COLABORADOR, _COMPETENCIA_JULHO)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (ReferenciaCanonica('UNIDADE_POSTO', 'local-1'),)


# --- Caso E: 2 postos comprovados -- cardinalidade preservada ---

def test_caso_e_dois_postos_comprovados_cardinalidade_preservada():
    leitor = LeitorFake(funcionarios=({'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-a', 'local-b']}},))
    fonte = _fonte(leitor, competencia_snapshot_comprovada=(2026, 7))
    resultado = resolver_unidade_posto_validado(fonte, _COLABORADOR, _COMPETENCIA_JULHO)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert set(resultado.valores_confirmados) == {
        ReferenciaCanonica('UNIDADE_POSTO', 'local-a'), ReferenciaCanonica('UNIDADE_POSTO', 'local-b'),
    }
    assert len(resultado.valores_confirmados) == 2  # nunca colapsado a 1


# --- Casos adicionais preservados ---

def test_colaborador_sem_local_vinculado_nao_encontrada():
    leitor = LeitorFake(funcionarios=({'id': 'func-1', 'fields': {}},))
    fonte = _fonte(leitor, competencia_snapshot_comprovada=(2026, 7))
    resultado = resolver_unidade_posto_validado(fonte, _COLABORADOR, _COMPETENCIA_JULHO)
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_adapter_atravessa_resolver_unidade_posto_validado_como_qualquer_fonte_fake():
    """`FonteUnidadePostoPrestacaoAirtableShadow` implementa o mesmo
    formato duck-typed usado pelos fakes puro-Python dos testes do
    corredor -- o validador genérico (`resolver_unidade_posto_
    validado`) nunca precisa saber que este é o adapter real."""
    leitor = LeitorFake(funcionarios=({'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1']}},))
    resultado = resolver_unidade_posto_validado(
        _fonte(leitor, competencia_snapshot_comprovada=(2026, 7)), _COLABORADOR, _COMPETENCIA_JULHO,
    )
    assert resultado.dimensao.value == 'UNIDADE_POSTO'
