"""Testes de `magnata_os/documental/alocacao/eventos.py` +
`captura.py` (missão "CAPTURA AUTOMÁTICA DE VÍNCULO E ALOCAÇÃO V1").
Persistência REAL via `RepositorioAlocacaoSQLite` (arquivo local, nunca
fake/mock de domínio) -- mesma disciplina já estabelecida em
`test_magnata_os_documental_alocacao_vigencia_historica.py`.

Cobre os 15 cenários da missão (Fase 8) + a integração real com o
corredor após uma sequência completa admissão -> alocação ->
transferência (Fase 9)."""
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock
from unittest.mock import Mock

import pytest

from magnata_os.classificacao.competencia_esperada_prestacao import ContextoCicloPrestacao
from magnata_os.classificacao.contratos import DimensaoResolucao, EstadoResolucaoDimensao, ReferenciaCanonica
from magnata_os.classificacao.resolucao_documento_prestacao import EstadoCorredorDocumentoPrestacao
from magnata_os.documental.alocacao.adapters.sqlite_alocacao import RepositorioAlocacaoSQLite
from magnata_os.documental.alocacao.captura import (
    aplicar_alocacao_encerrada,
    aplicar_alocacao_iniciada,
    aplicar_transferencia,
    aplicar_vinculo_encerrado,
    aplicar_vinculo_iniciado,
)
from magnata_os.documental.alocacao.eventos import (
    AlocacaoEncerrada,
    AlocacaoIniciada,
    ConflitoTemporalEventoError,
    EventoForaDeOrdemError,
    VinculoEncerrado,
    VinculoIniciado,
)
from magnata_os.documental.importacao_lote.adapters.airtable_vinculos_prestacao import (
    F_FUNC_LOCAIS,
    F_LOCAL_CLIENTE,
    TABLE_FUNC,
    TABLE_LOCAIS,
)
from magnata_os.documental.importacao_lote.composicao_corredor_readonly import ExecucaoCorredorReadonly
from magnata_os.documental.importacao_lote.contratos import CandidatoFuncionario

_COLAB = 'colab-captura-1'
_ORIGEM = 'holerite_data_admissao'


@pytest.fixture
def repo():
    with tempfile.TemporaryDirectory() as tmp:
        r = RepositorioAlocacaoSQLite(Path(tmp) / 'captura_teste.sqlite3')
        yield r
        r.fechar()


# ============================================================================
# eventos.py -- data efetiva obrigatória (caso 10)
# ============================================================================

def test_10_evento_sem_data_efetiva_falha_na_construcao():
    with pytest.raises(ValueError):
        VinculoIniciado(colaborador_id=_COLAB, data_efetiva=None, origem_evidencia=_ORIGEM)


def test_10b_evento_com_data_como_string_falha_na_construcao():
    with pytest.raises(ValueError):
        VinculoIniciado(colaborador_id=_COLAB, data_efetiva='2026-01-01', origem_evidencia=_ORIGEM)


def test_10c_evento_sem_colaborador_id_falha_na_construcao():
    with pytest.raises(ValueError):
        VinculoIniciado(colaborador_id='', data_efetiva=date(2026, 1, 1), origem_evidencia=_ORIGEM)


# ============================================================================
# Fase 8 -- cenários 1-9, 11-13
# ============================================================================

def test_1_primeira_admissao_cria_vinculo(repo):
    vinculo_id = aplicar_vinculo_iniciado(
        repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    recente = repo.vinculo_mais_recente_de(_COLAB)
    assert recente.id == vinculo_id
    assert recente.data_admissao == date(2026, 1, 1)
    assert recente.data_desligamento is None


def test_2_segunda_execucao_do_mesmo_evento_e_idempotente(repo):
    id1 = aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    id2 = aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    assert id1 == id2
    # nenhuma segunda linha criada -- só existe 1 vinculo para este colaborador
    assert repo.vinculo_mais_recente_de(_COLAB).id == id1


def test_3_primeira_alocacao(repo):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    aloc_id = aplicar_alocacao_iniciada(
        repo, AlocacaoIniciada(_COLAB, 'posto-A', date(2026, 1, 1), _ORIGEM))
    vinculo = repo.vinculo_mais_recente_de(_COLAB)
    recente = repo.alocacao_mais_recente_de(vinculo.id, 'posto-A')
    assert recente.id == aloc_id
    assert recente.vigente_ate is None


def test_4_troca_a_para_b(repo):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(_COLAB, 'posto-A', date(2026, 1, 1), _ORIGEM))
    aplicar_transferencia(repo, _COLAB, 'posto-A', 'posto-B', date(2026, 6, 15), _ORIGEM)

    vinculo = repo.vinculo_mais_recente_de(_COLAB)
    a = repo.alocacao_mais_recente_de(vinculo.id, 'posto-A')
    b = repo.alocacao_mais_recente_de(vinculo.id, 'posto-B')
    assert a.vigente_ate == date(2026, 6, 15)
    assert b.vigente_de == date(2026, 6, 15)
    assert b.vigente_ate is None


