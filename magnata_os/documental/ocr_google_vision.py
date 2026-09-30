"""Motor OCR real: Google Cloud Vision API REST (`files:annotate`).

Decisão de negócio (operador, registrada em
`docs/decisoes/ocr-motor-google-vision-v1.md`): Google Cloud Vision,
autenticado por Chave de API (não conta de serviço -- criação de chave
de conta de serviço é bloqueada por política de segurança da
organização), configurada como `GOOGLE_VISION_API_KEY` no Render.

Implementa a porta `MotorOcr` (`magnata_os/documental/ocr.py`) --
MESMA assinatura (`extrair_paginas(conteudo_pdf: bytes) ->
Tuple[str, ...]`), sem alterar a porta.

Endpoint escolhido: `files:annotate`, NÃO `images:annotate` -- desvio
deliberado da menção literal na missão, decisão técnica registrada
(ver docs/decisoes/ocr-motor-google-vision-v1.md, "Escolha de
endpoint"): `images:annotate` espera uma imagem rasterizada por
requisição (JPEG/PNG/...); este repositório não tem biblioteca de
conversão PDF -> imagem (nem PyMuPDF, nem pdf2image/poppler) e somar
uma é dependência de sistema nova, fora do escopo desta missão.
`files:annotate` aceita o PDF inteiro (bytes) inline via
`inputConfig.content` (base64) com `mimeType: application/pdf` e
devolve texto por página -- exatamente o formato que `MotorOcr.
extrair_paginas` já precisa (bytes -> texto por página), sem nenhuma
conversão. Limite conhecido da API: no máximo 5 páginas por
`AnnotateFileRequest` síncrono -- o motor agrupa em blocos de até 5
dentro do MESMO corpo HTTP (`requests: [...]`), então um PDF maior
ainda sai como poucas chamadas HTTP, nunca uma por página.

Chave: lida de `GOOGLE_VISION_API_KEY` só no momento do uso (nunca no
import do módulo, nunca cacheada em nível de módulo, nunca logada --
nem parcialmente). Ausente -> `ConfiguracaoGoogleVisionAusente` (mesmo
padrão de `ConfiguracaoBancoAusente` em
`modulo01/adapters/conexao.py`) -- fail-closed: o motor nunca finge
que fez OCR nem inventa texto. `extrair_paginas_com_ocr` (ocr.py) já
captura qualquer exceção do motor num `except Exception` genérico e
marca `ocr_falhou=True`/mantém a extração normal -- essa exceção É o
sinal esperado por esse contrato, não um caso não tratado.

Erro de rede, timeout ou resposta malformada da API DURANTE uma
tentativa real (categoria diferente de "chave ausente" -- aqui a
tentativa foi feita) nunca propaga para quem chamou `extrair_paginas`:
fica isolado por bloco de páginas (mesma disciplina de
`orquestrador/coleta_fontes_externas_v1.py` -- falha de uma parte não
derruba o resto), registrado em log (nunca com a chave, nunca com a
query string) e as páginas daquele bloco voltam como texto vazio --
nunca texto inventado. Como `extrair_paginas_com_ocr` só aceita OCR
quando ele devolve MAIS texto que a extração normal, texto vazio nunca
piora o resultado.

Cliente HTTP é injetável (`ClienteHttp`, interface mínima com um único
método `post`) -- nenhum teste deste módulo faz chamada de rede real;
a implementação real usa `requests` (já em requirements.txt), import
local dentro da fábrica do cliente default, só quando o motor real
precisa de fato enviar uma chamada.
"""
from __future__ import annotations

import base64
import io
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional, Protocol, Tuple

_logger = logging.getLogger(__name__)

URL_FILES_ANNOTATE = 'https://vision.googleapis.com/v1/files:annotate'
MIME_TYPE_PDF = 'application/pdf'
FEATURE_DOCUMENT_TEXT_DETECTION = 'DOCUMENT_TEXT_DETECTION'
MAXIMO_PAGINAS_POR_REQUISICAO = 5  # limite síncrono da Vision API (files:annotate)
TIMEOUT_PADRAO_SEGUNDOS = 30.0

EVENTO_OCR_GOOGLE_VISION_BLOCO_FALHOU = 'ocr_google_vision_bloco_falhou'


class ConfiguracaoGoogleVisionAusente(Exception):
    """GOOGLE_VISION_API_KEY não definida (ou vazia) no ambiente."""


class RespostaHttp(Protocol):
    status_code: int

    def json(self) -> Any:
        ...


class ClienteHttp(Protocol):
    def post(self, url: str, *, params: dict, json: dict, timeout: float) -> RespostaHttp:
        ...


def ler_chave_google_vision(ambiente: Optional[dict] = None) -> str:
    """Lê e valida `GOOGLE_VISION_API_KEY`. `ambiente` injetável para
    teste (default: `os.environ` real). Levanta
    `ConfiguracaoGoogleVisionAusente` se ausente/vazia -- nunca devolve
    string vazia silenciosamente, nunca inventa chave."""
    fonte = ambiente if ambiente is not None else os.environ
    valor = (fonte.get('GOOGLE_VISION_API_KEY') or '').strip()
    if not valor:
        raise ConfiguracaoGoogleVisionAusente(
            'GOOGLE_VISION_API_KEY nao configurada -- o motor real de OCR '
            '(Google Cloud Vision) requer essa variavel de ambiente (ver '
            'docs/decisoes/ocr-motor-google-vision-v1.md). Nenhum OCR real '
            'e feito sem ela.'
        )
    return valor


