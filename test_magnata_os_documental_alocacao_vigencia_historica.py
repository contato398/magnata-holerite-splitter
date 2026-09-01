"""Testes de `magnata_os/documental/alocacao/` (missão "IMPLEMENTAÇÃO
ESTRUTURAL DA ENTIDADE alocacao COM VIGÊNCIA HISTÓRICA"). Cobrem: schema
temporal via `RepositorioAlocacaoSQLite` (persistência REAL, arquivo
local -- nunca fake/mock de domínio), aritmética pura de `temporal.py`,
a composição de prioridade histórica-sobre-Airtable, e a integração real
com o corredor (`ExecucaoCorredorReadonly`) via
`fonte_unidade_posto_override`, provando o caso equivalente ao SKY
Junho/2026 desbloqueado."""
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

from magnata_os.classificacao.competencia_esperada_prestacao import (
    ContextoCicloPrestacao,
    REFERENCIA_CLIENTE_SKY_TATUI,
)
from magnata_os.classificacao.contratos import DimensaoResolucao, EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.fonte_unidade_posto_com_prioridade_historica import (
    FonteUnidadePostoPrestacaoComPrioridadeHistorica,
)
from magnata_os.classificacao.resolucao_documento_prestacao import EstadoCorredorDocumentoPrestacao
from magnata_os.documental.alocacao.adapters.sqlite_alocacao import RepositorioAlocacaoSQLite
from magnata_os.documental.alocacao.resolucao import MOTIVO_ALOCACAO_NAO_REGISTRADA
from magnata_os.documental.alocacao.temporal import (
    SobreposicaoAlocacaoError,
    SobreposicaoVinculoError,
    intervalo_do_mes,
    intervalos_se_sobrepoem,
)
from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import (
    F_FUNC_LOCAIS,
    F_LOCAL_CLIENTE,
    TABLE_FUNC,
    TABLE_LOCAIS,
)
from magnata_os.documental.importacao_lote.composicao_corredor_readonly import ExecucaoCorredorReadonly
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario

_COLABORADOR_1 = 'func-aloc-1'
_VINCULO_1 = 'vinculo-1'
_POSTO_A = 'posto-A'
_POSTO_B = 'posto-B'
_COMPETENCIA_JUNHO = ReferenciaCanonica('COMPETENCIA', '2026-06')
_COMPETENCIA_JULHO = ReferenciaCanonica('COMPETENCIA', '2026-07')


@pytest.fixture
def repo():
    with tempfile.TemporaryDirectory() as tmp:
        r = RepositorioAlocacaoSQLite(Path(tmp) / 'alocacao_teste.sqlite3')
        yield r
        r.fechar()


# ============================================================================
# temporal.py -- aritmética pura
# ============================================================================

def test_intervalo_do_mes_junho_2026():
    assert intervalo_do_mes(2026, 6) == (date(2026, 6, 1), date(2026, 6, 30))


def test_intervalos_se_sobrepoem_com_fim_aberto():
    assert intervalos_se_sobrepoem(date(2026, 1, 1), None, date(2026, 6, 1), date(2026, 6, 30))


def test_intervalos_nao_se_sobrepoem_quando_disjuntos():
    assert not intervalos_se_sobrepoem(date(2026, 1, 1), date(2026, 3, 31), date(2026, 6, 1), date(2026, 6, 30))


def test_intervalos_se_tocam_na_borda_sao_sobrepostos_inclusive():
    assert intervalos_se_sobrepoem(date(2026, 1, 1), date(2026, 6, 1), date(2026, 6, 1), date(2026, 6, 30))


# ============================================================================
# RepositorioAlocacaoSQLite -- persistência real (Fase 8, casos 1-13)
# ============================================================================

