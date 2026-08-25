"""Provas da autorrecuperacao segura, inclusive restart e concorrencia."""
import multiprocessing
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from magnata_os.orquestrador.autorrecuperacao import (
    CoordenadorAutorrecuperacao,
    DecisaoRecuperacao,
)
from magnata_os.orquestrador.classificador_falha import FalhaTransitoria
from magnata_os.orquestrador.eventos import (
    EstadoExecucao,
    Evento,
    Sensibilidade,
    TipoEvento,
)
from magnata_os.orquestrador.fila_desistencia import FilaDesistenciaEmMemoria
from magnata_os.orquestrador.motor import MotorOrquestrador, ResultadoAcao
from magnata_os.orquestrador.repositorio_execucoes import (
    RegistroExecucao,
    RepositorioExecucoesEmMemoria,
    RepositorioExecucoesSQLite,
)
from magnata_os.orquestrador.saude_motor import MonitorSaudemotorPersistente


INSTANTE = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def _evento(event_id: str, tipo: TipoEvento = TipoEvento.GIT_MAIN_AVANCOU) -> Evento:
    return Evento(
        event_id=event_id,
        event_type=tipo,
        source='teste',
        occurred_at=INSTANTE,
        received_at=INSTANTE,
        correlation_id=f'corr-{event_id}',
        entity_type='commit',
        entity_id=f'sha-{event_id}',
        payload_referencia=f'sha-{event_id}',
        sensibilidade=Sensibilidade.PUBLICO,
        proveniencia='teste_autorrecuperacao',
    )


def _anexar_marcador(caminho: str, texto: str) -> None:
    """Efeito observavel e atomico entre processos, restrito ao tmp do teste."""
    descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descritor, f'{texto}\n'.encode('utf-8'))
        os.fsync(descritor)
    finally:
        os.close(descritor)


def _worker_crash_real(caminho_db: str, marcador: str, event_id: str) -> None:
    """Processo isolado que morre dentro da Acao, sem finally nem close."""
    repo = RepositorioExecucoesSQLite(Path(caminho_db))

    def acao(evento):
        _anexar_marcador(marcador, evento.event_id)
        os._exit(73)

    motor = MotorOrquestrador(
        repo,
        {TipoEvento.GIT_MAIN_AVANCOU.value: acao},
    )
    motor.processar(_evento(event_id))


def _worker_retry_multiprocesso(
    caminho_db: str,
    marcador: str,
    barreira,
    resultados,
) -> None:
    """Worker independente para provar o CAS do SQLite entre processos."""
    repo = None
    try:
        class RepositorioComBarreira(RepositorioExecucoesSQLite):
            def reivindicar_retry(self, event_id, reivindicado_em):
                barreira.wait(timeout=10)
                return super().reivindicar_retry(event_id, reivindicado_em)

        repo = RepositorioComBarreira(Path(caminho_db))

        def acao(evento):
            _anexar_marcador(marcador, evento.event_id)
            time.sleep(0.1)
            return ResultadoAcao(sucesso=True, evidencia='retry multiprocesso unico')

        motor = MotorOrquestrador(
            repo,
            {TipoEvento.GIT_MAIN_AVANCOU.value: acao},
        )
        coordenador = CoordenadorAutorrecuperacao(
            repo,
            motor,
            relogio=lambda: INSTANTE,
        )
        decisoes = [resultado.decisao.value for resultado in coordenador.executar_ciclo()]
        resultados.put(('ok', decisoes))
    except BaseException as exc:  # pragma: no cover - devolvido ao processo pai
        resultados.put(('erro', f'{type(exc).__name__}: {exc}'))
    finally:
        if repo is not None:
            repo.fechar()


def _preparar_falha_retentavel(repo, evento, acao):
    motor = MotorOrquestrador(repo, {evento.event_type.value: acao})
    registro = motor.processar(evento)
    assert registro.estado == EstadoExecucao.FAILED_RETRYABLE
    return motor, registro


def _registro(
    event_id: str,
    estado: EstadoExecucao,
    atualizado_em: datetime = INSTANTE,
) -> RegistroExecucao:
    return RegistroExecucao(
        event_id=event_id,
        event_type=TipoEvento.GIT_MAIN_AVANCOU.value,
        estado=estado,
        nivel_autonomia=4,
        acao=TipoEvento.GIT_MAIN_AVANCOU.value,
        resultado=None,
        evidencia=None,
        attempt=1,
        next_retry_at=None,
        last_error_classe=None,
        last_error_at=None,
        criado_em=atualizado_em,
        atualizado_em=atualizado_em,
    )


