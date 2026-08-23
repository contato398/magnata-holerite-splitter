"""
Testes ponta a ponta do motor -- EVENTO -> NORMALIZACAO -> DEDUPLICACAO
-> CLASSIFICACAO -> POLITICA -> ACAO -> VALIDACAO -> REGISTRO.

Os 5 cenarios exigidos (missao "Grande Orquestrador V1"): sucesso,
duplicata, falha temporaria (com retry), falha definitiva, gate humano.
Mais: acao que tenta escrever em caminho proibido (bloqueada pelo
motor, nao so pela propria acao), e um teste de integracao REAL com a
unica Acao de producao (atualizar_auto_fact), sem mock nenhum.
"""
import os
from datetime import datetime, timezone

import pytest

from magnata_os.orquestrador.classificador_falha import FalhaGateHumano, FalhaTransitoria
from magnata_os.orquestrador.eventos import Evento, EstadoExecucao, Sensibilidade, TipoEvento
from magnata_os.orquestrador.motor import AcaoProibida, MotorOrquestrador, ResultadoAcao
from magnata_os.orquestrador.observabilidade import Observador
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria


def _evento(event_id, tipo=TipoEvento.GIT_MAIN_AVANCOU):
    quando = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    return Evento(
        event_id=event_id, event_type=tipo, source='teste',
        occurred_at=quando, received_at=quando, correlation_id='corr',
        entity_type='commit', entity_id='sha-teste',
        payload_referencia='sha-teste', sensibilidade=Sensibilidade.PUBLICO,
    )


def _motor(acoes, repo=None):
    repo = repo or RepositorioExecucoesEmMemoria()
    obs = Observador()
    return MotorOrquestrador(repo, acoes, observador=obs), repo, obs


# ============================================================================
# 1. SUCESSO
# ============================================================================

def test_e2e_sucesso():
    chamadas = []

    def acao_ok(evento):
        chamadas.append(evento.event_id)
        return ResultadoAcao(sucesso=True, evidencia='ok', caminhos_escritos=('ESTADO.json',))

    motor, repo, obs = _motor({TipoEvento.GIT_MAIN_AVANCOU.value: acao_ok})
    registro = motor.processar(_evento('ev-sucesso'))

    assert registro.estado == EstadoExecucao.SUCCEEDED
    assert registro.evidencia == 'ok'
    assert len(chamadas) == 1
    assert obs.resumo()['acao_sucesso'] == 1


# ============================================================================
# 2. DUPLICATA -- mesmo evento processado 2x nunca executa a acao 2x
# ============================================================================

def test_e2e_duplicata_nunca_executa_a_acao_duas_vezes():
    chamadas = []

    def acao_ok(evento):
        chamadas.append(evento.event_id)
        return ResultadoAcao(sucesso=True, evidencia='ok')

    motor, repo, obs = _motor({TipoEvento.GIT_MAIN_AVANCOU.value: acao_ok})
    evento = _evento('ev-dup')

    r1 = motor.processar(evento)
    r2 = motor.processar(evento)
    r3 = motor.processar(evento)

    assert len(chamadas) == 1, 'a acao real so pode ter sido chamada uma vez'
    assert r1.estado == r2.estado == r3.estado == EstadoExecucao.SUCCEEDED
    assert obs.resumo().get('evento_duplicado_ignorado') == 2


# ============================================================================
# 3. FALHA TEMPORARIA -- retry com backoff, depois sucesso
# ============================================================================

def test_e2e_falha_transitoria_tenta_de_novo_e_depois_sucede():
    tentativas = {'n': 0}

    def acao_instavel(evento):
        tentativas['n'] += 1
        if tentativas['n'] < 2:
            raise FalhaTransitoria('timeout simulado')
        return ResultadoAcao(sucesso=True, evidencia=f"ok na tentativa {tentativas['n']}")

    motor, repo, obs = _motor({TipoEvento.GIT_MAIN_AVANCOU.value: acao_instavel})
    evento = _evento('ev-retry')

    r1 = motor.processar(evento)
    assert r1.estado == EstadoExecucao.FAILED_RETRYABLE
    assert r1.attempt == 1
    assert r1.next_retry_at is not None
    assert r1.last_error_classe == 'TRANSIENT'

    # o "agendador" (fora do motor) decide quando tentar de novo --
    # aqui simulamos isso processando o MESMO evento outra vez.
    r2 = motor.processar(evento)
    assert r2.estado == EstadoExecucao.SUCCEEDED
    assert tentativas['n'] == 2
    assert obs.resumo()['falha_transitoria'] == 1


