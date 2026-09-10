"""Adapter concreto de `PortaTransporteWhatsapp` sobre o transporte Evolution
já existente em `app.py` (`_evolution_enviar_texto/video/documento`).

Este é o único lugar do pacote `adapters/` autorizado a conhecer a
taxonomia de exceções de `requests` -- é exatamente o seu trabalho:
traduzir falhas de rede reais na classificação conservadora exigida pela
missão (matriz Evolution). O domínio (`transporte_comunicacao.py`,
`executor_persistente_fake.py`, `wiring_*`) nunca vê `requests` nem sabe
que existe HTTP.

Reaproveita 100% do cliente Evolution já testado em `app.py` via
callables injetadas -- nunca importa `app` diretamente (evitaria acoplar
o domínio ao Flask/Airtable carregados por aquele módulo) e nunca
duplica autenticação/endpoint/payload.
"""
from __future__ import annotations

import base64
import dataclasses
import re
from typing import Callable, Optional

import requests
import requests.exceptions
import urllib3.exceptions

from ..classificador_falha import FalhaEnvioIncerto, FalhaTransitoria

# Assinaturas esperadas das callables injetadas -- espelham exatamente
# app.py:_evolution_enviar_texto/_evolution_enviar_video/_evolution_enviar_documento.
EnviarTexto = Callable[[str, str], dict]
EnviarVideo = Callable[..., dict]
EnviarDocumento = Callable[..., dict]

_PADRAO_HTTP_STATUS = re.compile(r'Evolution HTTP (\d{3})')


def _status_do_runtime_error(exc: RuntimeError) -> Optional[int]:
    """Extrai o status HTTP já embutido na mensagem do RuntimeError legado.

    `_evolution_enviar_*` levanta `RuntimeError(f'Evolution HTTP {status}...')`
    para qualquer resposta fora de 2xx, sem distinguir 4xx de 5xx na própria
    exceção -- a informação existe, só está em texto. Extrair por regex é
    frágil ao formato exato da mensagem legada, mas evita duplicar ou
    reescrever o cliente Evolution só para expor o status como atributo.
    Se o formato mudar sem essa extração acompanhar, o fail-safe abaixo
    (nenhum grupo casado) já trata como ENVIO_EXTERNO_INCERTO, nunca como
    seguro para retry.
    """
    casado = _PADRAO_HTTP_STATUS.search(str(exc))
    return int(casado.group(1)) if casado else None


def _falha_de_pre_conexao(exc: requests.exceptions.ConnectionError) -> bool:
    """True somente quando a causa encadeada prova que a conexão TCP nunca
    foi estabelecida (DNS inacessível, conexão recusada) -- a única forma
    de ConnectionError em que a biblioteca (`urllib3`) expõe, por tipo de
    exceção, prova de que nenhum byte da requisição saiu.

    Qualquer outro caso de ConnectionError (reset após conectar, conexão
    interrompida no meio da transmissão) NÃO tem essa prova disponível no
    cliente HTTP atual -- declarado aqui explicitamente, não presumido: o
    `requests`/`urllib3` não expõem se o corpo já havia sido total ou
    parcialmente escrito no socket no momento do reset.
    """
    causa = exc.args[0] if exc.args else None
    return isinstance(causa, urllib3.exceptions.NewConnectionError)


def _classificar_e_relancar(exc: Exception) -> None:
    """Aplica a matriz conservadora da missão e relança a exceção correta
    do vocabulário do Orquestrador. Nunca deixa uma exceção de `requests`
    vazar para fora do adapter."""
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        # Por definição da biblioteca: o handshake TCP não completou a
        # tempo -- nenhum byte do corpo da requisição foi transmitido.
        raise FalhaTransitoria('timeout de conexão antes de qualquer envio') from exc
    if isinstance(exc, requests.exceptions.ReadTimeout):
        # Conexão estabelecida e corpo enviado; só a resposta está
        # ausente -- a Evolution pode já ter processado a mensagem.
        raise FalhaEnvioIncerto('timeout de leitura após envio do corpo') from exc
    if isinstance(exc, requests.exceptions.ConnectionError):
        if _falha_de_pre_conexao(exc):
            raise FalhaTransitoria('conexão recusada ou host inacessível antes do envio') from exc
        raise FalhaEnvioIncerto(
            'conexão interrompida sem prova de que a requisição não saiu'
        ) from exc
    if isinstance(exc, RuntimeError):
        status = _status_do_runtime_error(exc)
        if status is not None and 400 <= status < 500:
            # Round-trip completo; por convenção HTTP padrão (não
            # comprovada especificamente contra o comportamento real da
            # Evolution) 4xx é rejeição síncrona antes do processamento.
            # Mesmo payload repetiria o erro -- defeito nosso, não retry.
            raise ValueError(f'Evolution rejeitou a requisição ({status})') from exc
        # 5xx, status não extraído, ou qualquer outro RuntimeError: receber
        # uma resposta de erro NÃO prova ausência de side effect -- a
        # Evolution pode ter despachado a mensagem e falhado só ao montar
        # a resposta. Fail-safe: incerto, nunca seguro.
        raise FalhaEnvioIncerto(f'Evolution retornou erro: {exc}') from exc
    if isinstance(exc, (ValueError, requests.exceptions.JSONDecodeError)):
        # 2xx recebido (a Evolution aceitou) mas o corpo não é JSON válido
        # -- falha é só de parsing do nosso lado, depois do side effect
        # provável.
        raise FalhaEnvioIncerto(f'resposta 2xx com corpo inválido: {exc}') from exc
    # Exceção de rede não mapeada explicitamente (ex.: exceção após o
    # envio do body, em qualquer ponto não coberto acima): fail-safe
    # conservador, nunca tratada como segura para retry automático.
    raise FalhaEnvioIncerto(f'falha não classificada no transporte: {exc}') from exc


@dataclasses.dataclass(frozen=True)
class TransporteEvolutionLegado:
    """Implementa `PortaTransporteWhatsapp` sobre o cliente Evolution já
    existente em `app.py`, recebido por injeção (nunca importado)."""

    enviar_texto_legado: EnviarTexto
    enviar_video_legado: EnviarVideo
    enviar_documento_legado: EnviarDocumento

    def enviar_texto(self, *, numero: str, texto: str) -> object:
        try:
            return self.enviar_texto_legado(numero, texto)
        except Exception as exc:
            _classificar_e_relancar(exc)

    def enviar_video(self, *, numero: str, conteudo: object,
                      nome_arquivo: str, legenda: str = '') -> object:
        video_base64 = base64.b64encode(bytes(conteudo)).decode('ascii')
        try:
            return self.enviar_video_legado(numero, video_base64, nome_arquivo, legenda=legenda)
        except Exception as exc:
            _classificar_e_relancar(exc)

    def enviar_documento(self, *, numero: str, conteudo: object,
                          nome_arquivo: str, legenda: str = '') -> object:
        try:
            return self.enviar_documento_legado(
                numero, None, nome_arquivo,
                caption=(legenda or None), media_bytes=bytes(conteudo),
            )
        except Exception as exc:
            _classificar_e_relancar(exc)