def test_aguarda_backoff_sem_executar_acao():
    repo = RepositorioExecucoesEmMemoria()
    chamadas = []

    def acao(evento):
        chamadas.append(evento.event_id)
        raise FalhaTransitoria('indisponivel')

    motor, registro = _preparar_falha_retentavel(repo, _evento('retry-futuro'), acao)
    registro.next_retry_at = INSTANTE + timedelta(minutes=5)
    repo.salvar(registro)

    resultados = CoordenadorAutorrecuperacao(repo, motor, relogio=lambda: INSTANTE).executar_ciclo()

    assert [r.decisao for r in resultados] == [DecisaoRecuperacao.AGUARDAR_BACKOFF]
    assert chamadas == ['retry-futuro']
    assert repo.buscar_por_event_id('retry-futuro').estado == EstadoExecucao.FAILED_RETRYABLE

    # Ciclos repetidos nao inflam a trilha com a mesma decisao identica.
    CoordenadorAutorrecuperacao(repo, motor, relogio=lambda: INSTANTE).executar_ciclo()
    assert len(repo.listar_recuperacoes('retry-futuro')) == 1


def test_retry_automatico_devido_sucede_e_fica_auditado():
    repo = RepositorioExecucoesEmMemoria()
    chamadas = []

    def acao(evento):
        chamadas.append(evento.event_id)
        if len(chamadas) == 1:
            raise FalhaTransitoria('timeout antes do efeito')
        return ResultadoAcao(sucesso=True, evidencia='snapshot reconciliado')

    motor, registro = _preparar_falha_retentavel(repo, _evento('retry-ok'), acao)
    registro.next_retry_at = INSTANTE - timedelta(seconds=1)
    repo.salvar(registro)

    resultados = CoordenadorAutorrecuperacao(repo, motor, relogio=lambda: INSTANTE).executar_ciclo()

    assert [r.decisao for r in resultados] == [DecisaoRecuperacao.RETRY_EXECUTADO]
    assert repo.buscar_por_event_id('retry-ok').estado == EstadoExecucao.SUCCEEDED
    assert chamadas == ['retry-ok', 'retry-ok']
    trilha = repo.listar_recuperacoes('retry-ok')
    assert [r.decisao for r in trilha] == ['RETRY_AUTORIZADO', 'RETRY_EXECUTADO']
    assert repo.listar_auditoria('retry-ok')[-2].motivo == 'retry_reivindicado_atomicamente'


def test_falha_da_auditoria_bloqueia_retry_antes_do_side_effect():
    repo = RepositorioExecucoesEmMemoria()
    chamadas = []

    def acao(evento):
        chamadas.append(evento.event_id)
        raise FalhaTransitoria('timeout')

    motor, registro = _preparar_falha_retentavel(repo, _evento('retry-sem-audit'), acao)
    registro.next_retry_at = INSTANTE - timedelta(seconds=1)
    repo.salvar(registro)

    def auditoria_indisponivel(_registro):
        raise IOError('audit store indisponivel')

    repo.registrar_recuperacao = auditoria_indisponivel
    coordenador = CoordenadorAutorrecuperacao(repo, motor, relogio=lambda: INSTANTE)

    with pytest.raises(IOError, match='audit store indisponivel'):
        coordenador.executar_ciclo()

    assert chamadas == ['retry-sem-audit']
    assert repo.buscar_por_event_id('retry-sem-audit').estado == EstadoExecucao.FAILED_RETRYABLE


def test_kill_switch_e_reavaliado_e_bloqueia_retry_existente():
    repo = RepositorioExecucoesEmMemoria()
    chamadas = []

    def acao(evento):
        chamadas.append(evento.event_id)
        raise FalhaTransitoria('timeout')

    motor, registro = _preparar_falha_retentavel(repo, _evento('retry-kill-switch'), acao)
    registro.next_retry_at = INSTANTE - timedelta(seconds=1)
    repo.salvar(registro)

    with patch(
        'magnata_os.orquestrador.motor.aplicar_kill_switch_bloqueio',
        return_value=5,
    ):
        resultado = CoordenadorAutorrecuperacao(
            repo, motor, relogio=lambda: INSTANTE,
        ).executar_ciclo()[0]

    assert resultado.decisao == DecisaoRecuperacao.ESCALAR_HUMANO
    assert repo.buscar_por_event_id('retry-kill-switch').estado == EstadoExecucao.WAITING_GATE
    assert chamadas == ['retry-kill-switch']


