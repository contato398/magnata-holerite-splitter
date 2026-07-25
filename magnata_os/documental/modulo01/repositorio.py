"""
Repositorios do Modulo 01 -- interfaces + implementacao em memoria.

Nao ha adapter de Airtable/Postgres nesta fase (fundacao apenas). A
implementacao concreta de armazenamento fica para fase futura -- ver
MAGNATA_OS_DOCUMENTAL_MODULO01.md. As classes em memoria aqui nunca
acessam rede nem disco.
"""
from __future__ import annotations

import threading
from typing import Callable, List, Optional, Protocol, Tuple

from .dominio import Documento, EventoHistorico


class RepositorioDocumentos(Protocol):
    """Contrato que qualquer adapter de persistencia de Documento precisa
    cumprir (Airtable, Postgres, etc., em fase futura). Um adapter real
    precisa garantir que salvar_se_ausente_por_hash seja atomica (ex.:
    constraint de unicidade no hash + tratamento de violacao), nao so
    logicamente correta em memoria com um lock de processo."""

    def buscar_por_hash(self, hash_sha256: str) -> Optional[Documento]: ...

    def buscar_por_id(self, documento_id: str) -> Optional[Documento]: ...

    def salvar(self, documento: Documento) -> None: ...

    def salvar_se_ausente_por_hash(
        self, hash_sha256: str, fabricar_documento: Callable[[], Documento],
    ) -> Tuple[Documento, bool]: ...

    def remover(self, documento_id: str) -> None: ...

    def listar_todos(self) -> List[Documento]: ...


class RepositorioHistorico(Protocol):
    """Contrato do repositorio de eventos -- append-only."""

    def registrar(self, evento: EventoHistorico) -> None: ...

    def listar_por_documento(self, documento_id: str) -> List[EventoHistorico]: ...

    def listar_todos(self) -> List[EventoHistorico]: ...


class RepositorioDocumentosEmMemoria:
    """Implementacao em memoria, para testes e para esta fase de
    fundacao. Nao persiste entre execucoes, nao acessa nada externo.
    Protegida por um unico threading.Lock -- todas as operacoes de
    leitura e escrita passam por ele, para que salvar_se_ausente_por_hash
    seja de fato atomica sob chamadas concorrentes."""

    def __init__(self) -> None:
        self._por_id: dict[str, Documento] = {}
        self._id_por_hash: dict[str, str] = {}
        self._lock = threading.Lock()

    def buscar_por_hash(self, hash_sha256: str) -> Optional[Documento]:
        with self._lock:
            documento_id = self._id_por_hash.get(hash_sha256)
            return self._por_id.get(documento_id) if documento_id else None

    def buscar_por_id(self, documento_id: str) -> Optional[Documento]:
        with self._lock:
            return self._por_id.get(documento_id)

    def salvar(self, documento: Documento) -> None:
        with self._lock:
            self._por_id[documento.documento_id] = documento
            self._id_por_hash[documento.hash_sha256] = documento.documento_id

    def salvar_se_ausente_por_hash(
        self, hash_sha256: str, fabricar_documento: Callable[[], Documento],
    ) -> Tuple[Documento, bool]:
        """
        Atomica: sob o mesmo lock, confere se ja existe Documento para
        este hash e, se nao existir, fabrica (chama fabricar_documento())
        e salva -- tudo numa unica secao critica. Sob chamadas
        concorrentes para o mesmo hash, exatamente uma cria um Documento
        novo; todas as outras recebem esse mesmo Documento de volta, sem
        nunca invocar fabricar_documento(). Retorna (documento, criado).
        """
        with self._lock:
            documento_id_existente = self._id_por_hash.get(hash_sha256)
            if documento_id_existente is not None:
                return self._por_id[documento_id_existente], False

            novo_documento = fabricar_documento()
            self._por_id[novo_documento.documento_id] = novo_documento
            self._id_por_hash[hash_sha256] = novo_documento.documento_id
            return novo_documento, True

    def remover(self, documento_id: str) -> None:
        """Rollback explicito: remove um Documento (e seu indice de
        hash, se ainda apontar para ele) sob o mesmo lock. Usado pelo
        servico quando o registro do historico falha logo apos a
        criacao -- nunca deixa o Documento orfao (sem historico) visivel
        no repositorio."""
        with self._lock:
            documento = self._por_id.pop(documento_id, None)
            if documento is not None and self._id_por_hash.get(documento.hash_sha256) == documento_id:
                del self._id_por_hash[documento.hash_sha256]

    def listar_todos(self) -> List[Documento]:
        with self._lock:
            return list(self._por_id.values())


class RepositorioHistoricoEmMemoria:
    """Implementacao em memoria do historico -- append-only, nunca edita
    nem remove eventos ja registrados. Lock proprio, independente do
    lock do repositorio de documentos -- append concorrente de eventos
    de threads distintas (ex.: tentativas duplicadas simultaneas) precisa
    ser seguro sem depender de detalhe de implementacao do interpretador."""

    def __init__(self) -> None:
        self._eventos: List[EventoHistorico] = []
        self._lock = threading.Lock()

    def registrar(self, evento: EventoHistorico) -> None:
        with self._lock:
            self._eventos.append(evento)

    def listar_por_documento(self, documento_id: str) -> List[EventoHistorico]:
        with self._lock:
            return [e for e in self._eventos if e.documento_id == documento_id]

    def listar_todos(self) -> List[EventoHistorico]:
        with self._lock:
            return list(self._eventos)
