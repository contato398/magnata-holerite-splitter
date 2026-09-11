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
from .envelope_execucao_autorizada import calcular_identidades_acao
from .plano_comunicacao import AcaoEnvio, PlanoDisparo
from .politica_comunicacao import hash_conteudo_comunicacao


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
    envelope_sha256: Optional[str]
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
    'conteudo_sha256', 'texto_sha256', 'envelope_sha256', 'estado', 'attempt',
    'proxima_tentativa_em', 'claim_sha256', 'reivindicado_em',
    'ultimo_erro_classe', 'resultado_referencia', 'evidencia_sha256',
    'criado_em', 'atualizado_em', 'concluido_em',
)
_COLUNAS_SQL = ', '.join(_COLUNAS)
_COLUNAS_SQL_ACAO = ', '.join(f'a.{coluna}' for coluna in _COLUNAS)


def _identidades_acao(acao: AcaoEnvio) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    try:
        ids = calcular_identidades_acao(acao)
    except ValueError as exc:
        raise RepositorioAcoesExecucaoPlanoError(str(exc)) from exc
    return (
        ids.destinatario_sha256, ids.nome_sha256,
        ids.conteudo_sha256, ids.texto_sha256,
    )


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
        envelope_sha256=None,
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
    return valores[:11] + (registro.estado.value,) + valores[12:]


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
        return self.materializar_registros(
            registros=registros, autorizacao=autorizacao,
        )

    def materializar_registros(
        self, *, registros: Tuple[RegistroAcaoExecucaoPlano, ...],
        autorizacao: RegistroAutorizacaoGate,
    ) -> Tuple[RegistroAcaoExecucaoPlano, ...]:
        """Persiste registros já preparados; blobs devem existir antes."""
        persistidos = []
        try:
            with self._conexao.cursor() as cursor:
                for registro in registros:
                    if (
                        registro.autorizacao_id != autorizacao.autorizacao_id
                        or registro.event_id != autorizacao.event_id
                        or registro.preview_id != autorizacao.preview_id
                    ):
                        raise RepositorioAcoesExecucaoPlanoError(
                            'registro diverge da autorizacao exata'
                        )
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
                            autorizacao.autorizacao_id, registro.event_id,
                            registro.preview_id, DecisaoGate.AUTORIZADO.value,
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
                        if _linha_registro(existente_registro)[:11] != _linha_registro(registro)[:11]:
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

    @staticmethod
    def _predicado_elegibilidade(alias: str) -> str:
        return f'''{alias}.envelope_sha256 IS NOT NULL
                  AND ({alias}.estado = %s OR (
                      {alias}.estado = %s AND
                      ({alias}.proxima_tentativa_em IS NULL OR
                       {alias}.proxima_tentativa_em <= %s)))
                  AND NOT EXISTS (
                      SELECT 1 FROM {_TABELA} AS anterior
                       WHERE anterior.event_id = {alias}.event_id
                         AND anterior.preview_id = {alias}.preview_id
                         AND anterior.destinatario_sha256 =
                             {alias}.destinatario_sha256
                         AND anterior.ordem < {alias}.ordem
                         AND anterior.estado <> %s
                  )'''

    @staticmethod
    def _parametros_elegibilidade(instante: datetime) -> tuple:
        return (
            EstadoAcaoExecucaoPlano.PENDING.value,
            EstadoAcaoExecucaoPlano.FAILED_RETRYABLE.value,
            instante,
            EstadoAcaoExecucaoPlano.SUCCEEDED.value,
        )

    def buscar_proxima_elegivel(
        self, *, event_id: str, preview_id: str, instante: datetime,
    ) -> Optional[RegistroAcaoExecucaoPlano]:
        """Descobre sem lock/claim; o claim exato fará novo CAS completo."""
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'''SELECT {_COLUNAS_SQL} FROM {_TABELA} AS candidata
                     WHERE candidata.event_id = %s
                       AND candidata.preview_id = %s
                       AND {self._predicado_elegibilidade('candidata')}
                     ORDER BY candidata.ordem ASC,
                              candidata.destinatario_sha256 ASC
                     LIMIT 1''',
                (event_id, preview_id) + self._parametros_elegibilidade(instante),
            )
            linha = cursor.fetchone()
        return _linha_para_registro(linha) if linha else None

    def listar_pares_elegiveis(
        self, *, instante: datetime, limite: int = 200,
    ) -> Tuple[Tuple[str, str], ...]:
        """Descoberta somente leitura, sem claim: pares (event_id,
        preview_id) distintos com ao menos uma ação elegível agora.
        Existe porque `buscar_proxima_elegivel`/`reivindicar_proxima`
        exigem event_id/preview_id já conhecidos -- o ciclo de produção
        precisa descobrir quais existem antes de poder chamá-los. Reusa
        o mesmo predicado de elegibilidade já usado no claim, nunca uma
        regra paralela."""
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'''SELECT DISTINCT candidata.event_id, candidata.preview_id
                      FROM {_TABELA} AS candidata
                     WHERE {self._predicado_elegibilidade('candidata')}
                     ORDER BY candidata.event_id, candidata.preview_id
                     LIMIT %s''',
                self._parametros_elegibilidade(instante) + (limite,),
            )
            linhas = cursor.fetchall()
        return tuple((linha[0], linha[1]) for linha in linhas)

    def listar_succeeded_recentes(
        self, *, limite: int = 200,
    ) -> Tuple[RegistroAcaoExecucaoPlano, ...]:
        """Somente leitura: ações já `SUCCEEDED`, mais recentes primeiro
        -- candidatas a observação de assinatura. O observador do ciclo
        de produção cruza isto com `conclusao_obrigacao_assinatura` (em
        outro repositório) para saber quais ainda faltam concluir; esta
        consulta nunca sabe nada sobre assinatura."""
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'''SELECT {_COLUNAS_SQL} FROM {_TABELA}
                     WHERE estado = %s AND tipo = %s
                     ORDER BY atualizado_em DESC
                     LIMIT %s''',
                (EstadoAcaoExecucaoPlano.SUCCEEDED.value, 'texto', limite),
            )
            linhas = cursor.fetchall()
        return tuple(_linha_para_registro(linha) for linha in linhas)

    def reivindicar_acao_exata(
        self, *, acao_execucao_id: str, claim_referencia: str,
        reivindicado_em: datetime,
    ) -> Optional[RegistroAcaoExecucaoPlano]:
        """CAS da ação previamente verificada; nunca troca por outra candidata."""
        claim_limpo = str(claim_referencia or '').strip()
        if not claim_limpo:
            raise RepositorioAcoesExecucaoPlanoError('claim_referencia e obrigatoria')
        claim_sha256 = hashlib.sha256(claim_limpo.encode('utf-8')).hexdigest()
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'''WITH candidata AS (
                           SELECT candidata.acao_execucao_id
                             FROM {_TABELA} AS candidata
                            WHERE candidata.acao_execucao_id = %s
                              AND {self._predicado_elegibilidade('candidata')}
                            FOR UPDATE SKIP LOCKED
                       )
                       UPDATE {_TABELA} AS a
                          SET estado = %s, attempt = attempt + 1,
                              claim_sha256 = %s, reivindicado_em = %s,
                              proxima_tentativa_em = NULL, atualizado_em = %s
                         FROM candidata
                        WHERE a.acao_execucao_id = candidata.acao_execucao_id
                          AND a.acao_execucao_id = %s
                          AND a.envelope_sha256 IS NOT NULL
                          AND a.estado IN (%s, %s)
                    RETURNING {_COLUNAS_SQL_ACAO}''',
                    (
                        acao_execucao_id,
                        *self._parametros_elegibilidade(reivindicado_em),
                        EstadoAcaoExecucaoPlano.EXECUTING.value,
                        claim_sha256, reivindicado_em, reivindicado_em,
                        acao_execucao_id,
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

    def reivindicar_proxima(
        self, *, event_id: str, preview_id: str,
        claim_referencia: str, reivindicado_em: datetime,
    ) -> Optional[RegistroAcaoExecucaoPlano]:
        claim_limpo = str(claim_referencia or '').strip()
        if not claim_limpo:
            raise RepositorioAcoesExecucaoPlanoError('claim_referencia e obrigatoria')
        claim_sha256 = hashlib.sha256(claim_limpo.encode('utf-8')).hexdigest()
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(
                    f'''WITH candidata AS (
                       SELECT candidata.acao_execucao_id FROM {_TABELA} AS candidata
                            WHERE candidata.event_id = %s
                              AND candidata.preview_id = %s
                              AND candidata.envelope_sha256 IS NOT NULL
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
                    RETURNING {_COLUNAS_SQL_ACAO}''',
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
        claim_sha256 = hashlib.sha256(
            str(claim_referencia or '').strip().encode('utf-8')
        ).hexdigest()
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

    def _finalizar_por_claim_sha256_atual(
        self, *, acao_execucao_id: str, claim_sha256_atual: str,
        estado: EstadoAcaoExecucaoPlano, atualizado_em: datetime,
        erro_classe: Optional[str] = None,
        proxima_tentativa_em: Optional[datetime] = None,
        resultado_referencia: Optional[str] = None,
        evidencia: Optional[bytes] = None,
    ) -> Optional[RegistroAcaoExecucaoPlano]:
        """Mesma forma de `_finalizar`, mas o CAS compara diretamente o
        `claim_sha256` já persistido na linha (lido antes por `buscar()`),
        em vez de recalcular a partir de uma `claim_referencia` em claro.

        Uso exclusivo de reconciliação humana (Bloqueio EXECUTING órfão,
        Casos A/C): quem está reconciliando não é o executor original e
        não tem, nem deveria ter, a `claim_referencia` efêmera do worker
        morto -- só a evidência já persistida na própria linha.
        """
        terminal = estado in {
            EstadoAcaoExecucaoPlano.SUCCEEDED,
            EstadoAcaoExecucaoPlano.FAILED_FINAL,
        }
        evidencia_sha256 = (
            hash_conteudo_comunicacao(evidencia) if evidencia is not None else None
        )
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
                        claim_sha256_atual,
                    ),
                )
                linha = cursor.fetchone()
            self._conexao.commit()
            return _linha_para_registro(linha) if linha else None
        except Exception:
            self._conexao.rollback()
            raise

    def liberar_apos_confirmacao_ausencia_envio(
        self, *, acao_execucao_id: str, claim_sha256_atual: str,
        atualizado_em: datetime,
    ) -> Optional[RegistroAcaoExecucaoPlano]:
        """Caso A do bloqueio EXECUTING órfão: um humano já confirmou, fora
        de banda, que esta ação presa em EXECUTING não teve side effect
        externo. Libera para retry (FAILED_RETRYABLE), nunca para SUCCEEDED
        -- retry continua passando pelas mesmas regras de elegibilidade e
        MAX_TENTATIVAS de sempre. `ator_referencia`/`motivo` não moram
        nesta tabela: são responsabilidade do chamador registrar via
        `RepositorioExecucoesPostgres.registrar_recuperacao` (ver
        `reconciliacao_execucao_orfa.py`) -- nunca esta função sozinha,
        que por isso nunca deve ser chamada isoladamente por automação."""
        return self._finalizar_por_claim_sha256_atual(
            acao_execucao_id=acao_execucao_id,
            claim_sha256_atual=claim_sha256_atual,
            estado=EstadoAcaoExecucaoPlano.FAILED_RETRYABLE,
            atualizado_em=atualizado_em,
            erro_classe='ORFAO_SEM_ENVIO_CONFIRMADO',
        )

    def reconciliar_envio_confirmado(
        self, *, acao_execucao_id: str, claim_sha256_atual: str,
        atualizado_em: datetime, resultado_referencia: str, evidencia: bytes,
    ) -> Optional[RegistroAcaoExecucaoPlano]:
        """Caso C do bloqueio EXECUTING órfão: evidência externa (ex.: log
        da Evolution) confirma que a mensagem foi entregue. Reconcilia o
        estado interno para SUCCEEDED com o ID externo confirmado -- nunca
        reenvia."""
        return self._finalizar_por_claim_sha256_atual(
            acao_execucao_id=acao_execucao_id,
            claim_sha256_atual=claim_sha256_atual,
            estado=EstadoAcaoExecucaoPlano.SUCCEEDED,
            atualizado_em=atualizado_em,
            resultado_referencia=resultado_referencia,
            evidencia=evidencia,
        )

    def listar_em_execucao_reivindicadas_antes_de(
        self, *, instante_limite: datetime,
    ) -> Tuple[RegistroAcaoExecucaoPlano, ...]:
        """Visão somente leitura (Caso B): lista ações em EXECUTING cujo
        `reivindicado_em` é anterior ao limite informado -- candidatas a
        inspeção humana, nunca a ação automática. Não altera nenhum
        estado; mesmo padrão de `VisaoFilaDesistenciaPersistente`
        (visão derivada, sem tabela nem fonte de verdade paralela)."""
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'''SELECT {_COLUNAS_SQL} FROM {_TABELA}
                     WHERE estado = %s AND reivindicado_em < %s
                     ORDER BY reivindicado_em ASC''',
                (EstadoAcaoExecucaoPlano.EXECUTING.value, instante_limite),
            )
            linhas = cursor.fetchall()
        return tuple(_linha_para_registro(linha) for linha in linhas)

    def fechar(self) -> None:
        self._conexao.close()
