"""
Macro — Pacote atômico de assinatura eletrônica: Holerite + Folha de Ponto.

Decisão arquitetural (documentada, ver comentário de TIPO_PACOTE_HOLERITE_PONTO
em app.py): Holerite nunca é assinável isolado -- só dentro deste pacote,
sempre pareado com a Folha de Ponto da MESMA competência, em uma única
solicitação/token/comprovante. Reaproveita 100% a tabela "Assinaturas
Digitais" e os 4 campos v3.6 já reais no Airtable (nenhum campo novo,
nenhuma rota nova -- extensão de /assinatura/gerar e /assinatura/<hash>).

Terminologia usada nestes testes e no código: "assinatura eletrônica com
evidências" -- nunca "assinatura digital certificada ICP-Brasil" (não há
comprovação técnica de certificado digital neste mecanismo).

100% dado sintético -- nenhum CPF/nome/telefone real em nenhum lugar deste
arquivo. IDs (recXXXX) são inventados.
"""
import hashlib
import io
from unittest.mock import Mock, patch

import pytest

import app
from app import (
    F_ASS_CHAVE_IDEMPOTENCIA,
    F_ASS_HASH,
    F_ASS_STATUS,
    NOMES_DOCUMENTOS,
    TIPO_PACOTE_HOLERITE_PONTO,
    TIPOS_DOCUMENTO_VALIDOS,
    _extrair_competencia_folha_ponto,
    _gerar_comprovante_assinatura_pacote_pdf,
    _gerar_pacote_assinatura_holerite_ponto,
)
from app import app as flask_app


def _client():
    flask_app.testing = True
    return flask_app.test_client()


def _resp(ok=True, json_dict=None, status_code=200):
    r = Mock()
    r.ok = ok
    r.status_code = status_code
    r.json.return_value = json_dict or {}
    return r


PDF_SINTETICO_HOLERITE = b'%PDF-1.4\n' + b'holerite-sintetico-de-teste' * 5
PDF_SINTETICO_PONTO = b'%PDF-1.4\n' + b'folha-ponto-sintetica-de-teste' * 5

SHA_HOL = hashlib.sha256(PDF_SINTETICO_HOLERITE).hexdigest()
SHA_PONTO = hashlib.sha256(PDF_SINTETICO_PONTO).hexdigest()

FUNC_ID = 'recFUNC0000000001'
ARQ_HOL_ID = 'recARQHOLERITE0001'
ARQ_PONTO_ID = 'recARQPONTO000001'
ARQ_OUTRO_FUNC_ID = 'recFUNC0000000099'

TEXTO_HOLERITE_JUNHO = 'MAGNATA PORTARIA E SERVICOS\nMensalista Junho de 2026\nTotal de Vencimentos: 2000,00'
TEXTO_PONTO_JUNHO = 'CARTAO DE PONTO\nJunho de 2026\nEntrada Saida'
TEXTO_PONTO_JULHO = 'CARTAO DE PONTO\nJulho de 2026\nEntrada Saida'
TEXTO_PONTO_INTERVALO_JUNHO = 'CARTAO DE PONTO\nPeriodo: 01/06/2026 a 30/06/2026\nEntrada Saida'
TEXTO_SEM_COMPETENCIA = 'documento sem nenhuma competencia impressa'


def _arquivo_ok(func_id=FUNC_ID, filename='doc.pdf', url='https://static/doc.pdf'):
    return _resp(ok=True, json_dict={
        'fields': {
            'fldm6S1xnp8S6sKFE': [{'url': url, 'filename': filename}],  # F_ARQ_ATTACH
            'fldxbZwVNa01pchqF': [func_id],  # F_ARQ_FUNC
        },
    })


# ── 1. Whitelist / decisão arquitetural ──────────────────────────────────

def test_pacote_esta_na_whitelist():
    assert TIPO_PACOTE_HOLERITE_PONTO in TIPOS_DOCUMENTO_VALIDOS
    assert TIPO_PACOTE_HOLERITE_PONTO in NOMES_DOCUMENTOS


def test_holerite_isolado_nunca_e_valido():
    """Decisão documentada: HOLERITE sozinho nunca entra na whitelist --
    só dentro do pacote. Guarda de regressão contra reabrir o mesmo
    problema estrutural dos 65 registros "Holerite" órfãos encontrados
    na auditoria (tipo pré-v3.6, sem vínculo de competência a outro
    documento, hoje permanentemente travados)."""
    assert 'HOLERITE' not in TIPOS_DOCUMENTO_VALIDOS


