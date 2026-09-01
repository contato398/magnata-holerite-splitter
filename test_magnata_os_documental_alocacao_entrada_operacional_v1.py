"""Testes de `magnata_os/documental/alocacao/fabrica_repositorio_alocacao.py`
+ `autorizacao.py` + `preview_confirmacao.py` + `api/handlers.py`
(missão "ENTRADA OPERACIONAL + POSTGRES PRÓPRIO V1").

Persistência REAL via `RepositorioAlocacaoSQLite` (mesma disciplina de
todo o resto do pacote `alocacao`) -- nunca produção, nunca Postgres
real fora de CI. `conexao.abrir_conexao`/`psycopg` NUNCA chamados de
verdade neste arquivo -- só com `conectar` fake injetado (mesma
disciplina de `conexao.py`, que também nunca exige o driver `psycopg`
instalado nos próprios testes).

Dados 100% sintéticos."""
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock
from unittest.mock import Mock

import pytest

from magnata_os.documental.alocacao.adapters.sqlite_alocacao import RepositorioAlocacaoSQLite
from magnata_os.documental.alocacao.api.handlers import (
    PERMISSAO_CONFIRMAR,
    PERMISSAO_PRE_VISUALIZAR,
    confirmar_alocacao,
    pre_visualizar_confirmacao,
)
from magnata_os.documental.alocacao.autorizacao import Perfil, PermissaoNegada, Sujeito, exigir_perfil
from magnata_os.documental.alocacao.captura import aplicar_alocacao_encerrada, aplicar_alocacao_iniciada, aplicar_vinculo_iniciado
from magnata_os.documental.alocacao.comparacao_airtable import EstadoComparacaoAirtable
from magnata_os.documental.alocacao.confirmacao import (
    ACAO_INICIAR,
    ACAO_TRANSFERIR,
    ColaboradorNaoIdentificadoError,
    SolicitacaoConfirmacaoAlocacao,
)
from magnata_os.documental.alocacao.eventos import AlocacaoEncerrada, AlocacaoIniciada, VinculoIniciado
from magnata_os.documental.alocacao.fabrica_repositorio_alocacao import (
    BackendAlocacao,
    ConfiguracaoRepositorioAlocacao,
    ConfiguracaoRepositorioAlocacaoInvalida,
    construir_repositorio_alocacao,
)
from magnata_os.documental.alocacao.preview_confirmacao import montar_preview
from magnata_os.documental.modulo01.adapters.conexao import ConfiguracaoBancoAusente, FalhaConexaoBanco

_COLABORADOR_ID = 'colab-entrada-1'
_POSTO_A = 'posto-entrada-A'
_POSTO_B = 'posto-entrada-B'
_ORIGEM = 'confirmacao_humana_shadow'


@pytest.fixture
def repo():
    with tempfile.TemporaryDirectory() as tmp:
        r = RepositorioAlocacaoSQLite(Path(tmp) / 'entrada_teste.sqlite3')
        yield r
        r.fechar()


class _ResolverSintetico:
    def __init__(self, colaboradores_existentes: set, postos_existentes: set):
        self._colaboradores_existentes = colaboradores_existentes
        self._postos_existentes = postos_existentes

    def confirmar_colaborador_existe(self, colaborador_id: str) -> bool:
        return colaborador_id in self._colaboradores_existentes

    def confirmar_posto_existe(self, posto_id: str) -> bool:
        return posto_id in self._postos_existentes


class _SnapshotSintetico:
    def __init__(self, postos_por_colaborador: dict):
        self._postos_por_colaborador = postos_por_colaborador

    def postos_atuais_do_colaborador(self, colaborador_id: str):
        if colaborador_id not in self._postos_por_colaborador:
            raise KeyError('sem snapshot configurado')
        return self._postos_por_colaborador[colaborador_id]


@pytest.fixture
def resolver():
    return _ResolverSintetico({_COLABORADOR_ID}, {_POSTO_A, _POSTO_B})


def _vinculo_ja_aberto(repo, data=date(2026, 1, 1)):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLABORADOR_ID, data, _ORIGEM))


# ============================================================================
# fabrica_repositorio_alocacao.py -- nenhum fallback silencioso, Airtable
# nunca e um backend aceito
# ============================================================================