def test_1_alocacao_aberta_valida_e_encontrada_por_data(repo):
    repo.registrar_vinculo(_VINCULO_1, _COLABORADOR_1, date(2026, 1, 1))
    repo.registrar_alocacao('aloc-1', _VINCULO_1, _POSTO_A, date(2026, 1, 1))  # vigente_ate=None
    postos = repo.postos_vigentes_em(_VINCULO_1, date(2026, 6, 1), date(2026, 6, 30))
    assert postos == (_POSTO_A,)


def test_2_alocacao_encerrada_nao_aparece_apos_o_fim(repo):
    repo.registrar_vinculo(_VINCULO_1, _COLABORADOR_1, date(2026, 1, 1))
    repo.registrar_alocacao('aloc-1', _VINCULO_1, _POSTO_A, date(2026, 1, 1), date(2026, 5, 31))
    postos_durante = repo.postos_vigentes_em(_VINCULO_1, date(2026, 3, 1), date(2026, 3, 31))
    postos_depois = repo.postos_vigentes_em(_VINCULO_1, date(2026, 6, 1), date(2026, 6, 30))
    assert postos_durante == (_POSTO_A,)
    assert postos_depois == ()


def test_3_consulta_dentro_da_vigencia_resolve(repo):
    repo.registrar_vinculo(_VINCULO_1, _COLABORADOR_1, date(2026, 1, 1))
    repo.registrar_alocacao('aloc-1', _VINCULO_1, _POSTO_A, date(2026, 6, 1), date(2026, 6, 30))
    resultado = repo.resolver_unidade_posto(ReferenciaCanonica('COLABORADOR', _COLABORADOR_1), _COMPETENCIA_JUNHO)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert resultado.valores_confirmados == (ReferenciaCanonica('UNIDADE_POSTO', _POSTO_A),)


def test_4_consulta_fora_da_vigencia_nao_encontra(repo):
    repo.registrar_vinculo(_VINCULO_1, _COLABORADOR_1, date(2026, 1, 1))
    repo.registrar_alocacao('aloc-1', _VINCULO_1, _POSTO_A, date(2026, 6, 1), date(2026, 6, 30))
    resultado = repo.resolver_unidade_posto(ReferenciaCanonica('COLABORADOR', _COLABORADOR_1), _COMPETENCIA_JULHO)
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


def test_5_transferencia_de_posto_fecha_vigencia_anterior_e_abre_nova(repo):
    repo.registrar_vinculo(_VINCULO_1, _COLABORADOR_1, date(2026, 1, 1))
    repo.registrar_alocacao('aloc-1', _VINCULO_1, _POSTO_A, date(2026, 1, 1), date(2026, 6, 14))
    repo.registrar_alocacao('aloc-2', _VINCULO_1, _POSTO_B, date(2026, 6, 15))
    assert repo.postos_vigentes_em(_VINCULO_1, date(2026, 3, 1), date(2026, 3, 31)) == (_POSTO_A,)
    assert repo.postos_vigentes_em(_VINCULO_1, date(2026, 7, 1), date(2026, 7, 31)) == (_POSTO_B,)


def test_6_duas_alocacoes_sequenciais_sem_sobreposicao_sao_aceitas(repo):
    repo.registrar_vinculo(_VINCULO_1, _COLABORADOR_1, date(2026, 1, 1))
    repo.registrar_alocacao('aloc-1', _VINCULO_1, _POSTO_A, date(2026, 1, 1), date(2026, 3, 31))
    repo.registrar_alocacao('aloc-2', _VINCULO_1, _POSTO_A, date(2026, 4, 1), date(2026, 6, 30))
    postos = repo.postos_vigentes_em(_VINCULO_1, date(2026, 1, 1), date(2026, 12, 31))
    # Consulta crua nunca dedupa (2 linhas reais, 2 vigencias distintas do
    # MESMO posto) -- dedupe acontece 1 nivel acima, em
    # resolver_unidade_posto_via_alocacao (via set()), nunca aqui.
    assert postos == (_POSTO_A, _POSTO_A)
    resultado = repo.resolver_unidade_posto(ReferenciaCanonica('COLABORADOR', _COLABORADOR_1), _COMPETENCIA_JUNHO)
    assert resultado.valores_confirmados == (ReferenciaCanonica('UNIDADE_POSTO', _POSTO_A),)