def test_gerar_assinatura_core_ainda_rejeita_holerite_isolado():
    """Regressão: a função de documento único, não tocada por esta Macro,
    continua rejeitando 'HOLERITE' -- prova que a decisão arquitetural é
    reforçada em código, não só em comentário."""
    resultado, status = app._gerar_assinatura_core(
        funcionario_id=FUNC_ID, tipo_documento='HOLERITE', arquivo_record_id=ARQ_HOL_ID,
    )
    assert status == 400
    assert resultado['status'] == 'erro'


# ── 2. _extrair_competencia_folha_ponto (função pura) ────────────────────

def test_competencia_folha_ponto_formato_mes_extenso():
    folha_mensal, data_str = _extrair_competencia_folha_ponto(TEXTO_PONTO_JUNHO)
    assert folha_mensal == 'Junho 2026'
    assert data_str == '2026-06-01'


def test_competencia_folha_ponto_formato_numerico():
    folha_mensal, _ = _extrair_competencia_folha_ponto('Competência: 07/2026')
    assert folha_mensal == 'Julho 2026'


def test_competencia_folha_ponto_fallback_intervalo_de_datas():
    """Formato específico de cartão de ponto (sem "de AAAA" nem
    "Competência:") -- usa o mês da data FINAL do intervalo."""
    folha_mensal, data_str = _extrair_competencia_folha_ponto(TEXTO_PONTO_INTERVALO_JUNHO)
    assert folha_mensal == 'Junho 2026'
    assert data_str == '2026-06-01'


def test_competencia_folha_ponto_indeterminavel_retorna_none():
    """Nunca adivinha por proximidade -- se não achar nenhum padrão,
    retorna (None, None) explicitamente."""
    assert _extrair_competencia_folha_ponto(TEXTO_SEM_COMPETENCIA) == (None, None)
    assert _extrair_competencia_folha_ponto('') == (None, None)
    assert _extrair_competencia_folha_ponto(None) == (None, None)


# ── 3. _gerar_pacote_assinatura_holerite_ponto — validações de entrada ───

def test_pacote_sem_funcionario_id_e_erro_400():
    resultado, status = _gerar_pacote_assinatura_holerite_ponto(
        funcionario_id=None, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
    )
    assert status == 400
    assert resultado['status'] == 'erro'


def test_pacote_mesmo_arquivo_para_os_dois_documentos_e_erro_400():
    """Nunca aceita o mesmo Record ID como Holerite e Folha de Ponto --
    bloqueio contra documento duplicado/trocado antes de qualquer I/O."""
    resultado, status = _gerar_pacote_assinatura_holerite_ponto(
        funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_HOL_ID,
    )
    assert status == 400
    assert resultado['status'] == 'erro'


def test_pacote_whatsapp_ausente_com_disparo_solicitado_e_erro_400():
    with patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', None)):
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
            disparar_whatsapp=True,
        )
    assert status == 400
    assert resultado['erro'] == 'whatsapp_ausente'


def test_pacote_arquivo_holerite_nao_encontrado_e_erro_404():
    with patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', return_value=_resp(ok=False, status_code=404)):
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 404
    assert 'Holerite' in resultado['erro']


def test_pacote_arquivo_de_outro_funcionario_e_erro_403():
    with patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', return_value=_arquivo_ok(func_id=ARQ_OUTRO_FUNC_ID)):
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 403
    assert 'outro funcionário' in resultado['erro']


def test_pacote_arquivo_sem_attachment_e_erro_400():
    resp_sem_anexo = _resp(ok=True, json_dict={'fields': {
        'fldm6S1xnp8S6sKFE': [], 'fldxbZwVNa01pchqF': [FUNC_ID],
    }})
    with patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', return_value=resp_sem_anexo):
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 400
    assert 'attachment' in resultado['erro']


# ── 4. Validação de competência ──────────────────────────────────────────

def test_pacote_competencia_holerite_indeterminavel_bloqueia():
    with patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok()]), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_SEM_COMPETENCIA, TEXTO_PONTO_JUNHO]):
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 422
    assert resultado['erro'] == 'competencia_holerite_indeterminavel'


def test_pacote_competencia_folha_ponto_indeterminavel_bloqueia():
    with patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok()]), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_SEM_COMPETENCIA]):
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 422
    assert resultado['erro'] == 'competencia_folha_ponto_indeterminavel'