def test_5_rateio_a_mais_b(repo):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(_COLAB, 'posto-A', date(2026, 6, 1), _ORIGEM))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(_COLAB, 'posto-B', date(2026, 6, 1), _ORIGEM))
    vinculo = repo.vinculo_mais_recente_de(_COLAB)
    postos = repo.postos_vigentes_em(vinculo.id, date(2026, 6, 1), date(2026, 6, 30))
    assert set(postos) == {'posto-A', 'posto-B'}


def test_6_remocao_somente_de_a(repo):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(_COLAB, 'posto-A', date(2026, 1, 1), _ORIGEM))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(_COLAB, 'posto-B', date(2026, 1, 1), _ORIGEM))
    aplicar_alocacao_encerrada(repo, AlocacaoEncerrada(_COLAB, 'posto-A', date(2026, 6, 30), _ORIGEM))

    vinculo = repo.vinculo_mais_recente_de(_COLAB)
    postos = repo.postos_vigentes_em(vinculo.id, date(2026, 7, 1), date(2026, 7, 31))
    assert postos == ('posto-B',)  # A encerrado, B nunca afetado (rateio preservado)


def test_7_desligamento(repo):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    aplicar_vinculo_encerrado(repo, VinculoEncerrado(_COLAB, date(2026, 6, 30), _ORIGEM))
    recente = repo.vinculo_mais_recente_de(_COLAB)
    assert recente.data_desligamento == date(2026, 6, 30)


def test_8_readmissao_posterior_cria_novo_vinculo(repo):
    id1 = aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2025, 1, 1), _ORIGEM))
    aplicar_vinculo_encerrado(repo, VinculoEncerrado(_COLAB, date(2025, 6, 30), _ORIGEM))
    id2 = aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    assert id1 != id2  # nunca reaproveita o vinculo antigo
    recente = repo.vinculo_mais_recente_de(_COLAB)
    assert recente.id == id2
    assert recente.data_desligamento is None


def test_9_evento_fora_de_ordem_alocacao_antes_de_admissao_falha(repo):
    with pytest.raises(EventoForaDeOrdemError):
        aplicar_alocacao_iniciada(repo, AlocacaoIniciada(_COLAB, 'posto-A', date(2026, 1, 1), _ORIGEM))


def test_9b_evento_fora_de_ordem_encerramento_sem_vinculo_falha(repo):
    with pytest.raises(EventoForaDeOrdemError):
        aplicar_vinculo_encerrado(repo, VinculoEncerrado(_COLAB, date(2026, 1, 1), _ORIGEM))


def test_9c_alocacao_apos_desligamento_falha(repo):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    aplicar_vinculo_encerrado(repo, VinculoEncerrado(_COLAB, date(2026, 6, 30), _ORIGEM))
    with pytest.raises(EventoForaDeOrdemError):
        aplicar_alocacao_iniciada(repo, AlocacaoIniciada(_COLAB, 'posto-A', date(2026, 7, 1), _ORIGEM))


def test_11_posto_desconhecido_funciona_como_identidade_opaca(repo):
    """Nenhuma validação de "posto conhecido" existe (nem deveria --
    posto_id é identidade opaca, sem FK própria, mesma decisão já
    registrada na migration 0001). Um posto nunca visto antes é aceito
    normalmente."""
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    aloc_id = aplicar_alocacao_iniciada(
        repo, AlocacaoIniciada(_COLAB, 'posto-nunca-visto-antes', date(2026, 1, 1), _ORIGEM))
    assert aloc_id is not None


def test_12_colaborador_desconhecido_e_evento_fora_de_ordem(repo):
    with pytest.raises(EventoForaDeOrdemError):
        aplicar_alocacao_iniciada(
            repo, AlocacaoIniciada('colaborador-nunca-cadastrado', 'posto-A', date(2026, 1, 1), _ORIGEM))


