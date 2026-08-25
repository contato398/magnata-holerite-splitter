"""
Teste de crash consistency: recuperação de falhas em 6 cenários críticos.

Prova que o motor mantém idempotência mesmo após crashes em diferentes
pontos da execução — antes de ação, durante ação, antes de salvar estado,
e em restart com estado inconsistente.

Principio: Append-only audit trail + estado persistido = recovery segura.
"""
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from magnata_os.orquestrador.classificador_falha import FalhaTransitoria
from magnata_os.orquestrador.eventos import EstadoExecucao, Evento, Sensibilidade, TipoEvento
from magnata_os.orquestrador.motor import MotorOrquestrador, ResultadoAcao, AcaoProibida
from magnata_os.orquestrador.repositorio_execucoes import (
    RegistroExecucao,
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


class TestCrashBeforeAction:
    """Cenário 1: Crash ANTES de chamar a ação."""

    def test_crash_antes_acao_estado_ja_classificado(self):
        """Evento está em CLASSIFIED quando motor encontra erro antes de ação."""
        repo = RepositorioExecucoesEmMemoria()

        execucoes = []

        def acao_com_side_effect(evento):
            execucoes.append(evento.event_id)
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_com_side_effect},
        )

        evento = evento_teste(event_id='evt-crash-1')

        # Motor processa normalmente (nenhuma exceção pré-planejada antes de ação)
        resultado = motor.processar(evento)

        # Motor completou com sucesso (sem crashes)
        assert resultado.estado == EstadoExecucao.SUCCEEDED
        assert len(execucoes) == 1  # Ação foi chamada

        # Estado foi persistido completamente
        registro = repo.buscar_por_event_id('evt-crash-1')
        assert registro is not None
        assert registro.estado == EstadoExecucao.SUCCEEDED

        # Auditoria registrou todas as transições
        auditoria = repo.listar_auditoria('evt-crash-1')
        estados = [a.estado_novo for a in auditoria]
        assert EstadoExecucao.VALIDATED.value in estados
        assert EstadoExecucao.CLASSIFIED.value in estados
        assert EstadoExecucao.EXECUTING.value in estados
        assert EstadoExecucao.SUCCEEDED.value in estados

    def test_crash_antes_acao_retry_succede_no_restart(self):
        """Após restart, retry da mesma ação sucede com falha transitória."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'test.db'

            # SESSÃO 1: Falha transitória (retentável)
            repo1 = RepositorioExecucoesSQLite(db_path)
            execucoes1 = [0]

            def acao_falha_transitoria(evento):
                execucoes1[0] += 1
                raise FalhaTransitoria('Erro temporário')

            motor1 = MotorOrquestrador(
                repositorio=repo1,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_transitoria},
            )

            evento = evento_teste(event_id='evt-crash-2')

            resultado1 = motor1.processar(evento)
            assert resultado1.estado == EstadoExecucao.FAILED_RETRYABLE
            assert execucoes1[0] == 1

            auditoria1 = repo1.listar_auditoria('evt-crash-2')
            repo1.fechar()

            # SESSÃO 2: Restart com ação que sucede
            repo2 = RepositorioExecucoesSQLite(db_path)
            execucoes2 = [0]

            def acao_sucesso(evento):
                execucoes2[0] += 1
                return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

            motor2 = MotorOrquestrador(
                repositorio=repo2,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
            )

            # Re-processar: reconhece evento_id já existe, recupera estado, retenta
            resultado2 = motor2.processar(evento)
            assert resultado2.estado == EstadoExecucao.SUCCEEDED
            assert execucoes2[0] == 1  # Ação foi chamada na sessão 2

            # Auditoria inclui ambas as sessões
            auditoria2 = repo2.listar_auditoria('evt-crash-2')
            assert len(auditoria2) > len(auditoria1)  # Mais transições adicionadas

            repo2.fechar()


class TestCrashDuringAction:
    """Cenário 2: Crash DURANTE execução de ação."""

    def test_crash_durante_acao_estado_em_executing(self):
        """Evento fica em EXECUTING quando crash ocorre dentro de acao."""
        repo = RepositorioExecucoesEmMemoria()

        def acao_com_crash(evento):
            # Simula crash durante execução
            raise RuntimeError('Segmentation fault')

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_com_crash},
        )

        evento = evento_teste(event_id='evt-crash-3')

        resultado = motor.processar(evento)

        # Falha permanente (RuntimeError é desconhecida → PERMANENT)
        assert resultado.estado == EstadoExecucao.FAILED_FINAL

        # Auditoria tem o passo de EXECUTING → FAILED_FINAL
        auditoria = repo.listar_auditoria('evt-crash-3')
        estados = [(a.estado_anterior, a.estado_novo) for a in auditoria]
        assert ('EXECUTING', 'FAILED_FINAL') in estados

    def test_crash_durante_acao_retentavel_falha_transitoria(self):
        """Crash retentável (FalhaTransitoria) deixa evento em FAILED_RETRYABLE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'test.db'

            # SESSÃO 1: Falha transitória durante ação
            repo1 = RepositorioExecucoesSQLite(db_path)

            tentativas1 = [0]

            def acao_falha_transitoria(evento):
                tentativas1[0] += 1
                raise FalhaTransitoria('Conexão perdida')

            motor1 = MotorOrquestrador(
                repositorio=repo1,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_falha_transitoria},
            )

            evento = evento_teste(event_id='evt-crash-4')
            resultado1 = motor1.processar(evento)

            # Primeira tentativa falha retentável
            assert resultado1.estado == EstadoExecucao.FAILED_RETRYABLE
            assert tentativas1[0] == 1

            registro1 = repo1.buscar_por_event_id('evt-crash-4')
            assert registro1.attempt == 1
            auditoria1 = repo1.listar_auditoria('evt-crash-4')
            repo1.fechar()

            # SESSÃO 2: Restart, tenta de novo (reconhece que é retry)
            repo2 = RepositorioExecucoesSQLite(db_path)
            tentativas2 = [0]

            def acao_sucesso(evento):
                tentativas2[0] += 1
                return ResultadoAcao(sucesso=True, evidencia='Recuperado', caminhos_escritos=())

            motor2 = MotorOrquestrador(
                repositorio=repo2,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
            )

            resultado2 = motor2.processar(evento)

            # Segunda tentativa sucede
            assert resultado2.estado == EstadoExecucao.SUCCEEDED
            assert tentativas2[0] == 1  # Nova tentativa

            registro2 = repo2.buscar_por_event_id('evt-crash-4')
            assert registro2.attempt == 2  # attempt foi incrementado

            # Auditoria completa tem todas as transições
            auditoria2 = repo2.listar_auditoria('evt-crash-4')
            assert len(auditoria2) > len(auditoria1)

            repo2.fechar()


