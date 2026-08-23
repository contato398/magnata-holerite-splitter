"""
Testes do nucleo do Orquestrador -- envelope de evento, maquina de
estados, politica de autonomia, classificacao de falha.

Cobre, explicitamente: evento repetido, retry, timeout/falha
transitoria, entrega duplicada, evento fora de ordem (transicao
invalida), fail-safe da politica de autonomia. Nenhum destes acessa
rede, disco alem de SQLite em tmp_path, Airtable ou producao.
"""
from datetime import timedelta

import pytest

from magnata_os.orquestrador.classificador_falha import (
    ClasseFalha, FalhaGateHumano, FalhaTransitoria, classificar,
)
from magnata_os.orquestrador.eventos import (
    Evento, EstadoExecucao, Sensibilidade, TipoEvento, TransicaoInvalida,
    agora, novo_event_id, validar_transicao,
)
from magnata_os.orquestrador.politica_autonomia import (
    NivelAutonomia, nivel_para, pode_executar_automaticamente,
)
from magnata_os.orquestrador.repositorio_execucoes import (
    RegistroExecucao, RepositorioExecucoesEmMemoria, RepositorioExecucoesSQLite,
)


def _evento(event_id='ev-1', tipo=TipoEvento.GIT_MAIN_AVANCOU, sensibilidade=Sensibilidade.PUBLICO,
            payload='abc123'):
    quando = agora()
    return Evento(
        event_id=event_id, event_type=tipo, source='teste',
        occurred_at=quando, received_at=quando, correlation_id='corr-1',
        entity_type='commit', entity_id='abc123', payload_referencia=payload,
        sensibilidade=sensibilidade,
    )


# ============================================================================
# Envelope de evento
# ============================================================================

def test_event_id_vazio_e_rejeitado():
    with pytest.raises(ValueError):
        _evento(event_id='')


def test_payload_grande_demais_para_sensibilidade_nao_publica_e_rejeitado():
    with pytest.raises(ValueError):
        _evento(sensibilidade=Sensibilidade.SENSIVEL, payload='x' * 501)


def test_payload_grande_e_permitido_quando_sensibilidade_e_publica():
    # sha/branch/PR number podem ser longos e nao sao PII -- so o
    # tamanho nao decide sozinho, a sensibilidade declarada decide.
    _evento(sensibilidade=Sensibilidade.PUBLICO, payload='x' * 501)  # nao levanta


def test_novo_event_id_e_deterministico():
    quando = agora()
    a = novo_event_id(TipoEvento.GIT_MAIN_AVANCOU, 'sha1', quando)
    b = novo_event_id(TipoEvento.GIT_MAIN_AVANCOU, 'sha1', quando)
    assert a == b, 'mesmo (tipo, entidade, instante) tem que produzir o mesmo event_id'


def test_novo_event_id_muda_com_entidade_diferente():
    quando = agora()
    a = novo_event_id(TipoEvento.GIT_MAIN_AVANCOU, 'sha1', quando)
    b = novo_event_id(TipoEvento.GIT_MAIN_AVANCOU, 'sha2', quando)
    assert a != b


# ============================================================================
# Maquina de estados -- transicao invalida = evento fora de ordem
# ============================================================================

def test_transicao_valida_nao_levanta():
    validar_transicao(EstadoExecucao.RECEIVED, EstadoExecucao.VALIDATED)


def test_transicao_invalida_e_detectada():
    with pytest.raises(TransicaoInvalida):
        validar_transicao(EstadoExecucao.RECEIVED, EstadoExecucao.SUCCEEDED)


def test_estado_terminal_nao_aceita_nenhuma_transicao():
    for terminal in (EstadoExecucao.SUCCEEDED, EstadoExecucao.FAILED_FINAL,
                      EstadoExecucao.IGNORED, EstadoExecucao.SUPERSEDED):
        with pytest.raises(TransicaoInvalida):
            validar_transicao(terminal, EstadoExecucao.EXECUTING)


def test_waiting_gate_e_terminal_para_o_motor():
    """So acao humana fora do motor avanca um WAITING_GATE -- o motor
    nunca reenfileira sozinho."""
    with pytest.raises(TransicaoInvalida):
        validar_transicao(EstadoExecucao.WAITING_GATE, EstadoExecucao.EXECUTING)


# ============================================================================
# Politica de autonomia -- fail-safe, nunca fail-open
# ============================================================================

