"""Adapters PostgreSQL para ItemExecucao e VersionamentoLogico (Fase 4 —
escrita real da importação em lote).

Mesmo padrão de `modulo01/adapters/postgres_repositorio.py`: escrito
contra a interface padronizada da DB-API 2.0 (PEP 249) — nunca importa
`psycopg2`/`psycopg` diretamente. Duck-typing de `IntegrityError` pelo
nome da classe, idêntico ao adapter de referência.

As tabelas esperadas são criadas pela migration 0009 — nenhuma delas é
aplicada por este módulo.
"""

from __future__ import annotations

import json
from typing import Callable, List, Optional, Tuple

from ..contratos import TipoDocumental
from ..contratos_execucao import EventoItemExecucao, ItemExecucao, SituacaoItemExecucao, VersionamentoLogico

_COLUNAS_ITEM = (
    'item_importacao_id', 'lote_id', 'manifesto_item_id', 'tipo_documental',
    'documento_id', 'identidade_ingestao', 'situacao', 'tentativas',
    'external_record_id', 'external_criado_por_esta_execucao',
    'attachment_confirmado', 'ultimo_erro_sanitizado', 'criado_em', 'atualizado_em',
)

_COLUNAS_EVENTO_ITEM = (
    'item_importacao_id', 'lote_id', 'documento_id', 'situacao', 'tentativas',
    'erro_sanitizado', '"timestamp"', 'detalhes',
)

_COLUNAS_VERSIONAMENTO = (
    'documento_id', 'documento_logico_id', 'versao_documento',
    'substitui_documento_id', 'criado_em',
)


def _e_violacao_de_integridade(exc: Exception) -> bool:
    """Deteccao duck-typed de violação de constraint (UNIQUE, FK, CHECK) —
    ver docstring equivalente em postgres_repositorio.py. Este adapter usa
    placeholders `%s` (estilo pyformat, específico de psycopg)."""
    return any(base.__name__ == 'IntegrityError' for base in type(exc).__mro__)


def _item_para_linha(item: ItemExecucao) -> tuple:
    return (
        item.item_importacao_id, item.lote_id, item.manifesto_item_id,
        item.tipo_documental.value, item.documento_id, item.identidade_ingestao,
        item.situacao.value, item.tentativas, item.external_record_id,
        item.external_criado_por_esta_execucao, item.attachment_confirmado,
        item.ultimo_erro_sanitizado, item.criado_em, item.atualizado_em,
    )


def _linha_para_item(linha: tuple) -> ItemExecucao:
    (
        item_importacao_id, lote_id, manifesto_item_id, tipo_documental,
        documento_id, identidade_ingestao, situacao, tentativas,
        external_record_id, external_criado_por_esta_execucao,
        attachment_confirmado, ultimo_erro_sanitizado, criado_em, atualizado_em,
    ) = linha
    return ItemExecucao(
        item_importacao_id=item_importacao_id,
        lote_id=lote_id,
        manifesto_item_id=manifesto_item_id,
        tipo_documental=TipoDocumental(tipo_documental),
        documento_id=documento_id,
        identidade_ingestao=identidade_ingestao,
        situacao=SituacaoItemExecucao(situacao),
        tentativas=tentativas,
        external_record_id=external_record_id,
        external_criado_por_esta_execucao=external_criado_por_esta_execucao,
        attachment_confirmado=attachment_confirmado,
        ultimo_erro_sanitizado=ultimo_erro_sanitizado,
        criado_em=criado_em,
        atualizado_em=atualizado_em,
    )


def _versionamento_para_linha(v: VersionamentoLogico) -> tuple:
    return (
        v.documento_id, v.documento_logico_id, v.versao_documento,
        v.substitui_documento_id, v.criado_em,
    )


def _linha_para_versionamento(linha: tuple) -> VersionamentoLogico:
    documento_id, documento_logico_id, versao_documento, substitui_documento_id, criado_em = linha
    return VersionamentoLogico(
        documento_id=documento_id,
        documento_logico_id=documento_logico_id,
        versao_documento=versao_documento,
        substitui_documento_id=substitui_documento_id,
        criado_em=criado_em,
    )


def _evento_item_para_linha(e: EventoItemExecucao) -> tuple:
    return (
        e.item_importacao_id, e.lote_id, e.documento_id, e.situacao.value, e.tentativas,
        e.erro_sanitizado, e.timestamp, json.dumps(dict(e.detalhes)),
    )


