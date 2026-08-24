"""
Teste de replay controlado: manual, explícito, rastreado.

Prova que eventos que falharam permanentemente podem ser
manualmente replicados com rastreamento completo de provenance.
"""
import pytest
from datetime import datetime, timezone

from magnata_os.orquestrador.classificador_falha import FalhaTransitoria
from magnata_os.orquestrador.eventos import EstadoExecucao, Evento, Sensibilidade, TipoEvento
from magnata_os.orquestrador.motor import MotorOrquestrador, ResultadoAcao
from magnata_os.orquestrador.repositorio_execucoes import (
    RepositorioExecucoesEmMemoria,
)


def evento_teste(
    event_id='evt-test', payload_ref='test', entity_id='sha-123',
    occurred_offset=0, received_offset=0
) -> Evento:
    """Factory para criar eventos de teste com timestamps válidos."""
    base_time = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
    return Evento(
        event_id=event_id,
        event_type=TipoEvento.GIT_MAIN_AVANCOU,
        source='test',
        occurred_at=datetime.fromtimestamp(
            base_time.timestamp() + occurred_offset, tz=timezone.utc
        ),
        received_at=datetime.fromtimestamp(
            base_time.timestamp() + received_offset, tz=timezone.utc
        ),
        correlation_id='corr-1',
        entity_type='main',
        entity_id=entity_id,
        payload_referencia=payload_ref,
        sensibilidade=Sensibilidade.PUBLICO,
        proveniencia='teste',
        retry_count=0,
    )