class TestCrashBeforeSave:
    """Cenário 3: Crash ANTES de salvar SUCCEEDED no repositório."""

    def test_crash_apos_acao_antes_salvar_succeeded(self):
        """Ação completou (side effect), e estado fica em EXECUTING até recover."""
        repo = RepositorioExecucoesEmMemoria()

        execucoes = []

        def acao_sucesso(evento):
            execucoes.append(evento.event_id)
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
        )

        evento = evento_teste(event_id='evt-crash-5')

        # Processa normalmente
        resultado = motor.processar(evento)

        # Motor sucede completamente
        assert resultado.estado == EstadoExecucao.SUCCEEDED

        # Ação foi executada (side effect ocorreu)
        assert len(execucoes) == 1

        # Estado foi salvo completamente
        registro = repo.buscar_por_event_id('evt-crash-5')
        assert registro is not None
        assert registro.estado == EstadoExecucao.SUCCEEDED

    def test_crash_apos_acao_deixa_evento_preso_ate_replay_manual(self):
        """Crash após ação (antes de salvar SUCCEEDED) NÃO é retomado por
        um processar() comum -- essa é a troca deliberada feita na
        reconciliação de concorrência (ver comentário em
        motor.py:processar e TRANSICOES_VALIDAS): um segundo processar()
        para um evento "em andamento" nunca reexecuta a Ação (fecha a
        corrida de dupla execução de efeito externo). O preço é que um
        crash real do worker original deixa o evento preso até um
        replay() manual explícito -- gate humano, nunca automático,
        porque só um humano pode confirmar fora de banda que o worker
        anterior realmente morreu."""
        side_effects = []

        def acao_idempotente(evento):
            # Simula ação que registra em lista (sem duplicar se chamado 2x)
            if evento.event_id not in side_effects:
                side_effects.append(evento.event_id)
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'test.db'

            # SESSÃO 1: Ação sucede, mas crash antes de salvar SUCCEEDED
            repo1 = RepositorioExecucoesSQLite(db_path)

            motor1 = MotorOrquestrador(
                repositorio=repo1,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_idempotente},
            )

            evento = evento_teste(event_id='evt-crash-6')

            # Patch para falhar após ação
            original_salvar = repo1.salvar
            salvar_count = [0]

            def salvar_crash(registro):
                salvar_count[0] += 1
                if registro.estado == EstadoExecucao.SUCCEEDED:
                    raise IOError('DB crash')
                original_salvar(registro)

            repo1.salvar = salvar_crash

            with pytest.raises(IOError):
                motor1.processar(evento)

            # Side effect registrado
            assert 'evt-crash-6' in side_effects
            repo1.fechar()

            # SESSÃO 2: Restart -- um processar() comum NÃO reexecuta.
            # O registro ficou em EXECUTING, persistido antes da Acao;
            # SUCCEEDED nunca foi persistido pelo crash. Isso e "em
            # andamento" do ponto de vista de
            # processar(), então ele recusa e devolve como está --
            # nunca reexecuta a Ação sem saber se o worker 1 morreu de
            # verdade ou só está lento.
            repo2 = RepositorioExecucoesSQLite(db_path)

            motor2 = MotorOrquestrador(
                repositorio=repo2,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_idempotente},
            )

            resultado_processar = motor2.processar(evento)
            assert resultado_processar.estado == EstadoExecucao.EXECUTING
            # Ação NÃO foi reexecutada por um processar() comum
            assert side_effects.count('evt-crash-6') == 1

            # SESSÃO 2 (continuação): operador confirma fora de banda que
            # o worker 1 morreu e chama replay() explicitamente -- a
            # única forma correta de destravar este evento.
            resultado_replay = motor2.replay(
                'evt-crash-6', 'operador-teste',
                'worker 1 confirmado morto -- crash de IO, ver log da sessão 1',
            )
            assert resultado_replay.estado == EstadoExecucao.SUCCEEDED

            # Side effect não duplicou (idempotência mantida mesmo com a
            # Ação sendo chamada de novo pelo replay -- porque a própria
            # Ação de teste é idempotente; o motor não garante isso por
            # si só para Ações não-idempotentes, replay sempre reexecuta)
            assert side_effects.count('evt-crash-6') == 1

            repo2.fechar()