def test_e2e_falha_transitoria_esgota_tentativas_vira_final():
    def acao_sempre_falha(evento):
        raise FalhaTransitoria('timeout sempre')

    motor, repo, obs = _motor({TipoEvento.GIT_MAIN_AVANCOU.value: acao_sempre_falha})
    evento = _evento('ev-esgota')

    r = None
    for _ in range(5):
        r = motor.processar(evento)
        if r.estado in (EstadoExecucao.SUCCEEDED, EstadoExecucao.FAILED_FINAL):
            break

    assert r.estado == EstadoExecucao.FAILED_FINAL
    assert r.attempt == 3, 'MAX_TENTATIVAS = 3 -- nunca retry infinito'


# ============================================================================
# 4. FALHA DEFINITIVA -- erro nao classificado como transitorio nunca tenta de novo
# ============================================================================

def test_e2e_falha_permanente_nao_tenta_de_novo():
    chamadas = []

    def acao_com_bug(evento):
        chamadas.append(1)
        raise RuntimeError('bug real, nao adianta tentar de novo')

    motor, repo, obs = _motor({TipoEvento.GIT_MAIN_AVANCOU.value: acao_com_bug})
    registro = motor.processar(_evento('ev-permanente'))

    assert registro.estado == EstadoExecucao.FAILED_FINAL
    assert registro.attempt == 1
    assert len(chamadas) == 1

    # processar de novo o MESMO evento nao rechama a acao -- ja e terminal.
    motor.processar(_evento('ev-permanente'))
    assert len(chamadas) == 1


# ============================================================================
# 5. GATE HUMANO -- nivel != EXECUTE_SAFE nunca executa a acao
# ============================================================================

def test_e2e_nivel_propose_nunca_executa_acao_automaticamente():
    chamadas = []

    def acao_que_nunca_deveria_rodar(evento):
        chamadas.append(1)
        return ResultadoAcao(sucesso=True, evidencia='nao deveria acontecer')

    motor, repo, obs = _motor({TipoEvento.ESTRUTURA_CODIGO_DIVERGIU.value: acao_que_nunca_deveria_rodar})
    registro = motor.processar(_evento('ev-gate', tipo=TipoEvento.ESTRUTURA_CODIGO_DIVERGIU))

    assert registro.estado == EstadoExecucao.WAITING_GATE
    assert len(chamadas) == 0, 'PROPOSE nunca pode executar a acao sozinho'
    assert obs.resumo()['gate_humano'] == 1


def test_e2e_falha_gate_humano_levantada_pela_acao_vira_waiting_state_correto():
    """Mesmo em EXECUTE_SAFE, se a ACAO descobrir em runtime que cruzaria
    um gate (FalhaGateHumano), o motor classifica como HUMAN_GATE e NAO
    tenta de novo -- diferente de TRANSIENT."""
    def acao_que_descobre_gate(evento):
        raise FalhaGateHumano('agiria sobre producao -- gate')

    motor, repo, obs = _motor({TipoEvento.GIT_MAIN_AVANCOU.value: acao_que_descobre_gate})
    registro = motor.processar(_evento('ev-gate-runtime'))

    assert registro.estado == EstadoExecucao.FAILED_FINAL
    assert registro.last_error_classe == 'HUMAN_GATE'
    assert registro.attempt == 1


def test_e2e_tipo_sem_acao_registrada_vira_gate_por_omissao():
    """EXECUTE_SAFE mas ninguem registrou a Acao -- nunca inventa
    comportamento, vira gate."""
    motor, repo, obs = _motor({})  # nenhuma acao registrada
    registro = motor.processar(_evento('ev-sem-acao'))

    assert registro.estado == EstadoExecucao.WAITING_GATE
    assert 'sem acao registrada' in registro.resultado


# ============================================================================
# Defesa em profundidade -- Acao que escreve em caminho proibido
# ============================================================================

def test_e2e_acao_que_escreve_em_decisions_md_e_bloqueada_pelo_motor():
    def acao_maliciosa_ou_com_bug(evento):
        return ResultadoAcao(
            sucesso=True, evidencia='???',
            caminhos_escritos=('docs/magnata-os/central-command/DECISIONS.md',),
        )

    motor, repo, obs = _motor({TipoEvento.GIT_MAIN_AVANCOU.value: acao_maliciosa_ou_com_bug})

    with pytest.raises(AcaoProibida):
        motor.processar(_evento('ev-proibido'))

    registro = repo.buscar_por_event_id('ev-proibido')
    assert registro.estado == EstadoExecucao.FAILED_FINAL
    assert 'BLOQUEADA' in registro.resultado
    assert obs.resumo()['acao_bloqueada_caminho_proibido'] == 1


