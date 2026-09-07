"""Wiring canônico Prestação -> Comunicação V1: somente shadow, zero envio."""
from datetime import datetime, timezone

import pytest

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.pacote_prestacao import (
    EstadoPacotePrestacao,
    PacotePrestacaoCliente,
)
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.orquestrador.eventos import EstadoExecucao, TipoEvento
from magnata_os.orquestrador.politica_autonomia import NivelAutonomia, nivel_para
from magnata_os.orquestrador.politica_comunicacao import (
    ItemComunicacao,
    hash_conteudo_comunicacao,
)
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria
from magnata_os.orquestrador.wiring_prestacao_comunicacao_shadow import (
    WiringPrestacaoComunicacaoError,
    identidade_pacote_prestacao,
    registrar_intencao_comunicacao_shadow,
)

_CLIENTE = ReferenciaCanonica('CLIENTE', 'cliente-1')
_COMPETENCIA = ReferenciaCanonica('COMPETENCIA', '2026-07')
_INSTANTE = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
_DOCUMENTO = b'documento-prestacao-sintetico'


def _pacote(estado=EstadoPacotePrestacao.PRONTO):
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
        estado=estado,
        itens_incluidos=(item,),
        tipos_obrigatorios=('Folha de Ponto',),
    )


def _registrar(repo, **overrides):
    kwargs = dict(
        pacote=_pacote(),
        repositorio=repo,
        destinatarios=('5515999999999',),
        texto='Prestação disponível para conferência.',
        itens=(ItemComunicacao(
            'documento', 'prestacao.pdf', hash_conteudo_comunicacao(_DOCUMENTO),
        ),),
        assinatura=False,
        comprovante=True,
        instante=_INSTANTE,
    )
    kwargs.update(overrides)
    return registrar_intencao_comunicacao_shadow(**kwargs)


def test_pacote_pronto_vira_intencao_persistida_em_waiting_gate():
    repo = RepositorioExecucoesEmMemoria()

    resultado = _registrar(repo)

    assert resultado.intencao.origem == 'PRESTACAO_CONTAS'
    assert resultado.intencao.canal_preferencial == 'WHATSAPP'
    assert resultado.execucao.estado == EstadoExecucao.WAITING_GATE
    assert resultado.execucao.event_type == TipoEvento.COMUNICACAO_SOLICITADA.value
    assert resultado.execucao.attempt == 0
    assert repo.buscar_por_event_id(resultado.execucao.event_id) is resultado.execucao


def test_comunicacao_solicitada_e_explicitamente_human_required():
    assert nivel_para(TipoEvento.COMUNICACAO_SOLICITADA) == NivelAutonomia.HUMAN_REQUIRED


@pytest.mark.parametrize('estado', [
    EstadoPacotePrestacao.INCOMPLETO,
    EstadoPacotePrestacao.EM_REVISAO,
    EstadoPacotePrestacao.BLOQUEADO,
])
def test_pacote_nao_pronto_nunca_gera_intencao_nem_execucao(estado):
    repo = RepositorioExecucoesEmMemoria()

    with pytest.raises(WiringPrestacaoComunicacaoError, match='somente pacote PRONTO'):
        _registrar(repo, pacote=_pacote(estado))

    assert repo.listar_todos() == []


def test_mesma_previa_e_mesmo_pacote_sao_idempotentes():
    repo = RepositorioExecucoesEmMemoria()

    primeira = _registrar(repo)
    segunda = _registrar(repo)

    assert primeira.intencao.intencao_id == segunda.intencao.intencao_id
    assert primeira.execucao.event_id == segunda.execucao.event_id
    assert len(repo.listar_todos()) == 1
    assert repo.listar_todos()[0].estado == EstadoExecucao.WAITING_GATE


def test_mudar_texto_ou_destinatario_cria_outra_previa_e_outra_intencao():
    repo = RepositorioExecucoesEmMemoria()
    original = _registrar(repo)
    texto_novo = _registrar(repo, texto='Outro texto autorizado.')
    destino_novo = _registrar(repo, destinatarios=('5515888888888',))

    assert original.intencao.preview.preview_id != texto_novo.intencao.preview.preview_id
    assert original.intencao.intencao_id != texto_novo.intencao.intencao_id
    assert original.intencao.preview.preview_id != destino_novo.intencao.preview.preview_id
    assert original.intencao.intencao_id != destino_novo.intencao.intencao_id
    assert len(repo.listar_todos()) == 3


def test_envelope_persistido_nao_contem_texto_nem_destinatario():
    repo = RepositorioExecucoesEmMemoria()
    resultado = _registrar(repo)
    evento_json = resultado.execucao.evento_json or ''

    assert '5515999999999' not in evento_json
    assert 'Prestação disponível para conferência.' not in evento_json
    assert resultado.intencao.preview.preview_id in evento_json


def test_identidade_do_pacote_independe_da_ordem_dos_itens():
    item_a = ItemInventarioPrestacao(
        documento_id='doc-a', tipo_documental='FGTS',
        cliente=_CLIENTE, competencia=_COMPETENCIA,
    )
    item_b = ItemInventarioPrestacao(
        documento_id='doc-b', tipo_documental='DCTFWeb',
        cliente=_CLIENTE, competencia=_COMPETENCIA,
    )
    pacote_a = PacotePrestacaoCliente(
        cliente=_CLIENTE, competencia=_COMPETENCIA,
        estado=EstadoPacotePrestacao.PRONTO,
        itens_incluidos=(item_a, item_b),
        tipos_obrigatorios=('FGTS', 'DCTFWeb'),
    )
    pacote_b = PacotePrestacaoCliente(
        cliente=_CLIENTE, competencia=_COMPETENCIA,
        estado=EstadoPacotePrestacao.PRONTO,
        itens_incluidos=(item_b, item_a),
        tipos_obrigatorios=('DCTFWeb', 'FGTS'),
    )

    assert identidade_pacote_prestacao(pacote_a) == identidade_pacote_prestacao(pacote_b)


def test_wiring_nao_expoe_transporte_como_parametro_de_execucao():
    """Regressão conceitual: o V1 shadow não recebe nem chama transporte."""
    repo = RepositorioExecucoesEmMemoria()
    resultado = _registrar(repo)
    assert resultado.execucao.acao == ''
    assert resultado.execucao.attempt == 0