def test_7_sobreposicao_invalida_mesmo_posto_e_rejeitada(repo):
    repo.registrar_vinculo(_VINCULO_1, _COLABORADOR_1, date(2026, 1, 1))
    repo.registrar_alocacao('aloc-1', _VINCULO_1, _POSTO_A, date(2026, 1, 1), date(2026, 6, 30))
    with pytest.raises(SobreposicaoAlocacaoError):
        repo.registrar_alocacao('aloc-2', _VINCULO_1, _POSTO_A, date(2026, 6, 1), date(2026, 12, 31))


def test_7b_sobreposicao_de_vinculo_e_rejeitada(repo):
    repo.registrar_vinculo(_VINCULO_1, _COLABORADOR_1, date(2026, 1, 1))
    with pytest.raises(SobreposicaoVinculoError):
        repo.registrar_vinculo('vinculo-2', _COLABORADOR_1, date(2026, 3, 1))


def test_7c_rateio_postos_diferentes_no_mesmo_periodo_e_permitido(repo):
    """Reconciliação registrada na migration 0001: sobreposição entre
    POSTOS DIFERENTES do mesmo vínculo é rateio legítimo, nunca
    rejeitada."""
    repo.registrar_vinculo(_VINCULO_1, _COLABORADOR_1, date(2026, 1, 1))
    repo.registrar_alocacao('aloc-1', _VINCULO_1, _POSTO_A, date(2026, 6, 1), date(2026, 6, 30))
    repo.registrar_alocacao('aloc-2', _VINCULO_1, _POSTO_B, date(2026, 6, 1), date(2026, 6, 30))
    postos = repo.postos_vigentes_em(_VINCULO_1, date(2026, 6, 1), date(2026, 6, 30))
    assert postos == (_POSTO_A, _POSTO_B)


def test_8_mudanca_no_meio_do_mes_preserva_os_2_postos_da_competencia(repo):
    repo.registrar_vinculo(_VINCULO_1, _COLABORADOR_1, date(2026, 1, 1))
    repo.registrar_alocacao('aloc-1', _VINCULO_1, _POSTO_A, date(2026, 1, 1), date(2026, 6, 14))
    repo.registrar_alocacao('aloc-2', _VINCULO_1, _POSTO_B, date(2026, 6, 15))
    resultado = repo.resolver_unidade_posto(ReferenciaCanonica('COLABORADOR', _COLABORADOR_1), _COMPETENCIA_JUNHO)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA
    assert set(v.entidade_id for v in resultado.valores_confirmados) == {_POSTO_A, _POSTO_B}


def test_9_colaborador_sem_historico_nunca_encontrado(repo):
    resultado = repo.resolver_unidade_posto(ReferenciaCanonica('COLABORADOR', 'func-fantasma'), _COMPETENCIA_JUNHO)
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert MOTIVO_ALOCACAO_NAO_REGISTRADA in resultado.motivos


def test_10_colaborador_de_outro_vinculo_nunca_vaza_posto_errado(repo):
    repo.registrar_vinculo(_VINCULO_1, _COLABORADOR_1, date(2026, 1, 1))
    repo.registrar_alocacao('aloc-1', _VINCULO_1, _POSTO_A, date(2026, 1, 1))
    repo.registrar_vinculo('vinculo-outro', 'func-outro', date(2026, 1, 1))
    repo.registrar_alocacao('aloc-outro', 'vinculo-outro', _POSTO_B, date(2026, 1, 1))
    resultado = repo.resolver_unidade_posto(ReferenciaCanonica('COLABORADOR', _COLABORADOR_1), _COMPETENCIA_JUNHO)
    assert resultado.valores_confirmados == (ReferenciaCanonica('UNIDADE_POSTO', _POSTO_A),)