def test_e2e_acao_que_escreve_em_app_py_e_bloqueada():
    def acao(evento):
        return ResultadoAcao(sucesso=True, evidencia='???', caminhos_escritos=('app.py',))

    motor, repo, obs = _motor({TipoEvento.GIT_MAIN_AVANCOU.value: acao})
    with pytest.raises(AcaoProibida):
        motor.processar(_evento('ev-app-py'))


# ============================================================================
# Verificacao adversarial: prova que a checagem de caminho proibido
# realmente esta ligada -- nao so declarada.
# ============================================================================

def test_e2e_acao_que_so_escreve_estado_json_passa_normalmente():
    """Controle negativo do teste acima -- garante que a checagem nao
    bloqueia escrita legitima em AUTO_FACT."""
    def acao(evento):
        return ResultadoAcao(
            sucesso=True, evidencia='ok',
            caminhos_escritos=('docs/magnata-os/central-command/ESTADO.json',),
        )

    motor, repo, obs = _motor({TipoEvento.GIT_MAIN_AVANCOU.value: acao})
    registro = motor.processar(_evento('ev-legitimo'))
    assert registro.estado == EstadoExecucao.SUCCEEDED


# ============================================================================
# Integracao real -- a unica Acao de producao, sem nenhum mock
# ============================================================================

@pytest.mark.skipif(
    os.environ.get('RODAR_INTEGRACAO_REAL_ORQUESTRADOR') != '1',
    reason=(
        'PERIGO DE RECURSAO se rodar por omissao: esta Acao real chama '
        'sensor.coletar(com_testes=True), que spawna `pytest -q --tb=no` '
        'sobre o repositorio INTEIRO -- que inclui este proprio arquivo. '
        'Sem este guard, uma suite normal dispara este teste, que spawna '
        'uma suite completa, que dispara este teste de novo, '
        'recursivamente, ate esgotar processos (visto e corrigido nesta '
        'mesma sessao). So roda com RODAR_INTEGRACAO_REAL_ORQUESTRADOR=1 '
        'explicito, nunca em pytest padrao nem dentro do proprio sensor.'
    ),
)
def test_integracao_real_atualizar_auto_fact_end_to_end(tmp_path, monkeypatch):
    """Sem mock: roda o sensor de verdade (com a suite completa) contra
    o repositorio real e escreve o ESTADO.json de verdade -- depois
    restaura o arquivo, para nao deixar o worktree sujo entre testes."""
    import json
    from magnata_os.orquestrador.acoes import atualizar_auto_fact

    # CRITICO: a Acao real dispara `subprocess.run(pytest ...)` sem
    # `env=` proprio -- herda os.environ NO MOMENTO DA CHAMADA. Se este
    # guard continuasse setado, o pytest aninhado tambem rodaria (e
    # pularia) este mesmo teste, mas o ponto e que ele reprocessaria a
    # suite inteira de novo dentro da suite -- e se o guard nao fosse
    # removido aqui, a proxima camada tambem executaria este teste,
    # recursivamente. Visto e corrigido nesta sessao: sem isto, um
    # `timeout 90` matou o processo sem nunca terminar.
    monkeypatch.delenv('RODAR_INTEGRACAO_REAL_ORQUESTRADOR', raising=False)

    caminho_estado = atualizar_auto_fact.RAIZ / 'docs' / 'magnata-os' / 'central-command' / 'ESTADO.json'
    original = caminho_estado.read_text(encoding='utf-8')
    try:
        evento = atualizar_auto_fact.detectar_evento()
        if evento is None:
            pytest.skip('ESTADO.json ja reflete o main_sha atual -- nada para detectar agora')

        motor, repo, obs = _motor({TipoEvento.GIT_MAIN_AVANCOU.value: atualizar_auto_fact.executar})
        registro = motor.processar(evento)

        assert registro.estado == EstadoExecucao.SUCCEEDED
        novo = json.loads(caminho_estado.read_text(encoding='utf-8'))
        assert novo['main_sha'] == evento.entity_id
        assert 'testes' in novo, 'a acao real roda com --com-testes, nunca perde a baseline'
    finally:
        caminho_estado.write_text(original, encoding='utf-8')
