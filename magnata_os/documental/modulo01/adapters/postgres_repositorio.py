"""
Adapters PostgreSQL para Documento e EventoHistorico (Modulo 01, Fase 2).

Escritos contra a interface padronizada da DB-API 2.0 (PEP 249) --
`.cursor()`, `.execute()`, `.fetchone()`, `.fetchall()`, `.commit()`,
`.rollback()` -- nunca importam psycopg2/psycopg diretamente. Qualquer
objeto de conexao compativel serve (psycopg2, psycopg v3, ou um duplo de
teste). Ver MAGNATA_OS_DOCUMENTAL_MODULO01_FASE2.md.

As tabelas esperadas sao criadas pelas migrations em
magnata_os/documental/modulo01/migrations/ -- nenhuma delas e aplicada
por este modulo.
"""
from __future__ import annotations

import json
from typing import Callable, List, Optional, Tuple

from ..dominio import Documento, EventoHistorico, StatusDocumento

_COLUNAS_DOCUMENTOS = (
    'documento_id', 'arquivo_original', 'nome_original', 'mime_type', 'tamanho',
    'hash_sha256', 'origem', 'recebido_em', 'lote_id', 'status',
    'correlation_id', 'criado_em', 'atualizado_em',
)

_COLUNAS_EVENTOS = (
    'documento_id', 'evento', 'status_anterior', 'status_novo',
    '"timestamp"', 'correlation_id', 'detalhes',
)


def _e_violacao_de_integridade(exc: Exception) -> bool:
    """
    Deteccao duck-typed de violacao de constraint (ex.: UNIQUE, FK), sem
    importar nenhum driver especifico. A PEP 249 (DB-API 2.0) padroniza
    o NOME da classe IntegrityError entre drivers compativeis (psycopg2,
    psycopg v3, sqlite3, etc.) -- confere pelo nome na cadeia de
    classes-base, nao por isinstance contra um modulo especifico.
    """
    return any(base.__name__ == 'IntegrityError' for base in type(exc).__mro__)


def _documento_para_linha(documento: Documento) -> tuple:
    return (
        documento.documento_id, documento.arquivo_original, documento.nome_original,
        documento.mime_type, documento.tamanho, documento.hash_sha256, documento.origem,
        documento.recebido_em, documento.lote_id, documento.status.value,
        documento.correlation_id, documento.criado_em, documento.atualizado_em,
    )


def _linha_para_documento(linha: tuple) -> Documento:
    (
        documento_id, arquivo_original, nome_original, mime_type, tamanho,
        hash_sha256, origem, recebido_em, lote_id, status,
        correlation_id, criado_em, atualizado_em,
    ) = linha
    return Documento(
        documento_id=documento_id,
        arquivo_original=arquivo_original,
        nome_original=nome_original,
        mime_type=mime_type,
        tamanho=tamanho,
        hash_sha256=hash_sha256,
        origem=origem,
        recebido_em=recebido_em,
        lote_id=lote_id,
        status=StatusDocumento(status),
        correlation_id=correlation_id,
        criado_em=criado_em,
        atualizado_em=atualizado_em,
    )


def _linha_para_evento(linha: tuple) -> EventoHistorico:
    documento_id, evento, status_anterior, status_novo, timestamp, correlation_id, detalhes = linha
    detalhes_dict = json.loads(detalhes) if isinstance(detalhes, str) else (detalhes or {})
    return EventoHistorico(
        documento_id=documento_id,
        evento=evento,
        status_anterior=StatusDocumento(status_anterior) if status_anterior else None,
        status_novo=StatusDocumento(status_novo) if status_novo else None,
        timestamp=timestamp,
        correlation_id=correlation_id,
        detalhes=detalhes_dict,
    )


