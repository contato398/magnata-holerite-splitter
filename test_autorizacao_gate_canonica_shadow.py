"""Autorizacao de gate canonica V1: fato append-only, zero transporte."""
from datetime import datetime, timezone

import pytest

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.pacote_prestacao import EstadoPacotePrestacao, PacotePrestacaoCliente
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.orquestrador.autorizacao_gate import (
    AutorizacaoGateError,
    ConflitoDecisaoGateError,
    DecisaoGate,
    RepositorioAutorizacoesGateEmMemoria,
    registrar_decisao_gate_shadow,
)
from magnata_os.orquestrador.eventos import EstadoExecucao
from magnata_os.orquestrador.plano_comunicacao import ConteudoItem
from magnata_os.orquestrador.politica_comunicacao import ItemComunicacao
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria
from magnata_os.orquestrador.wiring_autorizacao_persistida_plano_shadow import (
    materializar_plano_com_autorizacao_persistida_shadow,
)
from magnata_os.orquestrador.wiring_autorizacao_plano_shadow import WiringAutorizacaoPlanoError
from magnata_os.orquestrador.wiring_prestacao_comunicacao_shadow import registrar_intencao_comunicacao_shadow

_INSTANTE = datetime(2026, 9, 6, 15, 30, tzinfo=timezone.utc)
_TEXTO = 'Prestação disponível para conferência.'


def _intencao(repo):
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-1')
    competencia = ReferenciaCanonica('COMPETENCIA', '2026-07')
    pacote = PacotePrestacaoCliente(
        cliente=cliente,
        competencia=competencia,
        estado=EstadoPacotePrestacao.PRONTO,
        itens_incluidos=(ItemInventarioPrestacao(
            documento_id='doc-001',
            tipo_documental='Folha de Ponto',
            cliente=cliente,
            competencia=competencia,
            colaborador=ReferenciaCanonica('COLABORADOR', 'colab-1'),
        ),),
        tipos_obrigatorios=('Folha de Ponto',),
    )
    return registrar_intencao_comunicacao_shadow(
        pacote=pacote,
        repositorio=repo,
        destinatarios=('5515999999999',),
        texto=_TEXTO,
        itens=(ItemComunicacao('documento', 'prestacao.pdf'),),
        assinatura=False,
        comprovante=True,
        instante=_INSTANTE,
    ).intencao


def _registrar(repo_exec, repo_auth, intencao, decisao=DecisaoGate.AUTORIZADO):
    return registrar_decisao_gate_shadow(
        repositorio_execucoes=repo_exec,
        repositorio_autorizacoes=repo_auth,
        event_id=f'comunicacao:{intencao.intencao_id}',
        preview_id=intencao.preview.preview_id,
        decisao=decisao,
        ator_referencia='sujeito:gestor-1',
        proveniencia='sessao_autenticada',
        instante=_INSTANTE,
    )


def test_autorizacao_e_fato_separado_e_nao_muda_waiting_gate():
    repo_exec = RepositorioExecucoesEmMemoria()
    repo_auth = RepositorioAutorizacoesGateEmMemoria()
    intencao = _intencao(repo_exec)

    auth = _registrar(repo_exec, repo_auth, intencao)

    assert auth.decisao == DecisaoGate.AUTORIZADO
    assert repo_auth.buscar(auth.event_id, auth.preview_id) == auth
    execucao = repo_exec.buscar_por_event_id(auth.event_id)
    assert execucao.estado == EstadoExecucao.WAITING_GATE
    assert execucao.attempt == 0


def test_mesmo_fato_e_idempotente_sem_duplicacao():
    repo_exec = RepositorioExecucoesEmMemoria()
    repo_auth = RepositorioAutorizacoesGateEmMemoria()
    intencao = _intencao(repo_exec)

    primeiro = _registrar(repo_exec, repo_auth, intencao)
    segundo = _registrar(repo_exec, repo_auth, intencao)

    assert primeiro == segundo
    assert repo_auth.listar_por_evento(primeiro.event_id) == [primeiro]


