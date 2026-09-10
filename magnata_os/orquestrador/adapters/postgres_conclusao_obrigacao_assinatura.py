"""Adapter Postgres para `magnata_orquestrador.conclusao_obrigacao_assinatura`
(migration 0006, inerte/não aplicada em produção nesta missão).

Mesmo padrão de `RepositorioExecucoesPostgres.registrar_recuperacao` /
`listar_recuperacoes`: append-only, sem UPDATE nem DELETE (a tabela em si
já bloqueia isso por trigger de banco -- este adapter nunca tenta).
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import List, Optional

_TABELA = 'magnata_orquestrador.conclusao_obrigacao_assinatura'
_ESTADOS_VALIDOS = (
    'AGUARDANDO_ASSINATURA', 'ASSINADO', 'COMPROVANTE_VALIDADO', 'CONCLUIDO',
)


@dataclasses.dataclass(frozen=True)
class RegistroConclusaoObrigacaoAssinatura:
    acao_execucao_id: str
    estado: str
    correlacao_externa: Optional[str]
    evidencia_sha256: Optional[str]
    registrado_em: datetime

    def __post_init__(self) -> None:
        if self.estado not in _ESTADOS_VALIDOS:
            raise ValueError(f'estado inválido para conclusão de assinatura: {self.estado}')


class RepositorioConclusaoObrigacaoAssinaturaPostgres:
    """Só duas operações: registrar uma nova transição (append) e ler o
    histórico/estado mais recente por `acao_execucao_id`. Nunca UPDATE,
    nunca DELETE -- a durabilidade e a auditabilidade vêm de nunca perder
    uma transição anterior, nunca de "corrigir" uma linha."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def registrar_transicao(
        self, registro: RegistroConclusaoObrigacaoAssinatura,
    ) -> None:
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {_TABELA} '
                    '(acao_execucao_id, estado, correlacao_externa, '
                    'evidencia_sha256, registrado_em) VALUES (%s, %s, %s, %s, %s)',
                    (
                        registro.acao_execucao_id, registro.estado,
                        registro.correlacao_externa, registro.evidencia_sha256,
                        registro.registrado_em,
                    ),
                )
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise

    def listar_historico(
        self, acao_execucao_id: str,
    ) -> List[RegistroConclusaoObrigacaoAssinatura]:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'SELECT acao_execucao_id, estado, correlacao_externa, '
                f'evidencia_sha256, registrado_em FROM {_TABELA} '
                'WHERE acao_execucao_id = %s ORDER BY id ASC',
                (acao_execucao_id,),
            )
            linhas = cursor.fetchall()
        return [
            RegistroConclusaoObrigacaoAssinatura(
                acao_execucao_id=linha[0], estado=linha[1],
                correlacao_externa=linha[2], evidencia_sha256=linha[3],
                registrado_em=linha[4],
            )
            for linha in linhas
        ]

    def estado_mais_recente(self, acao_execucao_id: str) -> Optional[str]:
        """Recuperável após restart só a partir do Postgres: o estado
        `CONCLUIDO` (ou qualquer outro) nunca vive em memória -- é sempre
        a última linha append-only para aquele `acao_execucao_id`."""
        historico = self.listar_historico(acao_execucao_id)
        return historico[-1].estado if historico else None

    def fechar(self) -> None:
        self._conexao.close()
