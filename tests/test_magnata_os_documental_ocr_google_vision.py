import logging

import pytest

from _pdf_sintetico import pdf_com_paginas
from magnata_os.documental.ocr import extrair_paginas_com_ocr
from magnata_os.documental.ocr_google_vision import (
    ConfiguracaoGoogleVisionAusente,
    MotorOcrGoogleVision,
    URL_FILES_ANNOTATE,
    ler_chave_google_vision,
)

CHAVE_FALSA = 'chave-de-teste-nunca-real-000111'


class _RespostaFalsa:
    def __init__(self, status_code=200, corpo=None):
        self.status_code = status_code
        self._corpo = corpo or {}

    def json(self):
        return self._corpo


def _corpo_ok(*textos_por_pagina):
    return {'responses': [{'responses': [{'fullTextAnnotation': {'text': t}} for t in textos_por_pagina]}]}


class _ClienteHttpFake:
    """Nunca faz rede -- grava as chamadas e devolve respostas programadas."""

    def __init__(self, respostas=None, excecao=None):
        self.chamadas = []
        self._respostas = list(respostas or [])
        self._excecao = excecao

    def post(self, url, *, params, json, timeout):
        self.chamadas.append({'url': url, 'params': dict(params), 'json': json, 'timeout': timeout})
        if self._excecao is not None:
            raise self._excecao
        return self._respostas.pop(0)


# ---------------------------------------------------------------------------
# ler_chave_google_vision
# ---------------------------------------------------------------------------

def test_ler_chave_ausente_levanta_configuracao_ausente():
    with pytest.raises(ConfiguracaoGoogleVisionAusente):
        ler_chave_google_vision(ambiente={})


def test_ler_chave_em_branco_levanta_configuracao_ausente():
    valor_so_espacos = ' ' * 3
    with pytest.raises(ConfiguracaoGoogleVisionAusente):
        ler_chave_google_vision(ambiente={'GOOGLE_VISION_API_KEY': valor_so_espacos})


def test_ler_chave_presente_devolve_valor():
    assert ler_chave_google_vision(ambiente={'GOOGLE_VISION_API_KEY': CHAVE_FALSA}) == CHAVE_FALSA


# ---------------------------------------------------------------------------
# Sem chave configurada: nunca chama rede, sinaliza claramente
# ---------------------------------------------------------------------------

def test_sem_chave_nunca_chama_rede_e_sinaliza_via_excecao_tipada():
    cliente = _ClienteHttpFake()
    motor = MotorOcrGoogleVision(cliente_http=cliente, ambiente={})

    with pytest.raises(ConfiguracaoGoogleVisionAusente):
        motor.extrair_paginas(pdf_com_paginas(['']))

    assert cliente.chamadas == []


def test_sem_chave_via_extrair_paginas_com_ocr_marca_ocr_falhou_sem_excecao_subir(caplog):
    """Contrato já existente de ocr.py: falha do motor -> ocr_falhou=True,
    extração normal preservada, nunca exceção não tratada para quem chama
    extrair_paginas_com_ocr."""
    cliente = _ClienteHttpFake()
    motor = MotorOcrGoogleVision(cliente_http=cliente, ambiente={})

    extracao = extrair_paginas_com_ocr(pdf_com_paginas(['']), motor)

    assert extracao.ocr_falhou is True
    assert cliente.chamadas == []
    assert 'GOOGLE_VISION_API_KEY' not in caplog.text


# ---------------------------------------------------------------------------
# Com chave: chamada certa, tradução certa
# ---------------------------------------------------------------------------

def test_com_chave_faz_a_chamada_certa_e_traduz_a_resposta():
    cliente = _ClienteHttpFake(respostas=[_RespostaFalsa(200, _corpo_ok('texto pagina 1 via OCR real'))])
    motor = MotorOcrGoogleVision(cliente_http=cliente, ambiente={'GOOGLE_VISION_API_KEY': CHAVE_FALSA})

    textos = motor.extrair_paginas(pdf_com_paginas(['']))

    assert textos == ('texto pagina 1 via OCR real',)
    assert len(cliente.chamadas) == 1
    chamada = cliente.chamadas[0]
    assert chamada['url'] == URL_FILES_ANNOTATE
    assert chamada['params'] == {'key': CHAVE_FALSA}
    requisicao = chamada['json']['requests'][0]
    assert requisicao['inputConfig']['mimeType'] == 'application/pdf'
    assert requisicao['features'] == [{'type': 'DOCUMENT_TEXT_DETECTION'}]
    assert requisicao['pages'] == [1]
    assert isinstance(requisicao['inputConfig']['content'], str)


