"""Snapshot somente leitura para o Painel Central.

A fonte é o repositório de execuções já existente no Grande Orquestrador.
Nenhum dado novo é persistido aqui e nenhum canal externo é chamado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from magnata_os.orquestrador.eventos import EstadoExecucao
from magnata_os.orquestrador.repositorio_execucoes import RepositorioExecucoes


@dataclass(frozen=True)
class SnapshotCentral:
    total_eventos: int
    sucesso: int
    aguardando_humano: int
    em_execucao: int
    falha_retentavel: int
    falha_final: int
    ignorados: int
    superados: int
    saude: str

    def para_dict(self) -> Dict[str, object]:
        return {
            "total_eventos": self.total_eventos,
            "sucesso": self.sucesso,
            "aguardando_humano": self.aguardando_humano,
            "em_execucao": self.em_execucao,
            "falha_retentavel": self.falha_retentavel,
            "falha_final": self.falha_final,
            "ignorados": self.ignorados,
            "superados": self.superados,
            "saude": self.saude,
        }


def construir_snapshot_central(
    repositorio: RepositorioExecucoes,
) -> SnapshotCentral:
    """Reconstrói o painel a partir do estado persistido, sem efeitos colaterais."""

    contagem = {estado: 0 for estado in EstadoExecucao}
    for registro in repositorio.listar_todos():
        if registro is not None:
            contagem[registro.estado] += 1

    total = sum(contagem.values())
    falhas = contagem[EstadoExecucao.FAILED_FINAL]
    retentaveis = contagem[EstadoExecucao.FAILED_RETRYABLE]
    gates = contagem[EstadoExecucao.WAITING_GATE]

    if total == 0:
        saude = "VERDE"
    elif falhas > 0:
        saude = "VERMELHO"
    elif retentaveis > 0 or gates > 0:
        saude = "AMARELO"
    else:
        saude = "VERDE"

    return SnapshotCentral(
        total_eventos=total,
        sucesso=contagem[EstadoExecucao.SUCCEEDED],
        aguardando_humano=gates,
        em_execucao=contagem[EstadoExecucao.EXECUTING],
        falha_retentavel=retentaveis,
        falha_final=falhas,
        ignorados=contagem[EstadoExecucao.IGNORED],
        superados=contagem[EstadoExecucao.SUPERSEDED],
        saude=saude,
    )
