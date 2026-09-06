"""Adapter PostgreSQL duravel para autorizacoes humanas de gate.

Implementa ``RepositorioAutorizacoesGate`` com conexao DB-API injetada.
Nao le secret, nao abre conexao, nao aplica migration e nao escolhe provedor.
O adapter preserva as invariantes do contrato shadow:
- um unico fato por (event_id, preview_id);
- repeticao da mesma decisao e idempotente;
- decisao conflitante nunca sobrescreve o fato original;
- nenhuma autorizacao altera EstadoExecucao nem executa transporte.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .autorizacao_gate import (
    ConflitoDecisaoGateError,
    DecisaoGate,
    RegistroAutorizacaoGate,
)

_TABELA = 'magnata_orquestrador.autorizacoes_gate'
_COLUNAS = (
    'autorizacao_id', 'event_id', 'preview_id', 'decisao',
    'ator_referencia', 'registrado_em', 'proveniencia',
)
_COLUNAS_SQL = ', '.join(_COLUNAS)


def _datetime(valor):
    if isinstance(valor, datetime):
        return valor
    return datetime.fromisoformat(valor)


def _linha_para_registro(linha: tuple) -> RegistroAutorizacaoGate:
    dados = dict(zip(_COLUNAS, linha))
    return RegistroAutorizacaoGate(
        autorizacao_id=dados['autorizacao_id'],
        event_id=dados['event_id'],
        preview_id=dados['preview_id'],
        decisao=DecisaoGate(dados['decisao']),
        ator_referencia=dados['ator_referencia'],
        registrado_em=_datetime(dados['registrado_em']),
        proveniencia=dados['proveniencia'],
    )


def _registro_para_linha(registro: RegistroAutorizacaoGate) -> tuple:
    return (
        registro.autorizacao_id,
        registro.event_id,
        registro.preview_id,
        registro.decisao.value,
        registro.ator_referencia,
        registro.registrado_em,
        registro.proveniencia,
    )


class RepositorioAutorizacoesGatePostgres:
    """Persistencia append-only para decisoes humanas de gate."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def registrar_se_novo(self, registro: RegistroAutorizacaoGate) -> bool:
        marcadores = ', '.join(['%s'] * len(_COLUNAS))
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {_TABELA} ({_COLUNAS_SQL}) '
                    f'VALUES ({marcadores}) '
                    'ON CONFLICT (event_id, preview_id) DO NOTHING '
                    f'RETURNING {_COLUNAS_SQL}',
                    _registro_para_linha(registro),
                )
                criada = cursor.fetchone()
                if criada is not None:
                    self._conexao.commit()
                    return True

                cursor.execute(
                    f'SELECT {_COLUNAS_SQL} FROM {_TABELA} '
                    'WHERE event_id = %s AND preview_id = %s',
                    (registro.event_id, registro.preview_id),
                )
                linha_existente = cursor.fetchone()
                if linha_existente is None:
                    raise RuntimeError(
                        'conflito de unicidade sem fato persistido recuperavel'
                    )
                existente = _linha_para_registro(linha_existente)
                if existente.decisao != registro.decisao:
                    raise ConflitoDecisaoGateError(
                        'gate ja possui decisao final diferente para esta previa'
                    )
            self._conexao.commit()
            return False
        except Exception:
            self._conexao.rollback()
            raise

    def buscar(
        self, event_id: str, preview_id: str,
    ) -> Optional[RegistroAutorizacaoGate]:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'SELECT {_COLUNAS_SQL} FROM {_TABELA} '
                'WHERE event_id = %s AND preview_id = %s',
                (event_id, preview_id),
            )
            linha = cursor.fetchone()
        return _linha_para_registro(linha) if linha else None

    def listar_por_evento(self, event_id: str) -> List[RegistroAutorizacaoGate]:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'SELECT {_COLUNAS_SQL} FROM {_TABELA} '
                'WHERE event_id = %s ORDER BY registrado_em ASC, autorizacao_id ASC',
                (event_id,),
            )
            linhas = cursor.fetchall()
        return [_linha_para_registro(linha) for linha in linhas]

    def fechar(self) -> None:
        self._conexao.close()
