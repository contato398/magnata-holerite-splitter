"""Autorizacao -> PlanoDisparo V1 shadow: zero transporte, gate vinculante."""
from datetime import datetime, timezone

import pytest

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.pacote_prestacao import (
    EstadoPacotePrestacao,
    PacotePrestacaoCliente,
)
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.orquestrador.eventos import EstadoExecucao
from magnata_os.orquestrador.plano_comunicacao import ConteudoItem, PlanoComunicacaoError
from magnata_os.orquestrador.politica_comunicacao import AutorizacaoObrigatoriaError, ItemComunicacao
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria
from magnata_os.orquestrador.wiring_autorizacao_plano_shadow import (
    WiringAutorizacaoPlanoError,
    materializar_plano_autorizado_shadow,
)
from magnata_os.orquestrador.wiring_prestacao_comunicacao_shadow import (
    registrar_intencao_comunicacao_shadow,
)

_CLIENTE = ReferenciaCanonica('CLIENTE', 'cliente-1')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')
_INSTANTE = datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc)


def _pacote():
    item = ItemInventarioPrestacao(
        documento_id='doc-001',
        tipo_documental='Folha de Ponto',
        cliente=_CLIENTE,
        competencia=_COMPETENCIA,
        colaborador=ReferenciaCanonica('COLABORADOR', 'colab-1'),
    )
    return PacotePrestacaoCliente(
        cliente=_CLIENTE,
        competencia=_COMPETENCIA,
        estado=EstadoPacotePrestacao.PRONTO,
        itens_incluidos=(item,),
        tipos_obrigatorios=('Folha de Ponto',),
    )


def _intencao(repo):
    return registrar_intencao_comunicacao_shadow(
        pacote=_pacote(),
        repositorio=repo,
        destinatarios=('5515999999999',),
        texto='Prestação disponível para conferência.',
        itens=(ItemComunicacao('documento', 'prestacao.pdf'),),
        assinatura=False,
        comprovante=True,
        instante=_INSTANTE,
    ).intencao


def _conteudos():
    return (ConteudoItem('documento', 'prestacao.pdf', 'storage://doc-001'),)


def test_autorizacao_exata_materializa_plano_sem_mudar_waiting_gate():
    repo = RepositorioExecucoesEmMemoria()
    intencao = _intencao(repo)

    resultado = materializar_plano_autorizado_shadow(
        intencao=intencao,
        repositorio=repo,
        texto='Prestação disponível para conferência.',
        conteudos=_conteudos(),
        preview_id_autorizado=intencao.preview.preview_id,
        autorizacao_explicita=True,
    )

    assert resultado.preview_id == intencao.preview.preview_id
    assert resultado.plano.total_notificacoes == 1
    assert resultado.plano.mensagens_por_pessoa == 1
    assert resultado.plano.acoes[0].tipo == 'documento'
    assert resultado.plano.acoes[0].legenda == 'Prestação disponível para conferência.'
    registro = repo.buscar_por_event_id(f'comunicacao:{intencao.intencao_id}')
    assert registro.estado == EstadoExecucao.WAITING_GATE
    assert registro.attempt == 0


def test_sem_autorizacao_explicita_permanece_bloqueado():
    repo = RepositorioExecucoesEmMemoria()
    intencao = _intencao(repo)

    with pytest.raises(AutorizacaoObrigatoriaError):
        materializar_plano_autorizado_shadow(
            intencao=intencao,
            repositorio=repo,
            texto='Prestação disponível para conferência.',
            conteudos=_conteudos(),
            preview_id_autorizado=intencao.preview.preview_id,
            autorizacao_explicita=False,
        )


def test_autorizacao_de_outra_previa_nao_materializa_plano():
    repo = RepositorioExecucoesEmMemoria()
    intencao = _intencao(repo)

    with pytest.raises(AutorizacaoObrigatoriaError, match='não corresponde'):
        materializar_plano_autorizado_shadow(
            intencao=intencao,
            repositorio=repo,
            texto='Prestação disponível para conferência.',
            conteudos=_conteudos(),
            preview_id_autorizado='preview-de-outra-comunicacao',
            autorizacao_explicita=True,
        )


def test_texto_diferente_da_previa_autorizada_e_bloqueado():
    repo = RepositorioExecucoesEmMemoria()
    intencao = _intencao(repo)

    with pytest.raises(PlanoComunicacaoError, match='texto não corresponde'):
        materializar_plano_autorizado_shadow(
            intencao=intencao,
            repositorio=repo,
            texto='Texto alterado depois da autorização.',
            conteudos=_conteudos(),
            preview_id_autorizado=intencao.preview.preview_id,
            autorizacao_explicita=True,
        )


def test_conteudo_ausente_ou_extra_e_bloqueado():
    repo = RepositorioExecucoesEmMemoria()
    intencao = _intencao(repo)

    with pytest.raises(PlanoComunicacaoError, match='conteúdo ausente'):
        materializar_plano_autorizado_shadow(
            intencao=intencao,
            repositorio=repo,
            texto='Prestação disponível para conferência.',
            conteudos=(),
            preview_id_autorizado=intencao.preview.preview_id,
            autorizacao_explicita=True,
        )


def test_intencao_nao_persistida_nunca_materializa_plano():
    repo_origem = RepositorioExecucoesEmMemoria()
    intencao = _intencao(repo_origem)
    repo_vazio = RepositorioExecucoesEmMemoria()

    with pytest.raises(WiringAutorizacaoPlanoError, match='nao encontrada'):
        materializar_plano_autorizado_shadow(
            intencao=intencao,
            repositorio=repo_vazio,
            texto='Prestação disponível para conferência.',
            conteudos=_conteudos(),
            preview_id_autorizado=intencao.preview.preview_id,
            autorizacao_explicita=True,
        )


def test_repetir_materializacao_e_idempotente_e_nao_muta_execucao():
    repo = RepositorioExecucoesEmMemoria()
    intencao = _intencao(repo)
    kwargs = dict(
        intencao=intencao,
        repositorio=repo,
        texto='Prestação disponível para conferência.',
        conteudos=_conteudos(),
        preview_id_autorizado=intencao.preview.preview_id,
        autorizacao_explicita=True,
    )

    primeira = materializar_plano_autorizado_shadow(**kwargs)
    segunda = materializar_plano_autorizado_shadow(**kwargs)

    assert primeira.plano == segunda.plano
    assert len(repo.listar_todos()) == 1
    assert repo.listar_todos()[0].estado == EstadoExecucao.WAITING_GATE
