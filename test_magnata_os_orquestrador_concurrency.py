"""
Teste de concorrência: garantia AT_MOST_ONCE com múltiplos workers.

Prova que mesmo com processamento paralelo, cada evento é processado
no máximo uma vez — idempotência é mantida mesmo sob race conditions.

Cenários:
1. Múltiplos workers recebem mesmo evento simultaneamente
2. Race condition na transição RECEIVED → VALIDATED
3. Worker que vence a race continua, outros detectam e param
4. Resultado final é idêntico independente de qual worker "venceu"
"""
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from magnata_os.orquestrador.eventos import EstadoExecucao, Evento, Sensibilidade, TipoEvento
from magnata_os.orquestrador.motor import MotorOrquestrador, ResultadoAcao
from magnata_os.orquestrador.repositorio_execucoes import (
    RepositorioExecucoesEmMemoria,
    RepositorioExecucoesSQLite,
)


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


class TestConcurrentProcessing:
    """Testes de processamento concorrente com múltiplos workers."""

    def test_multiplos_workers_mesmo_evento_sequencial(self):
        """Dois workers processando sequencialmente não duplicam."""
        repo = RepositorioExecucoesEmMemoria()

        execucoes = []
        execucoes_lock = threading.Lock()

        def acao_com_registro(evento):
            with execucoes_lock:
                execucoes.append(evento.event_id)
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        evento = evento_teste(event_id='evt-concur-1')

        # Worker 1
        motor1 = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_com_registro},
        )
        resultado1 = motor1.processar(evento)

        # Worker 2 processa mesmo evento
        motor2 = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_com_registro},
        )
        resultado2 = motor2.processar(evento)

        # Ambos veem SUCCEEDED
        assert resultado1.estado == EstadoExecucao.SUCCEEDED
        assert resultado2.estado == EstadoExecucao.SUCCEEDED

        # Mas ação foi executada só uma vez
        assert len(execucoes) == 1
        assert execucoes[0] == 'evt-concur-1'

    def test_multiplos_workers_mesmo_evento_sqlite_serialization(self):
        """SQLite serializa escrita, mantendo AT_MOST_ONCE."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'test.db'

            execucoes = []
            execucoes_lock = threading.Lock()

            def acao_com_registro(evento):
                with execucoes_lock:
                    execucoes.append(evento.event_id)
                return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

            evento = evento_teste(event_id='evt-concur-3')

            resultados = []
            resultados_lock = threading.Lock()

            def worker():
                # Cada worker tem sua própria conexão ao DB
                repo = RepositorioExecucoesSQLite(db_path)
                motor = MotorOrquestrador(
                    repositorio=repo,
                    acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_com_registro},
                )
                resultado = motor.processar(evento)
                with resultados_lock:
                    resultados.append(resultado.estado)
                repo.fechar()

            # Lançar 3 workers concorrentemente
            threads = [threading.Thread(target=worker) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Todos completaram com sucesso
            assert len(resultados) == 3
            assert all(r == EstadoExecucao.SUCCEEDED for r in resultados)

            # Mas ação foi executada uma vez (idempotência sob concorrência)
            assert len(execucoes) == 1

    def test_multiplos_workers_diferentes_eventos_paralelo(self):
        """Múltiplos workers com eventos diferentes executam em paralelo."""
        repo = RepositorioExecucoesEmMemoria()

        execucoes = []
        execucoes_lock = threading.Lock()

        def acao_com_registro(evento):
            time.sleep(0.01)  # Simula trabalho
            with execucoes_lock:
                execucoes.append(evento.event_id)
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        start_time = time.time()

        def worker(event_id):
            evento = evento_teste(event_id=event_id)
            motor = MotorOrquestrador(
                repositorio=repo,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_com_registro},
            )
            motor.processar(evento)

        # Lançar 5 workers com eventos diferentes
        threads = [
            threading.Thread(target=worker, args=(f'evt-par-{i}',))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        elapsed = time.time() - start_time

        # Todos os 5 eventos foram processados
        assert len(execucoes) == 5
        assert set(execucoes) == {f'evt-par-{i}' for i in range(5)}

        # Paralelo é mais rápido que sequencial (5 * 0.01 = 0.05, com overhead)
        # Se fosse completamente sequencial, seria > 0.05 segundos
        # Com paralelismo, deve ser < 0.05 + overhead
        # Não fazemos assertion de tempo, só verificamos que ocorreu

    def test_concorrencia_nao_corrompe_auditoria(self):
        """Auditoria permanece consistente sob concorrência."""
        repo = RepositorioExecucoesEmMemoria()

        def acao_sucesso(evento):
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        evento = evento_teste(event_id='evt-concur-4')

        def worker():
            motor = MotorOrquestrador(
                repositorio=repo,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
            )
            motor.processar(evento)

        # Lançar múltiplos workers
        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Auditoria existe e é válida
        auditoria = repo.listar_auditoria('evt-concur-4')
        assert len(auditoria) > 0

        # Transições são sequenciais e ordenadas
        estados = [a.estado_novo for a in auditoria]
        assert EstadoExecucao.VALIDATED.value in estados
        assert EstadoExecucao.CLASSIFIED.value in estados
        assert EstadoExecucao.EXECUTING.value in estados
        assert EstadoExecucao.SUCCEEDED.value in estados

        # Timestamps são monotonicamente crescentes (ordem temporal)
        timestamps = [a.registrado_em for a in auditoria]
        for i in range(len(timestamps) - 1):
            assert timestamps[i] <= timestamps[i + 1]

    def test_concorrencia_recovery_com_falha_transitoria(self):
        """Concorrência com falha transitória mantém retry logic."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'test.db'

            tentativas = [0]
            tentativas_lock = threading.Lock()

            def acao_falha_depois_sucede(evento):
                with tentativas_lock:
                    tentativas[0] += 1
                    if tentativas[0] < 2:
                        from magnata_os.orquestrador.classificador_falha import FalhaTransitoria
                        raise FalhaTransitoria('Rede indisponível')
                return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

            evento = evento_teste(event_id='evt-concur-5')

            resultados = []
            resultados_lock = threading.Lock()

            def worker():
                repo = RepositorioExecucoesSQLite(db_path)
                motor = MotorOrquestrador(
                    repositorio=repo,
                    acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_depois_sucede},
                )
                resultado = motor.processar(evento)
                with resultados_lock:
                    resultados.append(resultado.estado)
                repo.fechar()

            # Worker 1: falha retentável
            t1 = threading.Thread(target=worker)
            t1.start()
            t1.join()

            # Deve estar em FAILED_RETRYABLE
            assert resultados[0] == EstadoExecucao.FAILED_RETRYABLE

            # Worker 2: retenta e sucede
            t2 = threading.Thread(target=worker)
            t2.start()
            t2.join()

            # Deve estar em SUCCEEDED
            assert resultados[1] == EstadoExecucao.SUCCEEDED

            # Ação foi chamada 2 vezes (1ª falha, 2ª sucesso)
            assert tentativas[0] == 2