def test_tipo_sem_politica_de_recuperacao_escala_sem_retry():
    repo = RepositorioExecucoesEmMemoria()
    chamadas = []

    def acao(evento):
        chamadas.append(evento.event_id)
        raise FalhaTransitoria('timeout')

    evento = _evento('retry-sem-politica', TipoEvento.PR_MESCLADO)
    motor, registro = _preparar_falha_retentavel(repo, evento, acao)
    registro.next_retry_at = INSTANTE - timedelta(seconds=1)
    repo.salvar(registro)

    resultado = CoordenadorAutorrecuperacao(repo, motor, relogio=lambda: INSTANTE).executar_ciclo()[0]

    assert resultado.decisao == DecisaoRecuperacao.ESCALAR_HUMANO
    assert chamadas == ['retry-sem-politica']
    assert repo.buscar_por_event_id(evento.event_id).estado == EstadoExecucao.FAILED_RETRYABLE


def test_health_vermelho_abre_circuito_e_nao_retenta():
    repo = RepositorioExecucoesEmMemoria()
    chamadas = []

    def acao(evento):
        chamadas.append(evento.event_id)
        raise FalhaTransitoria('timeout')

    motor, retry = _preparar_falha_retentavel(repo, _evento('retry-circuito'), acao)
    retry.next_retry_at = INSTANTE - timedelta(seconds=1)
    repo.salvar(retry)
    repo.salvar(_registro('final-1', EstadoExecucao.FAILED_FINAL))
    repo.salvar(_registro('final-2', EstadoExecucao.FAILED_FINAL))

    resultados = CoordenadorAutorrecuperacao(repo, motor, relogio=lambda: INSTANTE).executar_ciclo()
    por_evento = {r.event_id: r for r in resultados}

    assert por_evento['retry-circuito'].decisao == DecisaoRecuperacao.CIRCUITO_ABERTO
    assert por_evento['final-1'].decisao == DecisaoRecuperacao.ESCALAR_HUMANO
    assert chamadas == ['retry-circuito']


def test_evento_executing_antigo_nunca_recebe_replay_automatico():
    repo = RepositorioExecucoesEmMemoria()
    preso = _registro(
        'worker-morto',
        EstadoExecucao.EXECUTING,
        atualizado_em=INSTANTE - timedelta(hours=1),
    )
    repo.salvar(preso)
    motor = MotorOrquestrador(repo, {})

    resultado = CoordenadorAutorrecuperacao(repo, motor, relogio=lambda: INSTANTE).executar_ciclo()[0]

    assert resultado.decisao == DecisaoRecuperacao.ESCALAR_HUMANO
    assert resultado.estado_final == EstadoExecucao.EXECUTING
    assert 'confirmar morte do worker' in resultado.motivo


def test_trilha_de_recuperacao_sobrevive_restart_sqlite(tmp_path):
    db = tmp_path / 'orquestrador.sqlite3'
    chamadas = []

    def acao(evento):
        chamadas.append(evento.event_id)
        if len(chamadas) == 1:
            raise FalhaTransitoria('timeout')
        return ResultadoAcao(sucesso=True, evidencia='ok apos restart')

    repo = RepositorioExecucoesSQLite(db)
    evento = _evento('retry-restart')
    _, registro = _preparar_falha_retentavel(repo, evento, acao)
    registro.next_retry_at = INSTANTE - timedelta(seconds=1)
    repo.salvar(registro)
    repo.fechar()

    repo_reaberto = RepositorioExecucoesSQLite(db)
    motor_reaberto = MotorOrquestrador(repo_reaberto, {evento.event_type.value: acao})
    CoordenadorAutorrecuperacao(
        repo_reaberto, motor_reaberto, relogio=lambda: INSTANTE,
    ).executar_ciclo()
    repo_reaberto.fechar()

    repo_final = RepositorioExecucoesSQLite(db)
    assert repo_final.buscar_por_event_id(evento.event_id).estado == EstadoExecucao.SUCCEEDED
    assert [r.decisao for r in repo_final.listar_recuperacoes(evento.event_id)] == [
        'RETRY_AUTORIZADO',
        'RETRY_EXECUTADO',
    ]
    repo_final.fechar()


