"""Composição canônica Prestação -> Orquestrador Postgres, V1 shadow.

Encadeia exclusivamente contratos já existentes até ``PlanoDisparo`` e para.
O módulo não importa transporte, Evolution, Flask, Airtable ou requests e não
expõe qualquer dependência capaz de enviar uma comunicação.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Iterable, Sequence

from magnata_os.classificacao.pacote_prestacao import PacotePrestacaoCliente

from .autorizacao_gate import (
    AutorizacaoGateError,
    DecisaoGate,
    RegistroAutorizacaoGate,
    RepositorioAutorizacoesGate,
    registrar_decisao_gate_shadow,
)
from .plano_comunicacao import ConteudoItem
from .politica_comunicacao import ItemComunicacao, PreferenciaComposicao
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