def test_13_conflito_temporal_encerrar_vinculo_com_data_diferente(repo):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    aplicar_vinculo_encerrado(repo, VinculoEncerrado(_COLAB, date(2026, 6, 30), _ORIGEM))
    with pytest.raises(ConflitoTemporalEventoError):
        aplicar_vinculo_encerrado(repo, VinculoEncerrado(_COLAB, date(2026, 7, 15), _ORIGEM))


def test_13b_conflito_temporal_reabrir_vinculo_ja_aberto_com_outra_data(repo):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    with pytest.raises(ConflitoTemporalEventoError):
        aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 3, 1), _ORIGEM))


def test_14_repeticao_apos_falha_parcial_de_transferencia_nunca_duplica(repo):
    """Simula falha parcial: só o fechamento de A foi aplicado antes de
    travar (ex.: processo caiu entre as 2 escritas). Reprocessar o
    evento composto inteiro de novo nunca duplica o fechamento nem
    falha ao completar o restante."""
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(_COLAB, 'posto-A', date(2026, 1, 1), _ORIGEM))

    # Metade da transferência já aplicada manualmente (simula crash).
    aplicar_alocacao_encerrada(repo, AlocacaoEncerrada(_COLAB, 'posto-A', date(2026, 6, 15), _ORIGEM))

    # Reprocessa a transferência INTEIRA (idempotente na metade já feita).
    aplicar_transferencia(repo, _COLAB, 'posto-A', 'posto-B', date(2026, 6, 15), _ORIGEM)

    vinculo = repo.vinculo_mais_recente_de(_COLAB)
    a = repo.alocacao_mais_recente_de(vinculo.id, 'posto-A')
    b = repo.alocacao_mais_recente_de(vinculo.id, 'posto-B')
    assert a.vigente_ate == date(2026, 6, 15)  # nao duplicado, nao re-fechado com outra data
    assert b.vigente_de == date(2026, 6, 15)
    assert b.vigente_ate is None


def test_15_consulta_historica_apos_sequencia_completa(repo):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(_COLAB, 'posto-A', date(2026, 1, 1), _ORIGEM))
    aplicar_transferencia(repo, _COLAB, 'posto-A', 'posto-B', date(2026, 6, 15), _ORIGEM)

    antes = repo.resolver_unidade_posto(
        ReferenciaCanonica('COLABORADOR', _COLAB), ReferenciaCanonica('COMPETENCIA', '2026-03'))
    depois = repo.resolver_unidade_posto(
        ReferenciaCanonica('COLABORADOR', _COLAB), ReferenciaCanonica('COMPETENCIA', '2026-08'))
    transicao = repo.resolver_unidade_posto(
        ReferenciaCanonica('COLABORADOR', _COLAB), ReferenciaCanonica('COMPETENCIA', '2026-06'))

    assert antes.valores_confirmados == (ReferenciaCanonica('UNIDADE_POSTO', 'posto-A'),)
    assert depois.valores_confirmados == (ReferenciaCanonica('UNIDADE_POSTO', 'posto-B'),)
    assert set(v.entidade_id for v in transicao.valores_confirmados) == {'posto-A', 'posto-B'}


# ============================================================================
# Fase 9 -- corredor real usa a memória histórica, não o snapshot atual
# ============================================================================

