"""Testes de `magnata_os/autenticacao/eventos.py` +
`adapters/sqlite_auditoria.py` + `auditoria_integracao.py` (FASE 6/7 da
missão "AUTENTICAÇÃO ADMINISTRATIVA COMPARTILHADA V1") -- incluindo a
integração ponta a ponta com a Confirmação de Alocação já existente
(prova real de "identidade autenticada -> operação de domínio -> trilha
quem fez"). Persistência REAL via SQLite -- nunca produção. Dados 100%
sintéticos."""
import tempfile
from datetime import date
from pathlib import Path

import pytest

from magnata_os.autenticacao.adapters.sqlite_auditoria import RepositorioAuditoriaSQLite
from magnata_os.autenticacao.auditoria_integracao import confirmar_alocacao_com_auditoria, executar_com_auditoria
from magnata_os.autenticacao.eventos import (
    RESULTADO_ERRO,
    RESULTADO_SUCESSO,
    OperacaoAuditada,
    registrar_operacao,
)
from magnata_os.autenticacao.identidade import Perfil, Sujeito
from magnata_os.documental.alocacao.adapters.sqlite_alocacao import RepositorioAlocacaoSQLite
from magnata_os.documental.alocacao.captura import aplicar_vinculo_iniciado
from magnata_os.documental.alocacao.confirmacao import ACAO_INICIAR, SolicitacaoConfirmacaoAlocacao
from magnata_os.documental.alocacao.eventos import VinculoIniciado

_SUJEITO_GESTOR = Sujeito(Perfil.GESTOR, sujeito_id='sub-1', email='gestor@exemplo.com', autenticado_por='google_oidc')
_COLABORADOR_ID = 'colab-auditoria-1'
_POSTO_A = 'posto-auditoria-A'
_ORIGEM = 'confirmacao_humana_shadow'


@pytest.fixture
def repo_auditoria():
    with tempfile.TemporaryDirectory() as tmp:
        r = RepositorioAuditoriaSQLite(Path(tmp) / 'auditoria_teste.sqlite3')
        yield r
        r.fechar()


@pytest.fixture
def repo_alocacao():
    with tempfile.TemporaryDirectory() as tmp:
        r = RepositorioAlocacaoSQLite(Path(tmp) / 'alocacao_teste.sqlite3')
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


# ============================================================================
# OperacaoAuditada -- validação
# ============================================================================

def test_operacao_sem_email_no_sujeito_falha():
    with pytest.raises(ValueError):
        OperacaoAuditada(sujeito=Sujeito(Perfil.GESTOR), operacao='x', resultado=RESULTADO_SUCESSO)


def test_operacao_erro_sem_erro_codigo_falha():
    with pytest.raises(ValueError):
        OperacaoAuditada(sujeito=_SUJEITO_GESTOR, operacao='x', resultado=RESULTADO_ERRO)


def test_operacao_sucesso_com_erro_codigo_falha():
    with pytest.raises(ValueError):
        OperacaoAuditada(
            sujeito=_SUJEITO_GESTOR, operacao='x', resultado=RESULTADO_SUCESSO, erro_codigo='XError')


def test_operacao_resultado_invalido_falha():
    with pytest.raises(ValueError):
        OperacaoAuditada(sujeito=_SUJEITO_GESTOR, operacao='x', resultado='TALVEZ')


# ============================================================================
# registrar_operacao + RepositorioAuditoriaSQLite
# ============================================================================

def test_registrar_operacao_persiste_e_e_consultavel(repo_auditoria):
    operacao_id = registrar_operacao(repo_auditoria, OperacaoAuditada(
        sujeito=_SUJEITO_GESTOR, operacao='confirmar_alocacao', resultado=RESULTADO_SUCESSO,
        referencia_agregado='aloc-123',
    ))
    registros = repo_auditoria.listar_por_referencia('aloc-123')
    assert len(registros) == 1
    assert registros[0].id == operacao_id
    assert registros[0].email == 'gestor@exemplo.com'
    assert registros[0].resultado == RESULTADO_SUCESSO


def test_registrar_operacao_nunca_deduplica_tentativas_repetidas(repo_auditoria):
    """Auditoria nunca é idempotente -- cada tentativa gera sua própria
    linha, mesmo que o domínio subjacente seja idempotente."""
    for _ in range(3):
        registrar_operacao(repo_auditoria, OperacaoAuditada(
            sujeito=_SUJEITO_GESTOR, operacao='confirmar_alocacao', resultado=RESULTADO_SUCESSO,
            referencia_agregado='aloc-repetida',
        ))
    assert len(repo_auditoria.listar_por_referencia('aloc-repetida')) == 3


