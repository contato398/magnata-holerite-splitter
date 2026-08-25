"""Adapter PostgreSQL duravel para o repositorio do Orquestrador.

O modulo implementa o mesmo ``RepositorioExecucoes`` usado por motor,
health, DLQ e supervisor. Ele recebe uma conexao DB-API ja criada: nao le
secret, nao conecta sozinho, nao aplica migration e nao escolhe fornecedor.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .eventos import EstadoExecucao
from .repositorio_execucoes import (
    RegistroAuditoria,
    RegistroExecucao,
    RegistroRecuperacao,
)


_COLUNAS_EXECUCAO = (
    'event_id', 'event_type', 'estado', 'nivel_autonomia', 'acao',
    'resultado', 'evidencia', 'attempt', 'next_retry_at',
    'last_error_classe', 'last_error_at', 'criado_em', 'atualizado_em',
    'evento_json', 'manualmente_reiniciado_por',
    'manualmente_reiniciado_em', 'motivo_reinicio_manual',
)
_COLUNAS_SQL = ', '.join(_COLUNAS_EXECUCAO)
_TABELA_EXECUCOES = 'magnata_orquestrador.execucoes'
_TABELA_AUDITORIA = 'magnata_orquestrador.auditoria'
_TABELA_RECUPERACAO = 'magnata_orquestrador.auditoria_recuperacao'


def _datetime(valor):
    if valor is None or isinstance(valor, datetime):
        return valor
    return datetime.fromisoformat(valor)


def _registro_para_linha(registro: RegistroExecucao) -> tuple:
    return (
        registro.event_id,
        registro.event_type,
        registro.estado.value,
        registro.nivel_autonomia,
        registro.acao,
        registro.resultado,
        registro.evidencia,
        registro.attempt,
        registro.next_retry_at,
        registro.last_error_classe,
        registro.last_error_at,
        registro.criado_em,
        registro.atualizado_em,
        registro.evento_json,
        registro.manualmente_reiniciado_por,
        registro.manualmente_reiniciado_em,
        registro.motivo_reinicio_manual,
    )


def _linha_para_registro(linha: tuple) -> RegistroExecucao:
    dados = dict(zip(_COLUNAS_EXECUCAO, linha))
    return RegistroExecucao(
        event_id=dados['event_id'],
        event_type=dados['event_type'],
        estado=EstadoExecucao(dados['estado']),
        nivel_autonomia=dados['nivel_autonomia'],
        acao=dados['acao'],
        resultado=dados['resultado'],
        evidencia=dados['evidencia'],
        attempt=dados['attempt'],
        next_retry_at=_datetime(dados['next_retry_at']),
        last_error_classe=dados['last_error_classe'],
        last_error_at=_datetime(dados['last_error_at']),
        criado_em=_datetime(dados['criado_em']),
        atualizado_em=_datetime(dados['atualizado_em']),
        evento_json=dados['evento_json'],
        manualmente_reiniciado_por=dados['manualmente_reiniciado_por'],
        manualmente_reiniciado_em=_datetime(
            dados['manualmente_reiniciado_em']
        ),
        motivo_reinicio_manual=dados['motivo_reinicio_manual'],
    )


class RepositorioExecucoesPostgres:
    """Persistencia duravel, transacional e independente de provedor."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def buscar_por_event_id(self, event_id: str) -> Optional[RegistroExecucao]:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'SELECT {_COLUNAS_SQL} FROM {_TABELA_EXECUCOES} '
                'WHERE event_id = %s',
                (event_id,),
            )
            linha = cursor.fetchone()
        return _linha_para_registro(linha) if linha else None

    def salvar(self, registro: RegistroExecucao) -> None:
        marcadores = ', '.join(['%s'] * len(_COLUNAS_EXECUCAO))
        atualizacoes = ', '.join(
            f'{coluna} = EXCLUDED.{coluna}'
            for coluna in _COLUNAS_EXECUCAO
            if coluna not in ('event_id', 'event_type', 'criado_em')
        )
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {_TABELA_EXECUCOES} ({_COLUNAS_SQL}) '
                    f'VALUES ({marcadores}) ON CONFLICT (event_id) '
                    f'DO UPDATE SET {atualizacoes}',
                    _registro_para_linha(registro),
                )
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise

    def criar_se_novo(self, registro: RegistroExecucao) -> bool:
        marcadores = ', '.join(['%s'] * len(_COLUNAS_EXECUCAO))
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {_TABELA_EXECUCOES} ({_COLUNAS_SQL}) '
                    f'VALUES ({marcadores}) ON CONFLICT (event_id) DO NOTHING '
                    'RETURNING event_id',
                    _registro_para_linha(registro),
                )
                criado = cursor.fetchone() is not None
            self._conexao.commit()
            return criado
        except Exception:
            self._conexao.rollback()
            raise

    def reivindicar_retry(
        self, event_id: str, reivindicado_em: datetime,
    ) -> Optional[RegistroExecucao]:
        """CAS e auditoria pertencem a uma unica instrucao/transacao."""
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'''WITH reivindicado AS (
                           UPDATE {_TABELA_EXECUCOES}
                              SET estado = %s, attempt = attempt + 1,
                                  next_retry_at = NULL, atualizado_em = %s
                            WHERE event_id = %s AND estado = %s
                        RETURNING {_COLUNAS_SQL}
                       ), auditado AS (
                           INSERT INTO {_TABELA_AUDITORIA}
                               (event_id, estado_anterior, estado_novo,
                                registrado_em, motivo)
                           SELECT event_id, %s, %s, %s, %s
                             FROM reivindicado
                           RETURNING id
                       )
                       SELECT {_COLUNAS_SQL} FROM reivindicado''',
                    (
                        EstadoExecucao.EXECUTING.value,
                        reivindicado_em,
                        event_id,
                        EstadoExecucao.FAILED_RETRYABLE.value,
                        EstadoExecucao.FAILED_RETRYABLE.value,
                        EstadoExecucao.EXECUTING.value,
                        reivindicado_em,
                        'retry_reivindicado_atomicamente',
                    ),
                )
                linha = cursor.fetchone()
            self._conexao.commit()
            return _linha_para_registro(linha) if linha else None
        except Exception:
            self._conexao.rollback()
            raise

    def listar_todos(self) -> List[RegistroExecucao]:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'SELECT {_COLUNAS_SQL} FROM {_TABELA_EXECUCOES} '
                'ORDER BY criado_em ASC, event_id ASC'
            )
            linhas = cursor.fetchall()
        return [_linha_para_registro(linha) for linha in linhas]

    def registrar_auditoria(
        self,
        event_id: str,
        estado_anterior: str,
        estado_novo: str,
        registrado_em: datetime,
        motivo: Optional[str] = None,
    ) -> None:
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {_TABELA_AUDITORIA} '
                    '(event_id, estado_anterior, estado_novo, registrado_em, motivo) '
                    'VALUES (%s, %s, %s, %s, %s)',
                    (
                        event_id, estado_anterior, estado_novo,
                        registrado_em, motivo,
                    ),
                )
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise

    def listar_auditoria(self, event_id: str) -> List[RegistroAuditoria]:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'SELECT event_id, estado_anterior, estado_novo, '
                f'registrado_em, motivo FROM {_TABELA_AUDITORIA} '
                'WHERE event_id = %s ORDER BY id ASC',
                (event_id,),
            )
            linhas = cursor.fetchall()
        return [
            RegistroAuditoria(
                event_id=linha[0],
                estado_anterior=linha[1],
                estado_novo=linha[2],
                registrado_em=_datetime(linha[3]),
                motivo=linha[4],
            )
            for linha in linhas
        ]

    def registrar_recuperacao(self, registro: RegistroRecuperacao) -> None:
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {_TABELA_RECUPERACAO} '
                    '(event_id, decisao, estado_observado, registrado_em, '
                    'motivo, evidencia) VALUES (%s, %s, %s, %s, %s, %s)',
                    (
                        registro.event_id,
                        registro.decisao,
                        registro.estado_observado,
                        registro.registrado_em,
                        registro.motivo,
                        registro.evidencia,
                    ),
                )
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise

    def listar_recuperacoes(self, event_id: str) -> List[RegistroRecuperacao]:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'SELECT event_id, decisao, estado_observado, registrado_em, '
                f'motivo, evidencia FROM {_TABELA_RECUPERACAO} '
                'WHERE event_id = %s ORDER BY id ASC',
                (event_id,),
            )
            linhas = cursor.fetchall()
        return [
            RegistroRecuperacao(
                event_id=linha[0],
                decisao=linha[1],
                estado_observado=linha[2],
                registrado_em=_datetime(linha[3]),
                motivo=linha[4],
                evidencia=linha[5],
            )
            for linha in linhas
        ]

    def fechar(self) -> None:
        self._conexao.close()