def test_corredor_apos_sequencia_admissao_alocacao_transferencia(repo):
    func_id = 'colab-corredor-captura'

    aplicar_vinculo_iniciado(repo, VinculoIniciado(func_id, date(2025, 1, 1), _ORIGEM))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(func_id, 'posto-antigo', date(2025, 1, 1), _ORIGEM))
    aplicar_transferencia(repo, func_id, 'posto-antigo', 'posto-novo', date(2026, 6, 15), _ORIGEM)

    cliente_sintetico_id = 'cliente-captura-teste'

    def _listar_registros(**kwargs):
        table = kwargs.get('table_id')
        if table == TABLE_FUNC:
            return [{'id': func_id, 'fields': {F_FUNC_LOCAIS: ['local-captura-teste']}}]
        if table == TABLE_LOCAIS:
            return [{'id': 'local-captura-teste', 'fields': {F_LOCAL_CLIENTE: [cliente_sintetico_id]}}]
        return []

    leitor = Mock()
    leitor.listar_registros.side_effect = _listar_registros
    leitor.listar_clientes.return_value = []

    # Competência ANTES da transferência -- deve resolver posto-antigo,
    # via memória histórica (fonte_unidade_posto_override), nunca o
    # snapshot atual do Airtable (que nem é consultado aqui).
    execucao_antes = ExecucaoCorredorReadonly(
        leitor, ContextoCicloPrestacao((2026, 3)), fonte_unidade_posto_override=repo)
    texto_antes = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 03/2026\nCPF: 555.444.333-22'
    resultados_antes = execucao_antes.processar_documento(
        'doc-antes', 'a' * 64, texto=texto_antes,
        candidatos_colaborador=[CandidatoFuncionario(func_id=func_id, cpf='55544433322', nome_normalizado='CAPTURA')],
    )
    resultado_antes = resultados_antes[0].resultado_corredor
    dim_antes = {r.dimensao: r for r in resultado_antes.resolucao_semantica.resolucoes}
    assert dim_antes[DimensaoResolucao.UNIDADE_POSTO].valores_confirmados == (
        ReferenciaCanonica('UNIDADE_POSTO', 'posto-antigo'),
    )
    assert resultado_antes.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU

    # Competência DEPOIS da transferência -- resolve posto-novo.
    execucao_depois = ExecucaoCorredorReadonly(
        leitor, ContextoCicloPrestacao((2026, 8)), fonte_unidade_posto_override=repo)
    texto_depois = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 08/2026\nCPF: 555.444.333-22'
    resultados_depois = execucao_depois.processar_documento(
        'doc-depois', 'b' * 64, texto=texto_depois,
        candidatos_colaborador=[CandidatoFuncionario(func_id=func_id, cpf='55544433322', nome_normalizado='CAPTURA')],
    )
    resultado_depois = resultados_depois[0].resultado_corredor
    dim_depois = {r.dimensao: r for r in resultado_depois.resolucao_semantica.resolucoes}
    assert dim_depois[DimensaoResolucao.UNIDADE_POSTO].valores_confirmados == (
        ReferenciaCanonica('UNIDADE_POSTO', 'posto-novo'),
    )

    # Competência de TRANSIÇÃO -- cardinalidade legítima (os 2 postos),
    # nunca uma escolha arbitrária de qual "vale mais".
    postos_transicao = repo.postos_vigentes_em(
        repo.vinculo_mais_recente_de(func_id).id, date(2026, 6, 1), date(2026, 6, 30))
    assert set(postos_transicao) == {'posto-antigo', 'posto-novo'}


# ============================================================================
# Missão "REVISÃO OBRIGATÓRIA PR #114 -- ATOMICIDADE DA TRANSFERÊNCIA"
# ============================================================================

def test_transferencia_atomica_normal_funciona(repo):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(_COLAB, 'posto-A', date(2026, 1, 1), _ORIGEM))
    aplicar_transferencia(repo, _COLAB, 'posto-A', 'posto-B', date(2026, 6, 15), _ORIGEM)

    vinculo = repo.vinculo_mais_recente_de(_COLAB)
    a = repo.alocacao_mais_recente_de(vinculo.id, 'posto-A')
    b = repo.alocacao_mais_recente_de(vinculo.id, 'posto-B')
    assert a.vigente_ate == date(2026, 6, 15)
    assert b.vigente_de == date(2026, 6, 15)
    assert b.vigente_ate is None


def test_falha_simulada_na_abertura_de_b_mantem_a_aberta_e_b_ausente(repo):
    """Achado real da revisão independente do PR #114: sem transação,
    esta sequência deixaria A fechada com B nunca criada. Com
    `repo.transacao()`, uma falha ao abrir B reverte TAMBÉM o
    fechamento de A já feito na mesma chamada -- tudo-ou-nada real,
    provado contra o banco de verdade (SQLite aqui; Postgres real no
    arquivo `..._postgres_real.py`)."""
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(_COLAB, 'posto-A', date(2026, 1, 1), _ORIGEM))

    with mock.patch.object(repo, 'registrar_alocacao', side_effect=RuntimeError('falha simulada na abertura de B')):
        with pytest.raises(RuntimeError):
            aplicar_transferencia(repo, _COLAB, 'posto-A', 'posto-B', date(2026, 6, 15), _ORIGEM)

    vinculo = repo.vinculo_mais_recente_de(_COLAB)
    a = repo.alocacao_mais_recente_de(vinculo.id, 'posto-A')
    b = repo.alocacao_mais_recente_de(vinculo.id, 'posto-B')
    assert a.vigente_ate is None  # fechamento de A foi REVERTIDO junto com a falha de B
    assert b is None              # B nunca chegou a existir