def _linha_para_evento_item(linha: tuple) -> EventoItemExecucao:
    item_importacao_id, lote_id, documento_id, situacao, tentativas, erro_sanitizado, timestamp, detalhes = linha
    detalhes_dict = json.loads(detalhes) if isinstance(detalhes, str) else (detalhes or {})
    return EventoItemExecucao(
        item_importacao_id=item_importacao_id,
        lote_id=lote_id,
        documento_id=documento_id,
        situacao=SituacaoItemExecucao(situacao),
        tentativas=tentativas,
        erro_sanitizado=erro_sanitizado,
        timestamp=timestamp,
        detalhes=detalhes_dict,
    )


class RepositorioItensExecucaoPostgres:
    """Adapter PostgreSQL para RepositorioItensExecucao (ver
    repositorio_execucao.py). Atomicidade de `criar_se_ausente` vem da
    constraint UNIQUE(lote_id, manifesto_item_id) do banco (migration
    0009), não de lock de aplicação."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def buscar_por_lote_e_manifesto(
        self, lote_id: str, manifesto_item_id: str,
    ) -> Optional[ItemExecucao]:
        colunas = ', '.join(_COLUNAS_ITEM)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM itens_importacao_lote '
                f'WHERE lote_id = %s AND manifesto_item_id = %s',
                (lote_id, manifesto_item_id),
            )
            linha = cur.fetchone()
        return _linha_para_item(linha) if linha else None

    def criar_se_ausente(
        self, lote_id: str, manifesto_item_id: str,
        fabricar_item: Callable[[], ItemExecucao],
    ) -> Tuple[ItemExecucao, bool]:
        """Sempre chama fabricar_item() (mesmo custo aceito do adapter de
        referência) — a garantia de unicidade depende da constraint do
        banco, não de evitar a fabricação em caso de corrida."""
        item = fabricar_item()
        colunas = ', '.join(_COLUNAS_ITEM)
        marcadores = ', '.join(['%s'] * len(_COLUNAS_ITEM))
        try:
            with self._conexao.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO itens_importacao_lote ({colunas}) VALUES ({marcadores})
                    ON CONFLICT (lote_id, manifesto_item_id) DO NOTHING
                    RETURNING item_importacao_id
                    """,
                    _item_para_linha(item),
                )
                inserido = cur.fetchone() is not None
            self._conexao.commit()
        except Exception as exc:
            self._conexao.rollback()
            if not _e_violacao_de_integridade(exc):
                raise
            inserido = False

        if inserido:
            return item, True

        existente = self.buscar_por_lote_e_manifesto(lote_id, manifesto_item_id)
        if existente is None:
            raise RuntimeError(
                f'item (lote_id={lote_id}, manifesto_item_id={manifesto_item_id}) '
                f'não encontrado após INSERT não efetivado -- estado inesperado do banco.'
            )
        return existente, False

    def salvar(self, item: ItemExecucao) -> None:
        colunas = ', '.join(_COLUNAS_ITEM)
        marcadores = ', '.join(['%s'] * len(_COLUNAS_ITEM))
        atualizacoes = ', '.join(f'{c} = EXCLUDED.{c}' for c in _COLUNAS_ITEM if c != 'item_importacao_id')
        try:
            with self._conexao.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO itens_importacao_lote ({colunas}) VALUES ({marcadores})
                    ON CONFLICT (item_importacao_id) DO UPDATE SET {atualizacoes}
                    """,
                    _item_para_linha(item),
                )
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise

    def listar_por_lote(self, lote_id: str) -> List[ItemExecucao]:
        colunas = ', '.join(_COLUNAS_ITEM)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM itens_importacao_lote WHERE lote_id = %s ORDER BY criado_em ASC',
                (lote_id,),
            )
            linhas = cur.fetchall()
        return [_linha_para_item(l) for l in linhas]

    def listar_por_situacao(self, situacao: SituacaoItemExecucao) -> List[ItemExecucao]:
        colunas = ', '.join(_COLUNAS_ITEM)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM itens_importacao_lote WHERE situacao = %s ORDER BY criado_em ASC',
                (situacao.value,),
            )
            linhas = cur.fetchall()
        return [_linha_para_item(l) for l in linhas]

    def listar_por_documento_id(self, documento_id: str) -> List[ItemExecucao]:
        colunas = ', '.join(_COLUNAS_ITEM)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM itens_importacao_lote WHERE documento_id = %s ORDER BY criado_em ASC',
                (documento_id,),
            )
            linhas = cur.fetchall()
        return [_linha_para_item(l) for l in linhas]


class RepositorioVersionamentoLogicoPostgres:
    """Adapter PostgreSQL para RepositorioVersionamentoLogico. Atomicidade
    de `salvar_se_ausente` vem da PRIMARY KEY(documento_id) do banco
    (migration 0009)."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def buscar_por_documento_id(self, documento_id: str) -> Optional[VersionamentoLogico]:
        colunas = ', '.join(_COLUNAS_VERSIONAMENTO)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM documentos_versionamento_logico WHERE documento_id = %s',
                (documento_id,),
            )
            linha = cur.fetchone()
        return _linha_para_versionamento(linha) if linha else None

    def listar_por_documento_logico_id(self, documento_logico_id: str) -> List[VersionamentoLogico]:
        colunas = ', '.join(_COLUNAS_VERSIONAMENTO)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM documentos_versionamento_logico '
                f'WHERE documento_logico_id = %s ORDER BY versao_documento ASC',
                (documento_logico_id,),
            )
            linhas = cur.fetchall()
        return [_linha_para_versionamento(l) for l in linhas]

    def salvar_se_ausente(
        self, versionamento: VersionamentoLogico,
    ) -> Tuple[VersionamentoLogico, bool]:
        colunas = ', '.join(_COLUNAS_VERSIONAMENTO)
        marcadores = ', '.join(['%s'] * len(_COLUNAS_VERSIONAMENTO))
        try:
            with self._conexao.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO documentos_versionamento_logico ({colunas}) VALUES ({marcadores})
                    ON CONFLICT (documento_id) DO NOTHING
                    RETURNING documento_id
                    """,
                    _versionamento_para_linha(versionamento),
                )
                inserido = cur.fetchone() is not None
            self._conexao.commit()
        except Exception as exc:
            self._conexao.rollback()
            if not _e_violacao_de_integridade(exc):
                raise
            inserido = False

        if inserido:
            return versionamento, True

        existente = self.buscar_por_documento_id(versionamento.documento_id)
        if existente is None:
            raise RuntimeError(
                f'documento_id={versionamento.documento_id} não encontrado em '
                f'documentos_versionamento_logico após INSERT não efetivado.'
            )
        return existente, False


class RepositorioEventosItemExecucaoPostgres:
    """Adapter PostgreSQL para RepositorioEventosItemExecucao —
    `eventos_itens_importacao_lote` (migration 0009, correção de
    auditoria). Append-only por trigger de banco (mesmo padrão de
    `eventos_documentais`/migration 0003) — este adapter nunca tenta
    UPDATE nem DELETE."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def registrar(self, evento: EventoItemExecucao) -> None:
        colunas = ', '.join(_COLUNAS_EVENTO_ITEM)
        marcadores = ', '.join(['%s'] * len(_COLUNAS_EVENTO_ITEM))
        try:
            with self._conexao.cursor() as cur:
                cur.execute(
                    f'INSERT INTO eventos_itens_importacao_lote ({colunas}) VALUES ({marcadores})',
                    _evento_item_para_linha(evento),
                )
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise

    def listar_por_item(self, item_importacao_id: str) -> List[EventoItemExecucao]:
        colunas = ', '.join(_COLUNAS_EVENTO_ITEM)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM eventos_itens_importacao_lote '
                f'WHERE item_importacao_id = %s ORDER BY "timestamp" ASC, evento_id ASC',
                (item_importacao_id,),
            )
            linhas = cur.fetchall()
        return [_linha_para_evento_item(l) for l in linhas]

    def listar_por_lote(self, lote_id: str) -> List[EventoItemExecucao]:
        colunas = ', '.join(_COLUNAS_EVENTO_ITEM)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM eventos_itens_importacao_lote '
                f'WHERE lote_id = %s ORDER BY "timestamp" ASC, evento_id ASC',
                (lote_id,),
            )
            linhas = cur.fetchall()
        return [_linha_para_evento_item(l) for l in linhas]

    def listar_todos(self) -> List[EventoItemExecucao]:
        colunas = ', '.join(_COLUNAS_EVENTO_ITEM)
        with self._conexao.cursor() as cur:
            cur.execute(
                f'SELECT {colunas} FROM eventos_itens_importacao_lote '
                f'ORDER BY "timestamp" ASC, evento_id ASC'
            )
            linhas = cur.fetchall()
        return [_linha_para_evento_item(l) for l in linhas]