def test_restart_sqlite_preserva_metadados_de_autonomia_e_acao(tmp_path):
    """O snapshot persistido precisa explicar quem decidiu e o que executou."""
    db = tmp_path / 'orquestrador.sqlite3'
    evento = _evento('metadados-restart')
    repo = RepositorioExecucoesSQLite(db)
    motor = MotorOrquestrador(
        repo,
        {
            evento.event_type.value: lambda _: ResultadoAcao(
                sucesso=True,
                evidencia='metadados persistidos',
            )
        },
    )

    concluido = motor.processar(evento)
    assert concluido.nivel_autonomia == 4
    assert concluido.acao == TipoEvento.GIT_MAIN_AVANCOU.value
    repo.fechar()

    repo_reaberto = RepositorioExecucoesSQLite(db)
    persistido = repo_reaberto.buscar_por_event_id(evento.event_id)
    assert persistido.nivel_autonomia == 4
    assert persistido.acao == TipoEvento.GIT_MAIN_AVANCOU.value
    assert persistido.estado == EstadoExecucao.SUCCEEDED
    repo_reaberto.fechar()


def test_crash_real_de_processo_nao_dispara_auto_replay(tmp_path):
    """SIG-like exit prova que EXECUTING persiste antes do efeito externo.

    O processo filho realiza um efeito local observavel e morre via
    ``os._exit`` dentro da Acao. Um novo processo logico encontra o evento
    preso, registra escalonamento e nunca executa a Acao automaticamente.
    """
    db = tmp_path / 'orquestrador.sqlite3'
    marcador = tmp_path / 'efeitos.log'
    event_id = 'crash-processo-real'
    contexto = multiprocessing.get_context('spawn')
    processo = contexto.Process(
        target=_worker_crash_real,
        args=(str(db), str(marcador), event_id),
    )

    processo.start()
    processo.join(timeout=15)
    if processo.is_alive():
        processo.terminate()
        processo.join(timeout=5)
        pytest.fail('worker de crash real nao terminou no prazo')

    assert processo.exitcode == 73
    assert marcador.read_text(encoding='utf-8').splitlines() == [event_id]

    repo_reaberto = RepositorioExecucoesSQLite(db)
    preso = repo_reaberto.buscar_por_event_id(event_id)
    assert preso.estado == EstadoExecucao.EXECUTING
    assert preso.nivel_autonomia == 4
    assert preso.acao == TipoEvento.GIT_MAIN_AVANCOU.value
    assert MonitorSaudemotorPersistente(repo_reaberto).obter_saude().saude == 'AMARELO'

    chamadas_apos_restart = []

    def acao_que_nao_pode_rodar(evento):
        chamadas_apos_restart.append(evento.event_id)
        _anexar_marcador(str(marcador), f'reexecutado:{evento.event_id}')
        return ResultadoAcao(sucesso=True, evidencia='nao deveria executar')

    motor_reaberto = MotorOrquestrador(
        repo_reaberto,
        {TipoEvento.GIT_MAIN_AVANCOU.value: acao_que_nao_pode_rodar},
    )
    decisoes = CoordenadorAutorrecuperacao(
        repo_reaberto,
        motor_reaberto,
        relogio=lambda: preso.atualizado_em + timedelta(hours=1),
    ).executar_ciclo()

    assert [resultado.decisao for resultado in decisoes] == [
        DecisaoRecuperacao.ESCALAR_HUMANO
    ]
    assert chamadas_apos_restart == []
    assert marcador.read_text(encoding='utf-8').splitlines() == [event_id]
    assert repo_reaberto.buscar_por_event_id(event_id).estado == EstadoExecucao.EXECUTING
    assert [r.decisao for r in repo_reaberto.listar_recuperacoes(event_id)] == [
        'ESCALAR_HUMANO'
    ]
    repo_reaberto.fechar()


