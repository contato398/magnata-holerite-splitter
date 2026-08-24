"""
Testes de persistencia da event store (SQLite) do Orquestrador.

Verifica:
- Persistencia entre processos/contextos
- Idempotencia de salvar
- Integridade de dados
- Gerenciamento de conexao
"""
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from magnata_os.orquestrador.eventos import EstadoExecucao
from magnata_os.orquestrador.repositorio_execucoes import (
    RegistroExecucao,
    RepositorioExecucoesSQLite,
)


def _criar_registro(
    event_id: str = 'evt-1',
    event_type: str = 'GIT_MAIN_AVANCOU',
    estado: EstadoExecucao = EstadoExecucao.RECEIVED,
    nivel_autonomia: int = 4,
    acao: str = 'git_main_avancou',
    resultado: str = None,
    evidencia: str = None,
    attempt: int = 1,
    next_retry_at: datetime = None,
    last_error_classe: str = None,
    last_error_at: datetime = None,
    criado_em: datetime = None,
    atualizado_em: datetime = None,
) -> RegistroExecucao:
    agora = datetime.fromisoformat('2026-08-24T12:00:00')
    return RegistroExecucao(
        event_id=event_id,
        event_type=event_type,
        estado=estado,
        nivel_autonomia=nivel_autonomia,
        acao=acao,
        resultado=resultado,
        evidencia=evidencia,
        attempt=attempt,
        next_retry_at=next_retry_at,
        last_error_classe=last_error_classe,
        last_error_at=last_error_at,
        criado_em=criado_em or agora,
        atualizado_em=atualizado_em or agora,
    )


