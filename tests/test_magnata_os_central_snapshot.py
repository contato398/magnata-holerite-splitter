from datetime import datetime, timezone

from magnata_os.central.snapshot import construir_snapshot_central
from magnata_os.orquestrador.eventos import EstadoExecucao
from magnata_os.orquestrador.repositorio_execucoes import (
    RegistroExecucao,
    RepositorioExecucoesEmMemoria,
)


def registro(event_id: str, estado: EstadoExecucao) -> RegistroExecucao:
    agora = datetime.now(timezone.utc)
    return RegistroExecucao(
        event_id=event_id,
        event_type="COMUNICACAO_SOLICITADA",
        estado=estado,
        nivel_autonomia=1,
        acao="nenhuma",
        resultado=None,
        evidencia=None,
        attempt=0,
        next_retry_at=None,
        last_error_classe=None,
        last_error_at=None,
        criado_em=agora,
        atualizado_em=agora,
    )


def test_snapshot_eh_derivado_do_repositorio_sem_nova_fonte_de_verdade():
    repositorio = RepositorioExecucoesEmMemoria()
    for event_id, estado in (
        ("e1", EstadoExecucao.SUCCEEDED),
        ("e2", EstadoExecucao.WAITING_GATE),
        ("e3", EstadoExecucao.FAILED_RETRYABLE),
        ("e4", EstadoExecucao.EXECUTING),
    ):
        repositorio.salvar(registro(event_id, estado))

    snapshot = construir_snapshot_central(repositorio)

    assert snapshot.para_dict() == {
        "total_eventos": 4,
        "sucesso": 1,
        "aguardando_humano": 1,
        "em_execucao": 1,
        "falha_retentavel": 1,
        "falha_final": 0,
        "ignorados": 0,
        "superados": 0,
        "saude": "AMARELO",
    }


def test_falha_final_coloca_painel_em_vermelho():
    repositorio = RepositorioExecucoesEmMemoria()
    repositorio.salvar(registro("e-final", EstadoExecucao.FAILED_FINAL))

    snapshot = construir_snapshot_central(repositorio)

    assert snapshot.saude == "VERMELHO"


def test_sem_eventos_e_verde():
    snapshot = construir_snapshot_central(RepositorioExecucoesEmMemoria())

    assert snapshot.total_eventos == 0
    assert snapshot.saude == "VERDE"
