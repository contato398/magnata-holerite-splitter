"""Porta de transporte e executor de planos de comunicação.

O módulo coordena um :class:`PlanoDisparo` com um adapter injetado. Não conhece
Evolution, Flask, requests ou credenciais. Dessa forma o Magnata OS pode usar o
transporte legado atual sem duplicar o motor de envio e sem acoplar o domínio ao
fornecedor externo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Tuple

from .plano_comunicacao import AcaoEnvio, PlanoDisparo


class TransporteComunicacaoError(RuntimeError):
    """Erro de contrato ou execução do transporte de comunicação."""


@dataclass(frozen=True)
class ResultadoAcaoEnvio:
    destinatario: str
    ordem: int
    tipo: str
    nome: str
    resposta: object


@dataclass(frozen=True)
class ResultadoDisparo:
    preview_id: str
    resultados: Tuple[ResultadoAcaoEnvio, ...]


class FalhaDisparo(TransporteComunicacaoError):
    """Falha fail-fast com evidência das ações já concluídas."""

    def __init__(self, acao: AcaoEnvio, concluidas: Tuple[ResultadoAcaoEnvio, ...]) -> None:
        super().__init__(
            f"falha no envio {acao.tipo}:{acao.nome or acao.ordem} para {acao.destinatario}"
        )
        self.acao = acao
        self.concluidas = concluidas


class PortaTransporteWhatsapp(Protocol):
    """Contrato mínimo que o adapter do transporte legado precisa cumprir."""

    def enviar_texto(self, *, numero: str, texto: str) -> object:
        ...

    def enviar_video(
        self, *, numero: str, conteudo: object, nome_arquivo: str, legenda: str = ""
    ) -> object:
        ...

    def enviar_documento(
        self, *, numero: str, conteudo: object, nome_arquivo: str, legenda: str = ""
    ) -> object:
        ...


_TIPOS_EXECUTAVEIS = {"texto", "video", "documento"}


def _preflight(plano: PlanoDisparo) -> None:
    """Valida todo o plano antes da primeira chamada externa.

    Imagem/áudio existem na política para evolução futura, mas não são aceitos
    aqui enquanto o transporte legado oficial não tiver contrato equivalente.
    Isso evita executar metade de uma campanha antes de descobrir uma ação sem
    adapter.
    """
    nao_suportados = sorted({acao.tipo for acao in plano.acoes} - _TIPOS_EXECUTAVEIS)
    if nao_suportados:
        raise TransporteComunicacaoError(
            "transporte sem suporte para: " + ", ".join(nao_suportados)
        )


def executar_plano_disparo(
    *, plano: PlanoDisparo, transporte: PortaTransporteWhatsapp
) -> ResultadoDisparo:
    """Executa exatamente a ordem materializada no plano autorizado.

    A política e o gate já foram aplicados ao criar ``PlanoDisparo``. Aqui não
    há recomposição, deduplicação nem inferência: executar significa respeitar
    exatamente o plano. Qualquer falha interrompe o restante e devolve, pela
    exceção, as etapas concluídas para permitir retomada explícita pelo caller.
    """
    _preflight(plano)
    concluidas = []

    for acao in plano.acoes:
        try:
            if acao.tipo == "texto":
                resposta = transporte.enviar_texto(
                    numero=acao.destinatario,
                    texto=acao.texto,
                )
            elif acao.tipo == "video":
                resposta = transporte.enviar_video(
                    numero=acao.destinatario,
                    conteudo=acao.conteudo,
                    nome_arquivo=acao.nome,
                    legenda=acao.legenda,
                )
            elif acao.tipo == "documento":
                resposta = transporte.enviar_documento(
                    numero=acao.destinatario,
                    conteudo=acao.conteudo,
                    nome_arquivo=acao.nome,
                    legenda=acao.legenda,
                )
            else:  # protegido pelo preflight; defesa em profundidade
                raise TransporteComunicacaoError(f"tipo não executável: {acao.tipo}")
        except Exception as exc:
            if isinstance(exc, FalhaDisparo):
                raise
            raise FalhaDisparo(acao, tuple(concluidas)) from exc

        concluidas.append(ResultadoAcaoEnvio(
            destinatario=acao.destinatario,
            ordem=acao.ordem,
            tipo=acao.tipo,
            nome=acao.nome,
            resposta=resposta,
        ))

    return ResultadoDisparo(preview_id=plano.preview_id, resultados=tuple(concluidas))
