"""Composição completa da Prestação até PlanoDisparo, sempre sem transporte."""
import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from magnata_os.classificacao.contratos import ReferenciaCanonica
from magnata_os.classificacao.pacote_prestacao import (
    EstadoPacotePrestacao,
    PacotePrestacaoCliente,
)
from magnata_os.classificacao.prestacao_readiness import ItemInventarioPrestacao
from magnata_os.orquestrador.autorizacao_gate import (
    AutorizacaoGateError,
    ConflitoDecisaoGateError,
    DecisaoGate,
    RepositorioAutorizacoesGateEmMemoria,
    registrar_decisao_gate_shadow,
)
from magnata_os.orquestrador.eventos import EstadoExecucao, TipoEvento
from magnata_os.orquestrador.plano_comunicacao import (
    ConteudoItem,
    PlanoComunicacaoError,
)
from magnata_os.orquestrador.politica_comunicacao import (
    ItemComunicacao,
    hash_conteudo_comunicacao,
    montar_preview_comunicacao,
)
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria
from magnata_os.orquestrador.wiring_prestacao_comunicacao_shadow import (
    WiringPrestacaoComunicacaoError,
    registrar_intencao_comunicacao_shadow,
)
from magnata_os.orquestrador.wiring_prestacao_orquestrador_postgres_shadow import (
    materializar_prestacao_orquestrador_shadow,
)

_INSTANTE = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
_TEXTO = 'Comunicação sintética para validação do gate.'
_MIDIA = b'midia-prestacao-totalmente-sintetica-v1'
_DESTINATARIO = 'destinatario:sintetico:001'


def _pacote(estado=EstadoPacotePrestacao.PRONTO):
    cliente = ReferenciaCanonica('CLIENTE', 'cliente-sintetico-001')
    competencia = ReferenciaCanonica('COMPETENCIA', '2099-01')
    return PacotePrestacaoCliente(
        cliente=cliente,
        competencia=competencia,
        estado=estado,
        itens_incluidos=(ItemInventarioPrestacao(
            documento_id='documento-sintetico-001',
            tipo_documental='DOCUMENTO_SINTETICO',
            cliente=cliente,
            competencia=competencia,
        ),),
        tipos_obrigatorios=('DOCUMENTO_SINTETICO',),
    )


def _item(conteudo=_MIDIA):
    return ItemComunicacao(
        'documento', 'arquivo-sintetico.bin', hash_conteudo_comunicacao(conteudo),
    )


def _preview_id(conteudo=_MIDIA, texto=_TEXTO):
    return montar_preview_comunicacao(
        destinatarios=(_DESTINATARIO,), texto=texto, itens=(_item(conteudo),),
        assinatura=False, comprovante=True,
    ).preview_id


def _executar(repo_exec=None, repo_auth=None, **overrides):
    repo_exec = repo_exec or RepositorioExecucoesEmMemoria()
    repo_auth = repo_auth or RepositorioAutorizacoesGateEmMemoria()
    kwargs = dict(
        pacote=_pacote(),
        repositorio_execucoes=repo_exec,
        repositorio_autorizacoes=repo_auth,
        destinatarios=(_DESTINATARIO,),
        texto=_TEXTO,
        itens=(_item(),),
        conteudos=(ConteudoItem('documento', 'arquivo-sintetico.bin', _MIDIA),),
        assinatura=False,
        comprovante=True,
        preview_id_autorizado=_preview_id(),
        ator_referencia='ator:sintetico:001',
        proveniencia_autorizacao='e2e_shadow_sintetico',
        instante=_INSTANTE,
    )
    kwargs.update(overrides)
    return materializar_prestacao_orquestrador_shadow(**kwargs), repo_exec, repo_auth


def test_fluxo_pronto_chega_ao_plano_e_para_em_waiting_gate():
    resultado, repo_exec, repo_auth = _executar()

    registro = resultado.intencao.execucao
    assert registro.event_type == TipoEvento.COMUNICACAO_SOLICITADA.value
    assert registro.estado == EstadoExecucao.WAITING_GATE
    assert registro.attempt == 0
    assert registro.acao == ''
    assert repo_exec.buscar_por_event_id(registro.event_id) == registro
    assert repo_auth.buscar(registro.event_id, resultado.plano.preview_id) == resultado.autorizacao
    assert resultado.plano.plano.preview_id == resultado.autorizacao.preview_id
    assert resultado.plano.plano.acoes[0].conteudo == _MIDIA


