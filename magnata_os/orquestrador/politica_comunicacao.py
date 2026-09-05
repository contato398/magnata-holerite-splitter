"""Política de composição de comunicações WhatsApp do Magnata OS.

Camada pura, sem rede, banco ou Airtable. Ela não envia nada: somente transforma
uma intenção de campanha em uma prévia verificável e aplica as travas de
governança antes de um disparo real.

Regra pétrea: minimizar notificações sem retirar a liberdade do operador.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable, Literal, Optional, Sequence, Tuple

PreferenciaComposicao = Literal["otimizar", "separado"]
TipoItem = Literal["video", "documento", "imagem", "audio", "texto"]


class PoliticaComunicacaoError(ValueError):
    """Erro de validação da política de comunicação."""


class PreviewObrigatorioError(PoliticaComunicacaoError):
    """Tentativa de disparo sem prévia válida da composição atual."""


class AutorizacaoObrigatoriaError(PoliticaComunicacaoError):
    """Tentativa de disparo real sem autorização posterior à prévia."""


@dataclass(frozen=True)
class ItemComunicacao:
    tipo: TipoItem
    nome: str = ""

    def __post_init__(self) -> None:
        if self.tipo not in {"video", "documento", "imagem", "audio", "texto"}:
            raise PoliticaComunicacaoError(f"tipo de item não suportado: {self.tipo}")


@dataclass(frozen=True)
class PassoComposicao:
    tipo: TipoItem
    nome: str = ""
    usa_texto_como_legenda: bool = False


@dataclass(frozen=True)
class PreviewComunicacao:
    destinatarios: Tuple[str, ...]
    tem_texto: bool
    texto_sha256: str
    itens: Tuple[ItemComunicacao, ...]
    assinatura: bool
    comprovante: bool
    preferencia: PreferenciaComposicao
    composicao_solicitada: Tuple[PassoComposicao, ...]
    composicao_otimizada: Tuple[PassoComposicao, ...]
    mensagens_por_pessoa: int
    total_notificacoes: int
    mensagens_otimizadas_por_pessoa: int
    total_otimizado: int
    alternativa_mais_compacta: bool
    alerta_fragmentacao: bool
    preview_id: str


_TIPOS_COM_LEGENDA = {"video", "documento", "imagem"}


def _normalizar_destinatarios(destinatarios: Iterable[str]) -> Tuple[str, ...]:
    vistos = set()
    resultado = []
    for bruto in destinatarios:
        valor = str(bruto or "").strip()
        if not valor or valor in vistos:
            continue
        vistos.add(valor)
        resultado.append(valor)
    if not resultado:
        raise PoliticaComunicacaoError("ao menos um destinatário é obrigatório")
    return tuple(resultado)


def _validar_opcoes_explicitas(assinatura: Optional[bool], comprovante: Optional[bool]) -> None:
    if assinatura is None:
        raise PoliticaComunicacaoError("assinatura deve ser informada explicitamente como SIM ou NÃO")
    if comprovante is None:
        raise PoliticaComunicacaoError("comprovante deve ser informado explicitamente como SIM ou NÃO")
    if not isinstance(assinatura, bool) or not isinstance(comprovante, bool):
        raise PoliticaComunicacaoError("assinatura e comprovante devem ser booleanos")


def _composicao_separada(tem_texto: bool, itens: Sequence[ItemComunicacao]) -> Tuple[PassoComposicao, ...]:
    passos = []
    if tem_texto:
        passos.append(PassoComposicao(tipo="texto", nome="mensagem"))
    passos.extend(PassoComposicao(tipo=item.tipo, nome=item.nome) for item in itens)
    return tuple(passos)


def _composicao_compacta(tem_texto: bool, itens: Sequence[ItemComunicacao]) -> Tuple[PassoComposicao, ...]:
    if not tem_texto:
        return tuple(PassoComposicao(tipo=item.tipo, nome=item.nome) for item in itens)

    indice_legenda = next((i for i, item in enumerate(itens) if item.tipo in _TIPOS_COM_LEGENDA), None)
    if indice_legenda is None:
        return _composicao_separada(tem_texto, itens)

    passos = []
    for i, item in enumerate(itens):
        passos.append(PassoComposicao(
            tipo=item.tipo,
            nome=item.nome,
            usa_texto_como_legenda=(i == indice_legenda),
        ))
    return tuple(passos)


def _gerar_preview_id(payload: dict) -> str:
    canonico = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonico.encode("utf-8")).hexdigest()


def hash_texto_comunicacao(texto: str) -> str:
    """Hash canônico do texto efetivo exibido/autorizado na prévia."""
    return sha256((texto or "").strip().encode("utf-8")).hexdigest()


def montar_preview_comunicacao(
    *,
    destinatarios: Iterable[str],
    texto: str = "",
    itens: Sequence[ItemComunicacao] = (),
    assinatura: Optional[bool],
    comprovante: Optional[bool],
    preferencia: PreferenciaComposicao = "otimizar",
) -> PreviewComunicacao:
    """Monta a prévia obrigatória de uma campanha sem realizar I/O.

    ``preferencia='otimizar'`` incorpora o texto como legenda do primeiro item
    compatível (vídeo/documento/imagem), reduzindo uma notificação quando
    possível. ``preferencia='separado'`` preserva a escolha do operador, mas a
    prévia continua exibindo a alternativa compacta.
    """
    _validar_opcoes_explicitas(assinatura, comprovante)
    if preferencia not in ("otimizar", "separado"):
        raise PoliticaComunicacaoError("preferencia deve ser 'otimizar' ou 'separado'")

    dests = _normalizar_destinatarios(destinatarios)
    texto_limpo = (texto or "").strip()
    texto_sha256 = hash_texto_comunicacao(texto_limpo)
    itens_tupla = tuple(itens)
    if not texto_limpo and not itens_tupla:
        raise PoliticaComunicacaoError("a campanha precisa ter texto ou ao menos um item")

    separada = _composicao_separada(bool(texto_limpo), itens_tupla)
    compacta = _composicao_compacta(bool(texto_limpo), itens_tupla)
    escolhida = compacta if preferencia == "otimizar" else separada
    alternativa = len(compacta) < len(escolhida)

    payload_id = {
        "destinatarios": dests,
        "texto_sha256": texto_sha256,
        "itens": [(i.tipo, i.nome) for i in itens_tupla],
        "assinatura": assinatura,
        "comprovante": comprovante,
        "preferencia": preferencia,
        "composicao": [(p.tipo, p.nome, p.usa_texto_como_legenda) for p in escolhida],
    }
    preview_id = _gerar_preview_id(payload_id)

    por_pessoa = len(escolhida)
    otimizado_por_pessoa = len(compacta)
    return PreviewComunicacao(
        destinatarios=dests,
        tem_texto=bool(texto_limpo),
        texto_sha256=texto_sha256,
        itens=itens_tupla,
        assinatura=assinatura,
        comprovante=comprovante,
        preferencia=preferencia,
        composicao_solicitada=escolhida,
        composicao_otimizada=compacta,
        mensagens_por_pessoa=por_pessoa,
        total_notificacoes=por_pessoa * len(dests),
        mensagens_otimizadas_por_pessoa=otimizado_por_pessoa,
        total_otimizado=otimizado_por_pessoa * len(dests),
        alternativa_mais_compacta=alternativa,
        alerta_fragmentacao=por_pessoa >= 3,
        preview_id=preview_id,
    )


def validar_autorizacao_disparo(
    *,
    preview: Optional[PreviewComunicacao],
    preview_id_autorizado: Optional[str],
    autorizacao_explicita: bool,
) -> None:
    """Gate final: exige a prévia atual e autorização posterior a ela.

    O identificador vincula a autorização à composição exibida; mudar
    destinatário, conteúdo, política de evidência ou forma de composição gera
    outro ``preview_id`` e exige nova aprovação.
    """
    if preview is None:
        raise PreviewObrigatorioError("disparo de campanha exige prévia")
    if not autorizacao_explicita:
        raise AutorizacaoObrigatoriaError("disparo real exige autorização explícita após a prévia")
    if not preview_id_autorizado or preview_id_autorizado != preview.preview_id:
        raise AutorizacaoObrigatoriaError("a autorização não corresponde à prévia atual")
