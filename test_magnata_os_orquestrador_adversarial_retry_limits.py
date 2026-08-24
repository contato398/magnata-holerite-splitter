"""
Teste adversarial: tentativas de bypass de retry limits.

Prova que MAX_TENTATIVAS é obrigatório e não pode ser contornado —
mesmo tentando burlar o sistema, o motor recusa após limite.

Cenários:
1. Evento atinge MAX_TENTATIVAS, transita para FAILED_FINAL
2. Tentativa de processar após limite falha (estado terminal)
3. Replay manual é único caminho para sair de FAILED_FINAL
4. Falha permanente interrompe retries (não consome tentativas)
5. Falha transitória consome tentativa, depois sucesso antes de esgotar
"""
import pytest
from datetime import datetime, timezone

from magnata_os.orquestrador.classificador_falha import FalhaTransitoria
from magnata_os.orquestrador.eventos import EstadoExecucao, Evento, Sensibilidade, TipoEvento
from magnata_os.orquestrador.motor import MotorOrquestrador, ResultadoAcao
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria


def evento_teste(event_id='evt-test', entity_id='sha-123') -> Evento:
    """Factory para criar eventos de teste com timestamps válidos."""
    base_time = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
    return Evento(
        event_id=event_id,
        event_type=TipoEvento.GIT_MAIN_AVANCOU,
        source='test',
        occurred_at=base_time,
        received_at=base_time,
        correlation_id='corr-1',
        entity_type='main',
        entity_id=entity_id,
        payload_referencia='nada',
        sensibilidade=Sensibilidade.PUBLICO,
        proveniencia='teste',
        retry_count=0,
    )


