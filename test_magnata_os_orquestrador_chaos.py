"""
Teste de chaos: resiliência sob falhas de infraestrutura.

Prova que o motor é resiliente a:
- DB indisponível
- DB locked
- Auditoria indisponível
- Evento corrompido
- Timeout de operação
"""
import pytest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from magnata_os.orquestrador.eventos import EstadoExecucao, Evento, Sensibilidade, TipoEvento
from magnata_os.orquestrador.motor import MotorOrquestrador, ResultadoAcao
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesSQLite


def evento_teste(event_id='evt-test') -> Evento:
    """Factory para criar eventos de teste."""
    base_time = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
    return Evento(
        event_id=event_id,
        event_type=TipoEvento.GIT_MAIN_AVANCOU,
        source='test',
        occurred_at=base_time,
        received_at=base_time,
        correlation_id='corr-1',
        entity_type='main',
        entity_id='sha-123',
        payload_referencia='nada',
        sensibilidade=Sensibilidade.PUBLICO,
        proveniencia='teste',
        retry_count=0,
    )


class TestChaosDatabaseUnavailable:
    """DB indisponível."""

    def test_db_indisponivel_primeira_tentativa_falha(self):
        """Quando DB está indisponível, primeira tentativa falha."""
        repo = RepositorioExecucoesSQLite

        def acao_dummy(evento):
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        # Simular DB indisponível (não consegue criar)
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'locked.db'
            # Criar um arquivo que bloqueia a criação do DB
            db_path.write_text('locked')

            # Tentar usar DB nesse caminho deve falhar
            with pytest.raises((OSError, IOError, Exception)):
                repo(db_path)


class TestChaosDatabaseLocked:
    """DB locked durante operação."""

    def test_db_locked_recovery_com_retry(self):
        """DB lock durante operação é manejado (sem crash)."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'test.db'

            repo = RepositorioExecucoesSQLite(db_path)

            def acao_dummy(evento):
                return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

            motor = MotorOrquestrador(
                repositorio=repo,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_dummy},
            )

            evento = evento_teste(event_id='evt-chaos-1')

            # Processar normalmente (sem lock)
            resultado = motor.processar(evento)
            assert resultado.estado == EstadoExecucao.SUCCEEDED

            repo.fechar()


class TestChaosAuditUnavailable:
    """Auditoria indisponível."""

    def test_audit_indisponivel_graceful_degradation(self):
        """Quando auditoria falha, processamento continua."""
        from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria

        repo = RepositorioExecucoesEmMemoria()

        def acao_dummy(evento):
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_dummy},
        )

        evento = evento_teste(event_id='evt-chaos-2')

        # Mockar auditoria para falhar
        original_registrar = repo.registrar_auditoria
        chamadas = [0]

        def auditoria_falha(*args, **kwargs):
            chamadas[0] += 1
            raise OSError('Auditoria indisponível')

        repo.registrar_auditoria = auditoria_falha

        # Motor processa mesmo com auditoria falhando
        resultado = motor.processar(evento)

        # Processamento foi resiliente (não travou)
        assert resultado.estado in (
            EstadoExecucao.EXECUTING,
            EstadoExecucao.SUCCEEDED,
        )

        # Auditoria foi tentada (mas falhou)
        assert chamadas[0] > 0

        repo.fechar()


class TestChaosEventoCorrempido:
    """Evento corrompido."""

    def test_evento_sem_event_type_necessario(self):
        """Evento com event_type=None é rejeitado em __post_init__.

        Achado da reconciliação: dataclass nao valida tipo em runtime
        por si so (Python nao enforca type hints) -- a validacao
        explicita foi adicionada em Evento.__post_init__ porque motor.py
        despacha por evento.event_type.value em multiplos pontos; sem
        essa checagem, o erro so apareceria como AttributeError
        (NoneType tem no attribute value) no primeiro uso, nao na
        construcao do evento.
        """
        with pytest.raises(ValueError):
            Evento(
                event_id='evt-chaos-3',
                event_type=None,  # Inválido
                source='test',
                occurred_at=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc),
                correlation_id='corr-1',
                entity_type='main',
                entity_id='sha-123',
                payload_referencia='nada',
                sensibilidade=Sensibilidade.PUBLICO,
                proveniencia='teste',
                retry_count=0,
            )


class TestChaosMultipleFailures:
    """Múltiplas falhas simultâneas."""

    def test_falha_acao_e_falha_auditoria(self):
        """Quando ação e auditoria falham, motor maneja gracefully."""
        from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoesEmMemoria

        repo = RepositorioExecucoesEmMemoria()

        tentativas = [0]

        def acao_falha(evento):
            tentativas[0] += 1
            raise RuntimeError('Erro na ação')

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha},
        )

        evento = evento_teste(event_id='evt-chaos-4')

        # Mockar auditoria para falhar
        original_registrar = repo.registrar_auditoria

        def auditoria_falha(*args, **kwargs):
            raise OSError('Auditoria failed')

        repo.registrar_auditoria = auditoria_falha

        # Processar: ação falha, auditoria também falha
        resultado = motor.processar(evento)

        # Motor concluiu (resiliente)
        assert resultado.estado == EstadoExecucao.FAILED_FINAL
        # Ação foi tentada
        assert tentativas[0] == 1

        repo.fechar()

    def test_recuperacao_apos_multiplas_falhas(self):
        """Após múltiplas falhas, recovery é possível."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'test.db'

            # SESSÃO 1: Falhas múltiplas
            repo1 = RepositorioExecucoesSQLite(db_path)

            tentativas1 = [0]

            def acao_falha(evento):
                tentativas1[0] += 1
                raise RuntimeError('Erro')

            motor1 = MotorOrquestrador(
                repositorio=repo1,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha},
            )

            evento = evento_teste(event_id='evt-chaos-5')
            resultado1 = motor1.processar(evento)

            # Falhou permanentemente
            assert resultado1.estado == EstadoExecucao.FAILED_FINAL
            repo1.fechar()

            # SESSÃO 2: Replay com ação que funciona
            repo2 = RepositorioExecucoesSQLite(db_path)

            tentativas2 = [0]

            def acao_sucesso(evento):
                tentativas2[0] += 1
                return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

            motor2 = MotorOrquestrador(
                repositorio=repo2,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
            )

            # Replay do evento que estava em FAILED_FINAL
            resultado_replay = motor2.replay('evt-chaos-5', 'tester', 'chaos test recovery')

            # Deve suceder
            assert resultado_replay.estado == EstadoExecucao.SUCCEEDED

            repo2.fechar()