def test_11_competencia_historica_resolve_igual_a_qualquer_outra(repo):
    repo.registrar_vinculo(_VINCULO_1, _COLABORADOR_1, date(2020, 1, 1))
    repo.registrar_alocacao('aloc-1', _VINCULO_1, _POSTO_A, date(2020, 1, 1), date(2020, 12, 31))
    resultado = repo.resolver_unidade_posto(
        ReferenciaCanonica('COLABORADOR', _COLABORADOR_1), ReferenciaCanonica('COMPETENCIA', '2020-06'))
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_12_competencia_corrente_com_vigente_ate_aberto_resolve(repo):
    repo.registrar_vinculo(_VINCULO_1, _COLABORADOR_1, date(2026, 1, 1))
    repo.registrar_alocacao('aloc-1', _VINCULO_1, _POSTO_A, date(2026, 1, 1))  # em aberto
    resultado = repo.resolver_unidade_posto(ReferenciaCanonica('COLABORADOR', _COLABORADOR_1), _COMPETENCIA_JULHO)
    assert resultado.estado == EstadoResolucaoDimensao.RESOLVIDA


def test_13_vinculo_existe_mas_sem_alocacao_e_ausencia_de_prova(repo):
    """Vínculo comprovado não basta -- sem Alocação registrada para a
    competência, é NAO_ENCONTRADA honesta, nunca inferida do vínculo."""
    repo.registrar_vinculo(_VINCULO_1, _COLABORADOR_1, date(2026, 1, 1))
    resultado = repo.resolver_unidade_posto(ReferenciaCanonica('COLABORADOR', _COLABORADOR_1), _COMPETENCIA_JUNHO)
    assert resultado.estado == EstadoResolucaoDimensao.NAO_ENCONTRADA


# ============================================================================
# FonteUnidadePostoPrestacaoComPrioridadeHistorica -- composição (Fase 5)
# ============================================================================

def test_prioridade_historica_nunca_consulta_corrente_quando_historica_resolve():
    fonte_historica = Mock()
    fonte_historica.resolver_unidade_posto.return_value = ReferenciaCanonica  # placeholder, sobrescrito abaixo
    resolucao_resolvida = repo_resolucao_resolvida()
    fonte_historica.resolver_unidade_posto.return_value = resolucao_resolvida
    fonte_corrente = Mock()

    composta = FonteUnidadePostoPrestacaoComPrioridadeHistorica(fonte_historica, fonte_corrente)
    resultado = composta.resolver_unidade_posto(ReferenciaCanonica('COLABORADOR', _COLABORADOR_1), _COMPETENCIA_JUNHO)

    assert resultado is resolucao_resolvida
    fonte_corrente.resolver_unidade_posto.assert_not_called()


def test_prioridade_historica_cai_para_corrente_quando_nao_encontrada():
    from magnata_os.classificacao.contratos import ResolucaoDimensao

    fonte_historica = Mock()
    fonte_historica.resolver_unidade_posto.return_value = ResolucaoDimensao(
        dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
    )
    resolucao_corrente = repo_resolucao_resolvida()
    fonte_corrente = Mock()
    fonte_corrente.resolver_unidade_posto.return_value = resolucao_corrente

    composta = FonteUnidadePostoPrestacaoComPrioridadeHistorica(fonte_historica, fonte_corrente)
    resultado = composta.resolver_unidade_posto(ReferenciaCanonica('COLABORADOR', _COLABORADOR_1), _COMPETENCIA_JUNHO)

    assert resultado is resolucao_corrente
    fonte_corrente.resolver_unidade_posto.assert_called_once()


def repo_resolucao_resolvida():
    from magnata_os.classificacao.contratos import ConfiancaResolucao, NivelConfianca, ResolucaoDimensao
    return ResolucaoDimensao(
        dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.RESOLVIDA,
        valores_confirmados=(ReferenciaCanonica('UNIDADE_POSTO', _POSTO_A),),
        confianca=ConfiancaResolucao(NivelConfianca.FORTE),
    )


