"""Plano executável, porém sem I/O, para comunicações WhatsApp.

Traduz uma :class:`PreviewComunicacao` já validada em passos concretos de
transporte. Esta camada não conhece Flask, Evolution, Airtable ou rede. O
adapter de entrega consome os passos; assim a política de composição continua
independente do fornecedor e o legado pode ser migrado incrementalmente.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

from .politica_comunicacao import (
    PreviewComunicacao,
    TipoItem,
    hash_conteudo_comunicacao,
    hash_texto_comunicacao,
    validar_autorizacao_disparo,
)


class PlanoComunicacaoError(ValueError):
    """Plano não pode ser construído com os dados fornecidos."""


@dataclass(frozen=True)
class ConteudoItem:
    """Conteúdo opaco associado a um item da prévia.

    ``conteudo`` é deliberadamente opaco: pode ser base64, URL interna,
    identificador de storage ou bytes, conforme o adapter concreto. O domínio
    não interpreta nem persiste o valor.
    """

    tipo: TipoItem
    nome: str
    conteudo: bytes

    def __post_init__(self) -> None:
        try:
            conteudo_imutavel = bytes(self.conteudo)
        except (TypeError, ValueError) as exc:
            raise PlanoComunicacaoError(
                "conteúdo de mídia deve ser binário para validar integridade"
            ) from exc
        object.__setattr__(self, "conteudo", conteudo_imutavel)

    @property
    def conteudo_sha256(self) -> str:
        return hash_conteudo_comunicacao(self.conteudo)


@dataclass(frozen=True)
class AcaoEnvio:
    destinatario: str
    ordem: int
    tipo: TipoItem
    nome: str = ""
    conteudo: object = None
    texto: str = ""
    legenda: str = ""


@dataclass(frozen=True)
class PlanoDisparo:
    preview_id: str
    destinatarios: Tuple[str, ...]
    acoes: Tuple[AcaoEnvio, ...]
    mensagens_por_pessoa: int
    total_notificacoes: int


def _chave(tipo: str, nome: str) -> Tuple[str, str]:
    return tipo, nome


def _indexar_conteudos(conteudos: Iterable[ConteudoItem]) -> Dict[Tuple[str, str], ConteudoItem]:
    indice: Dict[Tuple[str, str], ConteudoItem] = {}
    for item in conteudos:
        chave = _chave(item.tipo, item.nome)
        if chave in indice:
            raise PlanoComunicacaoError(
                f"conteúdo duplicado para item {item.tipo}:{item.nome}"
            )
        indice[chave] = item
    return indice


def montar_plano_disparo(
    *,
    preview: PreviewComunicacao,
    texto: str,
    conteudos: Iterable[ConteudoItem] = (),
    preview_id_autorizado: Optional[str],
    autorizacao_explicita: bool,
) -> PlanoDisparo:
    """Converte a prévia autorizada no plano exato a ser entregue.

    O gate é revalidado aqui, imediatamente antes da materialização. Isso evita
    que um caller contorne a política chamando diretamente o planejador.
    Conteúdo de mídia é casado por ``(tipo, nome)`` e nunca por posição.
    """
    validar_autorizacao_disparo(
        preview=preview,
        preview_id_autorizado=preview_id_autorizado,
        autorizacao_explicita=autorizacao_explicita,
    )

    texto_limpo = (texto or "").strip()
    if hash_texto_comunicacao(texto_limpo) != preview.texto_sha256:
        raise PlanoComunicacaoError("texto não corresponde à prévia autorizada")

    indice = _indexar_conteudos(conteudos)
    esperados = {_chave(item.tipo, item.nome) for item in preview.itens}
    recebidos = set(indice)
    faltantes = esperados - recebidos
    extras = recebidos - esperados
    if faltantes:
        faltantes_txt = ", ".join(f"{t}:{n}" for t, n in sorted(faltantes))
        raise PlanoComunicacaoError(f"conteúdo ausente para: {faltantes_txt}")
    if extras:
        extras_txt = ", ".join(f"{t}:{n}" for t, n in sorted(extras))
        raise PlanoComunicacaoError(f"conteúdo não previsto na prévia: {extras_txt}")

    for previsto in preview.itens:
        efetivo = indice[_chave(previsto.tipo, previsto.nome)]
        if efetivo.conteudo_sha256 != previsto.conteudo_sha256:
            raise PlanoComunicacaoError(
                f"conteúdo diverge da prévia autorizada: {previsto.tipo}:{previsto.nome}"
            )

    acoes = []
    for destinatario in preview.destinatarios:
        for ordem, passo in enumerate(preview.composicao_solicitada, start=1):
            if passo.tipo == "texto":
                acoes.append(AcaoEnvio(
                    destinatario=destinatario,
                    ordem=ordem,
                    tipo="texto",
                    nome=passo.nome,
                    texto=texto_limpo,
                ))
                continue

            item = indice.get(_chave(passo.tipo, passo.nome))
            if item is None:
                raise PlanoComunicacaoError(
                    f"conteúdo ausente para passo {passo.tipo}:{passo.nome}"
                )
            acoes.append(AcaoEnvio(
                destinatario=destinatario,
                ordem=ordem,
                tipo=passo.tipo,
                nome=passo.nome,
                conteudo=item.conteudo,
                legenda=texto_limpo if passo.usa_texto_como_legenda else "",
            ))

    if len(acoes) != preview.total_notificacoes:
        raise PlanoComunicacaoError("plano divergiu da contagem da prévia")

    return PlanoDisparo(
        preview_id=preview.preview_id,
        destinatarios=preview.destinatarios,
        acoes=tuple(acoes),
        mensagens_por_pessoa=preview.mensagens_por_pessoa,
        total_notificacoes=preview.total_notificacoes,
    )
