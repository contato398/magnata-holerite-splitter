"""
Teste de concorrência: garantia AT_MOST_ONCE com múltiplos workers.

Prova que mesmo com processamento paralelo, a Ação de um evento (o
efeito externo real -- enviar e-mail, chamar API, etc.) executa no
máximo uma vez.

ACHADO DA RECONCILIAÇÃO (missão corretiva pós "PRONTO PARA PRODUÇÃO"):
os testes originais deste arquivo (test_multiplos_workers_*) rodam a
Ação sem nenhum atraso artificial -- rápidos o bastante para que, na
prática, threading + GIL quase sempre serializam a passagem de cada
worker pelo motor inteiro antes do próximo começar. Eles passavam, mas
não PROVAVAM nada sobre corrida real: um worker que só chega depois que
o outro já terminou encontra o evento em SUCCEEDED (estado terminal) e
sai pelo caminho de deduplicação de sempre -- isso nunca esteve quebrado.
Uma prova de corrida real de verdade precisa FORÇAR dois workers a
estarem dentro do motor ao mesmo tempo (via time.sleep()/Barrier na
própria Ação) -- os testes test_dupla_execucao_* abaixo fazem isso, e
foram os que expuseram a lacuna real: sem reivindicação atômica
(motor.py:criar_se_novo, adicionado nesta reconciliação), dois workers
que chegam ao mesmo tempo para um evento NOVO executavam a Ação duas
vezes. Ver magnata_os/orquestrador/motor.py:processar() e
TRANSICOES_VALIDAS em eventos.py para a explicação completa do fix e
da troca que ele implica (evento "em andamento" cujo worker morre fica
preso até replay() manual -- ver
test_magnata_os_orquestrador_crash_consistency.py).
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


class TestDuplaExecucaoForcada:
    """Prova de corrida REAL: força dois+ workers a estarem dentro do
    motor simultaneamente (nunca deixa ao acaso do scheduler)."""

    def test_dupla_execucao_evento_novo_com_barrier(self):
        """threading.Barrier obriga os dois workers a estarem dentro da
        Ação ao mesmo tempo -- se a reivindicação (criar_se_novo) não
        fosse atômica, os dois passariam. Prova a lacuna que existia
        antes desta reconciliação e o fix (motor.py:processar, ramo
        `if existente is None`)."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'test.db'
            barrier = threading.Barrier(2, timeout=2)
            execucoes = []
            execucoes_lock = threading.Lock()

            def acao_com_barrier(evento):
                # Se dois workers chegassem aqui, ambos passariam do
                # barrier.wait() -- BrokenBarrierError so ocorre se
                # SOMENTE UM chegar (prova de que o outro foi recusado
                # antes mesmo de tentar executar a Ação).
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    raise RuntimeError('so um worker chegou -- esperado')
                with execucoes_lock:
                    execucoes.append(evento.event_id)
                return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

            evento = evento_teste(event_id='evt-race-barrier')
            resultados = []
            resultados_lock = threading.Lock()

            def worker():
                repo = RepositorioExecucoesSQLite(db_path)
                motor = MotorOrquestrador(
                    repositorio=repo,
                    acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_com_barrier},
                )
                r = motor.processar(evento)
                with resultados_lock:
                    resultados.append(r.estado)
                repo.fechar()

            t1 = threading.Thread(target=worker)
            t2 = threading.Thread(target=worker)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            # A Ação nunca executou de fato (o vencedor sozinho ficou
            # preso no barrier.wait() até o timeout -- prova que o
            # perdedor NUNCA chegou perto de chamar a Ação)
            assert len(execucoes) == 0
            # O vencedor bateu no timeout do barrier sozinho (classificado
            # como falha permanente -- RuntimeError desconhecida); o
            # perdedor foi recusado antes de qualquer tentativa
            assert EstadoExecucao.FAILED_FINAL in resultados
            assert EstadoExecucao.RECEIVED in resultados

    def test_dupla_execucao_evento_novo_cinco_workers_com_delay(self):
        """5 workers verdadeiramente concorrentes (Ação com sleep real)
        contra o MESMO event_id novo -- exatamente 1 execução, os
        outros 4 recusam sem tocar na Ação. Depois, um processar()
        adicional após a conclusão confirma dedup normal (SUCCEEDED,
        sem nova execução) -- o fix não quebrou o caminho comum."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'test.db'
            execucoes = []
            execucoes_lock = threading.Lock()

            def acao_lenta(evento):
                time.sleep(0.05)
                with execucoes_lock:
                    execucoes.append(evento.event_id)
                return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

            evento = evento_teste(event_id='evt-race-5workers')
            resultados = []
            resultados_lock = threading.Lock()

            def worker():
                repo = RepositorioExecucoesSQLite(db_path)
                motor = MotorOrquestrador(
                    repositorio=repo,
                    acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_lenta},
                )
                r = motor.processar(evento)
                with resultados_lock:
                    resultados.append(r.estado)
                repo.fechar()

            threads = [threading.Thread(target=worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Exatamente uma execução real da Ação, apesar de 5 workers
            # verdadeiramente concorrentes
            assert len(execucoes) == 1
            assert resultados.count(EstadoExecucao.SUCCEEDED) == 1
            assert resultados.count(EstadoExecucao.RECEIVED) == 4

            # Caminho comum pós-conclusão continua correto: novo
            # processar() reconhece SUCCEEDED, não reexecuta
            repo_final = RepositorioExecucoesSQLite(db_path)
            motor_final = MotorOrquestrador(
                repositorio=repo_final,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_lenta},
            )
            resultado_final = motor_final.processar(evento)
            assert resultado_final.estado == EstadoExecucao.SUCCEEDED
            assert len(execucoes) == 1  # ainda 1 -- sem nova execução
            repo_final.fechar()
