"""Adapter Postgres para `magnata_orquestrador.conclusao_obrigacao_assinatura`
(migration 0006, inerte/não aplicada em produção nesta missão).

Mesmo padrão de `RepositorioExecucoesPostgres.registrar_recuperacao` /
`listar_recuperacoes`: append-only, sem UPDATE nem DELETE (a tabela em si
já bloqueia isso por trigger de banco -- este adapter nunca tenta).

Gate 1 -- registro canônico da obrigação de assinatura: a EXISTÊNCIA de
uma obrigação de assinatura é determinada por estado persistido nesta
tabela, correlacionado ao `acao_execucao_id` -- nunca pelo tipo
documental, pelo tipo físico da ação ou pelo conteúdo da mensagem. O
`acao_execucao_id` é opaco aqui: produtores diferentes (fluxo legado de
assinatura, núcleo genérico de distribuição) o derivam de formas
diferentes sem alterar este contrato.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import List, Optional, Tuple

_TABELA = 'magnata_orquestrador.conclusao_obrigacao_assinatura'
_TABELA_ACOES = 'magnata_orquestrador.acoes_execucao_plano'
_ESTADOS_VALIDOS = (
    'AGUARDANDO_ASSINATURA', 'ASSINADO', 'COMPROVANTE_VALIDADO', 'CONCLUIDO',
)
ESTADO_INICIAL_OBRIGACAO = 'AGUARDANDO_ASSINATURA'
ESTADO_TERMINAL_OBRIGACAO = 'CONCLUIDO'

# Namespace do advisory lock transacional por `acao_execucao_id` (forma de
# 2 chaves int4 -- espaço de chaves separado do lock global de sessão do
# ciclo de produção, que usa a forma de 1 chave bigint). 6006 = migration
# 0006. Serializa check-then-insert por ação sem nenhuma mudança de schema.
_NAMESPACE_LOCK_OBRIGACAO = 6006
_SQL_LOCK_ACAO = 'SELECT pg_advisory_xact_lock(%s, hashtext(%s))'
_SQL_ULTIMO_ESTADO = (
    f'SELECT estado FROM {_TABELA} WHERE acao_execucao_id = %s ORDER BY id DESC LIMIT 1'
)
_SQL_INSERT = (
    f'INSERT INTO {_TABELA} '
    '(acao_execucao_id, estado, correlacao_externa, evidencia_sha256, registrado_em) '
    'VALUES (%s, %s, %s, %s, %s)'
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
        """Append incondicional (primitiva histórica). Quem precisa de
        idempotência usa `registrar_obrigacao_inicial` ou
        `registrar_transicao_se_mudou`."""
        try:
            with self._conexao.cursor() as cursor:
                cursor.execute(_SQL_INSERT, self._valores(registro))
            self._conexao.commit()
        except Exception:
            self._conexao.rollback()
            raise

    @staticmethod
    def _valores(registro: RegistroConclusaoObrigacaoAssinatura) -> tuple:
        return (
            registro.acao_execucao_id, registro.estado,
            registro.correlacao_externa, registro.evidencia_sha256,
            registro.registrado_em,
        )

    def _verificar_e_inserir(self, cursor, registro: RegistroConclusaoObrigacaoAssinatura, deve_registrar) -> bool:
        """Check-then-insert sob advisory lock transacional por
        `acao_execucao_id`, no cursor/transação recebido (sem commit):
        dois processos concorrentes sobre a mesma ação nunca leem o mesmo
        "último estado" e gravam os dois. O lock dura até o commit/
        rollback de quem controla a transação."""
        cursor.execute(_SQL_LOCK_ACAO, (_NAMESPACE_LOCK_OBRIGACAO, registro.acao_execucao_id))
        cursor.execute(_SQL_ULTIMO_ESTADO, (registro.acao_execucao_id,))
        linha = cursor.fetchone()
        ultimo_estado = linha[0] if linha else None
        gravou = bool(deve_registrar(ultimo_estado))
        if gravou:
            cursor.execute(_SQL_INSERT, self._valores(registro))
        return gravou

    def _registrar_atomico(self, registro: RegistroConclusaoObrigacaoAssinatura, deve_registrar) -> bool:
        """`_verificar_e_inserir` em transação própria desta conexão."""
        try:
            with self._conexao.cursor() as cursor:
                gravou = self._verificar_e_inserir(cursor, registro, deve_registrar)
            self._conexao.commit()  # libera o advisory lock transacional
            return gravou
        except Exception:
            self._conexao.rollback()
            raise

    @staticmethod
    def _registro_inicial(acao_execucao_id, correlacao_externa, registrado_em) -> RegistroConclusaoObrigacaoAssinatura:
        return RegistroConclusaoObrigacaoAssinatura(
            acao_execucao_id=acao_execucao_id, estado=ESTADO_INICIAL_OBRIGACAO,
            correlacao_externa=correlacao_externa, evidencia_sha256=None,
            registrado_em=registrado_em,
        )

    def registrar_obrigacao_inicial(
        self, *, acao_execucao_id: str, correlacao_externa: Optional[str], registrado_em: datetime,
    ) -> bool:
        """Marcador canônico da EXISTÊNCIA da obrigação: grava
        `AGUARDANDO_ASSINATURA` SOMENTE se ainda não há nenhum histórico
        para a ação -- nunca "se diferente do último": no replay de uma
        obrigação já `ASSINADO`/`CONCLUIDO` isso regrediria o estado.
        Exige a ação já persistida (FK da migration 0006). Devolve True se
        gravou; False se o marcador (ou estado posterior) já existia.
        Transação própria -- para reparo avulso; os produtores usam
        `registrar_obrigacao_inicial_na_transacao` (atômico com a ação)."""
        registro = self._registro_inicial(acao_execucao_id, correlacao_externa, registrado_em)
        return self._registrar_atomico(registro, lambda ultimo: ultimo is None)

    def registrar_obrigacao_inicial_na_transacao(
        self, cursor, *, acao_execucao_id: str, correlacao_externa: Optional[str], registrado_em: datetime,
    ) -> bool:
        """Mesmo marcador, DENTRO da transação de quem persiste a ação
        (`RepositorioAcoesExecucaoPlanoPostgres.materializar_registros`,
        gancho `na_mesma_transacao`) -- ação e marcador nascem juntos: a
        ação nunca fica reivindicável/enviável sem o marcador, e falha no
        marcador (ex.: 0006 ausente) desfaz a ação. Sem commit aqui."""
        registro = self._registro_inicial(acao_execucao_id, correlacao_externa, registrado_em)
        return self._verificar_e_inserir(cursor, registro, lambda ultimo: ultimo is None)

    def registrar_transicao_se_mudou(
        self, registro: RegistroConclusaoObrigacaoAssinatura,
    ) -> bool:
        """Append idempotente para o observador: só grava se o estado
        difere do último persistido -- atômico (ver `_registrar_atomico`),
        nunca duplica histórico sob replay ou concorrência."""
        return self._registrar_atomico(registro, lambda ultimo: ultimo != registro.estado)

    def listar_acoes_para_observacao(self, *, limite: int = 200) -> Tuple[str, ...]:
        """Seleção CANÔNICA do observador: ações `SUCCEEDED` que TÊM
        obrigação de assinatura registrada nesta tabela e cujo último
        estado ainda não é terminal (`CONCLUIDO`). Parte das obrigações
        (DISTINCT ON sobre o índice `(acao_execucao_id, id)`), nunca de
        todas as ações SUCCEEDED -- ação sem obrigação nunca é
        selecionada e, portanto, nunca gera consulta ao adapter legado.
        Nenhum critério por tipo físico da ação, tipo documental ou
        conteúdo."""
        try:
            return self._listar_acoes_para_observacao(limite)
        except Exception:
            # Nunca deixa a conexão compartilhada em transação abortada
            # (o ciclo ainda libera seu advisory lock nela).
            self._conexao.rollback()
            raise

    def _listar_acoes_para_observacao(self, limite: int) -> Tuple[str, ...]:
        with self._conexao.cursor() as cursor:
            cursor.execute(
                f'''SELECT ultimo.acao_execucao_id
                      FROM (SELECT DISTINCT ON (c.acao_execucao_id) c.acao_execucao_id, c.estado
                              FROM {_TABELA} AS c
                             ORDER BY c.acao_execucao_id, c.id DESC) AS ultimo
                      JOIN {_TABELA_ACOES} AS a ON a.acao_execucao_id = ultimo.acao_execucao_id
                     WHERE ultimo.estado <> %s
                       AND a.estado = %s
                     ORDER BY a.atualizado_em DESC, a.acao_execucao_id
                     LIMIT %s''',
                (ESTADO_TERMINAL_OBRIGACAO, 'SUCCEEDED', limite),
            )
            linhas = cursor.fetchall()
        return tuple(linha[0] for linha in linhas)

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


class RepositorioConclusaoObrigacaoAssinaturaEmMemoria:
    """Mesma semântica de registro do adapter Postgres (append-only,
    marcador inicial só sem histórico, transição só se mudou), para
    testes e shadow -- mesmo padrão de `RepositorioDocumentosEmMemoria`.
    `listar_acoes_para_observacao` recebe o estado das ações por
    parâmetro (em memória não há JOIN com `acoes_execucao_plano`)."""

    def __init__(self) -> None:
        self._historico: List[RegistroConclusaoObrigacaoAssinatura] = []

    def registrar_transicao(self, registro: RegistroConclusaoObrigacaoAssinatura) -> None:
        self._historico.append(registro)

    def listar_historico(self, acao_execucao_id: str) -> List[RegistroConclusaoObrigacaoAssinatura]:
        return [r for r in self._historico if r.acao_execucao_id == acao_execucao_id]

    def estado_mais_recente(self, acao_execucao_id: str) -> Optional[str]:
        historico = self.listar_historico(acao_execucao_id)
        return historico[-1].estado if historico else None

    def registrar_obrigacao_inicial(
        self, *, acao_execucao_id: str, correlacao_externa: Optional[str], registrado_em: datetime,
    ) -> bool:
        if self.listar_historico(acao_execucao_id):
            return False
        self.registrar_transicao(RegistroConclusaoObrigacaoAssinatura(
            acao_execucao_id=acao_execucao_id, estado=ESTADO_INICIAL_OBRIGACAO,
            correlacao_externa=correlacao_externa, evidencia_sha256=None,
            registrado_em=registrado_em,
        ))
        return True

    def registrar_obrigacao_inicial_na_transacao(self, cursor, **kwargs) -> bool:
        """Em memória não há transação -- mesmo efeito de
        `registrar_obrigacao_inicial` (o cursor é ignorado)."""
        return self.registrar_obrigacao_inicial(**kwargs)

    def registrar_transicao_se_mudou(self, registro: RegistroConclusaoObrigacaoAssinatura) -> bool:
        if self.estado_mais_recente(registro.acao_execucao_id) == registro.estado:
            return False
        self.registrar_transicao(registro)
        return True

    def listar_acoes_para_observacao(self, *, estado_da_acao, limite: int = 200) -> Tuple[str, ...]:
        vistos = []
        for registro in self._historico:
            if registro.acao_execucao_id not in vistos:
                vistos.append(registro.acao_execucao_id)
        return tuple(
            acao_id for acao_id in vistos
            if self.estado_mais_recente(acao_id) != ESTADO_TERMINAL_OBRIGACAO
            and estado_da_acao(acao_id) == 'SUCCEEDED'
        )[:limite]