def test_decisao_conflitante_nao_sobrescreve_fato_original():
    repo_exec = RepositorioExecucoesEmMemoria()
    repo_auth = RepositorioAutorizacoesGateEmMemoria()
    intencao = _intencao(repo_exec)
    original = _registrar(repo_exec, repo_auth, intencao, DecisaoGate.RECUSADO)

    with pytest.raises(ConflitoDecisaoGateError):
        _registrar(repo_exec, repo_auth, intencao, DecisaoGate.AUTORIZADO)

    assert repo_auth.buscar(original.event_id, original.preview_id) == original


def test_nao_registra_decisao_para_evento_inexistente():
    repo_exec = RepositorioExecucoesEmMemoria()
    repo_auth = RepositorioAutorizacoesGateEmMemoria()

    with pytest.raises(AutorizacaoGateError, match='nao encontrado'):
        registrar_decisao_gate_shadow(
            repositorio_execucoes=repo_exec,
            repositorio_autorizacoes=repo_auth,
            event_id='comunicacao:inexistente',
            preview_id='preview-1',
            decisao=DecisaoGate.AUTORIZADO,
            ator_referencia='sujeito:gestor-1',
            proveniencia='sessao_autenticada',
            instante=_INSTANTE,
        )


def test_fato_autorizado_materializa_plano_sem_transporte():
    repo_exec = RepositorioExecucoesEmMemoria()
    repo_auth = RepositorioAutorizacoesGateEmMemoria()
    intencao = _intencao(repo_exec)
    auth = _registrar(repo_exec, repo_auth, intencao)

    resultado = materializar_plano_com_autorizacao_persistida_shadow(
        intencao=intencao,
        repositorio_execucoes=repo_exec,
        autorizacao=auth,
        texto=_TEXTO,
        conteudos=(ConteudoItem('documento', 'prestacao.pdf', 'storage://doc-001'),),
    )

    assert resultado.plano.total_notificacoes == 1
    assert repo_exec.buscar_por_event_id(auth.event_id).estado == EstadoExecucao.WAITING_GATE


def test_fato_recusado_nunca_materializa_plano():
    repo_exec = RepositorioExecucoesEmMemoria()
    repo_auth = RepositorioAutorizacoesGateEmMemoria()
    intencao = _intencao(repo_exec)
    auth = _registrar(repo_exec, repo_auth, intencao, DecisaoGate.RECUSADO)

    with pytest.raises(WiringAutorizacaoPlanoError, match='nao foi autorizado'):
        materializar_plano_com_autorizacao_persistida_shadow(
            intencao=intencao,
            repositorio_execucoes=repo_exec,
            autorizacao=auth,
            texto=_TEXTO,
            conteudos=(ConteudoItem('documento', 'prestacao.pdf', 'storage://doc-001'),),
        )


def test_autorizacao_de_outra_previa_nao_e_reutilizavel():
    repo_exec = RepositorioExecucoesEmMemoria()
    repo_auth = RepositorioAutorizacoesGateEmMemoria()
    intencao = _intencao(repo_exec)
    auth = _registrar(repo_exec, repo_auth, intencao)
    adulterado = type(auth)(
        autorizacao_id=auth.autorizacao_id,
        event_id=auth.event_id,
        preview_id='outra-previa',
        decisao=auth.decisao,
        ator_referencia=auth.ator_referencia,
        registrado_em=auth.registrado_em,
        proveniencia=auth.proveniencia,
    )

    with pytest.raises(WiringAutorizacaoPlanoError, match='outra previa'):
        materializar_plano_com_autorizacao_persistida_shadow(
            intencao=intencao,
            repositorio_execucoes=repo_exec,
            autorizacao=adulterado,
            texto=_TEXTO,
            conteudos=(ConteudoItem('documento', 'prestacao.pdf', 'storage://doc-001'),),
        )
