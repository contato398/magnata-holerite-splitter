from datetime import datetime, timezone

from magnata_os.orquestrador.eventos import EstadoExecucao
from magnata_os.orquestrador.repositorio_execucoes import RegistroExecucao, RepositorioExecucoesSQLite
from magnata_os.orquestrador.saude_motor import MonitorSaudemotorPersistente


def _registro(event_id: str, estado: EstadoExecucao) -> RegistroExecucao:
    agora = datetime(2026, 8, 24, 18, 0, tzinfo=timezone.utc)
    return RegistroExecucao(
        event_id=event_id,
        event_type='GIT_MAIN_AVANCOU',
        estado=estado,
        nivel_autonomia=4,
        acao='teste',
        resultado=None,
        evidencia=None,
        attempt=1,
        next_retry_at=None,
        last_error_classe=None,
        last_error_at=None,
        criado_em=agora,
        atualizado_em=agora,
    )


def test_health_persistente_sobrevive_reabertura_sqlite(tmp_path):
    caminho = tmp_path / 'orquestrador.sqlite3'
    repo = RepositorioExecucoesSQLite(caminho)
    repo.salvar(_registro('ok-1', EstadoExecucao.SUCCEEDED))
    repo.salvar(_registro('ok-2', EstadoExecucao.SUCCEEDED))
    repo.salvar(_registro('gate-1', EstadoExecucao.WAITING_GATE))
    repo.fechar()

    repo_reaberto = RepositorioExecucoesSQLite(caminho)
    saude = MonitorSaudemotorPersistente(repo_reaberto).obter_saude()
    repo_reaberto.fechar()

    assert saude.eventos_processados_total == 3
    assert saude.eventos_sucesso == 2
    assert saude.eventos_gate_humano == 1
    assert saude.saude == 'VERDE'


def test_health_persistente_reflete_estado_final_atual_sem_contar_transicoes(tmp_path):
    caminho = tmp_path / 'orquestrador.sqlite3'
    repo = RepositorioExecucoesSQLite(caminho)
    registro = _registro('retry-1', EstadoExecucao.FAILED_RETRYABLE)
    repo.salvar(registro)
    registro.estado = EstadoExecucao.SUCCEEDED
    repo.salvar(registro)

    saude = MonitorSaudemotorPersistente(repo).obter_saude()
    repo.fechar()

    assert saude.eventos_processados_total == 1
    assert saude.eventos_sucesso == 1
    assert saude.eventos_falha_retentavel == 0
    assert saude.saude == 'VERDE'


def test_health_persistente_fica_vermelho_com_falha_final_acima_de_30_porcento(tmp_path):
    caminho = tmp_path / 'orquestrador.sqlite3'
    repo = RepositorioExecucoesSQLite(caminho)
    repo.salvar(_registro('ok-1', EstadoExecucao.SUCCEEDED))
    repo.salvar(_registro('fail-1', EstadoExecucao.FAILED_FINAL))
    repo.salvar(_registro('fail-2', EstadoExecucao.FAILED_FINAL))

    saude = MonitorSaudemotorPersistente(repo).obter_saude()
    repo.fechar()

    assert saude.eventos_processados_total == 3
    assert saude.eventos_falha_final == 2
    assert saude.saude == 'VERMELHO'
