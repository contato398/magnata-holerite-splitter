"""
Teste de auditoria append-only: rastreamento imutável de transições.

Prova que todo evento tem histórico completo de transições,
registrado de forma append-only (nunca editado ou deletado).
"""
import pytest
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from pathlib import Path

from magnata_os.orquestrador.classificador_falha import FalhaTransitoria
from magnata_os.orquestrador.eventos import EstadoExecucao, Evento, Sensibilidade, TipoEvento
from magnata_os.orquestrador.motor import MotorOrquestrador, ResultadoAcao
from magnata_os.orquestrador.repositorio_execucoes import (
    RegistroAuditoria,
    RepositorioExecucoesEmMemoria,
    RepositorioExecucoesSQLite,
)


def evento_teste(event_id='evt-test', entity_id='sha-123') -> Evento:
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
        entity_id=entity_id,
        payload_referencia='nada',
        sensibilidade=Sensibilidade.PUBLICO,
        proveniencia='teste',
        retry_count=0,
    )


class TestAuditoriaAppendOnly:
    """Testes de auditoria append-only."""

    def test_auditoria_registra_todas_transicoes_em_memoria(self):
        """Cada transição de estado é registrada na auditoria."""
        repo = RepositorioExecucoesEmMemoria()

        def acao_sucesso(evento):
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
        )

        evento = evento_teste(event_id='evt-audit-1')

        # Processar evento (vai passar por: RECEIVED → VALIDATED → CLASSIFIED → EXECUTING → SUCCEEDED)
        resultado = motor.processar(evento)
        assert resultado.estado == EstadoExecucao.SUCCEEDED

        # Verificar auditoria
        auditoria = repo.listar_auditoria('evt-audit-1')
        assert len(auditoria) > 0

        # Deve ter transições: RECEIVED, VALIDATED, CLASSIFIED, EXECUTING, SUCCEEDED
        estados = [(a.estado_anterior, a.estado_novo) for a in auditoria]
        assert ('RECEIVED', 'VALIDATED') in estados
        assert ('VALIDATED', 'CLASSIFIED') in estados
        assert ('CLASSIFIED', 'EXECUTING') in estados
        assert ('EXECUTING', 'SUCCEEDED') in estados

    def test_auditoria_registra_falha_e_retentativas(self):
        """Falhas e retentativas aparecem na auditoria."""
        repo = RepositorioExecucoesEmMemoria()

        tentativas = [0]

        def acao_falha_depois_sucede(evento):
            tentativas[0] += 1
            if tentativas[0] < 3:
                raise FalhaTransitoria('Problema temporário')
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_depois_sucede},
        )

        evento = evento_teste(event_id='evt-audit-2')

        # Primeira tentativa: falha retentável
        resultado1 = motor.processar(evento)
        assert resultado1.estado == EstadoExecucao.FAILED_RETRYABLE

        # Segunda tentativa: falha retentável de novo
        resultado2 = motor.processar(evento)
        assert resultado2.estado == EstadoExecucao.FAILED_RETRYABLE

        # Terceira tentativa: sucede
        resultado3 = motor.processar(evento)
        assert resultado3.estado == EstadoExecucao.SUCCEEDED

        # Verificar auditoria com retentativas
        auditoria = repo.listar_auditoria('evt-audit-2')

        # Deve ter transições para FAILED_RETRYABLE duas vezes
        estados = [(a.estado_anterior, a.estado_novo) for a in auditoria]
        assert ('EXECUTING', 'FAILED_RETRYABLE') in estados
        assert ('FAILED_RETRYABLE', 'EXECUTING') in estados
        assert ('EXECUTING', 'SUCCEEDED') in estados

    def test_auditoria_e_imutavel_em_memoria(self):
        """Auditoria não pode ser modificada ou deletada em memória."""
        import dataclasses

        repo = RepositorioExecucoesEmMemoria()

        def acao_sucesso(evento):
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
        )

        evento = evento_teste(event_id='evt-audit-3')
        motor.processar(evento)

        # Recuperar auditoria inicial
        auditoria_inicial = repo.listar_auditoria('evt-audit-3')
        assert len(auditoria_inicial) > 0

        # Tenta modificar a entrada (isso não deve ser possível com uma entrada frozen)
        primeira_entrada = auditoria_inicial[0]

        # RegistroAuditoria é frozen, então tentar modificar deve levantar FrozenInstanceError
        with pytest.raises(dataclasses.FrozenInstanceError):
            primeira_entrada.motivo = 'MODIFICADO'

        # Recuperar auditoria novamente: deve ser igual
        auditoria_depois = repo.listar_auditoria('evt-audit-3')
        assert len(auditoria_depois) == len(auditoria_inicial)
        # A entrada original não foi modificada (nunca foi, porque é immutável)
        assert auditoria_depois[0].motivo is None

    def test_auditoria_registra_todas_transicoes_em_sqlite(self):
        """Auditoria funciona também com SQLite."""
        with TemporaryDirectory() as tmpdir:
            repo = RepositorioExecucoesSQLite(Path(tmpdir) / 'test.db')

            def acao_sucesso(evento):
                return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

            motor = MotorOrquestrador(
                repositorio=repo,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
            )

            evento = evento_teste(event_id='evt-audit-4')
            motor.processar(evento)

            # Verificar auditoria no SQLite
            auditoria = repo.listar_auditoria('evt-audit-4')
            assert len(auditoria) > 0

            # Deve ter as transições esperadas
            estados = [a.estado_novo for a in auditoria]
            assert EstadoExecucao.VALIDATED.value in estados
            assert EstadoExecucao.CLASSIFIED.value in estados
            assert EstadoExecucao.EXECUTING.value in estados
            assert EstadoExecucao.SUCCEEDED.value in estados

            repo.fechar()

    def test_auditoria_persiste_entre_sessoes_sqlite(self):
        """Auditoria persiste após fechar e reabrir repositório SQLite."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'test.db'

            # Primeira sessão: processar evento
            repo1 = RepositorioExecucoesSQLite(db_path)

            def acao_sucesso(evento):
                return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

            motor1 = MotorOrquestrador(
                repositorio=repo1,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
            )

            evento = evento_teste(event_id='evt-audit-5')
            motor1.processar(evento)

            auditoria1 = repo1.listar_auditoria('evt-audit-5')
            assert len(auditoria1) > 0
            repo1.fechar()

            # Segunda sessão: verificar auditoria persiste
            repo2 = RepositorioExecucoesSQLite(db_path)
            auditoria2 = repo2.listar_auditoria('evt-audit-5')

            # Deve ter os mesmos registros
            assert len(auditoria2) == len(auditoria1)
            for a1, a2 in zip(auditoria1, auditoria2):
                assert a1.event_id == a2.event_id
                assert a1.estado_anterior == a2.estado_anterior
                assert a1.estado_novo == a2.estado_novo

            repo2.fechar()

    def test_auditoria_registra_ordem_temporale_transicoes(self):
        """Transições são registradas em ordem temporal."""
        repo = RepositorioExecucoesEmMemoria()

        def acao_sucesso(evento):
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
        )

        evento = evento_teste(event_id='evt-audit-6')
        motor.processar(evento)

        auditoria = repo.listar_auditoria('evt-audit-6')
        assert len(auditoria) > 0

        # Verificar que timestamps são monotonicamente crescentes
        timestamps = [a.registrado_em for a in auditoria]
        for i in range(len(timestamps) - 1):
            assert timestamps[i] <= timestamps[i + 1]

    def test_auditoria_multiplos_eventos_separados(self):
        """Auditoria de eventos diferentes são mantidas separadas."""
        repo = RepositorioExecucoesEmMemoria()

        def acao_sucesso(evento):
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
        )

        evento1 = evento_teste(event_id='evt-audit-7a')
        evento2 = evento_teste(event_id='evt-audit-7b')

        motor.processar(evento1)
        motor.processar(evento2)

        # Auditoria de cada evento deve ser separada
        audit1 = repo.listar_auditoria('evt-audit-7a')
        audit2 = repo.listar_auditoria('evt-audit-7b')

        assert len(audit1) > 0
        assert len(audit2) > 0

        # Nenhuma entrada de audit1 deve aparecer em audit2
        for a1 in audit1:
            assert a1.event_id == 'evt-audit-7a'
            for a2 in audit2:
                assert a2.event_id == 'evt-audit-7b'