class RepositorioDocumentosPostgres:
    """Adapter PostgreSQL para RepositorioDocumentos (ver repositorio.py,
    Fase 1). Atomicidade de salvar_se_ausente_por_hash vem da constraint
    UNIQUE(hash_sha256) do banco (migration 0001), nao de lock de
    aplicacao -- funciona corretamente entre processos distintos, ao
    contrario do RepositorioDocumentosEmMemoria."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def buscar_por_hash(self, hash_sha256: str) -> Optional[Documento]:
        colunas = ', '.join(_COLUNAS_DOCUMENTOS)
        with self._conexao.cursor() as cur:
            cur.execute(f'SELECT {colunas} FROM documentos WHERE hash_sha256 = %s', (hash_sha256,))
            linha = cur.fetchone()
        return _linha_para_documento(linha) if linha else None

    def buscar_por_id(self, documento_id: str) -> Optional[Documento]:
        colunas = ', '.join(_COLUNAS_DOCUMENTOS)
        with self._conexao.cursor() as cur:
            cur.execute(f'SELECT {colunas} FROM documentos WHERE documento_id = %s', (documento_id,))
            linha = cur.fetchone()
        return _linha_para_documento(linha) if linha else None

    def salvar(self, documento: Documento) -> None:
        colunas = ', '.join(_COLUNAS_DOCUMENTOS)
        marcadores = ', '.join(['%s'] * len(_COLUNAS_DOCUMENTOS))
        atualizacoes = ', '.join(f'{c} = EXCLUDED.{c}' for c in _COLUNAS_DOCUMENTOS if c != 'documento_id')
        with self._conexao.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO documentos ({colunas}) VALUES ({marcadores})
                ON CONFLICT (documento_id) DO UPDATE SET {atualizacoes}
                """,
                _documento_para_linha(documento),
            )
        self._conexao.commit()

    def salvar_se_ausente_por_hash(
        self, hash_sha256: str, fabricar_documento: Callable[[], Documento],
    ) -> Tuple[Documento, bool]:
        """
        Atomica via UNIQUE(hash_sha256) do banco: tenta inserir; se a
        constraint rejeitar (outro processo inseriu esse hash entre a
        fabricacao e o commit), busca e retorna o existente. Ao
        contrario do adapter em memoria, fabricar_documento() e sempre
        chamada (o custo de gerar um documento_id/timestamp a mais em
        caso de corrida e aceitavel e barato) -- a garantia de
        unicidade nao depende disso, depende da constraint do banco.
        """
        documento = fabricar_documento()
        colunas = ', '.join(_COLUNAS_DOCUMENTOS)
        marcadores = ', '.join(['%s'] * len(_COLUNAS_DOCUMENTOS))
        try:
            with self._conexao.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO documentos ({colunas}) VALUES ({marcadores})
                    ON CONFLICT (hash_sha256) DO NOTHING
                    RETURNING documento_id
                    """,
                    _documento_para_linha(documento),
                )
                inserido = cur.fetchone() is not None
            self._conexao.commit()
        except Exception as exc:
            self._conexao.rollback()
            if not _e_violacao_de_integridade(exc):
                raise
            inserido = False

        if inserido:
            return documento, True

        existente = self.buscar_por_hash(hash_sha256)
        if existente is None:
            raise RuntimeError(
                f'hash_sha256={hash_sha256} nao encontrado apos INSERT nao efetivado -- '
                f'estado inesperado do banco.'
            )
        return existente, False

    def remover(self, documento_id: str) -> None:
        with self._conexao.cursor() as cur:
            cur.execute('DELETE FROM documentos WHERE documento_id = %s', (documento_id,))
        self._conexao.commit()

    def listar_todos(self) -> List[Documento]:
        colunas = ', '.join(_COLUNAS_DOCUMENTOS)
        with self._conexao.cursor() as cur:
            cur.execute(f'SELECT {colunas} FROM documentos ORDER BY criado_em ASC')
            linhas = cur.fetchall()
        return [_linha_para_documento(l) for l in linhas]


class RepositorioHistoricoPostgres:
    """Adapter PostgreSQL para RepositorioHistorico (ver repositorio.py,
    Fase 1). documento_id tem FK obrigatoria para documentos -- um
    evento para um documento_id inexistente e rejeitado pelo proprio
    banco (IntegrityError). A tabela e append-only por trigger (migration
    0003) -- este adapter nunca tenta UPDATE nem DELETE em eventos."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def registrar(self, evento: EventoHistorico) -> None:
        colunas = ', '.join(_COLUNAS_EVENTOS)
        marcadores = ', '.join(['%s'] * len(_COLUNAS_EVENTOS))
        with self._conexao.cursor() as cur:
            cur.execute(
                f'INSERT INTO eventos_documentais ({colunas}) VALUES ({marcadores})',
                (
                    evento.documento_id,
                    evento.evento,
                    evento.status_anterior.value if evento.status_anterior else None,
                    evento.status_novo.value if evento.status_novo else None,
                    evento.timestamp,
                    evento.correlation_id,
                    json.dumps(dict(evento.detalhes)),
                ),
            )
        self._conexao.commit()

    def listar_por_documento(self, documento_id: str) -> List[EventoHistorico]:
        colunas = ', '.join(_COLUNAS_EVENTOS)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM eventos_documentais '
                f'WHERE documento_id = %s ORDER BY "timestamp" ASC, evento_id ASC',
                (documento_id,),
            )
            linhas = cur.fetchall()
        return [_linha_para_evento(l) for l in linhas]

    def listar_todos(self) -> List[EventoHistorico]:
        colunas = ', '.join(_COLUNAS_EVENTOS)
        with self._conexao.cursor() as cur:
            cur.execute(f'SELECT {colunas} FROM eventos_documentais ORDER BY "timestamp" ASC, evento_id ASC')
            linhas = cur.fetchall()
        return [_linha_para_evento(l) for l in linhas]