class TestReplayControlado:
    """Testes de replay manual com provenance-tracking."""

    def test_replay_de_evento_falhado_sucede_se_problema_resolvido(self):
        """Evento que falha é replicado e sucede depois que o problema é corrigido."""
        repo = RepositorioExecucoesEmMemoria()

        # Estado: falha transitória na primeira tentativa
        tentativas = [0]
        problema_resolvido = [False]

        def acao_falha_depois_sucede(evento):
            tentativas[0] += 1
            if problema_resolvido[0]:
                return ResultadoAcao(sucesso=True, evidencia='Resolvido', caminhos_escritos=())
            raise FalhaTransitoria('Problema temporário')

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_depois_sucede},
        )

        evento = evento_teste(event_id='evt-replay-1')

        # Processa 3 vezes para esgotar tentativas
        for _ in range(3):
            resultado = motor.processar(evento)

        assert resultado.estado == EstadoExecucao.FAILED_FINAL
        assert tentativas[0] == 3

        # Simula que o problema foi resolvido
        problema_resolvido[0] = True

        # Replay manual
        resultado_replay = motor.replay(
            event_id='evt-replay-1',
            solicitado_por='usuario@teste.com',
            motivo='Banco de dados voltou online',
        )

        assert resultado_replay.estado == EstadoExecucao.SUCCEEDED
        assert tentativas[0] == 4  # Uma tentativa a mais depois do replay
        assert resultado_replay.manualmente_reiniciado_por == 'usuario@teste.com'
        assert resultado_replay.motivo_reinicio_manual == 'Banco de dados voltou online'

    def test_replay_rastreia_provenance(self):
        """Replay registra quem, quando e por quê solicitou."""
        repo = RepositorioExecucoesEmMemoria()

        def acao_sucesso(evento):
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
        )

        evento = evento_teste(event_id='evt-replay-2')

        # Força falha
        def acao_falha_perm(evento):
            raise RuntimeError('Erro permanente')

        motor._acoes[TipoEvento.GIT_MAIN_AVANCOU.value] = acao_falha_perm
        resultado = motor.processar(evento)
        assert resultado.estado == EstadoExecucao.FAILED_FINAL

        # Replay
        motor._acoes[TipoEvento.GIT_MAIN_AVANCOU.value] = acao_sucesso
        resultado_replay = motor.replay(
            event_id='evt-replay-2',
            solicitado_por='admin@magnata.com.br',
            motivo='Infraestrutura restaurada',
        )

        # Verificar provenance
        registro = repo.buscar_por_event_id('evt-replay-2')
        assert registro.manualmente_reiniciado_por == 'admin@magnata.com.br'
        assert registro.motivo_reinicio_manual == 'Infraestrutura restaurada'
        assert registro.manualmente_reiniciado_em is not None

    def test_replay_so_funciona_em_failed_final(self):
        """Replay rejeita eventos em estados que não são FAILED_FINAL."""
        repo = RepositorioExecucoesEmMemoria()

        def acao_sucesso(evento):
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
        )

        evento = evento_teste(event_id='evt-replay-3')

        # Processa com sucesso
        resultado = motor.processar(evento)
        assert resultado.estado == EstadoExecucao.SUCCEEDED

        # Tenta replay em SUCCEEDED (deve falhar)
        with pytest.raises(ValueError, match='FAILED_FINAL'):
            motor.replay(
                event_id='evt-replay-3',
                solicitado_por='usuario@teste.com',
                motivo='Teste',
            )

    def test_replay_preserva_event_id(self):
        """Replay não cria novo evento, usa mesmo event_id (idempotência)."""
        repo = RepositorioExecucoesEmMemoria()

        def acao_falha_permanentemente(evento):
            raise RuntimeError('Erro permanente')

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_permanentemente},
        )

        evento = evento_teste(event_id='evt-replay-4')

        # Falha
        resultado = motor.processar(evento)
        assert resultado.event_id == 'evt-replay-4'
        assert resultado.estado == EstadoExecucao.FAILED_FINAL

        # Muda a ação para suceder
        def acao_sucesso(evento):
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor._acoes[TipoEvento.GIT_MAIN_AVANCOU.value] = acao_sucesso

        # Replay
        resultado_replay = motor.replay(
            event_id='evt-replay-4',
            solicitado_por='usuario@teste.com',
            motivo='Problema resolvido',
        )

        # Deve manter o mesmo event_id
        assert resultado_replay.event_id == 'evt-replay-4'
        assert resultado_replay.estado == EstadoExecucao.SUCCEEDED

        # Repositório deve ter só um registro (atualizado, não duplicado)
        assert len(repo.listar_todos()) == 1

    def test_replay_rejeita_evento_nao_encontrado(self):
        """Replay falha se event_id não existe."""
        repo = RepositorioExecucoesEmMemoria()
        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: lambda e: None},
        )

        with pytest.raises(ValueError, match='não encontrado'):
            motor.replay(
                event_id='evt-inexistente',
                solicitado_por='usuario@teste.com',
                motivo='Teste',
            )

    def test_replay_reseta_attempt(self):
        """Replay reseta attempt a 0 (nova chance de retentativas)."""
        repo = RepositorioExecucoesEmMemoria()

        tentativas = [0]

        def acao_falha_permanentemente(evento):
            tentativas[0] += 1
            raise RuntimeError('Erro permanente')

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_permanentemente},
        )

        evento = evento_teste(event_id='evt-replay-5')

        # Falha permanentemente
        resultado = motor.processar(evento)
        assert resultado.estado == EstadoExecucao.FAILED_FINAL
        assert resultado.attempt == 1

        # Muda a ação para suceder
        def acao_sucesso_agora(evento):
            tentativas[0] += 1
            return ResultadoAcao(sucesso=True, evidencia='Resolvido', caminhos_escritos=())

        motor._acoes[TipoEvento.GIT_MAIN_AVANCOU.value] = acao_sucesso_agora

        # Replay (deve resetar attempt e suceder)
        resultado_replay = motor.replay(
            event_id='evt-replay-5',
            solicitado_por='usuario@teste.com',
            motivo='Problema resolvido',
        )

        assert resultado_replay.estado == EstadoExecucao.SUCCEEDED
        # attempt foi resetado durante replay, depois incrementado em _executar_e_registrar
        assert resultado_replay.attempt == 1
        assert tentativas[0] == 2  # Uma falha original + uma sucesso em replay

    def test_replay_com_multiplos_eventos(self):
        """Vários eventos podem ser replicados independentemente."""
        repo = RepositorioExecucoesEmMemoria()

        def acao_falha_depois_sucede(evento):
            if evento.payload_referencia == 'fix-ok':
                return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())
            raise RuntimeError('Erro')

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_depois_sucede},
        )

        # Dois eventos, ambos falham
        evento1 = evento_teste(event_id='evt-replay-6a', payload_ref='fail', entity_id='sha-1')
        evento2 = evento_teste(
            event_id='evt-replay-6b',
            payload_ref='fail',
            entity_id='sha-2',
            occurred_offset=60,
            received_offset=60,
        )

        motor.processar(evento1)
        motor.processar(evento2)

        # Redefine ação
        def acao_sucesso_agora(evento):
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor._acoes[TipoEvento.GIT_MAIN_AVANCOU.value] = acao_sucesso_agora

        # Replay primeiro evento
        resultado1 = motor.replay(
            event_id='evt-replay-6a',
            solicitado_por='admin1@teste.com',
            motivo='Fix para issue X',
        )
        assert resultado1.estado == EstadoExecucao.SUCCEEDED

        # Replay segundo evento
        resultado2 = motor.replay(
            event_id='evt-replay-6b',
            solicitado_por='admin2@teste.com',
            motivo='Fix para issue Y',
        )
        assert resultado2.estado == EstadoExecucao.SUCCEEDED

        # Verificar provenance separado para cada
        reg1 = repo.buscar_por_event_id('evt-replay-6a')
        reg2 = repo.buscar_por_event_id('evt-replay-6b')
        assert reg1.manualmente_reiniciado_por == 'admin1@teste.com'
        assert reg2.manualmente_reiniciado_por == 'admin2@teste.com'
