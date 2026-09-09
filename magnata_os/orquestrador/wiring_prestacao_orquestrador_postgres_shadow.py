"""Composição canônica Prestação -> Orquestrador Postgres, V1 shadow.

Encadeia exclusivamente contratos já existentes até ``PlanoDisparo`` e para.
O módulo não importa transporte, Evolution, Flask, Airtable ou requests e não
expõe qualquer dependência capaz de enviar uma comunicação.

``materializar_prestacao_orquestrador_persistente_shadow`` estende a mesma
composição um passo além: persiste as ações do ``PlanoDisparo`` autorizado em
``magnata_orquestrador.acoes_execucao_plano`` via
``RepositorioAcoesExecucaoPlanoPostgres`` (claim/checkpoint/retry já
existentes e testados nesse repositório, reutilizados sem alteração). Mantém
o sufixo ``_shadow`` porque nenhum transporte é acionado a partir daqui.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Iterable, Sequence, Tuple

from magnata_os.classificacao.pacote_prestacao import PacotePrestacaoCliente
from magnata_os.documental.modulo01.armazenamento import ArmazenamentoArquivos

from .autorizacao_gate import (
    AutorizacaoGateError,
    DecisaoGate,
    RegistroAutorizacaoGate,
    RepositorioAutorizacoesGate,
    registrar_decisao_gate_shadow,
)
from .plano_comunicacao import ConteudoItem
from .envelope_execucao_autorizada import armazenar_acao_e_envelope_v1
from .politica_comunicacao import ItemComunicacao, PreferenciaComposicao
from .repositorio_acoes_execucao_plano_postgres import (
    RegistroAcaoExecucaoPlano,
    RepositorioAcoesExecucaoPlanoPostgres,
    criar_registro_acao_plano,
)
from .repositorio_autorizacoes_gate_postgres import (
    RepositorioAutorizacoesGatePostgres,
)
from .repositorio_execucoes import RepositorioExecucoes
from .repositorio_execucoes_postgres import RepositorioExecucoesPostgres
from .wiring_autorizacao_persistida_plano_shadow import (
    materializar_plano_com_autorizacao_persistida_shadow,
)
from .wiring_autorizacao_plano_shadow import ResultadoAutorizacaoPlanoShadow
from .wiring_prestacao_comunicacao_shadow import (
    ResultadoWiringPrestacaoComunicacaoShadow,
    registrar_intencao_comunicacao_shadow,
)


@dataclasses.dataclass(frozen=True)
class ResultadoPrestacaoOrquestradorPostgresShadow:
    intencao: ResultadoWiringPrestacaoComunicacaoShadow
    autorizacao: RegistroAutorizacaoGate
    plano: ResultadoAutorizacaoPlanoShadow


def materializar_prestacao_orquestrador_shadow(
    *,
    pacote: PacotePrestacaoCliente,
    repositorio_execucoes: RepositorioExecucoes,
    repositorio_autorizacoes: RepositorioAutorizacoesGate,
    destinatarios: Iterable[str],
    texto: str,
    itens: Sequence[ItemComunicacao],
    conteudos: Iterable[ConteudoItem],
    assinatura: bool,
    comprovante: bool,
    preview_id_autorizado: str,
    ator_referencia: str,
    proveniencia_autorizacao: str,
    preferencia: PreferenciaComposicao = 'otimizar',
    canal_preferencial: str = 'WHATSAPP',
    instante: datetime | None = None,
) -> ResultadoPrestacaoOrquestradorPostgresShadow:
    """Persiste intenção e autorização, materializa o plano e sempre para."""
    resultado_intencao = registrar_intencao_comunicacao_shadow(
        pacote=pacote,
        repositorio=repositorio_execucoes,
        destinatarios=destinatarios,
        texto=texto,
        itens=itens,
        assinatura=assinatura,
        comprovante=comprovante,
        preferencia=preferencia,
        canal_preferencial=canal_preferencial,
        instante=instante,
    )

    preview_id = resultado_intencao.intencao.preview.preview_id
    if preview_id_autorizado != preview_id:
        raise AutorizacaoGateError(
            'autorizacao nao corresponde ao preview exato da intencao'
        )

    autorizacao = registrar_decisao_gate_shadow(
        repositorio_execucoes=repositorio_execucoes,
        repositorio_autorizacoes=repositorio_autorizacoes,
        event_id=resultado_intencao.execucao.event_id,
        preview_id=preview_id,
        decisao=DecisaoGate.AUTORIZADO,
        ator_referencia=ator_referencia,
        proveniencia=proveniencia_autorizacao,
        instante=instante,
    )
    resultado_plano = materializar_plano_com_autorizacao_persistida_shadow(
        intencao=resultado_intencao.intencao,
        repositorio_execucoes=repositorio_execucoes,
        autorizacao=autorizacao,
        texto=texto,
        conteudos=conteudos,
    )
    return ResultadoPrestacaoOrquestradorPostgresShadow(
        intencao=resultado_intencao,
        autorizacao=autorizacao,
        plano=resultado_plano,
    )


def materializar_prestacao_orquestrador_postgres_shadow(
    *, conexao_postgres, **kwargs,
) -> ResultadoPrestacaoOrquestradorPostgresShadow:
    """Compõe os adapters Postgres sobre conexão DB-API já autenticada."""
    return materializar_prestacao_orquestrador_shadow(
        repositorio_execucoes=RepositorioExecucoesPostgres(conexao_postgres),
        repositorio_autorizacoes=RepositorioAutorizacoesGatePostgres(
            conexao_postgres
        ),
        **kwargs,
    )


@dataclasses.dataclass(frozen=True)
class ResultadoPrestacaoOrquestradorPersistenteShadow:
    """Resultado da composição completa, com as ações já persistidas.

    ``acoes`` são os registros efetivamente gravados (ou já existentes, em
    caso de reaplicação idempotente) em ``acoes_execucao_plano``. Nenhum
    transporte é acionado por esta função nem por qualquer coisa que ela
    chame.
    """

    intencao: ResultadoWiringPrestacaoComunicacaoShadow
    autorizacao: RegistroAutorizacaoGate
    plano: ResultadoAutorizacaoPlanoShadow
    acoes: Tuple[RegistroAcaoExecucaoPlano, ...]


def materializar_prestacao_orquestrador_persistente_shadow(
    *,
    pacote: PacotePrestacaoCliente,
    repositorio_execucoes: RepositorioExecucoes,
    repositorio_autorizacoes: RepositorioAutorizacoesGate,
    repositorio_acoes: RepositorioAcoesExecucaoPlanoPostgres,
    armazenamento: ArmazenamentoArquivos,
    destinatarios: Iterable[str],
    texto: str,
    itens: Sequence[ItemComunicacao],
    conteudos: Iterable[ConteudoItem],
    assinatura: bool,
    comprovante: bool,
    preview_id_autorizado: str,
    ator_referencia: str,
    proveniencia_autorizacao: str,
    preferencia: PreferenciaComposicao = 'otimizar',
    canal_preferencial: str = 'WHATSAPP',
    instante: datetime | None = None,
) -> ResultadoPrestacaoOrquestradorPersistenteShadow:
    """Estende a composição shadow persistindo as ações do plano autorizado.

    Reutiliza ``materializar_prestacao_orquestrador_shadow`` sem alterá-la e
    encadeia ``RepositorioAcoesExecucaoPlanoPostgres.materializar_plano`` —
    mesmo claim/checkpoint/retry já existentes e testados nesse repositório,
    nenhum mecanismo novo. Ainda para exatamente antes do transporte: nenhuma
    ação aqui reivindica (`reivindicar_proxima`), executa ou finaliza
    (`marcar_sucesso`/`marcar_falha`) — apenas materializa.
    """
    agora = instante or datetime.now(timezone.utc)
    resultado = materializar_prestacao_orquestrador_shadow(
        pacote=pacote,
        repositorio_execucoes=repositorio_execucoes,
        repositorio_autorizacoes=repositorio_autorizacoes,
        destinatarios=destinatarios,
        texto=texto,
        itens=itens,
        conteudos=conteudos,
        assinatura=assinatura,
        comprovante=comprovante,
        preview_id_autorizado=preview_id_autorizado,
        ator_referencia=ator_referencia,
        proveniencia_autorizacao=proveniencia_autorizacao,
        preferencia=preferencia,
        canal_preferencial=canal_preferencial,
        instante=agora,
    )
    registros = []
    for acao in resultado.plano.plano.acoes:
        registro = criar_registro_acao_plano(
            event_id=resultado.intencao.execucao.event_id,
            plano=resultado.plano.plano,
            autorizacao=resultado.autorizacao,
            acao=acao,
            criado_em=agora,
        )
        envelope_sha256 = armazenar_acao_e_envelope_v1(
            armazenamento=armazenamento, registro=registro, acao=acao,
        )
        registros.append(dataclasses.replace(
            registro, envelope_sha256=envelope_sha256,
        ))
    acoes = repositorio_acoes.materializar_registros(
        registros=tuple(registros), autorizacao=resultado.autorizacao,
    )
    return ResultadoPrestacaoOrquestradorPersistenteShadow(
        intencao=resultado.intencao,
        autorizacao=resultado.autorizacao,
        plano=resultado.plano,
        acoes=acoes,
    )


def materializar_prestacao_orquestrador_persistente_postgres_shadow(
    *, conexao_postgres, **kwargs,
) -> ResultadoPrestacaoOrquestradorPersistenteShadow:
    """Compõe os três adapters Postgres sobre a mesma conexão DB-API.

    A mesma conexão é compartilhada pelos três repositórios para que a
    intenção, a autorização e a persistência das ações fiquem sob a
    disciplina transacional de cada adapter, sem introduzir uma segunda
    conexão nem uma transação distribuída.
    """
    return materializar_prestacao_orquestrador_persistente_shadow(
        repositorio_execucoes=RepositorioExecucoesPostgres(conexao_postgres),
        repositorio_autorizacoes=RepositorioAutorizacoesGatePostgres(
            conexao_postgres
        ),
        repositorio_acoes=RepositorioAcoesExecucaoPlanoPostgres(
            conexao_postgres
        ),
        **kwargs,
    )