@pytest.mark.parametrize('estado', [
    EstadoPacotePrestacao.INCOMPLETO,
    EstadoPacotePrestacao.EM_REVISAO,
    EstadoPacotePrestacao.BLOQUEADO,
])
def test_pacote_nao_pronto_nao_gera_comunicacao(estado):
    repo_exec = RepositorioExecucoesEmMemoria()
    repo_auth = RepositorioAutorizacoesGateEmMemoria()

    with pytest.raises(WiringPrestacaoComunicacaoError, match='somente pacote PRONTO'):
        _executar(repo_exec, repo_auth, pacote=_pacote(estado))

    assert repo_exec.listar_todos() == []
    assert repo_auth.listar_por_evento('qualquer-evento') == []


def test_evento_e_autorizacao_sao_deterministicos_e_idempotentes():
    repo_exec = RepositorioExecucoesEmMemoria()
    repo_auth = RepositorioAutorizacoesGateEmMemoria()

    primeiro, _, _ = _executar(repo_exec, repo_auth)
    segundo, _, _ = _executar(repo_exec, repo_auth)

    assert primeiro.intencao.execucao.event_id == segundo.intencao.execucao.event_id
    assert primeiro.autorizacao == segundo.autorizacao
    assert primeiro.plano.plano == segundo.plano.plano
    assert len(repo_exec.listar_todos()) == 1
    assert len(repo_auth.listar_por_evento(primeiro.autorizacao.event_id)) == 1


def test_autorizacao_sem_preview_exato_falha_antes_de_persistir_fato():
    repo_exec = RepositorioExecucoesEmMemoria()
    repo_auth = RepositorioAutorizacoesGateEmMemoria()

    with pytest.raises(AutorizacaoGateError, match='preview exato'):
        _executar(
            repo_exec, repo_auth, preview_id_autorizado='preview-incorreto',
        )

    registro = repo_exec.listar_todos()[0]
    assert registro.estado == EstadoExecucao.WAITING_GATE
    assert repo_auth.listar_por_evento(registro.event_id) == []


def test_decisao_conflitante_e_recusada_sem_sobrescrever_original():
    repo_exec = RepositorioExecucoesEmMemoria()
    repo_auth = RepositorioAutorizacoesGateEmMemoria()
    intencao = registrar_intencao_comunicacao_shadow(
        pacote=_pacote(), repositorio=repo_exec,
        destinatarios=(_DESTINATARIO,), texto=_TEXTO, itens=(_item(),),
        assinatura=False, comprovante=True, instante=_INSTANTE,
    )
    original = registrar_decisao_gate_shadow(
        repositorio_execucoes=repo_exec,
        repositorio_autorizacoes=repo_auth,
        event_id=intencao.execucao.event_id,
        preview_id=intencao.intencao.preview.preview_id,
        decisao=DecisaoGate.RECUSADO,
        ator_referencia='ator:sintetico:001',
        proveniencia='e2e_shadow_sintetico',
        instante=_INSTANTE,
    )

    with pytest.raises(ConflitoDecisaoGateError):
        _executar(repo_exec, repo_auth)

    assert repo_auth.buscar(original.event_id, original.preview_id) == original


def test_texto_ou_midia_alterados_apos_preview_invalidam_plano():
    with pytest.raises(AutorizacaoGateError, match='preview exato'):
        _executar(texto='Texto adulterado depois do preview.')

    with pytest.raises(PlanoComunicacaoError, match='diverge da prévia'):
        _executar(conteudos=(ConteudoItem(
            'documento', 'arquivo-sintetico.bin', b'midia-adulterada',
        ),))


def test_envelope_persistido_nao_contem_destinatario_texto_ator_ou_midia():
    resultado, _, _ = _executar()
    envelope = resultado.intencao.execucao.evento_json or ''

    for sensivel in (_DESTINATARIO, _TEXTO, 'ator:sintetico:001', _MIDIA.decode()):
        assert sensivel not in envelope


def test_modulo_e_estruturalmente_sem_transporte():
    fonte = Path(
        'magnata_os/orquestrador/wiring_prestacao_orquestrador_postgres_shadow.py'
    ).read_text(encoding='utf-8')

    arvore = ast.parse(fonte)
    imports = {
        alias.name
        for no in ast.walk(arvore)
        if isinstance(no, (ast.Import, ast.ImportFrom))
        for alias in no.names
    }

    assert 'executar_plano_disparo' not in imports
    assert not any('transporte' in nome.lower() for nome in imports)
    assert not any('evolution' in nome.lower() for nome in imports)
    assert '/whatsapp/enviar-' not in fonte