def test_fabrica_sqlite_constroi_repositorio_real(repo):
    with tempfile.TemporaryDirectory() as tmp:
        r = construir_repositorio_alocacao(
            ConfiguracaoRepositorioAlocacao(BackendAlocacao.SQLITE, caminho_sqlite=Path(tmp) / 'f.sqlite3'))
        assert isinstance(r, RepositorioAlocacaoSQLite)
        r.fechar()


def test_fabrica_sqlite_sem_caminho_falha():
    with pytest.raises(ConfiguracaoRepositorioAlocacaoInvalida):
        construir_repositorio_alocacao(ConfiguracaoRepositorioAlocacao(BackendAlocacao.SQLITE))


def test_fabrica_postgres_sem_database_url_falha_limpo():
    # nenhum psycopg real necessario -- ConfiguracaoBancoAusente vem de
    # conexao.py antes de qualquer tentativa de conectar
    with pytest.raises(ConfiguracaoBancoAusente):
        construir_repositorio_alocacao(
            ConfiguracaoRepositorioAlocacao(BackendAlocacao.POSTGRES), ambiente={})


def test_fabrica_postgres_indisponivel_propaga_falha_sem_fallback_para_airtable():
    """FASE 9 -- 'Postgres indisponível': a fabrica nunca tenta
    Airtable como substituto -- propaga a falha de conexao real."""
    def _conectar_que_falha(url):
        raise ConnectionError('Postgres indisponivel (simulado)')

    with pytest.raises(FalhaConexaoBanco):
        construir_repositorio_alocacao(
            ConfiguracaoRepositorioAlocacao(BackendAlocacao.POSTGRES),
            database_url='fake', conectar=_conectar_que_falha,
        )


def test_fabrica_postgres_com_conexao_fake_constroi_repositorio():
    conexao_fake = Mock()
    r = construir_repositorio_alocacao(
        ConfiguracaoRepositorioAlocacao(BackendAlocacao.POSTGRES),
        database_url='fake', conectar=lambda url: conexao_fake,
    )
    from magnata_os.documental.alocacao.adapters.postgres_alocacao import RepositorioAlocacaoPostgres
    assert isinstance(r, RepositorioAlocacaoPostgres)


def test_fabrica_postgres_nao_aceita_caminho_sqlite():
    with pytest.raises(ConfiguracaoRepositorioAlocacaoInvalida):
        construir_repositorio_alocacao(ConfiguracaoRepositorioAlocacao(
            BackendAlocacao.POSTGRES, caminho_sqlite=Path('nunca.sqlite3')))


def test_backend_alocacao_airtable_nao_e_um_valor_aceito():
    with pytest.raises(ValueError):
        BackendAlocacao('AIRTABLE')


# ============================================================================
# autorizacao.py -- exigir_perfil
# ============================================================================

def test_exigir_perfil_aceita_quando_perfil_permitido():
    exigir_perfil(Sujeito(Perfil.GESTOR), frozenset({Perfil.GESTOR}))  # nunca levanta


def test_exigir_perfil_recusa_quando_perfil_nao_permitido():
    with pytest.raises(PermissaoNegada):
        exigir_perfil(Sujeito(Perfil.OPERACIONAL), frozenset({Perfil.GESTOR}))


# ============================================================================
# preview_confirmacao.py -- nunca escreve, TOCTOU nunca corrompe
# ============================================================================

def test_preview_nunca_escreve_no_repo(repo, resolver):
    _vinculo_ja_aberto(repo)
    aplicar_confirmacao_de_teste = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    snapshot = _SnapshotSintetico({_COLABORADOR_ID: frozenset({_POSTO_A})})
    montar_preview(repo, snapshot, aplicar_confirmacao_de_teste)
    # nenhuma alocacao foi criada so por montar o preview
    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    assert repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A) is None