def test_pacote_competencias_divergentes_bloqueia_e_nao_cria_nada():
    """Holerite de Junho + Folha de Ponto de Julho -- nunca deve criar
    registro, mesmo com os dois documentos individualmente válidos."""
    with patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok()]), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JULHO]), \
         patch('app._criar_registro') as mock_criar:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 409
    assert resultado['erro'] == 'competencia_divergente'
    assert resultado['competencia_holerite'] == 'Junho 2026'
    assert resultado['competencia_folha_ponto'] == 'Julho 2026'
    mock_criar.assert_not_called()


# ── 5. Caminho feliz — dry_run e criação real ────────────────────────────

def test_pacote_dry_run_nao_cria_nada_e_mostra_os_2_documentos():
    with patch('app.requests.get', side_effect=[_arquivo_ok(filename='holerite.pdf'),
                                                 _arquivo_ok(filename='ponto.pdf')]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro') as mock_criar, \
         patch('app._anexar_attachment') as mock_anexar, \
         patch('app._evolution_enviar_texto') as mock_envia:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
            dry_run=True,
        )
    assert status == 200
    assert resultado['dry_run'] is True
    assert resultado['competencia'] == 'Junho 2026'
    assert resultado['holerite']['filename'] == 'holerite.pdf'
    assert resultado['folha_ponto']['filename'] == 'ponto.pdf'
    mock_criar.assert_not_called()
    mock_anexar.assert_not_called()
    mock_envia.assert_not_called()


def test_pacote_criacao_real_uma_solicitacao_um_token_dois_anexos():
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(),
                                                 _resp(ok=True, json_dict={'records': []})]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro', return_value='recASSINATURAPACOTE1') as mock_criar, \
         patch('app._anexar_attachment') as mock_anexar:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
            disparar_whatsapp=False,
        )
    assert status == 200
    assert resultado['status'] == 'ok'
    assert resultado['assinatura_id'] == 'recASSINATURAPACOTE1'
    assert resultado['tipo_documento'] == TIPO_PACOTE_HOLERITE_PONTO
    # UMA solicitação -> UM registro criado (não 2)
    assert mock_criar.call_count == 1
    campos_criados = mock_criar.call_args[0][1]
    assert campos_criados[F_ASS_STATUS] == 'PREPARADO'
    # Os 2 documentos vinculados na mesma chamada, delimitador documentado
    assert campos_criados[app.F_ASS_ARQUIVO_RECORD_ID] == f'{ARQ_HOL_ID}|{ARQ_PONTO_ID}'
    assert campos_criados[app.F_ASS_PDF_SHA256] == f'{SHA_HOL}|{SHA_PONTO}'
    # Os 2 PDFs originais anexados (dois documentos incluídos na transação)
    assert mock_anexar.call_count == 2


def test_pacote_disparo_whatsapp_envia_uma_unica_mensagem_mencionando_os_2_docs():
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(),
                                                 _resp(ok=True, json_dict={'records': []})]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro', return_value='recASSINATURAPACOTE2'), \
         patch('app._anexar_attachment'), \
         patch('app._evolution_enviar_texto') as mock_envia:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
            disparar_whatsapp=True,
        )
    assert status == 200
    assert resultado['whatsapp_disparo'] == 'enviado'
    mock_envia.assert_called_once()
    numero, mensagem = mock_envia.call_args[0]
    assert numero == '5511999999999'
    assert 'Holerite' in mensagem and 'Folha de Ponto' in mensagem
    assert mensagem.count('http') == 1  # um único link


def test_pacote_falha_evolution_no_disparo_nao_impede_registro_criado():
    """Falha parcial: registro criado, WhatsApp falhou -- nunca marca
    como sucesso silencioso; o retorno reporta a falha explicitamente."""
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(),
                                                 _resp(ok=True, json_dict={'records': []})]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro', return_value='recASSINATURAPACOTE3'), \
         patch('app._anexar_attachment'), \
         patch('app._evolution_enviar_texto', side_effect=RuntimeError('Evolution HTTP 500')):
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
            disparar_whatsapp=True,
        )
    assert status == 200
    assert resultado['assinatura_id'] == 'recASSINATURAPACOTE3'
    assert 'falha' in resultado['whatsapp_disparo']