# ============================================================================
# Integração real com o corredor (Fase 5/8 caso 14/15) -- caso equivalente
# ao SKY Junho/2026, agora DESBLOQUEADO pela fonte histórica.
# ============================================================================

def test_14_15_caso_equivalente_sky_junho_2026_desbloqueia_unidade_posto(repo):
    """Equivalente sintético ao segundo live real (SKY Tatuí, Junho/2026):
    ciclo base Julho, competência esperada Junho (regra SKY -1). Antes
    desta missão, UNIDADE_POSTO era SEMPRE NAO_ENCONTRADA para essa
    competência histórica (comprovado no live real) -- agora, com
    Alocação persistida cobrindo Junho, o documento avança de verdade."""
    func_id = 'func-sky-equivalente'
    cpf_texto = '111.222.333-44'
    cpf_digitos = '11122233344'

    repo.registrar_vinculo('vinculo-sky', func_id, date(2025, 1, 1))
    repo.registrar_alocacao('aloc-sky', 'vinculo-sky', 'posto-sky-residence', date(2026, 1, 1))

    def _listar_registros(**kwargs):
        table = kwargs.get('table_id')
        if table == TABLE_FUNC:
            return [{'id': func_id, 'fields': {F_FUNC_LOCAIS: ['local-sky']}}]
        if table == TABLE_LOCAIS:
            return [{'id': 'local-sky', 'fields': {F_LOCAL_CLIENTE: [REFERENCIA_CLIENTE_SKY_TATUI.entidade_id]}}]
        return []

    leitor = Mock()
    leitor.listar_registros.side_effect = _listar_registros
    leitor.listar_clientes.return_value = []

    fonte_corrente_fake = Mock()
    fonte_corrente_fake.resolver_unidade_posto.return_value = None  # nunca deveria ser chamada

    execucao = ExecucaoCorredorReadonly(
        leitor, ContextoCicloPrestacao((2026, 7)), cliente_do_ciclo=REFERENCIA_CLIENTE_SKY_TATUI,
        fonte_unidade_posto_override=FonteUnidadePostoPrestacaoComPrioridadeHistorica(repo, fonte_corrente_fake),
    )
    texto = f'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 06/2026\nCPF: {cpf_texto}'
    resultados = execucao.processar_documento(
        'doc-hol-sky-aloc', 'd' * 64, texto=texto,
        candidatos_colaborador=[CandidatoFuncionario(func_id=func_id, cpf=cpf_digitos, nome_normalizado='SINTETICO')],
    )
    resultado = resultados[0].resultado_corredor
    dimensoes = {r.dimensao: r for r in resultado.resolucao_semantica.resolucoes}

    # O achado central desta missão: UNIDADE_POSTO agora resolve para
    # competência histórica, com prova real de vigência -- nunca mais
    # NAO_ENCONTRADA só por falta de fonte.
    assert dimensoes[DimensaoResolucao.UNIDADE_POSTO].estado == EstadoResolucaoDimensao.RESOLVIDA
    assert dimensoes[DimensaoResolucao.UNIDADE_POSTO].valores_confirmados == (
        ReferenciaCanonica('UNIDADE_POSTO', 'posto-sky-residence'),
    )
    # O documento agora AVANÇA de verdade (RESOLVIDO_E_AVANCOU), nunca
    # mais preso em REVISAO_NECESSARIA só pelo gap de vigência.
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
    assert len(resultados[0].itens_inventario) == 1
    # A fonte corrente (fallback) nunca foi consultada -- a histórica
    # resolveu sozinha.
    fonte_corrente_fake.resolver_unidade_posto.assert_not_called()