def test_retry_completo_apos_falha_simulada_funciona(repo):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(_COLAB, 'posto-A', date(2026, 1, 1), _ORIGEM))

    with mock.patch.object(repo, 'registrar_alocacao', side_effect=RuntimeError('falha simulada')):
        with pytest.raises(RuntimeError):
            aplicar_transferencia(repo, _COLAB, 'posto-A', 'posto-B', date(2026, 6, 15), _ORIGEM)

    # Retry real, sem mock -- deve completar do zero (A ainda aberta,
    # graças ao rollback do teste anterior).
    aplicar_transferencia(repo, _COLAB, 'posto-A', 'posto-B', date(2026, 6, 15), _ORIGEM)

    vinculo = repo.vinculo_mais_recente_de(_COLAB)
    a = repo.alocacao_mais_recente_de(vinculo.id, 'posto-A')
    b = repo.alocacao_mais_recente_de(vinculo.id, 'posto-B')
    assert a.vigente_ate == date(2026, 6, 15)
    assert b.vigente_de == date(2026, 6, 15)
    assert b.vigente_ate is None


def test_transferencia_atomica_e_idempotente_quando_chamada_2x_com_sucesso(repo):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLAB, date(2026, 1, 1), _ORIGEM))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(_COLAB, 'posto-A', date(2026, 1, 1), _ORIGEM))
    id1 = aplicar_transferencia(repo, _COLAB, 'posto-A', 'posto-B', date(2026, 6, 15), _ORIGEM)
    id2 = aplicar_transferencia(repo, _COLAB, 'posto-A', 'posto-B', date(2026, 6, 15), _ORIGEM)
    assert id1 == id2


def test_transacao_aninhada_nao_e_suportada(repo):
    with repo.transacao():
        with pytest.raises(RuntimeError):
            with repo.transacao():
                pass


def test_corredor_historico_sem_regressao_apos_atomicidade(repo):
    """Não-regressão explícita (Fase 12): a mesma sequência de
    admissão->alocação->transferência já provada antes desta correção
    continua resolvendo A/B corretamente por competência através do
    corredor real -- a mudança de atomicidade não alterou nenhum
    resultado de leitura, só a segurança da escrita composta."""
    func_id = 'colab-corredor-sem-regressao'
    aplicar_vinculo_iniciado(repo, VinculoIniciado(func_id, date(2025, 1, 1), _ORIGEM))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(func_id, 'posto-antigo-nr', date(2025, 1, 1), _ORIGEM))
    aplicar_transferencia(repo, func_id, 'posto-antigo-nr', 'posto-novo-nr', date(2026, 6, 15), _ORIGEM)

    def _listar_registros(**kwargs):
        table = kwargs.get('table_id')
        if table == TABLE_FUNC:
            return [{'id': func_id, 'fields': {F_FUNC_LOCAIS: ['local-nr']}}]
        if table == TABLE_LOCAIS:
            return [{'id': 'local-nr', 'fields': {F_LOCAL_CLIENTE: ['cliente-nr']}}]
        return []

    leitor = Mock()
    leitor.listar_registros.side_effect = _listar_registros
    leitor.listar_clientes.return_value = []

    execucao = ExecucaoCorredorReadonly(
        leitor, ContextoCicloPrestacao((2026, 8)), fonte_unidade_posto_override=repo)
    texto = 'Recibo de Pagamento -- Total de Vencimentos\nCompetência: 08/2026\nCPF: 111.111.111-11'
    resultados = execucao.processar_documento(
        'doc-nr', 'c' * 64, texto=texto,
        candidatos_colaborador=[CandidatoFuncionario(func_id=func_id, cpf='11111111111', nome_normalizado='NR')],
    )
    resultado = resultados[0].resultado_corredor
    dimensoes = {r.dimensao: r for r in resultado.resolucao_semantica.resolucoes}
    assert dimensoes[DimensaoResolucao.UNIDADE_POSTO].valores_confirmados == (
        ReferenciaCanonica('UNIDADE_POSTO', 'posto-novo-nr'),
    )
    assert resultado.estado == EstadoCorredorDocumentoPrestacao.RESOLVIDO_E_AVANCOU