# ── 6. Idempotência — cobre TODOS os estados (corrige a lacuna da auditoria) ─

@pytest.mark.parametrize('status_existente,status_http_esperado,chave_erro_esperada', [
    ('PREPARADO', 409, 'duplicado'),
    ('AGUARDANDO_ENVIO', 409, 'duplicado'),
    ('ENVIANDO', 409, 'duplicado'),
    ('ASSINADO', 409, 'erro'),
    ('EXPIRADO', 409, 'erro'),
    ('CANCELADO', 409, 'erro'),
])
def test_pacote_idempotencia_bloqueia_recriacao_por_estado(status_existente, status_http_esperado, chave_erro_esperada):
    resp_idempotencia = _resp(ok=True, json_dict={'records': [{
        'id': 'recASSINATURAEXISTENTE',
        'fields': {F_ASS_STATUS: status_existente, F_ASS_HASH: 'hashantigo123'},
    }]})
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(), resp_idempotencia]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro') as mock_criar:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == status_http_esperado
    assert resultado['status'] == chave_erro_esperada
    mock_criar.assert_not_called()  # nunca cria um 2º registro com a mesma chave


def test_pacote_idempotencia_retorna_link_existente_quando_ja_enviado():
    resp_idempotencia = _resp(ok=True, json_dict={'records': [{
        'id': 'recASSINATURAEXISTENTE2',
        'fields': {F_ASS_STATUS: 'ENVIADO_AGUARDANDO_ASSINATURA', F_ASS_HASH: 'hashjaenviado456'},
    }]})
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(), resp_idempotencia]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro') as mock_criar:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 200
    assert 'hashjaenviado456' in resultado['link']
    mock_criar.assert_not_called()


def test_pacote_idempotencia_falha_envio_permite_reenvio_sem_duplicar():
    resp_idempotencia = _resp(ok=True, json_dict={'records': [{
        'id': 'recASSINATURAEXISTENTE3',
        'fields': {F_ASS_STATUS: 'FALHA_ENVIO', F_ASS_HASH: 'hashfalhaenvio789'},
    }]})
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(), resp_idempotencia]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]), \
         patch('app._criar_registro') as mock_criar:
        resultado, status = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID,
        )
    assert status == 200
    assert resultado['status'] == 'ok'
    assert 'hashfalhaenvio789' in resultado['link']
    mock_criar.assert_not_called()  # reenvia o mesmo link, não recria pacote


def test_pacote_chamadas_repetidas_com_o_mesmo_par_geram_a_mesma_chave():
    """Reexecução idempotente: os mesmos 2 documentos, para o mesmo
    colaborador e competência, sempre produzem a MESMA chave de
    idempotência (funcionário + competência + tipo/hash Holerite +
    tipo/hash Ponto + versão) -- pré-requisito para o bloqueio acima
    funcionar de verdade."""
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(),
                                                 _resp(ok=True, json_dict={'records': []})]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]):
        resultado1, _ = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID, dry_run=True,
        )
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok(),
                                                 _resp(ok=True, json_dict={'records': []})]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano de Tal', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]):
        resultado2, _ = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID, dry_run=True,
        )
    assert resultado1['idempotency_key'] == resultado2['idempotency_key']


def test_pacote_colaborador_diferente_gera_chave_diferente():
    with patch('app.requests.get', side_effect=[_arquivo_ok(), _arquivo_ok()]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Fulano', '5511999999999')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]):
        resultado1, _ = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID, dry_run=True,
        )
    with patch('app.requests.get', side_effect=[_arquivo_ok(func_id=ARQ_OUTRO_FUNC_ID),
                                                 _arquivo_ok(func_id=ARQ_OUTRO_FUNC_ID)]), \
         patch('app._buscar_funcionario_nome_whatsapp', return_value=('Ciclano', '5511988888888')), \
         patch('app._at_throttle', lambda: None), \
         patch('app._carregar_documento_url', side_effect=[PDF_SINTETICO_HOLERITE, PDF_SINTETICO_PONTO]), \
         patch('app._extrair_texto_pdf_bytes', side_effect=[TEXTO_HOLERITE_JUNHO, TEXTO_PONTO_JUNHO]):
        resultado2, _ = _gerar_pacote_assinatura_holerite_ponto(
            funcionario_id=ARQ_OUTRO_FUNC_ID, arquivo_holerite_id=ARQ_HOL_ID, arquivo_ponto_id=ARQ_PONTO_ID, dry_run=True,
        )
    assert resultado1['idempotency_key'] != resultado2['idempotency_key']