def test_sem_alocacao_persistida_cai_no_fallback_airtable_honesto():
    """Sem nenhuma Alocação registrada (colaborador não coberto pela
    migração/captura ainda), a composição cai para o Airtable-shadow --
    que, sem `competencia_snapshot_comprovada` para a competência exata,
    continua honestamente NAO_ENCONTRADA (comportamento idêntico ao
    pré-existente, provando que nada regrediu quando não há dado novo)."""
    func_id = 'func-sem-aloc'
    leitor = Mock()
    leitor.listar_registros.side_effect = lambda **kwargs: (
        [{'id': func_id, 'fields': {F_FUNC_LOCAIS: ['local-sky']}}] if kwargs.get('table_id') == TABLE_FUNC else []
    )
    leitor.listar_clientes.return_value = []

    repo_vazio = Mock()
    from magnata_os.classificacao.contratos import ResolucaoDimensao
    repo_vazio.resolver_unidade_posto.return_value = ResolucaoDimensao(
        dimensao=DimensaoResolucao.UNIDADE_POSTO, estado=EstadoResolucaoDimensao.NAO_ENCONTRADA,
    )

    from magnata_os.documental.importacao_lote.adapters.airtable_unidade_posto_prestacao import (
        FonteUnidadePostoPrestacaoAirtableShadow,
    )
    fonte_airtable = FonteUnidadePostoPrestacaoAirtableShadow(leitor, competencia_snapshot_comprovada=None)

    execucao = ExecucaoCorredorReadonly(
        leitor, ContextoCicloPrestacao((2026, 7)), cliente_do_ciclo=REFERENCIA_CLIENTE_SKY_TATUI,
        fonte_unidade_posto_override=FonteUnidadePostoPrestacaoComPrioridadeHistorica(repo_vazio, fonte_airtable),
    )
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 06/2026\nCPF: 111.222.333-44'
    resultados = execucao.processar_documento(
        'doc-hol-sem-aloc', 'e' * 64, texto=texto,
        candidatos_colaborador=[CandidatoFuncionario(func_id=func_id, cpf='11122233344', nome_normalizado='SINTETICO')],
    )
    resultado = resultados[0].resultado_corredor
    dimensoes = {r.dimensao: r for r in resultado.resolucao_semantica.resolucoes}
    assert dimensoes[DimensaoResolucao.UNIDADE_POSTO].estado == EstadoResolucaoDimensao.NAO_ENCONTRADA
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.REVISAO_NECESSARIA


def test_override_none_preserva_comportamento_anterior_exato():
    """Sem `fonte_unidade_posto_override` (default), o comportamento é
    IDÊNTICO ao já provado pelo teste pré-existente
    `test_sky_ciclo_base_julho_snapshot_comprovado_julho_unidade_posto_junho_nao_encontrada`
    -- prova de não-regressão desta missão sobre a composição real."""
    leitor = Mock()
    leitor.listar_registros.side_effect = lambda **kwargs: (
        [{'id': 'func-1', 'fields': {F_FUNC_LOCAIS: ['local-1']}}] if kwargs.get('table_id') == TABLE_FUNC else []
    )
    leitor.listar_clientes.return_value = []
    execucao = ExecucaoCorredorReadonly(
        leitor, ContextoCicloPrestacao((2026, 7)), competencia_snapshot_comprovada=(2026, 7),
        cliente_do_ciclo=REFERENCIA_CLIENTE_SKY_TATUI,
    )
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 06/2026\nCPF: 111.222.333-44'
    resultados = execucao.processar_documento(
        'doc-hol-sky-regressao', 'f' * 64, texto=texto,
        candidatos_colaborador=[CandidatoFuncionario(func_id='func-1', cpf='11122233344', nome_normalizado='JOAO')],
    )
    resultado = resultados[0].resultado_corredor
    dimensoes = {r.dimensao: r.estado for r in resultado.resolucao_semantica.resolucoes}
    assert dimensoes[DimensaoResolucao.UNIDADE_POSTO] == EstadoResolucaoDimensao.NAO_ENCONTRADA