def test_preview_mostra_estado_atual_e_consequencia(repo, resolver):
    _vinculo_ja_aberto(repo)
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    snapshot = _SnapshotSintetico({_COLABORADOR_ID: frozenset({_POSTO_A})})
    preview = montar_preview(repo, snapshot, solicitacao)
    assert preview.colaborador_id == _COLABORADOR_ID
    assert preview.acao == ACAO_INICIAR
    assert preview.postos_atuais_magnata_os == frozenset()  # nada aplicado ainda
    assert preview.postos_atuais_airtable == frozenset({_POSTO_A})
    assert preview.estado_comparacao == EstadoComparacaoAirtable.MAGNATA_SEM_DADO
    assert 'posto-entrada-A' in preview.consequencia_temporal


def test_preview_transferencia_mostra_de_e_para(repo, resolver):
    _vinculo_ja_aberto(repo)
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 6, 15),
        acao=ACAO_TRANSFERIR, origem_confirmacao=_ORIGEM, posto_destino_id=_POSTO_B,
    )
    snapshot = _SnapshotSintetico({_COLABORADOR_ID: frozenset()})
    preview = montar_preview(repo, snapshot, solicitacao)
    assert preview.posto_origem_id == _POSTO_A
    assert preview.posto_destino_id == _POSTO_B
    assert _POSTO_A in preview.consequencia_temporal
    assert _POSTO_B in preview.consequencia_temporal


def test_preview_airtable_indisponivel_vira_ambiguo_nunca_derruba(repo, resolver):
    _vinculo_ja_aberto(repo)
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )

    class _SnapshotIndisponivel:
        def postos_atuais_do_colaborador(self, colaborador_id: str):
            raise ConnectionError('Airtable indisponivel (simulado)')

    preview = montar_preview(repo, _SnapshotIndisponivel(), solicitacao)
    assert preview.postos_atuais_airtable is None
    assert preview.estado_comparacao == EstadoComparacaoAirtable.AMBIGUO


def test_falha_entre_preview_e_confirmacao_nao_deixa_estado_parcial(repo, resolver):
    """FASE 9 -- 'falha entre preview e confirmação': o preview é
    montado com sucesso; a confirmação real, chamada em seguida, falha
    (erro simulado de escrita) -- nenhum estado parcial fica no shadow,
    e o preview (já em memória) continua válido/inerte -- ele nunca é
    reaplicado nem precisa ser refeito por causa da falha."""
    _vinculo_ja_aberto(repo)
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    snapshot = _SnapshotSintetico({_COLABORADOR_ID: frozenset()})
    preview = montar_preview(repo, snapshot, solicitacao)  # sucesso
    assert preview.acao == ACAO_INICIAR

    with mock.patch.object(repo, 'registrar_alocacao', side_effect=RuntimeError('falha simulada na escrita real')):
        with pytest.raises(RuntimeError):
            confirmar_alocacao(Sujeito(Perfil.GESTOR), repo, resolver, solicitacao)

    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    assert repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A) is None  # nada parcial


def test_preview_estado_atual_usa_hoje_nunca_a_data_efetiva_da_solicitacao_pendente(repo, resolver):
    """Regressão -- achado da auto-revisão (FASE 10, temporalidade):
    'Estado atual Magnata OS' significa AGORA, nunca a data (passada ou
    futura) da mudança pendente. Cenário: posto A esteve aberto só de
    jan a jun/2026; a solicitação pendente tem data_efetiva em ago/2026
    (depois do fechamento) -- se o preview lesse pela data_efetiva, o
    posto A pareceria fechado; lendo por 'hoje' (mar/2026, durante a
    janela), ele aparece corretamente aberto."""
    _vinculo_ja_aberto(repo, data=date(2025, 1, 1))
    aplicar_alocacao_iniciada(repo, AlocacaoIniciada(_COLABORADOR_ID, _POSTO_A, date(2026, 1, 1), _ORIGEM))
    aplicar_alocacao_encerrada(repo, AlocacaoEncerrada(_COLABORADOR_ID, _POSTO_A, date(2026, 6, 1), _ORIGEM))

    solicitacao_pendente = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_B, data_efetiva=date(2026, 8, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    snapshot = _SnapshotSintetico({_COLABORADOR_ID: frozenset()})
    preview = montar_preview(repo, snapshot, solicitacao_pendente, hoje=date(2026, 3, 1))
    assert preview.postos_atuais_magnata_os == frozenset({_POSTO_A})


def test_preview_seguido_de_confirmacao_com_snapshot_airtable_mudado_nao_corrompe(repo, resolver):
    """FASE 9 -- 'snapshot Airtable mudou depois do preview': a
    confirmação real nunca usa nenhum dado do preview -- só o que
    `resolver`/`repo` dizem NO MOMENTO da aplicação. Um preview
    desatualizado nunca faz a escrita real aplicar algo diferente do
    que os dados atuais permitem."""
    _vinculo_ja_aberto(repo)
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    # snapshot no momento do preview: posto A existe
    snapshot_no_preview = _SnapshotSintetico({_COLABORADOR_ID: frozenset({_POSTO_A})})
    preview = montar_preview(repo, snapshot_no_preview, solicitacao)
    assert preview.postos_atuais_airtable == frozenset({_POSTO_A})

    # "Airtable mudou" -- resolver usado na confirmacao real ja nao
    # reconhece mais o posto A (ex.: Local foi removido/renomeado la)
    resolver_apos_mudanca = _ResolverSintetico({_COLABORADOR_ID}, postos_existentes=set())
    sujeito_gestor = Sujeito(Perfil.GESTOR)
    with pytest.raises(Exception):  # PostoNaoIdentificadoError
        confirmar_alocacao(sujeito_gestor, repo, resolver_apos_mudanca, solicitacao)

    # nada foi escrito -- a confirmacao real recusou com base no
    # estado ATUAL, nunca no preview desatualizado
    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    assert repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A) is None