# ── 7. Comprovante do pacote — cobre os 2 documentos e hashes ────────────

def test_comprovante_pacote_lista_os_2_documentos_e_2_hashes():
    pdf_bytes = _gerar_comprovante_assinatura_pacote_pdf(
        competencia='Junho 2026', func_nome='Fulano de Tal', ip='203.0.113.5',
        user_agent='TesteAgent/1.0', dt_str='01/07/2026 10:00', cpf4='1234',
        doc1_bytes=PDF_SINTETICO_HOLERITE, doc1_nome='holerite.pdf',
        doc2_bytes=PDF_SINTETICO_PONTO, doc2_nome='ponto.pdf',
    )
    assert pdf_bytes[:5] == b'%PDF-'

    import pdfplumber
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texto = '\n'.join((p.extract_text() or '') for p in pdf.pages)

    assert SHA_HOL in texto
    assert SHA_PONTO in texto
    assert 'holerite.pdf' in texto
    assert 'ponto.pdf' in texto
    assert 'Junho 2026' in texto

    # Normaliza quebras de linha do wrap do FPDF antes de checar frases —
    # o multi_cell insere \n no meio de frases longas.
    texto_normalizado = ' '.join(texto.lower().split())

    # Terminologia obrigatória: nunca afirma certificação ICP-Brasil
    assert 'assinatura eletrônica com evidências' in texto_normalizado
    assert 'icp-brasil' in texto_normalizado  # só aparece na frase que NEGA a certificação
    assert 'não de assinatura digital certificada icp-brasil' in texto_normalizado


# ── 8. Rota /assinatura/gerar — dispatch do pacote ───────────────────────

def test_rota_assinatura_gerar_pacote_sem_campos_obrigatorios_e_400():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._gerar_pacote_assinatura_holerite_ponto') as mock_core:
        resp = _client().post(
            '/assinatura/gerar',
            headers={'X-API-KEY': 'test'},
            json={'funcionario_id': FUNC_ID, 'tipo_documento': TIPO_PACOTE_HOLERITE_PONTO},
        )
    assert resp.status_code == 400
    mock_core.assert_not_called()


def test_rota_assinatura_gerar_pacote_despacha_para_core_correta():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, 'ok')), \
         patch('app._gerar_pacote_assinatura_holerite_ponto',
               return_value=({'status': 'ok', 'dry_run': True}, 200)) as mock_core:
        resp = _client().post(
            '/assinatura/gerar',
            headers={'X-API-KEY': 'test'},
            json={
                'funcionario_id': FUNC_ID, 'tipo_documento': TIPO_PACOTE_HOLERITE_PONTO,
                'arquivo_holerite_record_id': ARQ_HOL_ID, 'arquivo_folha_ponto_record_id': ARQ_PONTO_ID,
                'dry_run': True,
            },
        )
    assert resp.status_code == 200
    mock_core.assert_called_once()
    kwargs = mock_core.call_args.kwargs
    assert kwargs['funcionario_id'] == FUNC_ID
    assert kwargs['arquivo_holerite_id'] == ARQ_HOL_ID
    assert kwargs['arquivo_ponto_id'] == ARQ_PONTO_ID
    assert kwargs['dry_run'] is True


def test_rota_assinatura_gerar_pacote_sem_x_api_key_e_401():
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app._gerar_pacote_assinatura_holerite_ponto') as mock_core:
        resp = _client().post(
            '/assinatura/gerar',
            json={
                'funcionario_id': FUNC_ID, 'tipo_documento': TIPO_PACOTE_HOLERITE_PONTO,
                'arquivo_holerite_record_id': ARQ_HOL_ID, 'arquivo_folha_ponto_record_id': ARQ_PONTO_ID,
            },
        )
    assert resp.status_code == 401
    mock_core.assert_not_called()


