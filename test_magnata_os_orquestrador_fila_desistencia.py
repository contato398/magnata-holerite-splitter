"""
Testes da fila de desistencia (Dead-Letter Queue) do Orquestrador.

Verifica:
- Registro append-only de eventos permanentemente falhados
- Extracto de RegistroExecucao para ItemFilaDesistencia
- Filtragem e auditoria
"""
from datetime import datetime

import pytest

from magnata_os.orquestrador.eventos import EstadoExecucao
from magnata_os.orquestrador.fila_desistencia import (
    FilaDesistenciaEmMemoria,
    ItemFilaDesistencia,
    extrair_para_fila_desistencia,
)
from magnata_os.orquestrador.repositorio_execucoes import RegistroExecucao


def _registro_falha_final(
    event_id: str = 'evt-1',
    event_type: str = 'GIT_MAIN_AVANCOU',
    tentativas: int = 3,
    erro_classe: str = 'PERMANENT_ERROR',
    resultado: str = 'falha permanente',
) -> RegistroExecucao:
    agora = datetime.fromisoformat('2026-08-24T12:00:00')
    return RegistroExecucao(
        event_id=event_id,
        event_type=event_type,
        estado=EstadoExecucao.FAILED_FINAL,
        nivel_autonomia=4,
        acao='teste',
        resultado=resultado,
        evidencia=None,
        attempt=tentativas,
        next_retry_at=None,
        last_error_classe=erro_classe,
        last_error_at=agora,
        criado_em=agora,
        atualizado_em=agora,
    )


class TestFilaDesistenciaEmMemoria:
    """Testes da fila em memoria."""

    def test_registrar_e_listar_append_only(self):
        """Registrar e listar preserva ordem de chegada."""
        fila = FilaDesistenciaEmMemoria()

        item1 = ItemFilaDesistencia(
            event_id='evt-1',
            event_type='GIT_MAIN_AVANCOU',
            tentativas_consumidas=3,
            ultimo_erro_classe='PERMANENT',
            ultimo_erro_at=datetime.fromisoformat('2026-08-24T12:00:00'),
            resultado_final='falha permanente',
            registrado_em=datetime.fromisoformat('2026-08-24T12:00:00'),
        )
        item2 = ItemFilaDesistencia(
            event_id='evt-2',
            event_type='PR_MESCLADO',
            tentativas_consumidas=1,
            ultimo_erro_classe='INVALID_INPUT',
            ultimo_erro_at=datetime.fromisoformat('2026-08-24T12:01:00'),
            resultado_final='entrada invalida',
            registrado_em=datetime.fromisoformat('2026-08-24T12:01:00'),
        )

        fila.registrar(item1)
        fila.registrar(item2)

        todos = fila.listar_todos()
        assert len(todos) == 2
        assert todos[0].event_id == 'evt-1'
        assert todos[1].event_id == 'evt-2'

    def test_registrar_mesmo_event_id_nao_deduplica(self):
        """Registrar mesmo event_id duas vezes cria dois itens."""
        fila = FilaDesistenciaEmMemoria()

        item = ItemFilaDesistencia(
            event_id='evt-1',
            event_type='GIT_MAIN_AVANCOU',
            tentativas_consumidas=3,
            ultimo_erro_classe='PERMANENT',
            ultimo_erro_at=datetime.fromisoformat('2026-08-24T12:00:00'),
            resultado_final='falha permanente',
            registrado_em=datetime.fromisoformat('2026-08-24T12:00:00'),
        )

        fila.registrar(item)
        fila.registrar(item)

        todos = fila.listar_todos()
        assert len(todos) == 2

    def test_filtrar_por_event_type(self):
        """Listar por event_type filtra corretamente."""
        fila = FilaDesistenciaEmMemoria()

        agora = datetime.fromisoformat('2026-08-24T12:00:00')
        for i, tipo in enumerate(['GIT_MAIN_AVANCOU', 'GIT_MAIN_AVANCOU', 'PR_MESCLADO']):
            item = ItemFilaDesistencia(
                event_id=f'evt-{i}',
                event_type=tipo,
                tentativas_consumidas=1,
                ultimo_erro_classe='ERROR',
                ultimo_erro_at=agora,
                resultado_final='falha',
                registrado_em=agora,
            )
            fila.registrar(item)

        git_main = fila.listar_por_event_type('GIT_MAIN_AVANCOU')
        assert len(git_main) == 2
        assert all(item.event_type == 'GIT_MAIN_AVANCOU' for item in git_main)

        pr = fila.listar_por_event_type('PR_MESCLADO')
        assert len(pr) == 1
        assert pr[0].event_type == 'PR_MESCLADO'

    def test_item_e_immutable(self):
        """ItemFilaDesistencia e frozen (immutable)."""
        item = ItemFilaDesistencia(
            event_id='evt-1',
            event_type='GIT_MAIN_AVANCOU',
            tentativas_consumidas=3,
            ultimo_erro_classe='ERROR',
            ultimo_erro_at=datetime.fromisoformat('2026-08-24T12:00:00'),
            resultado_final='falha',
            registrado_em=datetime.fromisoformat('2026-08-24T12:00:00'),
        )

        # Tentar modificar deve falhar
        with pytest.raises(AttributeError):
            item.event_id = 'evt-2'