def test_dois_processos_de_recovery_executam_um_unico_retry_sqlite(tmp_path):
    """Processos independentes provam o CAS, nao apenas threads Python."""
    db = tmp_path / 'orquestrador.sqlite3'
    marcador = tmp_path / 'retries.log'
    evento = _evento('retry-multiprocesso')

    repo_inicial = RepositorioExecucoesSQLite(db)

    def primeira_tentativa(_evento_recebido):
        raise FalhaTransitoria('falha anterior ao efeito')

    _, registro = _preparar_falha_retentavel(
        repo_inicial,
        evento,
        primeira_tentativa,
    )
    registro.next_retry_at = INSTANTE - timedelta(seconds=1)
    repo_inicial.salvar(registro)
    repo_inicial.fechar()

    contexto = multiprocessing.get_context('spawn')
    barreira = contexto.Barrier(2)
    resultados = contexto.Queue()
    processos = [
        contexto.Process(
            target=_worker_retry_multiprocesso,
            args=(str(db), str(marcador), barreira, resultados),
        )
        for _ in range(2)
    ]
    for processo in processos:
        processo.start()
    for processo in processos:
        processo.join(timeout=20)
        if processo.is_alive():
            processo.terminate()
            processo.join(timeout=5)
            pytest.fail('worker multiprocesso nao terminou no prazo')

    respostas = [resultados.get(timeout=5) for _ in processos]
    assert all(processo.exitcode == 0 for processo in processos)
    assert all(status == 'ok' for status, _ in respostas), respostas

    repo_final = RepositorioExecucoesSQLite(db)
    persistido = repo_final.buscar_por_event_id(evento.event_id)
    assert persistido.estado == EstadoExecucao.SUCCEEDED
    assert persistido.attempt == 2
    assert marcador.read_text(encoding='utf-8').splitlines() == [evento.event_id]
    decisoes = [decisao for _, lista in respostas for decisao in lista]
    assert decisoes.count(DecisaoRecuperacao.RETRY_EXECUTADO.value) == 1
    assert decisoes.count(DecisaoRecuperacao.IGNORADO_CONCORRENCIA.value) == 1
    assert [
        entrada.motivo
        for entrada in repo_final.listar_auditoria(evento.event_id)
    ].count('retry_reivindicado_atomicamente') == 1
    repo_final.fechar()


def test_e2e_restart_dlq_auditoria_health_e_replay_manual(tmp_path):
    """Cadeia maior: retry seguro -> DLQ -> restart -> gate -> replay humano."""
    db = tmp_path / 'orquestrador.sqlite3'
    modo = {'falhar': True}

    def acao(evento):
        if modo['falhar']:
            raise FalhaTransitoria('servico indisponivel')
        return ResultadoAcao(sucesso=True, evidencia='servico recuperado')

    repo = RepositorioExecucoesSQLite(db)
    dlq = FilaDesistenciaEmMemoria()
    evento = _evento('e2e-recovery')
    motor = MotorOrquestrador(
        repo,
        {evento.event_type.value: acao},
        fila_desistencia=dlq,
    )

    registro = motor.processar(evento)  # attempt 1
    for _ in range(2):
        registro.next_retry_at = INSTANTE - timedelta(seconds=1)
        repo.salvar(registro)
        resultado = CoordenadorAutorrecuperacao(
            repo, motor, relogio=lambda: INSTANTE,
        ).executar_ciclo()[0]
        registro = repo.buscar_por_event_id(evento.event_id)

    assert resultado.decisao == DecisaoRecuperacao.ESCALAR_HUMANO
    assert registro.estado == EstadoExecucao.FAILED_FINAL
    assert registro.attempt == 3
    assert [item.event_id for item in dlq.listar_todos()] == [evento.event_id]
    assert MonitorSaudemotorPersistente(repo).obter_saude().saude == 'VERMELHO'
    auditoria_antes = repo.listar_auditoria(evento.event_id)
    repo.fechar()

    # Restart nao faz replay de FAILED_FINAL. A decisao continua humana.
    repo_reaberto = RepositorioExecucoesSQLite(db)
    motor_reaberto = MotorOrquestrador(
        repo_reaberto,
        {evento.event_type.value: acao},
    )
    decisoes = CoordenadorAutorrecuperacao(
        repo_reaberto, motor_reaberto, relogio=lambda: INSTANTE,
    ).executar_ciclo()
    assert decisoes[0].decisao == DecisaoRecuperacao.ESCALAR_HUMANO
    assert repo_reaberto.buscar_por_event_id(evento.event_id).estado == EstadoExecucao.FAILED_FINAL
    assert len(repo_reaberto.listar_auditoria(evento.event_id)) == len(auditoria_antes)

    # Somente depois da decisao humana explicita o replay e executado.
    modo['falhar'] = False
    recuperado = motor_reaberto.replay(
        evento.event_id,
        solicitado_por='operador_teste',
        motivo='servico validado fora de banda; replay autorizado',
    )
    assert recuperado.estado == EstadoExecucao.SUCCEEDED
    assert MonitorSaudemotorPersistente(repo_reaberto).obter_saude().saude == 'VERDE'
    assert len(repo_reaberto.listar_auditoria(evento.event_id)) > len(auditoria_antes)
    repo_reaberto.fechar()