def test_rota_assinatura_gerar_tipo_kit_admissao_continua_funcionando():
    """Regressão: dispatch de tipos existentes (não-pacote) não foi
    afetado pelo branch novo."""
    with patch('app.EMAIL_WEBHOOK_KEY', 'test'), \
         patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._validar_configuracao_assinatura_v36', return_value=(True, 'ok')), \
         patch('app._gerar_assinatura_core', return_value=({'status': 'ok'}, 200)) as mock_core_antiga, \
         patch('app._gerar_pacote_assinatura_holerite_ponto') as mock_core_pacote:
        resp = _client().post(
            '/assinatura/gerar',
            headers={'X-API-KEY': 'test'},
            json={'funcionario_id': FUNC_ID, 'tipo_documento': 'FOLHA_PONTO', 'arquivo_record_id': ARQ_PONTO_ID},
        )
    assert resp.status_code == 200
    mock_core_antiga.assert_called_once()
    mock_core_pacote.assert_not_called()


# ── 9. /assinatura/<hash> — carimbo dos 2 PDFs + comprovante único ───────

def _registro_pacote_pendente(status='Pendente', tentativas=0):
    return {
        'id': 'recASSINATURAPACOTEX',
        'fields': {
            'Nome': 'Holerite + Folha de Ponto - Junho 2026',
            'Status': status,
            'Tentativas': tentativas,
            'Tipo de Documento': TIPO_PACOTE_HOLERITE_PONTO,
            'Funcionário': [{'id': FUNC_ID}],
            'PDF SHA-256': f'{SHA_HOL}|{SHA_PONTO}',
            'Documento PDF': [
                {'id': 'attHOL', 'filename': 'holerite.pdf', 'url': 'https://static/holerite.pdf'},
                {'id': 'attPONTO', 'filename': 'ponto.pdf', 'url': 'https://static/ponto.pdf'},
            ],
        },
    }


def test_assinatura_pagina_pacote_confirmado_carimba_os_2_e_gera_1_comprovante():
    registro = _registro_pacote_pendente()
    resp_func = _resp(ok=True, json_dict={'fields': {'CPF': '111.222.333-44', 'Nome Completo': 'Fulano de Tal'}})
    resp_recheck = _resp(ok=True, json_dict={'fields': {'Status': 'Pendente'}})
    resp_patch_ok = _resp(ok=True)

    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._buscar_por_campo', return_value=registro), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[resp_func, resp_recheck, Mock(ok=True, content=PDF_SINTETICO_HOLERITE),
                                                 Mock(ok=True, content=PDF_SINTETICO_PONTO)]), \
         patch('app.requests.patch', return_value=resp_patch_ok), \
         patch('app._carimbar_pdf_assinado', side_effect=lambda b, *a: b) as mock_carimba, \
         patch('app._gerar_comprovante_assinatura_pacote_pdf', return_value=b'%PDF-comprovante') as mock_comprovante, \
         patch('app._anexar_attachment', return_value={'fields': {'Documento PDF': []}}) as mock_anexar:
        resp = _client().post('/assinatura/hashpacotefake123', data={'cpf': '3344'})

    assert resp.status_code == 200
    assert mock_carimba.call_count == 2  # os 2 PDFs, nunca 1 nem 3
    mock_comprovante.assert_called_once()
    # pelo menos: 2 carimbados + 1 comprovante em Assinaturas, +3 no Funcionário
    assert mock_anexar.call_count >= 6


def test_assinatura_pagina_pacote_cpf_incorreto_nao_carimba_nada():
    registro = _registro_pacote_pendente()
    resp_func = _resp(ok=True, json_dict={'fields': {'CPF': '111.222.333-44'}})

    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._buscar_por_campo', return_value=registro), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', return_value=resp_func), \
         patch('app.requests.patch', return_value=_resp(ok=True)), \
         patch('app._carimbar_pdf_assinado') as mock_carimba:
        resp = _client().post('/assinatura/hashpacotefake123', data={'cpf': '0000'})

    assert resp.status_code == 200  # página HTML de erro, não 500
    mock_carimba.assert_not_called()


def test_assinatura_pagina_pacote_expirado_apos_5_tentativas():
    registro = _registro_pacote_pendente(tentativas=4)
    resp_func = _resp(ok=True, json_dict={'fields': {'CPF': '111.222.333-44'}})

    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._buscar_por_campo', return_value=registro), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', return_value=resp_func), \
         patch('app.requests.patch', return_value=_resp(ok=True)) as mock_patch:
        resp = _client().post('/assinatura/hashpacotefake123', data={'cpf': '0000'})

    assert resp.status_code == 200
    campos_patch = mock_patch.call_args.kwargs['json']['fields']
    assert campos_patch.get(app.F_ASS_STATUS) == 'Expirado'


