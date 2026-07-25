"""
Repositorios da esteira operacional (Modulo 01, Fase 3) -- interfaces +
implementacao em memoria.

Mesma disciplina de repositorio.py (Fase 1): Protocols primeiro,
implementacao em memoria com threading.Lock para uso seguro em testes de
concorrencia. Nenhum adapter Postgres nesta fase -- ver migrations/ para
o schema que um adapter futuro vai preencher (fora de escopo aqui, ver
MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3.md).
"""
from __future__ import annotations

import threading
from typing import Callable, List, Optional, Protocol, Tuple

from .dominio_esteira import EstadoEsteiraDocumento, EtapaEsteira, LoteDocumental, SituacaoEsteira


class RepositorioLotes(Protocol):
    """Contrato de persistencia de LoteDocumental."""

    def buscar_por_id(self, lote_id: str) -> Optional[LoteDocumental]: ...

    def salvar(self, lote: LoteDocumental) -> None: ...

    def listar_recentes(self, limite: int = 50) -> List[LoteDocumental]: ...

    def listar_todos(self) -> List[LoteDocumental]: ...


class RepositorioEstadosEsteira(Protocol):
    """Contrato de persistencia de EstadoEsteiraDocumento -- uma linha
    por documento_id (estado ATUAL, nao historico)."""

    def buscar_por_documento_id(self, documento_id: str) -> Optional[EstadoEsteiraDocumento]: ...

    def salvar(self, estado: EstadoEsteiraDocumento) -> None: ...

    def criar_se_ausente(
        self, documento_id: str, fabricar_estado: Callable[[], EstadoEsteiraDocumento],
    ) -> Tuple[EstadoEsteiraDocumento, bool]: ...

    def listar_todos(self) -> List[EstadoEsteiraDocumento]: ...

    def listar_por_lote(self, lote_id: str) -> List[EstadoEsteiraDocumento]: ...

    def listar_por_etapa(self, etapa: EtapaEsteira) -> List[EstadoEsteiraDocumento]: ...

    def listar_por_situacao(self, situacao: SituacaoEsteira) -> List[EstadoEsteiraDocumento]: ...


class RepositorioLotesEmMemoria:
    """Implementacao em memoria, para testes e para esta fase de
    fundacao. Protegida por threading.Lock -- salvar/listar concorrentes
    de multiplas threads (ex.: criacao de varios lotes em paralelo) sao
    seguros."""

    def __init__(self) -> None:
        self._por_id: dict[str, LoteDocumental] = {}
        self._lock = threading.Lock()

    def buscar_por_id(self, lote_id: str) -> Optional[LoteDocumental]:
        with self._lock:
            return self._por_id.get(lote_id)

    def salvar(self, lote: LoteDocumental) -> None:
        with self._lock:
            self._por_id[lote.lote_id] = lote

    def listar_recentes(self, limite: int = 50) -> List[LoteDocumental]:
        """Mais recente primeiro. Se dois lotes tiverem exatamente o
        mesmo `criado_em` (relogio com resolucao baixa, ou lotes criados
        na mesma chamada de relogio congelado em teste), o desempate e
        pela ordem de insercao (o inserido por ultimo aparece primeiro)
        -- por isso a lista e revertida ANTES do sort estavel, nao
        depois."""
        with self._lock:
            inseridos_mais_recentes_primeiro = list(reversed(list(self._por_id.values())))
        lotes = sorted(inseridos_mais_recentes_primeiro, key=lambda l: l.criado_em, reverse=True)
        return lotes[:limite]

    def listar_todos(self) -> List[LoteDocumental]:
        with self._lock:
            return list(self._por_id.values())


class RepositorioEstadosEsteiraEmMemoria:
    """Implementacao em memoria do estado da esteira. `criar_se_ausente`
    espelha RepositorioDocumentosEmMemoria.salvar_se_ausente_por_hash
    (repositorio.py, Fase 1): sob o mesmo lock, confere se ja existe
    estado para o documento_id e, se nao existir, fabrica e salva --
    numa unica secao critica. E o que torna seguro decidir, sob
    concorrencia, se uma entrada de lote e a PRIMEIRA vez que esse
    documento entra na esteira (cria estado ENTRADA) ou uma duplicidade
    (reaproveita o estado ja existente, de qualquer lote anterior)."""

    def __init__(self) -> None:
        self._por_documento: dict[str, EstadoEsteiraDocumento] = {}
        self._lock = threading.Lock()

    def buscar_por_documento_id(self, documento_id: str) -> Optional[EstadoEsteiraDocumento]:
        with self._lock:
            return self._por_documento.get(documento_id)

    def salvar(self, estado: EstadoEsteiraDocumento) -> None:
        with self._lock:
            self._por_documento[estado.documento_id] = estado

    def criar_se_ausente(
        self, documento_id: str, fabricar_estado: Callable[[], EstadoEsteiraDocumento],
    ) -> Tuple[EstadoEsteiraDocumento, bool]:
        with self._lock:
            existente = self._por_documento.get(documento_id)
            if existente is not None:
                return existente, False
            novo_estado = fabricar_estado()
            self._por_documento[documento_id] = novo_estado
            return novo_estado, True

    def listar_todos(self) -> List[EstadoEsteiraDocumento]:
        with self._lock:
            return list(self._por_documento.values())

    def listar_por_lote(self, lote_id: str) -> List[EstadoEsteiraDocumento]:
        with self._lock:
            return [e for e in self._por_documento.values() if e.lote_id == lote_id]

    def listar_por_etapa(self, etapa: EtapaEsteira) -> List[EstadoEsteiraDocumento]:
        with self._lock:
            return [e for e in self._por_documento.values() if e.etapa_atual == etapa]

    def listar_por_situacao(self, situacao: SituacaoEsteira) -> List[EstadoEsteiraDocumento]:
        with self._lock:
            return [e for e in self._por_documento.values() if e.situacao == situacao]