# ============================================================================
# api/handlers.py -- exigir_perfil sempre primeiro, nunca depois de
# tocar repo/resolver
# ============================================================================

def test_pre_visualizar_confirmacao_com_perfil_operacional_funciona(repo, resolver):
    _vinculo_ja_aberto(repo)
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    snapshot = _SnapshotSintetico({_COLABORADOR_ID: frozenset()})
    preview = pre_visualizar_confirmacao(Sujeito(Perfil.OPERACIONAL), repo, snapshot, solicitacao)
    assert preview.colaborador_id == _COLABORADOR_ID


def test_pre_visualizar_confirmacao_com_perfil_auditor_recusado(repo, resolver):
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    with pytest.raises(PermissaoNegada):
        pre_visualizar_confirmacao(Sujeito(Perfil.AUDITOR), repo, Mock(), solicitacao)


def test_confirmar_alocacao_com_perfil_operacional_recusado_nunca_toca_repo(repo, resolver):
    """Confirmar exige GESTOR -- OPERACIONAL (suficiente só para
    preview) e recusado, e a checagem acontece ANTES de qualquer
    acesso a repo/resolver."""
    _vinculo_ja_aberto(repo)
    repo_espiao = Mock(wraps=repo)
    resolver_espiao = Mock(wraps=resolver)
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    with pytest.raises(PermissaoNegada):
        confirmar_alocacao(Sujeito(Perfil.OPERACIONAL), repo_espiao, resolver_espiao, solicitacao)
    resolver_espiao.confirmar_colaborador_existe.assert_not_called()
    resolver_espiao.confirmar_posto_existe.assert_not_called()


def test_confirmar_alocacao_com_perfil_gestor_aplica_de_verdade(repo, resolver):
    _vinculo_ja_aberto(repo)
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    aloc_id = confirmar_alocacao(Sujeito(Perfil.GESTOR), repo, resolver, solicitacao)
    vinculo = repo.vinculo_mais_recente_de(_COLABORADOR_ID)
    assert repo.alocacao_mais_recente_de(vinculo.id, _POSTO_A).id == aloc_id


def test_confirmar_alocacao_colaborador_inexistente_via_handler(repo, resolver):
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id='colab-nunca-existiu', posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    with pytest.raises(ColaboradorNaoIdentificadoError):
        confirmar_alocacao(Sujeito(Perfil.GESTOR), repo, resolver, solicitacao)


def test_permissoes_pre_visualizar_e_confirmar_sao_distintas():
    # confirmar e mais restrito que pre-visualizar -- nunca o contrario
    assert PERMISSAO_CONFIRMAR.issubset(PERMISSAO_PRE_VISUALIZAR)
    assert PERMISSAO_CONFIRMAR != PERMISSAO_PRE_VISUALIZAR