def test_com_chave_integra_com_extrair_paginas_com_ocr_e_substitui_pagina_deficiente():
    conteudo = pdf_com_paginas(['RECIBO texto normal suficiente para nao precisar de ocr', ''])
    cliente = _ClienteHttpFake(respostas=[
        _RespostaFalsa(200, _corpo_ok('nao deveria ser usada', 'texto reconhecido por OCR real da pagina 2 com bastante conteudo util')),
    ])
    motor = MotorOcrGoogleVision(cliente_http=cliente, ambiente={'GOOGLE_VISION_API_KEY': CHAVE_FALSA})

    extracao = extrair_paginas_com_ocr(conteudo, motor)

    assert extracao.paginas_por_ocr == (1,)
    assert 'OCR real da pagina 2' in extracao.paginas[1]
    assert extracao.ocr_falhou is False


def test_pdf_com_mais_de_5_paginas_agrupa_em_blocos_de_ate_5():
    conteudo = pdf_com_paginas([''] * 7)
    cliente = _ClienteHttpFake(respostas=[
        _RespostaFalsa(200, _corpo_ok(*[f'pagina {i}' for i in range(1, 6)])),
        _RespostaFalsa(200, _corpo_ok('pagina 6', 'pagina 7')),
    ])
    motor = MotorOcrGoogleVision(cliente_http=cliente, ambiente={'GOOGLE_VISION_API_KEY': CHAVE_FALSA})

    textos = motor.extrair_paginas(conteudo)

    assert len(cliente.chamadas) == 2
    assert cliente.chamadas[0]['json']['requests'][0]['pages'] == [1, 2, 3, 4, 5]
    assert cliente.chamadas[1]['json']['requests'][0]['pages'] == [6, 7]
    assert textos == tuple(f'pagina {i}' for i in range(1, 8))


# ---------------------------------------------------------------------------
# Erro de rede/timeout: tratado sem propagar
# ---------------------------------------------------------------------------

def test_erro_de_rede_nao_propaga_e_pagina_afetada_fica_vazia(caplog):
    caplog.set_level(logging.ERROR)
    cliente = _ClienteHttpFake(excecao=TimeoutError('tempo esgotado'))
    motor = MotorOcrGoogleVision(cliente_http=cliente, ambiente={'GOOGLE_VISION_API_KEY': CHAVE_FALSA})

    textos = motor.extrair_paginas(pdf_com_paginas(['']))

    assert textos == ('',)
    assert CHAVE_FALSA not in caplog.text


def test_erro_de_rede_via_extrair_paginas_com_ocr_nunca_sobe_excecao_e_mantem_extracao_normal():
    """Erro de rede é isolado DENTRO do motor (nunca propaga) -- ocr.py
    nem chega a ver exceção; `ocr_falhou` continua False porque o motor
    devolveu, com sucesso, texto vazio (nunca inventado) para a página
    afetada, que nunca supera a extração normal (também vazia aqui)."""
    cliente = _ClienteHttpFake(excecao=ConnectionError('sem rede'))
    motor = MotorOcrGoogleVision(cliente_http=cliente, ambiente={'GOOGLE_VISION_API_KEY': CHAVE_FALSA})

    extracao = extrair_paginas_com_ocr(pdf_com_paginas(['']), motor)

    assert extracao.ocr_falhou is False
    assert extracao.paginas_por_ocr == ()
    assert extracao.paginas == ('',)
    assert extracao.paginas_sem_texto == (0,)


# ---------------------------------------------------------------------------
# Resposta malformada: tratada sem quebrar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('resposta', [
    _RespostaFalsa(200, {}),
    _RespostaFalsa(200, {'responses': []}),
    _RespostaFalsa(200, {'responses': [{'responses': []}]}),
    _RespostaFalsa(200, {'responses': [{'responses': [{'fullTextAnnotation': {'text': 'a'}}, {'fullTextAnnotation': {'text': 'b'}}]}]}),
    _RespostaFalsa(403, {'error': {'message': 'API key not valid'}}),
    _RespostaFalsa(429, {'error': {'message': 'rate limit'}}),
])
def test_resposta_malformada_ou_erro_da_api_nao_quebra_e_pagina_fica_vazia(resposta):
    cliente = _ClienteHttpFake(respostas=[resposta])
    motor = MotorOcrGoogleVision(cliente_http=cliente, ambiente={'GOOGLE_VISION_API_KEY': CHAVE_FALSA})

    textos = motor.extrair_paginas(pdf_com_paginas(['']))

    assert textos == ('',)


# ---------------------------------------------------------------------------
# Nenhuma chave em log/erro nunca
# ---------------------------------------------------------------------------

def test_chave_nunca_aparece_em_mensagem_de_excecao(caplog):
    caplog.set_level(logging.ERROR)
    cliente = _ClienteHttpFake(excecao=RuntimeError('falha qualquer'))
    motor = MotorOcrGoogleVision(cliente_http=cliente, ambiente={'GOOGLE_VISION_API_KEY': CHAVE_FALSA})

    try:
        motor.extrair_paginas(pdf_com_paginas(['']))
    except Exception as exc:  # não deveria propagar, mas garante que nem a excecao carrega a chave
        assert CHAVE_FALSA not in str(exc)

    assert CHAVE_FALSA not in caplog.text