class _ClienteRequests:
    """Adapter fino sobre `requests.post` -- único ponto deste módulo que
    importa `requests`, e só quando de fato instanciado (nunca no import
    do módulo, nunca em teste)."""

    def post(self, url: str, *, params: dict, json: dict, timeout: float) -> RespostaHttp:
        import requests  # import local -- mesmo padrão de conexao.py/psycopg

        return requests.post(url, params=params, json=json, timeout=timeout)


def _contar_paginas(conteudo_pdf: bytes) -> int:
    """Conta páginas via `pypdf` (já em requirements.txt) -- só para saber
    em quantos blocos de até 5 dividir as requisições e para devolver a
    MESMA contagem que `paginas` (ocr.py rejeita contagem desalinhada)."""
    from pypdf import PdfReader

    return len(PdfReader(io.BytesIO(conteudo_pdf)).pages)


def _blocos_de_paginas(
    total_paginas: int, tamanho: int = MAXIMO_PAGINAS_POR_REQUISICAO
) -> Tuple[Tuple[int, ...], ...]:
    """Índices de página 1-based agrupados em blocos de até `tamanho` --
    a Vision API (`files:annotate`) só aceita até 5 páginas por
    `AnnotateFileRequest` síncrono."""
    paginas = list(range(1, total_paginas + 1))
    return tuple(
        tuple(paginas[i : i + tamanho]) for i in range(0, len(paginas), tamanho)
    )


def _textos_por_pagina_do_bloco(
    resposta: RespostaHttp, bloco: Tuple[int, ...]
) -> Tuple[str, ...]:
    """Traduz uma resposta HTTP de `files:annotate` para texto por página
    do bloco pedido. Levanta `ValueError` para qualquer formato
    inesperado -- nunca inventa texto para preencher lacuna; quem chama
    trata isso como falha isolada do bloco."""
    status = getattr(resposta, 'status_code', None)
    if status != 200:
        raise ValueError(f'Cloud Vision respondeu status HTTP {status!r} (esperado 200).')

    corpo = resposta.json()
    respostas_arquivo = (corpo or {}).get('responses') or []
    if not respostas_arquivo:
        raise ValueError('Cloud Vision devolveu "responses" vazio/ausente no corpo.')

    paginas_resp = respostas_arquivo[0].get('responses') or []
    if len(paginas_resp) != len(bloco):
        raise ValueError(
            f'Cloud Vision devolveu {len(paginas_resp)} pagina(s) para um '
            f'bloco pedido de {len(bloco)} pagina(s) -- nao ha como alinhar '
            'com seguranca.'
        )

    return tuple(
        str((pagina_resp.get('fullTextAnnotation') or {}).get('text') or '')
        for pagina_resp in paginas_resp
    )


@dataclass(frozen=True)
class MotorOcrGoogleVision:
    """Implementa `MotorOcr` (`magnata_os/documental/ocr.py`) contra a
    Cloud Vision API REST (`files:annotate`), autenticado por Chave de
    API na query string (`key=`) -- é assim que chave de API funciona
    nessa API (sem token OAuth, sem conta de serviço).

    `cliente_http`: injetável, nunca real por padrão em teste. `None`
    usa `_ClienteRequests` (só instanciado -- `requests` só é importado
    nesse caminho, na hora do uso real).
    `ambiente`: injetável para teste (default: `os.environ` real);
    passado para `ler_chave_google_vision`.
    """

    cliente_http: Optional[ClienteHttp] = None
    ambiente: Optional[dict] = None
    timeout_segundos: float = TIMEOUT_PADRAO_SEGUNDOS

    def extrair_paginas(self, conteudo_pdf: bytes) -> Tuple[str, ...]:
        # Chave ausente: sinaliza por exceção tipada (fail-closed) -- NÃO
        # tenta rede. `extrair_paginas_com_ocr` (ocr.py) já trata
        # qualquer exceção do motor como `ocr_falhou=True`; esse é o
        # mesmo contrato, não um caso especial.
        chave = ler_chave_google_vision(self.ambiente)
        cliente = self.cliente_http if self.cliente_http is not None else _ClienteRequests()

        total_paginas = _contar_paginas(conteudo_pdf)
        if total_paginas == 0:
            return ()

        conteudo_b64 = base64.b64encode(conteudo_pdf).decode('ascii')
        textos = [''] * total_paginas

        for bloco in _blocos_de_paginas(total_paginas):
            corpo = {
                'requests': [
                    {
                        'inputConfig': {'content': conteudo_b64, 'mimeType': MIME_TYPE_PDF},
                        'features': [{'type': FEATURE_DOCUMENT_TEXT_DETECTION}],
                        'pages': list(bloco),
                    }
                ]
            }
            try:
                resposta = cliente.post(
                    URL_FILES_ANNOTATE,
                    params={'key': chave},
                    json=corpo,
                    timeout=self.timeout_segundos,
                )
                textos_bloco = _textos_por_pagina_do_bloco(resposta, bloco)
            except Exception as exc:
                # Rede/timeout/resposta malformada DEPOIS de tentar: nunca
                # propaga. Isolado por bloco (mesma disciplina de
                # coleta_fontes_externas_v1.py); nunca loga a chave (nem o
                # corpo da requisição, nem os params).
                _logger.error(
                    '%s paginas=%s erro_tipo=%s',
                    EVENTO_OCR_GOOGLE_VISION_BLOCO_FALHOU,
                    bloco,
                    type(exc).__name__,
                    extra={
                        'evento': EVENTO_OCR_GOOGLE_VISION_BLOCO_FALHOU,
                        'paginas': bloco,
                        'erro_tipo': type(exc).__name__,
                    },
                )
                continue  # bloco falho fica com texto vazio -- nunca inventado

            for pagina, texto in zip(bloco, textos_bloco):
                textos[pagina - 1] = texto

        return tuple(textos)
