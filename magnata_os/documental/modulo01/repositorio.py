"""
Repositorios do Modulo 01 -- interfaces + implementacao em memoria.

Nao ha adapter de Airtable/Postgres nesta fase (fundacao apenas). A
implementacao concreta de armazenamento fica para fase futura -- ver
MAGNATA_OS_DOCUMENTAL_MODULO01.md. As classes em memoria aqui nunca
acessam rede nem disco.
"""
from __future__ import annotations

from typing import List, Optional, Protocol

from .dominio import Documento, EventoHistorico


class RepositorioDocumentos(Protocol):
    """Contrato que qualquer adapter de persistencia de Documento precisa
    cumprir (Airtable, Postgres, etc., em fase futura)."""

    def buscar_por_hash(self, hash_sha256: str) -> Optional[Documento]: ...

    def buscar_por_id(self, documento_id: str) -> Optional[Documento]: ...

    def salvar(self, documento: Documento) -> None: ...


class RepositorioHistorico(Protocol):
    """Contrato do repositorio de eventos -- append-only."""

    def registrar(self, evento: EventoHistorico) -> None: ...

    def listar_por_documento(self, documento_id: str) -> List[EventoHistorico]: ...


class RepositorioDocumentosEmMemoria:
    """Implementacao em memoria, para testes e para esta fase de
    fundacao. Nao persiste entre execucoes, nao acessa nada externo."""

    def __init__(self) -> None:
        self._por_id: dict[str, Documento] = {}
        self._id_por_hash: dict[str, str] = {}

    def buscar_por_hash(self, hash_sha256: str) -> Optional[Documento]:
        documento_id = self._id_por_hash.get(hash_sha256)
        return self._por_id.get(documento_id) if documento_id else None

    def buscar_por_id(self, documento_id: str) -> Optional[Documento]:
        return self._por_id.get(documento_id)

    def salvar(self, documento: Documento) -> None:
        self._por_id[documento.documento_id] = documento
        self._id_por_hash[documento.hash_sha256] = documento.documento_id


class RepositorioHistoricoEmMemoria:
    """Implementacao em memoria do historico -- append-only, nunca edita
    nem remove eventos ja registrados."""

    def __init__(self) -> None:
        self._eventos: List[EventoHistorico] = []

    def registrar(self, evento: EventoHistorico) -> None:
        self._eventos.append(evento)

    def listar_por_documento(self, documento_id: str) -> List[EventoHistorico]:
        return [e for e in self._eventos if e.documento_id == documento_id]
