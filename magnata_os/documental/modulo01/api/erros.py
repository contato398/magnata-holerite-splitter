"""
Hierarquia de erros da API de esteira (Modulo 01, Fase 4).

Todo erro que um handler (handlers.py) pode levantar de proposito herda
de ApiError -- cada um carrega um `codigo` estavel (para o cliente da
API decidir o que fazer programaticamente, sem parsear mensagem) e um
`status_http` sugerido (o adapter web futuro decide se usa ou nao).

`tratar_erro_para_resposta()` e o unico lugar que converte QUALQUER
excecao (ApiError ou nao) em ErroApiResponse -- e a fronteira que
garante que nenhum detalhe tecnico sensivel (stacktrace, mensagem de
excecao de infraestrutura, nome de tabela, path de arquivo) escapa para
fora da API: uma excecao que NAO e ApiError vira sempre o mesmo
ErroInternoNaoExposto, com a mesma mensagem generica, independente do
que a excecao original dizia.
"""
from __future__ import annotations

from typing import Optional

from .contratos import ErroApiResponse


class ApiError(Exception):
    """Erro de API com identidade estavel. `mensagem` PRECISA ser segura
    para mostrar ao usuario final -- nunca construa uma ApiError a partir
    de `str(excecao_interna)` sem revisar o texto primeiro."""

    codigo: str = 'ERRO_API'
    status_http: int = 400

    def __init__(self, mensagem: str, detalhes: Optional[dict] = None) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhes = detalhes


class DocumentoNaoEncontrado(ApiError):
    codigo = 'DOCUMENTO_NAO_ENCONTRADO'
    status_http = 404


class LoteNaoEncontrado(ApiError):
    codigo = 'LOTE_NAO_ENCONTRADO'
    status_http = 404


class FiltroInvalido(ApiError):
    codigo = 'FILTRO_INVALIDO'
    status_http = 400


class OrdenacaoInvalida(ApiError):
    codigo = 'ORDENACAO_INVALIDA'
    status_http = 400


class PaginacaoInvalida(ApiError):
    codigo = 'PAGINACAO_INVALIDA'
    status_http = 400


class PermissaoNegada(ApiError):
    """Sujeito autenticado (ver autorizacao.py -- sem autenticacao REAL
    nesta fase, so o perfil declarado) sem permissao para a consulta."""

    codigo = 'PERMISSAO_NEGADA'
    status_http = 403


class ErroInternoNaoExposto(ApiError):
    """Qualquer falha inesperada (bug, repositorio indisponivel, etc.)
    -- a mensagem exposta e SEMPRE generica, nunca a mensagem da
    excecao original. Quem precisar investigar usa a excecao original
    encadeada via `raise ... from exc` (visivel em logs/stacktrace do
    processo, nunca na resposta da API)."""

    codigo = 'ERRO_INTERNO'
    status_http = 500


MENSAGEM_ERRO_INTERNO_PADRAO = 'Erro interno ao processar a consulta. Tente novamente mais tarde.'


def tratar_erro_para_resposta(excecao: Exception) -> ErroApiResponse:
    """
    Converte qualquer excecao em ErroApiResponse. Unico ponto de
    conversao usado pelos handlers (via o decorator `proteger_erros`
    em handlers.py) -- garante que uma excecao nao prevista (nao
    ApiError) nunca vaza `str(excecao)` para o cliente da API.
    """
    if isinstance(excecao, ApiError):
        return ErroApiResponse(codigo=excecao.codigo, mensagem=excecao.mensagem, detalhes=excecao.detalhes)

    return ErroApiResponse(
        codigo=ErroInternoNaoExposto.codigo,
        mensagem=MENSAGEM_ERRO_INTERNO_PADRAO,
        detalhes=None,
    )
