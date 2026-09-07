"""Checkpoint PostgreSQL por ação de ``PlanoDisparo`` autorizado.

O adapter recebe conexão DB-API injetada, não abre rede, não aplica migration e
não conhece transporte. Destinatário, texto, legenda e mídia nunca são
persistidos em claro: somente identidades SHA-256 determinísticas.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple

from .autorizacao_gate import DecisaoGate, RegistroAutorizacaoGate
from .plano_comunicacao import AcaoEnvio, PlanoDisparo
from .politica_comunicacao import hash_conteudo_comunicacao, hash_texto_comunicacao


class EstadoAcaoExecucaoPlano(str, Enum):
    PENDING = 'PENDING'
    EXECUTING = 'EXECUTING'
    SUCCEEDED = 'SUCCEEDED'
    FAILED_RETRYABLE = 'FAILED_RETRYABLE'
    FAILED_FINAL = 'FAILED_FINAL'


class RepositorioAcoesExecucaoPlanoError(ValueError):
    """Plano, autorização ou transição incompatível com o contrato."""


@dataclasses.dataclass(frozen=True)
class RegistroAcaoExecucaoPlano:
    acao_execucao_id: str
    event_id: str
    preview_id: str
    autorizacao_id: str
    ordem: int
    tipo: str
    destinatario_sha256: str
    nome_sha256: Optional[str]
    conteudo_sha256: Optional[str]
    texto_sha256: Optional[str]
    estado: EstadoAcaoExecucaoPlano
    attempt: int
    proxima_tentativa_em: Optional[datetime]
    claim_sha256: Optional[str]
    reivindicado_em: Optional[datetime]
    ultimo_erro_classe: Optional[str]
    resultado_referencia: Optional[str]
    evidencia_sha256: Optional[str]
    criado_em: datetime
    atualizado_em: datetime
    concluido_em: Optional[datetime]


_TABELA = 'magnata_orquestrador.acoes_execucao_plano'
_COLUNAS = (
    'acao_execucao_id', 'event_id', 'preview_id', 'autorizacao_id',
    'ordem', 'tipo', 'destinatario_sha256', 'nome_sha256',
    'conteudo_sha256', 'texto_sha256', 'estado', 'attempt',
    'proxima_tentativa_em', 'claim_sha256', 'reivindicado_em',
    'ultimo_erro_classe', 'resultado_referencia', 'evidencia_sha256',
    'criado_em', 'atualizado_em', 'concluido_em',
)
_COLUNAS_SQL = ', '.join(_COLUNAS)


def _sha256_texto(valor: str) -> str:
    return hashlib.sha256(valor.encode('utf-8')).hexdigest()


def _identidades_acao(acao: AcaoEnvio) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    destinatario = str(acao.destinatario or '').strip()
    if not destinatario:
        raise RepositorioAcoesExecucaoPlanoError('destinatario canonico e obrigatorio')
    destinatario_sha256 = _sha256_texto(destinatario)
    nome_sha256 = _sha256_texto(acao.nome) if acao.nome else None
    if acao.tipo == 'texto':
        texto_sha256 = hash_texto_comunicacao(acao.texto)
        conteudo_sha256 = None
    else:
        try:
            conteudo_sha256 = hash_conteudo_comunicacao(acao.conteudo)
        except (TypeError, ValueError) as exc:
            raise RepositorioAcoesExecucaoPlanoError(
                'acao de midia exige conteudo binario integro'
            ) from exc
        texto_sha256 = hash_texto_comunicacao(acao.legenda) if acao.legenda else None
    return destinatario_sha256, nome_sha256, conteudo_sha256, texto_sha256


def criar_registro_acao_plano(
    *, event_id: str, plano: PlanoDisparo, autorizacao: RegistroAutorizacaoGate,
    acao: AcaoEnvio, criado_em: datetime,
) -> RegistroAcaoExecucaoPlano:
    """Deriva a identidade estável de uma ação sem persistir seu conteúdo."""
    if autorizacao.decisao != DecisaoGate.AUTORIZADO:
        raise RepositorioAcoesExecucaoPlanoError('autorizacao recusada nao materializa acoes')
    if autorizacao.event_id != event_id:
        raise RepositorioAcoesExecucaoPlanoError('autorizacao pertence a outro evento')
    if autorizacao.preview_id != plano.preview_id:
        raise RepositorioAcoesExecucaoPlanoError('preview diverge da autorizacao persistida')
    if criado_em.tzinfo is None:
        raise RepositorioAcoesExecucaoPlanoError('criado_em deve possuir timezone')

    dest, nome, conteudo, texto = _identidades_acao(acao)
    payload = json.dumps({
        'event_id': event_id,
        'preview_id': plano.preview_id,
        'autorizacao_id': autorizacao.autorizacao_id,
        'ordem': acao.ordem,
        'tipo': acao.tipo,
        'destinatario_sha256': dest,
        'nome_sha256': nome,
        'conteudo_sha256': conteudo,
        'texto_sha256': texto,
    }, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    acao_id = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    return RegistroAcaoExecucaoPlano(
        acao_execucao_id=acao_id, event_id=event_id,
        preview_id=plano.preview_id, autorizacao_id=autorizacao.autorizacao_id,
        ordem=acao.ordem, tipo=acao.tipo, destinatario_sha256=dest,
        nome_sha256=nome, conteudo_sha256=conteudo, texto_sha256=texto,
        estado=EstadoAcaoExecucaoPlano.PENDING, attempt=0,
        proxima_tentativa_em=None, claim_sha256=None, reivindicado_em=None,
        ultimo_erro_classe=None, resultado_referencia=None,
        evidencia_sha256=None, criado_em=criado_em, atualizado_em=criado_em,
        concluido_em=None,
    )


def _linha_para_registro(linha) -> RegistroAcaoExecucaoPlano:
    dados = dict(zip(_COLUNAS, linha))
    dados['estado'] = EstadoAcaoExecucaoPlano(dados['estado'])
    return RegistroAcaoExecucaoPlano(**dados)


def _linha_registro(registro: RegistroAcaoExecucaoPlano) -> tuple:
    valores = dataclasses.astuple(registro)
    return valores[:10] + (registro.estado.value,) + valores[11:]


class RepositorioAcoesExecucaoPlanoPostgres:
    """Materialização idempotente e checkpoints CAS, sem executar ações."""

    def __init__(self, conexao) -> None:
        self._conexao = conexao

    def materializar_plano(
        self, *, event_id: str, plano: PlanoDisparo,
        autorizacao: RegistroAutorizacaoGate, criado_em: datetime,
    ) -> Tuple[RegistroAcaoExecucaoPlano, ...]:
        registros = tuple(criar_registro_acao_plano(
            event_id=event_id, plano=plano, autorizacao=autorizacao,
            acao=acao, criado_em=criado_em,
        ) for acao in plano.acoes)
        persistidos = []
        try:
            with self._conexao.cursor() as cursor:
                for registro in registros:
                    marcadores = ', '.join(['%s'] * len(_COLUNAS))
                    cursor.execute(
                        f'INSERT INTO {_TABELA} ({_COLUNAS_SQL}) '
                        f'SELECT {marcadores} '
                        'FROM magnata_orquestrador.autorizacoes_gate ag '
                        'WHERE ag.autorizacao_id = %s AND ag.event_id = %s '
                        'AND ag.preview_id = %s AND ag.decisao = %s '
                        'ON CONFLICT (acao_execucao_id) DO NOTHING '
                        'RETURNING acao_execucao_id',
                        _linha_registro(registro) + (
                            autorizacao.autorizacao_id, event_id,
                            plano.preview_id, DecisaoGate.AUTORIZADO.value,
                        ),
                    )
                    inserida = cursor.fetchone()
                    if inserida is None:
                        cursor.execute(
                            f'SELECT {_COLUNAS_SQL} FROM {_TABELA} '
                            'WHERE acao_execucao_id = %s',
                            (registro.acao_execucao_id,),
                        )
                        existente = cursor.fetchone()
                        if existente is None:
                            raise RepositorioAcoesExecucaoPlanoError(
                                'autorizacao AUTORIZADO exata nao encontrada'
                            )
                        existente_registro = _linha_para_registro(existente)
                        if _linha_registro(existente_registro)[:10] != _linha_registro(registro)[:10]:
                            raise RepositorioAcoesExecucaoPlanoError(
                                'colisao de identidade com acao persistida divergente'
                            )
                        persistidos.append(existente_registro)
                    else:
                        persistidos.append(registro)
            self._conexao.commit()
            return tuple(persistidos)
        except Exception:
            self._conexao.rollback()
            raise

    def buscar(self, acao_execucao_id: str) -> Optional[RegistroAcaoExecucaoPlano]:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'SELECT {_COLUNAS_SQL} FROM {_TABELA} WHERE acao_execucao_id = %s',
                (acao_execucao_id,),
            )
            linha = cursor.fetchone()
        return _linha_para_registro(linha) if linha else None

    def reivindicar_proxima(
        self, *, event_id: str, preview_id: str,
        claim_referencia: str, reivindicado_em: datetime,
    ) -> Optional[RegistroAcaoExecucaoPlano]:
        claim_limpo = str(claim_referencia or '').strip()
        if not claim_limpo:
            raise RepositorioAcoesExecucaoPlanoError('claim_referencia e obrigatoria')
        claim_sha256 = _sha256_texto(claim_limpo)
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'''WITH candidata AS (
                       SELECT candidata.acao_execucao_id FROM {_TABELA} AS candidata
                            WHERE candidata.event_id = %s
                              AND candidata.preview_id = %s
                              AND (candidata.estado = %s OR (
                                  candidata.estado = %s AND
                                  (candidata.proxima_tentativa_em IS NULL OR
                                   candidata.proxima_tentativa_em <= %s)))
                              AND NOT EXISTS (
                                  SELECT 1 FROM {_TABELA} AS anterior
                                   WHERE anterior.event_id = candidata.event_id
                                     AND anterior.preview_id = candidata.preview_id
                                     AND anterior.destinatario_sha256 =
                                         candidata.destinatario_sha256
                                     AND anterior.ordem < candidata.ordem
                                     AND anterior.estado <> %s
                              )
                            ORDER BY candidata.ordem ASC,
                                     candidata.destinatario_sha256 ASC
                            FOR UPDATE SKIP LOCKED LIMIT 1
                       )
                       UPDATE {_TABELA} AS a
                          SET estado = %s, attempt = attempt + 1,
                              claim_sha256 = %s, reivindicado_em = %s,
                              proxima_tentativa_em = NULL,
                              atualizado_em = %s
                         FROM candidata
                        WHERE a.acao_execucao_id = candidata.acao_execucao_id
                          AND a.estado IN (%s, %s)
                    RETURNING a.*''',
                    (
                        event_id, preview_id,
                        EstadoAcaoExecucaoPlano.PENDING.value,
                        EstadoAcaoExecucaoPlano.FAILED_RETRYABLE.value,
                        reivindicado_em,
                        EstadoAcaoExecucaoPlano.SUCCEEDED.value,
                        EstadoAcaoExecucaoPlano.EXECUTING.value,
                        claim_sha256, reivindicado_em, reivindicado_em,
                        EstadoAcaoExecucaoPlano.PENDING.value,
                        EstadoAcaoExecucaoPlano.FAILED_RETRYABLE.value,
                    ),
                )
                linha = cursor.fetchone()
            self._conexao.commit()
            return _linha_para_registro(linha) if linha else None
        except Exception:
            self._conexao.rollback()
            raise

    def marcar_sucesso(
        self, *, acao_execucao_id: str, claim_referencia: str,
        atualizado_em: datetime, resultado_referencia: Optional[str] = None,
        evidencia: Optional[bytes] = None,
    ) -> Optional[RegistroAcaoExecucaoPlano]:
        return self._finalizar(
            acao_execucao_id=acao_execucao_id,
            claim_referencia=claim_referencia,
            estado=EstadoAcaoExecucaoPlano.SUCCEEDED,
            atualizado_em=atualizado_em,
            resultado_referencia=resultado_referencia,
            evidencia=evidencia,
        )

    def marcar_falha(
        self, *, acao_execucao_id: str, claim_referencia: str,
        atualizado_em: datetime, erro_classe: str, retentavel: bool,
        proxima_tentativa_em: Optional[datetime] = None,
    ) -> Optional[RegistroAcaoExecucaoPlano]:
        estado = (
            EstadoAcaoExecucaoPlano.FAILED_RETRYABLE if retentavel
            else EstadoAcaoExecucaoPlano.FAILED_FINAL
        )
        return self._finalizar(
            acao_execucao_id=acao_execucao_id,
            claim_referencia=claim_referencia,
            estado=estado, atualizado_em=atualizado_em,
            erro_classe=erro_classe,
            proxima_tentativa_em=proxima_tentativa_em,
        )

    def _finalizar(
        self, *, acao_execucao_id: str, claim_referencia: str,
        estado: EstadoAcaoExecucaoPlano, atualizado_em: datetime,
        erro_classe: Optional[str] = None,
        proxima_tentativa_em: Optional[datetime] = None,
        resultado_referencia: Optional[str] = None,
        evidencia: Optional[bytes] = None,
    ) -> Optional[RegistroAcaoExecucaoPlano]:
        terminal = estado in {
            EstadoAcaoExecucaoPlano.SUCCEEDED,
            EstadoAcaoExecucaoPlano.FAILED_FINAL,
        }
        evidencia_sha256 = (
            hash_conteudo_comunicacao(evidencia) if evidencia is not None else None
        )
        claim_sha256 = _sha256_texto(str(claim_referencia or '').strip())
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'''UPDATE {_TABELA}
                           SET estado = %s, proxima_tentativa_em = %s,
                               ultimo_erro_classe = %s,
                               resultado_referencia = %s,
                               evidencia_sha256 = %s, atualizado_em = %s,
                               concluido_em = %s
                         WHERE acao_execucao_id = %s AND estado = %s
                           AND claim_sha256 = %s
                     RETURNING {_COLUNAS_SQL}''',
                    (
                        estado.value, proxima_tentativa_em, erro_classe,
                        resultado_referencia, evidencia_sha256, atualizado_em,
                        atualizado_em if terminal else None,
                        acao_execucao_id,
                        EstadoAcaoExecucaoPlano.EXECUTING.value,
                        claim_sha256,
                    ),
                )
                linha = cursor.fetchone()
            self._conexao.commit()
            return _linha_para_registro(linha) if linha else None
        except Exception:
            self._conexao.rollback()
            raise

    def fechar(self) -> None:
        self._conexao.close()
