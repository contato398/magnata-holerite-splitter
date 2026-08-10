"""Repositórios da camada de ESCRITA da importação em lote (Fase 4) —
interfaces (Protocol) + implementação em memória.

Mesma disciplina de `modulo01/repositorio.py` e
`modulo01/repositorio_esteira.py`: Protocols primeiro, implementação em
memória com `threading.Lock` para uso seguro em teste de concorrência.
Nenhum destes repositórios acessa rede nem disco.
"""

from __future__ import annotations

import threading
from typing import Callable, List, Optional, Protocol, Tuple

from .contratos_execucao import EventoItemExecucao, ItemExecucao, SituacaoItemExecucao, VersionamentoLogico


class RepositorioItensExecucao(Protocol):
    """Contrato de persistência de `ItemExecucao`. Um adapter real garante
    que `criar_se_ausente` seja atômica via
    UNIQUE(lote_id, manifesto_item_id) (migration 0009), não só logicamente
    correta em memória com lock de processo."""

    def buscar_por_lote_e_manifesto(
        self, lote_id: str, manifesto_item_id: str,
    ) -> Optional[ItemExecucao]: ...

    def criar_se_ausente(
        self, lote_id: str, manifesto_item_id: str,
        fabricar_item: Callable[[], ItemExecucao],
    ) -> Tuple[ItemExecucao, bool]: ...

    def salvar(self, item: ItemExecucao) -> None: ...

    def listar_por_lote(self, lote_id: str) -> List[ItemExecucao]: ...

    def listar_por_situacao(self, situacao: SituacaoItemExecucao) -> List[ItemExecucao]: ...

    def listar_por_documento_id(self, documento_id: str) -> List[ItemExecucao]: ...


class RepositorioEventosItemExecucao(Protocol):
    """Contrato da trilha append-only de eventos do ITEM de execução —
    cobre inclusive a fase ANTES de `documento_id` existir (correção de
    auditoria: `RepositorioHistorico`/`eventos_documentais` exige
    documento_id NOT NULL e não consegue representar essa fase). Nunca
    editado nem apagado."""

    def registrar(self, evento: EventoItemExecucao) -> None: ...

    def listar_por_item(self, item_importacao_id: str) -> List[EventoItemExecucao]: ...

    def listar_por_lote(self, lote_id: str) -> List[EventoItemExecucao]: ...

    def listar_todos(self) -> List[EventoItemExecucao]: ...


class RepositorioVersionamentoLogico(Protocol):
    """Contrato de persistência de `VersionamentoLogico` — companheira
    1:1 de `Documento` (ver migration 0009)."""

    def buscar_por_documento_id(self, documento_id: str) -> Optional[VersionamentoLogico]: ...

    def listar_por_documento_logico_id(self, documento_logico_id: str) -> List[VersionamentoLogico]: ...

    def salvar_se_ausente(self, versionamento: VersionamentoLogico) -> Tuple[VersionamentoLogico, bool]: ...


class RepositorioItensExecucaoEmMemoria:
    """Implementação em memória. Protegida por um único `threading.Lock`
    — leitura e escrita passam por ele, para que `criar_se_ausente` seja
    de fato atômica sob chamadas concorrentes (mesma disciplina de
    `RepositorioDocumentosEmMemoria.salvar_se_ausente_por_hash`,
    modulo01/repositorio.py)."""

    def __init__(self) -> None:
        self._por_id: dict[str, ItemExecucao] = {}
        self._id_por_lote_manifesto: dict[tuple[str, str], str] = {}
        self._lock = threading.Lock()

    def buscar_por_lote_e_manifesto(
        self, lote_id: str, manifesto_item_id: str,
    ) -> Optional[ItemExecucao]:
        with self._lock:
            item_id = self._id_por_lote_manifesto.get((lote_id, manifesto_item_id))
            return self._por_id.get(item_id) if item_id else None

    def criar_se_ausente(
        self, lote_id: str, manifesto_item_id: str,
        fabricar_item: Callable[[], ItemExecucao],
    ) -> Tuple[ItemExecucao, bool]:
        with self._lock:
            chave = (lote_id, manifesto_item_id)
            item_id_existente = self._id_por_lote_manifesto.get(chave)
            if item_id_existente is not None:
                return self._por_id[item_id_existente], False

            novo_item = fabricar_item()
            self._por_id[novo_item.item_importacao_id] = novo_item
            self._id_por_lote_manifesto[chave] = novo_item.item_importacao_id
            return novo_item, True

    def salvar(self, item: ItemExecucao) -> None:
        with self._lock:
            self._por_id[item.item_importacao_id] = item
            self._id_por_lote_manifesto[(item.lote_id, item.manifesto_item_id)] = item.item_importacao_id

    def listar_por_lote(self, lote_id: str) -> List[ItemExecucao]:
        with self._lock:
            return [i for i in self._por_id.values() if i.lote_id == lote_id]

    def listar_por_situacao(self, situacao: SituacaoItemExecucao) -> List[ItemExecucao]:
        with self._lock:
            return [i for i in self._por_id.values() if i.situacao == situacao]

    def listar_por_documento_id(self, documento_id: str) -> List[ItemExecucao]:
        with self._lock:
            return [i for i in self._por_id.values() if i.documento_id == documento_id]


class RepositorioEventosItemExecucaoEmMemoria:
    """Implementação em memória — append-only, nunca edita nem remove
    evento já registrado. Lock próprio, independente dos demais
    repositórios (mesma disciplina de `RepositorioHistoricoEmMemoria`,
    modulo01/repositorio.py)."""

    def __init__(self) -> None:
        self._eventos: List[EventoItemExecucao] = []
        self._lock = threading.Lock()

    def registrar(self, evento: EventoItemExecucao) -> None:
        with self._lock:
            self._eventos.append(evento)

    def listar_por_item(self, item_importacao_id: str) -> List[EventoItemExecucao]:
        with self._lock:
            eventos = [e for e in self._eventos if e.item_importacao_id == item_importacao_id]
        return sorted(eventos, key=lambda e: e.timestamp)

    def listar_por_lote(self, lote_id: str) -> List[EventoItemExecucao]:
        with self._lock:
            eventos = [e for e in self._eventos if e.lote_id == lote_id]
        return sorted(eventos, key=lambda e: e.timestamp)

    def listar_todos(self) -> List[EventoItemExecucao]:
        with self._lock:
            return list(self._eventos)


class RepositorioVersionamentoLogicoEmMemoria:
    """Implementação em memória. `salvar_se_ausente` espelha
    `RepositorioDocumentosEmMemoria.salvar_se_ausente_por_hash`: sob o
    mesmo lock, confere se já existe versionamento para este
    `documento_id` e, se não existir, salva — numa única seção crítica."""

    def __init__(self) -> None:
        self._por_documento_id: dict[str, VersionamentoLogico] = {}
        self._lock = threading.Lock()

    def buscar_por_documento_id(self, documento_id: str) -> Optional[VersionamentoLogico]:
        with self._lock:
            return self._por_documento_id.get(documento_id)

    def listar_por_documento_logico_id(self, documento_logico_id: str) -> List[VersionamentoLogico]:
        with self._lock:
            return [
                v for v in self._por_documento_id.values()
                if v.documento_logico_id == documento_logico_id
            ]

    def salvar_se_ausente(
        self, versionamento: VersionamentoLogico,
    ) -> Tuple[VersionamentoLogico, bool]:
        with self._lock:
            existente = self._por_documento_id.get(versionamento.documento_id)
            if existente is not None:
                return existente, False
            self._por_documento_id[versionamento.documento_id] = versionamento
            return versionamento, True