class TestExtrairParaFilaDesistencia:
    """Testes de extracao de RegistroExecucao para fila."""

    def test_extracao_de_failed_final(self):
        """Extracao de FAILED_FINAL retorna item valido."""
        registro = _registro_falha_final(
            event_id='evt-1',
            event_type='GIT_MAIN_AVANCOU',
            tentativas=3,
            erro_classe='PERMANENT_ERROR',
        )

        item = extrair_para_fila_desistencia(registro)

        assert item is not None
        assert item.event_id == 'evt-1'
        assert item.event_type == 'GIT_MAIN_AVANCOU'
        assert item.tentativas_consumidas == 3
        assert item.ultimo_erro_classe == 'PERMANENT_ERROR'

    def test_extracao_de_nao_failed_final_retorna_none(self):
        """Extracao de estado nao-FAILED_FINAL retorna None."""
        agora = datetime.fromisoformat('2026-08-24T12:00:00')

        # SUCCEEDED
        registro_ok = RegistroExecucao(
            event_id='evt-1',
            event_type='GIT_MAIN_AVANCOU',
            estado=EstadoExecucao.SUCCEEDED,
            nivel_autonomia=4,
            acao='teste',
            resultado='sucesso',
            evidencia=None,
            attempt=1,
            next_retry_at=None,
            last_error_classe=None,
            last_error_at=None,
            criado_em=agora,
            atualizado_em=agora,
        )
        assert extrair_para_fila_desistencia(registro_ok) is None

        # FAILED_RETRYABLE
        registro_retry = RegistroExecucao(
            event_id='evt-2',
            event_type='GIT_MAIN_AVANCOU',
            estado=EstadoExecucao.FAILED_RETRYABLE,
            nivel_autonomia=4,
            acao='teste',
            resultado='falha transitoria',
            evidencia=None,
            attempt=1,
            next_retry_at=agora,
            last_error_classe='TRANSIENT',
            last_error_at=agora,
            criado_em=agora,
            atualizado_em=agora,
        )
        assert extrair_para_fila_desistencia(registro_retry) is None

        # WAITING_GATE
        registro_gate = RegistroExecucao(
            event_id='evt-3',
            event_type='GIT_MAIN_AVANCOU',
            estado=EstadoExecucao.WAITING_GATE,
            nivel_autonomia=5,
            acao='teste',
            resultado='aguardando revisao',
            evidencia=None,
            attempt=0,
            next_retry_at=None,
            last_error_classe=None,
            last_error_at=None,
            criado_em=agora,
            atualizado_em=agora,
        )
        assert extrair_para_fila_desistencia(registro_gate) is None

    def test_preserva_resultado_null_como_desconhecido(self):
        """Se resultado e None, usa 'desconhecido' no item."""
        agora = datetime.fromisoformat('2026-08-24T12:00:00')
        registro = RegistroExecucao(
            event_id='evt-1',
            event_type='GIT_MAIN_AVANCOU',
            estado=EstadoExecucao.FAILED_FINAL,
            nivel_autonomia=4,
            acao='teste',
            resultado=None,  # Null
            evidencia=None,
            attempt=3,
            next_retry_at=None,
            last_error_classe='ERROR',
            last_error_at=agora,
            criado_em=agora,
            atualizado_em=agora,
        )

        item = extrair_para_fila_desistencia(registro)
        assert item.resultado_final == 'desconhecido'

    def test_timestamp_registrado_em_e_utcnow(self):
        """Item tem registrado_em = agora quando extraido."""
        registro = _registro_falha_final()

        antes = datetime.utcnow()
        item = extrair_para_fila_desistencia(registro)
        depois = datetime.utcnow()

        assert antes <= item.registrado_em <= depois