class TestRepositorioExecucoesSQLite:
    """Testes de persistencia SQLite."""

    def test_salvar_e_buscar_persistence(self):
        """Dados salvos em SQLite sao recuperaveis apos fechar conexao."""
        with TemporaryDirectory() as tmpdir:
            caminho = Path(tmpdir) / 'events.db'

            # Contexto 1: salvar
            repo1 = RepositorioExecucoesSQLite(caminho)
            registro = _criar_registro(
                event_id='evt-1',
                estado=EstadoExecucao.EXECUTING,
                resultado='em progresso',
            )
            repo1.salvar(registro)
            repo1.fechar()

            # Contexto 2: buscar em novo repositorio
            repo2 = RepositorioExecucoesSQLite(caminho)
            recuperado = repo2.buscar_por_event_id('evt-1')
            repo2.fechar()

            assert recuperado is not None
            assert recuperado.event_id == 'evt-1'
            assert recuperado.estado == EstadoExecucao.EXECUTING
            assert recuperado.resultado == 'em progresso'
            assert recuperado.attempt == 1

    def test_salvar_de_novo_atualiza_nao_duplica(self):
        """Salvar mesmo event_id nao duplica registros, atualiza estado."""
        with TemporaryDirectory() as tmpdir:
            caminho = Path(tmpdir) / 'events.db'
            repo = RepositorioExecucoesSQLite(caminho)

            # Primeira salva
            reg1 = _criar_registro(
                event_id='evt-1',
                estado=EstadoExecucao.EXECUTING,
                attempt=1,
                resultado=None,
            )
            repo.salvar(reg1)

            # Segunda salva mesmo event_id, novo estado
            agora = datetime.fromisoformat('2026-08-24T12:05:00')
            reg2 = _criar_registro(
                event_id='evt-1',
                estado=EstadoExecucao.SUCCEEDED,
                attempt=2,
                resultado='sucesso',
                atualizado_em=agora,
            )
            repo.salvar(reg2)

            # Verificar que nao duplicou
            todos = repo.listar_todos()
            assert len(todos) == 1

            # Verificar que atualizou
            recuperado = repo.buscar_por_event_id('evt-1')
            assert recuperado.estado == EstadoExecucao.SUCCEEDED
            assert recuperado.attempt == 2
            assert recuperado.resultado == 'sucesso'
            assert recuperado.atualizado_em == agora

    def test_buscar_nao_encontrado(self):
        """Buscar event_id inexistente retorna None."""
        with TemporaryDirectory() as tmpdir:
            repo = RepositorioExecucoesSQLite(Path(tmpdir) / 'events.db')
            assert repo.buscar_por_event_id('evt-inexistente') is None

    def test_listar_todos_multiplos_registros(self):
        """listar_todos retorna todos os registros."""
        with TemporaryDirectory() as tmpdir:
            repo = RepositorioExecucoesSQLite(Path(tmpdir) / 'events.db')

            # Salvar 3 registros
            for i in range(1, 4):
                repo.salvar(_criar_registro(event_id=f'evt-{i}'))

            # Listar
            todos = repo.listar_todos()
            assert len(todos) == 3
            ids = {r.event_id for r in todos}
            assert ids == {'evt-1', 'evt-2', 'evt-3'}

    def test_datetime_serializa_isoformat(self):
        """Datas sao salvas/recuperadas como ISO format."""
        with TemporaryDirectory() as tmpdir:
            caminho = Path(tmpdir) / 'events.db'
            repo = RepositorioExecucoesSQLite(caminho)

            agora = datetime.fromisoformat('2026-08-24T12:34:56')
            proximo_retry = agora + timedelta(seconds=120)

            reg = RegistroExecucao(
                event_id='evt-1',
                event_type='GIT_MAIN_AVANCOU',
                estado=EstadoExecucao.FAILED_RETRYABLE,
                nivel_autonomia=4,
                acao='teste',
                resultado='falha temporaria',
                evidencia=None,
                attempt=1,
                next_retry_at=proximo_retry,
                last_error_classe='TRANSIENT',
                last_error_at=agora,
                criado_em=agora,
                atualizado_em=agora,
            )
            repo.salvar(reg)
            repo.fechar()

            # Verificar recuperacao preserva datetime
            repo2 = RepositorioExecucoesSQLite(caminho)
            recuperado = repo2.buscar_por_event_id('evt-1')

            assert recuperado.criado_em == agora
            assert recuperado.atualizado_em == agora
            assert recuperado.next_retry_at == proximo_retry
            assert recuperado.last_error_at == agora
            repo2.fechar()

    def test_nullable_fields_preservados(self):
        """Campos opcionais (None) sao preservados corretamente."""
        with TemporaryDirectory() as tmpdir:
            caminho = Path(tmpdir) / 'events.db'
            repo = RepositorioExecucoesSQLite(caminho)

            # Criar com campos None
            agora = datetime.fromisoformat('2026-08-24T12:00:00')
            reg = RegistroExecucao(
                event_id='evt-1',
                event_type='GIT_MAIN_AVANCOU',
                estado=EstadoExecucao.RECEIVED,
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
            repo.salvar(reg)
            repo.fechar()

            # Recuperar e verificar None
            repo2 = RepositorioExecucoesSQLite(caminho)
            recuperado = repo2.buscar_por_event_id('evt-1')

            assert recuperado.resultado is None
            assert recuperado.evidencia is None
            assert recuperado.next_retry_at is None
            assert recuperado.last_error_classe is None
            assert recuperado.last_error_at is None
            repo2.fechar()

    def test_estado_enum_serializa_e_recupera(self):
        """EstadoExecucao enum serializa como string e recupera como enum."""
        with TemporaryDirectory() as tmpdir:
            caminho = Path(tmpdir) / 'events.db'
            repo = RepositorioExecucoesSQLite(caminho)

            # Testar cada estado
            for estado in EstadoExecucao:
                reg = _criar_registro(
                    event_id=f'evt-{estado.value}',
                    estado=estado,
                )
                repo.salvar(reg)

            repo.fechar()

            # Recuperar e verificar
            repo2 = RepositorioExecucoesSQLite(caminho)
            for estado in EstadoExecucao:
                recuperado = repo2.buscar_por_event_id(f'evt-{estado.value}')
                assert recuperado.estado == estado
                assert isinstance(recuperado.estado, EstadoExecucao)
            repo2.fechar()

    def test_schema_criado_uma_vez(self):
        """Schema DDL executado uma vez mesmo se multiplas instancias."""
        with TemporaryDirectory() as tmpdir:
            caminho = Path(tmpdir) / 'events.db'

            # Primeira instancia cria schema
            repo1 = RepositorioExecucoesSQLite(caminho)
            repo1.salvar(_criar_registro(event_id='evt-1'))
            repo1.fechar()

            # Segunda instancia reutiliza schema (nao erro)
            repo2 = RepositorioExecucoesSQLite(caminho)
            reg = repo2.buscar_por_event_id('evt-1')
            assert reg is not None
            repo2.fechar()

    def test_concurrent_salvar_mesmo_event_id(self):
        """Salvar mesmo event_id duas vezes em contextos rapidos."""
        with TemporaryDirectory() as tmpdir:
            repo = RepositorioExecucoesSQLite(Path(tmpdir) / 'events.db')

            # Simular retentativa rapida
            reg1 = _criar_registro(
                event_id='evt-1',
                estado=EstadoExecucao.EXECUTING,
                attempt=1,
            )
            repo.salvar(reg1)

            reg2 = _criar_registro(
                event_id='evt-1',
                estado=EstadoExecucao.FAILED_RETRYABLE,
                attempt=1,
                resultado='falha transitoria',
            )
            repo.salvar(reg2)

            # Deve estar no estado mais recente
            recuperado = repo.buscar_por_event_id('evt-1')
            assert recuperado.estado == EstadoExecucao.FAILED_RETRYABLE
            assert recuperado.resultado == 'falha transitoria'

    def test_criar_db_em_subdiretorio(self):
        """Criar DB em subdiretorio cria diretorio se nao existir."""
        with TemporaryDirectory() as tmpdir:
            caminho = Path(tmpdir) / 'novo' / 'subdir' / 'events.db'
            assert not caminho.parent.exists()

            repo = RepositorioExecucoesSQLite(caminho)
            repo.salvar(_criar_registro(event_id='evt-1'))
            repo.fechar()

            # Diretorio foi criado
            assert caminho.exists()
            assert caminho.parent.exists()