def test_assinatura_pagina_pacote_hash_trocado_bloqueia_carimbo():
    """Bloqueio contra documento trocado (exigência desta Macro): se o
    conteúdo baixado não corresponder ao par de hashes gravado na
    criação do pacote, aborta sem carimbar -- nunca carimba "o que
    tiver lá"."""
    registro = _registro_pacote_pendente()
    resp_func = _resp(ok=True, json_dict={'fields': {'CPF': '111.222.333-44', 'Nome Completo': 'Fulano de Tal'}})
    resp_recheck = _resp(ok=True, json_dict={'fields': {'Status': 'Pendente'}})
    conteudo_trocado = b'%PDF-1.4\nconteudo-completamente-diferente-do-esperado'

    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._buscar_por_campo', return_value=registro), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[resp_func, resp_recheck, Mock(ok=True, content=conteudo_trocado),
                                                 Mock(ok=True, content=conteudo_trocado)]), \
         patch('app.requests.patch', return_value=_resp(ok=True)), \
         patch('app._carimbar_pdf_assinado') as mock_carimba, \
         patch('app._gerar_comprovante_assinatura_pacote_pdf') as mock_comprovante:
        resp = _client().post('/assinatura/hashpacotefake123', data={'cpf': '3344'})

    assert resp.status_code == 200  # assinatura AINDA é registrada (não é falha do colaborador)
    mock_carimba.assert_not_called()
    mock_comprovante.assert_not_called()


def test_assinatura_pagina_pacote_ja_assinado_por_concorrencia_nao_reprocessa():
    """Concorrência/dupla execução: se, entre o GET inicial e a gravação,
    OUTRA requisição já confirmou a mesma assinatura, a checagem de
    concorrência detecta e devolve sucesso sem carimbar de novo."""
    registro = _registro_pacote_pendente(status='Pendente')
    resp_func = _resp(ok=True, json_dict={'fields': {'CPF': '111.222.333-44'}})
    resp_recheck_ja_assinado = _resp(ok=True, json_dict={
        'fields': {'Status': 'Assinado', 'Data/Hora Assinatura': '2026-07-01T10:00:00-03:00'},
    })

    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._buscar_por_campo', return_value=registro), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[resp_func, resp_recheck_ja_assinado]), \
         patch('app.requests.patch') as mock_patch, \
         patch('app._carimbar_pdf_assinado') as mock_carimba:
        resp = _client().post('/assinatura/hashpacotefake123', data={'cpf': '3344'})

    assert resp.status_code == 200
    mock_patch.assert_not_called()  # não regrava "Assinado" por cima
    mock_carimba.assert_not_called()


def test_assinatura_pagina_pacote_ja_assinado_no_get_mostra_sucesso_sem_form():
    registro = _registro_pacote_pendente(status='Assinado')
    registro['fields']['Data/Hora Assinatura'] = '2026-07-01T10:00:00-03:00'
    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._buscar_por_campo', return_value=registro):
        resp = _client().get('/assinatura/hashpacotefake123')
    assert resp.status_code == 200
    assert b'cpf' not in resp.data.lower() or b'form' not in resp.data.lower()


def test_assinatura_pagina_pacote_estrutura_inesperada_e_isolada_nao_derruba_requisicao():
    """Falha parcial isolada: se o registro tiver 1 anexo em vez de 2
    (estrutura inesperada), a assinatura já foi gravada -- a página
    responde 200 (não 500), e o caso fica só registrado em log para
    revisão manual, sem afetar outros colaboradores."""
    registro = _registro_pacote_pendente()
    registro['fields']['Documento PDF'] = [
        {'id': 'attHOL', 'filename': 'holerite.pdf', 'url': 'https://static/holerite.pdf'},
    ]
    resp_func = _resp(ok=True, json_dict={'fields': {'CPF': '111.222.333-44'}})
    resp_recheck = _resp(ok=True, json_dict={'fields': {'Status': 'Pendente'}})

    with patch('app.AIRTABLE_API_KEY', 'test'), \
         patch('app._buscar_por_campo', return_value=registro), \
         patch('app._at_throttle', lambda: None), \
         patch('app.requests.get', side_effect=[resp_func, resp_recheck]), \
         patch('app.requests.patch', return_value=_resp(ok=True)), \
         patch('app._carimbar_pdf_assinado') as mock_carimba:
        resp = _client().post('/assinatura/hashpacotefake123', data={'cpf': '3344'})

    assert resp.status_code == 200
    mock_carimba.assert_not_called()