# ============================================================================
# executar_com_auditoria -- genérico
# ============================================================================

def test_executar_com_auditoria_sucesso_grava_1_linha(repo_auditoria):
    resultado = executar_com_auditoria(
        repo_auditoria, _SUJEITO_GESTOR, 'operacao_generica', lambda: 'resultado-123')
    assert resultado == 'resultado-123'
    registros = repo_auditoria.listar_por_referencia('resultado-123')
    assert len(registros) == 1
    assert registros[0].resultado == RESULTADO_SUCESSO


def test_executar_com_auditoria_erro_grava_1_linha_e_repropaga(repo_auditoria):
    def _falha():
        raise ValueError('falha simulada')

    with pytest.raises(ValueError):
        executar_com_auditoria(
            repo_auditoria, _SUJEITO_GESTOR, 'operacao_generica', _falha,
            referencia_agregado_de_erro='ref-erro-1',
        )
    registros = repo_auditoria.listar_por_referencia('ref-erro-1')
    assert len(registros) == 1
    assert registros[0].resultado == RESULTADO_ERRO
    assert registros[0].erro_codigo == 'ValueError'


# ============================================================================
# confirmar_alocacao_com_auditoria -- integração ponta a ponta real
# ============================================================================

def _vinculo_ja_aberto(repo):
    aplicar_vinculo_iniciado(repo, VinculoIniciado(_COLABORADOR_ID, date(2026, 1, 1), _ORIGEM))


def test_confirmar_alocacao_com_auditoria_sucesso_aplica_e_audita(repo_alocacao, repo_auditoria):
    _vinculo_ja_aberto(repo_alocacao)
    resolver = _ResolverSintetico({_COLABORADOR_ID}, {_POSTO_A})
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id=_COLABORADOR_ID, posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    aloc_id = confirmar_alocacao_com_auditoria(
        _SUJEITO_GESTOR, repo_alocacao, resolver, solicitacao, repo_auditoria)

    # aplicado de verdade no shadow de alocacao
    vinculo = repo_alocacao.vinculo_mais_recente_de(_COLABORADOR_ID)
    assert repo_alocacao.alocacao_mais_recente_de(vinculo.id, _POSTO_A).id == aloc_id

    # e auditado -- identidade completa chegou na trilha (sucesso
    # referencia o AGREGADO CRIADO -- o id da alocacao -- nunca o
    # colaborador_id, que so e usado como referencia no caminho de ERRO)
    registros = repo_auditoria.listar_por_referencia(aloc_id)
    assert len(registros) == 1
    assert registros[0].email == 'gestor@exemplo.com'
    assert registros[0].perfil == 'GESTOR'
    assert registros[0].operacao == 'confirmar_alocacao'
    assert registros[0].resultado == RESULTADO_SUCESSO


def test_confirmar_alocacao_com_auditoria_falha_tambem_e_auditada(repo_alocacao, repo_auditoria):
    """Colaborador inexistente -- confirmar_alocacao levanta
    ColaboradorNaoIdentificadoError; a auditoria registra o ERRO e a
    excecao original continua propagando (nunca mascarada)."""
    from magnata_os.documental.alocacao.confirmacao import ColaboradorNaoIdentificadoError

    resolver = _ResolverSintetico(colaboradores_existentes=set(), postos_existentes={_POSTO_A})
    solicitacao = SolicitacaoConfirmacaoAlocacao(
        colaborador_id='colab-nunca-existiu', posto_id=_POSTO_A, data_efetiva=date(2026, 2, 1),
        acao=ACAO_INICIAR, origem_confirmacao=_ORIGEM,
    )
    with pytest.raises(ColaboradorNaoIdentificadoError):
        confirmar_alocacao_com_auditoria(
            _SUJEITO_GESTOR, repo_alocacao, resolver, solicitacao, repo_auditoria)

    registros = repo_auditoria.listar_por_referencia('colab-nunca-existiu')
    assert len(registros) == 1
    assert registros[0].resultado == RESULTADO_ERRO
    assert registros[0].erro_codigo == 'ColaboradorNaoIdentificadoError'