def test_dois_workers_de_recovery_nao_duplicam_retry_sqlite(tmp_path):
    db = tmp_path / 'orquestrador.sqlite3'
    chamadas = []
    lock = threading.Lock()

    def acao(evento):
        with lock:
            chamadas.append(evento.event_id)
            numero = len(chamadas)
        if numero == 1:
            raise FalhaTransitoria('primeira tentativa falha')
        time.sleep(0.05)
        return ResultadoAcao(sucesso=True, evidencia='um unico retry')

    repo_inicial = RepositorioExecucoesSQLite(db)
    evento = _evento('retry-concorrente')
    _, registro = _preparar_falha_retentavel(repo_inicial, evento, acao)
    registro.next_retry_at = INSTANTE - timedelta(seconds=1)
    repo_inicial.salvar(registro)
    repo_inicial.fechar()

    barreira = threading.Barrier(2)
    decisoes = []
    decisoes_lock = threading.Lock()

    def worker():
        repo = RepositorioExecucoesSQLite(db)
        motor = MotorOrquestrador(repo, {evento.event_type.value: acao})
        coordenador = CoordenadorAutorrecuperacao(repo, motor, relogio=lambda: INSTANTE)
        barreira.wait()
        resultados = coordenador.executar_ciclo()
        with decisoes_lock:
            decisoes.extend(r.decisao for r in resultados)
        repo.fechar()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    repo_final = RepositorioExecucoesSQLite(db)
    assert repo_final.buscar_por_event_id(evento.event_id).estado == EstadoExecucao.SUCCEEDED
    assert len(chamadas) == 2  # tentativa inicial + exatamente um retry
    assert DecisaoRecuperacao.RETRY_EXECUTADO in decisoes
    repo_final.fechar()


def test_reivindicacao_de_retry_e_atomica_com_corrida_forcada_sqlite(tmp_path):
    """Barrier prova o CAS; nao depende da sorte do escalonador."""
    db = tmp_path / 'orquestrador.sqlite3'
    chamadas = []
    lock = threading.Lock()

    def acao(evento):
        with lock:
            chamadas.append(evento.event_id)
            numero = len(chamadas)
        if numero == 1:
            raise FalhaTransitoria('primeira tentativa')
        time.sleep(0.05)
        return ResultadoAcao(sucesso=True, evidencia='retry unico')

    repo_inicial = RepositorioExecucoesSQLite(db)
    evento = _evento('retry-cas-forcado')
    _preparar_falha_retentavel(repo_inicial, evento, acao)
    repo_inicial.fechar()

    barreira_reivindicacao = threading.Barrier(2, timeout=2)

    class RepositorioComBarreira(RepositorioExecucoesSQLite):
        def reivindicar_retry(self, event_id, reivindicado_em):
            barreira_reivindicacao.wait()
            return super().reivindicar_retry(event_id, reivindicado_em)

    resultados = []
    resultados_lock = threading.Lock()

    def worker():
        repo = RepositorioComBarreira(db)
        motor = MotorOrquestrador(repo, {evento.event_type.value: acao})
        resultado = motor.processar(evento)
        with resultados_lock:
            resultados.append(resultado.estado)
        repo.fechar()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    repo_final = RepositorioExecucoesSQLite(db)
    assert repo_final.buscar_por_event_id(evento.event_id).estado == EstadoExecucao.SUCCEEDED
    assert len(chamadas) == 2  # tentativa inicial + um unico retry
    assert EstadoExecucao.SUCCEEDED in resultados
    assert len(repo_final.listar_auditoria(evento.event_id)) >= 6
    repo_final.fechar()