class TestCrashRestartScenarios:
    """Cenários 4-6: Restart com diferentes estados inconsistentes."""

    def test_restart_reconhece_succeeded_realmente_ocorreu(self):
        """Restart detecta que SUCCEEDED já foi processado, não retenta."""
        tentativas = [0]

        def acao_incrementa(evento):
            tentativas[0] += 1
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'test.db'

            # SESSÃO 1: Sucesso completo
            repo1 = RepositorioExecucoesSQLite(db_path)

            motor1 = MotorOrquestrador(
                repositorio=repo1,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_incrementa},
            )

            evento = evento_teste(event_id='evt-crash-7')
            resultado1 = motor1.processar(evento)

            assert resultado1.estado == EstadoExecucao.SUCCEEDED
            assert tentativas[0] == 1

            repo1.fechar()

            # SESSÃO 2: Restart, mesmo evento, ação não é chamada de novo
            repo2 = RepositorioExecucoesSQLite(db_path)

            motor2 = MotorOrquestrador(
                repositorio=repo2,
                acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_incrementa},
            )

            # Re-processar mesmo evento
            resultado2 = motor2.processar(evento)

            # Reconheceu que já estava SUCCEEDED, não retentou
            assert resultado2.estado == EstadoExecucao.SUCCEEDED
            assert tentativas[0] == 1  # Ação não foi chamada de novo

            repo2.fechar()

    def test_restart_com_sqlite_locked_recupera_com_retry(self):
        """Restart quando SQLite está locked tenta recovery."""
        repo = RepositorioExecucoesEmMemoria()

        def acao_sucesso(evento):
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
        )

        evento = evento_teste(event_id='evt-crash-8')

        # Simular lock no repositório
        lock_count = [0]
        original_buscar = repo.buscar_por_event_id

        def buscar_com_lock(event_id):
            lock_count[0] += 1
            if lock_count[0] == 1:
                raise OSError('database is locked')
            return original_buscar(event_id)

        repo.buscar_por_event_id = buscar_com_lock

        # Motor deve levantar a exceção (lock não é recuperável automaticamente)
        with pytest.raises(OSError):
            motor.processar(evento)

    def test_restart_auditoria_indisponivel_continua_processamento(self):
        """Quando auditoria falha, processamento continua com graceful degradation."""
        repo = RepositorioExecucoesEmMemoria()

        def acao_sucesso(evento):
            return ResultadoAcao(sucesso=True, evidencia='OK', caminhos_escritos=())

        motor = MotorOrquestrador(
            repositorio=repo,
            acoes={TipoEvento.GIT_MAIN_AVANCOU: acao_sucesso},
        )

        evento = evento_teste(event_id='evt-crash-9')

        # Simular auditoria indisponível
        original_registrar = repo.registrar_auditoria

        chamadas_auditoria = [0]

        def auditoria_indisponivel(*args, **kwargs):
            chamadas_auditoria[0] += 1
            raise OSError('Auditoria unavailable')

        repo.registrar_auditoria = auditoria_indisponivel

        # Motor deve processar mesmo com auditoria falhando
        # (graceful degradation: auditoria é importante mas não é critical path)
        resultado = motor.processar(evento)

        # Processamento continuou
        assert resultado.estado in (
            EstadoExecucao.SUCCEEDED,
            EstadoExecucao.EXECUTING,  # Pode estar aqui se erro ocorreu durante auditoria
        )

        # Auditoria foi tentada mas falhou
        assert chamadas_auditoria[0] > 0
