"""
Módulo 01 (Ingestão) — Fase 0: Observabilidade do fluxo legado.

Mede o que já acontece hoje nas rotas de upload documental (ex.: /separar),
sem alterar resposta HTTP, corpo, estado do Airtable ou qualquer regra de
negócio existente. Ver MAGNATA_OS_MODULO_01_FASE_0_OBSERVABILIDADE.md.

Princípios aplicados (Manifesto, Auditoria Obrigatória; Erros Explícitos):
  - Nenhuma falha deste módulo pode alterar o retorno da rota instrumentada
    — todo bloco que não seja estritamente necessário para decidir CHAMAR
    a view function original está protegido por try/except que apenas
    registra e segue.
  - Nenhum dado sensível (token, header de autorização, conteúdo do
    arquivo, CPF, telefone) é registrado.
  - O identificador de correlação gerado aqui é só observacional — não é
    identidade canônica persistida (essa continuará vindo de UUIDv7 em
    entidades futuras, DEC-MOD01-011; este módulo não gera nem depende de
    UUIDv7).

Ativação: variável de ambiente MAGNATA_INGESTION_OBSERVABILITY_ENABLED.
Padrão: ativado (é o objetivo desta Fase — medir o que já acontece).
"""

import functools
import json
import logging
import os
import re
import secrets
import time

logger = logging.getLogger('ingestion.observability')

ENV_FLAG_OBSERVABILIDADE = 'MAGNATA_INGESTION_OBSERVABILITY_ENABLED'

_VALORES_DESATIVA = {'0', 'false', 'no', 'off', 'nao', 'não'}

_NOME_ARQUIVO_INSEGURO = re.compile(r'[^A-Za-z0-9._-]+')


def is_observability_enabled() -> bool:
    """Lê a flag de observabilidade. Padrão seguro: ativada."""
    valor = os.environ.get(ENV_FLAG_OBSERVABILIDADE, 'true').strip().lower()
    return valor not in _VALORES_DESATIVA


def nome_arquivo_seguro(nome: str, limite: int = 80) -> str:
    """Sanitiza um nome de arquivo para uso seguro em log (nunca em disco)."""
    if not nome:
        return '(sem nome)'
    limpo = _NOME_ARQUIVO_INSEGURO.sub('_', nome)
    return limpo[:limite]


def _extensao(nome: str) -> str:
    if not nome or '.' not in nome:
        return ''
    return nome.rsplit('.', 1)[-1].lower()


def _novo_correlation_id() -> str:
    # Observacional apenas — não é identidade canônica persistida.
    return f"obs{secrets.token_hex(8)}"


def _correlation_id_da_requisicao(req):
    existente = req.headers.get('X-Request-ID') or req.headers.get('X-Correlation-ID')
    if existente:
        return existente, True
    return _novo_correlation_id(), False


def _classificar_resultado(status_http, corpo_json):
    """
    Classificação observacional do resultado de uma chamada instrumentada.

    Valores: sucesso_real | falha_funcional_http_200 | falha_http |
    resultado_incerto.

    Não corrige nem mascara o comportamento atual — só nomeia o que já
    acontece (ex.: HTTP 200 com success=false em /separar).
    """
    corpo_valido = isinstance(corpo_json, dict)
    success = corpo_json.get('success') if corpo_valido else None

    if status_http == 200 and corpo_valido and success is False:
        return 'falha_funcional_http_200'
    if status_http in (200, 202) and corpo_valido and success is True:
        return 'sucesso_real'
    if status_http not in (200, 202):
        return 'falha_http'
    return 'resultado_incerto'


def _log_json(nome_evento: str, campos: dict) -> None:
    try:
        payload = {'evento': nome_evento}
        payload.update(campos)
        logger.info('ingestion_observability %s', json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        # A observabilidade nunca pode, ela própria, quebrar a requisição.
        logger.warning('[OBS] falha ao serializar log de observabilidade', exc_info=True)


def observar_ingestao(nome_rota: str):
    """
    Decorator de observabilidade para rotas de ingestão documental.

    Uso:
        @app.route('/separar', methods=['POST'])
        @observar_ingestao('/separar')
        def separar():
            ...

    Nunca altera o valor retornado pela view nem impede que uma exceção
    real se propague — só observa em volta dela.
    """
    def decorador(view_func):
        @functools.wraps(view_func)
        def wrapper(*args, **kwargs):
            if not is_observability_enabled():
                return view_func(*args, **kwargs)

            try:
                from flask import request as flask_request
            except Exception:
                # Sem Flask disponível, não há o que observar — chama direto.
                return view_func(*args, **kwargs)

            inicio = time.monotonic()
            correlation_id = None
            try:
                correlation_id, correlation_preexistente = _correlation_id_da_requisicao(flask_request)

                arquivo_nome = ''
                arquivo_mime = ''
                quantidade_arquivos = 0
                if flask_request.files:
                    quantidade_arquivos = len(flask_request.files)
                    primeiro = next(iter(flask_request.files.values()), None)
                    if primeiro is not None:
                        arquivo_nome = nome_arquivo_seguro(primeiro.filename or '')
                        arquivo_mime = primeiro.content_type or ''

                _log_json('inicio', {
                    'rota': nome_rota,
                    'metodo': flask_request.method,
                    'correlation_id': correlation_id,
                    'correlation_preexistente': correlation_preexistente,
                    'arquivo_nome': arquivo_nome,
                    'arquivo_mime_informado': arquivo_mime,
                    'arquivo_extensao': _extensao(arquivo_nome),
                    'quantidade_arquivos': quantidade_arquivos,
                    'tamanho_bytes_content_length': flask_request.content_length,
                })
            except Exception:
                logger.warning('[OBS] falha ao registrar início da observação', exc_info=True)

            try:
                resultado = view_func(*args, **kwargs)
            except Exception as exc:
                try:
                    duracao_ms = round((time.monotonic() - inicio) * 1000, 1)
                    _log_json('excecao', {
                        'rota': nome_rota,
                        'correlation_id': correlation_id,
                        'duracao_ms': duracao_ms,
                        'excecao_tipo': type(exc).__name__,
                    })
                except Exception:
                    logger.warning('[OBS] falha ao registrar exceção observada', exc_info=True)
                raise

            try:
                _registrar_fim(nome_rota, correlation_id, inicio, resultado)
            except Exception:
                logger.warning('[OBS] falha ao registrar fim da observação', exc_info=True)

            return resultado
        return wrapper
    return decorador


def _registrar_fim(nome_rota, correlation_id, inicio, resultado):
    duracao_ms = round((time.monotonic() - inicio) * 1000, 1)

    status_http = 200
    response_obj = resultado
    if isinstance(resultado, tuple) and len(resultado) >= 2:
        response_obj, status_http = resultado[0], resultado[1]

    corpo_json = None
    try:
        corpo_json = response_obj.get_json(silent=True)
    except Exception:
        corpo_json = None

    classificacao = _classificar_resultado(status_http, corpo_json)
    success_corpo = corpo_json.get('success') if isinstance(corpo_json, dict) else None
    codigo_erro = corpo_json.get('error_code') if isinstance(corpo_json, dict) else None
    registro_referenciado = (
        corpo_json.get('processar_arquivo_record_id') if isinstance(corpo_json, dict) else None
    )

    _log_json('fim', {
        'rota': nome_rota,
        'correlation_id': correlation_id,
        'duracao_ms': duracao_ms,
        'status_http': status_http,
        'success_corpo': success_corpo,
        'codigo_erro': codigo_erro,
        'registro_referenciado': registro_referenciado,
        'classificacao_observacional': classificacao,
    })