def test_tipos_com_politica_declarada_tem_nivel_esperado():
    assert nivel_para(TipoEvento.GIT_MAIN_AVANCOU) == NivelAutonomia.EXECUTE_SAFE
    assert nivel_para(TipoEvento.ESTRUTURA_CODIGO_DIVERGIU) == NivelAutonomia.PROPOSE


def test_pode_executar_automaticamente_so_para_execute_safe():
    assert pode_executar_automaticamente(TipoEvento.GIT_MAIN_AVANCOU) is True
    assert pode_executar_automaticamente(TipoEvento.ESTRUTURA_CODIGO_DIVERGIU) is False


def test_tipo_sem_politica_declarada_e_sempre_human_required(monkeypatch):
    """Prova o fail-safe removendo a entrada da politica de um tipo que
    normalmente e EXECUTE_SAFE -- se a funcao tivesse qualquer caminho
    de 'nao sei, deve ser seguro', este teste reprovaria."""
    import magnata_os.orquestrador.politica_autonomia as mod
    politica_reduzida = dict(mod._POLITICA)
    politica_reduzida.pop(TipoEvento.GIT_MAIN_AVANCOU)
    monkeypatch.setattr(mod, '_POLITICA', politica_reduzida)

    assert nivel_para(TipoEvento.GIT_MAIN_AVANCOU) == NivelAutonomia.HUMAN_REQUIRED
    assert pode_executar_automaticamente(TipoEvento.GIT_MAIN_AVANCOU) is False


# ============================================================================
# Classificacao de falha
# ============================================================================

def test_falha_transitoria_e_classificada_como_transient():
    assert classificar(FalhaTransitoria('timeout')) == ClasseFalha.TRANSIENT


def test_falha_gate_humano_e_classificada_e_nunca_vira_retry():
    assert classificar(FalhaGateHumano('cruzou app.py')) == ClasseFalha.HUMAN_GATE


def test_value_error_e_invalid_input():
    assert classificar(ValueError('malformado')) == ClasseFalha.INVALID_INPUT


def test_excecao_desconhecida_e_permanente_nunca_transient():
    """Fail-safe: um tipo de excecao nunca visto antes NAO vira retry
    automatico (retry de algo desconhecido pode repetir dano)."""
    class ErroNuncaVisto(Exception):
        pass

    assert classificar(ErroNuncaVisto('???')) == ClasseFalha.PERMANENT


# ============================================================================
# Repositorio -- em memoria e SQLite tem que se comportar identico
# ============================================================================

def _registro(event_id='ev-1', estado=EstadoExecucao.SUCCEEDED):
    quando = agora()
    return RegistroExecucao(
        event_id=event_id, event_type='GIT_MAIN_AVANCOU', estado=estado,
        nivel_autonomia=4, acao='GIT_MAIN_AVANCOU', resultado='sucesso',
        evidencia='ok', attempt=1, next_retry_at=None,
        last_error_classe=None, last_error_at=None,
        criado_em=quando, atualizado_em=quando,
    )


@pytest.mark.parametrize('fabrica_repo', [
    lambda tmp_path: RepositorioExecucoesEmMemoria(),
    lambda tmp_path: RepositorioExecucoesSQLite(tmp_path / 'execucoes.db'),
])
def test_repositorio_busca_e_salva_registro(tmp_path, fabrica_repo):
    repo = fabrica_repo(tmp_path)
    assert repo.buscar_por_event_id('ev-1') is None

    repo.salvar(_registro())
    encontrado = repo.buscar_por_event_id('ev-1')
    assert encontrado is not None
    assert encontrado.estado == EstadoExecucao.SUCCEEDED
    assert encontrado.evidencia == 'ok'


@pytest.mark.parametrize('fabrica_repo', [
    lambda tmp_path: RepositorioExecucoesEmMemoria(),
    lambda tmp_path: RepositorioExecucoesSQLite(tmp_path / 'execucoes.db'),
])
def test_repositorio_salvar_de_novo_atualiza_nao_duplica(tmp_path, fabrica_repo):
    repo = fabrica_repo(tmp_path)
    repo.salvar(_registro(estado=EstadoExecucao.EXECUTING))
    repo.salvar(_registro(estado=EstadoExecucao.SUCCEEDED))

    assert len(repo.listar_todos()) == 1
    assert repo.buscar_por_event_id('ev-1').estado == EstadoExecucao.SUCCEEDED