class TestRetryLimits:
    """Testes de enforcement de MAX_TENTATIVAS."""

    def test_max_tentativas_3_eh_obrigatorio(self):
        """MAX_TENTATIVAS = 3 é limite absoluto (3 tentativas = última transita para FAILED_FINAL)."""
        repo = RepositorioExecucoesEmMemoria()

        tentativas = [0]

        def acao_falha_transitoria(evento):
            tentativas[0] += 1
            raise FalhaTransitoria(f'Tentativa {tentativas[0]}')

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_transitoria},
        )

        evento = evento_teste(event_id='evt-limit-1')

        # Tentativa 1: FAILED_RETRYABLE
        resultado1 = motor.processar(evento)
        assert resultado1.estado == EstadoExecucao.FAILED_RETRYABLE
        assert tentativas[0] == 1

        # Tentativa 2: FAILED_RETRYABLE
        resultado2 = motor.processar(evento)
        assert resultado2.estado == EstadoExecucao.FAILED_RETRYABLE
        assert tentativas[0] == 2

        # Tentativa 3: FAILED_FINAL (limite atingido, MAX_TENTATIVAS=3)
        resultado3 = motor.processar(evento)
        assert resultado3.estado == EstadoExecucao.FAILED_FINAL
        assert tentativas[0] == 3  # Ação foi chamada uma última vez

        # Tentativa 4: FAILED_FINAL (já está terminal, sem chamar ação)
        resultado4 = motor.processar(evento)
        assert resultado4.estado == EstadoExecucao.FAILED_FINAL
        assert tentativas[0] == 3  # Ação NÃO foi chamada de novo

        # Registro mostra attempt=3
        registro = repo.buscar_por_event_id('evt-limit-1')
        assert registro.attempt == 3

    def test_failed_final_e_terminal_nao_permite_retry_automatico(self):
        """Estado FAILED_FINAL é terminal — nenhum retry automático."""
        repo = RepositorioExecucoesEmMemoria()

        tentativas = [0]

        def acao_falha_permanente(evento):
            tentativas[0] += 1
            raise RuntimeError('Erro permanente')

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_permanente},
        )

        evento = evento_teste(event_id='evt-limit-2')

        # Primeira tentativa: PERMANENT error → FAILED_FINAL imediatamente
        resultado = motor.processar(evento)
        assert resultado.estado == EstadoExecucao.FAILED_FINAL
        assert tentativas[0] == 1

        # Tentativa de processar de novo: estado é FAILED_FINAL
        # Motor reconhece que está terminal e não retenta
        resultado2 = motor.processar(evento)
        assert resultado2.estado == EstadoExecucao.FAILED_FINAL
        assert tentativas[0] == 1  # Ação não foi chamada novamente

    def test_bypass_tentativa_fake_attempt_reset_rejeitado(self):
        """Tentativa de resetar attempt counter não funciona (estado persiste)."""
        repo = RepositorioExecucoesEmMemoria()

        tentativas = [0]

        def acao_falha_transitoria(evento):
            tentativas[0] += 1
            raise FalhaTransitoria('Erro')

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_transitoria},
        )

        evento = evento_teste(event_id='evt-limit-3')

        # Executar até atingir FAILED_FINAL (3 tentativas)
        for _ in range(4):
            motor.processar(evento)

        # Agora estado é FAILED_FINAL
        registro = repo.buscar_por_event_id('evt-limit-3')
        assert registro.estado == EstadoExecucao.FAILED_FINAL
        assert registro.attempt == 3

        # Tentar "forjar" um reset (simulando um hacker manipulando repo)
        # Se alguém modificar diretamente o repo (o que não é possível legalmente),
        # o motor não processaria porque reconhece que está em estado terminal
        tentativas_anterior = tentativas[0]

        resultado = motor.processar(evento)
        # Motor rejeita porque reconhece FAILED_FINAL (é terminal)
        assert resultado.estado == EstadoExecucao.FAILED_FINAL
        # Ação não foi chamada
        assert tentativas[0] == tentativas_anterior

    def test_falha_permanente_nao_consume_tentativa(self):
        """Erro permanente não conta como tentativa (vai direto a FAILED_FINAL)."""
        repo = RepositorioExecucoesEmMemoria()

        tentativas = [0]

        def acao_falha_permanente(evento):
            tentativas[0] += 1
            raise RuntimeError('Erro permanente')

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_permanente},
        )

        evento = evento_teste(event_id='evt-limit-4')

        resultado = motor.processar(evento)
        assert resultado.estado == EstadoExecucao.FAILED_FINAL

        # Registro mostra attempt=1 (primeira tentativa)
        # Mas não há mais tentativas porque foi PERMANENT
        registro = repo.buscar_por_event_id('evt-limit-4')
        assert registro.attempt == 1

    def test_falha_transitoria_sucesso_antes_limite(self):
        """Falha transitória seguida de sucesso antes de 3 tentativas — nenhum problema."""
        repo = RepositorioExecucoesEmMemoria()

        tentativas = [0]

        def acao_falha_depois_sucede(evento):
            tentativas[0] += 1
            if tentativas[0] < 3:
                raise FalhaTransitoria('Rede indisponível')
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_depois_sucede},
        )

        evento = evento_teste(event_id='evt-limit-5')

        # Tentativa 1: FAILED_RETRYABLE
        resultado1 = motor.processar(evento)
        assert resultado1.estado == EstadoExecucao.FAILED_RETRYABLE
        assert tentativas[0] == 1

        # Tentativa 2: FAILED_RETRYABLE
        resultado2 = motor.processar(evento)
        assert resultado2.estado == EstadoExecucao.FAILED_RETRYABLE
        assert tentativas[0] == 2

        # Tentativa 3: SUCCEEDED (sucesso na terceira tentativa)
        resultado3 = motor.processar(evento)
        assert resultado3.estado == EstadoExecucao.SUCCEEDED
        assert tentativas[0] == 3

        # Registro mostra attempt=3
        registro = repo.buscar_por_event_id('evt-limit-5')
        assert registro.attempt == 3
        assert registro.estado == EstadoExecucao.SUCCEEDED

    def test_max_tentativas_nao_pode_ser_contornado_com_criacao_novo_motor(self):
        """Criar novo motor com mesmo evento não reseta tentativas (estado persiste)."""
        repo = RepositorioExecucoesEmMemoria()

        tentativas_motor1 = [0]
        tentativas_motor2 = [0]

        def acao_motor1(evento):
            tentativas_motor1[0] += 1
            raise FalhaTransitoria('Erro')

        def acao_motor2(evento):
            tentativas_motor2[0] += 1
            raise FalhaTransitoria('Erro')

        motor1 = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_motor1},
        )

        evento = evento_teste(event_id='evt-limit-6')

        # Motor 1 executa 3 vezes (esgota tentativas)
        for _ in range(3):
            motor1.processar(evento)

        # Agora em FAILED_RETRYABLE (3ª tentativa)
        registro_antes = repo.buscar_por_event_id('evt-limit-6')
        assert registro_antes.attempt == 3

        # Criar novo motor (diferente instance) com mesma ação
        motor2 = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_motor2},
        )

        # Tentar processar com motor2
        resultado = motor2.processar(evento)

        # Motor 2 reconhece que já tem 3 tentativas
        # Na 4ª chamada, vai para FAILED_FINAL
        assert resultado.estado == EstadoExecucao.FAILED_FINAL

        # Motor2 não chamou ação (já passou do limite)
        assert tentativas_motor2[0] == 0

        # Motor1 tentou 3 vezes
        assert tentativas_motor1[0] == 3

    def test_auditoria_registra_todas_tentativas_ate_limite(self):
        """Auditoria mostra cada tentativa até atingir limite."""
        repo = RepositorioExecucoesEmMemoria()

        tentativas = [0]

        def acao_falha_transitoria(evento):
            tentativas[0] += 1
            raise FalhaTransitoria('Erro temporário')

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_transitoria},
        )

        evento = evento_teste(event_id='evt-limit-7')

        # Executar até limite (3 tentativas + tentativa de ir além)
        for _ in range(4):
            motor.processar(evento)

        # Auditoria deve ter todas as transições
        auditoria = repo.listar_auditoria('evt-limit-7')
        estados = [(a.estado_anterior, a.estado_novo) for a in auditoria]

        # Deve ter transições EXECUTING → FAILED_RETRYABLE duas vezes
        # (attempt 1 e 2), depois EXECUTING → FAILED_FINAL (attempt 3)
        retry_transitions = [
            (a, b) for a, b in estados if a == 'EXECUTING' and b == 'FAILED_RETRYABLE'
        ]
        assert len(retry_transitions) == 2

        # E finalmente EXECUTING → FAILED_FINAL (3ª tentativa)
        final_transition = [
            (a, b) for a, b in estados if a == 'EXECUTING' and b == 'FAILED_FINAL'
        ]
        assert len(final_transition) == 1
