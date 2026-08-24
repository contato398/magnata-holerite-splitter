"""
Teste de integração: motor → DLQ (fila de desistência).

Prova que eventos FAILED_FINAL são automaticamente registrados na DLQ.
"""
import pytest

from magnata_os.orquestrador.classificador_falha import FalhaTransitoria
from magnata_os.orquestrador.eventos import EstadoExecucao, Evento, TipoEvento
from magnata_os.orquestrador.fila_desistencia import FilaDesistenciaEmMemoria
from magnata_os.orquestrador.motor import MotorOrquestrador, ResultadoAcao
from magnata_os.orquestrador.repositorio_execucoes import (
    RepositorioExecucoesEmMemoria,
)


class TestIntegracaoDLQMotor:
    """Testa integração de DLQ ao motor."""

    def test_evento_falha_final_entra_na_dlq(self):
        """Evento que falha após esgotar tentativas é registrado na DLQ."""
        repo = RepositorioExecucoesEmMemoria()
        dlq = FilaDesistenciaEmMemoria()

        # Contador para forçar 3 falhas transitórias
        tentativas = [0]

        def acao_falha_retentavel_permanentemente(evento):
            tentativas[0] += 1
            # Sempre falha com erro transitório (vai esgotar tentativas)
            raise FalhaTransitoria("Rede indisponível permanentemente")

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_retentavel_permanentemente},
            fila_desistencia=dlq,
        )

        evento = Evento(
            event_id='evt-fail-1',
            event_type=TipoEvento.GIT_MAIN_AVANCOU,
            source='test',
            occurred_at='2026-08-24T12:00:00Z',
            received_at='2026-08-24T12:00:00Z',
            correlation_id='corr-1',
            entity_type='main',
            entity_id='sha-123',
            payload_referencia='nada',
            sensibilidade='PUBLICO',
            proveniencia='teste',
            retry_count=0,
        )

        # Processar evento 3 vezes para esgotar tentativas
        for i in range(3):
            resultado = motor.processar(evento)
            if i < 2:
                # Primeiras 2 tentativas: FAILED_RETRYABLE
                assert resultado.estado == EstadoExecucao.FAILED_RETRYABLE
            else:
                # Terceira tentativa: FAILED_FINAL (esgotou)
                assert resultado.estado == EstadoExecucao.FAILED_FINAL

        # Verificar que foi registrado na DLQ
        itens_dlq = dlq.listar_todos()
        assert len(itens_dlq) == 1
        item = itens_dlq[0]

        assert item.event_id == 'evt-fail-1'
        assert item.event_type == TipoEvento.GIT_MAIN_AVANCOU.value
        assert item.tentativas_consumidas == 3  # Máximo de tentativas
        assert item.ultimo_erro_classe == 'TRANSIENT'  # FalhaTransitoria é TRANSIENT

    def test_evento_sucesso_nao_entra_na_dlq(self):
        """Evento que sucede não vai para DLQ."""
        repo = RepositorioExecucoesEmMemoria()
        dlq = FilaDesistenciaEmMemoria()

        def acao_sucesso(evento):
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
            fila_desistencia=dlq,
        )

        evento = Evento(
            event_id='evt-ok-1',
            event_type=TipoEvento.GIT_MAIN_AVANCOU,
            source='test',
            occurred_at='2026-08-24T12:00:00Z',
            received_at='2026-08-24T12:00:00Z',
            correlation_id='corr-1',
            entity_type='main',
            entity_id='sha-123',
            payload_referencia='nada',
            sensibilidade='PUBLICO',
            proveniencia='teste',
            retry_count=0,
        )

        resultado = motor.processar(evento)
        assert resultado.estado == EstadoExecucao.SUCCEEDED

        # Verificar que DLQ está vazia
        itens_dlq = dlq.listar_todos()
        assert len(itens_dlq) == 0

    def test_evento_retentavel_nao_entra_na_dlq_ate_esgotar(self):
        """Evento com falha retentável não entra DLQ até MAX_TENTATIVAS."""
        repo = RepositorioExecucoesEmMemoria()
        dlq = FilaDesistenciaEmMemoria()

        tentativas = [0]

        def acao_falha_retentavel(evento):
            tentativas[0] += 1
            if tentativas[0] < 3:
                # Simula falha retentável nas 2 primeiras tentativas
                raise FalhaTransitoria("Rede temporariamente indisponível")
            # Terceira tentativa sucede
            return ResultadoAcao(sucesso=True, evidencia='Recuperado', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_retentavel},
            fila_desistencia=dlq,
        )

        evento = Evento(
            event_id='evt-retry-1',
            event_type=TipoEvento.GIT_MAIN_AVANCOU,
            source='test',
            occurred_at='2026-08-24T12:00:00Z',
            received_at='2026-08-24T12:00:00Z',
            correlation_id='corr-1',
            entity_type='main',
            entity_id='sha-123',
            payload_referencia='nada',
            sensibilidade='PUBLICO',
            proveniencia='teste',
            retry_count=0,
        )

        # Primeira tentativa
        resultado1 = motor.processar(evento)
        assert resultado1.estado == EstadoExecucao.FAILED_RETRYABLE
        assert len(dlq.listar_todos()) == 0  # Ainda não na DLQ

        # Segunda tentativa (mesmo evento)
        resultado2 = motor.processar(evento)
        assert resultado2.estado == EstadoExecucao.FAILED_RETRYABLE
        assert len(dlq.listar_todos()) == 0  # Ainda não na DLQ

        # Terceira tentativa (vai suceder)
        resultado3 = motor.processar(evento)
        assert resultado3.estado == EstadoExecucao.SUCCEEDED
        assert len(dlq.listar_todos()) == 0  # Sucesso, não vai para DLQ

    def test_multiplos_eventos_falhados_em_dlq(self):
        """Múltiplos eventos falhados em permanente vão para DLQ."""
        repo = RepositorioExecucoesEmMemoria()
        dlq = FilaDesistenciaEmMemoria()

        def acao_falha_permanente(evento):
            raise RuntimeError("Erro permanente")

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={
                TipoEvento.GIT_MAIN_AVANCOU: acao_falha_permanente,
                TipoEvento.PR_MESCLADO: acao_falha_permanente,
            },
            fila_desistencia=dlq,
        )

        # Dois eventos diferentes, ambos falhando
        for i in range(2):
            evento = Evento(
                event_id=f'evt-fail-{i}',
                event_type=TipoEvento.GIT_MAIN_AVANCOU if i == 0 else TipoEvento.PR_MESCLADO,
                source='test',
                occurred_at='2026-08-24T12:00:00Z',
                received_at='2026-08-24T12:00:00Z',
                correlation_id=f'corr-{i}',
                entity_type='main',
                entity_id=f'sha-{i}',
                payload_referencia='nada',
                sensibilidade='PUBLICO',
                proveniencia='teste',
                retry_count=0,
            )

            resultado = motor.processar(evento)
            assert resultado.estado == EstadoExecucao.FAILED_FINAL

        # Ambos devem estar na DLQ
        itens_dlq = dlq.listar_todos()
        assert len(itens_dlq) == 2
        ids_dlq = {item.event_id for item in itens_dlq}
        assert ids_dlq == {'evt-fail-0', 'evt-fail-1'}

    def test_acao_bloqueada_caminho_proibido_entra_dlq(self):
        """Ação que escreve em caminho proibido (FAILED_FINAL) entra na DLQ."""
        repo = RepositorioExecucoesEmMemoria()
        dlq = FilaDesistenciaEmMemoria()

        def acao_escreve_proibido(evento):
            # Tenta escrever em DECISIONS.md (proibido)
            return ResultadoAcao(
                sucesso=False,
                evidencia='Tentou escrever',
                caminhos_escritos=('DECISIONS.md',),
            )

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_escreve_proibido},
            fila_desistencia=dlq,
        )

        evento = Evento(
            event_id='evt-blocked-1',
            event_type=TipoEvento.GIT_MAIN_AVANCOU,
            source='test',
            occurred_at='2026-08-24T12:00:00Z',
            received_at='2026-08-24T12:00:00Z',
            correlation_id='corr-1',
            entity_type='main',
            entity_id='sha-123',
            payload_referencia='nada',
            sensibilidade='PUBLICO',
            proveniencia='teste',
            retry_count=0,
        )

        # Deve levantar AcaoProibida, mas primeiro registra em FAILED_FINAL + DLQ
        from magnata_os.orquestrador.motor import AcaoProibida

        with pytest.raises(AcaoProibida):
            motor.processar(evento)

        # Mesmo com exception, deve estar em DLQ
        itens_dlq = dlq.listar_todos()
        assert len(itens_dlq) == 1
        item = itens_dlq[0]
        assert item.event_id == 'evt-blocked-1'
        assert 'BLOQUEADA' in item.resultado_final or 'proibido' in item.resultado_final

    def test_dlq_opcional_sem_passar_fila(self):
        """Motor cria DLQ padrão se não for passada."""
        repo = RepositorioExecucoesEmMemoria()

        def acao_falha_permanente(evento):
            raise RuntimeError("Erro")

        # Não passa dlq explicitamente
        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_permanente},
        )

        evento = Evento(
            event_id='evt-default-1',
            event_type=TipoEvento.GIT_MAIN_AVANCOU,
            source='test',
            occurred_at='2026-08-24T12:00:00Z',
            received_at='2026-08-24T12:00:00Z',
            correlation_id='corr-1',
            entity_type='main',
            entity_id='sha-123',
            payload_referencia='nada',
            sensibilidade='PUBLICO',
            proveniencia='teste',
            retry_count=0,
        )

        resultado = motor.processar(evento)
        assert resultado.estado == EstadoExecucao.FAILED_FINAL

        # Motor tem DLQ interna
        assert hasattr(motor, '_fila_desistencia')
        # Itens estarão na DLQ interna do motor
        assert len(motor._fila_desistencia.listar_todos()) == 1
